"""Focused tests for the bounded multi-step runner (Phase 5).

The runner walks a plan step by step through the single governed executor.
These tests assert the loop's own contract only: stop conditions,
confirmation pause/resume, and denial paths.  Policy, registry, and audit
behavior remain covered by their own suites.
"""

import unittest

from agent.confirmations import ConfirmationStore
from agent.planner import Plan, PlanStep
from agent.run_limits import RunLimits, RunUsage
from agent.runner import BoundedRunner


def _recon_plan(n=2):
    return Plan(
        task_type="reconnaissance",
        objective="Enumerate subdomains for an authorized domain",
        steps=[
            PlanStep(
                description=f"recon step {i}",
                capability="reconnaissance",
                requires_tool=True,
            )
            for i in range(n)
        ],
        execution_allowed=False,
    )


def _args(n=2):
    return [{"domain": "example.com"} for _ in range(n)]


class BoundedRunnerTests(unittest.TestCase):
    def test_completes_simulation_run(self):
        runner = BoundedRunner()
        result = runner.run(
            session_id="s-complete",
            role_id="offensive_security",
            plan=_recon_plan(2),
            arguments=_args(2),
            execution_mode="simulation",
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertTrue(result.all_succeeded)
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.usage.steps_started, 2)

    def test_step_limit_stops_before_extra_steps(self):
        runner = BoundedRunner()
        result = runner.run(
            session_id="s-step-limit",
            role_id="offensive_security",
            plan=_recon_plan(3),
            arguments=_args(3),
            execution_mode="simulation",
            limits=RunLimits(max_steps=1),
        )
        self.assertEqual(result.status, "STOPPED_STEP_LIMIT")
        self.assertEqual(len(result.steps), 1)

    def test_duration_limit_stops_without_executing(self):
        runner = BoundedRunner()
        result = runner.run(
            session_id="s-duration",
            role_id="offensive_security",
            plan=_recon_plan(2),
            arguments=_args(2),
            execution_mode="simulation",
            usage=RunUsage(elapsed_seconds=9999.0),
        )
        self.assertEqual(result.status, "STOPPED_DURATION_LIMIT")
        self.assertEqual(result.steps, [])

    def test_failure_tolerance_counts_failed_steps(self):
        runner = BoundedRunner()
        result = runner.run(
            session_id="s-fail",
            role_id="frontend_developer",  # denied for reconnaissance
            plan=_recon_plan(2),
            arguments=_args(2),
            execution_mode="simulation",
            limits=RunLimits(max_failed_steps=5),
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertFalse(result.all_succeeded)
        self.assertEqual(result.usage.failed_steps, 2)

    def test_failure_limit_stops_after_tolerance_exceeded(self):
        runner = BoundedRunner()
        result = runner.run(
            session_id="s-fail-limit",
            role_id="frontend_developer",
            plan=_recon_plan(3),
            arguments=_args(3),
            execution_mode="simulation",
            limits=RunLimits(max_failed_steps=1),
        )
        self.assertEqual(result.status, "STOPPED_FAILURE_LIMIT")
        self.assertEqual(len(result.steps), 2)

    def test_real_mode_reports_governed_denial_per_step(self):
        runner = BoundedRunner()
        result = runner.run(
            session_id="s-real-deny",
            role_id="offensive_security",
            plan=_recon_plan(1),
            arguments=_args(1),
            execution_mode="real",  # no scope -> policy denies; audited
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertFalse(result.all_succeeded)
        self.assertEqual(result.steps[0].status, "FAILED")

    def test_high_risk_budget_stops_extra_steps(self):
        runner = BoundedRunner()
        result = runner.run(
            session_id="s-high-risk",
            role_id="offensive_security",
            plan=_recon_plan(3),
            arguments=_args(3),
            execution_mode="simulation",
        )
        self.assertEqual(result.status, "STOPPED_HIGH_RISK_LIMIT")
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.usage.high_risk_steps, 2)

    def test_confirmation_pause_and_single_use_resume(self):
        from unittest.mock import patch

        from tools.base import ToolResult

        store = ConfirmationStore()
        runner = BoundedRunner(
            orchestrator=_ConfirmOrchestrator(), confirmations=store
        )
        plan = _recon_plan(1)
        paused = runner.run(
            session_id="s-confirm",
            role_id="offensive_security",
            plan=plan,
            arguments=_args(1),
            execution_mode="simulation",
        )
        self.assertEqual(paused.status, "AWAITING_CONFIRMATION")
        self.assertEqual(paused.steps, [])
        self.assertIsNotNone(paused.pending_confirmation)
        pending = paused.pending_confirmation
        assert pending is not None

        # Resume without a grant must pause again with a fresh request.
        paused_again = runner.run(
            session_id="s-confirm",
            role_id="offensive_security",
            plan=plan,
            arguments=_args(1),
            execution_mode="simulation",
        )
        self.assertEqual(paused_again.status, "AWAITING_CONFIRMATION")

        store.grant("s-confirm", pending.request_id, granted_by="tester")
        with patch(
            "tools.executor.execute",
            return_value=ToolResult(
                success=True, tool_name="needs-confirm",
                execution_mode="simulation", verified=False,
            ),
        ):
            resumed = runner.run(
                session_id="s-confirm",
                role_id="offensive_security",
                plan=plan,
                arguments=_args(1),
                execution_mode="simulation",
            )
        self.assertEqual(resumed.status, "COMPLETED")
        self.assertTrue(resumed.all_succeeded)

        # The grant was single-use: a repeat run pauses again.
        repeat = runner.run(
            session_id="s-confirm",
            role_id="offensive_security",
            plan=plan,
            arguments=_args(1),
            execution_mode="simulation",
        )
        self.assertEqual(repeat.status, "AWAITING_CONFIRMATION")


class _ConfirmSelection:
    success = True
    status = "READY_FOR_POLICY"
    tool_id = "needs-confirm"
    message = "ready"


class _ConfirmRegistry:
    class _Tool:
        confirmation_required = True

    def get(self, tool_id):
        assert tool_id == "needs-confirm"
        return self._Tool()


class _ConfirmOrchestrator:
    registry = _ConfirmRegistry()

    def select_tool_for_capability(self, **kwargs):
        return _ConfirmSelection()


class BoundedRunnerValidationTests(unittest.TestCase):
    def test_session_id_is_required(self):
        runner = BoundedRunner()
        with self.assertRaises(ValueError):
            runner.run(
                session_id="  ",
                role_id="offensive_security",
                plan=_recon_plan(1),
                arguments=_args(1),
                execution_mode="simulation",
            )

    def test_arguments_must_match_plan_steps(self):
        runner = BoundedRunner()
        with self.assertRaises(ValueError):
            runner.run(
                session_id="s-args",
                role_id="offensive_security",
                plan=_recon_plan(2),
                arguments=_args(1),
                execution_mode="simulation",
            )


if __name__ == "__main__":
    unittest.main()
