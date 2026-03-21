"""Tests for pnlclaw_market.stream_manager — WS stream lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pnlclaw_market.stream_manager import StreamManager, StreamType


@pytest.fixture
def ws_client() -> MagicMock:
    client = MagicMock()
    client.subscribe_ticker = AsyncMock()
    client.subscribe_kline = AsyncMock()
    client.subscribe_depth = AsyncMock()
    client.unsubscribe = AsyncMock()
    return client


@pytest.fixture
def l2_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def manager(ws_client: MagicMock, l2_manager: MagicMock) -> StreamManager:
    return StreamManager(ws_client=ws_client, l2_manager=l2_manager, kline_interval="1h")


class TestStreamManager:
    """Unit tests for the StreamManager."""

    @pytest.mark.asyncio
    async def test_start_stream_subscribes(self, manager: StreamManager, ws_client: MagicMock) -> None:
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        ws_client.subscribe_ticker.assert_awaited_once_with(["btcusdt"])

    @pytest.mark.asyncio
    async def test_start_kline_stream(self, manager: StreamManager, ws_client: MagicMock) -> None:
        await manager.start_stream("BTC/USDT", StreamType.KLINE)
        ws_client.subscribe_kline.assert_awaited_once_with(["btcusdt"], "1h")

    @pytest.mark.asyncio
    async def test_start_depth_stream(self, manager: StreamManager, ws_client: MagicMock) -> None:
        await manager.start_stream("BTC/USDT", StreamType.DEPTH)
        ws_client.subscribe_depth.assert_awaited_once_with(["btcusdt"])

    @pytest.mark.asyncio
    async def test_ref_counting(self, manager: StreamManager, ws_client: MagicMock) -> None:
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        # Only one actual subscribe call
        assert ws_client.subscribe_ticker.await_count == 1
        assert manager.ref_count("BTC/USDT", StreamType.TICKER) == 2

    @pytest.mark.asyncio
    async def test_stop_with_remaining_refs(self, manager: StreamManager, ws_client: MagicMock) -> None:
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        await manager.stop_stream("BTC/USDT", StreamType.TICKER)
        # Should NOT unsubscribe yet (ref=1 remaining)
        ws_client.unsubscribe.assert_not_awaited()
        assert manager.ref_count("BTC/USDT", StreamType.TICKER) == 1

    @pytest.mark.asyncio
    async def test_stop_last_ref_unsubscribes(self, manager: StreamManager, ws_client: MagicMock) -> None:
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        await manager.stop_stream("BTC/USDT", StreamType.TICKER)
        ws_client.unsubscribe.assert_awaited_once()
        assert manager.ref_count("BTC/USDT", StreamType.TICKER) == 0

    @pytest.mark.asyncio
    async def test_stop_nonexistent_is_noop(self, manager: StreamManager) -> None:
        await manager.stop_stream("NONE", StreamType.TICKER)  # no error

    @pytest.mark.asyncio
    async def test_active_symbols(self, manager: StreamManager) -> None:
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        await manager.start_stream("ETH/USDT", StreamType.KLINE)
        symbols = manager.active_symbols()
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols

    @pytest.mark.asyncio
    async def test_active_streams(self, manager: StreamManager) -> None:
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        await manager.start_stream("BTC/USDT", StreamType.DEPTH)
        streams = manager.active_streams()
        assert ("BTC/USDT", StreamType.TICKER) in streams
        assert ("BTC/USDT", StreamType.DEPTH) in streams

    @pytest.mark.asyncio
    async def test_resubscribe_all(self, manager: StreamManager, ws_client: MagicMock) -> None:
        await manager.start_stream("BTC/USDT", StreamType.TICKER)
        await manager.start_stream("ETH/USDT", StreamType.KLINE)
        ws_client.subscribe_ticker.reset_mock()
        ws_client.subscribe_kline.reset_mock()

        await manager.resubscribe_all()
        ws_client.subscribe_ticker.assert_awaited_once()
        ws_client.subscribe_kline.assert_awaited_once()
