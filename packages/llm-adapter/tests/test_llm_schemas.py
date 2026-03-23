"""Tests for pnlclaw_llm.schemas — structured output schemas and parsing."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, Field

from pnlclaw_llm.base import LLMError
from pnlclaw_llm.schemas import (
    MarketAnalysis,
    extract_structured,
    get_json_schema,
    market_analysis_schema,
    strategy_config_schema,
    trade_intent_schema,
)


# ---------------------------------------------------------------------------
# get_json_schema tests
# ---------------------------------------------------------------------------


class SimpleModel(BaseModel):
    name: str
    value: int = 0


class TestGetJsonSchema:
    def test_returns_dict(self) -> None:
        schema = get_json_schema(SimpleModel)
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "name" in schema["properties"]

    def test_trade_intent_schema(self) -> None:
        schema = trade_intent_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "symbol" in schema["properties"]
        assert "confidence" in schema["properties"]

    def test_strategy_config_schema(self) -> None:
        schema = strategy_config_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "symbols" in schema["properties"]

    def test_market_analysis_schema(self) -> None:
        schema = market_analysis_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "symbol" in schema["properties"]
        assert "regime" in schema["properties"]


# ---------------------------------------------------------------------------
# extract_structured tests
# ---------------------------------------------------------------------------


class TestExtractStructured:
    def test_valid_json_parses_correctly(self) -> None:
        raw = json.dumps({"name": "test", "value": 42})
        result = extract_structured(raw, SimpleModel)
        assert isinstance(result, SimpleModel)
        assert result.name == "test"
        assert result.value == 42

    def test_defaults_applied(self) -> None:
        raw = json.dumps({"name": "test"})
        result = extract_structured(raw, SimpleModel)
        assert result.value == 0

    def test_invalid_json_raises_llm_error(self) -> None:
        with pytest.raises(LLMError, match="Failed to parse"):
            extract_structured("not json {{{", SimpleModel)

    def test_validation_error_raises_llm_error(self) -> None:
        # Missing required field 'name'
        with pytest.raises(LLMError, match="does not match"):
            extract_structured('{"value": 42}', SimpleModel)

    def test_wrong_type_raises_llm_error(self) -> None:
        with pytest.raises(LLMError, match="does not match"):
            extract_structured('{"name": "ok", "value": "not_an_int"}', SimpleModel)

    def test_extract_market_analysis(self) -> None:
        raw = json.dumps({
            "symbol": "BTC/USDT",
            "summary": "Strong uptrend with high volume",
            "regime": "trending",
            "trend_direction": "bullish",
            "confidence": 0.85,
            "key_levels": {"support": 65000, "resistance": 72000},
            "recommendation": "Consider long positions",
        })
        result = extract_structured(raw, MarketAnalysis)
        assert result.symbol == "BTC/USDT"
        assert result.confidence == 0.85
        assert result.key_levels["support"] == 65000

    def test_extract_trade_intent(self) -> None:
        from pnlclaw_types.agent import TradeIntent

        raw = json.dumps({
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 0.1,
            "order_type": "market",
            "reasoning": "SMA cross",
            "confidence": 0.8,
            "timestamp": 1711000000000,
        })
        result = extract_structured(raw, TradeIntent)
        assert result.symbol == "BTC/USDT"
        assert result.confidence == 0.8

    def test_market_analysis_key_levels_not_shared(self) -> None:
        a = MarketAnalysis(
            symbol="BTC/USDT",
            summary="A",
            regime="trending",
            trend_direction="bullish",
            confidence=0.9,
        )
        b = MarketAnalysis(
            symbol="ETH/USDT",
            summary="B",
            regime="ranging",
            trend_direction="neutral",
            confidence=0.6,
        )
        a.key_levels["support"] = 60000.0
        assert "support" not in b.key_levels
