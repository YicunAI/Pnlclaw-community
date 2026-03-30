---
name: backtest-explain
description: Analyzes backtest results in plain language, connecting metrics to what they mean for the strategy
version: 0.1.0
tags: [backtest, explanation, metrics]
user_invocable: true
model_invocable: true
requires_tools: [backtest_result, explain_pnl]
---

# Backtest Explanation

## Description
Analyzes backtest results in plain language, connecting metrics to what they mean for the strategy.

## Triggers
- "Explain my backtest results"
- "What does this backtest tell me?"
- "Explain this backtest"
- "帮我解释这个回测"

## Steps
1. Obtain the backtest run id the user cares about (or the latest completed run).
2. Call `backtest_result` to load metrics, trade count, and equity context.
3. Call `explain_pnl` when the discussion ties to PnL decomposition on paper accounts; otherwise focus on backtest metrics from step 2.
4. Explain return, drawdown, Sharpe, win rate, and trade count in plain language with caveats.

## Tools Used
- `backtest_result`: Retrieve stored backtest output including metrics and identifiers.
- `explain_pnl`: Relate profit/loss composition when comparing live paper performance to backtest expectations.

## Example Interaction
**User**: I ran a backtest yesterday—can you explain if the drawdown is acceptable?
**Agent**: I will pull the result with `backtest_result`, then walk through max drawdown, win rate, and trade count in context of your strategy goals.

## Notes
- Distinguish backtest metrics from live/paper PnL unless the user links them.
