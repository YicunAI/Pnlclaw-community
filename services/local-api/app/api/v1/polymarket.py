"""Polymarket prediction market endpoints.

Provides enriched market data from Polymarket Gamma + CLOB APIs:
- Event listing with volume sorting and category detection
- Market details with Chinese translations
- Orderbook depth
- Price queries
- Crypto Up/Down rolling prediction markets (5m/15m/1h/daily)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import build_response_meta
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/polymarket", tags=["polymarket"])

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_poly_client = None


async def _get_client():
    global _poly_client
    if _poly_client is None:
        from pnlclaw_exchange.exchanges.polymarket.client import PolymarketClient

        _poly_client = PolymarketClient()
    return _poly_client


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

_CATEGORY_RULES: list[tuple[str, list[re.Pattern[str]]]] = [
    (
        "crypto",
        [
            re.compile(r"\bbitcoin\b", re.I),
            re.compile(r"\bbtc\b", re.I),
            re.compile(r"\bethereum\b", re.I),
            re.compile(r"\beth\b", re.I),
            re.compile(r"\bsolana\b", re.I),
            re.compile(r"\bcrypto\b", re.I),
            re.compile(r"\bdefi\b", re.I),
            re.compile(r"\bnft\b", re.I),
            re.compile(r"\bweb3\b", re.I),
            re.compile(r"\bblockchain\b", re.I),
            re.compile(r"\baltcoin\b", re.I),
            re.compile(r"\bmemecoin\b", re.I),
            re.compile(r"\bdoge\b", re.I),
            re.compile(r"\bxrp\b", re.I),
            re.compile(r"\bcardano\b", re.I),
            re.compile(r"\bmicrostrategy\b", re.I),
            re.compile(r"\bbackpack\s+fdv\b", re.I),
            re.compile(r"\bairdrop\b", re.I),
            re.compile(r"\bpump\.fun\b", re.I),
            re.compile(r"\bhyperliquid\b", re.I),
        ],
    ),
    (
        "finance",
        [
            re.compile(r"\bcrude oil\b", re.I),
            re.compile(r"\bgold\b", re.I),
            re.compile(r"\bsilver\b", re.I),
            re.compile(r"\bs&p\b", re.I),
            re.compile(r"\bspx\b", re.I),
            re.compile(r"\bnasdaq\b", re.I),
            re.compile(r"\bdow\b", re.I),
            re.compile(r"\bfed decision\b", re.I),
            re.compile(r"\bfed\s", re.I),
            re.compile(r"\brate cut\b", re.I),
            re.compile(r"\brate hike\b", re.I),
            re.compile(r"\binterest rate\b", re.I),
            re.compile(r"\bcpi\b", re.I),
            re.compile(r"\binflation\b", re.I),
            re.compile(r"\bgdp\b", re.I),
            re.compile(r"\btreasury\b", re.I),
            re.compile(r"\bipo\b", re.I),
        ],
    ),
    (
        "geopolitics",
        [
            re.compile(r"\biran\b", re.I),
            re.compile(r"\bisrael\b", re.I),
            re.compile(r"\bukraine\b", re.I),
            re.compile(r"\brussia\b", re.I),
            re.compile(r"\btaiwan\b", re.I),
            re.compile(r"\bnorth korea\b", re.I),
            re.compile(r"\bsyria\b", re.I),
            re.compile(r"\bgaza\b", re.I),
            re.compile(r"\bhamas\b", re.I),
            re.compile(r"\bhezbollah\b", re.I),
            re.compile(r"\bmilitary\b", re.I),
            re.compile(r"\binvasion\b", re.I),
            re.compile(r"\bceasefire\b", re.I),
            re.compile(r"\boffensive\b", re.I),
            re.compile(r"\bnato\b", re.I),
            re.compile(r"\bsanctions\b", re.I),
        ],
    ),
    (
        "politics",
        [
            re.compile(r"\belection\b", re.I),
            re.compile(r"\bpresident\b", re.I),
            re.compile(r"\bdemocrat\b", re.I),
            re.compile(r"\brepublican\b", re.I),
            re.compile(r"\bvote\b", re.I),
            re.compile(r"\bcongress\b", re.I),
            re.compile(r"\btrump\b", re.I),
            re.compile(r"\bbiden\b", re.I),
            re.compile(r"\bparliament\b", re.I),
            re.compile(r"\bsenate\b", re.I),
            re.compile(r"\bnominee\b", re.I),
            re.compile(r"\bgovernor\b", re.I),
            re.compile(r"\bprime minister\b", re.I),
            re.compile(r"\btariff\b", re.I),
            re.compile(r"\bspeaker\b", re.I),
        ],
    ),
    (
        "sports",
        [
            re.compile(r"\bnba\b", re.I),
            re.compile(r"\bnfl\b", re.I),
            re.compile(r"\bmlb\b", re.I),
            re.compile(r"\bnhl\b", re.I),
            re.compile(r"\bfifa\b", re.I),
            re.compile(r"\bf1\b", re.I),
            re.compile(r"\bufc\b", re.I),
            re.compile(r"\batp\b", re.I),
            re.compile(r"\bncaa\b", re.I),
            re.compile(r"\bpremier league\b", re.I),
            re.compile(r"\bla liga\b", re.I),
            re.compile(r"\bchampions league\b", re.I),
            re.compile(r"\bworld cup\b", re.I),
            re.compile(r"\bsuper bowl\b", re.I),
            re.compile(r"\bstanley cup\b", re.I),
            re.compile(r"\bplayoff\b", re.I),
            re.compile(r"\bvs\.?\b", re.I),
        ],
    ),
    (
        "entertainment",
        [
            re.compile(r"\beurovision\b", re.I),
            re.compile(r"\boscar\b", re.I),
            re.compile(r"\bgrammy\b", re.I),
            re.compile(r"\bemmy\b", re.I),
            re.compile(r"\bmovie\b", re.I),
            re.compile(r"\bgta\b", re.I),
            re.compile(r"\btaylor swift\b", re.I),
        ],
    ),
    (
        "tech",
        [
            re.compile(r"\belon musk\b", re.I),
            re.compile(r"\bopenai\b", re.I),
            re.compile(r"\btesla\b", re.I),
            re.compile(r"\bspacex\b", re.I),
            re.compile(r"\btweet\b", re.I),
        ],
    ),
    (
        "science",
        [
            re.compile(r"\bclimate\b", re.I),
            re.compile(r"\bearthquake\b", re.I),
            re.compile(r"\bhurricane\b", re.I),
            re.compile(r"\bnasa\b", re.I),
        ],
    ),
]


def _detect_category(title: str, description: str = "") -> str:
    """Categorize an event based primarily on its title using regex word boundaries."""
    scores: dict[str, int] = {}
    for cat, patterns in _CATEGORY_RULES:
        score = sum(3 for p in patterns if p.search(title))
        if description:
            score += sum(1 for p in patterns if p.search(description))
        if score > 0:
            scores[cat] = score
    if not scores:
        return "other"
    return max(scores, key=scores.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Chinese translation helpers
# ---------------------------------------------------------------------------

_ZH_TERM_MAP: list[tuple[re.Pattern[str], str]] = [
    # Multi-word phrases first (longer matches take priority)
    (re.compile(r"\bPresidential Election Winner\b", re.I), "总统大选获胜者"),
    (re.compile(r"\bPresidential Election\b", re.I), "总统大选"),
    (re.compile(r"\bPresidential Nominee\b", re.I), "总统提名人"),
    (re.compile(r"\bParliamentary Election\b", re.I), "议会选举"),
    (re.compile(r"\bFed decision\b", re.I), "美联储决议"),
    (re.compile(r"\brate cut\b", re.I), "降息"),
    (re.compile(r"\brate hike\b", re.I), "加息"),
    (re.compile(r"\bground offensive\b", re.I), "地面进攻"),
    (re.compile(r"\bFIFA World Cup\b", re.I), "FIFA世界杯"),
    (re.compile(r"\bWorld Cup\b", re.I), "世界杯"),
    (re.compile(r"\bSuper Bowl\b", re.I), "超级碗"),
    (re.compile(r"\bMarch Madness\b", re.I), "疯狂三月"),
    (re.compile(r"\bCrude Oil\b", re.I), "原油"),
    (re.compile(r"\bUS forces\b", re.I), "美军"),
    (re.compile(r"\bby end of\b", re.I), "截止"),
    # Crypto
    (re.compile(r"\bBitcoin\b", re.I), "比特币"),
    (re.compile(r"\bEthereum\b", re.I), "以太坊"),
    (re.compile(r"\bSolana\b", re.I), "Solana"),
    (re.compile(r"\bMicroStrategy\b", re.I), "MicroStrategy"),
    # Sports
    (re.compile(r"\bNBA Champion\b", re.I), "NBA 冠军"),
    (re.compile(r"\bF1 Drivers' Champion\b", re.I), "F1 车手冠军"),
    (re.compile(r"\bEurovision Winner\b", re.I), "欧洲歌唱大赛冠军"),
    (re.compile(r"\bPlayoff\b", re.I), "季后赛"),
    # Politics / geopolitics
    (re.compile(r"\bDemocratic\b", re.I), "民主党"),
    (re.compile(r"\bRepublican\b", re.I), "共和党"),
    (re.compile(r"\bceasefire\b", re.I), "停火"),
    (re.compile(r"\bWinner\b", re.I), "获胜者"),
    (re.compile(r"\bNominee\b", re.I), "提名人"),
    (re.compile(r"\bChampion\b", re.I), "冠军"),
    (re.compile(r"\bElection\b", re.I), "选举"),
    # Months
    (re.compile(r"\bJanuary\b", re.I), "一月"),
    (re.compile(r"\bFebruary\b", re.I), "二月"),
    (re.compile(r"\bMarch\b(?!\s+Madness)", re.I), "三月"),
    (re.compile(r"\bApril\b", re.I), "四月"),
    (re.compile(r"\bJune\b", re.I), "六月"),
    (re.compile(r"\bJuly\b", re.I), "七月"),
    (re.compile(r"\bAugust\b", re.I), "八月"),
    (re.compile(r"\bSeptember\b", re.I), "九月"),
    (re.compile(r"\bOctober\b", re.I), "十月"),
    (re.compile(r"\bNovember\b", re.I), "十一月"),
    (re.compile(r"\bDecember\b", re.I), "十二月"),
]

_ZH_CATEGORY_MAP = {
    "crypto": "加密货币",
    "politics": "政治",
    "sports": "体育",
    "finance": "金融",
    "entertainment": "娱乐",
    "geopolitics": "地缘政治",
    "tech": "科技",
    "science": "科学",
    "other": "其他",
}


def _translate_title(title: str) -> str:
    result = title
    for pattern, replacement in _ZH_TERM_MAP:
        result = pattern.sub(replacement, result)
    return result


# ---------------------------------------------------------------------------
# Outcome extraction from Gamma market objects
# ---------------------------------------------------------------------------


def _extract_outcomes_from_market(m: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract outcomes from a Gamma market object.

    Gamma markets store token IDs in ``clobTokenIds`` (JSON-encoded list),
    outcome labels in ``outcomes`` (JSON-encoded list), and prices in
    ``outcomePrices`` (JSON-encoded list).  The older ``tokens`` field may
    be empty for short-lived prediction markets.
    """
    import json as _json

    outcomes_list: list[dict[str, Any]] = []

    clob_ids_raw = m.get("clobTokenIds", "")
    outcomes_raw = m.get("outcomes", "")
    prices_raw = m.get("outcomePrices", "")

    clob_ids = _json.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) and clob_ids_raw else clob_ids_raw
    outcome_names = _json.loads(outcomes_raw) if isinstance(outcomes_raw, str) and outcomes_raw else outcomes_raw
    prices = _json.loads(prices_raw) if isinstance(prices_raw, str) and prices_raw else prices_raw

    if isinstance(clob_ids, list) and isinstance(outcome_names, list):
        prices_list = prices if isinstance(prices, list) else []
        for i, tid in enumerate(clob_ids):
            name = outcome_names[i] if i < len(outcome_names) else f"Outcome {i}"
            price = float(prices_list[i]) if i < len(prices_list) else 0.0
            outcomes_list.append({
                "token_id": str(tid),
                "outcome": str(name),
                "price": price,
            })
        if outcomes_list:
            return outcomes_list

    tokens = m.get("tokens", [])
    if isinstance(tokens, str):
        try:
            tokens = _json.loads(tokens) if tokens else []
        except Exception:
            tokens = []
    for t in (tokens if isinstance(tokens, list) else []):
        if isinstance(t, dict):
            outcomes_list.append({
                "token_id": t.get("token_id", ""),
                "outcome": t.get("outcome", ""),
                "price": float(t.get("price", 0) or 0),
            })

    return outcomes_list


