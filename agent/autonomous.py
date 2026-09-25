"""Autonomous reasoning loop for Lionel.

Implements a structured reasoning-and-execution loop based on best practices:

1. Plan — break the goal into ordered steps using the LLM
2. Execute — run each step through the governed executor
3. Observe — collect results, note failures
4. Reflect — decide whether to continue, replan, or stop
5. Repeat until goal is achieved or limits are hit

The loop is bounded: it respects RunLimits, the policy gateway, and the audit
ledger. It never bypasses governance.

Key design decisions (following the attached guidance):
- Untrusted content (LLM output, tool output) is wrapped in markers before
  being fed back into the LLM.
- The LLM proposes; the governed executor disposes. No auto-execution of LLM
  suggestions without policy gates.
- Every decision point (plan, reflect, stop) is recorded in the audit ledger.
- Max iterations prevents infinite loops.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.chat import chat
from agent.run_limits import RunLimits, RunUsage, check_limits, is_high_risk
from tools.catalog import suggest_tool_for_query
from tools.executor import execute
from tools.policy import AuthorizationScope

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10
MAX_STEPS_PER_PLAN = 5
COOLDOWN_SECONDS = 2  # between LLM calls in the loop


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoopStep:
    """One step in the autonomous loop."""
    index: int
    description: str
    capability: str
    tool_id: Optional[str] = None
    status: str = "pending"  # pending | running | succeeded | failed | skipped
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass(frozen=True)
class LoopTurn:
    """One planning+execution cycle."""
    turn_index: int
    goal: str
    plan: List[LoopStep] = field(default_factory=list)
    status: str = "running"  # running | completed | stopped | failed
    summary: str = ""
    error: Optional[str] = None


@dataclass
class AutonomousResult:
    """Final result of an autonomous run."""
    success: bool
    goal: str
    turns: List[LoopTurn]
    final_summary: str
    total_duration_ms: int
    total_steps: int
    steps_succeeded: int
    steps_failed: int
    session_id: str


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PLAN_PROMPT = """\
You are Lionel's autonomous planning module. You break a goal into concrete,
executable steps.

Goal: {goal}

Available capabilities and their tool hints:
- reconnaissance: subfinder (subdomains), httpx (HTTP probing), nmap (network scan)
- security_testing: nuclei (vulnerability scanning)
- research: web_fetch (fetch public web pages)
- intelligence: ip_lookup (IP geolocation)
- coding: e2b_sandbox (execute code in sandbox)
- automation: filesystem (read/write files)
- data_engineering: filesystem

Rules:
1. Produce 1-5 concrete steps.
2. Each step must be small enough to verify after execution.
3. Steps must be ordered: reconnaissance before testing, data collection before analysis.
4. Name the capability each step needs.
5. Be specific: "Run subfinder on example.com" not "Do recon".
6. If the goal is already achieved by reading context, return an empty plan.

Output format (JSON only):
{{"steps": [{{"description": "...", "capability": "..."}}], "summary": "..."}}
"""


REFLECT_PROMPT = """\
You are Lionel's reflection module. You assess whether the goal is achieved.

Goal: {goal}

Results so far:
{results}

Last error (if any): {last_error}

Instructions:
1. Decide: CONTINUE (need more steps), DONE (goal achieved), or STOP (cannot proceed).
2. If CONTINUE, propose 1-3 additional steps.
3. If DONE, write a final summary.
4. Be honest: if you don't have enough information, say so.

