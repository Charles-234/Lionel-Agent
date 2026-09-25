"""
Lionel Agent - Command registry.
"""
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from skills import retriever

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    text: str
    is_error: bool = False


def cmd_help(args: List[str]) -> CommandResult:
    lines = [
        "Lionel commands:",
        "",
        "/help                        - this message",
        "/search <query>              - find skills by keyword",
        "/skill <name>                - print a full skill",
        "/skills                      - list skill counts by source",
        "/categories                  - list skill categories",
        "/sources                     - list skill sources",
        "/chat <message>              - AI chat with skill context",
        "/clear                       - clear conversation history",
        "/budget                      - show your token usage today",
        "/status                      - agent status (router, cooldowns)",
        "/ingest <url>                - fetch and index public TTP skill",
        "/schedule <sec> <desc>       - queue an autonomous task",
        "/scheduler_status            - show scheduled task queue",
        "/run <goal>                  - run an autonomous task",
    ]
    return CommandResult("\n".join(lines))


def cmd_search(args: List[str]) -> CommandResult:
    if not args:
        return CommandResult("Usage: /search <query>", is_error=True)
    query = " ".join(args)
    matches = retriever.search(query, top_k=10)
    if not matches:
        return CommandResult(f"No skills found for: {query}")
    lines = [f"Top {len(matches)} matches for {query!r}:", ""]
    for i, m in enumerate(matches, 1):
        desc = m.description[:140].replace("\n", " ")
        lines.append(f"{i}. [{m.source}] {m.name}")
        lines.append(f"   {desc}")
        lines.append("")
    lines.append("Use: /skill <name>  to load one")
    return CommandResult("\n".join(lines))


def cmd_skill(args: List[str]) -> CommandResult:
    if not args:
        return CommandResult("Usage: /skill <name>", is_error=True)
    name = " ".join(args)
    content = retriever.get_retriever().load_skill_by_name(name)
    if content is None:
        return CommandResult(f"Skill not found: {name}", is_error=True)
    if len(content) > 8000:
        content = content[:8000] + "\n\n... (truncated)"
    return CommandResult(content)


def cmd_skills(args: List[str]) -> CommandResult:
    sources = retriever.list_sources()
    total = sum(sources.values())
    lines = [f"Total skills: {total}", ""]
    for source, count in sorted(sources.items()):
        lines.append(f"  {source:12s} {count}")
    return CommandResult("\n".join(lines))


def cmd_categories(args: List[str]) -> CommandResult:
    cats = retriever.list_categories()
    lines = [f"Categories ({len(cats)} total):", ""]
    for cat, count in sorted(cats.items(), key=lambda x: -x[1])[:30]:
        lines.append(f"  {count:5d}  {cat}")
    return CommandResult("\n".join(lines))


def cmd_sources(args: List[str]) -> CommandResult:
    from config import SKILL_SOURCES
    lines = ["Skill sources:", ""]
    for name, cfg in SKILL_SOURCES.items():
        lines.append(f"  {name:12s} root={cfg.get('root', '?')}")
    return CommandResult("\n".join(lines))


def cmd_status(args: List[str]) -> CommandResult:
    from providers import router
    lines = ["Lionel status:", ""]
    state = router.router_state()
    if not state:
        lines.append("  Router: all models healthy")
    else:
        lines.append("  Router: models in cooldown:")
        for model, status in state.items():
            lines.append(f"    {model}: {status}")
    return CommandResult("\n".join(lines))


def cmd_chat(args: List[str]) -> CommandResult:
    """Simple CLI chat. Real chat runs through telegram/CLI in the wrapper."""
    if not args:
        return CommandResult("Usage: /chat <message>", is_error=True)
    message = " ".join(args)
    from agent.chat import chat
    # Use 0 as user_id for CLI (non-admin)
    resp = chat(user_id=0, user_message=message, include_skills=True)
    lines = [resp.text, ""]
    lines.append(f"[{resp.provider}/{resp.model} | {resp.tokens_used} tokens | {len(resp.skills_used)} skills]")
    return CommandResult("\n".join(lines), is_error=bool(resp.error))


def cmd_clear(args: List[str]) -> CommandResult:
    from memory import history
    history.clear(0)
    return CommandResult("History cleared.")


def cmd_budget(args: List[str]) -> CommandResult:
    from providers import token_budget
    s = token_budget.stats(0)
    lines = [
        "Token budget today:",
        f"  used:      {s['used']}",
        f"  cap:       {s['cap']}",
        f"  remaining: {s['remaining']}",
    ]
    return CommandResult("\n".join(lines))


def cmd_ingest(args: List[str]) -> CommandResult:
    if not args:
        return CommandResult("Usage: /ingest <url>", is_error=True)
    url = args[0].strip().strip("\"'")
    from skills.ingest import ingest_url
    res = ingest_url(url)
    return CommandResult(res.message, is_error=not res.success)


