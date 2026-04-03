"""GitHub OAuth 2.0 provider using Authlib."""

from __future__ import annotations

import logging

from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import-untyped]

from pnlclaw_pro_auth.errors import OAuthError
from pnlclaw_pro_auth.models import OAuthTokenResponse, OAuthUserInfo

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_EMAILS_URL = "https://api.github.com/user/emails"
_SCOPE = "read:user user:email"


class GitHubOAuthProvider:
    """GitHub OAuth 2.0 implementation.

    Args:
        client_id: GitHub OAuth app client ID.
        client_secret: GitHub OAuth app client secret.
    """

    provider_name: str = "github"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def _make_client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )

    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Build the GitHub authorization redirect URL."""
        client = self._make_client()
        url, _ = client.create_authorization_url(
            _AUTHORIZE_URL,
            state=state,
            redirect_uri=redirect_uri,
            scope=_SCOPE,
        )
        return url

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> OAuthTokenResponse:
        """Exchange an authorization code for tokens with GitHub."""
        client = self._make_client()
        try:
            # GitHub returns JSON when Accept header is set
            token = await client.fetch_token(
                _TOKEN_URL,
                code=code,
                redirect_uri=redirect_uri,
                grant_type="authorization_code",
                headers={"Accept": "application/json"},
            )
        except Exception as exc:
            raise OAuthError(f"GitHub token exchange failed: {exc}") from exc
        finally:
            await client.aclose()

        return OAuthTokenResponse(
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            expires_in=token.get("expires_in"),
            token_type=token.get("token_type", "Bearer"),
        )

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch the authenticated user's profile from GitHub.

        If the /user endpoint does not include an email (private email),
        falls back to /user/emails to find the primary verified address.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        client = self._make_client()
        client.token = {"access_token": access_token, "token_type": "Bearer"}
        try:
            resp = await client.get(_USER_URL, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            email = data.get("email") or ""

            if not email:
                try:
                    emails_resp = await client.get(_EMAILS_URL, headers=headers)
                    emails_resp.raise_for_status()
                    for entry in emails_resp.json():
                        if entry.get("primary") and entry.get("verified"):
                            email = entry["email"]
                            break
                    if not email:
                        for entry in emails_resp.json():
                            if entry.get("verified"):
                                email = entry["email"]
                                break
                except Exception:
                    logger.warning("Failed to fetch /user/emails, proceeding without email")
        except Exception as exc:
            raise OAuthError(f"GitHub user info request failed: {exc}") from exc
        finally:
            await client.aclose()

        provider_user_id = str(data.get("id", ""))
        if not provider_user_id:
            raise OAuthError("GitHub did not return a user ID")

        return OAuthUserInfo(
            provider="github",
            provider_user_id=provider_user_id,
            email=email or None,
            name=data.get("name") or data.get("login"),
            avatar_url=data.get("avatar_url"),
        )
