"""OAuth provider protocol definition."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pnlclaw_pro_auth.models import OAuthTokenResponse, OAuthUserInfo


@runtime_checkable
class OAuthProvider(Protocol):
    """Protocol that all OAuth provider implementations must satisfy.

    Notes:
        - Most providers return ``str`` from ``get_authorization_url``.
        - Twitter (PKCE) returns ``tuple[str, str]`` — ``(url, code_verifier)``.
          Callers must handle both return shapes or use provider-specific typing.
    """

    provider_name: str

    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Return the URL the user should be redirected to for authorization.

        Twitter's implementation returns ``tuple[str, str]`` instead (url +
        PKCE code_verifier).  See :class:`TwitterOAuthProvider`.
        """
        ...

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> OAuthTokenResponse:
        """Exchange an authorization code for an access token.

        Args:
            code: The authorization code from the callback.
            redirect_uri: Must match the URI used during authorization.
            code_verifier: PKCE code verifier (required for Twitter, ignored
                by other providers).
        """
        ...

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch user profile information using the access token."""
        ...
