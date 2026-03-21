"""Tests for pnlclaw_backtest.slippage."""

from pnlclaw_types.trading import OrderSide

from pnlclaw_backtest.slippage import FixedSlippage, NoSlippage


class TestNoSlippage:
    def test_buy_no_change(self) -> None:
        s = NoSlippage()
        assert s.apply(100.0, OrderSide.BUY) == 100.0

    def test_sell_no_change(self) -> None:
        s = NoSlippage()
        assert s.apply(100.0, OrderSide.SELL) == 100.0


class TestFixedSlippage:
    def test_buy_slips_up(self) -> None:
        s = FixedSlippage(bps=10)  # 0.10%
        result = s.apply(1000.0, OrderSide.BUY)
        assert result == 1000.0 * 1.001

    def test_sell_slips_down(self) -> None:
        s = FixedSlippage(bps=10)
        result = s.apply(1000.0, OrderSide.SELL)
        assert result == 1000.0 * 0.999

    def test_default_1bp(self) -> None:
        s = FixedSlippage()
        result = s.apply(10000.0, OrderSide.BUY)
        assert result == 10000.0 * 1.0001

    def test_negative_bps_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="non-negative"):
            FixedSlippage(bps=-1)
