"""Central policy gate for Lionel tool execution.

Default posture: deny real network/security-tool execution unless the caller
provides an explicit authorization scope. Simulation is allowed only for tools
that declare simulation support and is clearly marked as unverified.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional
import ipaddress
import logging
import socket

logger = logging.getLogger(__name__)

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class AuthorizationScope:
    """Explicit scope supplied by the trusted caller, not inferred by Lionel."""
    principal: str
    targets: tuple[str, ...] = ()
    allow_network: bool = False
    allow_filesystem: bool = False
    max_risk: str = "low"
    reason: str = ""
    simulation_only: bool = False

    @classmethod
    def for_targets(cls, principal: str, targets: Iterable[str], **kwargs: Any) -> "AuthorizationScope":
        return cls(principal=principal, targets=tuple(t.strip() for t in targets if t and t.strip()), **kwargs)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class PolicyGateway:
    """Single enforcement point before any Tool.run() call."""

    def evaluate(
        self,
        tool: Any,
        arguments: Dict[str, Any],
        scope: Optional[AuthorizationScope] = None,
        execution_mode: str = "real",
        confirmed: bool = False,
    ) -> PolicyDecision:
        if execution_mode not in {"real", "simulation"}:
            return PolicyDecision(False, "Unsupported execution mode.")

        if execution_mode == "simulation":
            if not getattr(tool, "supports_simulation", False):
                return PolicyDecision(False, "Tool does not support simulation mode.")
            return PolicyDecision(True, "Simulation explicitly requested.", metadata={"verified": False})

        if getattr(tool, "risk_level", "low") not in RISK_ORDER:
            return PolicyDecision(False, "Tool declares an invalid risk level.")

        if scope is None:
            if getattr(tool, "requires_authorized_target", False) or getattr(tool, "network_access", False):
                return PolicyDecision(False, "Explicit authorization scope is required for this tool.")
            scope = AuthorizationScope(principal="system", allow_network=False, allow_filesystem=False)

        if RISK_ORDER[tool.risk_level] > RISK_ORDER.get(scope.max_risk, -1):
            return PolicyDecision(False, "Tool risk exceeds the authorization scope.")
        if getattr(tool, "network_access", False) and not scope.allow_network:
            return PolicyDecision(False, "Network access is not allowed by the authorization scope.")
        if getattr(tool, "filesystem_access", False) and not scope.allow_filesystem:
            return PolicyDecision(False, "Filesystem access is not allowed by the authorization scope.")
        if getattr(tool, "confirmation_required", False) and not confirmed:
            return PolicyDecision(False, "Explicit confirmation is required before execution.", requires_confirmation=True)

        if getattr(tool, "requires_authorized_target", False):
            requested = extract_targets(arguments)
            if not requested:
                return PolicyDecision(False, "No target was supplied for an authorized-target tool.")
            if not targets_in_scope(requested, scope.targets):
                return PolicyDecision(False, "Requested target is outside the supplied authorization scope.")

        return PolicyDecision(True, "Allowed by policy.", metadata={"principal": scope.principal, "verified": True})


def extract_targets(arguments: Dict[str, Any]) -> list[str]:
    values = []
    for key in ("domain", "target", "url", "host", "hosts", "targets"):
        value = arguments.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple)):
            values.extend(str(v) for v in value)
    return [v.strip() for v in values if str(v).strip()]


def _host(value: str) -> Optional[str]:
    value = value.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].split(":", 1)[0].rstrip(".")
    return value or None


def targets_in_scope(requested: Iterable[str], allowed: Iterable[str]) -> bool:
    """Conservative target matching: exact host/IP or subdomain of an allowed domain."""
    allowed_hosts = [_host(a) for a in allowed]
    allowed_hosts = [a for a in allowed_hosts if a]
    if not allowed_hosts:
        return False
    for raw in requested:
        h = _host(raw)
        if not h:
            return False
        if h in allowed_hosts:
            continue
        # IPs are exact-match only.
        try:
            ipaddress.ip_address(h)
            return False
        except ValueError:
            pass
        if not any(h.endswith("." + a) for a in allowed_hosts if a):
            return False
    return True
