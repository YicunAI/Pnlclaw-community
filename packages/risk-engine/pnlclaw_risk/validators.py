"""TradeIntent validators — pre-execution sanity checks.

Validates price reasonability, stop-loss presence, and direction
consistency before a TradeIntent is submitted to the risk engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.trading import OrderSide


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a TradeIntent."""

    valid: bool
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

_DEFAULT_MAX_PRICE_DEVIATION = 0.05  # 5%


def validate_price(
    intent: TradeIntent,
    current_price: float,
    *,
    max_deviation: float = _DEFAULT_MAX_PRICE_DEVIATION,
) -> list[str]:
    """Check that the intent price is within reasonable deviation of current price.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []
    target = intent.price
    if target is None or current_price <= 0:
        return errors

    deviation = abs(target - current_price) / current_price
    if deviation > max_deviation:
        errors.append(
            f"Price {target:.2f} deviates {deviation:.1%} from current {current_price:.2f} (max {max_deviation:.0%})"
        )
    return errors


def validate_stop_loss(intent: TradeIntent) -> list[str]:
    """Ensure the intent has a stop_loss in risk_params."""
    errors: list[str] = []
    if "stop_loss" not in intent.risk_params:
        errors.append("Missing stop_loss in risk_params")
        return errors

    stop_loss = intent.risk_params["stop_loss"]
    if not isinstance(stop_loss, (int, float)) or stop_loss <= 0:
        errors.append(f"Invalid stop_loss value: {stop_loss}")
    return errors


def validate_direction(intent: TradeIntent) -> list[str]:
    """Check direction consistency: for a BUY, take_profit must be above entry price.

    For a SELL (short), take_profit must be below entry price.
    Only validates when both entry price and take_profit are available.
    """
    errors: list[str] = []
    take_profit = intent.risk_params.get("take_profit")
    entry = intent.price

    if take_profit is None or entry is None:
        return errors

    if intent.side == OrderSide.BUY and take_profit <= entry:
        errors.append(f"BUY direction but take_profit ({take_profit:.2f}) <= entry ({entry:.2f})")
    elif intent.side == OrderSide.SELL and take_profit >= entry:
        errors.append(f"SELL direction but take_profit ({take_profit:.2f}) >= entry ({entry:.2f})")

    # Also check stop_loss direction
    stop_loss = intent.risk_params.get("stop_loss")
    if stop_loss is not None:
        if intent.side == OrderSide.BUY and stop_loss >= entry:
            errors.append(f"BUY direction but stop_loss ({stop_loss:.2f}) >= entry ({entry:.2f})")
        elif intent.side == OrderSide.SELL and stop_loss <= entry:
            errors.append(f"SELL direction but stop_loss ({stop_loss:.2f}) <= entry ({entry:.2f})")
    return errors


# ---------------------------------------------------------------------------
# Combined validator
# ---------------------------------------------------------------------------


def validate(intent: TradeIntent, current_price: float) -> ValidationResult:
    """Run all validators on a TradeIntent.

    Args:
        intent: The trade intent to validate.
        current_price: Current market price for deviation checks.

    Returns:
        ValidationResult with valid=True if all checks pass.
    """
    errors: list[str] = []
    errors.extend(validate_price(intent, current_price))
    errors.extend(validate_stop_loss(intent))
    errors.extend(validate_direction(intent))
    return ValidationResult(valid=len(errors) == 0, errors=errors)
