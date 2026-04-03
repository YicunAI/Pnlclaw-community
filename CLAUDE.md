# CLAUDE.md

## Project identity

This repository is **PnLClaw Pro**, the commercial multi-user edition.

PnLClaw is a production crypto quantitative trading platform covering **real-time market data, strategy research, backtesting, paper trading, live trading, prediction markets, and AI-assisted workflows**.

The repository contains both Pro-exclusive modules and Community-shared code. Files listed in `.pro-only` are stripped when syncing to the public Community repository.

### Edition map

| Edition | Status | Scope |
|---------|--------|-------|
| Community v0.1 | **Completed** | Local-first: market data, strategy drafting, backtesting, paper trading, result explanation |
| Pro v1.0 | **Current target** | Multi-user, OAuth/JWT auth, live trading, Polymarket, admin panel, production deployment |
| HFT | Not started | Low-latency execution engine (separate future effort) |

---

## Current product scope

The current target is **Pro v1.0** — a production multi-user platform deployed at `pnlclaw.com` serving 1000+ concurrent users.

Pro v1.0 includes everything from Community v0.1 plus:

- Multi-user OAuth/JWT/TOTP authentication (`packages/pro-auth`)
- PostgreSQL user storage (`packages/pro-storage`)
- Admin API and admin panel (`services/admin-api`, `apps/admin`)
- Live trading with Binance and OKX (`LiveExecutionEngine`)
- Polymarket CLOB prediction market integration
- Production CI/CD with GitHub Actions + systemd deployment
- Redis for shared K-line caching and WebSocket fan-out (in progress)

---

## Hard constraints

These constraints are mandatory unless the user explicitly changes them.

### Language and stack

- **Python is the only main backend/runtime language**
- Do **not** introduce Go or Rust as a second main business stack
- Rust may be considered later only for isolated performance hotspots
- The frontend entrypoint is under `apps/desktop`
- The local backend/API entrypoint is under `services/local-api`
- The admin API is under `services/admin-api`
- **Redis** is used for K-line caching and cross-worker WebSocket pub/sub

### Exchange/data policy

- Do **not** use CCXT as the primary market data path
- Use **native exchange WebSocket APIs**
- The project must support **L2 orderbook event models**
- Build a first-party `exchange-sdk` abstraction
- Normalize exchange data into unified internal event models
- Supported exchanges: **Binance** (spot + futures), **OKX** (spot + futures), **Polymarket** (CLOB)

### Security boundaries

- High-risk capabilities must be gated via `security-gateway`
- Secrets must never enter prompts, normal logs, or normal frontend storage
- Agent code must not gain default shell/file/network authority
- Live trading requires explicit `PNLCLAW_ENABLE_REAL_TRADING=true`
- Real-money operations require valid exchange API keys via secure keyring

---

## Architectural structure

```text
PnLClaw/
├─ apps/
│  ├─ desktop/                  # Next.js frontend (user-facing)
│  └─ admin/                    # Admin panel (Pro-only)
├─ services/
│  ├─ local-api/                # FastAPI main API (92 endpoints, 5 WS routes)
│  └─ admin-api/                # Admin/auth API (Pro-only)
├─ packages/
│  ├─ core/                     # Config, logging, diagnostics, resilience, plugins
│  ├─ shared-types/             # Pydantic models: market, trading, strategy, risk, agent
│  ├─ exchange-sdk/             # Binance/OKX/Polymarket WS + REST + trading adapters
│  ├─ market-data/              # Multi-source service, event bus, aggregators, cache
│  ├─ strategy-engine/          # YAML strategies, validation, indicators, runtime
│  ├─ backtest-engine/          # Event-driven backtesting, broker sim, metrics
│  ├─ paper-engine/             # Paper trading engine, accounts, orders, PnL
│  ├─ risk-engine/              # Rule-based pre-trade risk checks, kill switch
│  ├─ agent-runtime/            # AI runtime, tools, MCP, skills, context management
│  ├─ llm-adapter/              # OpenAI-compatible + Ollama + router
│  ├─ security-gateway/         # Policy engine, secrets, redaction, guardrails
│  ├─ storage/                  # SQLite persistence, migrations, repositories
│  ├─ pro-storage/              # PostgreSQL user storage (Pro-only)
│  ├─ pro-auth/                 # OAuth/JWT/TOTP auth (Pro-only)
│  └─ openclaw-compat/          # Transition stub (intentionally minimal)
├─ docs/
├─ tests/
├─ scripts/
└─ .github/workflows/           # CI + production deploy
```

