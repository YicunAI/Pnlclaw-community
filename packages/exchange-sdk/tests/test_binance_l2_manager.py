"""Tests for BinanceL2Manager.

This is the most critical test file in exchange-sdk, covering:
- Normal delta application flow
- Stale delta dropping
- First delta validation
- Sequence gap detection and recovery
- Depth validation (bid < ask invariant)
- Recovery during delta processing
- End-to-end flow with simulated gaps
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pnlclaw_exchange.exchanges.binance.l2_manager import BinanceL2Manager
from pnlclaw_exchange.exchanges.binance.normalizer import BinanceDepthDelta
from pnlclaw_types.market import OrderBookL2Delta, OrderBookL2Snapshot, PriceLevel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_delta(
    first_id: int,
    last_id: int,
    bids: list[tuple[float, float]] | None = None,
    asks: list[tuple[float, float]] | None = None,
    symbol: str = "BTC/USDT",
) -> BinanceDepthDelta:
    """Create a BinanceDepthDelta for testing."""
    bid_levels = [PriceLevel(price=p, quantity=q) for p, q in (bids or [])]
    ask_levels = [PriceLevel(price=p, quantity=q) for p, q in (asks or [])]
    delta = OrderBookL2Delta(
        exchange="binance",
        symbol=symbol,
        timestamp=1711000000000,
        sequence_id=last_id,
        bids=bid_levels,
        asks=ask_levels,
    )
    return BinanceDepthDelta(
        delta=delta, first_update_id=first_id, last_update_id=last_id
    )


def _mock_http_client(snapshot_data: dict[str, Any]) -> AsyncMock:
    """Create a mock httpx.AsyncClient that returns the given snapshot."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = snapshot_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()
    return mock_client


BASIC_SNAPSHOT = {
    "lastUpdateId": 100,
    "bids": [
        ["66999.00", "2.00"],
        ["66998.00", "1.50"],
    ],
    "asks": [
        ["67001.00", "1.00"],
        ["67002.00", "3.00"],
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_fetches_snapshot() -> None:
    """initialize() should fetch a REST snapshot and build the local book."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    mgr = BinanceL2Manager(http_client=http)

    snapshot = await mgr.initialize("BTCUSDT")

    assert isinstance(snapshot, OrderBookL2Snapshot)
    assert snapshot.exchange == "binance"
    assert snapshot.symbol == "BTC/USDT"
    assert snapshot.sequence_id == 100
    assert len(snapshot.bids) == 2
    assert len(snapshot.asks) == 2
    assert snapshot.bids[0].price == 66999.0
    assert snapshot.asks[0].price == 67001.0
    http.get.assert_called_once()


@pytest.mark.asyncio
async def test_apply_sequential_deltas() -> None:
    """Sequential deltas should update the orderbook correctly."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # First delta: U=100, u=101 bridges snapshot (lastUpdateId=100)
    delta1 = _make_delta(
        100, 101,
        bids=[(66999.0, 3.0)],  # Update bid quantity
        asks=[(67001.0, 0.0)],  # Remove ask level
    )
    snap1 = await mgr.apply_delta("BTCUSDT", delta1)
    assert snap1 is not None
    assert snap1.bids[0].quantity == 3.0
    # 67001.0 was removed, best ask now 67002.0
    assert snap1.asks[0].price == 67002.0

    # Second delta: contiguous U=102, u=103
    delta2 = _make_delta(
        102, 103,
        bids=[(67000.0, 1.0)],  # New bid level
    )
    snap2 = await mgr.apply_delta("BTCUSDT", delta2)
    assert snap2 is not None
    # Best bid should now be 67000.0
    assert snap2.bids[0].price == 67000.0


@pytest.mark.asyncio
async def test_stale_delta_dropped() -> None:
    """Deltas with u <= lastUpdateId should be silently dropped."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # Stale delta: u=50 < lastUpdateId=100
    stale = _make_delta(40, 50, bids=[(66999.0, 99.0)])
    result = await mgr.apply_delta("BTCUSDT", stale)
    assert result is None

    # Book should be unchanged.
    snap = mgr.get_snapshot("BTCUSDT")
    assert snap is not None
    assert snap.bids[0].quantity == 2.0  # Original value


@pytest.mark.asyncio
async def test_first_delta_validation_passes() -> None:
    """First delta that bridges the snapshot should be accepted."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # U=100 <= lastUpdateId+1=101, u=101 >= 101 → valid
    delta = _make_delta(100, 101, bids=[(66999.0, 5.0)])
    result = await mgr.apply_delta("BTCUSDT", delta)
    assert result is not None
    assert result.bids[0].quantity == 5.0


@pytest.mark.asyncio
async def test_first_delta_validation_fails_triggers_recovery() -> None:
    """First delta that doesn't bridge the snapshot triggers recovery."""
    http = _mock_http_client(BASIC_SNAPSHOT)

    # After recovery, provide a new snapshot.
    recovery_snapshot = {
        "lastUpdateId": 200,
        "bids": [["67010.00", "1.00"]],
        "asks": [["67020.00", "1.00"]],
    }
    http.get = AsyncMock(
        side_effect=[
            # Initial snapshot
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=BASIC_SNAPSHOT),
                raise_for_status=MagicMock(),
            ),
            # Recovery snapshot
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=recovery_snapshot),
                raise_for_status=MagicMock(),
            ),
        ]
    )

    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # Gap: U=110 > lastUpdateId+1=101 → triggers recovery
    delta = _make_delta(110, 115, bids=[(66999.0, 5.0)])
    result = await mgr.apply_delta("BTCUSDT", delta)
    assert result is None  # Delta dropped during recovery

    # Two REST calls: initial + recovery
    assert http.get.call_count == 2

    # After recovery, snapshot should reflect new data
    snap = mgr.get_snapshot("BTCUSDT")
    assert snap is not None
    assert snap.sequence_id == 200


