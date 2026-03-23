#!/usr/bin/env python3
"""Download Binance 1h klines (BTC/USDT, ETH/USDT) or write deterministic synthetic Parquet.

Public REST API — no API key. Falls back to synthetic data if the API is unreachable.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
INTERVAL = "1h"
MS_PER_HOUR = 3_600_000
N_BARS_90D = 90 * 24  # 2160


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate demo kline Parquet files for PnLClaw.")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("demo/data"),
        help="Directory for Parquet output (default: demo/data)",
    )
    return p.parse_args()


def _synthetic_ohlcv(
    *,
    base_price: float,
    n_bars: int,
    seed: int,
    start_ts_ms: int | None = None,
) -> pd.DataFrame:
    """Deterministic sine + drift + noise (used when API fails)."""
    rng = np.random.default_rng(seed)
    if start_ts_ms is None:
        start_ts_ms = int(time.time() * 1000) - n_bars * MS_PER_HOUR

    t = np.arange(n_bars, dtype=np.float64)
    trend = 0.00008 * t
    seasonal = 0.02 * np.sin(2 * math.pi * t / 168.0)  # ~1 week
    noise = rng.normal(0.0, 0.004, size=n_bars)
    log_px = np.log(base_price) + trend + seasonal + noise.cumsum() * 0.0005
    close = np.exp(log_px)

    open_ = np.empty(n_bars)
    open_[0] = close[0] * 0.999
    open_[1:] = close[:-1]

    spread = rng.uniform(0.001, 0.008, size=n_bars)
    high = np.maximum(open_, close) * (1.0 + spread)
    low = np.minimum(open_, close) * (1.0 - spread)
    volume = rng.uniform(20.0, 800.0, size=n_bars)
    quote_volume = volume * close

    ts = start_ts_ms + np.arange(n_bars, dtype=np.int64) * MS_PER_HOUR

    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": np.round(open_, 8),
            "high": np.round(high, 8),
            "low": np.round(low, 8),
            "close": np.round(close, 8),
            "volume": np.round(volume, 8),
            "quote_volume": np.round(quote_volume, 8),
        }
    )


def _klines_to_frame(rows: list) -> pd.DataFrame:
    """Binance kline array rows → DataFrame with required columns."""
    records = []
    for row in rows:
        records.append(
            {
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "quote_volume": float(row[7]),
            }
        )
    return pd.DataFrame(records)


def _fetch_symbol(
    client: httpx.Client,
    symbol: str,
    display_pair: str,
    start_ms: int,
    end_ms: int,
) -> pd.DataFrame:
    """Paginate Binance klines (max 1000 per request)."""
    all_rows: list = []
    cursor = start_ms
    page = 0
    bar_count = max(1, (end_ms - start_ms) // MS_PER_HOUR)
    est_pages = max(1, int(math.ceil(bar_count / 1000.0)))

    while cursor < end_ms:
        page += 1
        print(f"Downloading {display_pair} 1h klines... page {page}/{est_pages}")

        r = client.get(
            BINANCE_KLINES,
            params={
                "symbol": symbol,
                "interval": INTERVAL,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            },
            timeout=30.0,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        all_rows.extend(batch)
        last_open = int(batch[-1][0])
        cursor = last_open + MS_PER_HOUR
        if len(batch) < 1000:
            break

    if not all_rows:
        raise RuntimeError("No kline rows returned")
    return _klines_to_frame(all_rows)


def _download_or_synthetic(
    client: httpx.Client,
    *,
    symbol: str,
    display_pair: str,
    parquet_name: str,
    out_dir: Path,
    synthetic_base: float,
    synthetic_seed: int,
) -> None:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - N_BARS_90D * MS_PER_HOUR
    path = out_dir / parquet_name

    try:
        df = _fetch_symbol(client, symbol, display_pair, start_ms, end_ms)
        if len(df) < N_BARS_90D // 2:
            raise RuntimeError("Incomplete kline download")
    except Exception as exc:
        print(f"Binance fetch failed ({exc!r}); writing synthetic data for {display_pair}.")
        df = _synthetic_ohlcv(base_price=synthetic_base, n_bars=N_BARS_90D, seed=synthetic_seed)

    df.to_parquet(path, engine="pyarrow", index=False)
    print(f"Wrote {len(df)} rows to {path}")


def main() -> int:
    args = _parse_args()
    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    client: httpx.Client | None = None
    try:
        client = httpx.Client()
        _download_or_synthetic(
            client,
            symbol="BTCUSDT",
            display_pair="BTC/USDT",
            parquet_name="btc_usdt_1h_90d.parquet",
            out_dir=out_dir,
            synthetic_base=40_000.0,
            synthetic_seed=101,
        )
        _download_or_synthetic(
            client,
            symbol="ETHUSDT",
            display_pair="ETH/USDT",
            parquet_name="eth_usdt_1h_90d.parquet",
            out_dir=out_dir,
            synthetic_base=2500.0,
            synthetic_seed=202,
        )
    finally:
        if client is not None:
            client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
