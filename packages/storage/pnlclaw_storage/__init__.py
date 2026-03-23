"""pnlclaw_storage -- Local persistence (SQLite + Parquet).

Public API
----------
.. autoclass:: AsyncSQLiteManager
.. autoclass:: MigrationRunner
.. autoclass:: StrategyRepository
.. autoclass:: BacktestRepository
.. autoclass:: PaperAccountRepository
.. autoclass:: AuditLogRepository
"""

from pnlclaw_storage.migrations import Migration, MigrationRunner
from pnlclaw_storage.migrations_pkg import ALL_MIGRATIONS
from pnlclaw_storage.repositories.audit_logs import AuditLogRepository
from pnlclaw_storage.repositories.backtests import BacktestRepository
from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository
from pnlclaw_storage.repositories.strategies import StrategyRepository
from pnlclaw_storage.sqlite import AsyncSQLiteManager

__all__ = [
    "ALL_MIGRATIONS",
    "AsyncSQLiteManager",
    "AuditLogRepository",
    "BacktestRepository",
    "Migration",
    "MigrationRunner",
    "PaperAccountRepository",
    "StrategyRepository",
]
