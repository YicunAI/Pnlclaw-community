"""Shared event helpers for the agent runtime package."""

from __future__ import annotations

import time
from typing import Any

from pnlclaw_types.agent import AgentStreamEvent, AgentStreamEventType


def make_event(event_type: AgentStreamEventType, data: dict[str, Any]) -> AgentStreamEvent:
    """Create an ``AgentStreamEvent`` with the current millisecond timestamp."""
    return AgentStreamEvent(
        type=event_type,
        data=data,
        timestamp=int(time.time() * 1000),
    )
