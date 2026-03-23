"""pnlclaw_storage.migrations — migration registry."""

from __future__ import annotations

from pnlclaw_storage.migrations import Migration

# Import all migration modules so they register themselves
from pnlclaw_storage.migrations_pkg.v001_initial import migration as v001

ALL_MIGRATIONS: list[Migration] = [v001]
