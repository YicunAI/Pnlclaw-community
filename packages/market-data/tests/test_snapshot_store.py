"""Tests for pnlclaw_market.snapshot_store — L2 snapshot storage."""

from __future__ import annotations

from pnlclaw_market.snapshot_store import SnapshotStore
from pnlclaw_types.market import OrderBookL2Snapshot, PriceLevel


def _make_snapshot(symbol: str = "BTC/USDT", seq: int = 100) -> OrderBookL2Snapshot:
    return OrderBookL2Snapshot(
        exchange="binance",
        symbol=symbol,
        timestamp=1711000000000,
        sequence_id=seq,
        bids=[PriceLevel(price=66999.0, quantity=2.0)],
        asks=[PriceLevel(price=67001.0, quantity=1.0)],
    )


class TestSnapshotStore:
    """Unit tests for the SnapshotStore."""

    def test_update_and_get(self) -> None:
        store = SnapshotStore()
        snap = _make_snapshot()
        store.update("BTC/USDT", snap)
        assert store.get_snapshot("BTC/USDT") == snap

    def test_get_missing_returns_none(self) -> None:
        store = SnapshotStore()
        assert store.get_snapshot("NONE") is None

    def test_update_replaces(self) -> None:
        store = SnapshotStore()
        store.update("BTC/USDT", _make_snapshot(seq=100))
        store.update("BTC/USDT", _make_snapshot(seq=200))
        snap = store.get_snapshot("BTC/USDT")
        assert snap is not None
        assert snap.sequence_id == 200

    def test_remove(self) -> None:
        store = SnapshotStore()
        store.update("BTC/USDT", _make_snapshot())
        assert store.remove("BTC/USDT") is True
        assert store.get_snapshot("BTC/USDT") is None
        assert store.remove("BTC/USDT") is False

    def test_symbols(self) -> None:
        store = SnapshotStore()
        store.update("BTC/USDT", _make_snapshot("BTC/USDT"))
        store.update("ETH/USDT", _make_snapshot("ETH/USDT"))
        assert sorted(store.symbols()) == ["BTC/USDT", "ETH/USDT"]

    def test_clear(self) -> None:
        store = SnapshotStore()
        store.update("BTC/USDT", _make_snapshot())
        store.clear()
        assert store.size == 0

    def test_size(self) -> None:
        store = SnapshotStore()
        assert store.size == 0
        store.update("BTC/USDT", _make_snapshot())
        assert store.size == 1