def cmd_schedule(args: List[str]) -> CommandResult:
    """Queue an autonomous task. Usage: /schedule <seconds> <description>"""
    if not args or len(args) < 2:
        return CommandResult(
            "Usage: /schedule <seconds> <description>\n"
            "Example: /schedule 60 scan example.com\n"
            "The description is passed to the agent runtime for planning.",
            is_error=True,
        )
    try:
        delay = float(args[0])
    except ValueError:
        return CommandResult("First argument must be a number of seconds.", is_error=True)
    description = " ".join(args[1:])

    from agent.scheduler import get_scheduler, schedule_task

    def _run():
        from tools.executor import execute
        from tools.policy import AuthorizationScope
        # Pass through to the recon chain if it looks like a domain scan
        from chains.recon import run as recon_run
        import re
        domain_match = re.search(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
            description,
        )
        if domain_match:
            domain = domain_match.group(0)
            scope = AuthorizationScope.for_targets(
                "system:scheduled",
                [domain],
                allow_network=True,
                max_risk="high",
                reason=f"Scheduled recon: {domain}",
            )
            return recon_run(domain, scope=scope, execution_mode="real")
        return {"status": "skipped", "reason": "No domain target found in description"}

    task_id = schedule_task(description, _run, delay_seconds=delay)
    return CommandResult(f"Scheduled task {task_id}: {description} (in {delay}s)")


def cmd_scheduler_status(args: List[str]) -> CommandResult:
    """Show scheduled task status."""
    from agent.scheduler import scheduler_stats
    s = scheduler_stats()
    lines = [
        "Scheduler status:",
        f"  Uptime: {s['uptime_seconds']}s",
        f"  Queued: {s['total_queued']}",
        f"  Completed: {s['total_completed']}",
        f"  Failed: {s['total_failed']}",
        f"  Running now: {s['running_now']}",
    ]
    if s["tasks"]:
        lines.append("")
        lines.append("Pending tasks:")
        for t in s["tasks"]:
            lines.append(
                f"  {t['task_id']}: {t['description'][:60]} "
                f"[{t['status']} in {max(0, t['run_at'] - __import__('time').time()):.0f}s]"
            )
    else:
        lines.append("  (no pending tasks)")
    return CommandResult("\n".join(lines))


def cmd_run(args: List[str]) -> CommandResult:
    """Run an autonomous goal. Usage: /run <goal description>"""
    if not args:
        return CommandResult(
            "Usage: /run <goal description>\n"
            "Example: /run scan example.com for subdomains and live hosts\n"
            "The agent will plan, execute, and report results autonomously.",
            is_error=True,
        )
    goal = " ".join(args)

    from agent.autonomous import autonomous_run

    result = autonomous_run(goal, user_id=0)

    lines = [
        f"Goal: {goal}",
        f"Status: {'SUCCESS' if result.success else 'FAILED'}",
        f"Summary: {result.final_summary}",
        f"Duration: {result.total_duration_ms}ms",
        f"Steps: {result.steps_succeeded} succeeded, {result.steps_failed} failed (total {result.total_steps})",
        "",
        "Turns:",
    ]
    for turn in result.turns:
        lines.append(f"  Turn {turn.turn_index}: {turn.status} — {len(turn.plan)} steps")
        for step in turn.plan:
            icon = {"succeeded": "+", "failed": "!", "skipped": "-", "running": "?"}.get(
                step.status, "?"
            )
            lines.append(f"    [{icon}] {step.description[:80]}")
            if step.error:
                lines.append(f"        Error: {step.error[:100]}")

    return CommandResult("\n".join(lines))


COMMANDS: Dict[str, Callable[[List[str]], CommandResult]] = {
    "help": cmd_help,
    "search": cmd_search,
    "skill": cmd_skill,
    "skills": cmd_skills,
    "categories": cmd_categories,
    "sources": cmd_sources,
    "status": cmd_status,
    "chat": cmd_chat,
    "clear": cmd_clear,
    "budget": cmd_budget,
    "ingest": cmd_ingest,
    "schedule": cmd_schedule,
    "scheduler_status": cmd_scheduler_status,
    "run": cmd_run,
}


def parse_and_dispatch(text: str) -> Optional[CommandResult]:
    if not text or not text.startswith("/"):
        return None
    parts = text[1:].strip().split()
    if not parts:
        return CommandResult("Type /help for commands")
    cmd = parts[0].lower()
    args = parts[1:]
    handler = COMMANDS.get(cmd)
    if handler is None:
        return CommandResult(f"Unknown command: /{cmd}. Type /help.", is_error=True)
    try:
        return handler(args)
    except Exception:
        # Full diagnostics go to server logs only; the reply stays generic.
        logger.exception("Command '/%s' failed", cmd)
        return CommandResult("That command could not be completed. Try /help.", is_error=True)