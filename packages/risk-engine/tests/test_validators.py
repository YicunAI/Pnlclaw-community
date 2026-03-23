"""Tests for TradeIntent validators (S2-H03)."""

from __future__ import annotations

import time

from pnlclaw_risk.validators import (
    validate,
    validate_direction,
    validate_price,
    validate_stop_loss,
)
from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.trading import OrderSide, OrderType


def _make_intent(**overrides) -> TradeIntent:
    defaults = {
        "symbol": "BTC/USDT",
        "side": OrderSide.BUY,
        "quantity": 0.1,
        "price": 67000.0,
        "order_type": OrderType.LIMIT,
        "reasoning": "test",
        "confidence": 0.8,
        "risk_params": {"stop_loss": 65000.0, "take_profit": 70000.0},
        "timestamp": int(time.time() * 1000),
    }
    defaults.update(overrides)
    return TradeIntent(**defaults)


class TestValidatePrice:
    def test_within_deviation(self) -> None:
        errors = validate_price(_make_intent(price=67000.0), 67500.0)
        assert errors == []

    def test_exceeds_deviation(self) -> None:
        errors = validate_price(_make_intent(price=67000.0), 60000.0)
        assert len(errors) == 1
        assert "deviates" in errors[0]

    def test_no_price_skips(self) -> None:
        errors = validate_price(_make_intent(price=None), 67000.0)
        assert errors == []


class TestValidateStopLoss:
    def test_valid_stop_loss(self) -> None:
        errors = validate_stop_loss(_make_intent())
        assert errors == []

    def test_missing_stop_loss(self) -> None:
        errors = validate_stop_loss(_make_intent(risk_params={}))
        assert len(errors) == 1
        assert "Missing stop_loss" in errors[0]

    def test_invalid_stop_loss(self) -> None:
        errors = validate_stop_loss(_make_intent(risk_params={"stop_loss": -100}))
        assert len(errors) == 1
        assert "Invalid" in errors[0]


class TestValidateDirection:
    def test_valid_buy_direction(self) -> None:
        intent = _make_intent(
            side=OrderSide.BUY, price=67000.0,
            risk_params={"stop_loss": 65000.0, "take_profit": 70000.0},
        )
        assert validate_direction(intent) == []

    def test_invalid_buy_tp_below(self) -> None:
        intent = _make_intent(
            side=OrderSide.BUY, price=67000.0,
            risk_params={"stop_loss": 65000.0, "take_profit": 66000.0},
        )
        errors = validate_direction(intent)
        assert len(errors) == 1
        assert "BUY" in errors[0]

    def test_valid_sell_direction(self) -> None:
        intent = _make_intent(
            side=OrderSide.SELL, price=67000.0,
            risk_params={"stop_loss": 69000.0, "take_profit": 64000.0},
        )
        assert validate_direction(intent) == []

    def test_invalid_sell_tp_above(self) -> None:
        intent = _make_intent(
            side=OrderSide.SELL, price=67000.0,
            risk_params={"stop_loss": 69000.0, "take_profit": 70000.0},
        )
        errors = validate_direction(intent)
        assert any("SELL" in e for e in errors)

    def test_invalid_buy_sl_above_entry(self) -> None:
        intent = _make_intent(
            side=OrderSide.BUY, price=67000.0,
            risk_params={"stop_loss": 68000.0, "take_profit": 70000.0},
        )
        errors = validate_direction(intent)
        assert any("stop_loss" in e for e in errors)


class TestValidateCombined:
    def test_all_valid(self) -> None:
        result = validate(_make_intent(), 67000.0)
        assert result.valid is True
        assert result.errors == []

    def test_multiple_errors(self) -> None:
        intent = _make_intent(
            price=80000.0,
            risk_params={},
        )
        result = validate(intent, 67000.0)
        assert result.valid is False
        assert len(result.errors) >= 2  # price deviation + missing stop_loss
