"""Tests for pnlclaw_security.redaction."""

from pnlclaw_security.redaction import (
    CHUNK_THRESHOLD,
    mask_token,
    redact_text,
)

# ---------------------------------------------------------------------------
# mask_token
# ---------------------------------------------------------------------------


class TestMaskToken:
    def test_short_token(self) -> None:
        assert mask_token("abc123") == "***"

    def test_exactly_threshold(self) -> None:
        token = "a" * 18
        assert mask_token(token) == "aaaaaa...aaaa"

    def test_long_token(self) -> None:
        token = "sk-abc123def456ghi789jkl012"
        result = mask_token(token)
        assert result.startswith("sk-abc")
        assert result.endswith("l012")
        assert "..." in result


# ---------------------------------------------------------------------------
# Provider-prefix patterns
# ---------------------------------------------------------------------------


class TestProviderPrefixes:
    def test_openai_sk_prefix(self) -> None:
        text = "My key is sk-abc123xyz456qrs789tuvw"
        result = redact_text(text)
        assert "sk-abc123xyz456qrs789tuvw" not in result
        assert "sk-abc" in result  # first 6 chars preserved

    def test_github_ghp(self) -> None:
        token = "ghp_" + "A" * 30
        text = f"token={token}"
        result = redact_text(text)
        assert token not in result

    def test_github_pat(self) -> None:
        token = "github_pat_" + "B" * 30
        text = f"Using {token} for auth"
        result = redact_text(text)
        assert token not in result

    def test_slack_xoxb(self) -> None:
        token = "xoxb-" + "1234567890-" * 3
        text = f"SLACK_TOKEN={token}"
        result = redact_text(text)
        assert token not in result

    def test_groq_gsk(self) -> None:
        token = "gsk_" + "X" * 30
        text = f"key: {token}"
        result = redact_text(text)
        assert token not in result

    def test_google_aiza(self) -> None:
        token = "AIza" + "Y" * 30
        text = f"GOOGLE_API_KEY={token}"
        result = redact_text(text)
        assert token not in result

    def test_perplexity(self) -> None:
        token = "pplx-" + "Z" * 20
        text = f"api_key={token}"
        result = redact_text(text)
        assert token not in result

    def test_npm_token(self) -> None:
        token = "npm_" + "N" * 20
        text = f"//registry/:_authToken={token}"
        result = redact_text(text)
        assert token not in result

    def test_aws_access_key(self) -> None:
        token = "AKIA" + "A" * 16
        text = f"AWS_ACCESS_KEY_ID={token}"
        result = redact_text(text)
        assert token not in result


# ---------------------------------------------------------------------------
# Structured patterns
# ---------------------------------------------------------------------------


class TestStructuredPatterns:
    def test_env_assignment(self) -> None:
        text = "OPENAI_API_KEY=sk-reallyreallylongsecretkey1234"
        result = redact_text(text)
        assert "sk-reallyreallylongsecretkey1234" not in result
        assert "OPENAI_API_KEY=" in result

    def test_json_field(self) -> None:
        text = '{"apiKey": "my-super-secret-api-key-value"}'
        result = redact_text(text)
        assert "my-super-secret-api-key-value" not in result

    def test_cli_flag(self) -> None:
        text = "--api-key sk-verylongsecretkeythatneedsredaction"
        result = redact_text(text)
        assert "sk-verylongsecretkeythatneedsredaction" not in result

    def test_bearer_header(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
        result = redact_text(text)
        assert "eyJhbGciOiJIUzI1NiJ9.payload.signature" not in result


# ---------------------------------------------------------------------------
# PEM blocks
# ---------------------------------------------------------------------------


class TestPEMBlock:
    def test_pem_private_key(self) -> None:
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn/ygWep4PAtGoSo0gI\n"
            "dummydata1234567890abcdefghijklmnopqrstuvwxyz\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = redact_text(pem)
        assert "-----BEGIN RSA PRIVATE KEY-----" in result
        assert "-----END RSA PRIVATE KEY-----" in result
        assert "MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn" not in result
        assert "...redacted..." in result


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


class TestJWT:
    def test_jwt_token(self) -> None:
        jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature_part_here"
        text = f"token: {jwt}"
        result = redact_text(text)
        assert jwt not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_string(self) -> None:
        assert redact_text("") == ""

    def test_no_secrets(self) -> None:
        text = "This is a normal log message with no secrets"
        assert redact_text(text) == text

    def test_safe_paths_not_redacted(self) -> None:
        text = "Loading file from /usr/local/share/data"
        assert redact_text(text) == text


# ---------------------------------------------------------------------------
# Chunked processing
# ---------------------------------------------------------------------------


class TestChunkedProcessing:
    def test_large_text_redacted(self) -> None:
        # Create text larger than CHUNK_THRESHOLD
        padding = "x" * (CHUNK_THRESHOLD + 1000)
        secret = "sk-" + "a" * 40
        text = padding + f" key={secret} " + padding
        result = redact_text(text)
        assert secret not in result

    def test_small_text_not_chunked(self) -> None:
        text = "short text with sk-abcdef123456789012345678"
        result = redact_text(text)
        assert "sk-abcdef123456789012345678" not in result
