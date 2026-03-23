# Strategy Draft

## Description
Helps users create quantitative strategies through guided conversation and validation.

## Triggers
- "Help me draft a trading strategy"
- "Validate my strategy configuration"

## Steps
1. Clarify the user's market, timeframe, and strategy intent (trend, mean reversion, etc.).
2. Capture symbols, interval, parameters, and entry/exit ideas in structured form.
3. Call `strategy_validate` with a complete strategy config object and iterate on errors.
4. Summarize validated settings and any remaining assumptions.

## Tools Used
- `strategy_validate`: Check parameter ranges, indicator availability, and config consistency before backtesting.

## Example Interaction
**User**: I want a simple SMA crossover on BTC/USDT hourly with 10 and 50 periods.
**Agent**: Here is a draft config. I will run `strategy_validate` with symbols `BTC/USDT`, interval `1h`, and parameters `sma_short=10`, `sma_long=50`. If validation passes, we can refine entry/exit rules or move to a backtest.

## Notes
- Prefer explicit numeric parameters and one primary symbol set before adding complexity.
