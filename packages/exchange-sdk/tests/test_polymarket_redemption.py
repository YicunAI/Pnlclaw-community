"""Tests for Polymarket position tracking and auto-redemption."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from pnlclaw_exchange.exchanges.polymarket.models import (
    AutoRedeemSummary,
    PolymarketMarket,
    PolymarketPosition,
    PolymarketPositionStatus,
    RedemptionResult,
)
from pnlclaw_exchange.exchanges.polymarket.redemption import (
    CTF_ADDRESS,
    DEFAULT_CLOB_URL,
    DEFAULT_DATA_URL,
    DEFAULT_GAMMA_URL,
    PARENT_COLLECTION_ID,
    USDC_E_ADDRESS,
    PolymarketRedemptionClient,
)

SAMPLE_WALLET = "0x1234567890abcdef1234567890abcdef12345678"
SAMPLE_CONDITION_ID = "0xabc123def456789abc123def456789abc123def456789abc123def456789abc1"
SAMPLE_TOKEN_YES = "111222333444"
SAMPLE_TOKEN_NO = "555666777888"


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_position_status_enum(self) -> None:
        assert PolymarketPositionStatus.OPEN == "open"
        assert PolymarketPositionStatus.REDEEMABLE == "redeemable"
        assert PolymarketPositionStatus.REDEEMED == "redeemed"
        assert PolymarketPositionStatus.CLOSED == "closed"

    def test_position_defaults(self) -> None:
        pos = PolymarketPosition(condition_id="0xabc")
        assert pos.size == 0.0
        assert pos.redeemable is False
        assert pos.is_winner is False
        assert pos.status == PolymarketPositionStatus.OPEN

    def test_position_with_values(self) -> None:
        pos = PolymarketPosition(
            condition_id="0xabc",
            asset_id="token_yes",
            title="Will X happen?",
            outcome="Yes",
            size=100.0,
            avg_price=0.55,
            current_price=1.0,
            current_value=100.0,
            cost_basis=55.0,
            cash_pnl=45.0,
            percent_pnl=81.8,
            redeemable=True,
            is_winner=True,
            status=PolymarketPositionStatus.REDEEMABLE,
        )
        assert pos.cash_pnl == 45.0
        assert pos.is_winner is True

    def test_redemption_result_defaults(self) -> None:
        r = RedemptionResult(condition_id="0xabc")
        assert r.success is False
        assert r.shares_redeemed == 0.0
        assert r.usdc_received == 0.0
        assert r.transaction_hash == ""

    def test_redemption_result_success(self) -> None:
        r = RedemptionResult(
            condition_id="0xabc",
            outcome="Yes",
            shares_redeemed=100.0,
            usdc_received=100.0,
            transaction_hash="0xhash123",
            success=True,
        )
        assert r.success is True
        assert r.usdc_received == 100.0

    def test_auto_redeem_summary_defaults(self) -> None:
        s = AutoRedeemSummary()
        assert s.markets_checked == 0
        assert s.redeemable_found == 0
        assert s.total_usdc_redeemed == 0.0
        assert s.results == []

    def test_market_resolved_fields(self) -> None:
        m = PolymarketMarket(
            condition_id="0xabc",
            question="Will X happen?",
            resolved=True,
            winning_outcome="Yes",
        )
        assert m.resolved is True
        assert m.winning_outcome == "Yes"


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_ctf_address(self) -> None:
        assert CTF_ADDRESS.startswith("0x")
        assert len(CTF_ADDRESS) == 42

    def test_usdc_address(self) -> None:
        assert USDC_E_ADDRESS.startswith("0x")
        assert len(USDC_E_ADDRESS) == 42

    def test_parent_collection_id(self) -> None:
        assert PARENT_COLLECTION_ID.startswith("0x")
        assert len(PARENT_COLLECTION_ID) == 66  # 0x + 64 hex chars


# ---------------------------------------------------------------------------
# Client construction tests
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_basic_init(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        assert client._wallet == SAMPLE_WALLET
        assert client._gamma_url == DEFAULT_GAMMA_URL
        assert client._clob_url == DEFAULT_CLOB_URL
        assert client._data_url == DEFAULT_DATA_URL

    def test_custom_urls(self) -> None:
        client = PolymarketRedemptionClient(
            wallet_address=SAMPLE_WALLET,
            gamma_url="https://custom-gamma.example.com/",
            clob_url="https://custom-clob.example.com/",
            data_url="https://custom-data.example.com/",
        )
        assert client._gamma_url == "https://custom-gamma.example.com"
        assert client._clob_url == "https://custom-clob.example.com"
        assert client._data_url == "https://custom-data.example.com"

    def test_private_key_optional(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        assert client._private_key is None

        client_with_key = PolymarketRedemptionClient(
            wallet_address=SAMPLE_WALLET,
            private_key="0xprivatekey",
        )
        assert client_with_key._private_key == "0xprivatekey"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_response(data: Any, status: int = 200) -> httpx.Response:
    """Build a fake httpx.Response."""
    content = json.dumps(data).encode()
    return httpx.Response(
        status_code=status,
        content=content,
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://test.example.com"),
    )


def _market_data(
    *,
    resolved: bool = False,
    winner_outcome: str = "",
) -> dict[str, Any]:
    """Build a sample market API response."""
    tokens = [
        {
            "token_id": SAMPLE_TOKEN_YES,
            "outcome": "Yes",
            "price": 1.0 if winner_outcome == "Yes" else 0.0,
            "winner": winner_outcome == "Yes",
        },
        {
            "token_id": SAMPLE_TOKEN_NO,
            "outcome": "No",
            "price": 1.0 if winner_outcome == "No" else 0.0,
            "winner": winner_outcome == "No",
        },
    ]
    return {
        "condition_id": SAMPLE_CONDITION_ID,
        "question_id": "qid_123",
        "question": "Will X happen?",
        "description": "Test market",
        "market_slug": "will-x-happen",
        "end_date_iso": "2026-12-31T23:59:59Z",
        "active": not resolved,
        "closed": resolved,
        "resolved": resolved,
        "tokens": tokens,
        "volume": "50000",
        "volume_num_24hr": "1200",
        "liquidity": "25000",
    }


def _positions_data(*, redeemable: bool = False, is_winner: bool = False) -> list[dict[str, Any]]:
    """Build a sample positions API response."""
    return [
        {
            "conditionId": SAMPLE_CONDITION_ID,
            "assetId": SAMPLE_TOKEN_YES,
            "title": "Will X happen?",
            "outcome": "Yes",
            "size": "50",
            "avgPrice": "0.6",
            "curPrice": "1.0" if redeemable else "0.75",
            "currentValue": "50" if redeemable else "37.5",
            "initialValue": "30",
            "cashPnl": "20" if redeemable else "7.5",
            "percentPnl": "66.7" if redeemable else "25.0",
            "redeemable": redeemable,
            "isWinner": is_winner,
        },
    ]


# ---------------------------------------------------------------------------
# Position query tests
# ---------------------------------------------------------------------------


class TestGetPositions:
    @pytest.mark.asyncio
    async def test_get_positions_basic(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_positions_data()))
        client._rate_limiter = AsyncMock()

        positions = await client.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.condition_id == SAMPLE_CONDITION_ID
        assert pos.asset_id == SAMPLE_TOKEN_YES
        assert pos.outcome == "Yes"
        assert pos.size == 50.0
        assert pos.avg_price == 0.6
        assert pos.status == PolymarketPositionStatus.OPEN

    @pytest.mark.asyncio
    async def test_get_positions_redeemable(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_positions_data(redeemable=True, is_winner=True)))
        client._rate_limiter = AsyncMock()

        positions = await client.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.redeemable is True
        assert pos.is_winner is True
        assert pos.status == PolymarketPositionStatus.REDEEMABLE

    @pytest.mark.asyncio
    async def test_get_redeemable_positions(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_positions_data(redeemable=True, is_winner=True)))
        client._rate_limiter = AsyncMock()

        positions = await client.get_redeemable_positions()
        assert len(positions) == 1
        assert positions[0].redeemable is True

    @pytest.mark.asyncio
    async def test_get_positions_empty(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response([]))
        client._rate_limiter = AsyncMock()

        positions = await client.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_portfolio_value(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response({"value": 1234.56}))
        client._rate_limiter = AsyncMock()

        value = await client.get_portfolio_value()
        assert value == 1234.56


# ---------------------------------------------------------------------------
# Market resolution tests
# ---------------------------------------------------------------------------


class TestMarketResolution:
    @pytest.mark.asyncio
    async def test_get_market_unresolved(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=False)))
        client._rate_limiter = AsyncMock()

        market = await client.get_market(SAMPLE_CONDITION_ID)
        assert market.resolved is False
        assert market.winning_outcome == ""
        assert market.active is True

    @pytest.mark.asyncio
    async def test_get_market_resolved_yes_wins(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=True, winner_outcome="Yes")))
        client._rate_limiter = AsyncMock()

        market = await client.get_market(SAMPLE_CONDITION_ID)
        assert market.resolved is True
        assert market.winning_outcome == "Yes"

    @pytest.mark.asyncio
    async def test_get_market_resolved_no_wins(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=True, winner_outcome="No")))
        client._rate_limiter = AsyncMock()

        market = await client.get_market(SAMPLE_CONDITION_ID)
        assert market.resolved is True
        assert market.winning_outcome == "No"

    @pytest.mark.asyncio
    async def test_is_market_resolved(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=True, winner_outcome="Yes")))
        client._rate_limiter = AsyncMock()

        assert await client.is_market_resolved(SAMPLE_CONDITION_ID) is True

    @pytest.mark.asyncio
    async def test_is_market_not_resolved(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=False)))
        client._rate_limiter = AsyncMock()

        assert await client.is_market_resolved(SAMPLE_CONDITION_ID) is False

    @pytest.mark.asyncio
    async def test_get_winning_outcome_resolved(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=True, winner_outcome="Yes")))
        client._rate_limiter = AsyncMock()

        assert await client.get_winning_outcome(SAMPLE_CONDITION_ID) == "Yes"

    @pytest.mark.asyncio
    async def test_get_winning_outcome_not_resolved(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=False)))
        client._rate_limiter = AsyncMock()

        assert await client.get_winning_outcome(SAMPLE_CONDITION_ID) is None


# ---------------------------------------------------------------------------
# Redemption tests
# ---------------------------------------------------------------------------


class TestRedemption:
    @pytest.mark.asyncio
    async def test_redeem_success(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))
        redeem_resp = _mock_response(
            {
                "transactionHash": "0xredeem_hash_123",
                "message": "Tokens redeemed successfully.",
            }
        )

        async def mock_get(*args: Any, **kwargs: Any) -> httpx.Response:
            return market_resp

        async def mock_post(*args: Any, **kwargs: Any) -> httpx.Response:
            return redeem_resp

        client._http = AsyncMock()
        client._http.get = AsyncMock(side_effect=mock_get)
        client._http.post = AsyncMock(side_effect=mock_post)

        result = await client.redeem_position(condition_id=SAMPLE_CONDITION_ID)

        assert result.success is True
        assert result.transaction_hash == "0xredeem_hash_123"
        assert result.condition_id == SAMPLE_CONDITION_ID
        assert result.outcome == "Yes"

    @pytest.mark.asyncio
    async def test_redeem_market_not_resolved(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(_market_data(resolved=False)))

        result = await client.redeem_position(condition_id=SAMPLE_CONDITION_ID)
        assert result.success is False
        assert "not yet resolved" in result.error

    @pytest.mark.asyncio
    async def test_redeem_api_error(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))
        error_resp = _mock_response({"error": "Invalid condition ID"}, status=400)

        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=market_resp)
        client._http.post = AsyncMock(return_value=error_resp)

        result = await client.redeem_position(condition_id=SAMPLE_CONDITION_ID)
        assert result.success is False
        assert "Invalid condition ID" in result.error

    @pytest.mark.asyncio
    async def test_redeem_network_error(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))

        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=market_resp)
        client._http.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await client.redeem_position(condition_id=SAMPLE_CONDITION_ID)
        assert result.success is False
        assert "connection refused" in result.error

    @pytest.mark.asyncio
    async def test_redeem_custom_index_sets(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))
        redeem_resp = _mock_response({"transactionHash": "0xhash456"})

        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=market_resp)
        client._http.post = AsyncMock(return_value=redeem_resp)

        result = await client.redeem_position(condition_id=SAMPLE_CONDITION_ID, index_sets=[1])
        assert result.success is True

        post_call = client._http.post.call_args
        body = post_call.kwargs.get("json", {})
        assert body["indexSets"] == [1]

    @pytest.mark.asyncio
    async def test_redeem_headers_include_wallet(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        headers = client._build_redeem_headers()
        assert headers["POLY-ADDRESS"] == SAMPLE_WALLET
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_redeem_posts_correct_body(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))
        redeem_resp = _mock_response({"transactionHash": "0xhash"})

        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=market_resp)
        client._http.post = AsyncMock(return_value=redeem_resp)

        await client.redeem_position(condition_id=SAMPLE_CONDITION_ID)

        post_call = client._http.post.call_args
        body = post_call.kwargs.get("json", {})
        assert body["collateralToken"] == USDC_E_ADDRESS
        assert body["parentCollectionId"] == PARENT_COLLECTION_ID
        assert body["conditionId"] == SAMPLE_CONDITION_ID
        assert body["indexSets"] == [1, 2]


# ---------------------------------------------------------------------------
# Auto-redemption tests
# ---------------------------------------------------------------------------


class TestAutoRedeem:
    @pytest.mark.asyncio
    async def test_auto_redeem_no_positions(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response([]))

        summary = await client.auto_redeem_all()
        assert summary.markets_checked == 0
        assert summary.redeemable_found == 0
        assert summary.redemptions_attempted == 0

    @pytest.mark.asyncio
    async def test_auto_redeem_with_redeemable(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        positions_resp = _mock_response(_positions_data(redeemable=True, is_winner=True))
        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))
        redeem_resp = _mock_response({"transactionHash": "0xauto_hash"})

        async def mock_get(url: str, **kwargs: Any) -> httpx.Response:
            if "positions" in url:
                return positions_resp
            return market_resp

        client._http = AsyncMock()
        client._http.get = AsyncMock(side_effect=mock_get)
        client._http.post = AsyncMock(return_value=redeem_resp)

        summary = await client.auto_redeem_all()
        assert summary.markets_checked == 1
        assert summary.redeemable_found == 1
        assert summary.redemptions_attempted == 1
        assert summary.redemptions_succeeded == 1
        assert summary.total_usdc_redeemed == 50.0
        assert len(summary.results) == 1
        assert summary.results[0].success is True

    @pytest.mark.asyncio
    async def test_auto_redeem_dry_run(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        positions_resp = _mock_response(_positions_data(redeemable=True, is_winner=True))

        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=positions_resp)

        summary = await client.auto_redeem_all(dry_run=True)
        assert summary.redeemable_found == 1
        assert summary.redemptions_attempted == 0
        assert len(summary.results) == 1
        assert summary.results[0].error == "dry_run"
        assert summary.results[0].usdc_received == 50.0

        client._http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_redeem_min_shares_filter(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        small_position = [
            {
                "conditionId": SAMPLE_CONDITION_ID,
                "assetId": SAMPLE_TOKEN_YES,
                "title": "Small position",
                "outcome": "Yes",
                "size": "0.05",
                "avgPrice": "0.5",
                "curPrice": "1.0",
                "currentValue": "0.05",
                "initialValue": "0.025",
                "cashPnl": "0.025",
                "percentPnl": "100",
                "redeemable": True,
                "isWinner": True,
            },
        ]
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=_mock_response(small_position))

        summary = await client.auto_redeem_all(min_shares=1.0)
        assert summary.redeemable_found == 0
        assert summary.redemptions_attempted == 0

    @pytest.mark.asyncio
    async def test_auto_redeem_untagged_positions(self) -> None:
        """When API doesn't tag position as redeemable, we check market directly."""
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        positions_resp = _mock_response(_positions_data(redeemable=False, is_winner=False))
        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))
        redeem_resp = _mock_response({"transactionHash": "0xuntagged"})

        async def mock_get(url: str, **kwargs: Any) -> httpx.Response:
            if "positions" in url:
                return positions_resp
            return market_resp

        client._http = AsyncMock()
        client._http.get = AsyncMock(side_effect=mock_get)
        client._http.post = AsyncMock(return_value=redeem_resp)

        summary = await client.auto_redeem_all()
        assert summary.redeemable_found == 1
        assert summary.redemptions_attempted == 1
        assert summary.redemptions_succeeded == 1

    @pytest.mark.asyncio
    async def test_auto_redeem_losing_position_skipped(self) -> None:
        """Untagged position on losing side should not be redeemed."""
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        losing_position = [
            {
                "conditionId": SAMPLE_CONDITION_ID,
                "assetId": SAMPLE_TOKEN_NO,
                "title": "Losing position",
                "outcome": "No",
                "size": "50",
                "avgPrice": "0.4",
                "curPrice": "0",
                "currentValue": "0",
                "initialValue": "20",
                "cashPnl": "-20",
                "percentPnl": "-100",
                "redeemable": False,
                "isWinner": False,
            },
        ]
        market_resp = _mock_response(_market_data(resolved=True, winner_outcome="Yes"))

        async def mock_get(url: str, **kwargs: Any) -> httpx.Response:
            if "positions" in url:
                return _mock_response(losing_position)
            return market_resp

        client._http = AsyncMock()
        client._http.get = AsyncMock(side_effect=mock_get)

        summary = await client.auto_redeem_all()
        assert summary.redeemable_found == 0
        assert summary.redemptions_attempted == 0

    @pytest.mark.asyncio
    async def test_auto_redeem_partial_failure(self) -> None:
        """When redemption fails for one, the sweep continues."""
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._rate_limiter = AsyncMock()

        positions = [
            {
                "conditionId": "0xcond_a",
                "assetId": "tok_a",
                "title": "Market A",
                "outcome": "Yes",
                "size": "100",
                "avgPrice": "0.5",
                "curPrice": "1.0",
                "currentValue": "100",
                "initialValue": "50",
                "cashPnl": "50",
                "percentPnl": "100",
                "redeemable": True,
                "isWinner": True,
            },
            {
                "conditionId": "0xcond_b",
                "assetId": "tok_b",
                "title": "Market B",
                "outcome": "Yes",
                "size": "200",
                "avgPrice": "0.3",
                "curPrice": "1.0",
                "currentValue": "200",
                "initialValue": "60",
                "cashPnl": "140",
                "percentPnl": "233",
                "redeemable": True,
                "isWinner": True,
            },
        ]

        market_a = _market_data(resolved=True, winner_outcome="Yes")
        market_a["condition_id"] = "0xcond_a"
        market_b = _market_data(resolved=True, winner_outcome="Yes")
        market_b["condition_id"] = "0xcond_b"

        error_resp = _mock_response({"error": "Network timeout"}, status=500)
        success_resp = _mock_response({"transactionHash": "0xb_hash"})

        async def mock_get(url: str, **kwargs: Any) -> httpx.Response:
            if "positions" in url:
                return _mock_response(positions)
            if "0xcond_a" in url:
                return _mock_response(market_a)
            return _mock_response(market_b)

        post_call_count = 0

        async def mock_post(*args: Any, **kwargs: Any) -> httpx.Response:
            nonlocal post_call_count
            post_call_count += 1
            if post_call_count == 1:
                return error_resp
            return success_resp

        client._http = AsyncMock()
        client._http.get = AsyncMock(side_effect=mock_get)
        client._http.post = AsyncMock(side_effect=mock_post)

        summary = await client.auto_redeem_all()
        assert summary.redeemable_found == 2
        assert summary.redemptions_attempted == 2
        assert summary.redemptions_succeeded == 1
        assert len(summary.results) == 2
        assert summary.results[0].success is False
        assert summary.results[1].success is True
        assert summary.total_usdc_redeemed == 200.0


# ---------------------------------------------------------------------------
# Close / cleanup tests
# ---------------------------------------------------------------------------


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = PolymarketRedemptionClient(wallet_address=SAMPLE_WALLET)
        client._http = AsyncMock()
        await client.close()
        client._http.aclose.assert_called_once()
