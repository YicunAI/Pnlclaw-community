"""Polymarket position tracking and auto-redemption service.

After a prediction market resolves:
- Winning tokens are worth $1 USDC.e each
- Losing tokens are worth $0
- Users must call ``redeemPositions`` on the CTF contract to convert

This module provides:
- Position querying via Gamma / Data API
- Market resolution status checking
- On-chain redemption via CTF smart contract
- Auto-redemption sweep that finds and redeems all winning positions

Contract details:
    CTF (Conditional Token Framework) on Polygon:
        ``0x4D97DCd97eC945f40cF65F87097ACe5EA0476045``
    USDC.e on Polygon:
        ``0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174``

Docs: https://docs.polymarket.com/trading/ctf/redeem
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter
from pnlclaw_exchange.exchanges.polymarket.models import (
    AutoRedeemSummary,
    PolymarketMarket,
    PolymarketPosition,
    PolymarketPositionStatus,
    PolymarketToken,
    RedemptionResult,
)

logger = logging.getLogger(__name__)

DEFAULT_GAMMA_URL = "https://gamma-api.polymarket.com"
DEFAULT_CLOB_URL = "https://clob.polymarket.com"
DEFAULT_DATA_URL = "https://data-api.polymarket.com"

CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
PARENT_COLLECTION_ID = "0x" + "00" * 32


class PolymarketRedemptionClient:
    """Client for position tracking, settlement checking, and token redemption.

    Combines three API layers:
    1. **Gamma API** — market metadata and resolution status
    2. **Data API** — user position tracking and portfolio value
    3. **CLOB API** — balance queries

    And the on-chain CTF contract for actual redemption.

    Usage::

        client = PolymarketRedemptionClient(
            wallet_address="0xYour...",
            private_key="0xYour...",  # needed for on-chain redemption
        )

        # Check positions
        positions = await client.get_positions()

        # Find redeemable (resolved + winning)
        redeemable = await client.get_redeemable_positions()

        # Auto-redeem everything
        summary = await client.auto_redeem_all()

        await client.close()
    """

    def __init__(
        self,
        *,
        wallet_address: str,
        private_key: str | None = None,
        gamma_url: str = DEFAULT_GAMMA_URL,
        clob_url: str = DEFAULT_CLOB_URL,
        data_url: str = DEFAULT_DATA_URL,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._wallet = wallet_address
        self._private_key = private_key
        self._gamma_url = gamma_url.rstrip("/")
        self._clob_url = clob_url.rstrip("/")
        self._data_url = data_url.rstrip("/")
        self._rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            calls_per_window=60, window_ms=10_000
        )
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Position queries
    # ------------------------------------------------------------------

    async def get_positions(
        self,
        *,
        size_threshold: float = 0.0,
        redeemable_only: bool = False,
    ) -> list[PolymarketPosition]:
        """Get all user positions from the Data API.

        Args:
            size_threshold: Minimum position size (shares) to include.
            redeemable_only: If True, only return redeemable (resolved+winning) positions.

        Returns:
            List of PolymarketPosition objects.
        """
        await self._rate_limiter.acquire()

        params: dict[str, Any] = {
            "user": self._wallet,
            "sizeThreshold": str(size_threshold),
            "sortBy": "CURRENT",
            "sortDirection": "DESC",
        }
        if redeemable_only:
            params["redeemable"] = "true"

        resp = await self._http.get(
            f"{self._data_url}/positions", params=params
        )
        resp.raise_for_status()
        raw_positions: list[dict[str, Any]] = resp.json()

        positions: list[PolymarketPosition] = []
        for raw in raw_positions:
            status = PolymarketPositionStatus.OPEN
            redeemable = bool(raw.get("redeemable", False))
            if redeemable:
                status = PolymarketPositionStatus.REDEEMABLE

            positions.append(PolymarketPosition(
                condition_id=raw.get("conditionId", raw.get("condition_id", "")),
                asset_id=raw.get("assetId", raw.get("asset_id", "")),
                title=raw.get("title", raw.get("question", "")),
                outcome=raw.get("outcome", ""),
                size=float(raw.get("size", 0)),
                avg_price=float(raw.get("avgPrice", raw.get("avg_price", 0))),
                current_price=float(raw.get("curPrice", raw.get("current_price", 0))),
                current_value=float(raw.get("currentValue", raw.get("current_value", 0))),
                cost_basis=float(raw.get("initialValue", raw.get("cost_basis", 0))),
                cash_pnl=float(raw.get("cashPnl", raw.get("cash_pnl", 0))),
                percent_pnl=float(raw.get("percentPnl", raw.get("percent_pnl", 0))),
                redeemable=redeemable,
                is_winner=bool(raw.get("isWinner", raw.get("is_winner", False))),
                status=status,
            ))

        return positions

    async def get_redeemable_positions(self) -> list[PolymarketPosition]:
        """Get only positions that are resolved and can be redeemed.

        Returns winning positions from resolved markets.
        """
        return await self.get_positions(redeemable_only=True)

    async def get_portfolio_value(self) -> float:
        """Get total portfolio value in USDC.

        Returns:
            Total value of all open positions.
        """
        await self._rate_limiter.acquire()

        resp = await self._http.get(
            f"{self._data_url}/value",
            params={"user": self._wallet},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return float(data.get("value", 0))

    # ------------------------------------------------------------------
    # Market resolution checks
    # ------------------------------------------------------------------

    async def get_market(self, condition_id: str) -> PolymarketMarket:
        """Get full market details including resolution status.

        Args:
            condition_id: The market's condition ID.

        Returns:
            PolymarketMarket with resolved/winning_outcome fields.
        """
        await self._rate_limiter.acquire()

        resp = await self._http.get(
            f"{self._clob_url}/markets/{condition_id}"
        )
        resp.raise_for_status()
        m: dict[str, Any] = resp.json()

        tokens = [
            PolymarketToken(
                token_id=t.get("token_id", ""),
                outcome=t.get("outcome", ""),
                price=float(t.get("price", 0) or 0),
                winner=bool(t.get("winner", False)),
            )
            for t in m.get("tokens", [])
        ]

        winning_outcome = ""
        for t in tokens:
            if t.winner:
                winning_outcome = t.outcome
                break

        return PolymarketMarket(
            condition_id=m.get("condition_id", condition_id),
            question_id=m.get("question_id", ""),
            question=m.get("question", ""),
            description=m.get("description", ""),
            market_slug=m.get("market_slug", ""),
            end_date_iso=m.get("end_date_iso"),
            active=m.get("active", True),
            closed=m.get("closed", False),
            resolved=bool(m.get("resolved", False)),
            winning_outcome=winning_outcome,
            tokens=tokens,
            volume=float(m.get("volume", 0) or 0),
            volume_24h=float(m.get("volume_num_24hr", 0) or 0),
            liquidity=float(m.get("liquidity", 0) or 0),
        )

    async def is_market_resolved(self, condition_id: str) -> bool:
        """Check if a market has been resolved.

        Args:
            condition_id: Market condition ID.
        """
        market = await self.get_market(condition_id)
        return market.resolved

    async def get_winning_outcome(self, condition_id: str) -> str | None:
        """Get the winning outcome of a resolved market.

        Args:
            condition_id: Market condition ID.

        Returns:
            The winning outcome (e.g. "Yes", "No") or None if not resolved.
        """
        market = await self.get_market(condition_id)
        if not market.resolved:
            return None
        return market.winning_outcome or None

    # ------------------------------------------------------------------
    # Redemption
    # ------------------------------------------------------------------

    async def redeem_position(
        self,
        *,
        condition_id: str,
        index_sets: list[int] | None = None,
    ) -> RedemptionResult:
        """Redeem winning tokens for USDC.e after market resolution.

        Calls the CTF contract's ``redeemPositions`` function.
        Winning tokens → $1 USDC.e each, losing tokens → $0.

        Args:
            condition_id: The market's condition ID.
            index_sets: Index sets to redeem. Defaults to ``[1, 2]``
                       (both YES and NO — only the winner pays out).

        Returns:
            RedemptionResult with transaction details.
        """
        if index_sets is None:
            index_sets = [1, 2]

        market = await self.get_market(condition_id)
        if not market.resolved:
            return RedemptionResult(
                condition_id=condition_id,
                success=False,
                error="Market not yet resolved",
            )

        winning = market.winning_outcome

        await self._rate_limiter.acquire()

        try:
            body = {
                "collateralToken": USDC_E_ADDRESS,
                "parentCollectionId": PARENT_COLLECTION_ID,
                "conditionId": condition_id,
                "indexSets": index_sets,
            }

            resp = await self._http.post(
                f"{self._clob_url}/redeemPositions",
                json=body,
                headers=self._build_redeem_headers(),
            )

            if resp.status_code >= 400:
                error_data: dict[str, Any] = {}
                try:
                    error_data = resp.json()
                except Exception:
                    error_data = {"error": resp.text}

                return RedemptionResult(
                    condition_id=condition_id,
                    outcome=winning,
                    success=False,
                    error=error_data.get("error", str(error_data)),
                )

            data: dict[str, Any] = resp.json()
            return RedemptionResult(
                condition_id=condition_id,
                outcome=winning,
                transaction_hash=data.get("transactionHash", data.get("hash", "")),
                success=True,
            )

        except Exception as exc:
            logger.error("Redemption failed for %s: %s", condition_id, exc)
            return RedemptionResult(
                condition_id=condition_id,
                outcome=winning,
                success=False,
                error=str(exc),
            )

    def _build_redeem_headers(self) -> dict[str, str]:
        """Build headers for redemption requests."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._wallet:
            headers["POLY-ADDRESS"] = self._wallet
        return headers

    # ------------------------------------------------------------------
    # Auto-redemption sweep
    # ------------------------------------------------------------------

    async def auto_redeem_all(
        self,
        *,
        min_shares: float = 0.1,
        dry_run: bool = False,
    ) -> AutoRedeemSummary:
        """Scan all positions and automatically redeem winning ones.

        This is the main entry point for the auto-redemption feature.
        After a market resolves and the user holds winning tokens,
        this method redeems them for USDC.e.

        Args:
            min_shares: Minimum shares to consider for redemption.
            dry_run: If True, report what would be redeemed without executing.

        Returns:
            AutoRedeemSummary with counts and per-position results.
        """
        logger.info("Starting auto-redemption sweep for %s", self._wallet)

        all_positions = await self.get_positions(size_threshold=min_shares)
        summary = AutoRedeemSummary(markets_checked=len(all_positions))

        redeemable: list[PolymarketPosition] = []
        for pos in all_positions:
            if pos.redeemable and pos.size > min_shares:
                redeemable.append(pos)

        if not redeemable:
            resolved_positions = await self._check_untagged_positions(
                all_positions, min_shares
            )
            redeemable.extend(resolved_positions)

        summary.redeemable_found = len(redeemable)

        if dry_run:
            logger.info(
                "Dry run: found %d redeemable positions", len(redeemable)
            )
            for pos in redeemable:
                summary.results.append(RedemptionResult(
                    condition_id=pos.condition_id,
                    outcome=pos.outcome,
                    shares_redeemed=pos.size,
                    usdc_received=pos.size if pos.is_winner else 0.0,
                    success=True,
                    error="dry_run",
                ))
            summary.total_usdc_redeemed = sum(
                r.usdc_received for r in summary.results
            )
            return summary

        for pos in redeemable:
            summary.redemptions_attempted += 1
            result = await self.redeem_position(condition_id=pos.condition_id)
            result.shares_redeemed = pos.size
            if result.success and pos.is_winner:
                result.usdc_received = pos.size
            summary.results.append(result)
            if result.success:
                summary.redemptions_succeeded += 1

        summary.total_usdc_redeemed = sum(
            r.usdc_received for r in summary.results
        )

        logger.info(
            "Auto-redeem complete: %d/%d succeeded, %.2f USDC recovered",
            summary.redemptions_succeeded,
            summary.redemptions_attempted,
            summary.total_usdc_redeemed,
        )
        return summary

    async def _check_untagged_positions(
        self,
        positions: list[PolymarketPosition],
        min_shares: float,
    ) -> list[PolymarketPosition]:
        """Check positions not yet tagged as redeemable by the API.

        Some positions may not have the 'redeemable' flag set yet.
        We check the market resolution status directly.
        """
        redeemable: list[PolymarketPosition] = []
        seen_conditions: set[str] = set()

        for pos in positions:
            if pos.condition_id in seen_conditions:
                continue
            if pos.size <= min_shares:
                continue

            seen_conditions.add(pos.condition_id)

            try:
                market = await self.get_market(pos.condition_id)
                if not market.resolved:
                    continue

                winning_token_ids: set[str] = set()
                for tok in market.tokens:
                    if tok.winner:
                        winning_token_ids.add(tok.token_id)

                if pos.asset_id in winning_token_ids:
                    pos.redeemable = True
                    pos.is_winner = True
                    pos.status = PolymarketPositionStatus.REDEEMABLE
                    redeemable.append(pos)
                    logger.info(
                        "Found untagged redeemable: %s (%s, %.1f shares)",
                        pos.title, pos.outcome, pos.size,
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to check market %s: %s", pos.condition_id, exc
                )

        return redeemable
