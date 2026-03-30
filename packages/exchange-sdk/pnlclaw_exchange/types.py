"""Internal configuration types for the exchange-sdk package."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WSClientConfig(BaseModel):
    """Configuration for a WebSocket client connection."""

    url: str = Field(..., description="WebSocket endpoint URL")
    exchange: str = Field(..., description="Exchange identifier, e.g. 'binance'")
    reconnect_enabled: bool = Field(True, description="Whether auto-reconnect is enabled")
    stall_timeout_s: float = Field(30.0, gt=0, description="Stall detection timeout in seconds")
    max_restarts_per_hour: int = Field(10, ge=1, description="Max reconnection attempts per hour")
    proxy_url: str | None = Field(None, description="SOCKS5/HTTP proxy URL, e.g. 'socks5h://127.0.0.1:1081'")


class ReconnectConfig(BaseModel):
    """Configuration for the reconnection manager."""

    initial_delay_s: float = Field(1.0, gt=0, description="Initial backoff delay in seconds")
    max_delay_s: float = Field(30.0, gt=0, description="Maximum backoff delay in seconds")
    factor: float = Field(2.0, gt=1, description="Exponential backoff multiplier")
    jitter: float = Field(0.2, ge=0, le=1, description="Jitter fraction (±jitter)")
    max_restarts_per_hour: int = Field(10, ge=1, description="Max restarts per hour")


class RateLimiterConfig(BaseModel):
    """Configuration for the API rate limiter."""

    calls_per_window: int = Field(1200, ge=1, description="Max calls allowed per window")
    window_ms: int = Field(60_000, ge=1000, description="Sliding window duration in milliseconds")