# ---------------------------------------------------------------------------
# Enrich event data
# ---------------------------------------------------------------------------


def _enrich_event(raw: dict[str, Any]) -> dict[str, Any]:
    """Add category, Chinese translation, and structured market data."""
    title = raw.get("title", "")
    desc = raw.get("description", "")
    category = raw.get("category", "").lower() or _detect_category(title, desc)

    markets_raw = raw.get("markets", [])
    markets_enriched = []
    for m in markets_raw:
        outcomes = _extract_outcomes_from_market(m)
        for o in outcomes:
            o.setdefault("winner", False)

        markets_enriched.append({
            "id": m.get("id", ""),
            "question": m.get("question", ""),
            "question_zh": _translate_title(m.get("question", "")),
            "condition_id": m.get("conditionId", m.get("condition_id", "")),
            "slug": m.get("slug", ""),
            "active": m.get("active", True),
            "closed": m.get("closed", False),
            "volume": float(m.get("volume", 0) or 0),
            "liquidity": float(m.get("liquidity", 0) or 0),
            "outcomes": outcomes,
        })

    return {
        "id": raw.get("id", ""),
        "title": title,
        "title_zh": _translate_title(title),
        "slug": raw.get("slug", ""),
        "description": desc,
        "category": category,
        "category_zh": _ZH_CATEGORY_MAP.get(category, category),
        "image": raw.get("image", ""),
        "icon": raw.get("icon", ""),
        "active": raw.get("active", True),
        "closed": raw.get("closed", False),
        "volume": float(raw.get("volume", 0) or 0),
        "volume_24h": float(raw.get("volume24hr", 0) or 0),
        "liquidity": float(raw.get("liquidity", 0) or 0),
        "start_date": raw.get("startDate", ""),
        "end_date": raw.get("endDate", ""),
        "markets": markets_enriched,
        "market_count": len(markets_enriched),
    }


