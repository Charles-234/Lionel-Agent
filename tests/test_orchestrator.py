import unittest

from agent.orchestrator import LionelOrchestrator


class TestLionelOrchestrator(unittest.TestCase):

    def setUp(self):
        self.orchestrator = LionelOrchestrator()

    def test_reconnaissance_discovers_real_declared_tools(self):
        tools = self.orchestrator.inspect_tools_for_capability(
            "reconnaissance"
        )

        self.assertIn("subfinder", tools)
        self.assertIn("httpx", tools)
        self.assertIn("nuclei", tools)
        self.assertIn("nmap", tools)

    def test_planner_creates_plan_without_execution(self):
        plan = self.orchestrator.create_plan(
            "reconnaissance",
            "Enumerate subdomains for an authorized domain",
        )

        self.assertFalse(plan.execution_allowed)
        self.assertEqual(len(plan.steps), 1)

    def test_authorized_recon_request_reaches_tool_selection(self):
        result = self.orchestrator.prepare_execution(
            task_type="reconnaissance",
            objective="Enumerate subdomains for an authorized domain",
            role_id="offensive_security",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "READY_FOR_POLICY")
        self.assertEqual(result.capability_id, "reconnaissance")
        self.assertIn(
            result.tool_id,
            {"subfinder", "httpx", "nuclei"},
        )

    def test_unauthorized_role_is_denied(self):
        result = self.orchestrator.prepare_execution(
            task_type="reconnaissance",
            objective="Enumerate subdomains",
            role_id="frontend_developer",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "CAPABILITY_DENIED")

    def test_unknown_task_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.orchestrator.create_plan(
                "not_a_real_task",
                "Do something",
            )


if __name__ == "__main__":
    unittest.main()
