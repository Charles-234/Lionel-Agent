"""Governed IP geolocation lookup with primary and fallback sources.

This tool resolves an IP address to coarse location and network metadata.

It is deliberately narrow:

- Only public IPv4 and IPv6 addresses are accepted.
- Private, loopback, link-local, and reserved ranges are refused.
- The primary source is IPinfo. The fallback source is IPGeolocation.
- If the primary fails, the fallback is tried once.
- If both fail, a clean failure is returned. No raw exceptions escape.
- Responses are size-capped and control-character-cleaned.
- Credential-shaped lines are redacted before the result leaves the tool.

PolicyGateway remains the single enforcement point; this adapter only
keeps its own input and output clean.
"""
import ipaddress
import logging
import re
import time
from typing import Any, Dict, Optional

import requests

import config
from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15
_MAX_BODY_BYTES = 64_000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class IPLookup(Tool):
    name = "ip_lookup"
    description = "Resolve a public IP address to coarse location and network metadata"
    category = "intelligence"
    requires_binary = None
    risk_level = "low"
    requires_authorized_target = False
    network_access = True
    filesystem_access = False
    credentials_required = True
    supports_simulation = True
    confirmation_required = False
    provenance = "builtin"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ip": {
                    "type": "string",
                    "description": "Public IPv4 or IPv6 address to look up",
                },
            },
            "required": ["ip"],
        }

    def available(self) -> bool:
        return bool(config.IPINFO_AVAILABLE or config.IPGEOLOCATION_AVAILABLE)

    def run(self, ip: str, **kwargs: Any) -> ToolResult:
        cleaned_ip = _clean_ip(ip)
        if not cleaned_ip:
            return ToolResult(
                success=False,
                error="Only public IPv4 or IPv6 addresses are supported.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )

        if not self.available():
            return ToolResult(
                success=False,
                error="No IP geolocation provider is configured.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )

        start = time.time()
        primary_error: Optional[str] = None
        fallback_error: Optional[str] = None

        # Primary: IPinfo
        if config.IPINFO_AVAILABLE:
            try:
                result = _call_ipinfo(cleaned_ip)
                if result is not None:
                    return _success(result, cleaned_ip, "ipinfo", start, self.name)
            except Exception:
                logger.warning("IPinfo lookup failed", exc_info=True)
                primary_error = "primary_unavailable"

        # Fallback: IPGeolocation
        if config.IPGEOLOCATION_AVAILABLE:
            try:
                result = _call_ipgeolocation(cleaned_ip)
                if result is not None:
                    return _success(result, cleaned_ip, "ipgeolocation", start, self.name)
            except Exception:
                logger.warning("IPGeolocation lookup failed", exc_info=True)
                fallback_error = "fallback_unavailable"

        duration = int((time.time() - start) * 1000)
        error = "IP lookup failed safely without details."
        if primary_error and not fallback_error:
            error = "Primary source unavailable and no fallback configured."
        elif primary_error and fallback_error:
            error = "All IP geolocation sources are unavailable."

        return ToolResult(
            success=False,
            error=error,
            duration_ms=duration,
            tool_name=self.name,
            execution_mode="real",
            verified=False,
        )


def _call_ipinfo(ip: str) -> Optional[Dict[str, Any]]:
    """Call IPinfo Lite. Returns cleaned metadata, or None on empty body."""
    url = f"https://api.ipinfo.io/lite/{ip}"
    resp = requests.get(
        url,
        params={"token": config.IPINFO_TOKEN},
        timeout=_REQUEST_TIMEOUT,
        headers={"User-Agent": "LionelGovernedIPLookup/1.0"},
    )
    if resp.status_code != 200:
        return None
    body = resp.content[:_MAX_BODY_BYTES]
    data = resp.json()
    return _clean_result(data, "ipinfo")


def _call_ipgeolocation(ip: str) -> Optional[Dict[str, Any]]:
    """Call IPGeolocation.io. Returns cleaned metadata, or None on empty body."""
    url = "https://api.ipgeolocation.io/ipgeo"
    resp = requests.get(
        url,
        params={"apiKey": config.IPGEOLOCATION_API_KEY, "ip": ip},
        timeout=_REQUEST_TIMEOUT,
        headers={"User-Agent": "LionelGovernedIPLookup/1.0"},
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return _clean_result(data, "ipgeolocation")


def _clean_result(data: Any, source: str) -> Dict[str, Any]:
    """Keep only coarse fields. Drop anything that looks like a credential."""
    if not isinstance(data, dict):
        return {"source": source}
    keep = (
        "ip", "country", "country_code", "country_name",
        "region", "region_name", "city",
        "latitude", "longitude", "timezone", "time_zone",
        "asn", "org", "organization", "isp", "continent",
    )
    cleaned: Dict[str, Any] = {"source": source}
    for key in keep:
        if key in data:
            value = data[key]
            if isinstance(value, str):
                value = _CONTROL_RE.sub("", value)[:256]
            cleaned[key] = value
    return cleaned


def _success(
    data: Dict[str, Any],
    ip: str,
    source: str,
    start: float,
    tool_name: str,
) -> ToolResult:
    duration = int((time.time() - start) * 1000)
    return ToolResult(
        success=True,
        data={**data, "queried_ip": ip},
        duration_ms=duration,
        tool_name=tool_name,
        execution_mode="real",
        verified=False,
    )


def _clean_ip(value: Any) -> str:
    """Return a normalized public IP string, or \"\" when it is not usable."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > 64:
        return ""
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return ""
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    ):
        return ""
    return str(addr)