# ---------------------------------------------------------------------------
# Events (primary endpoint — Gamma API with enrichment)
# ---------------------------------------------------------------------------


@router.get("/events")
async def list_events(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="Number of events"),
    active: bool = Query(True, description="Only active events"),
    closed: bool = Query(False, description="Include closed events"),
    category: str = Query("", description="Filter by category"),
    sort: str = Query("volume24hr", description="Sort field: volume24hr, volume, liquidity"),
    client=Depends(_get_client),
) -> APIResponse[dict[str, Any]]:
    """List enriched Polymarket events with categories and Chinese translations.

    Sorted by 24h volume (descending) by default to show the hottest events first.
    """
    try:
        fetch_limit = limit * 3 if category else limit
        events_raw = await client.list_events(
            limit=min(fetch_limit, 100),
            active=active,
            closed=closed,
            order=sort,
            ascending=False,
        )
        enriched = [_enrich_event(e) for e in events_raw]

        if category:
            cat_lower = category.lower()
            enriched = [e for e in enriched if e["category"] == cat_lower]
            enriched = enriched[:limit]

        return APIResponse(
            data={
                "events": enriched,
                "count": len(enriched),
                "categories": list(_ZH_CATEGORY_MAP.keys()),
                "categories_zh": _ZH_CATEGORY_MAP,
            },
            meta=build_response_meta(request),
            error=None,
        )
    except Exception as exc:
        logger.error("Failed to fetch Polymarket events: %s", exc)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Polymarket API error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Event detail
