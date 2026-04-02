"""pnlclaw_storage.migrations — migration registry."""

from __future__ import annotations

from pnlclaw_storage.migrations import Migration

# Import all migration modules so they register themselves
from pnlclaw_storage.migrations_pkg.v001_initial import migration as v001
from pnlclaw_storage.migrations_pkg.v002_strategy_versions import migration as v002
from pnlclaw_storage.migrations_pkg.v003_chat_sessions import migration as v003
from pnlclaw_storage.migrations_pkg.v004_backtest_curves import migration as v004
from pnlclaw_storage.migrations_pkg.v005_backtest_symbol_interval import migration as v005
from pnlclaw_storage.migrations_pkg.v006_user_id import migration as v006

ALL_MIGRATIONS: list[Migration] = [v001, v002, v003, v004, v005, v006]
