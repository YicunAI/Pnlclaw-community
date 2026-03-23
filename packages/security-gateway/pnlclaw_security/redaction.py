"""Log redaction engine — pattern-based sensitive data masking.

Distilled from OpenClaw src/logging/redact.ts.
Implements SE-02: Logs automatically redact API Key, Secret, Token, JWT, Password.
Implements HC-07: Secrets never enter logs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Masking helpers
# ---------------------------------------------------------------------------

_SHORT_THRESHOLD = 18


def mask_token(token: str) -> str:
    """Mask a sensitive token value.

    - Tokens shorter than 18 characters → ``***``
    - Longer tokens → ``first6…last4``
    """
    if len(token) < _SHORT_THRESHOLD:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def _redact_pem_block(match: re.Match[str]) -> str:
    """Replace the interior of a PEM block, keeping first and last lines."""
    block = match.group(0)
    lines = block.splitlines()
    if len(lines) <= 2:
        return "***"
    return f"{lines[0]}\n...redacted...\n{lines[-1]}"


# ---------------------------------------------------------------------------
# Redaction patterns
# ---------------------------------------------------------------------------
# Each entry: (name, compiled regex, replacement_fn_or_None)
# If replacement_fn is None, the default mask_token logic is used.

_RAW_PATTERNS: list[tuple[str, str, int]] = [
    # --- Structured assignments ---
    (
        "env_assignment",
        r"\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)\b\s*[=:]\s*"
        r"""(["']?)([^\s"'\\]{4,})\1""",
        0,
    ),
    (
        "json_field",
        r'"(?:apiKey|api_key|token|secret|password|passwd|accessToken|access_token|'
        r'refreshToken|refresh_token|secretKey|secret_key|apiSecret|api_secret)"'
        r"""\s*:\s*"([^"]{4,})""" + '"',
        0,
    ),
    (
        "cli_flag",
        r"""--(?:api[-_]?key|token|secret|password|passwd)\s+(["']?)([^\s"']{4,})\1""",
        0,
    ),
    # --- Bearer / Authorization ---
    (
        "bearer_header",
        r"Authorization\s*[:=]\s*Bearer\s+([A-Za-z0-9._\-+=]{8,})",
        0,
    ),
    (
        "bearer_loose",
        r"\bBearer\s+([A-Za-z0-9._\-+=]{18,})\b",
        0,
    ),
    # --- Provider-specific prefixes ---
    ("sk_prefix", r"\b(sk-[A-Za-z0-9_\-]{8,})\b", 0),
    ("ghp_prefix", r"\b(ghp_[A-Za-z0-9]{20,})\b", 0),
    ("github_pat", r"\b(github_pat_[A-Za-z0-9_]{20,})\b", 0),
    ("slack_token", r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})\b", 0),
    ("slack_app", r"\b(xapp-[A-Za-z0-9\-]{10,})\b", 0),
    ("groq_key", r"\b(gsk_[A-Za-z0-9_\-]{10,})\b", 0),
    ("google_ai", r"\b(AIza[0-9A-Za-z\-_]{20,})\b", 0),
    ("perplexity", r"\b(pplx-[A-Za-z0-9_\-]{10,})\b", 0),
    ("npm_token", r"\b(npm_[A-Za-z0-9]{10,})\b", 0),
    ("aws_access_key", r"\b(AKIA[A-Z0-9]{16})\b", 0),
    # --- Telegram ---
    ("telegram_bot", r"\bbot(\d{6,}:[A-Za-z0-9_\-]{20,})\b", 0),
    ("telegram_id", r"\b(\d{6,}:[A-Za-z0-9_\-]{20,})\b", 0),
    # --- JWT ---
    (
        "jwt_token",
        r"\b(eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})\b",
        0,
    ),
]

# PEM blocks handled separately with multi-line regex
_PEM_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"
)


def _build_default_replacement(pattern: re.Pattern[str]) -> re.Pattern[str]:
    """Return *pattern* as-is (used by _apply_pattern)."""
    return pattern


# Compile all patterns once at module load
_COMPILED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(raw, re.IGNORECASE if name.startswith(("env_", "json_", "cli_")) else 0))
    for name, raw, _flags in _RAW_PATTERNS
]


# ---------------------------------------------------------------------------
# Core replacement logic
# ---------------------------------------------------------------------------


def _replace_match(match: re.Match[str]) -> str:
    """Extract the most specific capture group and mask it."""
    # Walk capture groups from last to first; first non-None is the secret
    groups = match.groups()
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g is not None and len(g) >= 4:
            masked = mask_token(g)
            # Replace the captured secret within the full match
            full = match.group(0)
            return full.replace(g, masked, 1)

    # Fallback: mask the entire match
    return mask_token(match.group(0))


# ---------------------------------------------------------------------------
# Chunked processing to prevent ReDoS on large inputs
# ---------------------------------------------------------------------------

CHUNK_THRESHOLD = 32_768
CHUNK_SIZE = 16_384
_OVERLAP = 256  # overlap between chunks to catch tokens straddling boundaries


def _redact_chunk(
    text: str,
    patterns: Sequence[tuple[str, re.Pattern[str]]],
) -> str:
    """Apply all patterns to a single chunk of text."""
    result = text
    # PEM blocks first (multi-line)
    result = _PEM_PATTERN.sub(_redact_pem_block, result)
    # Then line-oriented patterns
    for _name, pat in patterns:
        result = pat.sub(_replace_match, result)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact_text(
    text: str,
    *,
    extra_patterns: list[re.Pattern[str]] | None = None,
) -> str:
    """Redact sensitive tokens from *text*.

    For inputs larger than :data:`CHUNK_THRESHOLD` bytes the text is
    processed in overlapping chunks to bound regex execution time and
    prevent ReDoS.

    Args:
        text: The input string to redact.
        extra_patterns: Additional compiled regex patterns whose group-1
            captures will be masked.

    Returns:
        A copy of *text* with sensitive tokens replaced by masked values.
    """
    if not text:
        return text

    patterns = list(_COMPILED_PATTERNS)
    if extra_patterns:
        for i, pat in enumerate(extra_patterns):
            patterns.append((f"custom_{i}", pat))

    if len(text) <= CHUNK_THRESHOLD:
        return _redact_chunk(text, patterns)

    # Chunked processing for large texts
    result_parts: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + CHUNK_SIZE + _OVERLAP, len(text))
        chunk = text[pos:end]
        redacted = _redact_chunk(chunk, patterns)

        if pos == 0:
            # First chunk: take everything up to CHUNK_SIZE
            result_parts.append(redacted[:CHUNK_SIZE])
        elif end >= len(text):
            # Last chunk: take from overlap onwards
            result_parts.append(redacted[_OVERLAP:])
        else:
            # Middle chunk: take from overlap to CHUNK_SIZE
            result_parts.append(redacted[_OVERLAP : CHUNK_SIZE + _OVERLAP])

        pos += CHUNK_SIZE

    return "".join(result_parts)
