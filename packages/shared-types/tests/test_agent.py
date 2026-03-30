"""Tests for pnlclaw_types.agent — serialization/deserialization roundtrips."""

from pnlclaw_types.agent import (
    AgentRole,
    AgentStreamEvent,
    AgentStreamEventType,
    ChatMessage,
    MarketRegime,
    MarketState,
    TradeIntent,
)
from pnlclaw_types.trading import OrderSide, OrderType


class TestAgentRole:
    def test_four_roles(self):
        assert set(AgentRole) == {
            AgentRole.MARKET_ANALYST,
            AgentRole.STRATEGY_ARCHITECT,
            AgentRole.RISK_GUARDIAN,
            AgentRole.STRATEGY_CODER,
        }


class TestTradeIntent:
    def test_roundtrip(self):
        ti = TradeIntent(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            quantity=0.1,
            order_type=OrderType.MARKET,
            reasoning="SMA cross detected",
            confidence=0.82,
            risk_params={"stop_loss": 65000.0},
            timestamp=1711000000000,
        )
        raw = ti.model_dump_json()
        restored = TradeIntent.model_validate_json(raw)
        assert restored == ti

    def test_has_reasoning_confidence_risk_params(self):
        """Spec: TradeIntent must have reasoning + confidence + risk_params."""
        fields = set(TradeIntent.model_fields.keys())
        assert {"reasoning", "confidence", "risk_params"}.issubset(fields)


class TestMarketState:
    def test_roundtrip(self):
        ms = MarketState(
            symbol="BTC/USDT",
            regime=MarketRegime.TRENDING,
            trend_strength=0.75,
            volatility=0.45,
            timestamp=1711000000000,
        )
        raw = ms.model_dump_json()
        restored = MarketState.model_validate_json(raw)
        assert restored == ms

    def test_regimes(self):
        assert set(MarketRegime) == {
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.VOLATILE,
        }


class TestChatMessage:
    def test_roundtrip(self):
        msg = ChatMessage(
            role="user",
            content="Create a strategy",
            timestamp=1711000000000,
            metadata={"source": "web"},
        )
        raw = msg.model_dump_json()
        restored = ChatMessage.model_validate_json(raw)
        assert restored == msg

    def test_metadata_optional(self):
        msg = ChatMessage(
            role="assistant",
            content="Here is your strategy.",
            timestamp=1711000000000,
        )
        assert msg.metadata is None


class TestAgentStreamEvent:
    def test_text_delta(self):
        e = AgentStreamEvent(
            type=AgentStreamEventType.TEXT_DELTA,
            data={"text": "Based on..."},
            timestamp=1711000000000,
        )
        raw = e.model_dump_json()
        restored = AgentStreamEvent.model_validate_json(raw)
        assert restored == e

    def test_tool_call(self):
        e = AgentStreamEvent(
            type=AgentStreamEventType.TOOL_CALL,
            data={"tool": "market_ticker", "args": {"symbol": "BTC/USDT"}},
            timestamp=1711000000100,
        )
        raw = e.model_dump_json()
        restored = AgentStreamEvent.model_validate_json(raw)
        assert restored.type == AgentStreamEventType.TOOL_CALL

    def test_done(self):
        e = AgentStreamEvent(
            type=AgentStreamEventType.DONE,
            data={},
            timestamp=1711000001000,
        )
        raw = e.model_dump_json()
        restored = AgentStreamEvent.model_validate_json(raw)
        assert restored.type == AgentStreamEventType.DONE

    def test_event_types(self):
        """Spec: AgentStreamEvent must have text_delta/tool_call/done types."""
        values = {t.value for t in AgentStreamEventType}
        assert {"text_delta", "tool_call", "done"}.issubset(values)
