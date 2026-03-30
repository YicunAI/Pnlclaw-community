"""Strategy Runner — continuously executes deployed strategies against live market data.

Subscribes to kline events from MarketDataService, feeds them through
StrategyRuntime, and converts resulting Signals into paper orders via
PaperExecutionEngine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ORDER_SIZE_USDT = 1000.0
MAX_POSITION_SIZE_USDT = 5000.0
MAX_SIGNAL_HISTORY = 50
WARMUP_KLINE_COUNT = 200


def _kline_label_ms(event: Any) -> int:
    """Return the kline open/label timestamp for use as signal time.

    Charts label candles by their open time (e.g. the "06:00 candle" spans
    06:00–07:00).  Strategy fills should be timestamped with this label so
    they visually align with the candle that produced the signal.
    """
    ts: int = getattr(event, "timestamp", 0)
    return ts if ts else int(time.time() * 1000)


def _config_has_rules(cfg: dict[str, Any]) -> bool:
    """Return True if a strategy config contains non-empty trading rules."""
    entry = cfg.get("entry_rules") or {}
    exit_ = cfg.get("exit_rules") or {}
    return bool(entry) or bool(exit_)


@dataclass
class RunnerSlot:
    """In-flight state for a single strategy deployment."""

    deployment_id: str
    strategy_id: str
    account_id: str
    symbol: str
    interval: str
    runtime: Any  # StrategyRuntime
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    last_signal_ts: int = 0
    signals_emitted: int = 0
    orders_placed: int = 0
    errors: int = 0
    signal_history: list[dict[str, Any]] = field(default_factory=list)


class StrategyRunner:
    """Manages multiple concurrently running strategy deployments.

    Lifecycle:
        1. ``start()`` — restores persisted deployments and hooks into kline events.
        2. ``deploy(deployment_id, strategy_config, account_id)`` — adds a new slot.
        3. ``stop_deployment(deployment_id)`` — removes a slot.
        4. ``stop()`` — tears down all slots and saves state.
    """

    def __init__(
        self,
        paper_engine: Any,
        market_service: Any,
        *,
        state_dir: Path | None = None,
        order_size_usdt: float = DEFAULT_ORDER_SIZE_USDT,
    ) -> None:
        self._paper = paper_engine
        self._market = market_service
        self._slots: dict[str, RunnerSlot] = {}
        self._state_dir = state_dir or Path.home() / ".pnlclaw" / "runner"
        self._order_size = order_size_usdt
        self._running = False
        self._kline_registered = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def active_deployments(self) -> list[str]:
        return list(self._slots.keys())

    def get_slot_status(self, deployment_id: str) -> dict[str, Any] | None:
        slot = self._slots.get(deployment_id)
        if slot is None:
            return None
        return {
            "deployment_id": slot.deployment_id,
            "strategy_id": slot.strategy_id,
            "account_id": slot.account_id,
            "symbol": slot.symbol,
            "interval": slot.interval,
            "position": slot.runtime.position,
            "bar_count": slot.runtime.bar_count,
            "signals_emitted": slot.signals_emitted,
            "orders_placed": slot.orders_placed,
            "errors": slot.errors,
            "last_signal_ts": slot.last_signal_ts,
            "recent_signals": slot.signal_history[-20:],
        }

    def get_signal_history(self, deployment_id: str) -> list[dict[str, Any]]:
        slot = self._slots.get(deployment_id)
        if slot is None:
            return []
        return list(slot.signal_history)

    async def start(self) -> None:
        self._running = True
        self._ensure_kline_hook()
        await self._restore_state()
        logger.info(
            "StrategyRunner started, %d deployments restored",
            len(self._slots),
        )

    async def stop(self) -> None:
        self._running = False
        self._save_state()
        self._slots.clear()
        logger.info("StrategyRunner stopped")

    async def deploy(
        self,
        deployment_id: str,
        strategy_config: dict[str, Any],
        account_id: str,
    ) -> str | None:
        """Compile and activate a strategy deployment. Returns error string or None."""
        if deployment_id in self._slots:
            return f"Deployment {deployment_id} already running"

        if not _config_has_rules(strategy_config):
            return (
                "Cannot deploy: entry_rules and exit_rules are empty. "
                "The strategy has no trading logic — save complete rules first."
            )

        strategy_id = strategy_config.get("id", "")
        existing = [
            s for s in self._slots.values()
            if s.strategy_id == strategy_id
        ]
        if existing:
            dep_ids = ", ".join(s.deployment_id for s in existing)
            return (
                f"Strategy {strategy_id} is already deployed ({dep_ids}). "
                f"Stop existing deployment(s) first."
            )

        if account_id in ("paper-default", "auto", ""):
            new_account_id = await self._create_strategy_account(strategy_config)
            if new_account_id:
                account_id = new_account_id

        try:
            from pnlclaw_agent.tools.strategy_tools import _sanitize_config
            from pnlclaw_strategy.compiler import compile as compile_strategy
            from pnlclaw_strategy.models import EngineStrategyConfig
            from pnlclaw_strategy.runtime import StrategyRuntime

            cfg = dict(strategy_config)
            _sanitize_config(cfg)
            engine_config = EngineStrategyConfig.model_validate(cfg)
            compiled = compile_strategy(engine_config)
            runtime = StrategyRuntime(compiled, direction=engine_config.direction)
        except Exception as exc:
            logger.error("Failed to compile strategy for deployment %s: %s", deployment_id, exc)
            return f"Compilation failed: {exc}"

        symbol = engine_config.symbols[0] if engine_config.symbols else "BTC/USDT"
        interval = engine_config.interval or "1h"

        slot = RunnerSlot(
            deployment_id=deployment_id,
            strategy_id=engine_config.id,
            account_id=account_id,
            symbol=symbol,
            interval=interval,
            runtime=runtime,
            config_snapshot=strategy_config,
        )
        self._slots[deployment_id] = slot
        self._ensure_kline_hook()

        await self._ensure_symbol_subscribed(symbol, interval)

        await self._warmup_historical_klines(slot)

        self._save_state()
        logger.info(
            "Deployed strategy %s on %s/%s → account %s (warmup bars: %d)",
            engine_config.id, symbol, interval, account_id, runtime.bar_count,
        )
        return None

    async def _ensure_symbol_subscribed(self, symbol: str, interval: str) -> None:
        """Subscribe the market service to the strategy's symbol and check interval support."""
        try:
            await self._market.add_symbol(symbol)
        except Exception:
            logger.warning("Failed to subscribe symbol %s for runner", symbol, exc_info=True)

        _intervals_raw = (
            os.environ.get("PNLCLAW_KLINE_INTERVALS")
            or os.environ.get("PNLCLAW_DEFAULT_INTERVAL")
            or "30m,1h"
        )
        supported = [i.strip() for i in _intervals_raw.split(",") if i.strip()]
        if interval not in supported:
            logger.warning(
                "Strategy interval '%s' is not in configured kline intervals %s. "
                "Signals will NOT fire. Set PNLCLAW_KLINE_INTERVALS to include '%s'.",
                interval, supported, interval,
            )
        else:
            logger.info(
                "Strategy interval '%s' is supported (configured: %s).",
                interval, supported,
            )

    async def _create_strategy_account(self, strategy_config: dict[str, Any]) -> str | None:
        """Create a dedicated paper account for a strategy deployment."""
        try:
            from app.core.dependencies import get_paper_account_manager
            from pnlclaw_paper.accounts import AccountType

            mgr = get_paper_account_manager()
            if mgr is None:
                return None

            strategy_name = strategy_config.get("name") or strategy_config.get("id", "unknown")
            strategy_id = strategy_config.get("id", "")
            acct = mgr.create_account(
                name=f"Strategy: {strategy_name}",
                initial_balance=float(
                    os.environ.get("PNLCLAW_PAPER_STARTING_BALANCE", "100000")
                ),
                account_type=AccountType.STRATEGY,
                strategy_id=strategy_id,
            )
            logger.info(
                "Auto-created strategy account %s for strategy %s",
                acct.id, strategy_id,
            )
            return acct.id
        except Exception:
            logger.warning("Failed to auto-create strategy account", exc_info=True)
            return None

    async def _warmup_historical_klines(self, slot: RunnerSlot) -> None:
        """Preload historical closed klines via REST so indicators start warm."""
        try:
            klines = await self._market.fetch_klines_rest(
                slot.symbol,
                exchange="binance",
                market_type="spot",
                interval=slot.interval,
                limit=WARMUP_KLINE_COUNT,
            )
            if not klines:
                logger.warning("No historical klines for warmup (%s/%s)", slot.symbol, slot.interval)
                return

            fed = 0
            for kline in klines:
                if not getattr(kline, "closed", True):
                    continue
                slot.runtime.on_kline(kline)
                fed += 1

            logger.info(
                "Warmup: fed %d historical klines to deployment %s (%s/%s), bar_count=%d",
                fed, slot.deployment_id, slot.symbol, slot.interval, slot.runtime.bar_count,
            )
        except Exception:
            logger.warning(
                "Historical kline warmup failed for deployment %s",
                slot.deployment_id, exc_info=True,
            )

    def stop_deployment(self, deployment_id: str) -> bool:
        slot = self._slots.pop(deployment_id, None)
        if slot is None:
            return False
        self._save_state()
        logger.info("Stopped deployment %s (strategy %s)", deployment_id, slot.strategy_id)
        return True

    def stop_by_strategy_id(self, strategy_id: str) -> list[str]:
        """Stop ALL deployments for a given strategy_id and return their ids."""
        to_remove = [
            dep_id for dep_id, slot in self._slots.items()
            if slot.strategy_id == strategy_id
        ]
        for dep_id in to_remove:
            slot = self._slots.pop(dep_id)
            logger.info("Stopped deployment %s (strategy %s)", dep_id, slot.strategy_id)
        if to_remove:
            self._save_state()
        return to_remove

    # ------------------------------------------------------------------
    # Kline event handler
    # ------------------------------------------------------------------

    def _ensure_kline_hook(self) -> None:
        if self._kline_registered:
            return
        try:
            from pnlclaw_market import MarketDataService as _MDS
            svc: _MDS = self._market
            svc.on_kline(self._on_kline)
            self._kline_registered = True
        except Exception:
            logger.warning("Failed to register kline handler for StrategyRunner", exc_info=True)

    def _on_kline(self, event: Any) -> None:
        """Synchronous kline callback — route to matching slots."""
        if not self._running:
            return
        kline_close_ts = _kline_label_ms(event)
        for slot in list(self._slots.values()):
            if not self._matches(slot, event):
                continue
            try:
                signal = slot.runtime.on_kline(event)
                if signal is not None:
                    slot.signals_emitted += 1
                    slot.last_signal_ts = kline_close_ts
                    sig_record = {
                        "ts": kline_close_ts,
                        "side": signal.side.value if hasattr(signal.side, "value") else str(signal.side),
                        "reason": getattr(signal, "reason", ""),
                        "strength": getattr(signal, "strength", None),
                        "price": event.close,
                        "symbol": slot.symbol,
                    }
                    slot.signal_history.append(sig_record)
                    if len(slot.signal_history) > MAX_SIGNAL_HISTORY:
                        slot.signal_history = slot.signal_history[-MAX_SIGNAL_HISTORY:]
                    asyncio.ensure_future(self._execute_signal(slot, signal, event.close, kline_close_ts))
                asyncio.ensure_future(self._broadcast_status(slot))
            except Exception:
                slot.errors += 1
                logger.warning(
                    "Error processing kline for deployment %s",
                    slot.deployment_id, exc_info=True,
                )

    @staticmethod
    def _matches(slot: RunnerSlot, event: Any) -> bool:
        if event.symbol != slot.symbol:
            return False
        event_interval = getattr(event, "interval", None)
        if event_interval and event_interval != slot.interval:
            return False
        # Only accept klines from a single source (binance/spot) to avoid
        # duplicate bars from multiple exchanges feeding the same runtime.
        event_exchange = getattr(event, "exchange", None)
        event_market_type = getattr(event, "market_type", None)
        if event_exchange and event_exchange != "binance":
            return False
        if event_market_type and event_market_type != "spot":
            return False
        return True

    async def _execute_signal(
        self, slot: RunnerSlot, signal: Any, current_price: float, signal_ts_ms: int | None = None,
    ) -> None:
        """Convert a Signal into a paper order."""
        try:
            from pnlclaw_types.trading import OrderSide

            side = signal.side
            order_type = "market"
            quantity = self._order_size

            pos_side = "long" if side == OrderSide.BUY else "short"

            if slot.runtime.position == "flat" and side in (OrderSide.BUY, OrderSide.SELL):
                reduce_only = False
            else:
                reduce_only = True

            order = await self._paper.place_order(
                account_id=slot.account_id,
                symbol=slot.symbol,
                side=side.value if hasattr(side, "value") else str(side),
                order_type=order_type,
                quantity=quantity,
                leverage=1,
                margin_mode="cross",
                pos_side=pos_side,
                reduce_only=reduce_only,
                mark_price=current_price,
                signal_timestamp_ms=signal_ts_ms,
            )
            slot.orders_placed += 1
            logger.info(
                "Runner placed order for deployment %s: %s %s %s @ %.2f (reason: %s)",
                slot.deployment_id, side, slot.symbol, order_type,
                current_price, signal.reason,
            )

            await self._broadcast_signal(slot, signal, order)

        except Exception:
            slot.errors += 1
            logger.warning(
                "Failed to place order for deployment %s",
                slot.deployment_id, exc_info=True,
            )

    async def _broadcast_signal(self, slot: RunnerSlot, signal: Any, order: Any) -> None:
        """Push strategy signal event via paper WS channel."""
        try:
            from app.api.v1.ws import broadcast_paper_event
            await broadcast_paper_event(
                slot.account_id,
                "strategy_signal",
                {
                    "deployment_id": slot.deployment_id,
                    "strategy_id": slot.strategy_id,
                    "signal": signal.model_dump() if hasattr(signal, "model_dump") else str(signal),
                    "order_id": order.id if hasattr(order, "id") else str(order),
                },
            )
        except Exception:
            logger.debug("Failed to broadcast strategy signal event", exc_info=True)

    async def _broadcast_status(self, slot: RunnerSlot) -> None:
        """Push runner_status event with live slot metrics via paper WS."""
        try:
            from app.api.v1.ws import broadcast_paper_event
            await broadcast_paper_event(
                slot.account_id,
                "runner_status",
                {
                    "deployment_id": slot.deployment_id,
                    "strategy_id": slot.strategy_id,
                    "symbol": slot.symbol,
                    "interval": slot.interval,
                    "position": slot.runtime.position,
                    "bar_count": slot.runtime.bar_count,
                    "signals_emitted": slot.signals_emitted,
                    "orders_placed": slot.orders_placed,
                    "errors": slot.errors,
                    "last_signal_ts": slot.last_signal_ts,
                },
            )
        except Exception:
            logger.debug("Failed to broadcast runner status", exc_info=True)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            state_file = self._state_dir / "deployments.json"
            data = {}
            for dep_id, slot in self._slots.items():
                data[dep_id] = {
                    "deployment_id": slot.deployment_id,
                    "strategy_id": slot.strategy_id,
                    "account_id": slot.account_id,
                    "config_snapshot": slot.config_snapshot,
                    "signals_emitted": slot.signals_emitted,
                    "orders_placed": slot.orders_placed,
                }
            state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("Failed to save runner state", exc_info=True)

    async def _restore_state(self) -> None:
        state_file = self._state_dir / "deployments.json"
        if not state_file.exists():
            return
        try:
            data = json.loads(state_file.read_text(encoding="utf-8-sig"))
            if not data:
                return

            seen_strategies: set[str] = set()
            for dep_id, info in data.items():
                if dep_id in self._slots:
                    continue
                strategy_id = info.get("strategy_id", "")

                if strategy_id in seen_strategies:
                    logger.info(
                        "Skipping duplicate deployment %s for strategy %s",
                        dep_id, strategy_id,
                    )
                    continue

                config = await self._load_fresh_config(strategy_id, info.get("config_snapshot", {}))

                if not _config_has_rules(config):
                    logger.warning(
                        "Skipping restore of deployment %s: strategy %s has empty rules",
                        dep_id, strategy_id,
                    )
                    continue

                err = await self.deploy(
                    deployment_id=dep_id,
                    strategy_config=config,
                    account_id=info.get("account_id", "auto"),
                )
                if err:
                    logger.warning("Failed to restore deployment %s: %s", dep_id, err)
                else:
                    seen_strategies.add(strategy_id)

            logger.info("Restored %d runner deployments from disk", len(self._slots))
        except Exception:
            logger.warning("Failed to restore runner state", exc_info=True)

    async def _load_fresh_config(
        self, strategy_id: str, fallback: dict[str, Any],
    ) -> dict[str, Any]:
        """Try to load the latest strategy config from the DB/store."""
        try:
            from app.api.v1.strategies import _get_strategy
            config = await _get_strategy(strategy_id)
            if config is not None:
                fresh = config.model_dump()
                logger.info(
                    "Restored fresh config for strategy %s (v%d, rules: entry=%s exit=%s)",
                    strategy_id, fresh.get("version", 0),
                    bool(fresh.get("entry_rules")), bool(fresh.get("exit_rules")),
                )
                return fresh
        except Exception:
            logger.debug("Could not load fresh config for %s, using snapshot", strategy_id, exc_info=True)
        return fallback
