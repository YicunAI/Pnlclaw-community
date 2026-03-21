"""Channel plugin ABC — abstract base for messaging channel integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ChannelPlugin(ABC):
    """Abstract base class for messaging channel plugins.

    Implementations handle a specific messaging platform
    (e.g. Telegram, Discord, Slack).
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the channel connection / polling loop."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the channel."""
        ...

    @abstractmethod
    async def send_text(self, recipient: str, text: str) -> None:
        """Send a plain text message.

        Args:
            recipient: Target user/channel identifier.
            text: Message content.
        """
        ...

    @abstractmethod
    async def send_payload(self, recipient: str, payload: dict[str, Any]) -> None:
        """Send a structured payload (e.g. rich message, card, embed).

        Args:
            recipient: Target user/channel identifier.
            payload: Structured message data.
        """
        ...
