"""pnlclaw_security -- Policy, tool gating, redaction, approvals."""

# -- Tool policy (C01) --
# -- Audit (C06) --
from pnlclaw_security.audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditSeverity,
)

# -- Environment security (C03) --
from pnlclaw_security.env_security import (
    EnvSanitizationResult,
    is_dangerous_env_key,
    is_dangerous_override_key,
    is_secret_env_key,
    sanitize_env,
)

# -- Guardrails (C10-C12) --
from pnlclaw_security.guardrails.hallucination import (
    HallucinationDetector,
    PriceDeviationAlert,
)
from pnlclaw_security.guardrails.overtrading import (
    OvertradingAlert,
    OvertradingConfig,
    OvertradingDetector,
)
from pnlclaw_security.guardrails.regime_mismatch import (
    STRATEGY_REGIME_COMPAT,
    RegimeMismatchAlert,
    RegimeMismatchDetector,
)
from pnlclaw_security.pairing.challenge import ChallengeResult, PairingChallenge

# -- Pairing (C07-C09) --
from pnlclaw_security.pairing.store import PairingRequest, PairingStore
from pnlclaw_security.pairing.token import PairingToken, TokenStore

# -- Redaction (C02) --
from pnlclaw_security.redaction import mask_token, redact_text

# -- Sanitizer (C04) --
from pnlclaw_security.sanitizer import (
    detect_injection_markers,
    sanitize_for_prompt,
    strip_control_chars,
    wrap_untrusted,
)

# -- Secrets (C05) --
from pnlclaw_security.secrets import (
    ResolvedSecret,
    SecretManager,
    SecretRef,
    SecretResolutionError,
    SecretSource,
)
from pnlclaw_security.tool_policy import (
    TOOL_GROUPS,
    ToolPolicy,
    ToolPolicyEngine,
    expand_tool_groups,
    normalize_tool_name,
)

__all__ = [
    # Tool policy
    "TOOL_GROUPS",
    "ToolPolicy",
    "ToolPolicyEngine",
    "expand_tool_groups",
    "normalize_tool_name",
    # Redaction
    "mask_token",
    "redact_text",
    # Env security
    "EnvSanitizationResult",
    "is_dangerous_env_key",
    "is_dangerous_override_key",
    "is_secret_env_key",
    "sanitize_env",
    # Sanitizer
    "detect_injection_markers",
    "sanitize_for_prompt",
    "strip_control_chars",
    "wrap_untrusted",
    # Secrets
    "ResolvedSecret",
    "SecretManager",
    "SecretRef",
    "SecretResolutionError",
    "SecretSource",
    # Audit
    "AuditEvent",
    "AuditEventType",
    "AuditLogger",
    "AuditSeverity",
    # Pairing
    "ChallengeResult",
    "PairingChallenge",
    "PairingRequest",
    "PairingStore",
    "PairingToken",
    "TokenStore",
    # Guardrails
    "HallucinationDetector",
    "OvertradingAlert",
    "OvertradingConfig",
    "OvertradingDetector",
    "PriceDeviationAlert",
    "RegimeMismatchAlert",
    "RegimeMismatchDetector",
    "STRATEGY_REGIME_COMPAT",
]