# ---------------------------------------------------------------------------


@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    request: Request,
    client=Depends(_get_client),
) -> APIResponse[dict[str, Any]]:
    """Get full details for a single Polymarket event, including all sub-markets."""
    try:
        raw = await client.get_event(event_id)
        enriched = _enrich_event(raw)

        enriched["description_zh"] = _translate_title(raw.get("description", ""))
        enriched["comment_count"] = raw.get("commentCount", 0)
        enriched["created_at"] = raw.get("createdAt", "")
        enriched["updated_at"] = raw.get("updatedAt", "")
        enriched["competitive"] = raw.get("competitive", 0)
        enriched["enableOrderBook"] = raw.get("enableOrderBook", True)
        enriched["neg_risk"] = raw.get("negRisk", False)

        for m in enriched["markets"]:
            raw_m_list = raw.get("markets", [])
            raw_m = next(
                (
                    rm
                    for rm in raw_m_list
                    if rm.get("id", "") == m["id"]
                    or rm.get("conditionId", "") == m["condition_id"]
                ),
                {},
            )
            m["description"] = raw_m.get("description", "")
            m["description_zh"] = _translate_title(raw_m.get("description", ""))
            m["end_date"] = raw_m.get("endDate", "")
            m["start_date"] = raw_m.get("startDate", "")
            m["neg_risk"] = raw_m.get("negRisk", False)
            m["best_bid"] = float(raw_m.get("bestBid", 0) or 0)
            m["best_ask"] = float(raw_m.get("bestAsk", 0) or 0)
            m["spread"] = float(raw_m.get("spread", 0) or 0)
            m["last_trade_price"] = float(raw_m.get("lastTradePrice", 0) or 0)
            m["volume_24h"] = float(raw_m.get("volume24hr", 0) or 0)

        return APIResponse(data=enriched, meta=build_response_meta(request), error=None)
    except Exception as exc:
        logger.error("Failed to fetch event %s: %s", event_id, exc)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Polymarket API error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Crypto price predictions (BTC/ETH Up/Down rolling markets)
