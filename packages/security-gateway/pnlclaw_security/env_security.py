"""Environment variable sanitization — dangerous variable blacklist.

Distilled from OpenClaw src/infra/host-env-security.ts.
Implements SE-03: Environment variable loading has a dangerous variable blacklist.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Blocked keys — always stripped from environment
# ---------------------------------------------------------------------------

BLOCKED_KEYS: frozenset[str] = frozenset({
    # Language runtime injection vectors
    "NODE_OPTIONS",
    "NODE_PATH",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONBREAKPOINT",
    "PYTHONSTARTUP",
    "PERL5LIB",
    "PERL5OPT",
    "PERL5DB",
    "PERL5DBCMD",
    "RUBYLIB",
    "RUBYOPT",
    # Shell injection vectors
    "BASH_ENV",
    "ENV",
    "SHELLOPTS",
    "PS4",
    "IFS",
    "GCONV_PATH",
    # Security-sensitive
    "SSLKEYLOGFILE",
    "OPENSSL_CONF",
    "OPENSSL_ENGINES",
    # Git execution vectors
    "GIT_EXTERNAL_DIFF",
    "GIT_EXEC_PATH",
    # Java injection vectors
    "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS",
    "JDK_JAVA_OPTIONS",
    # .NET injection vectors
    "DOTNET_STARTUP_HOOKS",
    "DOTNET_ADDITIONAL_DEPS",
    # System-level
    "GLIBC_TUNABLES",
    # Build tool injection vectors
    "MAVEN_OPTS",
    "SBT_OPTS",
    "GRADLE_OPTS",
    "ANT_OPTS",
})

# ---------------------------------------------------------------------------
# Blocked prefixes — any key starting with these is stripped
# ---------------------------------------------------------------------------

BLOCKED_PREFIXES: tuple[str, ...] = (
    "DYLD_",
    "LD_",
    "BASH_FUNC_",
)

# ---------------------------------------------------------------------------
# Blocked override keys — blocked only when coming from override context
# (e.g. user-provided env overrides, not the host environment)
# ---------------------------------------------------------------------------

BLOCKED_OVERRIDE_KEYS: frozenset[str] = frozenset({
    "HOME",
    "SHELL",
    "ZDOTDIR",
    "GRADLE_USER_HOME",
    # Git command injection
    "GIT_SSH_COMMAND",
    "GIT_SSH",
    "GIT_PROXY_COMMAND",
    "GIT_ASKPASS",
    "SSH_ASKPASS",
    # Editor/pager execution
    "EDITOR",
    "VISUAL",
    "FCEDIT",
    "SUDO_EDITOR",
    "PAGER",
    "MANPAGER",
    "GIT_PAGER",
    "LESSOPEN",
    "LESSCLOSE",
    # Shell execution hooks
    "PROMPT_COMMAND",
    "HISTFILE",
    # Network config
    "WGETRC",
    "CURL_HOME",
})

BLOCKED_OVERRIDE_PREFIXES: tuple[str, ...] = (
    "GIT_CONFIG_",
    "NPM_CONFIG_",
)

# ---------------------------------------------------------------------------
# Secret key patterns — env vars that hold credentials
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^AWS_SECRET_ACCESS_KEY$",
        r"^AWS_SESSION_TOKEN$",
        r"^AWS_ACCESS_KEY_ID$",
        r"^OPENAI_API_KEY$",
        r"^ANTHROPIC_API_KEY$",
        r"^GOOGLE_API_KEY$",
        r"^DEEPSEEK_API_KEY$",
        r"^GROQ_API_KEY$",
        # Exchange-specific
        r"^BINANCE_API_KEY$",
        r"^BINANCE_API_SECRET$",
        r"^OKX_API_KEY$",
        r"^OKX_API_SECRET$",
        r"^OKX_PASSPHRASE$",
        r"^BYBIT_API_KEY$",
        r"^BYBIT_API_SECRET$",
        # Generic patterns
        r".*_API_KEY$",
        r".*_API_SECRET$",
        r".*_SECRET_KEY$",
        r".*_ACCESS_TOKEN$",
        r".*_REFRESH_TOKEN$",
        r".*_PASSWORD$",
        r".*_PASSWD$",
        r".*_CREDENTIAL$",
        r".*_PRIVATE_KEY$",
    ]
]

# Maximum env var value length (32 KB) — reject suspiciously large values
_MAX_VALUE_LENGTH = 32_768


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_dangerous_env_key(key: str) -> bool:
    """Return ``True`` if *key* is a dangerous environment variable name.

    Checks both the exact-match blacklist and prefix blacklist.
    Comparison is case-insensitive.
    """
    upper = key.strip().upper()
    if upper in BLOCKED_KEYS:
        return True
    return any(upper.startswith(prefix) for prefix in BLOCKED_PREFIXES)


def is_dangerous_override_key(key: str) -> bool:
    """Return ``True`` if *key* is dangerous in an override context.

    This includes all keys from :func:`is_dangerous_env_key` plus
    additional keys that are only dangerous when user-provided.
    """
    upper = key.strip().upper()
    if is_dangerous_env_key(upper):
        return True
    if upper in BLOCKED_OVERRIDE_KEYS:
        return True
    return any(upper.startswith(prefix) for prefix in BLOCKED_OVERRIDE_PREFIXES)


def is_secret_env_key(key: str) -> bool:
    """Return ``True`` if *key* matches a known credential-bearing env var pattern."""
    stripped = key.strip()
    return any(pat.match(stripped) for pat in _SECRET_PATTERNS)


def _validate_env_value(key: str, value: str) -> str | None:
    """Validate an env var value. Return warning message or ``None``."""
    if "\x00" in value:
        return f"Null byte in value for {key}"
    if len(value) > _MAX_VALUE_LENGTH:
        return f"Value for {key} exceeds {_MAX_VALUE_LENGTH} bytes"
    return None


class EnvSanitizationResult(BaseModel):
    """Result of environment variable sanitization."""

    allowed: dict[str, str] = Field(default_factory=dict, description="Sanitized env vars that passed all checks")
    blocked: list[str] = Field(default_factory=list, description="Keys that were blocked")
    secrets_detected: list[str] = Field(default_factory=list, description="Keys identified as holding secrets")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")


def sanitize_env(
    env: dict[str, str],
    *,
    overrides: dict[str, str] | None = None,
) -> EnvSanitizationResult:
    """Sanitize a set of environment variables.

    Args:
        env: Base environment variables (e.g. from ``os.environ``).
        overrides: User-provided overrides (subject to stricter checks).

    Returns:
        :class:`EnvSanitizationResult` with allowed vars, blocked keys,
        and any warnings.
    """
    result = EnvSanitizationResult()

    # Process base env
    for key, value in env.items():
        if is_dangerous_env_key(key):
            result.blocked.append(key)
            continue

        warning = _validate_env_value(key, value)
        if warning:
            result.warnings.append(warning)
            result.blocked.append(key)
            continue

        if is_secret_env_key(key):
            result.secrets_detected.append(key)
            # Secrets are allowed through (they're needed) but flagged

        result.allowed[key] = value

    # Process overrides with stricter checks
    if overrides:
        for key, value in overrides.items():
            if is_dangerous_override_key(key):
                result.blocked.append(key)
                result.warnings.append(f"Override blocked: {key}")
                continue

            warning = _validate_env_value(key, value)
            if warning:
                result.warnings.append(warning)
                result.blocked.append(key)
                continue

            if is_secret_env_key(key):
                result.secrets_detected.append(key)

            result.allowed[key] = value

    return result
