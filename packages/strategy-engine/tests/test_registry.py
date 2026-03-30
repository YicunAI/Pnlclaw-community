"""Tests for S2-E05: indicator registry."""

from __future__ import annotations

import pytest

from pnlclaw_strategy.indicators.base import Indicator
from pnlclaw_strategy.indicators.ema import EMA
from pnlclaw_strategy.indicators.macd import MACD
from pnlclaw_strategy.indicators.registry import (
    IndicatorNotFoundError,
    IndicatorRegistry,
    indicator_registry,
)
from pnlclaw_strategy.indicators.rsi import RSI
from pnlclaw_strategy.indicators.sma import SMA


class TestIndicatorRegistry:
    """Test IndicatorRegistry operations."""

    def test_register_and_get(self) -> None:
        reg = IndicatorRegistry()
        reg.register("sma", SMA)
        assert reg.get("sma") is SMA

    def test_get_case_insensitive(self) -> None:
        reg = IndicatorRegistry()
        reg.register("sma", SMA)
        assert reg.get("SMA") is SMA
        assert reg.get("Sma") is SMA

    def test_get_not_found(self) -> None:
        reg = IndicatorRegistry()
        with pytest.raises(IndicatorNotFoundError, match="ichimoku"):
            reg.get("ichimoku")

    def test_list_empty(self) -> None:
        reg = IndicatorRegistry()
        assert reg.list() == []

    def test_list_sorted(self) -> None:
        reg = IndicatorRegistry()
        reg.register("rsi", RSI)
        reg.register("ema", EMA)
        reg.register("sma", SMA)
        assert reg.list() == ["ema", "rsi", "sma"]

    def test_has(self) -> None:
        reg = IndicatorRegistry()
        reg.register("sma", SMA)
        assert reg.has("sma")
        assert reg.has("SMA")
        assert not reg.has("rsi")

    def test_overwrite_registration(self) -> None:
        reg = IndicatorRegistry()
        reg.register("sma", SMA)
        reg.register("sma", EMA)  # Overwrite
        assert reg.get("sma") is EMA


class TestDefaultRegistry:
    """Test the module-level default registry."""

    def test_has_five_builtins(self) -> None:
        names = indicator_registry.list()
        assert names == ["bbands", "ema", "macd", "rsi", "sma"]

    def test_get_sma(self) -> None:
        assert indicator_registry.get("sma") is SMA

    def test_get_ema(self) -> None:
        assert indicator_registry.get("ema") is EMA

    def test_get_rsi(self) -> None:
        assert indicator_registry.get("rsi") is RSI

    def test_get_macd(self) -> None:
        assert indicator_registry.get("macd") is MACD

    def test_instantiate_from_registry(self) -> None:
        cls = indicator_registry.get("sma")
        instance = cls(period=20)
        assert isinstance(instance, Indicator)
        assert instance.name == "sma"
        assert instance.period == 20
