"""Strategy tools — validate, backtest run, and backtest result lookup.

``StrategyValidateTool`` validates a strategy config using the strategy
engine validator.  ``BacktestRunTool`` compiles and runs a backtest.
``BacktestResultTool`` retrieves a previously run backtest result.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
from pydantic import ValidationError

from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.risk import RiskLevel
from pnlclaw_types.strategy import BacktestResult

# ---------------------------------------------------------------------------
# Shared backtest results store (in-memory cache, also synced to DB)
# ---------------------------------------------------------------------------

_MAX_RESULTS = 1000
_backtest_results: dict[str, BacktestResult] = {}


def get_results_store() -> dict[str, BacktestResult]:
    """Return the shared in-memory backtest results store."""
    return _backtest_results


def _evict_oldest_results() -> None:
    """Remove oldest results when exceeding limit."""
    while len(_backtest_results) > _MAX_RESULTS:
        oldest_key = next(iter(_backtest_results))
        _backtest_results.pop(oldest_key, None)


# ---------------------------------------------------------------------------
# Config sanitizer — bridge AI-generated YAML to engine-compatible format
# ---------------------------------------------------------------------------

_KNOWN_CONFIG_FIELDS = frozenset({
    "id", "name", "type", "description", "symbols", "interval", "direction",
    "parameters", "entry_rules", "exit_rules", "risk_params", "tags",
    "source", "version", "lifecycle_state",
    "parsed_entry_rules", "parsed_exit_rules", "parsed_risk_params",
})


def _sanitize_config(cfg: dict) -> None:
    """In-place normalization of an AI-generated config dict.

    Fixes common mismatches between what the LLM generates and what
    ``EngineStrategyConfig.model_validate()`` expects:
    - Auto-generate ``id`` if missing.
    - Strip unknown top-level fields (``indicators``, ``filters``, etc.).
    - Build an alias→indicator mapping from ``indicators`` before removing it.
    - Normalize ``parsed_entry_rules`` / ``parsed_exit_rules`` from the
      ``{condition, rules}`` format into the expected list-of-ConditionRule.
    """
    import uuid as _uuid

    if "id" not in cfg or not cfg["id"]:
        cfg["id"] = f"ai-strat-{_uuid.uuid4().hex[:8]}"

    alias_map: dict[str, dict] = {}
    indicators_section = cfg.get("indicators")
    if isinstance(indicators_section, list):
        for ind in indicators_section:
            if isinstance(ind, dict) and "name" in ind and "type" in ind:
                params: dict = {}
                for k in ("period", "fast_period", "slow_period", "signal_period"):
                    if k in ind:
                        params[k] = ind[k]
                alias_map[ind["name"]] = {"indicator": ind["type"], "params": params}

    for key in list(cfg.keys()):
        if key not in _KNOWN_CONFIG_FIELDS:
            del cfg[key]

    def _resolve_ref(ref: str) -> dict:
        if ref in alias_map:
            return dict(alias_map[ref])
        return {"indicator": ref, "params": {}}

    _RAW_TO_PARSED = {
        "entry_rules": "parsed_entry_rules",
        "exit_rules": "parsed_exit_rules",
        "risk_params": "parsed_risk_params",
    }
    for raw_key, parsed_key in _RAW_TO_PARSED.items():
        raw_val = cfg.get(raw_key)
        parsed_val = cfg.get(parsed_key)
        if raw_val and isinstance(raw_val, dict) and not parsed_val:
            cfg[parsed_key] = dict(raw_val)

    for section_key in ("parsed_entry_rules", "parsed_exit_rules"):
        section = cfg.get(section_key)
        if not isinstance(section, dict):
            continue
        for side, rules in list(section.items()):
            if isinstance(rules, dict) and "rules" in rules:
                rules = rules["rules"]
                section[side] = rules
            if not isinstance(rules, list):
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                if "value_from" in rule and "comparator" not in rule:
                    rule["comparator"] = _resolve_ref(rule.pop("value_from"))
                if "value" in rule and "comparator" not in rule:
                    rule["comparator"] = rule.pop("value")
                if "params" not in rule:
                    ind_name = rule.get("indicator", "")
                    if ind_name in alias_map:
                        resolved = alias_map[ind_name]
                        rule["indicator"] = resolved["indicator"]
                        rule["params"] = resolved["params"]
                    else:
                        rule["params"] = {}


# ---------------------------------------------------------------------------
# StrategyValidateTool
# ---------------------------------------------------------------------------


class StrategyValidateTool(BaseTool):
    """Validate a strategy configuration for correctness."""

    @property
    def name(self) -> str:
        return "strategy_validate"

    @property
    def description(self) -> str:
        return (
            "Validate a strategy configuration, checking parameter ranges, "
            "logic consistency, and indicator availability."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "description": "Strategy configuration dict (StrategyConfig fields)",
                    "properties": {
                        "name": {"type": "string"},
                        "symbols": {"type": "array", "items": {"type": "string"}},
                        "type": {"type": "string"},
                        "interval": {"type": "string"},
                        "direction": {"type": "string"},
                        "parameters": {"type": "object", "additionalProperties": True},
                        "entry_rules": {"type": "object", "additionalProperties": True},
                        "exit_rules": {"type": "object", "additionalProperties": True},
                        "risk_params": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["name", "symbols", "type", "interval"],
                },
            },
            "required": ["config"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        config_dict = args.get("config")
        if not config_dict or not isinstance(config_dict, dict):
            return ToolResult(output="", error="Missing or invalid 'config' parameter")

        try:
            from pnlclaw_strategy.models import EngineStrategyConfig

            _sanitize_config(config_dict)
            engine_config = EngineStrategyConfig.model_validate(config_dict)
        except (ValidationError, Exception) as exc:
            return ToolResult(
                output=f"Strategy config parsing failed:\n{exc}",
                error="Invalid strategy configuration",
            )

        from pnlclaw_strategy.validator import validate

        result = validate(engine_config)

        if result.valid:
            return ToolResult(
                output=f"Strategy '{engine_config.name}' is valid. All checks passed."
            )

        errors_text = "\n".join(f"  - {e}" for e in result.errors)
        return ToolResult(
            output=(
                f"Strategy '{engine_config.name}' has {len(result.errors)} "
                f"validation error(s):\n{errors_text}"
            )
        )


# ---------------------------------------------------------------------------
# BacktestRunTool
# ---------------------------------------------------------------------------


class BacktestRunTool(BaseTool):
    """Run a backtest with a strategy config.

    The tool can auto-fetch historical klines from the exchange when
    ``symbol``, ``exchange``, ``interval``, and ``days`` are provided,
    so the LLM does NOT need to pass raw OHLCV data.
    """

    def __init__(
        self,
        backtest_engine: Any,
        backtest_repo: Any | None = None,
        market_service: Any | None = None,
    ) -> None:
        self._engine = backtest_engine
        self._repo = backtest_repo
        self._market_service = market_service

    @property
    def name(self) -> str:
        return "backtest_run"

    @property
    def description(self) -> str:
        return (
            "Run a backtest simulation. You can either provide historical data "
            "directly via 'data', OR let the tool auto-fetch by specifying "
            "'symbol', 'exchange', 'market_type', 'interval', and 'days'. "
            "Auto-fetch is recommended for backtests > 50 candles. "
            "Returns performance metrics: total return, Sharpe, max drawdown, win rate."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "ID of the strategy being backtested (e.g. 'strat-xxxxx'). Used to link backtest results to the strategy.",
                },
                "strategy_config": {
                    "type": "object",
                    "description": (
                        "COMPLETE strategy configuration. MUST include entry_rules, "
                        "exit_rules, and risk_params with actual structured data — "
                        "otherwise the backtest produces zero trades."
                    ),
                    "properties": {
                        "name": {"type": "string"},
                        "symbols": {"type": "array", "items": {"type": "string"}},
                        "type": {"type": "string"},
                        "interval": {"type": "string"},
                        "direction": {"type": "string"},
                        "parameters": {"type": "object", "additionalProperties": True},
                        "entry_rules": {
                            "type": "object", "additionalProperties": True,
                            "description": "REQUIRED. Entry conditions as structured dict.",
                        },
                        "exit_rules": {
                            "type": "object", "additionalProperties": True,
                            "description": "REQUIRED. Exit conditions as structured dict.",
                        },
                        "risk_params": {
                            "type": "object", "additionalProperties": True,
                            "description": "REQUIRED. Risk parameters (stop_loss_pct, take_profit_pct, etc.).",
                        },
                    },
                    "required": ["name", "symbols", "type", "interval", "entry_rules", "exit_rules", "risk_params"],
                },
                "symbol": {
                    "type": "string",
                    "description": "Trading pair for auto-fetch, e.g. 'BTC/USDT'. Required when 'data' is not provided.",
                },
                "exchange": {
                    "type": "string",
                    "description": "Exchange for auto-fetch: 'binance', 'okx'. Default 'binance'.",
                },
                "market_type": {
                    "type": "string",
                    "description": "Market type for auto-fetch: 'spot' or 'futures'. Default 'futures'.",
                },
                "interval": {
                    "type": "string",
                    "description": "Kline interval for auto-fetch: '1m','5m','15m','30m','1h','4h','1d'. Default from strategy config.",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of historical data to fetch (default 90, max 365).",
                },
                "data": {
                    "type": "array",
                    "description": (
                        "Optional: raw OHLCV data. If omitted, the tool auto-fetches "
                        "using symbol/exchange/interval/days."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "timestamp": {"type": "number"},
                            "open": {"type": "number"},
                            "high": {"type": "number"},
                            "low": {"type": "number"},
                            "close": {"type": "number"},
                            "volume": {"type": "number"},
                        },
                        "required": ["timestamp", "open", "high", "low", "close", "volume"],
                    },
                },
            },
            "required": ["strategy_config"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.RESTRICTED

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            output="",
            error="backtest_run requires async execution. Use the async agent path.",
        )

    async def async_execute(self, args: dict[str, Any]) -> ToolResult | None:
        """Async execution — can auto-fetch klines before running the backtest."""
        import logging as _logging

        _log = _logging.getLogger(__name__)

        strategy_id = args.get("strategy_id", "")

        config_dict = args.get("strategy_config")
        if not config_dict or not isinstance(config_dict, dict):
            return ToolResult(output="", error="Missing or invalid 'strategy_config'")

        data_list = args.get("data")

        if not data_list or not isinstance(data_list, list) or len(data_list) < 2:
            data_list = await self._auto_fetch_klines(args, config_dict, _log)
            if data_list is None:
                return ToolResult(
                    output="",
                    error=(
                        "No kline data provided and auto-fetch failed. "
                        "Provide 'symbol' + 'exchange' + 'days', or pass 'data' directly."
                    ),
                )

        if len(data_list) < 2:
            return ToolResult(output="", error="Need at least 2 kline bars for backtest")

        try:
            from pnlclaw_strategy.compiler import compile as compile_strategy
            from pnlclaw_strategy.models import EngineStrategyConfig
            from pnlclaw_strategy.runtime import StrategyRuntime

            _sanitize_config(config_dict)
            engine_config = EngineStrategyConfig.model_validate(config_dict)
            compiled = compile_strategy(engine_config)
            strategy_rt = StrategyRuntime(compiled, direction=engine_config.direction)
        except Exception as exc:
            return ToolResult(
                output=f"Strategy compilation failed: {exc}",
                error="Strategy compilation error",
            )

        try:
            df = pd.DataFrame(data_list)
            required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
            missing = required_cols - set(df.columns)
            if missing:
                return ToolResult(
                    output="",
                    error=f"Data missing required columns: {sorted(missing)}",
                )
        except Exception as exc:
            return ToolResult(output=f"Data conversion failed: {exc}", error="Data error")

        import dataclasses as _dc
        config_updates: dict[str, str] = {}
        if strategy_id:
            config_updates["strategy_id"] = strategy_id
        cfg_symbol = config_dict.get("symbols", [""])[0] if isinstance(config_dict.get("symbols"), list) and config_dict.get("symbols") else args.get("symbol", "")
        cfg_interval = config_dict.get("interval", "") or args.get("interval", "")
        if cfg_symbol:
            config_updates["symbol"] = cfg_symbol
        if cfg_interval:
            config_updates["interval"] = cfg_interval
        if config_updates:
            self._engine._config = _dc.replace(self._engine._config, **config_updates)

        try:
            result: BacktestResult = self._engine.run(strategy_rt, df)
        except Exception as exc:
            return ToolResult(output=f"Backtest execution failed: {exc}", error="Backtest error")

        patches: dict[str, Any] = {}
        if strategy_id and result.strategy_id != strategy_id:
            patches["strategy_id"] = strategy_id
        if not result.symbol and cfg_symbol:
            patches["symbol"] = cfg_symbol
        if not result.interval and cfg_interval:
            patches["interval"] = cfg_interval
        if patches:
            result = result.model_copy(update=patches)

        _backtest_results[result.id] = result

        if self._repo is not None:
            try:
                await self._repo.save(result)
                _log.info("Backtest %s persisted to DB", result.id)
            except Exception:
                _log.warning("Failed to persist backtest %s to DB", result.id, exc_info=True)
        else:
            _log.warning("No backtest repo — result %s is in-memory only", result.id)

        m = result.metrics
        lines = [
            f"Backtest Complete — ID: {result.id}",
            f"  Strategy: {result.strategy_id}",
            f"  Period: {result.start_date:%Y-%m-%d} to {result.end_date:%Y-%m-%d}",
            f"  Data: {len(data_list)} candles",
            f"  Trades: {result.trades_count}",
            "",
            "  Performance Metrics:",
            f"    Total Return: {m.total_return:+.2%}",
            f"    Annual Return: {m.annual_return:+.2%}",
            f"    Sharpe Ratio: {m.sharpe_ratio:.2f}",
            f"    Max Drawdown: {m.max_drawdown:.2%}",
            f"    Win Rate: {m.win_rate:.1%}",
            f"    Profit Factor: {m.profit_factor:.2f}",
        ]
        return ToolResult(output="\n".join(lines))

    async def _auto_fetch_klines(
        self,
        args: dict[str, Any],
        config_dict: dict[str, Any],
        _log: Any,
    ) -> list[dict[str, Any]] | None:
        """Paginated fetch of historical klines for backtesting."""
        if self._market_service is None:
            return None

        symbol = args.get("symbol") or (config_dict.get("symbols") or [None])[0]
        if not symbol:
            return None

        exchange = args.get("exchange", "binance")
        market_type = args.get("market_type", "futures")
        interval = args.get("interval") or config_dict.get("interval", "1h")
        days = min(args.get("days", 90), 365)

        interval_minutes = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480,
            "12h": 720, "1d": 1440,
        }
        minutes_per_candle = interval_minutes.get(interval, 60)
        total_candles = (days * 24 * 60) // minutes_per_candle

        _log.info(
            "Auto-fetching %d candles (%d days, %s) for %s on %s/%s",
            total_candles, days, interval, symbol, exchange, market_type,
        )

        try:
            klines = await self._market_service.fetch_klines_batch(
                symbol,
                exchange=exchange,
                market_type=market_type,
                interval=interval,
                total=total_candles,
            )
        except Exception as exc:
            _log.error("Auto-fetch failed: %s", exc)
            return None

        if not klines:
            return None

        _log.info("Auto-fetched %d klines for backtest", len(klines))

        data_list = []
        for k in klines:
            data_list.append({
                "timestamp": getattr(k, "timestamp", 0),
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
            })
        return data_list


# ---------------------------------------------------------------------------
# BacktestResultTool
# ---------------------------------------------------------------------------


class BacktestResultTool(BaseTool):
    """Look up a previously run backtest result by ID."""

    def __init__(self, results_store: dict[str, BacktestResult] | None = None) -> None:
        self._store = results_store if results_store is not None else _backtest_results

    @property
    def name(self) -> str:
        return "backtest_result"

    @property
    def description(self) -> str:
        return (
            "Retrieve a previously run backtest result by its ID, "
            "showing performance metrics and trade count."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "backtest_id": {
                    "type": "string",
                    "description": "The backtest run ID to look up",
                },
            },
            "required": ["backtest_id"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        backtest_id = args.get("backtest_id", "")
        if not backtest_id:
            return ToolResult(output="", error="Missing required parameter: backtest_id")

        result = self._store.get(backtest_id)
        if result is None:
            available = list(self._store.keys())[:5]
            hint = f" Available IDs: {available}" if available else ""
            return ToolResult(output=f"No backtest found with ID '{backtest_id}'.{hint}")

        m = result.metrics
        lines = [
            f"Backtest Result — ID: {result.id}",
            f"  Strategy: {result.strategy_id}",
            f"  Period: {result.start_date:%Y-%m-%d} to {result.end_date:%Y-%m-%d}",
            f"  Trades: {result.trades_count}",
            "",
            "  Performance Metrics:",
            f"    Total Return: {m.total_return:+.2%}",
            f"    Annual Return: {m.annual_return:+.2%}",
            f"    Sharpe Ratio: {m.sharpe_ratio:.2f}",
            f"    Max Drawdown: {m.max_drawdown:.2%}",
            f"    Win Rate: {m.win_rate:.1%}",
            f"    Profit Factor: {m.profit_factor:.2f}",
        ]
        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# StrategySaveVersionTool
# ---------------------------------------------------------------------------


class StrategySaveVersionTool(BaseTool):
    """Save a strategy config as a new version with changelog note.

    Designed to be called by the Agent after generating or modifying
    a strategy YAML so that every iteration is automatically versioned.
    """

    def __init__(self, save_fn: Any | None = None) -> None:
        self._save_fn = save_fn

    @property
    def name(self) -> str:
        return "save_strategy_version"

    @property
    def description(self) -> str:
        return (
            "Save a strategy configuration as a new version. "
            "Call this EVERY TIME you generate or modify a strategy YAML. "
            "The version number is auto-incremented. "
            "IMPORTANT: The 'config' parameter MUST contain the COMPLETE "
            "strategy configuration including name, symbols, interval, "
            "entry_rules, exit_rules, and risk_params as structured dicts. "
            "Do NOT pass an empty config — include ALL strategy logic. "
            "entry_rules and exit_rules should be structured objects describing "
            "the conditions, e.g. {\"conditions\": [...], \"logic\": \"AND\"}. "
            "risk_params should include stop_loss, take_profit, max_position_size etc."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "ID of the strategy to update",
                },
                "config": {
                    "type": "object",
                    "description": (
                        "COMPLETE strategy configuration. MUST include ALL fields, "
                        "especially entry_rules, exit_rules, and risk_params with "
                        "actual structured data (not empty objects)."
                    ),
                    "properties": {
                        "name": {"type": "string", "description": "Strategy name"},
                        "description": {"type": "string", "description": "Strategy description"},
                        "symbols": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['BTC/USDT']"},
                        "type": {"type": "string", "description": "Strategy type, e.g. 'custom'"},
                        "interval": {"type": "string", "description": "Kline interval, e.g. '1h'"},
                        "direction": {"type": "string", "description": "long_only, short_only, or neutral"},
                        "parameters": {"type": "object", "additionalProperties": True, "description": "Strategy-specific parameters"},
                        "entry_rules": {
                            "type": "object", "additionalProperties": True,
                            "description": "REQUIRED. Entry conditions as structured dict. Example: {\"conditions\": [{\"indicator\": \"EMA\", \"params\": {\"fast\": 12, \"slow\": 26}, \"comparison\": \"cross_above\"}], \"logic\": \"AND\"}",
                        },
                        "exit_rules": {
                            "type": "object", "additionalProperties": True,
                            "description": "REQUIRED. Exit conditions as structured dict. Same format as entry_rules.",
                        },
                        "risk_params": {
                            "type": "object", "additionalProperties": True,
                            "description": "REQUIRED. Risk parameters. Example: {\"stop_loss_pct\": 0.02, \"take_profit_pct\": 0.05, \"max_position_pct\": 0.35}",
                        },
                    },
                    "required": ["name", "symbols", "interval", "entry_rules", "exit_rules", "risk_params"],
                },
                "changelog": {
                    "type": "string",
                    "description": "Brief description of what changed in this version",
                },
            },
            "required": ["strategy_id", "config"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.RESTRICTED

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            output="",
            error="save_strategy_version requires async execution.",
        )

    async def async_execute(self, args: dict[str, Any]) -> ToolResult | None:
        strategy_id = args.get("strategy_id", "")
        config = args.get("config")
        changelog = args.get("changelog", "AI-generated update")

        if not strategy_id:
            return ToolResult(output="", error="Missing required parameter: strategy_id")
        if not config or not isinstance(config, dict):
            return ToolResult(output="", error="Missing or invalid 'config' parameter")

        if self._save_fn is None:
            return ToolResult(output="", error="Strategy save function not configured")

        try:
            result = await self._save_fn(strategy_id, config, changelog)
            return ToolResult(output=result)
        except Exception as exc:
            return ToolResult(
                output=f"Failed to save strategy version: {exc}",
                error="Save failed",
            )


# ---------------------------------------------------------------------------
# StrategyGenerateTool
# ---------------------------------------------------------------------------


class StrategyGenerateTool(BaseTool):
    """Generate a strategy config from a natural language description."""

    @property
    def name(self) -> str:
        return "strategy_generate"

    @property
    def description(self) -> str:
        return (
            "Generate an EngineStrategyConfig YAML configuration from a user's "
            "natural language description of a trading strategy."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Natural language description of the desired strategy",
                },
            },
            "required": ["description"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        user_desc = args.get("description", "")
        if not user_desc:
            return ToolResult(output="", error="Missing 'description' parameter")

        output = (
            f"Strategy generation request received:\n"
            f"  Description: {user_desc}\n\n"
            "Generate a JSON config with EXACTLY these fields:\n"
            "  - name (str), type (sma_cross|rsi_reversal|macd|custom)\n"
            "  - symbols (list), interval (1h etc), direction (long_only|short_only|neutral)\n"
            "  - entry_rules: {long: [...], short: [...]}\n"
            "  - exit_rules: {close_long: [...], close_short: [...]}\n"
            "  - risk_params: {stop_loss_pct, take_profit_pct, max_position_pct}\n\n"
            "Each rule is a ConditionRule:\n"
            '  {"indicator": "ema", "params": {"period": 20}, "operator": "less_than",\n'
            '   "comparator": {"indicator": "ema", "params": {"period": 50}}}\n'
            "  OR with numeric comparator:\n"
            '  {"indicator": "rsi", "params": {"period": 14}, "operator": "less_than", "comparator": 45}\n\n'
            "Available indicators: sma, ema, rsi, macd, macd_signal, macd_histogram\n"
            "Operators: crosses_above, crosses_below, greater_than, less_than, equal\n\n"
            "FORBIDDEN: 'indicators' section, 'filters', 'execution', 'management', 'notes',\n"
            "  'value_from', 'value' in rules, 'condition: all' wrappers, 'close' as indicator.\n"
            "FORBIDDEN: Do NOT use 'parsed_entry_rules', 'parsed_exit_rules', 'parsed_risk_params'.\n"
            "  Use 'entry_rules', 'exit_rules', 'risk_params' directly.\n\n"
            "After generating, call save_strategy_version with the COMPLETE config.\n"
            "Then call strategy_validate to verify correctness."
        )
        return ToolResult(output=output)


# ---------------------------------------------------------------------------
# StrategyExplainTool
# ---------------------------------------------------------------------------


class StrategyExplainTool(BaseTool):
    """Explain a strategy configuration in plain language."""

    @property
    def name(self) -> str:
        return "strategy_explain"

    @property
    def description(self) -> str:
        return (
            "Explain a strategy's logic, entry/exit conditions, and risk "
            "parameters in plain language."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "description": "Strategy configuration dict to explain",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "symbols": {"type": "array", "items": {"type": "string"}},
                        "interval": {"type": "string"},
                        "direction": {"type": "string"},
                        "parameters": {"type": "object", "additionalProperties": True},
                        "entry_rules": {"type": "object", "additionalProperties": True},
                        "exit_rules": {"type": "object", "additionalProperties": True},
                        "risk_params": {"type": "object", "additionalProperties": True},
                    },
                },
            },
            "required": ["config"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        config_dict = args.get("config")
        if not config_dict or not isinstance(config_dict, dict):
            return ToolResult(output="", error="Missing or invalid 'config' parameter")

        try:
            from pnlclaw_strategy.models import EngineStrategyConfig
            config = EngineStrategyConfig.model_validate(config_dict)
        except Exception as exc:
            return ToolResult(output=f"Cannot parse config: {exc}", error="Invalid config")

        lines = [
            f"Strategy: {config.name} (ID: {config.id})",
            f"Type: {config.type.value}",
            f"Symbols: {', '.join(config.symbols)}",
            f"Interval: {config.interval}",
            f"Direction: {config.direction.value}",
            "",
        ]

        entry = config.parsed_entry_rules
        if entry.long:
            lines.append("Long Entry Conditions (all must be true):")
            for r in entry.long:
                comp = r.comparator if isinstance(r.comparator, (int, float)) else r.comparator.get("indicator", "?")
                lines.append(f"  - {r.indicator}({r.params}) {r.operator} {comp}")
        if entry.short:
            lines.append("Short Entry Conditions:")
            for r in entry.short:
                comp = r.comparator if isinstance(r.comparator, (int, float)) else r.comparator.get("indicator", "?")
                lines.append(f"  - {r.indicator}({r.params}) {r.operator} {comp}")

        exit_ = config.parsed_exit_rules
        if exit_.close_long:
            lines.append("Close Long Conditions:")
            for r in exit_.close_long:
                comp = r.comparator if isinstance(r.comparator, (int, float)) else r.comparator.get("indicator", "?")
                lines.append(f"  - {r.indicator}({r.params}) {r.operator} {comp}")

        risk = config.parsed_risk_params
        lines.append("")
        lines.append("Risk Parameters:")
        if risk.stop_loss_pct is not None:
            lines.append(f"  Stop Loss: {risk.stop_loss_pct:.1%}")
        if risk.take_profit_pct is not None:
            lines.append(f"  Take Profit: {risk.take_profit_pct:.1%}")
        lines.append(f"  Max Position: {risk.max_position_pct:.0%} of portfolio")

        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# Deploy / Stop strategy tools
# ---------------------------------------------------------------------------


class StrategyDeployTool(BaseTool):
    """Deploy a strategy to continuous paper trading execution.

    IMPORTANT: This tool must NOT be called automatically by the agent.
    The agent should present the deployment plan to the user and only
    deploy after the user explicitly confirms.
    """

    def __init__(self, deploy_fn: Any) -> None:
        self._deploy_fn = deploy_fn

    @property
    def name(self) -> str:
        return "deploy_strategy"

    @property
    def description(self) -> str:
        return (
            "Deploy a strategy for continuous paper trading execution. "
            "CRITICAL: You MUST ask the user for explicit confirmation BEFORE calling this tool. "
            "Never deploy without user consent. Present a summary of the strategy "
            "(name, rules, risk params) and ask 'Should I deploy this strategy to paper trading?' "
            "Only call this tool after the user says yes."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "The strategy ID to deploy.",
                },
                "account_id": {
                    "type": "string",
                    "description": "Target paper account ID. Use 'paper-default' if none specified.",
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "MUST be true. Set to true only if the user explicitly confirmed deployment.",
                },
            },
            "required": ["strategy_id", "user_confirmed"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.RESTRICTED

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            output="",
            error="deploy_strategy requires async execution.",
        )

    async def async_execute(self, args: dict[str, Any]) -> ToolResult | None:
        strategy_id = args.get("strategy_id", "")
        user_confirmed = args.get("user_confirmed", False)
        account_id = args.get("account_id", "paper-default")

        if not strategy_id:
            return ToolResult(output="Missing strategy_id", error="Missing parameter")

        if not user_confirmed:
            return ToolResult(
                output=(
                    "Deployment NOT executed — user confirmation required. "
                    "Please present the strategy summary to the user and ask "
                    "for explicit confirmation before deploying."
                ),
                error="User confirmation required before deployment",
            )

        try:
            result = await self._deploy_fn(strategy_id, account_id)
            return ToolResult(output=result)
        except Exception as exc:
            return ToolResult(output=f"Deploy failed: {exc}", error=str(exc))


class StrategyStopTool(BaseTool):
    """Stop a running strategy deployment."""

    def __init__(self, stop_fn: Any) -> None:
        self._stop_fn = stop_fn

    @property
    def name(self) -> str:
        return "stop_strategy"

    @property
    def description(self) -> str:
        return "Stop a running strategy deployment and halt its automatic trading."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "The strategy ID to stop.",
                },
            },
            "required": ["strategy_id"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            output="",
            error="stop_strategy requires async execution.",
        )

    async def async_execute(self, args: dict[str, Any]) -> ToolResult | None:
        strategy_id = args.get("strategy_id", "")
        if not strategy_id:
            return ToolResult(output="Missing strategy_id", error="Missing parameter")

        try:
            result = await self._stop_fn(strategy_id)
            return ToolResult(output=result)
        except Exception as exc:
            return ToolResult(output=f"Stop failed: {exc}", error=str(exc))