@pytest.mark.asyncio
async def test_sequence_gap_triggers_recovery() -> None:
    """A gap in subsequent deltas should trigger recovery."""
    http = _mock_http_client(BASIC_SNAPSHOT)

    recovery_snapshot = {
        "lastUpdateId": 300,
        "bids": [["67015.00", "2.00"]],
        "asks": [["67025.00", "2.00"]],
    }
    http.get = AsyncMock(
        side_effect=[
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=BASIC_SNAPSHOT),
                raise_for_status=MagicMock(),
            ),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=recovery_snapshot),
                raise_for_status=MagicMock(),
            ),
        ]
    )

    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # First valid delta
    delta1 = _make_delta(100, 101, bids=[(66999.0, 3.0)])
    await mgr.apply_delta("BTCUSDT", delta1)

    # Gap! Expected U=102, got U=110
    delta_gap = _make_delta(110, 115, bids=[(66999.0, 5.0)])
    result = await mgr.apply_delta("BTCUSDT", delta_gap)
    assert result is None

    assert http.get.call_count == 2
    snap = mgr.get_snapshot("BTCUSDT")
    assert snap is not None
    assert snap.sequence_id == 300


@pytest.mark.asyncio
async def test_depth_validation_bid_ask_cross_triggers_recovery() -> None:
    """If best bid >= best ask after delta, trigger recovery."""
    snapshot_data = {
        "lastUpdateId": 100,
        "bids": [["66999.00", "2.00"]],
        "asks": [["67001.00", "1.00"]],
    }
    recovery_data = {
        "lastUpdateId": 200,
        "bids": [["66990.00", "1.00"]],
        "asks": [["67010.00", "1.00"]],
    }
    http = AsyncMock()
    http.get = AsyncMock(
        side_effect=[
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=snapshot_data),
                raise_for_status=MagicMock(),
            ),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=recovery_data),
                raise_for_status=MagicMock(),
            ),
        ]
    )

    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # Delta that causes bid >= ask (bid=68000 > ask=67001)
    bad_delta = _make_delta(
        100, 101,
        bids=[(68000.0, 1.0)],  # Bid above ask
    )
    result = await mgr.apply_delta("BTCUSDT", bad_delta)
    assert result is None  # Recovery triggered

    assert http.get.call_count == 2


@pytest.mark.asyncio
async def test_deltas_during_recovery_are_dropped() -> None:
    """Deltas arriving during recovery should be silently dropped."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # Manually set recovering flag
    book = mgr._books["BTCUSDT"]
    book.recovering = True

    delta = _make_delta(100, 101, bids=[(66999.0, 5.0)])
    result = await mgr.apply_delta("BTCUSDT", delta)
    assert result is None


@pytest.mark.asyncio
async def test_get_snapshot_returns_none_for_unknown() -> None:
    mgr = BinanceL2Manager()
    assert mgr.get_snapshot("UNKNOWN") is None


@pytest.mark.asyncio
async def test_apply_delta_warns_for_uninitialized() -> None:
    mgr = BinanceL2Manager()
    delta = _make_delta(1, 2, bids=[(100.0, 1.0)])
    result = await mgr.apply_delta("BTCUSDT", delta)
    assert result is None


@pytest.mark.asyncio
async def test_on_snapshot_callback_fires() -> None:
    """on_snapshot callback should fire after each successful delta."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    snapshots: list[OrderBookL2Snapshot] = []

    mgr = BinanceL2Manager(
        http_client=http, on_snapshot=lambda s: snapshots.append(s)
    )
    await mgr.initialize("BTCUSDT")

    delta = _make_delta(100, 101, bids=[(66999.0, 5.0)])
    await mgr.apply_delta("BTCUSDT", delta)

    assert len(snapshots) == 1
    assert snapshots[0].bids[0].quantity == 5.0


