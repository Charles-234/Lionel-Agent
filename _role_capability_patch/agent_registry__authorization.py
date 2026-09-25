"""Role -> capability authorization for Lionel.

This module is the authoritative bridge between the declarative role registry
and the capability registry. Tool authorization remains in the tool/policy layers.
"""
from dataclasses import dataclass
from typing import List, Optional

from agent_registry.roles import ROLES
from agent_registry.capabilities import CAPABILITIES


@dataclass(frozen=True)
class RoleCapabilityDecision:
    allowed: bool
    reason: str
    role_id: Optional[str] = None
    capability_id: Optional[str] = None


def get_role_capabilities(role_id: str) -> List[str]:
    """Return the capability IDs declared by a role."""
    return list(ROLES[role_id].capability_categories)


def validate_role_capability_contract() -> List[str]:
    """Return role capability references that are missing from the registry."""
    errors = []
    for role in ROLES.values():
        for capability_id in role.capability_categories:
            if capability_id not in CAPABILITIES:
                errors.append(
                    f"Role '{role.id}' references undefined capability '{capability_id}'."
                )
    return errors


def authorize_role_capability(
    role_id: Optional[str], capability_id: Optional[str]
) -> RoleCapabilityDecision:
    """Authorize a capability only when the active role declares it."""
    if not role_id:
        return RoleCapabilityDecision(False, "Role context is required for capability authorization.", role_id, capability_id)
    if role_id not in ROLES:
        return RoleCapabilityDecision(False, "Unknown role.", role_id, capability_id)
    if not capability_id:
        return RoleCapabilityDecision(False, "Capability context is required for role authorization.", role_id, capability_id)
    if capability_id not in CAPABILITIES:
        return RoleCapabilityDecision(False, "Unknown capability.", role_id, capability_id)
    if capability_id not in ROLES[role_id].capability_categories:
        return RoleCapabilityDecision(False, "Capability is not authorized for this role.", role_id, capability_id)
    if not CAPABILITIES[capability_id].enabled:
        return RoleCapabilityDecision(False, "Capability is disabled.", role_id, capability_id)
    return RoleCapabilityDecision(True, "Role is authorized for capability.", role_id, capability_id)
