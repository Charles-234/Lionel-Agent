"""Lionel Agent - governed tool contracts."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import shutil
import time


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    raw: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    tool_name: str = ""
    execution_mode: str = "real"
    verified: bool = False
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "tool": self.tool_name,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "execution_mode": self.execution_mode,
            "verified": self.verified,
            "evidence": self.evidence,
        }


class Tool(ABC):
    """Base contract. Policy metadata is declarative; PolicyGateway enforces it."""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    category: str = "uncategorized"
    requires_binary: Optional[str] = None
    risk_level: str = "low"                 # low | medium | high | critical
    requires_authorized_target: bool = False
    network_access: bool = False
    filesystem_access: bool = False
    credentials_required: bool = False
    supports_simulation: bool = False
    confirmation_required: bool = False
    provenance: str = "builtin"

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        ...

    def available(self) -> bool:
        if not self.requires_binary:
            return True
        return shutil.which(self.requires_binary) is not None

    def manifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "requires_binary": self.requires_binary,
            "available": self.available(),
            "risk_level": self.risk_level,
            "requires_authorized_target": self.requires_authorized_target,
            "network_access": self.network_access,
            "filesystem_access": self.filesystem_access,
            "credentials_required": self.credentials_required,
            "supports_simulation": self.supports_simulation,
            "confirmation_required": self.confirmation_required,
            "provenance": self.provenance,
            "schema": self.schema(),
        }

    def info(self) -> Dict[str, Any]:
        return self.manifest()
