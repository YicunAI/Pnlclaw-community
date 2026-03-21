# PnLClaw Community

**Local-first AI crypto quantitative trading platform.**

Real-time market data | Strategy drafting | Backtesting | Paper trading | Result explanation

> AGPL-3.0-only | Python 3.11+ | Community v0.1

---

## What is PnLClaw?

PnLClaw is a heavily refactored evolution of an OpenClaw-based runtime, redesigned for **crypto quantitative research, prediction market workflows, backtesting, and paper trading** instead of a generic high-privilege autonomous agent.

This repository is the **Community edition** (AGPLv3). Pro and HFT editions are separate.

## Community v0.1 Scope

- Real-time market data via native exchange WebSocket (not CCXT)
- AI-assisted strategy drafting and explanation
- Backtesting with performance metrics (Sharpe, MDD, win rate)
- Paper trading with simulated execution
- Risk controls and safety gates
- Local desktop app (Tauri + React)

**Not included in v0.1:** multi-tenant SaaS, cloud control plane, HFT engine, real-money trading by default.

## Project Structure

```text
PnLClaw/
├── apps/desktop/                  # Tauri 2 + React + shadcn/ui
├── services/local-api/            # FastAPI local entrypoint
├── packages/
│   ├── shared-types/              # Unified Pydantic data models
│   ├── core/                      # Config, logging, resilience, plugins
│   ├── security-gateway/          # Policy, tool gating, redaction
│   ├── exchange-sdk/              # Native exchange WebSocket adapters
│   ├── market-data/               # Market stream normalization, cache
│   ├── strategy-engine/           # Strategy configs, indicators, runtime
│   ├── backtest-engine/           # Backtesting engine
│   ├── paper-engine/              # Paper trading simulation
│   ├── risk-engine/               # Rule-based risk controls
│   ├── agent-runtime/             # AI strategy drafting workflows
│   ├── llm-adapter/               # LLM provider abstraction
│   ├── storage/                   # SQLite + Parquet persistence
│   └── openclaw-compat/           # Transition layer (temporary)
├── tests/                         # Integration & e2e tests
├── docs/                          # Documentation
└── scripts/                       # Build & dev scripts
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for desktop frontend)
- Rust toolchain (for Tauri desktop shell)

### Installation

```bash
# Clone
git clone <repo-url>
cd PnLClaw

# Python virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install all packages
pip install -e ".[dev]"
pip install -e packages/shared-types

# Copy environment config
cp .env.example .env
```

### Development Commands

```bash
# Start local API server
make dev                  # uvicorn on :8080 with hot reload

# Quality checks
make lint                 # ruff check .
make format               # ruff format + fix
make typecheck            # mypy packages/

# Testing
make test                 # pytest all packages
make test-cov             # pytest with coverage report

# Cleanup
make clean                # remove __pycache__, .egg-info, etc.
```

### Desktop App

```bash
cd apps/desktop
npm install
npm run dev               # Next.js dev server
# cargo tauri dev         # Tauri desktop window (when configured)
```

## Architecture

```
Desktop (Tauri) → Frontend (React) → Local API (FastAPI) → Packages
```

- **Frontend** talks only to `services/local-api`, never directly to packages
- **Packages** depend on `shared-types` for data models and `core` for infrastructure
- **Security-first**: all tool calls go through `security-gateway`
- **Exchange data**: native WebSocket, normalized to unified internal models

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop Shell | Tauri 2 |
| Frontend | React + TypeScript + Tailwind + shadcn/ui |
| Local API | FastAPI (Python) |
| Core Runtime | Python 3.11+ |
| Data Processing | pandas + numpy |
| Local Storage | SQLite (metadata) + Parquet (time series) |
| Exchange Adapters | Native WebSocket + httpx |
| LLM | OpenAI-compatible interface |
| Logging | structlog + JSON |
| Testing | pytest + pytest-asyncio |
| Types | Pydantic v2 |

## Security

PnLClaw is **not** a generic high-privilege agent. Core principles:

- Secrets never enter prompts or logs
- High-risk actions are gated by `security-gateway`
- Tools are policy-controlled (safe/restricted/dangerous)
- Paper trading before real execution
- Agent has no default shell/file/network authority

## License

GNU Affero General Public License v3.0 (AGPL-3.0-only)

See [LICENSE](LICENSE) for details.

## Status

Active early-stage development. Currently building the Community v0.1 engineering baseline.