# ---------------------------------------------------------------------------

_UP_OR_DOWN_RE = re.compile(r"Up or Down", re.I)

_ASSET_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("BTC", "比特币", re.compile(r"\bBitcoin\b", re.I)),
    ("ETH", "以太坊", re.compile(r"\bEthereum\b", re.I)),
    ("SOL", "Solana", re.compile(r"\bSolana\b", re.I)),
    ("DOGE", "狗狗币", re.compile(r"\bDogecoin\b", re.I)),
    ("XRP", "XRP", re.compile(r"\bXRP\b", re.I)),
    ("BNB", "BNB", re.compile(r"\bBNB\b", re.I)),
    ("HYPE", "Hyperliquid", re.compile(r"\b(?:Hyperliquid|HYPE)\b", re.I)),
]

_TIMEFRAME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("5m", re.compile(r"updown[_-]5m[_-]", re.I)),
    ("15m", re.compile(r"updown[_-]15m[_-]", re.I)),
    ("1h", re.compile(r"\d{1,2}(?:AM|PM)\s+ET$", re.I)),
    ("daily", re.compile(r"Up or Down (?:on|–) ", re.I)),
]


def _detect_asset(title: str) -> tuple[str, str]:
    for code, zh, pat in _ASSET_PATTERNS:
        if pat.search(title):
            return code, zh
    return "OTHER", "其他"


def _detect_timeframe(slug: str, title: str) -> str:
    for tf, pat in _TIMEFRAME_PATTERNS:
        if pat.search(slug) or pat.search(title):
            return tf
    return "other"


