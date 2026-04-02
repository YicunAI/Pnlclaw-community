"""Google OAuth 2.0 provider using Authlib."""

from __future__ import annotations

import logging

from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import-untyped]

from pnlclaw_pro_auth.errors import OAuthError
from pnlclaw_pro_auth.models import OAuthTokenResponse, OAuthUserInfo

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_SCOPE = "openid email profile"


class GoogleOAuthProvider:
    """Google OAuth 2.0 implementation.

    Args:
        client_id: Google OAuth client ID.
        client_secret: Google OAuth client secret.
    """

    provider_name: str = "google"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def _make_client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )

    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Build the Google authorization redirect URL."""
        client = self._make_client()
        url, _ = client.create_authorization_url(
            _AUTHORIZE_URL,
            state=state,
            redirect_uri=redirect_uri,
            scope=_SCOPE,
            access_type="offline",
            prompt="consent",
        )
        return url

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> OAuthTokenResponse:
        """Exchange an authorization code for tokens with Google."""
        client = self._make_client()
        try:
            token = await client.fetch_token(
                _TOKEN_URL,
                code=code,
                redirect_uri=redirect_uri,
                grant_type="authorization_code",
            )
        except Exception as exc:
            raise OAuthError(f"Google token exchange failed: {exc}") from exc
        finally:
            await client.aclose()

        return OAuthTokenResponse(
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            expires_in=token.get("expires_in"),
            token_type=token.get("token_type", "Bearer"),
        )

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch the authenticated user's profile from Google."""
        client = self._make_client()
        client.token = {"access_token": access_token, "token_type": "Bearer"}
        try:
            resp = await client.get(_USERINFO_URL)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise OAuthError(f"Google user info request failed: {exc}") from exc
        finally:
            await client.aclose()

        provider_user_id = data.get("sub", "")
        if not provider_user_id:
            raise OAuthError("Google did not return a user ID (sub claim)")

        return OAuthUserInfo(
            provider="google",
            provider_user_id=provider_user_id,
            email=data.get("email"),
            name=data.get("name"),
            avatar_url=data.get("picture"),
        )