@pytest.mark.asyncio
async def test_on_snapshot_async_callback() -> None:
    """on_snapshot should work with async callbacks."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    snapshots: list[OrderBookL2Snapshot] = []

    async def handler(s: OrderBookL2Snapshot) -> None:
        snapshots.append(s)

    mgr = BinanceL2Manager(http_client=http, on_snapshot=handler)
    await mgr.initialize("BTCUSDT")

    delta = _make_delta(100, 101, bids=[(66999.0, 5.0)])
    await mgr.apply_delta("BTCUSDT", delta)

    assert len(snapshots) == 1


@pytest.mark.asyncio
async def test_remove_level_with_zero_quantity() -> None:
    """A delta with quantity=0 should remove the price level."""
    http = _mock_http_client(BASIC_SNAPSHOT)
    mgr = BinanceL2Manager(http_client=http)
    await mgr.initialize("BTCUSDT")

    # Remove the 66999.0 bid level
    delta = _make_delta(100, 101, bids=[(66999.0, 0.0)])
    snap = await mgr.apply_delta("BTCUSDT", delta)
    assert snap is not None
    # Only 66998.0 should remain
    assert len(snap.bids) == 1
    assert snap.bids[0].price == 66998.0


@pytest.mark.asyncio
async def test_end_to_end_with_gap_and_recovery() -> None:
    """Full flow: init → deltas → gap → recovery → resume."""
    initial = {
        "lastUpdateId": 100,
        "bids": [["50000.00", "1.00"], ["49999.00", "2.00"]],
        "asks": [["50001.00", "1.00"], ["50002.00", "2.00"]],
    }
    recovery = {
        "lastUpdateId": 200,
        "bids": [["50010.00", "1.50"], ["50009.00", "2.50"]],
        "asks": [["50011.00", "1.50"], ["50012.00", "2.50"]],
    }
    http = AsyncMock()
    http.get = AsyncMock(
        side_effect=[
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=initial),
                raise_for_status=MagicMock(),
            ),
            MagicMock(
                status_code=200,
                json=MagicMock(return_value=recovery),
                raise_for_status=MagicMock(),
            ),
        ]
    )

    mgr = BinanceL2Manager(http_client=http)
    snapshots: list[OrderBookL2Snapshot] = []
    mgr._on_snapshot = lambda s: snapshots.append(s)

    # 1. Initialize
    await mgr.initialize("BTCUSDT")
    snap0 = mgr.get_snapshot("BTCUSDT")
    assert snap0 is not None
    assert snap0.sequence_id == 100

    # 2. Apply valid deltas
    d1 = _make_delta(100, 101, bids=[(50000.0, 1.5)])
    s1 = await mgr.apply_delta("BTCUSDT", d1)
    assert s1 is not None
    assert s1.bids[0].quantity == 1.5

    d2 = _make_delta(102, 103, asks=[(50001.0, 0.5)])
    s2 = await mgr.apply_delta("BTCUSDT", d2)
    assert s2 is not None

    # 3. Simulate gap (expected U=104, got U=150)
    d_gap = _make_delta(150, 155, bids=[(50000.0, 9.0)])
    s_gap = await mgr.apply_delta("BTCUSDT", d_gap)
    assert s_gap is None  # Recovery triggered

    # 4. After recovery, snapshot reflects new data
    snap_after = mgr.get_snapshot("BTCUSDT")
    assert snap_after is not None
    assert snap_after.sequence_id == 200
    assert snap_after.bids[0].price == 50010.0

    # 5. Resume with new deltas
    d3 = _make_delta(200, 201, bids=[(50010.0, 2.0)])
    s3 = await mgr.apply_delta("BTCUSDT", d3)
    assert s3 is not None
    assert s3.bids[0].quantity == 2.0

    # Verify bid < ask throughout
    assert s3.bids[0].price < s3.asks[0].price


@pytest.mark.asyncio
async def test_bids_sorted_descending_asks_sorted_ascending() -> None:
    """Snapshot bids should be sorted descending, asks ascending."""
    snapshot_data = {
        "lastUpdateId": 100,
        "bids": [["50000.00", "1.00"], ["50005.00", "2.00"], ["49995.00", "3.00"]],
        "asks": [["50010.00", "1.00"], ["50006.00", "2.00"], ["50015.00", "3.00"]],
    }
    http = _mock_http_client(snapshot_data)
    mgr = BinanceL2Manager(http_client=http)
    snap = await mgr.initialize("BTCUSDT")

    # Bids: highest first
    bid_prices = [level.price for level in snap.bids]
    assert bid_prices == sorted(bid_prices, reverse=True)

    # Asks: lowest first
    ask_prices = [level.price for level in snap.asks]
    assert ask_prices == sorted(ask_prices)
