"""MCP configuration loading.

Reads MCP server definitions from the PnLClaw config file
(``~/.pnlclaw/config.yaml`` by default) and returns a validated
``McpConfig`` model.

Example YAML structure::

    mcp:
      servers:
        filesystem:
          command: npx
          args: ["-y", "@anthropic/mcp-server-filesystem"]
          transport: stdio
          risk_level: restricted
        remote:
          url: https://mcp.example.com/sse
          transport: sse
          enabled: false
"""

from __future__ import annotations

from pathlib import Path

from pnlclaw_agent.mcp.types import McpConfig, McpServerConfig


def load_mcp_config(config_path: Path | None = None) -> McpConfig:
    """Load MCP configuration from a YAML file.

    Reads the ``mcp`` section from the config file and parses each
    server entry into an ``McpServerConfig``.  Invalid entries are
    silently skipped so that one bad server definition does not prevent
    other servers from loading.

    Args:
        config_path: Explicit path to config file.
            Defaults to ``~/.pnlclaw/config.yaml``.

    Returns:
        Parsed ``McpConfig`` (empty if file is missing or unparseable).
    """
    if config_path is None:
        config_path = Path.home() / ".pnlclaw" / "config.yaml"

    if not config_path.is_file():
        return McpConfig()

    # Lazy import -- yaml is only needed when we actually read a config file
    try:
        import yaml
    except ImportError:
        return McpConfig()

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except Exception:
        return McpConfig()

    if not isinstance(data, dict):
        return McpConfig()

    mcp_data = data.get("mcp", {})
    if not isinstance(mcp_data, dict):
        return McpConfig()

    servers: dict[str, McpServerConfig] = {}
    raw_servers = mcp_data.get("servers", {})
    if isinstance(raw_servers, dict):
        for name, server_data in raw_servers.items():
            if isinstance(server_data, dict):
                try:
                    servers[name] = McpServerConfig(**server_data)
                except Exception:
                    pass  # Skip invalid server configs silently

    return McpConfig(servers=servers)
