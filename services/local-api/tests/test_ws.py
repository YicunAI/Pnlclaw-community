"""Tests for WebSocket gateway (S3-L09)."""

from __future__ import annotations

import app.api.v1.ws as _ws_mod
import pytest
from app.main import create_app
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_managers():
    """Reset connection managers between tests."""
    _ws_mod._market_manager = _ws_mod.ConnectionManager()
    _ws_mod._paper_manager = _ws_mod.ConnectionManager()
    yield


def _app():
    return create_app()


def test_ws_markets_subscribe():
    """Client can connect and subscribe to market symbols."""
    app = _app()
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/markets") as ws:
        ws.send_json({"action": "subscribe", "symbols": ["BTC/USDT"]})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"
        assert resp["symbols"] == ["BTC/USDT"]


def test_ws_markets_unsubscribe():
    app = _app()
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/markets") as ws:
        ws.send_json({"action": "subscribe", "symbols": ["BTC/USDT"]})
        ws.receive_json()  # subscribed

        ws.send_json({"action": "unsubscribe", "symbols": ["BTC/USDT"]})
        resp = ws.receive_json()
        assert resp["type"] == "unsubscribed"


def test_ws_markets_invalid_json():
    app = _app()
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/markets") as ws:
        ws.send_text("not json")
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "Invalid JSON" in resp["message"]


def test_ws_markets_unknown_action():
    app = _app()
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/markets") as ws:
        ws.send_json({"action": "foobar"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "Unknown action" in resp["message"]


def test_ws_paper_subscribe():
    app = _app()
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/paper") as ws:
        ws.send_json({"action": "subscribe", "account_id": "pa-12345"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"
        assert resp["account_id"] == "pa-12345"


def test_ws_paper_unsubscribe():
    app = _app()
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/paper") as ws:
        ws.send_json({"action": "subscribe", "account_id": "pa-12345"})
        ws.receive_json()

        ws.send_json({"action": "unsubscribe", "account_id": "pa-12345"})
        resp = ws.receive_json()
        assert resp["type"] == "unsubscribed"


@pytest.mark.asyncio
async def test_connection_manager_broadcast():
    """Test ConnectionManager broadcast to subscribed channels."""
    mgr = _ws_mod.ConnectionManager()
    # Broadcast with no connections should not raise
    await mgr.broadcast("test:channel", {"msg": "hello"})
    assert mgr.active_count == 0