_TIMEFRAME_LABELS = {
    "5m": {"en": "5 Minutes", "zh": "5分钟"},
    "15m": {"en": "15 Minutes", "zh": "15分钟"},
    "1h": {"en": "Hourly", "zh": "1小时"},
    "daily": {"en": "Daily", "zh": "日级别"},
    "other": {"en": "Other", "zh": "其他"},
}

_TIMEFRAME_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "daily": 24 * 60 * 60,
}

_SLUG_TS_RE = re.compile(r"-(\d{10})$")


def _parse_iso_date(s: str) -> datetime | None:
    """Best-effort ISO date parsing."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_window_from_slug(slug: str, tf: str) -> tuple[datetime | None, datetime | None]:
    """Extract the real prediction window start/end from the slug timestamp.

    Gamma API ``startDate`` is the *market creation* time, NOT the prediction
    window start.  The actual window start is the Unix epoch embedded at the
    end of the slug (e.g. ``btc-updown-5m-1774510200``).
    """
    m = _SLUG_TS_RE.search(slug)
    if not m:
        return None, None
    window_start = datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc)
    duration = _TIMEFRAME_SECONDS.get(tf, 0)
    if duration:
        from datetime import timedelta
        window_end = window_start + timedelta(seconds=duration)
    else:
        window_end = None
    return window_start, window_end


def _event_to_prediction(ev: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a Gamma event to a prediction entry if it matches Up/Down."""
    title = ev.get("title", "")
    if not _UP_OR_DOWN_RE.search(title):
        return None

    asset, asset_zh = _detect_asset(title)
    slug = ev.get("slug", "")
    tf = _detect_timeframe(slug, title)

    # Parse time boundaries for filtering
    start_date_str = ev.get("startDate", "")
    end_date_str = ev.get("endDate", "")
    # Markets have startDate/endDate; for events, aggregate from first market
    markets_raw = ev.get("markets", [])
    if not end_date_str and markets_raw:
        end_date_str = markets_raw[0].get("endDate", "")
    if not start_date_str and markets_raw:
        start_date_str = markets_raw[0].get("startDate", "")

    outcomes: list[dict[str, Any]] = []
    for m in markets_raw:
        outcomes.extend(_extract_outcomes_from_market(m))

    # The TRUE prediction window comes from the slug timestamp, not
    # Gamma's startDate (which is the market creation time).
    window_start, window_end = _extract_window_from_slug(slug, tf)

    return {
        "id": str(ev.get("id", "")),
        "title": title,
        "title_zh": _translate_title(title),
        "slug": slug,
        "asset": asset,
        "asset_zh": asset_zh,
        "timeframe": tf,
        "timeframe_label": _TIMEFRAME_LABELS.get(tf, _TIMEFRAME_LABELS["other"]),
        "active": ev.get("active", True),
        "closed": ev.get("closed", False),
        "start_date": start_date_str,
        "end_date": end_date_str,
        "_window_start": window_start,
        "_window_end": window_end or _parse_iso_date(end_date_str),
        "volume": float(ev.get("volume", 0) or 0),
        "volume_24h": float(ev.get("volume24hr", 0) or 0),
        "liquidity": float(ev.get("liquidity", 0) or 0),
        "outcomes": outcomes,
        "polymarket_url": f"https://polymarket.com/event/{slug}",
    }


_ASSET_SLUGS = ["btc", "eth", "sol", "doge", "xrp", "bnb", "hype"]
_ROLLING_TFS = [("5m", 300), ("15m", 900)]


def _build_current_window_slugs(now: datetime) -> list[tuple[str, str, int]]:
    """Generate slugs for the currently active prediction windows.

    Returns ``(slug, tf_label, window_start_ts)`` tuples for each
    asset × timeframe combination.
    """
    now_ts = int(now.timestamp())
    slugs: list[tuple[str, str, int]] = []
    for asset_slug in _ASSET_SLUGS:
        for tf_label, duration in _ROLLING_TFS:
            window_start_ts = now_ts - (now_ts % duration)
            slug = f"{asset_slug}-updown-{tf_label}-{window_start_ts}"
            slugs.append((slug, tf_label, window_start_ts))
    return slugs


