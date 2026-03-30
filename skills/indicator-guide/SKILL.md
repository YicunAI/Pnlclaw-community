---
name: indicator-guide
description: Explains common technical indicators (SMA, EMA, RSI, MACD) with quantitative intuition and example calculations
version: 0.1.0
tags: [indicators, education, technical-analysis]
user_invocable: true
model_invocable: true
requires_tools: [market_kline]
---

# Indicator Guide

## Description
Explains common technical indicators (SMA, EMA, RSI, MACD) with quantitative intuition and example calculations.

## Triggers
- "What is the difference between SMA and EMA?"
- "How do I interpret RSI and MACD together?"

## Steps
1. Ask which indicators and timeframe matter for the user's strategy style.
2. Define each indicator: formula idea, smoothing behavior, and typical range.
3. Give a small numeric toy example (e.g. five closes → SMA vs EMA weighting).
4. Relate signals to strategy design (crossovers, divergence, overbought/oversold) without recommending specific trades.

## Tools Used
- `market_kline`: Optional OHLCV context when the user wants a concrete worked example on a symbol.

## Example Interaction
**User**: Explain MACD in simple terms with numbers.
**Agent**: MACD compares a fast and slow EMA of price, then smooths their difference (signal). For example, if fast EMA is 102 and slow EMA is 100, the MACD line is about +2; the signal line is an EMA of that series. Crossovers and histogram slope are common signal building blocks—always validate on your interval and costs.

## Notes
- This skill is educational; quantitative examples should use hypothetical or cited bars, not investment advice.
