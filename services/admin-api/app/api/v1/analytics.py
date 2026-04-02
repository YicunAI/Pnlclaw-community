"""Analytics endpoints -- admin only."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_login_history_repo,
    get_postgres_manager,
    get_user_repo,
    require_admin,
)
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


from sqlalchemy import text


def _rewrite_positional(sql: str, args: tuple[Any, ...]) -> tuple[str, dict[str, Any]]:
    """Convert asyncpg-style $1/$2 to SQLAlchemy :p1/:p2 and build params dict."""
    if not args:
        return sql, {}
    params: dict[str, Any] = {}
    rewritten = sql
    for i, val in enumerate(args, 1):
        params[f"p{i}"] = val
        rewritten = rewritten.replace(f"${i}", f":p{i}")
    return rewritten, params


async def _query(pg: Any, sql: str, *args: Any) -> list[dict[str, Any]]:
    """Execute a raw SQL query via SQLAlchemy session and return list of dicts."""
    if pg is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Database not available",
        )
    rewritten, params = _rewrite_positional(sql, args)
    async with pg.session() as session:
        result = await session.execute(text(rewritten), params)
        rows = result.mappings().all()
        return [_serialize_row(r) for r in rows]


async def _query_one(pg: Any, sql: str, *args: Any) -> dict[str, Any]:
    """Execute a raw SQL query and return a single dict."""
    if pg is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Database not available",
        )
    rewritten, params = _rewrite_positional(sql, args)
    async with pg.session() as session:
        result = await session.execute(text(rewritten), params)
        row = result.mappings().first()
        return _serialize_row(row) if row else {}


def _serialize_row(row: Any) -> dict[str, Any]:
    """Ensure all values in a row dict are JSON-serializable."""
    import uuid as _uuid
    from datetime import date, datetime
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, date):
            d[k] = v.isoformat()
        elif isinstance(v, _uuid.UUID):
            d[k] = str(v)
    return d


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/overview")
async def analytics_overview(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, Any]]:
    """Key metrics overview.

    Returns total users, active users (last 24h/7d/30d),
    new signups today, and total sessions.
    """
    total_users = await _query_one(pg, "SELECT COUNT(*) as count FROM users WHERE deleted_at IS NULL")
    active_24h = await _query_one(
        pg,
        "SELECT COUNT(DISTINCT user_id) as count FROM sessions WHERE created_at > NOW() - INTERVAL '24 hours'",
    )
    active_7d = await _query_one(
        pg,
        "SELECT COUNT(DISTINCT user_id) as count FROM sessions WHERE created_at > NOW() - INTERVAL '7 days'",
    )
    active_30d = await _query_one(
        pg,
        "SELECT COUNT(DISTINCT user_id) as count FROM sessions WHERE created_at > NOW() - INTERVAL '30 days'",
    )
    new_today = await _query_one(
        pg,
        "SELECT COUNT(*) as count FROM users WHERE created_at > NOW() - INTERVAL '24 hours' AND deleted_at IS NULL",
    )
    total_sessions = await _query_one(pg, "SELECT COUNT(*) as count FROM sessions")
    banned_count = await _query_one(
        pg,
        "SELECT COUNT(*) as count FROM users WHERE status = 'banned' AND deleted_at IS NULL",
    )

    return APIResponse(
        data={
            "total_users": total_users.get("count", 0),
            "active_24h": active_24h.get("count", 0),
            "active_7d": active_7d.get("count", 0),
            "active_30d": active_30d.get("count", 0),
            "new_signups_today": new_today.get("count", 0),
            "total_sessions": total_sessions.get("count", 0),
            "banned_users": banned_count.get("count", 0),
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/users/active")
async def active_users(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
    period: str = Query("7d", pattern="^(24h|7d|30d|90d)$"),
) -> APIResponse[dict[str, Any]]:
    """Active users by period, broken down by day."""
    interval_map = {
        "24h": "24 hours",
        "7d": "7 days",
        "30d": "30 days",
        "90d": "90 days",
    }
    interval = interval_map[period]

    rows = await _query(
        pg,
        f"""
        SELECT DATE(created_at) as date, COUNT(DISTINCT user_id) as active_count
        FROM sessions
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY DATE(created_at)
        ORDER BY date
        """,
    )

    return APIResponse(
        data={"period": period, "data": rows},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/users/signups")
async def signup_rate(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
    period: str = Query("30d", pattern="^(7d|30d|90d|365d)$"),
) -> APIResponse[dict[str, Any]]:
    """Signup rate broken down by day."""
    interval_map = {
        "7d": "7 days",
        "30d": "30 days",
        "90d": "90 days",
        "365d": "365 days",
    }
    interval = interval_map[period]

    rows = await _query(
        pg,
        f"""
        SELECT DATE(created_at) as date, COUNT(*) as signup_count
        FROM users
        WHERE created_at > NOW() - INTERVAL '{interval}'
          AND deleted_at IS NULL
        GROUP BY DATE(created_at)
        ORDER BY date
        """,
    )

    return APIResponse(
        data={"period": period, "data": rows},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/users/providers")
async def provider_breakdown(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, Any]]:
    """OAuth provider breakdown showing how many users use each provider."""
    rows = await _query(
        pg,
        """
        SELECT provider, COUNT(DISTINCT user_id) as user_count
        FROM oauth_accounts
        GROUP BY provider
        ORDER BY user_count DESC
        """,
    )

    return APIResponse(
        data={"providers": rows},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/users/geo")
async def geographic_distribution(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, Any]]:
    """Geographic distribution of users based on login history."""
    rows = await _query(
        pg,
        """
        SELECT
            country,
            COUNT(DISTINCT user_id) as user_count
        FROM login_history
        WHERE country IS NOT NULL
        GROUP BY country
        ORDER BY user_count DESC
        LIMIT 50
        """,
    )

    return APIResponse(
        data={"countries": rows},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/users/retention")
async def retention_rate(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, Any]]:
    """Retention rate: percentage of users who logged in again after signup.

    Returns weekly cohort retention for the last 12 weeks.
    """
    rows = await _query(
        pg,
        """
        WITH cohorts AS (
            SELECT
                id as user_id,
                DATE_TRUNC('week', created_at) as cohort_week
            FROM users
            WHERE created_at > NOW() - INTERVAL '12 weeks'
              AND deleted_at IS NULL
        ),
        activity AS (
            SELECT
                user_id,
                DATE_TRUNC('week', created_at) as activity_week
            FROM sessions
            WHERE created_at > NOW() - INTERVAL '12 weeks'
        )
        SELECT
            c.cohort_week,
            COUNT(DISTINCT c.user_id) as cohort_size,
            COUNT(DISTINCT CASE
                WHEN a.activity_week > c.cohort_week THEN c.user_id
            END) as retained_count
        FROM cohorts c
        LEFT JOIN activity a ON c.user_id = a.user_id
        GROUP BY c.cohort_week
        ORDER BY c.cohort_week
        """,
    )

    # Calculate retention percentage
    for row in rows:
        cohort_size = row.get("cohort_size", 0)
        retained = row.get("retained_count", 0)
        row["retention_pct"] = round(
            (retained / cohort_size * 100) if cohort_size > 0 else 0,
            1,
        )

    return APIResponse(
        data={"cohorts": rows},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/traffic")
async def api_traffic(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
    period: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
) -> APIResponse[dict[str, Any]]:
    """API traffic metrics broken down by hour or day."""
    interval_map = {
        "1h": ("1 hour", "minute"),
        "24h": ("24 hours", "hour"),
        "7d": ("7 days", "day"),
        "30d": ("30 days", "day"),
    }
    interval, bucket = interval_map[period]

    rows = await _query(
        pg,
        f"""
        SELECT
            DATE_TRUNC('{bucket}', created_at) as time_bucket,
            COUNT(*) as request_count,
            COUNT(DISTINCT user_id) as unique_users
        FROM activity_logs
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY 1
        ORDER BY 1
        """,
    )

    return APIResponse(
        data={"period": period, "bucket": bucket, "data": rows},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/devices")
async def device_distribution(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, Any]]:
    """Device distribution from login history."""
    browsers = await _query(
        pg,
        """
        SELECT
            browser,
            COUNT(*) as count
        FROM login_history
        WHERE browser IS NOT NULL
          AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY browser
        ORDER BY count DESC
        LIMIT 20
        """,
    )

    os_data = await _query(
        pg,
        """
        SELECT
            os,
            COUNT(*) as count
        FROM login_history
        WHERE os IS NOT NULL
          AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY os
        ORDER BY count DESC
        LIMIT 20
        """,
    )

    device_types = await _query(
        pg,
        """
        SELECT
            device_type,
            COUNT(*) as count
        FROM login_history
        WHERE device_type IS NOT NULL
          AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY device_type
        ORDER BY count DESC
        LIMIT 20
        """,
    )

    return APIResponse(
        data={
            "browsers": browsers,
            "operating_systems": os_data,
            "device_types": device_types,
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/logins")
async def login_stats(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
    period: str = Query("7d", pattern="^(24h|7d|30d|90d)$"),
) -> APIResponse[dict[str, Any]]:
    """Login statistics including success/failure rates."""
    interval_map = {
        "24h": "24 hours",
        "7d": "7 days",
        "30d": "30 days",
        "90d": "90 days",
    }
    interval = interval_map[period]

    daily = await _query(
        pg,
        f"""
        SELECT
            DATE(created_at) as date,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE success = true) as successful,
            COUNT(*) FILTER (WHERE success = false) as failed
        FROM login_history
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY DATE(created_at)
        ORDER BY date
        """,
    )

    by_provider = await _query(
        pg,
        f"""
        SELECT
            provider,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE success = true) as successful,
            COUNT(*) FILTER (WHERE success = false) as failed
        FROM login_history
        WHERE created_at > NOW() - INTERVAL '{interval}'
        GROUP BY provider
        ORDER BY total DESC
        """,
    )

    return APIResponse(
        data={
            "period": period,
            "daily": daily,
            "by_provider": by_provider,
        },
        meta=build_response_meta(request),
        error=None,
    )
