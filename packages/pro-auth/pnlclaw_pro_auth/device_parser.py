"""User-Agent string parsing for device metadata.

Uses :pypi:`ua-parser` when available, falling back to basic regex
extraction when it is not installed.
"""

from __future__ import annotations

import logging
import re

from pnlclaw_pro_auth.models import DeviceInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback regex patterns
# ---------------------------------------------------------------------------

_RE_MOBILE = re.compile(r"(?i)(android|iphone|ipod|windows phone|mobile)")
_RE_TABLET = re.compile(r"(?i)(ipad|tablet|kindle|silk|playbook)")

_RE_OS = re.compile(
    r"(?i)(Windows NT [\d.]+|Mac OS X [\d_.]+|Linux|Android [\d.]+|"
    r"iPhone OS [\d_]+|iPad OS [\d_]+|CrOS)"
)
_RE_BROWSER = re.compile(r"(?i)(Chrome|Firefox|Safari|Edge|OPR|Opera|MSIE|Trident|Brave)")


def _fallback_parse(user_agent: str) -> DeviceInfo:
    """Extract device info using simple regex when ua-parser is absent."""
    # Device type
    if _RE_TABLET.search(user_agent):
        device_type = "tablet"
    elif _RE_MOBILE.search(user_agent):
        device_type = "mobile"
    else:
        device_type = "desktop"

    # OS
    os_match = _RE_OS.search(user_agent)
    os_name = os_match.group(1).replace("_", ".") if os_match else "unknown"

    # Browser
    browser_match = _RE_BROWSER.search(user_agent)
    browser = browser_match.group(1) if browser_match else "unknown"
    # Normalize Opera's alternate name
    if browser == "OPR":
        browser = "Opera"
    if browser == "Trident":
        browser = "IE"

    return DeviceInfo(device_type=device_type, os=os_name, browser=browser)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class DeviceParser:
    """Parse User-Agent strings into structured device metadata."""

    def __init__(self) -> None:
        self._ua_parser_available = False
        try:
            import ua_parser  # noqa: F401  # type: ignore[import-untyped]

            self._ua_parser_available = True
        except ImportError:
            logger.debug("ua-parser not installed — using fallback regex parsing")

    def parse(self, user_agent: str) -> DeviceInfo:
        """Parse *user_agent* and return :class:`DeviceInfo`."""
        if not user_agent:
            return DeviceInfo()

        if self._ua_parser_available:
            return self._parse_with_ua_parser(user_agent)
        return _fallback_parse(user_agent)

    def _parse_with_ua_parser(self, user_agent: str) -> DeviceInfo:
        """Parse using the ua-parser library."""
        from ua_parser import user_agent_parser  # type: ignore[import-untyped]

        result = user_agent_parser.Parse(user_agent)

        # Device type
        device_family = (result.get("device", {}).get("family", "") or "").lower()
        if "spider" in device_family or "bot" in device_family:
            device_type = "desktop"
        elif any(kw in device_family for kw in ("phone", "mobile", "ipod")):
            device_type = "mobile"
        elif any(kw in device_family for kw in ("tablet", "ipad", "kindle")):
            device_type = "tablet"
        else:
            # Fall back to regex check on the raw string
            if _RE_TABLET.search(user_agent):
                device_type = "tablet"
            elif _RE_MOBILE.search(user_agent):
                device_type = "mobile"
            else:
                device_type = "desktop"

        # OS
        os_data = result.get("os", {})
        os_family = os_data.get("family", "unknown") or "unknown"
        os_major = os_data.get("major", "")
        os_name = f"{os_family} {os_major}".strip() if os_major else os_family

        # Browser
        ua_data = result.get("user_agent", {})
        browser_family = ua_data.get("family", "unknown") or "unknown"

        return DeviceInfo(device_type=device_type, os=os_name, browser=browser_family)
