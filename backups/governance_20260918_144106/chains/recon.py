"""
Recon chain - subfinder -> httpx -> nuclei.

Takes a domain, runs the full recon pipeline, returns combined results.
No AI needed: the chain is predefined.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tools.recon.subfinder import Subfinder
from tools.recon.httpx import Httpx
from tools.recon.nuclei import Nuclei

logger = logging.getLogger(__name__)


@dataclass
class ChainResult:
    """Result of running a chain."""
    success: bool
    domain: str
    subdomains: List[str] = field(default_factory=list)
    live_hosts: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "domain": self.domain,
            "subdomains_count": len(self.subdomains),
            "live_hosts_count": len(self.live_hosts),
            "findings_count": len(self.findings),
            "subdomains": self.subdomains,
            "live_hosts": self.live_hosts,
            "findings": self.findings,
            "steps": self.steps,
            "total_duration_ms": self.total_duration_ms,
            "error": self.error,
        }


class ReconChain:
    """subfinder -> httpx -> nuclei pipeline."""

    name = "recon"
    description = "Full recon: subdomains, live hosts, vulnerabilities"

    def __init__(self):
        self.subfinder = Subfinder()
        self.httpx = Httpx()
        self.nuclei = Nuclei()

    def run(self, domain: str, skip_nuclei: bool = False) -> ChainResult:
        """Run the full recon chain against a domain."""
        start = time.time()
        result = ChainResult(success=False, domain=domain)
        steps = []

        # Step 1: subfinder
        logger.info(f"[recon] Step 1: subfinder on {domain}")
        sf = self.subfinder.run(domain=domain)
        steps.append({
            "step": "subfinder",
            "success": sf.success,
            "count": (sf.data or {}).get("count", 0) if sf.success else 0,
            "duration_ms": sf.duration_ms,
            "mock": not self.subfinder.available(),
        })
        if not sf.success:
            result.error = f"subfinder failed: {sf.error}"
            result.steps = steps
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result

        result.subdomains = (sf.data or {}).get("subdomains", [])
        if not result.subdomains:
            result.error = "no subdomains found"
            result.steps = steps
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result

        # Step 2: httpx
        logger.info(f"[recon] Step 2: httpx on {len(result.subdomains)} subdomains")
        hx = self.httpx.run(hosts=result.subdomains)
        steps.append({
            "step": "httpx",
            "success": hx.success,
            "count": (hx.data or {}).get("count", 0) if hx.success else 0,
            "duration_ms": hx.duration_ms,
            "mock": not self.httpx.available(),
        })
        if not hx.success:
            result.error = f"httpx failed: {hx.error}"
            result.steps = steps
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result

        result.live_hosts = (hx.data or {}).get("live_hosts", [])
        if not result.live_hosts:
            result.error = "no live hosts found"
            result.steps = steps
            result.total_duration_ms = int((time.time() - start) * 1000)
            return result

        # Step 3: nuclei (optional)
        if not skip_nuclei:
            targets = [h["url"] for h in result.live_hosts]
            logger.info(f"[recon] Step 3: nuclei on {len(targets)} live hosts")
            nc = self.nuclei.run(targets=targets)
            steps.append({
                "step": "nuclei",
                "success": nc.success,
                "count": (nc.data or {}).get("count", 0) if nc.success else 0,
                "duration_ms": nc.duration_ms,
                "mock": not self.nuclei.available(),
            })
            if nc.success:
                result.findings = (nc.data or {}).get("findings", [])
        else:
            steps.append({"step": "nuclei", "skipped": True})

        result.success = True
        result.steps = steps
        result.total_duration_ms = int((time.time() - start) * 1000)
        return result


# Module-level convenience
def run(domain: str, skip_nuclei: bool = False) -> ChainResult:
    return ReconChain().run(domain, skip_nuclei=skip_nuclei)