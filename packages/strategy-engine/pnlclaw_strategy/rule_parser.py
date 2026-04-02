"""Parse human-readable strategy rule strings into ConditionRule objects.

Handles patterns produced by the AI strategy generator:
    "EMA21 > EMA55"
    "EMA9 crosses_above EMA21"
    "MACD Histogram > 0"
    "RSI < 30"
    "SMA20 crosses_below SMA50"
"""

from __future__ import annotations

import re
from typing import Any

from pnlclaw_strategy.models import ConditionRule, EntryRules, ExitRules

_OPERATOR_MAP: dict[str, str] = {
    ">": "greater_than",
    "<": "less_than",
    "=": "equal",
    ">=": "greater_than",
    "<=": "less_than",
    "crosses_above": "crosses_above",
    "crosses_below": "crosses_below",
    "greater_than": "greater_than",
    "less_than": "less_than",
    "equal": "equal",
}

_INDICATOR_ALIASES: dict[str, str] = {
    "ema": "ema",
    "sma": "sma",
    "rsi": "rsi",
    "macd": "macd",
    "macd_signal": "macd_signal",
    "macd_histogram": "macd_histogram",
    "macd signal": "macd_signal",
    "macd histogram": "macd_histogram",
    "bbands": "bbands",
    "bbands_upper": "bbands_upper",
    "bbands_lower": "bbands_lower",
    "bbands_middle": "bbands_middle",
    "bbands upper": "bbands_upper",
    "bbands lower": "bbands_lower",
    "bbands middle": "bbands_middle",
    "bollinger upper": "bbands_upper",
    "bollinger lower": "bbands_lower",
    "bollinger middle": "bbands_middle",
}

_COMPOUND_INDICATORS = re.compile(
    r"^(macd\s+histogram|macd\s+signal|bbands\s+upper|bbands\s+lower|bbands\s+middle"
    r"|bollinger\s+upper|bollinger\s+lower|bollinger\s+middle)",
    re.IGNORECASE,
)

_SIMPLE_INDICATOR = re.compile(
    r"^([a-zA-Z_]+)(\d+)?$",
)


def _parse_indicator_token(token: str) -> tuple[str, dict[str, Any]]:
    """Parse an indicator token into (name, params).

    Examples:
        "EMA21"  -> ("ema", {"period": 21})
        "RSI"    -> ("rsi", {})
        "MACD Histogram" -> ("macd_histogram", {})
    """
    token = token.strip()
    lower = token.lower()

    if lower in _INDICATOR_ALIASES:
        return _INDICATOR_ALIASES[lower], {}

    m = _SIMPLE_INDICATOR.match(token)
    if m:
        name_part = m.group(1).lower()
        period_part = m.group(2)
        ind_name = _INDICATOR_ALIASES.get(name_part, name_part)
        params: dict[str, Any] = {}
        if period_part:
            params["period"] = int(period_part)
        return ind_name, params

    return lower, {}


def _try_parse_number(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_rule_string(rule: str) -> ConditionRule:
    """Parse a single rule string into a ConditionRule.

    Supports:
        "EMA21 > EMA55"
        "EMA9 crosses_above EMA21"
        "MACD Histogram > 0"
        "RSI < 30"
    """
    rule = rule.strip()

    # First, try to extract a compound indicator at the start
    left_token: str
    remainder: str

    m = _COMPOUND_INDICATORS.match(rule)
    if m:
        left_token = m.group(1)
        remainder = rule[m.end() :].strip()
    else:
        parts = rule.split(None, 1)
        if len(parts) < 2:
            raise ValueError(f"Cannot parse rule: '{rule}'")
        left_token = parts[0]
        remainder = parts[1]

    operator: str | None = None
    right_part: str = ""

    for op_str in sorted(_OPERATOR_MAP.keys(), key=len, reverse=True):
        if op_str in (" ", ""):
            continue
        idx = remainder.lower().find(op_str.lower() if len(op_str) > 1 else op_str)
        if idx != -1:
            prefix = remainder[:idx].strip()
            if prefix:
                left_token = left_token + " " + prefix
            operator = _OPERATOR_MAP[op_str]
            right_part = remainder[idx + len(op_str) :].strip()
            break

    if operator is None:
        for op_str, op_name in _OPERATOR_MAP.items():
            pattern = re.compile(r"\b" + re.escape(op_str) + r"\b", re.IGNORECASE)
            match = pattern.search(remainder)
            if match:
                prefix = remainder[: match.start()].strip()
                if prefix:
                    left_token = left_token + " " + prefix
                operator = op_name
                right_part = remainder[match.end() :].strip()
                break

    if operator is None:
        raise ValueError(f"No operator found in rule: '{rule}'")

    left_name, left_params = _parse_indicator_token(left_token)

    num_val = _try_parse_number(right_part)
    if num_val is not None:
        return ConditionRule(
            indicator=left_name,
            params=left_params,
            operator=operator,
            comparator=num_val,
        )

    m2 = _COMPOUND_INDICATORS.match(right_part)
    if m2:
        right_token = m2.group(1)
        extra = right_part[m2.end() :].strip()
        if extra:
            right_token = right_token + " " + extra
    else:
        right_token = right_part

    right_name, right_params = _parse_indicator_token(right_token)

    return ConditionRule(
        indicator=left_name,
        params=left_params,
        operator=operator,
        comparator={"indicator": right_name, "params": right_params},
    )


def parse_rules_list(rules: list[Any]) -> list[ConditionRule]:
    """Parse a list of rules (strings or dicts) into ConditionRule objects."""
    result: list[ConditionRule] = []
    for rule in rules:
        if isinstance(rule, str):
            try:
                result.append(parse_rule_string(rule))
            except ValueError:
                continue
        elif isinstance(rule, dict):
            if "indicator" in rule and "operator" in rule:
                try:
                    result.append(ConditionRule.model_validate(rule))
                except Exception:
                    continue
    return result


def parse_entry_rules(raw: dict[str, Any]) -> EntryRules:
    """Parse raw entry_rules dict into structured EntryRules."""
    long_raw = raw.get("long", [])
    short_raw = raw.get("short", [])

    return EntryRules(
        long=parse_rules_list(long_raw) if isinstance(long_raw, list) else [],
        short=parse_rules_list(short_raw) if isinstance(short_raw, list) else [],
    )


def parse_exit_rules(raw: dict[str, Any]) -> ExitRules:
    """Parse raw exit_rules dict into structured ExitRules."""
    close_long_raw = raw.get("close_long", [])
    close_short_raw = raw.get("close_short", [])

    if isinstance(close_long_raw, str):
        close_long_raw = [close_long_raw]
    if isinstance(close_short_raw, str):
        close_short_raw = [close_short_raw]

    return ExitRules(
        close_long=parse_rules_list(close_long_raw) if isinstance(close_long_raw, list) else [],
        close_short=parse_rules_list(close_short_raw) if isinstance(close_short_raw, list) else [],
    )
