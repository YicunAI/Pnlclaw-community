# Legal Notice

## Project Identity

**PnLClaw Community** is an independently developed, local-first crypto
quantitative research and paper-trading platform. It is licensed under the
**GNU Affero General Public License v3.0** (AGPL-3.0-only).

## Relationship to OpenClaw

PnLClaw is **not** a fork, mirror, or redistribution of the OpenClaw codebase.

PnLClaw uses OpenClaw's publicly available source code as a **design
reference** — a process we call "distillation". This means:

- We studied OpenClaw's architecture, patterns, and design decisions.
- We re-implemented equivalent functionality in Python from scratch.
- No OpenClaw source code was copied verbatim into this repository.
- All code in this repository is original work by the PnLClaw contributors.

### Distillation Scope

The following subsystems were informed by OpenClaw's design (see
`docs/DEVELOPMENT_PLAN.md` Section 8 for the full traceability table):

| PnLClaw Subsystem | OpenClaw Design Reference |
|---|---|
| `packages/core/resilience/` | Retry, backoff, circuit-breaker patterns |
| `packages/core/infra/` | Debounce, deduplication, keyed queue, file lock |
| `packages/core/plugin_sdk/` | Plugin discovery and loading |
| `packages/core/hooks/` | Internal hook system |
| `packages/core/scheduler/` | Cron scheduling |
| `packages/security-gateway/pairing/` | Device pairing flow |
| `packages/security-gateway/` | Tool policy, redaction, sanitization |
| `packages/agent-runtime/context/` | Context pruning, compaction, budget |
| `packages/agent-runtime/cost/` | Token usage tracking |
| `packages/storage/migrations.py` | Migration framework pattern |

### What Was NOT Distilled

The following are **original to PnLClaw** with no OpenClaw equivalent:

- Exchange SDK with native WebSocket L2 orderbook support
- Strategy engine with YAML-defined strategies and indicator registry
- Backtest engine with golden-file regression testing
- Paper-trading engine with decision pipeline
- Risk engine with quantitative trading rules
- Market state analysis engine
- PnL attribution engine
- Trading memory and user preferences
- All Pydantic data models in `shared-types`

## Trademarks

"PnLClaw" is the project name used by its contributors. It is not affiliated
with, endorsed by, or sponsored by OpenClaw or its maintainers.

"OpenClaw" is a trademark of its respective owners. Use of the name in this
document is solely for the purpose of accurate attribution.

## Third-Party Dependencies

All third-party dependencies used by PnLClaw are open-source libraries
distributed under their own licenses. A full list of dependencies and their
licenses can be found in the respective `pyproject.toml` files under each
package directory.

Key dependencies include:

- **Pydantic** (MIT) — data validation
- **FastAPI** (MIT) — web framework
- **pandas** (BSD-3) — data processing
- **numpy** (BSD-3) — numerical computing
- **structlog** (Apache-2.0 OR MIT) — structured logging
- **aiosqlite** (MIT) — async SQLite
- **httpx** (BSD-3) — HTTP client
- **websockets** (BSD-3) — WebSocket client

## Contributor License

By contributing to this repository, you agree that your contributions are
licensed under the AGPL-3.0-only license, consistent with the project's
`LICENSE` file.
