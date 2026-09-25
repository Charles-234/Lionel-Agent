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
        self.assertEqual(result.capabily_id, "reconnaissance")
        self.assertIsNotNone(result.tool_id)

    def test_policy_gateway_has_governance_evaluation_boundary(self):
        gateway = PolicyGateway()

        self.assertTrue(hasattr(gateway, "evaluate"))
        self.assertTrue(callable(gateway.evaluate))

        signature = inspect.signature(gateway.evaluate)

        self.assertIn("tool", signature.parameters)
        self.assertIn("arguments", signature.parameters)

    def test_executor_api_is_discoverable(self):
        classes = [
            value
            for value in vars(executor_module).values()
            if inspect.isclass(value)
            and value.__module__ == executor_module.__name__
        ]

        self.assertTrue(
            classes,
            "No executor class was found in tools.executor.",
        )

        executable_methods = []

        for cls in classes:
            for name in dir(cls):
                if name.startswith("_"):
                    continue

                value = getattr(cls, name)

                if callable(value) and name in {
                    "execute",
                    "run",
                    "authorize_and_run",
                }:
                    executable_methods.append((cls.__name__, name))

        self.assertTrue(
            executable_methods,
            "No recognized executor entry point was found.",
        )


if __name__ == "__main__":
    unittest.main()
