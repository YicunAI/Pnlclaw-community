# CLAUDE.md

## Project identity

This repository is **PnLClaw Community**, the AGPLv3 community edition of PnLClaw.

PnLClaw is a heavily refactored evolution of an OpenClaw-based runtime, redesigned for **crypto quantitative research, prediction market workflows, backtesting, and paper trading** instead of a generic high-privilege autonomous agent.

This repository is **not** the commercial Pro edition and **not** the HFT edition.

---

## Current product scope

The current target is **Community v0.1**.

Community v0.1 must focus on the smallest useful local-first workflow:

- real-time market data
- strategy drafting
- backtesting
- paper trading
- result explanation

Community v0.1 is intentionally limited in scope.  
Do **not** expand it into a cloud platform, multi-tenant SaaS, or HFT execution system.

---

## Hard constraints

These constraints are mandatory unless the user explicitly changes them.

### Language and stack

- **Python is the only main backend/runtime language**
- Do **not** introduce Go or Rust as a second main business stack
- Rust may be considered later only for isolated performance hotspots, not as a parallel system
- The frontend entrypoint is under `apps/desktop`
- The local backend/API entrypoint is under `services/local-api`

### Exchange/data policy

- Do **not** use CCXT as the primary market data path
- Use **native exchange WebSocket APIs**
- The project must support **L2 orderbook event models**
- Build a first-party `exchange-sdk` abstraction
- Normalize exchange data into unified internal event models

### Product boundaries

Community v0.1 does **not** include:

- multi-tenant SaaS
- cloud control plane
- hosted execution
- team collaboration
- HFT execution engine
- broad exchange coverage
- plugin marketplace
- default real-money automated trading

### Security boundaries

- Do **not** treat this project as a generic “do anything” agent
- High-risk capabilities must be gated
- Secrets must never enter prompts
- Secrets must never be written to normal logs
- Secrets must never be stored in normal frontend storage
- New high-risk logic must go through `security-gateway`
- Agent code must not gain default shell/file/network authority

---

## Architectural intent

The repository should evolve toward this structure:

```text
PnLClaw/
├─ apps/
│  └─ desktop/
├─ services/
│  └─ local-api/
├─ packages/
│  ├─ core/
│  ├─ openclaw-compat/
│  ├─ security-gateway/
│  ├─ shared-types/
│  ├─ exchange-sdk/
│  ├─ market-data/
│  ├─ strategy-engine/
│  ├─ backtest-engine/
│  ├─ paper-engine/
│  ├─ risk-engine/
│  ├─ agent-runtime/
│  ├─ llm-adapter/
│  └─ storage/
├─ docs/
├─ tests/
├─ scripts/
└─ ...
Module responsibilities
apps/desktop: desktop-facing UI

services/local-api: local FastAPI entrypoint and API composition layer

packages/core: shared config, constants, exceptions, logging, utilities

packages/openclaw-compat: temporary compatibility layer for retained OpenClaw logic

packages/security-gateway: policy, tool gating, redaction, approvals

packages/shared-types: unified internal event/data models

packages/exchange-sdk: native exchange WebSocket and related adapters

packages/market-data: market stream normalization, cache, event bus

packages/strategy-engine: strategy configs, validation, indicators, runtime

packages/backtest-engine: backtesting foundations

packages/paper-engine: paper trading state and execution simulation

packages/risk-engine: rule-based risk controls

packages/agent-runtime: strategy drafting and explanation workflows

packages/llm-adapter: LLM provider abstraction

packages/storage: local persistence

OpenClaw refactor rules
PnLClaw is inspired by / derived from OpenClaw ideas, but it should not remain a generic OpenClaw fork in architecture.

Required approach
Keep openclaw-compat as a transition layer

Do not put new core business logic into openclaw-compat

Gradually move PnLClaw logic into first-party packages

Prioritize security hardening before adding new product features

Refactor priority
Lock down unsafe default capabilities

Define unified internal models

Build native exchange-sdk skeleton

Build market-data layer

Build backtest-engine skeleton

Build paper-engine skeleton

Build risk-engine skeleton

Add agent strategy drafting on top of the safe tool layer

What to remove or restrict from generic agent behavior
Do not preserve unsafe default patterns such as:

unconstrained shell execution

unconstrained file writes

unconstrained external fetch

self-modifying persistent prompts/config

dynamic high-risk plugin behavior without policy gates

Working style for Claude
When working in this repository, follow this process:

Read the relevant docs first

Perform a short gap analysis

List the files you will create or modify

Implement the smallest correct unit

Avoid overbuilding

Summarize what changed and what remains

Do not jump straight into large uncontrolled edits.

Documents to consult
Read these docs when relevant:

docs/community-v0.1.md

docs/openclaw-refactor-v0.1.md

docs/architecture-spec.md

docs/security-baseline.md

docs/production-readiness.md

docs/product-matrix.md

If a task is about exchange data or unified event models, prioritize:

docs/community-v0.1.md

docs/architecture-spec.md

If a task is about OpenClaw migration or high-risk tool behavior, prioritize:

docs/openclaw-refactor-v0.1.md

docs/security-baseline.md

Coding instructions
General
Prefer clear, minimal, extensible code

Preserve module boundaries

Avoid premature optimization

Avoid introducing unnecessary frameworks

Keep comments concise and useful

Prefer typed Python

Prefer Pydantic models, dataclasses, Protocols, and ABCs where appropriate

Python
Target Python 3.11+

Keep business logic in Python

Use FastAPI for the local API layer

Use structured logging patterns

Keep code import paths clean and predictable

Frontend
apps/desktop is the current UI entrypoint

Do not let frontend directly own backend business logic

Frontend should talk to services/local-api

Prefer consistent naming under components/, not multiple overlapping UI directories

What Claude should not do
Do not:

add cloud SaaS features unless explicitly asked

add multi-tenant logic to Community v0.1

replace Python with Go/Rust for core logic

use CCXT as the main data layer

add real-money auto trading by default

move new logic into openclaw-compat

create large speculative abstractions with no immediate use

silently rename major directories without explaining the migration

produce broad architectural rewrites without first listing the affected files

Preferred implementation order
When the user asks what to build next, prefer this sequence:

root project files (README.md, pyproject.toml, .env.example, .gitignore)

packages/shared-types

packages/exchange-sdk

packages/market-data

packages/backtest-engine

packages/paper-engine

packages/risk-engine

services/local-api

packages/agent-runtime

frontend integration in apps/desktop

Task response format
For implementation tasks, respond in this format:

Brief understanding of the task

Files to create/modify

Minimal implementation

Notes about assumptions

Next recommended step

Keep outputs practical and execution-oriented.

Current status assumptions
Unless the user states otherwise, assume:

this repo is still in early bootstrap stage

docs exist but code skeleton is incomplete

apps/desktop exists as the current frontend entrypoint

the project is moving from planning into structured implementation

safety and architecture boundaries matter more than shipping flashy UI first

License and repository identity
This repository is the Community edition and should be treated as AGPLv3 project space.

Keep a clear separation between:

Community code in this repo

future Pro code

future HFT code

Do not accidentally design Community as if it already includes Pro/HFT responsibilities.