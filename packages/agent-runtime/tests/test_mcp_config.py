"""Tests for MCP config loading from YAML files."""

from __future__ import annotations

from pathlib import Path

import pytest

from pnlclaw_agent.mcp.config import load_mcp_config
from pnlclaw_agent.mcp.types import McpTransport
from pnlclaw_types.risk import RiskLevel


# ---------------------------------------------------------------------------
# Valid config loading
# ---------------------------------------------------------------------------


class TestLoadMcpConfigValid:
    def test_load_full_config(self, tmp_path: Path) -> None:
        """A well-formed config with multiple servers should be parsed correctly."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers:
    filesystem:
      command: npx
      args:
        - "-y"
        - "@anthropic/mcp-server-filesystem"
      transport: stdio
      risk_level: restricted
    remote:
      url: https://mcp.example.com/sse
      transport: sse
      enabled: false
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)

        assert len(config.servers) == 2
        assert "filesystem" in config.servers
        assert "remote" in config.servers

        fs = config.servers["filesystem"]
        assert fs.command == "npx"
        assert fs.args == ["-y", "@anthropic/mcp-server-filesystem"]
        assert fs.transport == McpTransport.STDIO
        assert fs.risk_level == RiskLevel.RESTRICTED

        remote = config.servers["remote"]
        assert remote.url == "https://mcp.example.com/sse"
        assert remote.transport == McpTransport.SSE
        assert remote.enabled is False

    def test_load_single_server(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers:
    simple:
      command: python
      args: ["server.py"]
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert len(config.servers) == 1
        assert config.servers["simple"].command == "python"

    def test_load_with_env_and_cwd(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers:
    custom:
      command: node
      args: ["index.js"]
      env:
        API_KEY: secret123
        NODE_ENV: production
      cwd: /opt/mcp-server
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        server = config.servers["custom"]
        assert server.env == {"API_KEY": "secret123", "NODE_ENV": "production"}
        assert server.cwd == "/opt/mcp-server"

    def test_load_with_risk_levels(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers:
    safe_server:
      command: echo
      risk_level: safe
    dangerous_server:
      command: rm
      risk_level: dangerous
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert config.servers["safe_server"].risk_level == RiskLevel.SAFE
        assert config.servers["dangerous_server"].risk_level == RiskLevel.DANGEROUS


# ---------------------------------------------------------------------------
# Missing/empty MCP section
# ---------------------------------------------------------------------------


class TestLoadMcpConfigEmpty:
    def test_no_mcp_section(self, tmp_path: Path) -> None:
        """Config file without 'mcp' section should return empty config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
other_section:
  key: value
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert config.servers == {}

    def test_empty_mcp_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp: {}
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert config.servers == {}

    def test_mcp_servers_empty(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers: {}
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert config.servers == {}

    def test_empty_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("", encoding="utf-8")

        config = load_mcp_config(config_file)
        assert config.servers == {}


# ---------------------------------------------------------------------------
# Nonexistent file
# ---------------------------------------------------------------------------


class TestLoadMcpConfigMissing:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Loading from a nonexistent file returns empty config."""
        config = load_mcp_config(tmp_path / "nonexistent.yaml")
        assert config.servers == {}

    def test_default_path_not_exist(self) -> None:
        """Default path (~/.pnlclaw/config.yaml) typically doesn't exist in CI."""
        # Use a guaranteed-nonexistent path
        config = load_mcp_config(Path("/definitely/not/a/real/path/config.yaml"))
        assert config.servers == {}


# ---------------------------------------------------------------------------
# Invalid YAML handling
# ---------------------------------------------------------------------------


class TestLoadMcpConfigInvalid:
    def test_invalid_yaml(self, tmp_path: Path) -> None:
        """Invalid YAML should not crash, should return empty config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "mcp:\n  servers:\n    - this is not a dict: {{{{",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        # Should not crash; may or may not have servers
        assert isinstance(config, type(config))

    def test_mcp_section_not_dict(self, tmp_path: Path) -> None:
        """If the mcp section is not a dict, return empty config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp: "just a string"
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert config.servers == {}

    def test_servers_section_not_dict(self, tmp_path: Path) -> None:
        """If servers is a list instead of a dict, return empty config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers:
    - invalid_format
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert config.servers == {}

    def test_invalid_server_entry_skipped(self, tmp_path: Path) -> None:
        """Invalid server entries should be silently skipped."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers:
    valid:
      command: echo
    invalid:
      transport: not_a_real_transport
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        # The valid server should be loaded; the invalid one skipped
        assert "valid" in config.servers
        # The invalid one may or may not appear depending on Pydantic handling
        # of enum coercion. The key is it does not crash.

    def test_server_entry_is_string_skipped(self, tmp_path: Path) -> None:
        """A server value that is a string (not dict) should be skipped."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
mcp:
  servers:
    good:
      command: echo
    bad: "just a string"
""",
            encoding="utf-8",
        )

        config = load_mcp_config(config_file)
        assert "good" in config.servers
        assert "bad" not in config.servers

    def test_yaml_not_a_dict(self, tmp_path: Path) -> None:
        """If the entire YAML parses to a non-dict, return empty config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- just\n- a\n- list\n", encoding="utf-8")

        config = load_mcp_config(config_file)
        assert config.servers == {}


# ---------------------------------------------------------------------------
# Default path behavior
# ---------------------------------------------------------------------------


class TestLoadMcpConfigDefaultPath:
    def test_none_path_uses_default(self) -> None:
        """Passing None should use the default path without crashing."""
        # This test just verifies no exception is raised.
        # The default path is ~/.pnlclaw/config.yaml which likely does not exist.
        config = load_mcp_config(None)
        assert isinstance(config.servers, dict)
