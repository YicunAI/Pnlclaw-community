"""Shared fixtures for full-pipeline integration tests (no external services)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
import pandas as pd
import pytest

from pnlclaw_paper.accounts import AccountStatus, PaperAccount
from pnlclaw_risk.engine import RiskEngine
from pnlclaw_risk.rules import create_default_rules


def _generate_deterministic_btc_klines(
    n_bars: int = 800,
    seed: int = 42,
    initial_price: float = 40_000.0,
    start_ts_ms: int = 1_704_067_200_000,
    interval_ms: int = 3_600_000,
) -> pd.DataFrame:
    """Deterministic OHLCV (same spirit as backtest-engine test fixtures)."""
    rng = np.random.RandomState(seed)

    log_returns = rng.normal(loc=0.0002, scale=0.015, size=n_bars)
    closes = np.zeros(n_bars)
    closes[0] = initial_price
    for i in range(1, n_bars):
        closes[i] = closes[i - 1] * np.exp(log_returns[i])

    opens = np.roll(closes, 1)
    opens[0] = initial_price * 0.999

    high_spread = rng.uniform(0.002, 0.010, size=n_bars)
    low_spread = rng.uniform(0.002, 0.010, size=n_bars)
    highs = np.maximum(opens, closes) * (1 + high_spread)
    lows = np.minimum(opens, closes) * (1 - low_spread)
    volumes = rng.uniform(50.0, 500.0, size=n_bars)

    timestamps = start_ts_ms + np.arange(n_bars) * interval_ms

    return pd.DataFrame(
        {
            "timestamp": timestamps.astype(np.int64),
            "exchange": "backtest",
            "symbol": "BTC/USDT",
            "interval": "1h",
            "open": np.round(opens, 2),
            "high": np.round(highs, 2),
            "low": np.round(lows, 2),
            "close": np.round(closes, 2),
            "volume": np.round(volumes, 2),
            "closed": True,
        }
    )


@pytest.fixture
def demo_data() -> pd.DataFrame:
    """Deterministic synthetic BTC/USDT 1h bars (does not use demo/ on disk)."""
    return _generate_deterministic_btc_klines(n_bars=800, seed=42)


class _PresetMockLLM:
    """Minimal LLM stub matching AgentRuntime's structured-output contract."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._i = 0

    async def chat(self, messages: list[Any], **kwargs: Any) -> str:
        import json

        if self._i >= len(self._responses):
            return json.dumps({"response": "done", "tool_calls": []})
        r = self._responses[self._i]
        self._i += 1
        return json.dumps(r)

    async def chat_stream(self, messages: list[Any], **kwargs: Any) -> AsyncIterator[str]:
        async def _empty() -> AsyncIterator[str]:
            if False:
                yield ""

        return _empty()

    async def chat_with_tools(
        self, messages: list[Any], tools: list[dict[str, Any]] | None = None, **kwargs: Any
    ) -> Any:
        from pnlclaw_llm.schemas import TokenUsage, ToolCall, ToolCallResult

        if self._i >= len(self._responses):
            return ToolCallResult(text="done")
        r = self._responses[self._i]
        self._i += 1
        raw_calls = r.get("tool_calls", [])
        parsed = [
            ToolCall(id=f"int_call_{i}", name=tc.get("tool", ""), arguments=tc.get("arguments", {}))
            for i, tc in enumerate(raw_calls)
            if isinstance(tc, dict)
        ]
        text = r.get("response", "") or None
        return ToolCallResult(tool_calls=parsed, text=text, usage=TokenUsage())

    async def generate_structured(
        self, messages: list[Any], output_schema: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        if self._i >= len(self._responses):
            return {"response": "done", "tool_calls": []}
        r = self._responses[self._i]
        self._i += 1
        return r


@pytest.fixture
def mock_llm() -> _PresetMockLLM:
    """LLM that requests one safe tool call then finishes."""
    return _PresetMockLLM(
        [
            {
                "response": "",
                "tool_calls": [{"tool": "integration_echo", "arguments": {"msg": "ping"}}],
            },
        ]
    )


@pytest.fixture
def paper_account() -> PaperAccount:
    """Paper account with $10,000 balance."""
    return PaperAccount(
        name="integration-test",
        initial_balance=10_000.0,
        current_balance=10_000.0,
        status=AccountStatus.ACTIVE,
        created_at=int(time.time() * 1000),
        updated_at=int(time.time() * 1000),
    )


@pytest.fixture
def risk_engine() -> RiskEngine:
    """Risk engine with the standard built-in rule set."""
    return RiskEngine(create_default_rules())
