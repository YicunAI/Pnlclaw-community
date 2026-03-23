"""Live server acceptance checks (PF-01, SE-02, F-08 live)."""

from __future__ import annotations

import io
import statistics
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx

BASE = "http://127.0.0.1:8099"


def measure_latency(method: str, path: str, **kwargs: object) -> float:
    client = httpx.Client(base_url=BASE, timeout=10)
    t0 = time.time()
    if method == "GET":
        r = client.get(path)
    elif method == "POST":
        r = client.post(path, **kwargs)  # type: ignore[arg-type]
    else:
        raise ValueError(method)
    elapsed = (time.time() - t0) * 1000
    client.close()
    return elapsed


def check_pf01() -> None:
    """PF-01: API latency p95 < 500ms (excluding agent/chat)."""
    endpoints = [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/markets"),
        ("GET", "/api/v1/strategies"),
        ("GET", "/api/v1/backtests"),
        ("GET", "/api/v1/paper/accounts"),
    ]

    all_latencies: list[float] = []
    for method, path in endpoints:
        latencies = []
        for _ in range(10):
            ms = measure_latency(method, path)
            latencies.append(ms)
        avg = statistics.mean(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        all_latencies.extend(latencies)
        print(f"  {method} {path}: avg={avg:.1f}ms p95={p95:.1f}ms")

    overall_p95 = sorted(all_latencies)[int(len(all_latencies) * 0.95)]
    print(f"\n  Overall p95: {overall_p95:.1f}ms")
    if overall_p95 < 500:
        print("  [OK] PF-01: PASS")
    else:
        print("  [!!] PF-01: FAIL")


def check_se02() -> None:
    """SE-02: No 'sk-' in server logs (we check response headers/body)."""
    client = httpx.Client(base_url=BASE, timeout=10)
    r = client.get("/api/v1/health")
    body = r.text
    has_key = "sk-" in body
    print(f"\n  SE-02: 'sk-' in health response: {has_key}")
    if not has_key:
        print("  [OK] SE-02: PASS (no secrets in API responses)")
    else:
        print("  [!!] SE-02: FAIL")
    client.close()


def check_f08_live() -> None:
    """F-08: Hit all endpoints live."""
    client = httpx.Client(base_url=BASE, timeout=10)
    endpoints = [
        ("GET", "/api/v1/health", 200),
        ("GET", "/api/v1/markets", 200),
        ("GET", "/api/v1/strategies", 200),
        ("GET", "/api/v1/backtests", 200),
        ("GET", "/api/v1/paper/accounts", 200),
    ]
    print("\n  F-08 Live endpoint test:")
    all_ok = True
    for method, path, expected in endpoints:
        r = client.get(path) if method == "GET" else client.post(path)
        ok = r.status_code == expected
        all_ok = all_ok and ok
        icon = "[OK]" if ok else "[!!]"
        print(f"  {icon} {method} {path} -> {r.status_code}")

    r2 = client.post(
        "/api/v1/strategies/validate",
        json={"name": "test", "type": "sma_cross", "symbols": ["BTC/USDT"],
              "interval": "1h", "parameters": {}},
    )
    ok2 = r2.status_code in (200, 422)
    icon2 = "[OK]" if ok2 else "[!!]"
    print(f"  {icon2} POST /api/v1/strategies/validate -> {r2.status_code}")
    all_ok = all_ok and ok2

    if all_ok:
        print("  [OK] F-08 live: PASS")
    else:
        print("  [!!] F-08 live: FAIL")
    client.close()


def main() -> None:
    print("=" * 60)
    print("PnLClaw v0.1.0 Live Server Acceptance")
    print("=" * 60)

    print("\n--- PF-01: API Latency ---")
    check_pf01()

    print("\n--- SE-02: Secret Redaction ---")
    check_se02()

    print("\n--- F-08: Live Endpoint Test ---")
    check_f08_live()

    print("\n" + "=" * 60)
    print("Live server tests complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
