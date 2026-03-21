"""Test fixtures for strategy-engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_yaml(tmp_path: Path):
    """Create a temporary YAML strategy file helper."""

    def _write(content: str, filename: str = "strategy.yaml") -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return p

    return _write
