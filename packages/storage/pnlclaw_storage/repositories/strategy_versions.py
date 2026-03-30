"""Repositories for strategy version snapshots and deployments."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pnlclaw_storage.sqlite import AsyncSQLiteManager
from pnlclaw_types.strategy import StrategyDeployment, StrategyVersionSnapshot


def _ts_ms_to_iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()


def _iso_to_ts_ms(value: str) -> int:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return int(dt.timestamp() * 1000)


class StrategyVersionRepository:
    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    async def save(self, snapshot: StrategyVersionSnapshot) -> str:
        await self._db.execute(
            """
            INSERT INTO strategy_versions (id, strategy_id, version, config_json, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                config_json = excluded.config_json,
                note = excluded.note
            """,
            (
                snapshot.id,
                snapshot.strategy_id,
                snapshot.version,
                json.dumps(snapshot.config_snapshot),
                snapshot.note,
                _ts_ms_to_iso(snapshot.created_at),
            ),
        )
        return snapshot.id

    async def list_by_strategy(self, strategy_id: str) -> list[StrategyVersionSnapshot]:
        rows = await self._db.query(
            """
            SELECT id, strategy_id, version, config_json, note, created_at
            FROM strategy_versions
            WHERE strategy_id = ?
            ORDER BY version DESC
            """,
            (strategy_id,),
        )
        return [
            StrategyVersionSnapshot(
                id=row["id"],
                strategy_id=row["strategy_id"],
                version=row["version"],
                config_snapshot=json.loads(row["config_json"]),
                note=row["note"],
                created_at=_iso_to_ts_ms(row["created_at"]),
            )
            for row in rows
        ]


class StrategyDeploymentRepository:
    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    async def save(self, deployment: StrategyDeployment) -> str:
        await self._db.execute(
            """
            INSERT INTO strategy_deployments (id, strategy_id, strategy_version, account_id, mode, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status
            """,
            (
                deployment.id,
                deployment.strategy_id,
                deployment.strategy_version,
                deployment.account_id,
                deployment.mode,
                deployment.status,
                _ts_ms_to_iso(deployment.created_at),
            ),
        )
        return deployment.id

    async def list_by_strategy(self, strategy_id: str) -> list[StrategyDeployment]:
        rows = await self._db.query(
            """
            SELECT id, strategy_id, strategy_version, account_id, mode, status, created_at
            FROM strategy_deployments
            WHERE strategy_id = ?
            ORDER BY created_at DESC
            """,
            (strategy_id,),
        )
        return [
            StrategyDeployment(
                id=row["id"],
                strategy_id=row["strategy_id"],
                strategy_version=row["strategy_version"],
                account_id=row["account_id"],
                mode=row["mode"],
                status=row["status"],
                created_at=_iso_to_ts_ms(row["created_at"]),
            )
            for row in rows
        ]
