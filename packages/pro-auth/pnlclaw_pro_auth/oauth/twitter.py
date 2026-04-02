"""Twitter / X OAuth 2.0 provider with PKCE using Authlib."""

from __future__ import annotations

import hashlib
import logging
import secrets
from base64 import urlsafe_b64encode

from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import-untyped]

from pnlclaw_pro_auth.errors import OAuthError
from pnlclaw_pro_auth.models import OAuthTokenResponse, OAuthUserInfo

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
_USER_URL = "https://api.twitter.com/2/users/me?user.fields=profile_image_url,name"
_SCOPE = "users.read tweet.read"
_CODE_CHALLENGE_METHOD = "S256"


def _generate_code_verifier() -> str:
    """Generate a cryptographically random PKCE code verifier."""
    return secrets.token_urlsafe(48)


def _generate_code_challenge(verifier: str) -> str:
    """Derive a S256 code challenge from a code verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class TwitterOAuthProvider:
    """Twitter / X OAuth 2.0 implementation with PKCE.

    Args:
        client_id: Twitter OAuth 2.0 client ID.
        client_secret: Twitter OAuth 2.0 client secret.
    """

    provider_name: str = "twitter"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def _make_client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            code_challenge_method=_CODE_CHALLENGE_METHOD,
        )

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Generate a ``(code_verifier, code_challenge)`` PKCE pair.

        The verifier must be stored server-side (e.g. in the OAuth state
        token) and supplied when exchanging the authorization code.
        """
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        return verifier, challenge

    async def get_authorization_url(self, state: str, redirect_uri: str) -> tuple[str, str]:
        """Build the Twitter authorization redirect URL with PKCE challenge.

        Returns:
            A ``(url, code_verifier)`` tuple.  The caller **must** persist
            the ``code_verifier`` (e.g. in the OAuth state token) and pass it
            to :meth:`exchange_code` later.
        """
        client = self._make_client()
        verifier, challenge = self.generate_pkce_pair()
        url, _ = client.create_authorization_url(
            _AUTHORIZE_URL,
            state=state,
            redirect_uri=redirect_uri,
            scope=_SCOPE,
            code_challenge=challenge,
            code_challenge_method=_CODE_CHALLENGE_METHOD,
        )
        return url, verifier

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthTokenResponse:
        """Exchange an authorization code for tokens with Twitter.

        Args:
            code: The authorization code from the callback.
            redirect_uri: Must match the URI used during authorization.
            code_verifier: The PKCE code verifier generated earlier.
        """
        client = self._make_client()
        try:
            kwargs: dict = {
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
            if code_verifier:
                kwargs["code_verifier"] = code_verifier
            token = await client.fetch_token(_TOKEN_URL, **kwargs)
        except Exception as exc:
            raise OAuthError(f"Twitter token exchange failed: {exc}") from exc
        finally:
            await client.aclose()

        return OAuthTokenResponse(
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            expires_in=token.get("expires_in"),
            token_type=token.get("token_type", "Bearer"),
        )

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch the authenticated user's profile from Twitter."""
        client = self._make_client()
        client.token = {"access_token": access_token, "token_type": "Bearer"}
        try:
            resp = await client.get(
                _USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", {})
        except Exception as exc:
            raise OAuthError(f"Twitter user info request failed: {exc}") from exc
        finally:
            await client.aclose()

        return OAuthUserInfo(
            provider="twitter",
            provider_user_id=data.get("id", ""),
            email=None,  # Twitter v2 does not return email by default
            name=data.get("name") or data.get("username"),
            avatar_url=data.get("profile_image_url"),
        )
