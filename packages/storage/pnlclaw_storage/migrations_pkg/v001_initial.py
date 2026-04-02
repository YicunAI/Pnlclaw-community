"""V001 — Initial schema for PnLClaw Community v0.1.

Creates 6 tables:
  1. strategies     — strategy configurations
  2. backtests      — backtest run results
  3. paper_accounts — paper trading accounts
  4. paper_orders   — paper trading orders
  5. paper_positions— paper trading positions
  6. audit_logs     — security/operational audit trail

All tables use IF NOT EXISTS for idempotency.
Schema designed so that v0.2 can ``ALTER TABLE ADD COLUMN tenant_id TEXT``
without rebuilding any table.
"""

from __future__ import annotations

import aiosqlite

from pnlclaw_storage.migrations import Migration

_STATEMENTS: list[str] = [
    # 1. strategies
    """
    CREATE TABLE IF NOT EXISTS strategies (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        type        TEXT NOT NULL,
        config_json TEXT NOT NULL DEFAULT '{}',
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_strategies_name ON strategies (name)",
    "CREATE INDEX IF NOT EXISTS idx_strategies_type ON strategies (type)",
    # 2. backtests
    """
    CREATE TABLE IF NOT EXISTS backtests (
        id                TEXT PRIMARY KEY,
        strategy_id       TEXT NOT NULL,
        start_date        TEXT NOT NULL,
        end_date          TEXT NOT NULL,
        metrics_json      TEXT NOT NULL DEFAULT '{}',
        equity_curve_json TEXT NOT NULL DEFAULT '[]',
        trades_count      INTEGER NOT NULL DEFAULT 0,
        created_at        TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (strategy_id) REFERENCES strategies (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_backtests_strategy_id ON backtests (strategy_id)",
    "CREATE INDEX IF NOT EXISTS idx_backtests_created_at  ON backtests (created_at)",
    # 3. paper_accounts
    """
    CREATE TABLE IF NOT EXISTS paper_accounts (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        initial_balance REAL NOT NULL DEFAULT 10000.0,
        current_balance REAL NOT NULL DEFAULT 10000.0,
        status          TEXT NOT NULL DEFAULT 'active',
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_paper_accounts_status ON paper_accounts (status)",
    # 4. paper_orders
    """
    CREATE TABLE IF NOT EXISTS paper_orders (
        id              TEXT PRIMARY KEY,
        account_id      TEXT NOT NULL,
        symbol          TEXT NOT NULL,
        side            TEXT NOT NULL,
        type            TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'created',
        quantity        REAL NOT NULL,
        price           REAL,
        filled_quantity REAL NOT NULL DEFAULT 0.0,
        avg_fill_price  REAL,
        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (account_id) REFERENCES paper_accounts (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_paper_orders_account_id ON paper_orders (account_id)",
    "CREATE INDEX IF NOT EXISTS idx_paper_orders_status     ON paper_orders (status)",
    "CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol     ON paper_orders (symbol)",
    # 5. paper_positions
    """
    CREATE TABLE IF NOT EXISTS paper_positions (
        id              TEXT PRIMARY KEY,
        account_id      TEXT NOT NULL,
        symbol          TEXT NOT NULL,
        side            TEXT NOT NULL,
        quantity        REAL NOT NULL DEFAULT 0.0,
        avg_entry_price REAL NOT NULL DEFAULT 0.0,
        unrealized_pnl  REAL NOT NULL DEFAULT 0.0,
        realized_pnl    REAL NOT NULL DEFAULT 0.0,
        updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (account_id) REFERENCES paper_accounts (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_paper_positions_account_id ON paper_positions (account_id)",
    "CREATE INDEX IF NOT EXISTS idx_paper_positions_symbol     ON paper_positions (symbol)",
    # 6. audit_logs
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id           TEXT PRIMARY KEY,
        timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
        event_type   TEXT NOT NULL,
        severity     TEXT NOT NULL DEFAULT 'info',
        actor        TEXT NOT NULL DEFAULT '',
        action       TEXT NOT NULL DEFAULT '',
        resource     TEXT NOT NULL DEFAULT '',
        outcome      TEXT NOT NULL DEFAULT '',
        details_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp  ON audit_logs (timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs (event_type)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_severity   ON audit_logs (severity)",
    # 7. paper_equity_history
    """
    CREATE TABLE IF NOT EXISTS paper_equity_history (
        id          TEXT PRIMARY KEY,
        account_id  TEXT NOT NULL,
        timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
        equity      REAL NOT NULL,
        FOREIGN KEY (account_id) REFERENCES paper_accounts (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_paper_equity_history_account_id ON paper_equity_history (account_id)",
    "CREATE INDEX IF NOT EXISTS idx_paper_equity_history_timestamp  ON paper_equity_history (timestamp)",
]


async def _apply(conn: aiosqlite.Connection) -> None:
    """Apply the initial schema DDL."""
    for stmt in _STATEMENTS:
        await conn.execute(stmt)


migration = Migration(
    id="v001_initial",
    version=1,
    description=(
        "Create initial schema (strategies, backtests, paper_accounts, paper_orders, paper_positions, audit_logs)"
    ),
    apply=_apply,
)
