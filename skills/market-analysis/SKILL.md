---
name: market-analysis
description: Analyzes current market state and short-term trends using ticker, candle, and narrative context
version: 0.1.0
tags: [market, analysis, data]
user_invocable: true
model_invocable: true
requires_tools: [market_ticker, market_kline, explain_market]
---

# Market Analysis

## Description
Analyzes current market state and short-term trends using ticker, candle, and narrative context.

## Triggers
- "What is the market doing for BTC/USDT?"
- "Analyze price action and trend"

## Steps
1. Confirm symbol(s) and whether the user wants spot context or a specific interval.
2. Call `market_ticker` for last price, spread, and 24h change.
3. Call `market_kline` for the latest OHLCV bar(s) as needed.
4. Call `explain_market` to synthesize regime-style commentary from available data.
5. Present a concise view: level, momentum, and risks—without implying certainty.

## Tools Used
- `market_ticker`: Latest quote snapshot for a trading pair.
- `market_kline`: Recent candlestick data for structure and volatility.
- `explain_market`: Structured explanation of market state for the LLM-facing summary.

## Example Interaction
**User**: Quick read on ETH/USDT before I adjust my strategy.
**Agent**: I will fetch `market_ticker` and `market_kline` for ETH/USDT, then use `explain_market` to summarize trend and volatility in plain language.

## Notes
- Market tools read data only; they do not place orders or move capital.
