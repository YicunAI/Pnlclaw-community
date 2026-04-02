"""pnlclaw_pro_auth — Pro authentication: OAuth, JWT, TOTP for PnLClaw."""

from pnlclaw_pro_auth.config import AuthConfig
from pnlclaw_pro_auth.errors import (
    AccountBannedError,
    AccountSuspendedError,
    AuthenticationError,
    InvalidTokenError,
    OAuthError,
    TokenExpiredError,
    TOTPRequiredError,
)
from pnlclaw_pro_auth.jwt_manager import JWTManager
from pnlclaw_pro_auth.models import (
    AuthenticatedUser,
    DeviceInfo,
    GeoLocation,
    OAuthTokenResponse,
    OAuthUserInfo,
    TokenPair,
)
from pnlclaw_pro_auth.session_manager import SessionManager
from pnlclaw_pro_auth.totp_manager import TOTPManager

__all__ = [
    # config
    "AuthConfig",
    # errors
    "AccountBannedError",
    "AccountSuspendedError",
    "AuthenticationError",
    "InvalidTokenError",
    "OAuthError",
    "TokenExpiredError",
    "TOTPRequiredError",
    # managers
    "JWTManager",
    "SessionManager",
    "TOTPManager",
    # models
    "AuthenticatedUser",
    "DeviceInfo",
    "GeoLocation",
    "OAuthTokenResponse",
    "OAuthUserInfo",
    "TokenPair",
]
