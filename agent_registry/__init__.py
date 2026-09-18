"""Lionel agent registry package."""
from .roles import ROLES, Role, get_role, list_roles
from .capabilities import CAPABILITIES, Capability, get_capability, list_capabilities

__all__ = [
    "ROLES", "Role", "get_role", "list_roles",
    "CAPABILITIES", "Capability", "get_capability", "list_capabilities",
]
