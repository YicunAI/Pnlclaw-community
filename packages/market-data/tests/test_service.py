"""Tests for pnlclaw_market.service — MarketDataService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnlclaw_market.service import MarketDataService, MarketDataServiceNotRunning


class TestMarketDataService:
    """Unit tests for MarketDataService."""

    def test_not_running_raises(self) -> None:
        svc = MarketDataService()
        with pytest.raises(MarketDataServiceNotRunning):
            svc.get_ticker("BTC/USDT")
        with pytest.raises(MarketDataServiceNotRunning):
            svc.get_kline("BTC/USDT")
        with pytest.raises(MarketDataServiceNotRunning):
            svc.get_orderbook("BTC/USDT")

    def test_is_running_default_false(self) -> None:
        svc = MarketDataService()
        assert svc.is_running is False

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        svc = MarketDataService()
        with (
            patch("pnlclaw_market.service.BinanceWSClient") as mock_ws_cls,
            patch("pnlclaw_market.service.BinanceL2Manager") as mock_l2_cls,
            patch("pnlclaw_market.service.ReconnectManager") as mock_rm_cls,
        ):
            mock_ws = MagicMock()
            mock_ws_cls.return_value = mock_ws

            mock_l2 = MagicMock()
            mock_l2.close = AsyncMock()
            mock_l2_cls.return_value = mock_l2

            mock_rm = MagicMock()
            mock_rm.run = AsyncMock()
            mock_rm.stop = AsyncMock()
            mock_rm_cls.return_value = mock_rm

            await svc.start()
            assert svc.is_running is True

            await svc.stop()
            assert svc.is_running is False
            mock_rm.stop.assert_awaited_once()
            mock_l2.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        svc = MarketDataService()
        with (
            patch("pnlclaw_market.service.BinanceWSClient"),
            patch("pnlclaw_market.service.BinanceL2Manager") as mock_l2_cls,
            patch("pnlclaw_market.service.ReconnectManager") as mock_rm_cls,
        ):
            mock_l2_cls.return_value = MagicMock(close=AsyncMock())
            mock_rm = MagicMock(run=AsyncMock(), stop=AsyncMock())
            mock_rm_cls.return_value = mock_rm

            await svc.start()
            await svc.start()  # second call is no-op
            assert mock_rm_cls.call_count == 1
            await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        svc = MarketDataService()
        await svc.stop()  # should not raise

    def test_get_symbols_when_not_started(self) -> None:
        svc = MarketDataService()
        assert svc.get_symbols() == []

    def test_event_bus_accessible(self) -> None:
        svc = MarketDataService()
        assert svc.event_bus is not None

    def test_on_ticker_callback(self) -> None:
        svc = MarketDataService()
        received: list = []
        svc.on_ticker(received.append)
        from pnlclaw_types.market import TickerEvent

        assert svc.event_bus.handler_count(TickerEvent) == 1
