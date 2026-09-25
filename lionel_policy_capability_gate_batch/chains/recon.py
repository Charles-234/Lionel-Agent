"""Governed recon chain: capability context is explicit at every tool boundary."""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tools.executor import execute
from tools.policy import AuthorizationScope


@dataclass
class ChainResult:
    success: bool
    domain: str
    subdomains: List[str] = field(default_factory=list)
    live_hosts: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_ms: int = 0
    error: Optional[str] = None
    execution_mode: str = "real"
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success, "domain": self.domain,
            "subdomains_count": len(self.subdomains),
            "live_hosts_count": len(self.live_hosts),
            "findings_count": len(self.findings),
            "subdomains": self.subdomains, "live_hosts": self.live_hosts,
            "findings": self.findings, "steps": self.steps,
            "total_duration_ms": self.total_duration_ms, "error": self.error,
            "execution_mode": self.execution_mode, "verified": self.verified,
        }


class ReconChain:
    name = "recon"
    description = "Governed recon: subdomains, live hosts, vulnerability findings"

    def run(
        self, domain: str, skip_nuclei: bool = False, *,
        scope: Optional[AuthorizationScope] = None,
        execution_mode: str = "real", confirmed: bool = False,
    ) -> ChainResult:
        start = time.time()
        result = ChainResult(False, domain, execution_mode=execution_mode)

        sf = execute("subfinder", {"domain": domain},
                     capability_id="reconnaissance", scope=scope,
                     execution_mode=execution_mode, confirmed=confirmed)
        result.steps.append({"step": "subfinder", "success": sf.success,
                             "count": (sf.data or {}).get("count", 0),
                             "execution_mode": sf.execution_mode, "verified": sf.verified})
        if not sf.success:
            result.error = sf.error
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result
        result.subdomains = (sf.data or {}).get("subdomains", [])
        if not result.subdomains:
            result.error = "no subdomains found"
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result

        hx = execute("httpx", {"hosts": result.subdomains},
                     capability_id="reconnaissance", scope=scope,
                     execution_mode=execution_mode, confirmed=confirmed)
        result.steps.append({"step": "httpx", "success": hx.success,
                             "count": (hx.data or {}).get("count", 0),
                             "execution_mode": hx.execution_mode, "verified": hx.verified})
        if not hx.success:
            result.error = hx.error
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result
        result.live_hosts = (hx.data or {}).get("live_hosts", [])
        if not result.live_hosts:
            result.error = "no live hosts found"
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result

        if not skip_nuclei:
            targets = [h["url"] for h in result.live_hosts]
            nc = execute("nuclei", {"targets": targets},
                         capability_id="security_testing", scope=scope,
                         execution_mode=execution_mode, confirmed=confirmed)
            result.steps.append({"step": "nuclei", "success": nc.success,
                                 "count": (nc.data or {}).get("count", 0),
                                 "execution_mode": nc.execution_mode, "verified": nc.verified})
            if nc.success:
                result.findings = (nc.data or {}).get("findings", [])
            else:
                result.error = nc.error
                result.total_duration_ms = int((time.time() - start) * 1000)
                return result
        else:
            result.steps.append({"step": "nuclei", "skipped": True})

        result.success = True
        result.verified = execution_mode == "real"
        result.total_duration_ms = int((time.time() - start) * 1000)
        return result


def run(domain: str, skip_nuclei: bool = False, *,
        scope: Optional[AuthorizationScope] = None,
        execution_mode: str = "real", confirmed: bool = False) -> ChainResult:
    return ReconChain().run(domain, skip_nuclei=skip_nuclei, scope=scope,
                            execution_mode=execution_mode, confirmed=confirmed)
