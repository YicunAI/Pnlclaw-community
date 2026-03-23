# pnlclaw-ext-ollama

PnLClaw extension that registers a local Ollama LLM provider using `pnlclaw_llm.ollama.OllamaProvider`.

## Defaults

- Base URL: `http://localhost:11434` when `LLMConfig.base_url` is unset.

## Install

From the repository root (development):

```bash
pip install -e ./extensions/ollama
```

## Entry point

- `pnlclaw_ext_ollama.plugin:setup` — calls `register_llm_provider("ollama", OllamaExtensionProvider)`.
