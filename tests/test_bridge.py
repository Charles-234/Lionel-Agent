"""Focused tests for the decision-to-runner bridge.

The bridge carries a finished plan from one desk to the other. It must
refuse anything that is not ready, and it must never add permission or
repeat safety checks that belong to the runner and the governed executor.
"""

import unittest

from agent.bridge import (
    BRIDGE_DECISION_NOT_READY_MESSAGE,
    BRIDGE_DECISION_REQUIRED_MESSAGE,
    BRIDGE_EXECUTION_MODE_MESSAGE,
    BRIDGE_PLAN_REQUIRED_MESSAGE,
    BRIDGE_ROLE_REQUIRED_MESSAGE,
    BRIDGE_SESSION_REQUIRED_MESSAGE,
    BridgeError,
    can_run,
    describe_decision,
    run_decision,
    summarize_run,
)
from agent.planner import Plan, PlanStep
from agent.request_normalizer import NormalizedRequest
from agent.role_selector import RoleSelection
from agent.runtime import AgentDecision, AgentRuntime
from agent.run_limits import RunLimits


def _ready_decision():
    return AgentRuntime().decide(
        "Look up public info on the authorized target",
        task_type="intelligence",
        step_descriptions=["Gather public threat notes", "Summarize findings"],
    )


class BridgeTests(unittest.TestCase):
    def test_refuses_missing_decision(self):
        with self.assertRaises(BridgeError) as ctx:
            run_decision(None, session_id="s-bridge")
        self.assertEqual(str(ctx.exception), BRIDGE_DECISION_REQUIRED_MESSAGE)

    def test_refuses_decision_that_is_not_ready(self):
        runtime = AgentRuntime()
        decision = runtime.decide("Help me review this")
        self.assertNotEqual(decision.status, "PLAN_READY")
        with self.assertRaises(BridgeError) as ctx:
            run_decision(decision, session_id="s-bridge")
        self.assertEqual(str(ctx.exception), BRIDGE_DECISION_NOT_READY_MESSAGE)

    def test_refuses_decision_without_plan(self):
        decision = AgentDecision(
            status="PLAN_READY",
            message="ready",
            request=NormalizedRequest(
                raw_text="hi", objective="hi", task_type="coding"
            ),
            role_selection=RoleSelection(
                status="SELECTED",
                task_type="coding",
                role_id="software_ai_architecture",
                candidate_role_ids=("software_ai_architecture",),
            ),
            plan=None,
        )
        with self.assertRaises(BridgeError) as ctx:
            run_decision(decision, session_id="s-bridge")
        self.assertEqual(str(ctx.exception), BRIDGE_PLAN_REQUIRED_MESSAGE)

    def test_refuses_decision_without_single_role(self):
        decision = AgentDecision(
            status="PLAN_READY",
            message="ready",
            request=NormalizedRequest(
                raw_text="hi", objective="hi", task_type="reconnaissance"
            ),
            role_selection=RoleSelection(
                status="AMBIGUOUS",
                task_type="reconnaissance",
                role_id=None,
                candidate_role_ids=("a", "b"),
            ),
            plan=Plan(
                task_type="reconnaissance",
                objective="hi",
                steps=[PlanStep(description="one", capability="reconnaissance")],
            ),
        )
        with self.assertRaises(BridgeError) as ctx:
            run_decision(decision, session_id="s-bridge")
        self.assertEqual(str(ctx.exception), BRIDGE_ROLE_REQUIRED_MESSAGE)

    def test_refuses_blank_session_before_runner(self):
        decision = _ready_decision()

        calls = []

        class NoRunRunner:
            def run(self, **kwargs):
                calls.append(kwargs)
                raise AssertionError("runner must not be reached")

        with self.assertRaises(BridgeError) as ctx:
            run_decision(decision, session_id="  ", runner=NoRunRunner())
        self.assertEqual(str(ctx.exception), BRIDGE_SESSION_REQUIRED_MESSAGE)
        self.assertEqual(calls, [])

    def test_refuses_bad_execution_mode_before_runner(self):
        decision = _ready_decision()

        calls = []

        class NoRunRunner:
            def run(self, **kwargs):
                calls.append(kwargs)
                raise AssertionError("runner must not be reached")

        with self.assertRaises(BridgeError) as ctx:
            run_decision(
                decision, session_id="s-bridge", execution_mode="fast",
                runner=NoRunRunner(),
            )
        self.assertEqual(str(ctx.exception), BRIDGE_EXECUTION_MODE_MESSAGE)
        self.assertEqual(calls, [])

    def test_carries_ready_decision_to_runner_in_simulation(self):
        decision = AgentDecision(
            status="PLAN_READY",
            message="ready",
            request=NormalizedRequest(
                raw_text="Enumerate subdomains",
                objective="Enumerate subdomains",
                task_type="reconnaissance",
            ),
            role_selection=RoleSelection(
                status="SELECTED",
                task_type="reconnaissance",
                role_id="offensive_security",
                candidate_role_ids=("offensive_security",),
            ),
            plan=Plan(
                task_type="reconnaissance",
                objective="Enumerate subdomains",
                steps=[PlanStep(description="recon step", capability="reconnaissance")],
            ),
        )
        result = run_decision(
            decision,
            session_id="s-bridge-ready",
            arguments=[{"domain": "example.com"}],
            execution_mode="simulation",
            limits=RunLimits(),
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.session_id, "s-bridge-ready")
        self.assertTrue(result.all_succeeded)

    def test_bridge_never_runs_a_non_ready_decision(self):
        runtime = AgentRuntime()
        decision = runtime.decide(
            "Implement the requested feature",
            task_type="coding",
        )
        self.assertEqual(decision.status, "PLAN_REQUIRED")

        calls = []

        class NoRunRunner:
            def run(self, **kwargs):
                calls.append(kwargs)
                raise AssertionError("runner must not be reached")

        with self.assertRaises(BridgeError):
            run_decision(decision, session_id="s-bridge", runner=NoRunRunner())
        self.assertEqual(calls, [])

    def test_describe_and_can_run_share_one_check(self):
        runtime = AgentRuntime()
        not_ready = runtime.decide("Help me review this")
        self.assertFalse(can_run(not_ready))
        self.assertEqual(
            describe_decision(not_ready), BRIDGE_DECISION_NOT_READY_MESSAGE
        )
        self.assertEqual(describe_decision(None), BRIDGE_DECISION_REQUIRED_MESSAGE)

    def test_summarize_run_uses_counts_only(self):
        decision = AgentDecision(
            status="PLAN_READY",
            message="ready",
            request=NormalizedRequest(
                raw_text="Enumerate subdomains",
                objective="Enumerate subdomains",
                task_type="reconnaissance",
            ),
            role_selection=RoleSelection(
                status="SELECTED",
                task_type="reconnaissance",
                role_id="offensive_security",
                candidate_role_ids=("offensive_security",),
            ),
            plan=Plan(
                task_type="reconnaissance",
                objective="Enumerate subdomains",
                steps=[PlanStep(description="recon step", capability="reconnaissance")],
            ),
        )
        result = run_decision(
            decision,
            session_id="s-bridge-summary",
            arguments=[{"domain": "example.com"}],
            execution_mode="simulation",
            limits=RunLimits(),
        )
        self.assertTrue(can_run(decision))
        self.assertIn("Ready to run 1 step", describe_decision(decision))
        line = summarize_run(result)
        self.assertIn("Finished all 1 step", line)
        self.assertNotIn("example.com", line)


if __name__ == "__main__":
    unittest.main()