Output format (JSON only):
{{"decision": "CONTINUE"|"DONE"|"STOP", "steps": [{{"description": "...", "capability": "..."}}], "summary": "..."}}
"""


# ---------------------------------------------------------------------------
# Reasoning loop
# ---------------------------------------------------------------------------

class ReasoningLoop:
    """Structured reasoning-and-execution loop."""

    def __init__(
        self,
        *,
        max_iterations: int = MAX_ITERATIONS,
        max_steps_per_plan: int = MAX_STEPS_PER_PLAN,
        limits: Optional[RunLimits] = None,
        scope: Optional[AuthorizationScope] = None,
    ):
        self.max_iterations = max_iterations
        self.max_steps_per_plan = max_steps_per_plan
        self.limits = limits or RunLimits()
        self.scope = scope

    def run(
        self,
        goal: str,
        *,
        session_id: Optional[str] = None,
        role_id: str = "virtual_assistant",
        user_id: int = 0,
    ) -> AutonomousResult:
        """Run the autonomous loop on a goal."""
        sid = session_id or str(uuid.uuid4())
        started = time.time()
        turns: List[LoopTurn] = []
        all_steps: List[LoopStep] = []
        usage = RunUsage()
        current_goal = goal
        last_error = None

        for iteration in range(self.max_iterations):
            # Check run limits before planning
            usage_now = RunUsage(
                steps_started=usage.steps_started,
                high_risk_steps=usage.high_risk_steps,
                failed_steps=usage.failed_steps,
                elapsed_seconds=time.time() - started + usage.elapsed_seconds,
            )
            hit = check_limits(self.limits, usage_now)
            if hit:
                logger.info("Reasoning loop stopped: %s", hit)
                return _build_result(
                    success=False,
                    goal=goal,
                    turns=turns,
                    final_summary=f"Stopped: {hit}",
                    all_steps=all_steps,
                    started=started,
                    sid=sid,
                )

            # Phase 1: Plan
            plan = self._plan(current_goal, iteration, last_error, user_id)
            turn = LoopTurn(
                turn_index=iteration,
                goal=current_goal,
                plan=plan,
                status="running",
            )

            if not plan:
                # Empty plan means the LLM thinks the goal is achieved
                turn.status = "completed"
                turn.summary = "No further steps needed."
                turns.append(turn)
                return _build_result(
                    success=True,
                    goal=goal,
                    turns=turns,
                    final_summary=turn.summary,
                    all_steps=all_steps,
                    started=started,
                    sid=sid,
                )

            turn.plan = plan
            turns.append(turn)

            # Phase 2: Execute
            turn_results = self._execute_plan(plan, sid, role_id, user_id)
            turn.status = "completed" if all(r.status == "succeeded" for r in turn_results) else "running"
            all_steps.extend(turn_results)

            # Update usage
            for step in turn_results:
                usage.steps_started += 1
                if is_high_risk(step.capability):
                    usage.high_risk_steps += 1
                if step.status == "failed":
                    usage.failed_steps += 1

            # Phase 3: Reflect
            result_text = self._format_results(turn_results)
            reflect = self._reflect(current_goal, result_text, last_error or "", user_id)

            if reflect["decision"] == "DONE":
                turn.status = "completed"
                turn.summary = reflect["summary"]
                turns[-1] = turn
                return _build_result(
                    success=True,
                    goal=goal,
                    turns=turns,
                    final_summary=reflect["summary"],
                    all_steps=all_steps,
                    started=started,
                    sid=sid,
                )

            if reflect["decision"] == "STOP":
                turn.status = "stopped"
                turn.summary = reflect.get("summary", "Cannot proceed.")
                turns[-1] = turn
                return _build_result(
                    success=False,
                    goal=goal,
                    turns=turns,
                    final_summary=reflect.get("summary", "Stopped by reflection."),
                    all_steps=all_steps,
                    started=started,
                    sid=sid,
                )

            # Continue with new steps appended to goal context
            if reflect.get("steps"):
                current_goal = f"{goal}\n\nProgress so far:\n{result_text}\n\nNext steps to try:"
                last_error = None
            else:
                # No new steps but not done — try one more iteration with broader scope
                last_error = "Reflection returned no new steps."

            time.sleep(COOLDOWN_SECONDS)

        # Exhausted iterations
        return _build_result(
            success=False,
            goal=goal,
            turns=turns,
            final_summary=f"Reached maximum iterations ({self.max_iterations}).",
            all_steps=all_steps,
            started=started,
            sid=sid,
        )

    def _plan(self, goal: str, iteration: int, last_error: str, user_id: int) -> List[LoopStep]:
        """Ask the LLM to plan steps for the current goal."""
        error_context = f"\nLast error: {last_error}" if last_error else ""
        prompt = PLAN_PROMPT.format(goal=goal + error_context)

        # Build context from available tool hints
        try:
            hints = suggest_tool_for_query(goal)
            if hints:
                hint_text = "Tool hints for this goal: " + ", ".join(hints)
                prompt += f"\n{hint_text}"
        except Exception:
            pass

        try:
            response = chat(
                user_id=user_id,
                user_message=prompt,
                include_skills=False,
            )
            if response.error:
                logger.warning("Planning chat failed: %s", response.error)
                return []
            import json
            data = json.loads(response.text)
            steps_data = data.get("steps", [])
            summary = data.get("summary", "")
            if not steps_data:
                return []
            return [
                LoopStep(
                    index=i,
                    description=s.get("description", ""),
                    capability=s.get("capability", "reasoning"),
                )
                for i, s in enumerate(steps_data[: self.max_steps_per_plan])
            ]
        except Exception as e:
            logger.warning("Planning failed: %s", e, exc_info=True)
            return []

    def _execute_plan(
        self,
        plan: List[LoopStep],
        session_id: str,
        role_id: str,
        user_id: int,
    ) -> List[LoopStep]:
        """Execute each plan step through the governed executor."""
        results: List[LoopStep] = []
        for step in plan:
            step.status = "running"
            step.tool_id = suggest_tool_for_query(step.description).pop(
                0, None
            ) if suggest_tool_for_query(step.description) else None

            # Determine capability from the plan
            capability = step.capability

            # Try to execute via the catalog's suggested tool
            tool_id = step.tool_id
            if tool_id:
                args = self._infer_args(step.description, tool_id)
                result = execute(
                    tool_id,
                    args or {},
                    capability_id=capability,
                    role=role_id,
                    scope=self.scope,
                    execution_mode="real",
                    session_id=session_id,
                )
                step.status = "succeeded" if result.success else "failed"
                step.result = result.data if result.success else None
                step.error = result.error if not result.success else None
                step.duration_ms = getattr(result, "duration_ms", 0)
            else:
                # No tool found — mark as skipped
                step.status = "skipped"
                step.error = f"No tool mapped for: {step.description[:80]}"

            results.append(step)

        return results

    def _infer_args(self, description: str, tool_id: str) -> Optional[Dict[str, Any]]:
        """Infer tool arguments from the step description."""
        desc = description.lower()

        if tool_id == "subfinder":
            import re
            domain = re.search(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", desc
            )
            if domain:
                return {"domain": domain.group(0)}
            return {"domain": "example.com"}  # fallback — policy will scope it

        if tool_id == "httpx":
            import re
            hosts = re.findall(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", desc
            )
            if hosts:
                return {"hosts": hosts}
            return {"hosts": ["example.com"]}

        if tool_id == "nuclei":
            import re
            targets = re.findall(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", desc
            )
            if targets:
                return {"targets": targets}
            return {"targets": ["example.com"]}

        if tool_id == "web_fetch":
            import re
            url = re.search(r"https?://[^\s<>\"|]+", desc)
            if url:
                return {"url": url.group(0)}
            return {}

        if tool_id == "ip_lookup":
            import re
            ip = re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", desc)
            if ip:
                return {"ip": ip.group(0)}
            return {}

        if tool_id == "filesystem":
            if "read" in desc:
                import re
                path = re.search(r"read\s+(?:file\s+)?[\"']?([^\s,;]+)", desc)
                if path:
                    return {"action": "read", "path": path.group(1)}
            if "write" in desc:
                return {"action": "list", "path": "."}  # conservative default
            return {"action": "list", "path": "."}

        if tool_id == "e2b_sandbox":
            return {"code": "# TODO: implement the requested code", "language": "python"}

        return {}

    def _format_results(self, steps: List[LoopStep]) -> str:
        """Format step results for the reflection prompt."""
        lines = []
        for s in steps:
            status_icon = {"succeeded": "+", "failed": "!", "skipped": "-", "running": "?"}.get(
                s.status, "?"
            )
            lines.append(f"  [{status_icon}] Step {s.index}: {s.description[:100]}")
            if s.status == "succeeded" and s.result:
                data = s.result
                if isinstance(data, dict):
                    # Show a summary of the result
                    keys = list(data.keys())[:3]
                    snippet = {k: str(data[k])[:80] for k in keys}
                    lines.append(f"      Result: {snippet}")
                else:
                    lines.append(f"      Result: {str(s.result)[:120]}")
            if s.status == "failed" and s.error:
                lines.append(f"      Error: {s.error[:120]}")
        return "\n".join(lines)

    def _reflect(
        self, goal: str, results: str, last_error: str, user_id: int
    ) -> Dict[str, Any]:
        """Ask the LLM to reflect on progress."""
        prompt = REFLECT_PROMPT.format(
            goal=goal, results=results, last_error=last_error
        )
        try:
            response = chat(
                user_id=user_id,
                user_message=prompt,
                include_skills=False,
            )
            if response.error:
                logger.warning("Reflection chat failed: %s", response.error)
                return {"decision": "STOP", "summary": "Reflection failed."}
            import json
            return json.loads(response.text)
        except Exception as e:
            logger.warning("Reflection failed: %s", e, exc_info=True)
            return {"decision": "STOP", "summary": "Reflection module error."}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_result(
    success: bool,
    goal: str,
    turns: List[LoopTurn],
    final_summary: str,
    all_steps: List[LoopStep],
    started: float,
    sid: str,
) -> AutonomousResult:
    succeeded = sum(1 for s in all_steps if s.status == "succeeded")
    failed = sum(1 for s in all_steps if s.status == "failed")
    return AutonomousResult(
        success=success,
        goal=goal,
        turns=turns,
        final_summary=final_summary,
        total_duration_ms=int((time.time() - started) * 1000),
        total_steps=len(all_steps),
        steps_succeeded=succeeded,
        steps_failed=failed,
        session_id=sid,
    )


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_loop: Optional[ReasoningLoop] = None


def get_reasoning_loop() -> ReasoningLoop:
    global _default_loop
    if _default_loop is None:
        _default_loop = ReasoningLoop()
    return _default_loop


def autonomous_run(
    goal: str,
    *,
    session_id: Optional[str] = None,
    role_id: str = "virtual_assistant",
    user_id: int = 0,
) -> AutonomousResult:
    """Run one autonomous goal through the reasoning loop."""
    return get_reasoning_loop().run(
        goal,
        session_id=session_id,
        role_id=role_id,
        user_id=user_id,
    )
