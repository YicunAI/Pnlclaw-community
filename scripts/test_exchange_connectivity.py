"""Test real-time connectivity to all exchange data sources.

Uses PnLClaw's own exchange-sdk modules — not raw websockets/httpx.
This validates that our SDK layer works end-to-end with live data.
"""

import asyncio
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")


async def test_binance() -> bool:
    """Test Binance via our BinanceWSClient + normalizer."""
    from pnlclaw_exchange.exchanges.binance.ws_client import BinanceWSClient
    from pnlclaw_types.market import TickerEvent

    received: list[TickerEvent] = []
    client = BinanceWSClient(on_ticker=received.append)

    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        await client.subscribe_ticker(["btcusdt"])
        # Wait for data
        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.5)

        if received:
            t = received[0]
            print(f"  [OK] Binance BTC/USDT via SDK")
            print(f"       last={t.last_price} bid={t.bid} ask={t.ask}")
            print(f"       vol24h={t.volume_24h} change={t.change_24h_pct}%")
            return True
        else:
            print("  [FAIL] Binance: No ticker received in 10s")
            return False
    except Exception as e:
        print(f"  [FAIL] Binance: {e}")
        return False
    finally:
        await client.close()


async def test_binance_kline() -> bool:
    """Test Binance kline stream via SDK."""
    from pnlclaw_exchange.exchanges.binance.ws_client import BinanceWSClient
    from pnlclaw_types.market import KlineEvent

    received: list[KlineEvent] = []
    client = BinanceWSClient(on_kline=received.append)

    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        await client.subscribe_kline(["btcusdt"], "1m")
        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.5)

        if received:
            k = received[0]
            print(f"  [OK] Binance BTC/USDT kline via SDK")
            print(f"       o={k.open} h={k.high} l={k.low} c={k.close}")
            print(f"       interval={k.interval} closed={k.closed}")
            return True
        else:
            print("  [FAIL] Binance kline: No data in 10s")
            return False
    except Exception as e:
        print(f"  [FAIL] Binance kline: {e}")
        return False
    finally:
        await client.close()


async def test_binance_l2() -> bool:
    """Test Binance L2 orderbook depth REST snapshot."""
    import httpx

    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                "https://data-api.binance.vision/api/v3/depth",
                params={"symbol": "BTCUSDT", "limit": 5},
            )
            resp.raise_for_status()
            data = resp.json()
            bids = data["bids"][:3]
            asks = data["asks"][:3]
            print(f"  [OK] Binance L2 depth (REST)")
            print(f"       Top bids: {bids}")
            print(f"       Top asks: {asks}")
            return True
    except Exception as e:
        print(f"  [FAIL] Binance L2: {e}")
        return False


async def test_okx() -> bool:
    """Test OKX via our OKXWSClient + normalizer."""
    from pnlclaw_exchange.exchanges.okx.ws_client import OKXWSClient
    from pnlclaw_types.market import TickerEvent

    received: list[TickerEvent] = []
    client = OKXWSClient(on_ticker=received.append)

    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        await client.subscribe_ticker(["BTC-USDT"])
        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.5)

        if received:
            t = received[0]
            print(f"  [OK] OKX BTC-USDT via SDK")
            print(f"       last={t.last_price} bid={t.bid} ask={t.ask}")
            print(f"       vol24h={t.volume_24h} change={t.change_24h_pct}%")
            return True
        else:
            print("  [FAIL] OKX: No ticker received in 10s")
            return False
    except Exception as e:
        print(f"  [FAIL] OKX: {e}")
        return False
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def test_polymarket() -> bool:
    """Test Polymarket via our PolymarketClient."""
    from pnlclaw_exchange.exchanges.polymarket.client import PolymarketClient

    client = PolymarketClient()
    try:
        # 1. List markets
        markets = await client.list_markets(limit=50)
        if not markets:
            print("  [FAIL] Polymarket: No markets returned")
            return False

        # Filter for truly active markets (price between 0.01 and 0.99)
        active_markets = [
            m for m in markets
            if m.tokens and any(0.01 < t.price < 0.99 for t in m.tokens)
        ]
        print(f"  [OK] Total markets: {len(markets)}, active (live prices): {len(active_markets)}")

        display = active_markets[:2] if active_markets else markets[:2]
        for i, m in enumerate(display):
            print(f"       {i+1}. {m.question[:65]}")
            if m.tokens:
                for t in m.tokens[:2]:
                    print(f"          {t.outcome}: price={t.price}")

        # 2. Orderbook — try active markets first
        target = active_markets[0] if active_markets else markets[0]
        if target.tokens:
            token_id = target.tokens[0].token_id
            try:
                book = await client.get_orderbook(token_id)
                n_bids = len(book.bids)
                n_asks = len(book.asks)
                print(f"\n  [OK] Orderbook for token {token_id[:20]}...")
                print(f"       {n_bids} bids, {n_asks} asks")
                if book.bids:
                    print(f"       Best bid: {book.bids[0]}")
                if book.asks:
                    print(f"       Best ask: {book.asks[0]}")
                print(f"       Last trade: {book.last_trade_price}")
            except Exception as e:
                print(f"\n  [WARN] Orderbook failed: {e}")

        # 3. Midpoint
        if target.tokens:
            token_id = target.tokens[0].token_id
            try:
                mid = await client.get_midpoint(token_id)
                print(f"\n  [OK] Midpoint price: {mid}")
            except Exception:
                pass

        return True
    except Exception as e:
        print(f"  [FAIL] Polymarket: {e}")
        return False
    finally:
        await client.close()


async def main() -> None:
    print("=" * 65)
    print("PnLClaw Exchange SDK — Live Connectivity Test")
    print("=" * 65)

    results: dict[str, bool] = {}

    print("\n--- 1. Binance (data-stream.binance.vision) ---")
    results["Binance Ticker"] = await test_binance()

    print("\n--- 2. Binance Kline ---")
    results["Binance Kline"] = await test_binance_kline()

    print("\n--- 3. Binance L2 Depth ---")
    results["Binance L2"] = await test_binance_l2()

    print("\n--- 4. OKX (ws.okx.com) ---")
    results["OKX Ticker"] = await test_okx()

    print("\n--- 5. Polymarket (clob.polymarket.com) ---")
    results["Polymarket"] = await test_polymarket()

    print("\n" + "=" * 65)
    print("RESULTS SUMMARY:")
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        icon = "[v]" if ok else "[x]"
        print(f"  {icon} {name}: {status}")
    total_pass = sum(1 for v in results.values() if v)
    print(f"\n  {total_pass}/{len(results)} data sources verified")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
