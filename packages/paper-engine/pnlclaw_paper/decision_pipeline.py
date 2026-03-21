"""Real-time decision pipeline for paper trading.

Complete chain: Signal → Dedup → Throttle → Risk Pre-check →
TradeIntent Generation → Validation → Execution → Audit.

Each step may terminate the pipeline and return a reason.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.strategy import Signal
from pnlclaw_types.trading import OrderSide, OrderType

from pnlclaw_core.infra.dedupe import Deduplicator

from pnlclaw_risk.engine import RiskEngine
from pnlclaw_risk.kill_switch import KillSwitch
from pnlclaw_risk.validators import validate

from pnlclaw_security.audit import AuditEvent, AuditEventType, AuditLogger, AuditSeverity

from pnlclaw_paper.orders import PaperOrderManager


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


class PipelineAction(str, Enum):
    """Outcome of pipeline processing."""

    EXECUTED = "executed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class PipelineResult:
    """Result of processing a signal through the decision pipeline."""

    action: PipelineAction
    reason: str = ""
    order_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------


@dataclass
class PipelineConfig:
    """Configuration for the decision pipeline."""

    # Signal deduplication TTL
    dedupe_ttl_seconds: float = 60.0
    # Minimum interval between orders for the same symbol (throttle)
    min_order_interval_seconds: float = 10.0
    # Default quantity when signal doesn't specify
    default_quantity: float = 0.01
    # Default account ID for order placement
    default_account_id: str = ""


# ---------------------------------------------------------------------------
# DecisionPipeline
# ---------------------------------------------------------------------------


class DecisionPipeline:
    """Processes trading signals through a multi-stage pipeline.

    Stages:
      1. Kill switch check
      2. Signal deduplication
      3. Throttle (min interval per symbol)
      4. Risk engine pre-check
      5. TradeIntent generation from Signal
      6. TradeIntent validation
      7. Order execution
      8. Audit logging

    Args:
        risk_engine: Risk engine instance for pre-trade checks.
        order_manager: Paper order manager for execution.
        audit_logger: Audit logger for recording actions.
        kill_switch: KillSwitch instance.
        config: Pipeline configuration.
        risk_context_provider: Callable that returns current risk context dict.
    """

    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        order_manager: PaperOrderManager,
        audit_logger: AuditLogger | None = None,
        kill_switch: KillSwitch | None = None,
        config: PipelineConfig | None = None,
        risk_context_provider: Any = None,
        current_price_provider: Any = None,
    ) -> None:
        self._risk_engine = risk_engine
        self._order_mgr = order_manager
        self._audit = audit_logger
        self._kill_switch = kill_switch
        self._config = config or PipelineConfig()
        self._risk_context_provider = risk_context_provider
        self._current_price_provider = current_price_provider

        self._deduplicator = Deduplicator(
            ttl_seconds=self._config.dedupe_ttl_seconds,
        )
        # symbol → last order epoch seconds
        self._last_order_times: dict[str, float] = {}

    def process_signal(self, signal: Signal) -> PipelineResult:
        """Process a trading signal through the full pipeline.

        Args:
            signal: Trading signal from a strategy.

        Returns:
            PipelineResult indicating what happened.
        """
        # Stage 1: Kill switch
        if self._kill_switch and self._kill_switch.is_active:
            result = PipelineResult(
                action=PipelineAction.BLOCKED,
                reason="Kill switch is active",
            )
            self._audit_event(signal, result, "kill_switch_blocked")
            return result

        # Stage 2: Deduplication
        dedupe_key = f"{signal.strategy_id}:{signal.symbol}:{signal.side.value}:{signal.timestamp}"
        if self._deduplicator.is_duplicate(dedupe_key):
            return PipelineResult(
                action=PipelineAction.SKIPPED,
                reason="Duplicate signal",
            )

        # Stage 3: Throttle
        now = time.time()
        last_time = self._last_order_times.get(signal.symbol)
        if last_time is not None:
            elapsed = now - last_time
            if elapsed < self._config.min_order_interval_seconds:
                return PipelineResult(
                    action=PipelineAction.SKIPPED,
                    reason=f"Throttled: {elapsed:.1f}s since last order "
                           f"(min {self._config.min_order_interval_seconds:.0f}s)",
                )

        # Stage 4: Generate TradeIntent from Signal
        intent = self._signal_to_intent(signal)

        # Stage 5: Risk engine pre-check
        risk_ctx = {}
        if self._risk_context_provider:
            risk_ctx = self._risk_context_provider()
        risk_decision = self._risk_engine.pre_check(intent, risk_ctx)
        if not risk_decision.allowed:
            result = PipelineResult(
                action=PipelineAction.BLOCKED,
                reason=f"Risk denied: {risk_decision.reason}",
                details={"triggered_rules": risk_decision.rule_id},
            )
            self._audit_event(signal, result, "risk_blocked")
            return result

        # Stage 6: TradeIntent validation
        current_price = 0.0
        if self._current_price_provider:
            current_price = self._current_price_provider(signal.symbol)
        validation = validate(intent, current_price)
        if not validation.valid:
            result = PipelineResult(
                action=PipelineAction.BLOCKED,
                reason=f"Validation failed: {'; '.join(validation.errors)}",
            )
            self._audit_event(signal, result, "validation_failed")
            return result

        # Stage 7: Execute — place order
        account_id = self._config.default_account_id
        order = self._order_mgr.place_order(
            account_id,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            price=intent.price,
        )

        # Record throttle time
        self._last_order_times[signal.symbol] = time.time()

        result = PipelineResult(
            action=PipelineAction.EXECUTED,
            reason="Order placed successfully",
            order_id=order.id,
        )

        # Stage 8: Audit
        self._audit_event(signal, result, "order_executed")

        return result

    # -- internal --------------------------------------------------------------

    def _signal_to_intent(self, signal: Signal) -> TradeIntent:
        """Convert a Signal to a TradeIntent."""
        return TradeIntent(
            symbol=signal.symbol,
            side=signal.side,
            quantity=self._config.default_quantity,
            price=None,  # Market order
            order_type=OrderType.MARKET,
            reasoning=signal.reason or f"Signal from {signal.strategy_id}",
            confidence=signal.strength,
            risk_params={},
            timestamp=int(time.time() * 1000),
        )

    def _audit_event(
        self,
        signal: Signal,
        result: PipelineResult,
        action: str,
    ) -> None:
        """Log an audit event if logger is available."""
        if self._audit is None:
            return
        severity = (
            AuditSeverity.INFO
            if result.action == PipelineAction.EXECUTED
            else AuditSeverity.WARN
        )
        self._audit.log(AuditEvent(
            event_type=AuditEventType.ORDER_INTENT,
            severity=severity,
            actor="pipeline",
            action=action,
            resource=signal.symbol,
            outcome=result.action.value,
            details={
                "strategy_id": signal.strategy_id,
                "signal_side": signal.side.value,
                "signal_strength": signal.strength,
                "result_reason": result.reason,
                "order_id": result.order_id or "",
            },
        ))
