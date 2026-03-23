"""Minimal ANSI styling (no rich/textual)."""

from __future__ import annotations

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
DIM = "\033[2m"


def ok(text: str) -> str:
    return f"{GREEN}{text}{RESET}"


def warn(text: str) -> str:
    return f"{YELLOW}{text}{RESET}"


def err(text: str) -> str:
    return f"{RED}{text}{RESET}"


def info(text: str) -> str:
    return f"{CYAN}{text}{RESET}"


def dim(text: str) -> str:
    return f"{DIM}{text}{RESET}"
