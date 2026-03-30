"""Paper trading account, order, and position CRUD repository.

Persists paper trading state to ``paper_accounts``, ``paper_orders``,
and ``paper_positions`` tables.  All data is returned as plain dicts
to keep the repository layer free of business logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pnlclaw_storage.sqlite import AsyncSQLiteManager


class PaperAccountRepository:
    """CRUD operations for paper trading accounts, orders, and positions.

    Args:
        db: An initialized ``AsyncSQLiteManager`` instance.
    """

    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    async def save_account(self, account: dict[str, Any]) -> str:
        """Insert or update a paper account.

        Expected keys: id, name, initial_balance, current_balance, status.

        Returns:
            The account ID.
        """
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            INSERT INTO paper_accounts
                (id, name, initial_balance, current_balance, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                current_balance = excluded.current_balance,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                account["id"],
                account["name"],
                account.get("initial_balance", 10000.0),
                account.get("current_balance", account.get("initial_balance", 10000.0)),
                account.get("status", "active"),
                now,
                now,
            ),
        )
        return str(account["id"])

    async def get_account(self, account_id: str) -> dict[str, Any] | None:
        """Retrieve a paper account by ID.

        Returns:
            Account dict or ``None`` if not found.
        """
        rows = await self._db.query(
            """
            SELECT id, name, initial_balance, current_balance, status,
                   created_at, updated_at
            FROM paper_accounts WHERE id = ?
            """,
            (account_id,),
        )
        if not rows:
            return None
        return dict(rows[0])

    async def delete_account(self, account_id: str) -> bool:
        """Permanently delete a paper account.
        
        Cascades to orders and positions in database.
        """
        rows = await self._db.execute(
            "DELETE FROM paper_accounts WHERE id = ?", (account_id,)
        )
        # rows is empty for DELETE but commit was successful
        return True

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def save_order(self, order: dict[str, Any]) -> str:
        """Insert or update a paper order.

        Expected keys: id, account_id, symbol, side, type, status,
        quantity, price, filled_quantity, avg_fill_price.

        Returns:
            The order ID.
        """
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            INSERT INTO paper_orders
                (id, account_id, symbol, side, type, status,
                 quantity, price, filled_quantity, avg_fill_price,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                filled_quantity = excluded.filled_quantity,
                avg_fill_price = excluded.avg_fill_price,
                updated_at = excluded.updated_at
            """,
            (
                order["id"],
                order["account_id"],
                order["symbol"],
                order["side"],
                order["type"],
                order.get("status", "created"),
                order["quantity"],
                order.get("price"),
                order.get("filled_quantity", 0.0),
                order.get("avg_fill_price"),
                now,
                now,
            ),
        )
        return str(order["id"])

    async def get_orders(
        self,
        account_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List orders for an account, optionally filtered by status.

        Args:
            account_id: The account to query.
            status: Optional status filter (e.g. ``"filled"``).

        Returns:
            List of order dicts, newest first.
        """
        if status is not None:
            rows = await self._db.query(
                """
                SELECT id, account_id, symbol, side, type, status,
                       quantity, price, filled_quantity, avg_fill_price,
                       created_at, updated_at
                FROM paper_orders
                WHERE account_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (account_id, status),
            )
        else:
            rows = await self._db.query(
                """
                SELECT id, account_id, symbol, side, type, status,
                       quantity, price, filled_quantity, avg_fill_price,
                       created_at, updated_at
                FROM paper_orders
                WHERE account_id = ?
                ORDER BY created_at DESC
                """,
                (account_id,),
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def save_position(self, position: dict[str, Any]) -> str:
        """Insert or update a paper position.

        Expected keys: id, account_id, symbol, side, quantity,
        avg_entry_price, unrealized_pnl, realized_pnl.

        Returns:
            The position ID.
        """
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            INSERT INTO paper_positions
                (id, account_id, symbol, side, quantity,
                 avg_entry_price, unrealized_pnl, realized_pnl, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                quantity = excluded.quantity,
                avg_entry_price = excluded.avg_entry_price,
                unrealized_pnl = excluded.unrealized_pnl,
                realized_pnl = excluded.realized_pnl,
                updated_at = excluded.updated_at
            """,
            (
                position["id"],
                position["account_id"],
                position["symbol"],
                position["side"],
                position.get("quantity", 0.0),
                position.get("avg_entry_price", 0.0),
                position.get("unrealized_pnl", 0.0),
                position.get("realized_pnl", 0.0),
                now,
            ),
        )
        return str(position["id"])

    async def get_positions(self, account_id: str) -> list[dict[str, Any]]:
        """List all positions for an account.

        Returns:
            List of position dicts.
        """
        rows = await self._db.query(
            """
            SELECT id, account_id, symbol, side, quantity,
                   avg_entry_price, unrealized_pnl, realized_pnl, updated_at
            FROM paper_positions
            WHERE account_id = ?
            ORDER BY symbol
            """,
            (account_id,),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Equity History
    # ------------------------------------------------------------------

    async def save_equity_point(self, account_id: str, equity: float) -> str:
        """Record a current equity point for an account."""
        import uuid
        now = datetime.now(UTC).isoformat()
        point_id = f"eh-{uuid.uuid4().hex[:8]}"
        await self._db.execute(
            """
            INSERT INTO paper_equity_history (id, account_id, timestamp, equity)
            VALUES (?, ?, ?, ?)
            """,
            (point_id, account_id, now, equity),
        )
        return point_id

    async def get_equity_history(
        self, account_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Retrieve the most recent equity points for an account (in ASC order)."""
        rows = await self._db.query(
            """
            SELECT timestamp, equity FROM (
                SELECT timestamp, equity
                FROM paper_equity_history
                WHERE account_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ) sub
            ORDER BY timestamp ASC
            """,
            (account_id, limit),
        )
        return [dict(r) for r in rows]

    async def has_equity_history(self, account_id: str) -> bool:
        """Check if an account has any recorded equity history."""
        rows = await self._db.query(
            "SELECT 1 FROM paper_equity_history WHERE account_id = ? LIMIT 1",
            (account_id,),
        )
        return len(rows) > 0

    async def clear_equity_history(self, account_id: str) -> None:
        """Delete all equity history for an account (used on account reset)."""
        await self._db.execute(
            "DELETE FROM paper_equity_history WHERE account_id = ?",
            (account_id,),
        )
