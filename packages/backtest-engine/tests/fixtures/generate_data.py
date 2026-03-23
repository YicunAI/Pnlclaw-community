"""Generate deterministic BTC/USDT 1h sample data for regression tests.

This script creates a Parquet file with 200 kline bars using a seeded
random walk so results are perfectly reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_deterministic_btc_data(
    n_bars: int = 200,
    seed: int = 42,
    initial_price: float = 40_000.0,
    start_ts_ms: int = 1_704_067_200_000,  # 2024-01-01 00:00 UTC
    interval_ms: int = 3_600_000,  # 1 hour
) -> pd.DataFrame:
    """Generate deterministic OHLCV data using a seeded random walk.

    Args:
        n_bars: Number of kline bars to generate.
        seed: Random seed for reproducibility.
        initial_price: Starting close price.
        start_ts_ms: Starting timestamp in milliseconds.
        interval_ms: Interval between bars in milliseconds.

    Returns:
        A DataFrame with columns:
        timestamp, exchange, symbol, interval, open, high, low, close, volume, closed
    """
    rng = np.random.RandomState(seed)  # noqa: NPY002 — deterministic seed

    # Generate log returns with slight upward drift and mean-reversion
    log_returns = rng.normal(loc=0.0002, scale=0.015, size=n_bars)

    closes = np.zeros(n_bars)
    closes[0] = initial_price
    for i in range(1, n_bars):
        closes[i] = closes[i - 1] * np.exp(log_returns[i])

    # Generate OHLV from close
    opens = np.roll(closes, 1)
    opens[0] = initial_price * 0.999

    # High/Low: random spread around close
    high_spread = rng.uniform(0.002, 0.010, size=n_bars)
    low_spread = rng.uniform(0.002, 0.010, size=n_bars)
    highs = np.maximum(opens, closes) * (1 + high_spread)
    lows = np.minimum(opens, closes) * (1 - low_spread)

    volumes = rng.uniform(50.0, 500.0, size=n_bars)

    timestamps = start_ts_ms + np.arange(n_bars) * interval_ms

    df = pd.DataFrame(
        {
            "timestamp": timestamps.astype(np.int64),
            "exchange": "backtest",
            "symbol": "BTC/USDT",
            "interval": "1h",
            "open": np.round(opens, 2),
            "high": np.round(highs, 2),
            "low": np.round(lows, 2),
            "close": np.round(closes, 2),
            "volume": np.round(volumes, 2),
            "closed": True,
        }
    )
    return df


if __name__ == "__main__":
    import pathlib

    out = pathlib.Path(__file__).parent / "btc_usdt_1h_sample.parquet"
    df = generate_deterministic_btc_data()
    df.to_parquet(out, engine="pyarrow", index=False)
    print(f"Written {len(df)} rows to {out}")
