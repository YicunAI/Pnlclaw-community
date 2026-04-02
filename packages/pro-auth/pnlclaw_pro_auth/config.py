"""Auth configuration via pydantic-settings."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class AuthConfig(BaseSettings):
    """Authentication settings for PnLClaw Pro.

    Reads from environment variables with ``PNLCLAW_AUTH_`` prefix, e.g.
    ``PNLCLAW_AUTH_JWT_SECRET``.
    """

    model_config = {"env_prefix": "PNLCLAW_AUTH_"}

    jwt_secret: str = Field(..., description="JWT signing secret (required, no default)")
    jwt_algorithm: str = Field("HS256", description="JWT signing algorithm")

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(f"jwt_algorithm must be one of {allowed}, got {v!r}")
        return v

    access_token_expire_minutes: int = Field(15, description="Access token lifetime in minutes")
    refresh_token_expire_days: int = Field(7, description="Refresh token lifetime in days")
    oauth_state_expire_minutes: int = Field(5, description="OAuth state token lifetime in minutes")

    # Google OAuth
    google_client_id: str = Field("", description="Google OAuth client ID")
    google_client_secret: str = Field("", description="Google OAuth client secret")

    # GitHub OAuth
    github_client_id: str = Field("", description="GitHub OAuth client ID")
    github_client_secret: str = Field("", description="GitHub OAuth client secret")

    # Twitter / X OAuth
    twitter_client_id: str = Field("", description="Twitter/X OAuth client ID")
    twitter_client_secret: str = Field("", description="Twitter/X OAuth client secret")

    # Redirect
    oauth_redirect_base_url: str = Field(
        "http://localhost:3001", description="Base URL for OAuth redirect callbacks (frontend origin)"
    )

    # Bootstrap
    initial_admin_email: str = Field("", description="Email address of the first admin user")
