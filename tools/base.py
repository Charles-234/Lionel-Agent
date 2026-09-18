"""
Lionel Agent - Tool base classes.

Every tool inherits from Tool. Tools are called with keyword args and
return a ToolResult. Tools declare their category, dependencies, and
a schema describing valid arguments.
"""
import logging
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of running a tool."""
    success: bool
    data: Any = None
    raw: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    tool_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "tool": self.tool_name,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class Tool(ABC):
    """
    Base class for all tools.

    Subclasses must define:
    - name: short identifier (used by chains and agent)
    - description: one-line summary
    - category: grouping (recon, osint, web, defense, etc.)
    - requires_binary: name of external binary if any (for availability check)
    """

    name: str = ""
    description: str = ""
    category: str = "uncategorized"
    requires_binary: Optional[str] = None

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """JSON schema describing arguments this tool accepts."""

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments."""

    def available(self) -> bool:
        """Check if the tool's external dependency is installed."""
        if not self.requires_binary:
            return True
        return shutil.which(self.requires_binary) is not None

    def info(self) -> Dict[str, Any]:
        """Describe the tool for agent discovery."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "requires_binary": self.requires_binary,
            "available": self.available(),
            "schema": self.schema(),
        }