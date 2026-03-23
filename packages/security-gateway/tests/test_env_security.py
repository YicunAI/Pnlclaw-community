"""Tests for pnlclaw_security.env_security."""

from pnlclaw_security.env_security import (
    is_dangerous_env_key,
    is_dangerous_override_key,
    is_secret_env_key,
    sanitize_env,
)

# ---------------------------------------------------------------------------
# is_dangerous_env_key
# ---------------------------------------------------------------------------


class TestIsDangerousEnvKey:
    def test_blocked_exact_keys(self) -> None:
        for key in ["NODE_OPTIONS", "PYTHONPATH", "BASH_ENV", "IFS", "SSLKEYLOGFILE"]:
            assert is_dangerous_env_key(key) is True, f"{key} should be blocked"

    def test_blocked_prefixes(self) -> None:
        assert is_dangerous_env_key("LD_PRELOAD") is True
        assert is_dangerous_env_key("LD_LIBRARY_PATH") is True
        assert is_dangerous_env_key("DYLD_INSERT_LIBRARIES") is True
        assert is_dangerous_env_key("BASH_FUNC_something") is True

    def test_case_insensitive(self) -> None:
        assert is_dangerous_env_key("pythonpath") is True
        assert is_dangerous_env_key("Bash_Env") is True

    def test_safe_keys(self) -> None:
        assert is_dangerous_env_key("PATH") is False
        assert is_dangerous_env_key("HOME") is False
        assert is_dangerous_env_key("LANG") is False
        assert is_dangerous_env_key("TZ") is False
        assert is_dangerous_env_key("TERM") is False

    def test_whitespace_stripped(self) -> None:
        assert is_dangerous_env_key("  PYTHONPATH  ") is True


# ---------------------------------------------------------------------------
# is_dangerous_override_key
# ---------------------------------------------------------------------------


class TestIsDangerousOverrideKey:
    def test_includes_base_dangerous(self) -> None:
        assert is_dangerous_override_key("PYTHONPATH") is True

    def test_override_specific_keys(self) -> None:
        assert is_dangerous_override_key("HOME") is True
        assert is_dangerous_override_key("GIT_SSH_COMMAND") is True
        assert is_dangerous_override_key("EDITOR") is True
        assert is_dangerous_override_key("VISUAL") is True
        assert is_dangerous_override_key("PROMPT_COMMAND") is True

    def test_override_prefixes(self) -> None:
        assert is_dangerous_override_key("GIT_CONFIG_GLOBAL") is True
        assert is_dangerous_override_key("NPM_CONFIG_REGISTRY") is True

    def test_safe_override(self) -> None:
        assert is_dangerous_override_key("MY_APP_CONFIG") is False


# ---------------------------------------------------------------------------
# is_secret_env_key
# ---------------------------------------------------------------------------


class TestIsSecretEnvKey:
    def test_known_secrets(self) -> None:
        assert is_secret_env_key("AWS_SECRET_ACCESS_KEY") is True
        assert is_secret_env_key("OPENAI_API_KEY") is True
        assert is_secret_env_key("ANTHROPIC_API_KEY") is True
        assert is_secret_env_key("BINANCE_API_SECRET") is True

    def test_generic_patterns(self) -> None:
        assert is_secret_env_key("MY_SERVICE_API_KEY") is True
        assert is_secret_env_key("DB_PASSWORD") is True
        assert is_secret_env_key("AUTH_ACCESS_TOKEN") is True
        assert is_secret_env_key("SIGNING_PRIVATE_KEY") is True

    def test_non_secret_keys(self) -> None:
        assert is_secret_env_key("PATH") is False
        assert is_secret_env_key("HOME") is False
        assert is_secret_env_key("PYTHONPATH") is False


# ---------------------------------------------------------------------------
# sanitize_env
# ---------------------------------------------------------------------------


class TestSanitizeEnv:
    def test_blocks_dangerous_keys(self) -> None:
        env = {"PATH": "/usr/bin", "LD_PRELOAD": "/evil.so", "HOME": "/home/user"}
        result = sanitize_env(env)
        assert "LD_PRELOAD" in result.blocked
        assert "PATH" in result.allowed
        assert "HOME" in result.allowed

    def test_blocks_override_keys(self) -> None:
        env = {"PATH": "/usr/bin"}
        overrides = {"HOME": "/tmp/evil", "MY_VAR": "ok"}
        result = sanitize_env(env, overrides=overrides)
        assert "HOME" in result.blocked
        assert result.allowed["MY_VAR"] == "ok"

    def test_detects_secrets(self) -> None:
        env = {"OPENAI_API_KEY": "sk-test123", "PATH": "/usr/bin"}
        result = sanitize_env(env)
        assert "OPENAI_API_KEY" in result.secrets_detected
        # Secrets pass through (needed for operation) but are flagged
        assert "OPENAI_API_KEY" in result.allowed

    def test_null_byte_rejection(self) -> None:
        env = {"SAFE_VAR": "normal", "BAD_VAR": "evil\x00payload"}
        result = sanitize_env(env)
        assert "BAD_VAR" in result.blocked
        assert "SAFE_VAR" in result.allowed

    def test_oversized_value_rejection(self) -> None:
        env = {"BIG_VAR": "x" * 40_000}
        result = sanitize_env(env)
        assert "BIG_VAR" in result.blocked

    def test_empty_env(self) -> None:
        result = sanitize_env({})
        assert result.allowed == {}
        assert result.blocked == []
