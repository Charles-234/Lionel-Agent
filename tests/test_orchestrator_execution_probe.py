"""Minimal V1 integration probe.

Purpose:
    Identify the smallest valid boundary between:
    Orchestrator -> existing governance -> existing executor.

This probe intentionally does not modify production code.
"""

import inspect
import unittest

from agent.orchestrator import LionelOrchestrator
from tools.policy import PolicyGateway
import tools.executor as executor_module


class OrchestratorExecutionIntegrationProbe(unittest.TestCase):

    def test_orchestrator_exposes_prepare_boundary(self):
        orchestrator = LionelOrchestrator()

        result = orchestrator.prepare_execution(
            task_type="reconnaissance",
            objective="Enumerate subdomains for an authorized target",
            role_id="offensive_security",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "READY_FOR_POLICY")
        self.assertEqual(result.capability_id, "reconnaissance")
        self.assertIsNotNone(result.tool_id)

    def test_policy_gateway_has_governance_evaluation_boundary(self):
        gateway = PolicyGateway()

        self.assertTrue(hasattr(gateway, "evaluate"))
        self.assertTrue(callable(gateway.evaluate))

        signature = inspect.signature(gateway.evaluate)

        self.assertIn("tool", signature.parameters)
        self.assertIn("arguments", signature.parameters)

    def test_executor_api_is_discoverable(self):
        self.assertTrue(
            hasattr(executor_module, "execute"),
            "tools.executor must expose the governed execute() entry point.",
        )

        self.assertTrue(
            callable(executor_module.execute),
            "tools.executor.execute must be callable.",
        )

        signature = inspect.signature(executor_module.execute)

        self.assertIn("tool", signature.parameters)
        self.assertIn("args", signature.parameters)
        self.assertIn("capability_id", signature.parameters)
        self.assertIn("scope", signature.parameters)
        self.assertIn("execution_mode", signature.parameters)
        self.assertIn("confirmed", signature.parameters)
        self.assertIn("role", signature.parameters)


if __name__ == "__main__":
    unittest.main()


