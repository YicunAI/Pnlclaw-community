"""Conftest for local-api tests — adds app to sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure ``services/local-api/`` is on sys.path so ``import app`` works.
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))
