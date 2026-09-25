import unittest

from tools_registry import TOOLS, tools_for_capability
from tools_registry.resolver import resolve_tools


class ToolRegistryTests(unittest.TestCase):
    def test_registry_loads(self):
        self.assertGreaterEqual(len(TOOLS), 8)

    def test_existing_recon_tools_are_registered(self):
        for tool_id in ("subfinder", "httpx", "nuclei"):
            self.assertIn(tool_id, TOOLS)
            self.assertTrue(TOOLS[tool_id].implemented)

    def test_high_risk_network_tools_require_authorized_target(self):
        for tool_id in ("subfinder", "httpx", "nuclei", "nmap"):
            tool = TOOLS[tool_id]
            self.assertEqual(tool.risk_level, "high")
            self.assertTrue(tool.network_access)
            self.assertTrue(tool.requires_authorized_target)

    def test_capability_resolution_returns_implemented_tools(self):
        ids = {t.id for t in resolve_tools("reconnaissance")}
        self.assertTrue({"subfinder", "httpx", "nuclei", "nmap"}.issubset(ids))

    def test_planned_tools_cannot_execute(self):
        for tool_id in ("amass", "recon_ng", "spiderfoot", "ghidra"):
            tool = TOOLS[tool_id]
            self.assertFalse(tool.implemented)
            self.assertFalse(tool.enabled)
            self.assertEqual(resolve_tools(tool.capabilities[0]).count(tool), 0)

    def test_simulation_is_explicit(self):
        for tool_id in ("subfinder", "httpx", "nuclei", "nmap"):
            self.assertIn("simulation", TOOLS[tool_id].execution_modes)
            self.assertTrue(TOOLS[tool_id].supports_simulation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
