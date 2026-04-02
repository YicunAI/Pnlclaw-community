"""Pydantic transport/API models for authentication.

These are NOT SQLAlchemy ORM models — they are used for API request/response
serialization and internal data transfer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OAuthUserInfo(BaseModel):
    """User information returned by an OAuth provider."""

    provider: str
    provider_user_id: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None


class OAuthTokenResponse(BaseModel):
    """Token response from an OAuth provider token exchange."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"


class AuthenticatedUser(BaseModel):
    """Represents a user whose identity has been verified via JWT."""

    user_id: str = Field(..., description="UUID of the authenticated user")
    role: str = Field(..., description="User role (e.g. 'user', 'admin')")
    session_id: str = Field(..., description="Session identifier (jti)")


class TokenPair(BaseModel):
    """Access + refresh token pair issued after authentication."""

    access_token: str
    refresh_token: str


class GeoLocation(BaseModel):
    """Geographic location resolved from an IP address."""

    country: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class DeviceInfo(BaseModel):
    """Parsed device information from a User-Agent string."""

    device_type: str = Field("unknown", description="desktop, mobile, tablet, or unknown")
    os: str = Field("unknown", description="Operating system name")
    browser: str = Field("unknown", description="Browser name")
