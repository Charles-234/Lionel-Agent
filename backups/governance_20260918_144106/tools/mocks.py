"""
Mock tools - return realistic fake data when real binaries are missing.

Used for chain development and testing without installing external tools.
When a real binary is available, real adapters take over automatically.
"""
import random
import time
from typing import Any, Dict, List

from tools.base import Tool, ToolResult


# Fake data pools
_FAKE_SUBDOMAINS = [
    "www", "api", "mail", "dev", "staging", "admin", "test", "cdn",
    "blog", "shop", "app", "portal", "support", "docs", "static",
    "assets", "img", "media", "vpn", "git", "jenkins", "grafana",
]

_FAKE_PORTS = [80, 443, 8080, 8443, 3000, 5000, 8000, 9000]

_FAKE_TECH = ["nginx", "apache", "cloudflare", "react", "express", "django"]

_FAKE_SEVERITIES = ["info", "low", "medium", "high", "critical"]

_FAKE_FINDING_TEMPLATES = [
    ("exposed-panel", "Login panel exposed to internet", "medium"),
    ("missing-hsts", "HSTS header not set", "info"),
    ("outdated-nginx", "Outdated nginx version detected", "low"),
    ("default-creds", "Default credentials accepted", "high"),
    ("directory-listing", "Directory listing enabled", "low"),
    ("cors-misconfig", "CORS allows arbitrary origins", "medium"),
    ("ssl-weak", "Weak SSL/TLS cipher suite", "medium"),
    ("open-redirect", "Open redirect via redirect param", "low"),
]


class MockSubfinder(Tool):
    name = "subfinder"
    description = "Passively enumerate subdomains for a domain (MOCK)"
    category = "recon"
    requires_binary = None

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["domain"],
        }

    def run(self, domain: str, limit: int = 8, **kwargs: Any) -> ToolResult:
        start = time.time()
        count = random.randint(4, min(limit, 12))
        subs = random.sample(_FAKE_SUBDOMAINS, min(count, len(_FAKE_SUBDOMAINS)))
        subdomains = [f"{s}.{domain}" for s in subs]

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"domain": domain, "subdomains": subdomains, "count": len(subdomains)},
            raw="\n".join(subdomains),
            duration_ms=duration,
            tool_name=self.name,
        )


class MockHttpx(Tool):
    name = "httpx"
    description = "Probe HTTP services on a list of hosts (MOCK)"
    category = "recon"
    requires_binary = None

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "hosts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["hosts"],
        }

    def run(self, hosts: List[str], **kwargs: Any) -> ToolResult:
        start = time.time()
        live = []
        for host in hosts:
            if random.random() < 0.8:
                port = random.choice([443, 80, 8080])
                scheme = "https" if port in (443, 8443) else "http"
                live.append({
                    "url": f"{scheme}://{host}",
                    "status_code": random.choice([200, 200, 200, 301, 302, 403]),
                    "title": f"{host} - service",
                    "tech": random.sample(_FAKE_TECH, k=min(2, len(_FAKE_TECH))),
                    "port": port,
                })

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"live_hosts": live, "count": len(live)},
            raw=f"{len(live)} live hosts",
            duration_ms=duration,
            tool_name=self.name,
        )


class MockNuclei(Tool):
    name = "nuclei"
    description = "Template-based vulnerability scan (MOCK)"
    category = "recon"
    requires_binary = None

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "targets": {"type": "array", "items": {"type": "string"}},
                "severity": {"type": "string", "default": "medium,high,critical"},
            },
            "required": ["targets"],
        }

    def run(self, targets: List[str], severity: str = "medium,high,critical", **kwargs: Any) -> ToolResult:
        start = time.time()
        findings = []
        for target in targets:
            num_findings = random.choices([0, 1, 2, 3], weights=[40, 35, 20, 5])[0]
            for _ in range(num_findings):
                tmpl_id, name, sev = random.choice(_FAKE_FINDING_TEMPLATES)
                findings.append({
                    "template_id": tmpl_id,
                    "name": name,
                    "severity": sev,
                    "target": target,
                    "matched_at": target,
                })

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"findings": findings, "count": len(findings)},
            raw=f"{len(findings)} findings",
            duration_ms=duration,
            tool_name=self.name,
        )


# Registry of mocks
MOCK_TOOLS = {
    "subfinder": MockSubfinder,
    "httpx": MockHttpx,
    "nuclei": MockNuclei,
}