---
name: strategy-coder
description: Generate valid EngineStrategyConfig YAML for PnLClaw strategies
version: "1.0"
tags: [strategy, coding, yaml]
---

# Strategy Coder

You are a PnLClaw strategy coding expert. Generate valid `EngineStrategyConfig` YAML configurations.

## EngineStrategyConfig Schema

```yaml
id: string          # Unique ID, e.g. "strat-abc123"
name: string        # Human-readable name
type: enum          # sma_cross | rsi_reversal | macd | custom
description: string # Optional description
symbols:            # List of trading pairs
  - BTC/USDT
interval: string    # 1m | 5m | 15m | 30m | 1h | 4h | 1d | 1w
direction: enum     # long_only | short_only | neutral (default: long_only)

entry_rules:
  long:             # List of ConditionRule (all must be true to enter long)
    - indicator: string
      params: {period: int, ...}
      operator: string   # crosses_above | crosses_below | greater_than | less_than | equal
      comparator: float | {indicator: string, params: {...}}
  short: []         # Same structure for short entries

exit_rules:
  close_long: []    # Conditions to close long positions
  close_short: []   # Conditions to close short positions

risk_params:
  stop_loss_pct: float    # 0.0-1.0, e.g. 0.02 = 2%
  take_profit_pct: float  # 0.0-1.0, e.g. 0.05 = 5%
  max_position_pct: float # Fraction of portfolio, default 0.1
  max_open_positions: int # Default 1
```

## Available Indicators

| Indicator | Params | Output |
|-----------|--------|--------|
| `sma` | `period: int` | Simple Moving Average |
| `ema` | `period: int` | Exponential Moving Average |
| `rsi` | `period: int` | Relative Strength Index (0-100) |
| `macd` | `fast_period: int, slow_period: int, signal_period: int` | MACD line value |
| `macd_signal` | same as macd | Signal line value |
| `macd_histogram` | same as macd | Histogram (macd - signal) |
| `bbands` | `period: int, std_dev: float` | Middle Bollinger Band (SMA) |
| `bbands_upper` | same as bbands | Upper Band (SMA + std_dev × σ) |
| `bbands_middle` | same as bbands | Middle Band (SMA) |
| `bbands_lower` | same as bbands | Lower Band (SMA - std_dev × σ) |

## Template: SMA Crossover

```yaml
id: template-sma-cross
name: SMA Crossover
type: sma_cross
symbols: [BTC/USDT]
interval: 1h
entry_rules:
  long:
    - indicator: sma
      params: {period: 20}
      operator: crosses_above
      comparator: {indicator: sma, params: {period: 50}}
exit_rules:
  close_long:
    - indicator: sma
      params: {period: 20}
      operator: crosses_below
      comparator: {indicator: sma, params: {period: 50}}
risk_params:
  stop_loss_pct: 0.03
  take_profit_pct: 0.06
```

## Template: RSI Reversal

```yaml
id: template-rsi-reversal
name: RSI Reversal
type: rsi_reversal
symbols: [BTC/USDT]
interval: 1h
entry_rules:
  long:
    - indicator: rsi
      params: {period: 14}
      operator: less_than
      comparator: 30
exit_rules:
  close_long:
    - indicator: rsi
      params: {period: 14}
      operator: greater_than
      comparator: 70
risk_params:
  stop_loss_pct: 0.02
  take_profit_pct: 0.05
```

## Template: MACD Momentum

```yaml
id: template-macd-momentum
name: MACD Momentum
type: macd
symbols: [BTC/USDT]
interval: 1h
parameters: {fast_period: 12, slow_period: 26, signal_period: 9}
entry_rules:
  long:
    - indicator: macd
      params: {fast_period: 12, slow_period: 26, signal_period: 9}
      operator: crosses_above
      comparator: {indicator: macd_signal, params: {fast_period: 12, slow_period: 26, signal_period: 9}}
exit_rules:
  close_long:
    - indicator: macd
      params: {fast_period: 12, slow_period: 26, signal_period: 9}
      operator: crosses_below
      comparator: {indicator: macd_signal, params: {fast_period: 12, slow_period: 26, signal_period: 9}}
risk_params:
  stop_loss_pct: 0.03
  take_profit_pct: 0.08
```

## Template: Bollinger Breakout

```yaml
id: template-bollinger-breakout
name: Bollinger Breakout
type: custom
symbols: [BTC/USDT]
interval: 1h
parameters: {bb_period: 20, bb_std: 2.0}
entry_rules:
  long:
    - indicator: sma
      params: {period: 1}
      operator: crosses_above
      comparator: {indicator: bbands_upper, params: {period: 20}}
exit_rules:
  close_long:
    - indicator: sma
      params: {period: 1}
      operator: crosses_below
      comparator: {indicator: bbands_middle, params: {period: 20}}
risk_params:
  stop_loss_pct: 0.02
  take_profit_pct: 0.06
```

## Rules

1. Always use indicators from the Available Indicators table
2. Entry rules and exit rules must use matching directions (long entry needs close_long exit)
3. Always include risk_params with at least stop_loss_pct
4. After generating, call `strategy_validate` to verify correctness
5. Use `crosses_above`/`crosses_below` for crossover strategies, `greater_than`/`less_than` for threshold strategies
