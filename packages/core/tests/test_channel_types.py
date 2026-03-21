"""Tests for pnlclaw_core.channel_sdk.types."""

import pytest

from pnlclaw_core.channel_sdk.types import ChannelPlugin


class TestChannelPlugin:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            ChannelPlugin()  # type: ignore[abstract]

    def test_has_four_methods(self):
        """Spec: start/stop/send_text/send_payload."""
        abstract_methods = ChannelPlugin.__abstractmethods__
        assert {"start", "stop", "send_text", "send_payload"} == abstract_methods

    def test_concrete_implementation(self):
        class MockChannel(ChannelPlugin):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send_text(self, recipient, text):
                pass

            async def send_payload(self, recipient, payload):
                pass

        ch = MockChannel()
        assert isinstance(ch, ChannelPlugin)