@router.get("/crypto-predictions")
async def list_crypto_predictions(
    request: Request,
    limit: int = Query(30, ge=1, le=100, description="Max predictions to return"),
    asset: str = Query("", description="Filter by asset: BTC, ETH, SOL, etc."),
    timeframe: str = Query("", description="Filter by timeframe: 5m, 15m, 1h, daily"),
    client=Depends(_get_client),
) -> APIResponse[dict[str, Any]]:
    """Fetch crypto Up/Down rolling prediction markets.

    Only returns events whose **prediction window** is currently in progress.
    The real window start/end is derived from the slug's Unix timestamp
    (Gamma ``startDate`` is the market *creation* time, not the window start).

    Results are sorted by ``window_end`` ascending so the soonest-to-resolve
    (= currently active window) appears first.
    """
    try:
        import asyncio as _aio

        now = datetime.now(tz=timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        # --- Strategy 1: deterministic slug fetch for 5m/15m (fast & precise) ---
        current_slugs = _build_current_window_slugs(now)

        async def _fetch_one(slug: str) -> dict[str, Any] | None:
            return await client.get_event_by_slug(slug)

        # --- Strategy 2: end_date_min filter for 1h/daily (official Gamma param) ---
        async def _fetch_hourly() -> list[dict[str, Any]]:
            return await client.list_events(
                limit=50, active=True, closed=False,
                order="endDate", ascending=True,
                end_date_min=now_iso,
            )

        slug_results, hourly_events = await _aio.gather(
            _aio.gather(*[_fetch_one(s) for s, _, _ in current_slugs], return_exceptions=True),
            _fetch_hourly(),
            return_exceptions=False,
        )

        predictions: list[dict[str, Any]] = []

        # Process slug-based results (5m/15m)
        for (slug, tf_label, ws_ts), result in zip(current_slugs, slug_results):
            if isinstance(result, Exception) or result is None:
                continue
            pred = _event_to_prediction(result)
            if pred is None:
                continue
            pred.pop("_window_start", None)
            pred.pop("_window_end", None)

            if asset and pred["asset"].upper() != asset.upper():
                continue
            if timeframe and pred["timeframe"] != timeframe.lower():
                continue

            window_end = datetime.fromtimestamp(
                ws_ts + _TIMEFRAME_SECONDS.get(tf_label, 300), tz=timezone.utc
            )
            pred["_end_sort"] = window_end
            predictions.append(pred)

        # Process end_date_min results (1h/daily/other)
        seen_slugs = {s for s, _, _ in current_slugs}
        for ev in hourly_events:
            title = ev.get("title", "")
            if not _UP_OR_DOWN_RE.search(title):
                continue
            ev_slug = ev.get("slug", "")
            if ev_slug in seen_slugs:
                continue  # already covered by slug fetch

            pred = _event_to_prediction(ev)
            if pred is None:
                continue
            if pred["timeframe"] in ("5m", "15m"):
                # Already handled above; use slug timestamp for these
                window_start = pred.pop("_window_start", None)
                window_end = pred.pop("_window_end", None)
                if window_start and window_start > now:
                    continue
            else:
                window_start = pred.pop("_window_start", None)
                window_end = pred.pop("_window_end", None)
                if window_start and window_start > now:
                    continue

            if asset and pred["asset"].upper() != asset.upper():
                continue
            if timeframe and pred["timeframe"] != timeframe.lower():
                continue

            pred["_end_sort"] = window_end or _parse_iso_date(ev.get("endDate", "")) or now
            predictions.append(pred)

        predictions.sort(key=lambda p: p.pop("_end_sort"))

        # Deduplicate: keep at most 1 per (asset, timeframe) combination
        seen: set[tuple[str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for p in predictions:
            key = (p["asset"], p["timeframe"])
            if key not in seen:
                seen.add(key)
                deduped.append(p)
        predictions = deduped[:limit]

        by_asset: dict[str, list[dict[str, Any]]] = {}
        for p in predictions:
            by_asset.setdefault(p["asset"], []).append(p)

        by_timeframe: dict[str, list[dict[str, Any]]] = {}
        for p in predictions:
            by_timeframe.setdefault(p["timeframe"], []).append(p)

        available_assets = sorted({p["asset"] for p in predictions})

        return APIResponse(
            data={
                "predictions": predictions,
                "by_asset": by_asset,
                "by_timeframe": by_timeframe,
                "count": len(predictions),
                "available_assets": available_assets,
                "timeframe_labels": _TIMEFRAME_LABELS,
            },
            meta=build_response_meta(request),
            error=None,
        )
    except Exception as exc:
        logger.error("Failed to fetch crypto predictions: %s", exc, exc_info=True)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Polymarket API error: {type(exc).__name__}: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Markets (CLOB)
# ---------------------------------------------------------------------------


@router.get("/markets")
async def list_markets(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="Number of markets"),
    next_cursor: str = Query("", description="Pagination cursor"),
    client=Depends(_get_client),
) -> APIResponse[dict[str, Any]]:
    """List active Polymarket prediction markets from CLOB."""
    try:
        markets = await client.list_markets(limit=limit, next_cursor=next_cursor)
        result = []
        for m in markets:
            d = m.model_dump()
            d["category"] = _detect_category(m.question, m.description)
            d["category_zh"] = _ZH_CATEGORY_MAP.get(d["category"], d["category"])
            d["question_zh"] = _translate_title(m.question)
            result.append(d)
        return APIResponse(
            data={"markets": result, "count": len(result)},
            meta=build_response_meta(request),
            error=None,
        )
    except Exception as exc:
        logger.error("Failed to fetch Polymarket markets: %s", exc)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Polymarket API error: {exc}",
        ) from exc


@router.get("/markets/{condition_id}")
async def get_market(
    condition_id: str,
    request: Request,
    client=Depends(_get_client),
) -> APIResponse[dict[str, Any]]:
    """Get details for a specific market by condition ID."""
    try:
        from pnlclaw_exchange.exchanges.polymarket.redemption import (
            PolymarketRedemptionClient,
        )

        redemption = PolymarketRedemptionClient(wallet_address="")
        try:
            market = await redemption.get_market(condition_id)
            d = market.model_dump()
            d["category"] = _detect_category(market.question, market.description)
            d["category_zh"] = _ZH_CATEGORY_MAP.get(d["category"], d["category"])
            d["question_zh"] = _translate_title(market.question)
            return APIResponse(data=d, meta=build_response_meta(request), error=None)
        finally:
            await redemption.close()
    except Exception as exc:
        logger.error("Failed to fetch market %s: %s", condition_id, exc)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Polymarket API error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Orderbook
# ---------------------------------------------------------------------------


@router.get("/orderbook/{token_id}")
async def get_orderbook(
    token_id: str,
    request: Request,
    client=Depends(_get_client),
) -> APIResponse[dict[str, Any]]:
    """Get orderbook for a Polymarket outcome token."""
    try:
        book = await client.get_orderbook(token_id)
        return APIResponse(
            data=book.model_dump(),
            meta=build_response_meta(request),
            error=None,
        )
    except Exception as exc:
        logger.error("Failed to fetch orderbook for %s: %s", token_id, exc)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Polymarket API error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------


@router.get("/price/{token_id}")
async def get_price(
    token_id: str,
    request: Request,
    side: str = Query("BUY", description="BUY or SELL"),
    client=Depends(_get_client),
) -> APIResponse[dict[str, Any]]:
    """Get market price for a Polymarket outcome token."""
    try:
        price = await client.get_price(token_id, side=side.upper())
        midpoint = await client.get_midpoint(token_id)
        return APIResponse(
            data={
                "token_id": token_id,
                "price": price,
                "midpoint": midpoint,
                "side": side.upper(),
            },
            meta=build_response_meta(request),
            error=None,
        )
    except Exception as exc:
        logger.error("Failed to fetch price for %s: %s", token_id, exc)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"Polymarket API error: {exc}",
        ) from exc
