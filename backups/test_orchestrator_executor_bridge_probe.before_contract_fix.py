import unittest

from agent.orchestrator import LionelOrchestrator
from tools.executor import execute
from tools.policy import AuthorizationScope


class OrchestratorExecutorBridgeProbe(unittest.TestCase):

    def test_prepared_result_contains_execution_inputs(self):
        orchestrator = LionelOrchestrator()

        result = orchestrator.prepare_execution(
            task_type="reconnaissance",
            objective="Enumerate subdomains for an authorized target",
            role_id="offensive_security",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "READY_FOR_POLICY")

        required = {
            "capability_id": getattr(result, "capability_id", None),
            "role_id": getattr(result, "role_id", None),
            "tool_id": getattr(result, "tool_id", None),
        }

        for name, value in required.items():
            self.assertIsNotNone(
                value,
                f"Prepared orchestration result is missing {name}.",
            )

    def test_existing_executor_accepts_governed_execution_inputs(self):
        orchestrator = LionelOrchestrator()

        result = orchestrator.prepare_execution(
            task_type="reconnaissance",
            objective="Enumerate subdomains for an authorized target",
            role_id="offensive_security",
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.tool_id)

        signature_args = {
            "tool": result.tool_id,
            "args": {"domain": "example.com"},
            "capability_id": result.capability_id,
            "role": "offensive_security",
            "execution_mode": "simulation",
            "confirmed": False,
        }

        # The probe intentionally stops before calling execute().
        # It verifies that the orchestrator result can supply the
        # inputs required by the existing governed executor.
        self.assertIsNotNone(signature_args["tool"])
        self.assertIsNotNone(signature_args["capability_id"])
        self.assertIsNotNone(signature_args["role"])

    def test_authorization_scope_contract_can_be_supplied(self):
        scope = AuthorizationScope.for_targets(
            principal="offensive_security",
            targets=["example.com"],
            allow_network=True,
            max_risk="high",
        )

        self.assertEqual(scope.principal, "offensive_security")
        self.assertIn("example.com", scope.targets)
        self.assertTrue(scope.allow_network)
        self.assertEqual(scope.max_risk, "high")


if __name__ == "__main__":
    unittest.main()