### Module status

All packages are **functional with tests**. This is a production codebase, not a skeleton.

---

## Performance requirements (exchange-level)

The frontend must deliver exchange-level responsiveness:

| Metric | Target |
|--------|--------|
| K-line first render (warm cache) | < 200ms |
| K-line first render (cold) | < 500ms |
| Module switch (hot return) | < 80ms |
| Page refresh with IndexedDB cache | < 100ms |
| WebSocket subscription restore | 0 reconnections |
| Chart interval switch | No canvas destroy/recreate |
| Orderbook/ticker update rate | 10-20 FPS (50ms batched) |

### Key performance principles

- **UI never waits for data** — show cached/old data immediately, replace when fresh data arrives
- **Chart instance is a singleton** — never destroy/recreate on interval or symbol change
- **WebSocket connections are persistent** — page navigation does not disconnect
- **High-frequency data is batched** — requestAnimationFrame or 50ms throttle before setState
- **Redis caches K-line data** — 1000 users requesting BTC/USDT = 1 exchange call + 999 Redis hits

---

## Working style for Claude

When working in this repository, follow this process:

1. Read relevant source files first
2. Perform a short gap analysis
3. List the files you will create or modify
4. Implement the smallest correct unit
5. Run lints and verify no regressions
6. Summarize what changed and what remains

Do not jump straight into large uncontrolled edits.

### Coding instructions

**General:**
- Prefer clear, minimal, extensible code
- Preserve module boundaries
- Keep comments concise — explain *why*, not *what*
- Prefer typed Python (Pydantic, dataclasses, Protocols, ABCs)

**Python:**
- Target Python 3.11+
- Use FastAPI for the API layer
- Use structured logging (structlog)
- Use `httpx.AsyncClient` with connection pooling (not per-request)
- Use `redis.asyncio` for Redis operations

**Frontend:**
- `apps/desktop` is the user-facing UI (Next.js)
- Frontend talks to `services/local-api`, never owns backend business logic
- Chart components must be imperative (ref-based), not declarative (props-driven)
- High-frequency WS data must not directly trigger React re-renders
- Use IndexedDB for persistent K-line caching

### What Claude should not do

- Replace Python with Go/Rust for core logic
- Use CCXT as the main data layer
- Add real-money auto trading without explicit `PNLCLAW_ENABLE_REAL_TRADING`
- Move new logic into `openclaw-compat`
- Create large speculative abstractions with no immediate use
- Silently rename major directories without explaining the migration
- Produce broad architectural rewrites without first listing affected files
- Destroy and recreate chart instances on interval/symbol change

### Task response format

For implementation tasks, respond in this format:

1. Brief understanding of the task
2. Files to create/modify
3. Minimal implementation
4. Notes about assumptions
5. Next recommended step

Keep outputs practical and execution-oriented.

---

## Current status

- **Deployment**: Production at `pnlclaw.com`, systemd services (`pnlclaw-api`, `pnlclaw-web`)
- **Users**: 1000+ concurrent target
- **Auth**: OAuth/JWT/TOTP via `packages/pro-auth`
- **Database**: SQLite (strategies/backtests/paper) + PostgreSQL (users/auth)
- **Caching**: Redis (K-line cache, WS pub/sub — in progress)
- **Exchanges**: Binance spot+futures, OKX spot+futures, Polymarket CLOB
- **CI/CD**: GitHub Actions → SSH deploy → systemd restart

### Active optimization focus

K-line data loading performance is the current priority:
- Backend: Redis K-line cache, httpx connection pooling, startup warmup
- Frontend: chart singleton, IndexedDB cache, WS kline_snapshot, RAF batching
- Infrastructure: GZip compression, multi-worker deployment, Redis pub/sub

---

## License

Pro-exclusive code (`packages/pro-storage`, `packages/pro-auth`, `services/admin-api`, `apps/admin`) is proprietary.

Community-shared code is AGPLv3. The `.pro-only` file lists paths excluded from community sync.
