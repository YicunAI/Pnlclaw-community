"""PnLClaw Local API — FastAPI entrypoint with lifespan management."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.agent import router as agent_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.chat_sessions import router as chat_sessions_router
from app.api.v1.derivatives import router as derivatives_router
from app.api.v1.health import router as health_router
from app.api.v1.markets import router as markets_router
from app.api.v1.mcp import router as mcp_router
from app.api.v1.paper import router as paper_router
from app.api.v1.polymarket import router as polymarket_router
from app.api.v1.settings import router as settings_router
from app.api.v1.skills_api import router as skills_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.trading import router as trading_router
from app.api.v1.ws import router as ws_router
from app.core.dependencies import (
    set_agent_runtime,
    set_db_manager,
    set_execution_engine,
    set_execution_mode,
    set_funding_rate_fetcher,
    set_health_registry,
    set_jwt_manager,
    set_key_pair_manager,
    set_market_service,
    set_mcp_registry,
    set_paper_managers,
    set_risk_engine,
    set_settings_service,
    set_skill_registry,
    set_strategy_repo,
    set_strategy_runner,
    set_tool_catalog,
)
from app.middleware.error_handler import install_error_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from pnlclaw_core.diagnostics.health import HealthCheckResult, HealthRegistry

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger(__name__)

_kline_flush_task: asyncio.Task | None = None


async def _seed_template_strategies(
    strategies: dict,
    repo: object,
) -> None:
    """Seed template strategies from YAML files if not already in store."""
    import pathlib

    try:
        import yaml
    except ImportError:
        try:
            from pnlclaw_strategy.models import EngineStrategyConfig  # noqa: F401,F811
        except ImportError:
            return
        # PyYAML not available — skip seeding
        logger.debug("PyYAML not installed, skipping template seeding")
        return

    from pnlclaw_types.strategy import StrategyConfig

    templates_dir = (
        pathlib.Path(__file__).resolve().parents[3] / "packages" / "strategy-engine" / "pnlclaw_strategy" / "templates"
    )
    if not templates_dir.is_dir():
        logger.debug("Templates directory not found: %s", templates_dir)
        return

    seeded = 0
    for yaml_path in sorted(templates_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if not raw or not isinstance(raw, dict):
                continue
            template_id = raw.get("id", f"template-{yaml_path.stem}")
            if template_id in strategies:
                continue

            config = StrategyConfig(
                id=template_id,
                name=raw.get("name", yaml_path.stem),
                type=raw.get("type", "custom"),
                description=raw.get("description", ""),
                symbols=raw.get("symbols", ["BTC/USDT"]),
                interval=raw.get("interval", "1h"),
                parameters=raw.get("parameters", {}),
                entry_rules=raw.get("entry_rules", {}),
                exit_rules=raw.get("exit_rules", {}),
                risk_params=raw.get("risk_params", {}),
                tags=raw.get("tags", ["template"]),
                source="template",
            )
            strategies[template_id] = config
            if repo is not None and hasattr(repo, "save"):
                await repo.save(config)
            seeded += 1
        except Exception:
            logger.debug("Failed to seed template %s", yaml_path.name, exc_info=True)

    if seeded:
        logger.info("Seeded %d template strategies from YAML files", seeded)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks."""
    from app.core.crypto import KeyPairManager
    from app.core.redis import close_redis, init_redis
    from app.core.settings_service import SettingsService
    from pnlclaw_market import BinanceSource, MarketDataService, OKXSource
    from pnlclaw_security.secrets import SecretManager

    # --- Redis (shared K-line cache + WS pub/sub) ---
    await init_redis()

    # --- JWT (Pro mode: verify tokens from admin-api) ---
    jwt_secret = os.environ.get("PNLCLAW_AUTH_JWT_SECRET", "")
    if jwt_secret:
        try:
            from pnlclaw_pro_auth.jwt_manager import JWTManager

            jwt_mgr = JWTManager(secret_key=jwt_secret)
            set_jwt_manager(jwt_mgr)
            logger.info("JWT auth enabled — local-api will verify admin-api tokens")
        except ImportError:
            logger.info("pnlclaw_pro_auth not available, JWT auth disabled")
    else:
        bind_host = os.environ.get("UVICORN_HOST", os.environ.get("HOST", "127.0.0.1"))
        if bind_host in ("0.0.0.0", "::"):
            logger.critical(
                "FATAL: Community (no-auth) mode on public interface %s is unsafe! "
                "Set PNLCLAW_AUTH_JWT_SECRET or bind to 127.0.0.1.",
                bind_host,
            )
            raise RuntimeError(
                "Refusing to start in Community (no-auth) mode on a public interface. "
                "Either set PNLCLAW_AUTH_JWT_SECRET for Pro mode, or bind to 127.0.0.1."
            )
        logger.info("PNLCLAW_AUTH_JWT_SECRET not set, running in Community (no-auth) mode")

    # --- Health ---
    async def _local_api_health() -> HealthCheckResult:
        return HealthCheckResult(name="local_api", status="healthy", latency_ms=0.0)

    key_pair_manager = KeyPairManager()
    set_key_pair_manager(key_pair_manager)

    settings_service = SettingsService(
        secret_manager=SecretManager(),
        key_pair_manager=key_pair_manager,
    )
    set_settings_service(settings_service)

    registry = HealthRegistry()
    registry.register_check("local_api", _local_api_health)
    set_health_registry(registry)

    # --- Storage (SQLite) ---
    db_manager = None
    strategy_repo = None
    try:
        from pnlclaw_storage import (
            ALL_MIGRATIONS,
            AsyncSQLiteManager,
            MigrationRunner,
            StrategyRepository,
        )

        migration_runner = MigrationRunner(ALL_MIGRATIONS)
        db_manager = AsyncSQLiteManager(migration_runner=migration_runner)
        await db_manager.connect()
        set_db_manager(db_manager)

        strategy_repo = StrategyRepository(db_manager)
        set_strategy_repo(strategy_repo)

        from app.core.dependencies import set_chat_session_repo
        from pnlclaw_storage.repositories.chat_sessions import ChatSessionRepository

        chat_session_repo = ChatSessionRepository(db_manager)
        set_chat_session_repo(chat_session_repo)

        from app.core.audit import set_audit_repo
        from pnlclaw_storage.repositories.audit_logs import AuditLogRepository

        audit_repo = AuditLogRepository(db_manager)
        set_audit_repo(audit_repo)

        # Pre-load persisted strategies into in-memory store used by routes
        from app.api.v1.strategies import _strategies

        saved = await strategy_repo.list(limit=1000)
        for s in saved:
            _strategies[s.id] = s
        logger.info("Storage initialized, loaded %d persisted strategies", len(saved))

        # FX02: Seed template strategies from YAML files if not already present
        await _seed_template_strategies(_strategies, strategy_repo)
    except ImportError:
        logger.info("pnlclaw_storage not installed, using in-memory strategy store")
    except Exception:
        logger.warning("Failed to initialize storage", exc_info=True)

    # --- Market Data Service (multi-source) ---
    # Multi-interval: PNLCLAW_KLINE_INTERVALS takes priority over PNLCLAW_DEFAULT_INTERVAL
    _intervals_raw = os.environ.get("PNLCLAW_KLINE_INTERVALS") or os.environ.get("PNLCLAW_DEFAULT_INTERVAL") or "1m,5m,15m,30m,1h,4h,1d"
    kline_intervals = [i.strip() for i in _intervals_raw.split(",") if i.strip()]
    if not kline_intervals:
        kline_intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
    default_interval = kline_intervals[0]
    logger.info("Kline intervals: %s (primary: %s)", kline_intervals, default_interval)

    # Proxy priority: env var > persisted setting > Windows registry auto-detect
    saved_settings = settings_service._load_non_sensitive()
    saved_proxy = saved_settings.get("network", {}).get("proxy_url", "")
    proxy_url = (
        os.environ.get("PNLCLAW_PROXY_URL") or os.environ.get("https_proxy") or (saved_proxy if saved_proxy else None)
    )
    if not proxy_url:
        from pnlclaw_exchange.exchanges.polymarket.client import detect_local_proxy

        proxy_url = detect_local_proxy()
    if proxy_url:
        logger.info("Using WebSocket proxy: %s", proxy_url)

    market_svc = MarketDataService()

    # Binance USDT-M Futures
    market_svc.register_source(
        BinanceSource(
            market_type="futures",
            ws_url=os.environ.get("PNLCLAW_BINANCE_FUTURES_WS_URL", None),
            rest_url=os.environ.get("PNLCLAW_BINANCE_FUTURES_REST_URL", None),
            proxy_url=proxy_url,
            kline_intervals=kline_intervals,
        )
    )

    # OKX Futures (Perpetual Swap)
    market_svc.register_source(
        OKXSource(
            market_type="futures",
            proxy_url=proxy_url,
            kline_intervals=kline_intervals,
        )
    )

    # --- Funding Rate Fetcher (bulk REST, all exchanges) ---
    from pnlclaw_market.funding_rate_fetcher import FundingRateFetcher

    funding_fetcher = FundingRateFetcher(proxy_url=proxy_url)
    set_funding_rate_fetcher(funding_fetcher)

    try:
        await market_svc.start()
        set_market_service(market_svc)

        # Bridge EventBus → WS broadcast so that incoming exchange events
        # are pushed to connected WebSocket clients in real time.
        _bridge_market_events(market_svc)

        # Start Redis Pub/Sub subscriber only in multi-worker mode
        if os.environ.get("PNLCLAW_WS_PUBSUB_ENABLED", "").lower() in ("1", "true"):
            from app.core.redis_pubsub import start_subscriber as _start_pubsub

            async def _pubsub_forward(channel: str, data: dict) -> None:
                from app.api.v1.ws import _market_manager
                await _market_manager.broadcast(channel, data)

            await _start_pubsub(_pubsub_forward)
            logger.info("Redis Pub/Sub enabled for multi-worker broadcasting")
        else:
            logger.info("Redis Pub/Sub disabled (single-worker mode)")

        # Subscribe default symbols on ALL sources so large-trade and
        # liquidation monitors see data from every exchange.
        default_symbols = os.environ.get("PNLCLAW_DEFAULT_SYMBOLS") or "BTC/USDT,ETH/USDT"
        if default_symbols:
            all_sources: list[tuple[str, str]] = [
                ("binance", "futures"),
                ("okx", "futures"),
            ]
            for sym in default_symbols.split(","):
                sym = sym.strip()
                if not sym:
                    continue
                for ex, mt in all_sources:
                    try:
                        await market_svc.add_symbol(sym, exchange=ex, market_type=mt)
                        logger.info("Subscribed %s on %s/%s", sym, ex, mt)
                    except Exception:
                        logger.warning(
                            "Failed to subscribe %s on %s/%s (may be unreachable)",
                            sym,
                            ex,
                            mt,
                            exc_info=True,
                        )
                    await asyncio.sleep(0.3)

        # --- K-line warmup: pre-fetch common symbols x intervals into Redis ---
        from app.core.redis import get_redis

        _warmup_redis = get_redis()
        if _warmup_redis is not None:
            from pnlclaw_market.kline_store import KlineStore

            _warmup_store = KlineStore(_warmup_redis)
            _warmup_intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
            _warmup_symbols_str = os.environ.get("PNLCLAW_DEFAULT_SYMBOLS") or "BTC/USDT,ETH/USDT"
            _warmup_symbols = [s.strip() for s in _warmup_symbols_str.split(",") if s.strip()]

            async def _warmup_task() -> None:
                """Background task: pre-fetch K-lines for default symbols.

                Fetches high-priority intervals first (1h, 30m, 15m, 4h)
                then fills remaining. Short delays between requests to avoid
                hammering exchanges while still completing quickly.
                """
                await asyncio.sleep(3)
                _priority_intervals = ["1h", "30m", "15m", "4h", "1m", "5m", "1d"]
                for sym in _warmup_symbols:
                    for ivl in _priority_intervals:
                        for ex, mt in [("binance", "futures"), ("okx", "futures")]:
                            try:
                                existing = await _warmup_store.count(ex, mt, sym, ivl)
                                if existing >= 100:
                                    continue
                                klines = await market_svc.fetch_klines_rest(sym, ex, mt, interval=ivl, limit=500)
                                if klines:
                                    await _warmup_store.put(ex, mt, sym, ivl, klines)
                                    logger.info("Warmup: cached %d klines %s/%s %s %s", len(klines), ex, mt, sym, ivl)
                                await asyncio.sleep(0.3)
                            except Exception:
                                logger.debug("Warmup skip %s/%s %s %s", ex, mt, sym, ivl, exc_info=True)
                logger.info("K-line warmup completed")

            asyncio.create_task(_warmup_task(), name="kline-warmup")
        else:
            logger.info("Redis not available, skipping K-line warmup")

        # Register market health check
        async def _market_health() -> HealthCheckResult:
            running = market_svc.is_running
            source_status = {}
            for (ex, mt), src in market_svc.sources.items():
                source_status[f"{ex}/{mt}"] = {
                    "running": src.is_running,
                    "symbols": len(src.get_symbols()),
                }
            return HealthCheckResult(
                name="market_data",
                status="healthy" if running else "degraded",
                latency_ms=0.0,
                detail={"running": running, "sources": source_status},
            )

        registry.register_check("market_data", _market_health)

        # FX15: Pre-initialize variables to avoid UnboundLocalError in finally
        paper_engine = None  # type: ignore[assignment]
        paper_state = None  # type: ignore[assignment]
        _autosave_task = None  # type: ignore[assignment]
        strategy_runner_instance = None  # type: ignore[assignment]
        mcp_registry_instance = None  # type: ignore[assignment]
        agent_runtime_instance = None  # type: ignore[assignment]

        # --- Execution Engine (Paper by default) ---
        from pnlclaw_paper.paper_execution import PaperExecutionEngine

        paper_engine = PaperExecutionEngine(
            initial_balance=float(os.environ.get("PNLCLAW_PAPER_BALANCE", "100000")),
        )

        from pnlclaw_paper.state import PaperState

        paper_state = PaperState()
        try:
            fills, _meta = paper_state.load_state(
                paper_engine._account_mgr,
                paper_engine._order_mgr,
                paper_engine._position_mgr,
            )
            if fills:
                paper_engine._fills = fills
                logger.info("Restored %d fills from paper state", len(fills))
        except Exception:
            logger.warning("Failed to load paper state, starting fresh", exc_info=True)

        await paper_engine.start()
        set_execution_engine(paper_engine)
        set_execution_mode("paper")

        # Unify paper managers so /paper REST and /trading WS share the same state
        set_paper_managers(
            paper_engine._account_mgr,
            paper_engine._order_mgr,
            paper_engine._position_mgr,
        )

        # Auto-save paper state periodically
        async def _paper_autosave() -> None:
            while True:
                await asyncio.sleep(60)
                try:
                    paper_state.save_state(
                        paper_engine._account_mgr,
                        paper_engine._order_mgr,
                        paper_engine._position_mgr,
                        fills=paper_engine._fills,
                    )
                except Exception:
                    logger.debug("Paper state autosave failed", exc_info=True)

        _autosave_task = asyncio.create_task(_paper_autosave(), name="paper-autosave")

        # Bridge price ticks from MarketDataService to PaperExecutionEngine
        _bridge_price_to_paper(market_svc, paper_engine)

        _bridge_paper_engine_events(paper_engine)

        # --- Strategy Runner (continuous strategy execution) ---
        strategy_runner_instance = None
        try:
            from app.core.strategy_runner import StrategyRunner as _SR

            strategy_runner_instance = _SR(
                paper_engine=paper_engine,
                market_service=market_svc,
            )
            await strategy_runner_instance.start()
            set_strategy_runner(strategy_runner_instance)
            logger.info(
                "Strategy runner started with %d restored deployments",
                len(strategy_runner_instance.active_deployments),
            )
        except Exception:
            logger.warning("Failed to initialize strategy runner", exc_info=True)

        # --- Live Execution Engine (Real Trading) ---
        from app.core.dependencies import set_live_engine

        try:
            exchange_provider = saved_settings.get("exchange", {}).get("provider", "binance")

            from pnlclaw_security.secrets import SecretManager, SecretRef, SecretSource

            sm = SecretManager()
            api_key_ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.exchange", id="api_key")
            api_secret_ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.exchange", id="api_secret")
            passphrase_ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw.exchange", id="passphrase")

            api_key = ""
            api_secret = ""
            passphrase = ""
            try:
                if await sm.exists(api_key_ref):
                    api_key = (await sm.resolve(api_key_ref)).use()
                if await sm.exists(api_secret_ref):
                    api_secret = (await sm.resolve(api_secret_ref)).use()
                if await sm.exists(passphrase_ref):
                    passphrase = (await sm.resolve(passphrase_ref)).use()
            except Exception as e:
                logger.warning("Failed to resolve exchange secrets: %s", e)

            if api_key and api_secret:
                from pydantic import SecretStr

                from pnlclaw_exchange.base.auth import ExchangeCredentials

                creds = ExchangeCredentials(
                    api_key=SecretStr(api_key),
                    api_secret=SecretStr(api_secret),
                    passphrase=SecretStr(passphrase) if passphrase else None,
                )

                client = None
                if exchange_provider == "binance":
                    from pnlclaw_exchange.exchanges.binance.rest_client import BinanceRESTClient
                    from pnlclaw_exchange.trading import BinanceTradingAdapter

                    bc = BinanceRESTClient(credentials=creds, testnet=False)
                    client = BinanceTradingAdapter(bc)
                elif exchange_provider == "okx":
                    from pnlclaw_exchange.exchanges.okx.rest_client import OKXRESTClient
                    from pnlclaw_exchange.trading import OKXTradingAdapter

                    oc = OKXRESTClient(credentials=creds, demo=False)
                    client = OKXTradingAdapter(oc)

                if client is not None:
                    from pnlclaw_exchange.execution.live_engine import LiveExecutionEngine

                    live_engine_instance = LiveExecutionEngine(client=client, reconciliation_interval_s=60.0)
                    set_live_engine(live_engine_instance)
                    asyncio.create_task(live_engine_instance.start())
                    _bridge_execution_events(live_engine_instance)
                    logger.info("Live execution engine initialized with %s adapter", exchange_provider)
        except Exception:
            logger.error("Failed to initialize live execution engine", exc_info=True)

        # --- Risk Engine ---
        risk_engine_instance = None
        try:
            from pnlclaw_risk.engine import RiskEngine
            from pnlclaw_risk.rules import create_default_rules

            risk_rules = create_default_rules()

            # Apply risk params from saved settings if available
            risk_settings = saved_settings.get("risk", {})
            if risk_settings:
                for rule in risk_rules:
                    rid = rule.rule_id
                    if rid == "max_position" and risk_settings.get("max_position_pct"):
                        rule._max_pct = float(risk_settings["max_position_pct"])
                    elif rid == "max_single_risk" and risk_settings.get("single_risk_pct"):
                        rule._max_pct = float(risk_settings["single_risk_pct"])
                    elif rid == "daily_loss_limit" and risk_settings.get("daily_loss_limit_pct"):
                        rule._max_pct = float(risk_settings["daily_loss_limit_pct"])
                    elif rid == "cooldown" and risk_settings.get("cooldown_seconds"):
                        rule._cooldown = float(risk_settings["cooldown_seconds"])

            risk_engine_instance = RiskEngine(rules=risk_rules)
            set_risk_engine(risk_engine_instance)
            logger.info("Risk engine initialized with %d rules", len(risk_rules))
        except ImportError:
            logger.info("pnlclaw_risk not installed, risk engine disabled")
        except Exception:
            logger.warning("Failed to initialize risk engine", exc_info=True)

        logger.info("PnLClaw Local API started with multi-source MarketDataService + PaperExecutionEngine")

        # --- Skills Registry ---
        skill_registry_instance = None
        try:
            from pnlclaw_agent.skills import SkillRegistry, SkillsConfig

            skill_registry_instance = SkillRegistry(config=SkillsConfig())
            skill_registry_instance.load()
            set_skill_registry(skill_registry_instance)
            skill_count = len(skill_registry_instance.list_skills())
            logger.info("Skills registry loaded with %d skills", skill_count)
        except Exception:
            logger.warning("Failed to initialize Skills registry", exc_info=True)

        # FX09: Create a single ToolCatalog shared by MCP and Agent
        from pnlclaw_agent import ToolCatalog as _TC

        try:
            from pnlclaw_security.tool_policy import ToolPolicyEngine

            _policy_engine = ToolPolicyEngine()
            logger.info("ToolPolicyEngine loaded — tool gating active")
        except Exception:
            _policy_engine = None
            logger.warning("ToolPolicyEngine not available — all tools allowed")

        tool_catalog = _TC(policy_engine=_policy_engine)

        # --- MCP Registry (uses the shared tool_catalog) ---
        try:
            from pnlclaw_agent.mcp import McpRegistry
            from pnlclaw_agent.mcp.config import load_mcp_config

            mcp_config = load_mcp_config()
            if mcp_config.servers:
                mcp_registry_instance = McpRegistry()
                await mcp_registry_instance.start(mcp_config, tool_catalog)
                set_mcp_registry(mcp_registry_instance)
                logger.info(
                    "MCP registry started with %d servers",
                    len(mcp_registry_instance.list_servers()),
                )
            else:
                logger.info("No MCP servers configured, skipping MCP initialization")
        except ImportError:
            logger.info("MCP SDK not installed, MCP support disabled")
        except Exception:
            logger.warning("Failed to initialize MCP registry", exc_info=True)

        # --- Component Registry (Open Core architecture) ---
        from pnlclaw_agent.implementations import (
            BasicContextManager as BasicCtxMgr,
        )
        from pnlclaw_agent.implementations import (
            FixedModelRouter,
            KeywordMemoryBackend,
            RuleBasedFeedback,
            SingleAgentRunner,
        )
        from pnlclaw_agent.registry import ComponentRegistry

        component_registry = ComponentRegistry()
        component_registry.register("memory", KeywordMemoryBackend())
        component_registry.register("orchestrator", SingleAgentRunner())
        component_registry.register("model_router", FixedModelRouter())
        component_registry.register("context_engine", BasicCtxMgr())
        component_registry.register("feedback_engine", RuleBasedFeedback())
        logger.info(
            "Component registry initialized: %s",
            list(component_registry.list_registered().keys()),
        )

        # --- Register agent tools into the shared catalog ---
        _register_agent_tools(
            tool_catalog,
            market_service=market_svc,
            account_manager=paper_engine._account_mgr,
            order_manager=paper_engine._order_mgr,
            position_manager=paper_engine._position_mgr,
            risk_engine=risk_engine_instance,
        )
        set_tool_catalog(tool_catalog)
        logger.info("Tool catalog initialized with %d tools: %s", len(tool_catalog), tool_catalog.tool_names())

        # --- Agent Runtime (wired to saved LLM settings) ---
        try:
            agent_runtime_instance = await _build_agent_runtime(settings_service, tool_catalog)
            if agent_runtime_instance is not None:
                set_agent_runtime(agent_runtime_instance)
                logger.info("Agent runtime initialized with saved LLM settings")
            else:
                logger.info("No LLM API key configured, agent runtime uses mock")
        except Exception:
            logger.warning("Failed to initialize agent runtime", exc_info=True)

        yield

    finally:
        # --- Shutdown ---
        set_tool_catalog(None)
        set_agent_runtime(None)
        if agent_runtime_instance is not None:
            try:
                llm_provider = getattr(agent_runtime_instance, "_llm", None)
                if hasattr(llm_provider, "close"):
                    await llm_provider.close()
            except Exception:
                logger.warning("Error closing agent LLM provider", exc_info=True)

        # Clean up MCP
        if mcp_registry_instance is not None:
            try:
                await mcp_registry_instance.stop()
            except Exception:
                logger.warning("Error stopping MCP registry", exc_info=True)
        set_mcp_registry(None)
        set_skill_registry(None)

        # FX15: Safe shutdown — guard against uninitialized variables
        if _autosave_task is not None:
            try:
                _autosave_task.cancel()
            except Exception:
                logger.debug(
                    "Could not cancel paper autosave task on shutdown",
                    exc_info=True,
                )
        # Stop strategy runner before paper engine
        if strategy_runner_instance is not None:
            try:
                await strategy_runner_instance.stop()
            except Exception:
                logger.warning("Error stopping strategy runner", exc_info=True)
        set_strategy_runner(None)

        if paper_engine is not None and paper_state is not None:
            try:
                paper_state.save_state(
                    paper_engine._account_mgr,
                    paper_engine._order_mgr,
                    paper_engine._position_mgr,
                    fills=paper_engine._fills,
                )
                logger.info("Paper state saved on shutdown")
            except Exception:
                logger.warning("Failed to save paper state on shutdown", exc_info=True)

        if paper_engine is not None:
            await paper_engine.stop()
        set_execution_engine(None)
        set_paper_managers(None, None, None)
        set_risk_engine(None)
        set_settings_service(None)
        set_key_pair_manager(None)
        await market_svc.stop()
        set_market_service(None)

        try:
            await funding_fetcher.close()
        except Exception:
            logger.debug(
                "Error closing funding rate fetcher on shutdown",
                exc_info=True,
            )
        set_funding_rate_fetcher(None)

        # Close storage
        set_chat_session_repo(None)
        set_strategy_repo(None)
        if db_manager is not None:
            try:
                await db_manager.close()
            except Exception:
                logger.warning("Error closing database", exc_info=True)
        set_db_manager(None)

        from app.core.redis_pubsub import stop_subscriber as _stop_pubsub

        await _stop_pubsub()
        if _kline_flush_task is not None:
            _kline_flush_task.cancel()
        await close_redis()
        logger.info("PnLClaw Local API shutdown complete")


async def _deploy_strategy_callback(strategy_id: str, account_id: str) -> str:
    """Callback for StrategyDeployTool: deploy strategy to paper runner.

    The StrategyRunner handles account creation, rule validation,
    duplicate prevention, and historical kline warmup internally.
    """
    from app.api.v1.strategies import (
        _get_strategy,
        _persist_save,
        _save_deployment,
        _strategies,
        _strategy_deployments,
    )
    from app.core.dependencies import get_strategy_runner

    config = await _get_strategy(strategy_id, user_id="local")
    if config is None:
        return f"Strategy '{strategy_id}' not found"

    has_rules = bool(config.entry_rules) or bool(config.exit_rules)
    if not has_rules:
        return (
            "ERROR: Cannot deploy strategy — entry_rules and exit_rules are empty. "
            "Save the strategy with complete rules first using save_strategy_version."
        )

    existing_running = next(
        (d for d in _strategy_deployments if d.strategy_id == strategy_id and d.status == "running"),
        None,
    )
    if existing_running:
        return (
            f"Strategy '{config.name}' is already deployed (deployment: "
            f"{existing_running.id}, account: {existing_running.account_id})"
        )

    runner = get_strategy_runner()
    if runner is None:
        return "Strategy runner not available"

    deployment_id = f"dep-{strategy_id[:8]}-{int(time.time())}"
    err = await runner.deploy(
        deployment_id=deployment_id,
        strategy_config=config.model_dump(),
        account_id=account_id,
    )
    if err:
        return f"Deploy failed: {err}"

    slot_status = runner.get_slot_status(deployment_id)
    actual_account_id = slot_status["account_id"] if slot_status else account_id

    try:
        from pnlclaw_types.strategy import StrategyDeployment

        dep = StrategyDeployment(
            id=deployment_id,
            strategy_id=strategy_id,
            strategy_version=config.version,
            account_id=actual_account_id,
            status="running",
        )
        await _save_deployment(dep)
        updated = config.model_copy(update={"lifecycle_state": "running"})
        _strategies[strategy_id] = updated
        await _persist_save(updated, user_id="local")
    except Exception:
        pass

    bar_count = slot_status.get("bar_count", 0) if slot_status else 0
    return (
        f"Strategy '{config.name}' deployed to dedicated account {actual_account_id}. "
        f"It will now automatically trade based on live {config.symbols[0]} "
        f"{config.interval} klines. "
        f"Historical warmup: {bar_count} bars preloaded."
    )


async def _stop_strategy_callback(strategy_id: str) -> str:
    """Callback for StrategyStopTool: stop running deployments for a strategy."""
    from app.api.v1.strategies import _strategy_deployments
    from app.core.dependencies import get_strategy_runner

    runner = get_strategy_runner()
    if runner is None:
        return "Strategy runner not available"

    stopped = 0
    for dep_id in list(runner.active_deployments):
        slot = runner.get_slot_status(dep_id)
        if slot and slot.get("strategy_id") == strategy_id:
            runner.stop_deployment(dep_id)
            stopped += 1

    for dep in _strategy_deployments:
        if dep.strategy_id == strategy_id and dep.status == "running":
            dep.status = "stopped"

    if stopped == 0:
        return f"No active deployments found for strategy {strategy_id}"
    return f"Stopped {stopped} deployment(s) for strategy {strategy_id}"


async def _save_strategy_version_callback(
    strategy_id: str,
    config: dict,
    changelog: str,
) -> str:
    """Callback for StrategySaveVersionTool: update strategy & create version snapshot."""
    from app.api.v1.strategies import (
        _get_strategy,
        _persist_save,
        _save_version_snapshot,
        _strategies,
    )

    logger.info(
        "save_strategy_version_callback invoked: strategy_id=%s, config_keys=%s",
        strategy_id,
        list(config.keys()) if config else "NONE",
    )

    existing = await _get_strategy(strategy_id)
    if existing is None:
        return f"Strategy '{strategy_id}' not found"

    if not config or not isinstance(config, dict):
        return (
            "ERROR: 'config' parameter is empty or invalid. "
            "You MUST provide a complete config dict with entry_rules, "
            "exit_rules, risk_params, name, symbols, interval, etc."
        )

    _PARSED_TO_RAW = {
        "parsed_entry_rules": "entry_rules",
        "parsed_exit_rules": "exit_rules",
        "parsed_risk_params": "risk_params",
    }
    for parsed_key, raw_key in _PARSED_TO_RAW.items():
        parsed_val = config.pop(parsed_key, None)
        if parsed_val is None:
            continue
        if hasattr(parsed_val, "model_dump"):
            parsed_val = parsed_val.model_dump()
        raw_val = config.get(raw_key)
        raw_is_empty = raw_val is None or raw_val == {} or raw_val == []
        if raw_is_empty and parsed_val:
            config[raw_key] = parsed_val

    known_fields = set(existing.model_fields.keys())
    update_fields = {k: v for k, v in config.items() if v is not None and k in known_fields}

    entry = update_fields.get("entry_rules") or existing.entry_rules
    exit_ = update_fields.get("exit_rules") or existing.exit_rules
    risk = update_fields.get("risk_params") or existing.risk_params
    has_rules = bool(entry) or bool(exit_) or bool(risk)

    if not has_rules:
        return (
            "ERROR: Cannot save strategy — entry_rules, exit_rules, and "
            "risk_params are ALL empty. You MUST provide at least entry_rules "
            "and exit_rules with actual strategy logic (conditions, indicators, "
            "operators). Call save_strategy_version again with the COMPLETE "
            "config including the rules you generated."
        )

    new_version = existing.version + 1
    update_fields["version"] = new_version
    updated = existing.model_copy(update=update_fields)
    _strategies[strategy_id] = updated
    await _persist_save(updated)
    await _save_version_snapshot(updated, changelog or "AI-generated update")

    logger.info(
        "save_strategy_version_callback done: name=%s, version=%d, entry_rules=%s, exit_rules=%s, risk_params=%s",
        updated.name,
        new_version,
        bool(updated.entry_rules),
        bool(updated.exit_rules),
        bool(updated.risk_params),
    )

    return (
        f"Strategy '{updated.name}' saved as version {new_version} "
        f"(ID: {strategy_id}). Rules: entry={bool(updated.entry_rules)}, "
        f"exit={bool(updated.exit_rules)}, risk={bool(updated.risk_params)}"
    )


def _register_agent_tools(
    catalog: object,
    *,
    market_service: object | None = None,
    account_manager: object | None = None,
    order_manager: object | None = None,
    position_manager: object | None = None,
    risk_engine: object | None = None,
) -> None:
    """Populate a ToolCatalog with all available agent tools."""
    from pnlclaw_agent import ToolCatalog

    tc: ToolCatalog = catalog  # type: ignore[assignment]

    if market_service is not None:
        from pnlclaw_agent.tools.market_tools import (
            MarketKlineTool,
            MarketOrderbookTool,
            MarketTickerTool,
        )

        tc.register(MarketTickerTool(market_service))
        tc.register(MarketKlineTool(market_service))
        tc.register(MarketOrderbookTool(market_service))

    if account_manager is not None:
        from pnlclaw_agent.tools.paper_tools import PaperCreateAccountTool

        tc.register(PaperCreateAccountTool(account_manager))

    if order_manager is not None:
        from pnlclaw_agent.tools.paper_tools import PaperPlaceOrderTool

        tc.register(PaperPlaceOrderTool(order_manager))

    if position_manager is not None:
        from pnlclaw_agent.tools.paper_tools import PaperPositionsTool

        tc.register(PaperPositionsTool(position_manager))

    if position_manager is not None and market_service is not None:
        from pnlclaw_agent.tools.paper_tools import PaperPnlTool

        tc.register(PaperPnlTool(position_manager, market_service))

        from pnlclaw_agent.tools.explain_tools import ExplainPnlTool

        tc.register(ExplainPnlTool(position_manager, market_service))

    # Strategy validate tool has no external dependencies
    try:
        from pnlclaw_agent.tools.strategy_tools import (
            BacktestResultTool,
            BacktestRunTool,
            StrategyDeployTool,
            StrategyExplainTool,
            StrategyGenerateTool,
            StrategySaveVersionTool,
            StrategyStopTool,
            StrategyValidateTool,
        )

        tc.register(StrategyValidateTool())
        tc.register(BacktestResultTool())
        tc.register(StrategyGenerateTool())
        tc.register(StrategyExplainTool())
        tc.register(StrategySaveVersionTool(save_fn=_save_strategy_version_callback))
        tc.register(StrategyDeployTool(deploy_fn=_deploy_strategy_callback))
        tc.register(StrategyStopTool(stop_fn=_stop_strategy_callback))

        # BacktestRunTool requires a BacktestEngine instance
        try:
            from pnlclaw_backtest.engine import BacktestEngine

            bt_engine = BacktestEngine()
            # Optional: pass backtest repo for persistence
            backtest_repo = None
            db = None
            try:
                from app.core.dependencies import get_db_manager

                db = get_db_manager()
                if db is not None:
                    from pnlclaw_storage.repositories.backtests import BacktestRepository

                    backtest_repo = BacktestRepository(db)
            except Exception:
                logger.debug(
                    "Optional backtest repository not wired for BacktestRunTool",
                    exc_info=True,
                )
            tc.register(
                BacktestRunTool(
                    bt_engine,
                    backtest_repo=backtest_repo,
                    market_service=market_service,
                )
            )
        except ImportError:
            logger.debug("BacktestRunTool not available (missing pnlclaw_backtest)")
    except ImportError:
        logger.debug("Strategy tools not available (missing pnlclaw_strategy)")

    if risk_engine is not None:
        from pnlclaw_agent.tools.risk_tools import RiskCheckTool, RiskReportTool

        tc.register(RiskCheckTool(risk_engine))
        tc.register(RiskReportTool(risk_engine))


async def _build_agent_runtime(
    settings_service: object,
    tool_catalog: object | None = None,
    *,
    user_id: str | None = None,
) -> object | None:
    """Build an AgentRuntime from persisted LLM settings, or return None."""
    from app.core.settings_service import SettingsService
    from pnlclaw_security.secrets import (
        SecretManager,
        SecretRef,
        SecretResolutionError,
        SecretSource,
    )

    svc: SettingsService = settings_service  # type: ignore[assignment]
    settings = svc._load_non_sensitive(user_id=user_id)
    llm_section = settings.get("llm", {})

    sm = SecretManager()
    llm_prov = svc._kr_provider("pnlclaw.llm", user_id)
    smart_prov = svc._kr_provider("pnlclaw.llm.smart", user_id)
    net_prov = svc._kr_provider("pnlclaw.network", user_id)

    ref = SecretRef(source=SecretSource.KEYRING, provider=llm_prov, id="api_key")
    try:
        resolved = await sm.resolve(ref)
        api_key = resolved.use()
    except SecretResolutionError:
        return None
    if not api_key:
        return None

    _keyring_fields = {"base_url": "", "model": "", "provider": ""}
    for field in _keyring_fields:
        try:
            r = await sm.resolve(SecretRef(source=SecretSource.KEYRING, provider=llm_prov, id=field))
            _keyring_fields[field] = r.use() or ""
        except SecretResolutionError:
            pass

    llm_section["base_url"] = _keyring_fields["base_url"] or llm_section.get("base_url", "")
    llm_section["model"] = _keyring_fields["model"] or llm_section.get("model", "")
    llm_section["provider"] = _keyring_fields["provider"] or llm_section.get("provider", "")

    _smart_fields = ("strategy", "analysis", "quick")
    smart_models_kr: dict[str, str] = {}
    for sf in _smart_fields:
        try:
            r = await sm.resolve(SecretRef(source=SecretSource.KEYRING, provider=smart_prov, id=sf))
            val = r.use() or ""
            if val:
                smart_models_kr[sf] = val
        except SecretResolutionError:
            pass
    if smart_models_kr:
        existing = llm_section.get("smart_models")
        if isinstance(existing, dict):
            existing.update(smart_models_kr)
        else:
            llm_section["smart_models"] = smart_models_kr

    proxy_url = ""
    try:
        r = await sm.resolve(SecretRef(source=SecretSource.KEYRING, provider=net_prov, id="proxy_url"))
        proxy_url = r.use() or ""
    except SecretResolutionError:
        pass

    from pnlclaw_agent import AgentRuntime, ToolCatalog
    from pnlclaw_agent.context.manager import ContextManager
    from pnlclaw_agent.prompt_builder import AgentContext
    from pnlclaw_llm.base import LLMConfig
    from pnlclaw_llm.openai_compat import OpenAICompatProvider

    smart_mode = llm_section.get("smart_mode", False)
    if isinstance(smart_mode, str):
        smart_mode = smart_mode.lower() == "true"

    default_model = llm_section.get("model") or ""
    if smart_mode:
        smart_models = llm_section.get("smart_models")
        if isinstance(smart_models, dict):
            model = smart_models.get("analysis", default_model)
        else:
            model = default_model
    else:
        model = default_model

    logger.info(
        "Building agent runtime: model=%s, base_url=%s",
        model,
        llm_section.get("base_url", "")[:40],
    )

    config = LLMConfig(
        model=model,
        api_key=api_key,
        base_url=llm_section.get("base_url") or None,
    )

    proxy_url = proxy_url or settings.get("network", {}).get("proxy_url", "")
    transport = None
    if proxy_url:
        import httpx

        transport = httpx.AsyncHTTPTransport(proxy=proxy_url)

    client = None
    if transport:
        import httpx

        client = httpx.AsyncClient(transport=transport, timeout=60.0)

    llm_provider = OpenAICompatProvider(config, client=client)

    if tool_catalog is None:
        tool_catalog = ToolCatalog()

    context_manager = ContextManager()
    prompt_context = AgentContext(
        available_tools=tool_catalog.get_tool_definitions(),  # type: ignore[union-attr]
    )

    # FX01: Inject skills prompt into agent context (fixed: pass skills list)
    try:
        from app.core.dependencies import get_skill_registry
        from pnlclaw_agent.skills.prompt import format_skills_for_prompt

        skill_registry = get_skill_registry()
        if skill_registry is not None:
            skills_list = skill_registry.list_skills()
            if skills_list:
                skills_text = format_skills_for_prompt(skills_list)
                if skills_text:
                    prompt_context.skills_prompt = skills_text
                    logger.info("Injected %d skills into agent context", len(skills_list))
    except Exception:
        logger.debug("Failed to load skills prompt", exc_info=True)

    return AgentRuntime(
        llm=llm_provider,
        tool_catalog=tool_catalog,  # type: ignore[arg-type]
        context_manager=context_manager,
        prompt_context=prompt_context,
    )


def _bridge_market_events(market_svc: object) -> None:
    """Bridge MarketDataService EventBus events to WebSocket broadcast.

    Orderbook snapshots are throttled to avoid saturating the event loop
    with expensive ``model_dump()`` serialisation of 2000-level books at
    ~120 updates/s.  Other event types are lightweight and forwarded
    immediately.
    """
    import asyncio
    import time as _time

    from app.api.v1.ws import _market_manager, broadcast_market_event, broadcast_market_event_fast
    from pnlclaw_types.derivatives import (
        FundingRateEvent,
        LargeOrderEvent,
        LargeTradeEvent,
        LiquidationEvent,
        LiquidationStats,
    )
    from pnlclaw_types.market import KlineEvent, OrderBookL2Snapshot, TickerEvent

    _ORDERBOOK_BROADCAST_INTERVAL = 0.25  # max 4 broadcasts/s per symbol
    _last_ob_broadcast: dict[str, float] = {}
    _pending_ob: dict[str, OrderBookL2Snapshot] = {}
    _ob_flush_running = False

    async def _flush_pending_orderbooks() -> None:
        """Periodically flush throttled orderbook snapshots."""
        nonlocal _ob_flush_running
        _ob_flush_running = True
        try:
            while True:
                await asyncio.sleep(_ORDERBOOK_BROADCAST_INTERVAL)
                if not _pending_ob:
                    continue
                if _market_manager.active_count == 0:
                    _pending_ob.clear()
                    continue
                batch = dict(_pending_ob)
                _pending_ob.clear()
                now = _time.monotonic()
                for key, snap in batch.items():
                    _last_ob_broadcast[key] = now
                    asyncio.ensure_future(
                        broadcast_market_event(
                            snap.symbol,
                            "depth",
                            snap.model_dump(),
                        )
                    )
        except asyncio.CancelledError:
            pass
        finally:
            _ob_flush_running = False

    def _on_ticker(event: TickerEvent) -> None:
        if _market_manager.active_count == 0:
            return
        channel = f"market:{event.exchange}:{event.market_type}:{event.symbol}"
        if not _market_manager.has_subscribers(channel):
            return
        asyncio.ensure_future(
            broadcast_market_event_fast(
                event.symbol,
                "ticker",
                event.model_dump_json(),
                exchange=event.exchange,
                market_type=event.market_type,
            )
        )

    global _kline_flush_task
    _kline_buffer: dict[str, KlineEvent] = {}
    _KLINE_FLUSH_INTERVAL = 2.0

    async def _flush_kline_buffer() -> None:
        """Periodically flush buffered kline events to Redis (every 2s)."""
        while True:
            await asyncio.sleep(_KLINE_FLUSH_INTERVAL)
            if not _kline_buffer:
                continue
            redis_client = _get_redis_lazy()
            if redis_client is None:
                _kline_buffer.clear()
                continue
            from pnlclaw_market.kline_store import KlineStore
            store = KlineStore(redis_client)
            batch = dict(_kline_buffer)
            _kline_buffer.clear()
            for _buf_key, event in batch.items():
                try:
                    await store.append(
                        event.exchange, event.market_type, event.symbol, event.interval, event
                    )
                except Exception:
                    logger.debug("Flush kline to Redis failed: %s", _buf_key, exc_info=True)

    _kline_flush_task = asyncio.create_task(_flush_kline_buffer(), name="kline-redis-flush")

    def _get_redis_lazy():  # noqa: ANN202
        from app.core.redis import get_redis
        return get_redis()

    def _buffer_kline_for_redis(event: KlineEvent) -> None:
        """Buffer kline event for batched Redis write (deduplicates by key)."""
        buf_key = f"{event.exchange}:{event.market_type}:{event.symbol}:{event.interval}"
        _kline_buffer[buf_key] = event

    def _on_kline(event: KlineEvent) -> None:
        _buffer_kline_for_redis(event)
        if _market_manager.active_count == 0:
            return
        channel = f"market:{event.exchange}:{event.market_type}:{event.symbol}"
        if not _market_manager.has_subscribers(channel):
            return
        asyncio.ensure_future(
            broadcast_market_event_fast(
                event.symbol,
                "kline",
                event.model_dump_json(),
                exchange=event.exchange,
                market_type=event.market_type,
            )
        )

    def _on_orderbook(event: OrderBookL2Snapshot) -> None:
        nonlocal _ob_flush_running
        if _market_manager.active_count == 0:
            return
        channel = f"market:{event.exchange}:{event.market_type}:{event.symbol}"
        if not _market_manager.has_subscribers(channel):
            return
        key = f"{event.exchange}:{event.market_type}:{event.symbol}"
        _pending_ob[key] = event
        if not _ob_flush_running:
            asyncio.ensure_future(_flush_pending_orderbooks())

    def _on_large_trade(event: LargeTradeEvent) -> None:
        asyncio.ensure_future(
            broadcast_market_event(
                event.symbol,
                "large_trade",
                event.model_dump(),
            )
        )

    def _on_large_order(event: LargeOrderEvent) -> None:
        asyncio.ensure_future(
            broadcast_market_event(
                event.symbol,
                "large_order",
                event.model_dump(),
            )
        )

    def _on_liquidation(event: LiquidationEvent) -> None:
        asyncio.ensure_future(
            broadcast_market_event(
                event.symbol,
                "liquidation",
                event.model_dump(),
            )
        )

    def _on_liquidation_stats(event: LiquidationStats) -> None:
        asyncio.ensure_future(
            broadcast_market_event(
                "ALL",
                "liquidation_stats",
                event.model_dump(),
            )
        )

    def _on_funding_rate(event: FundingRateEvent) -> None:
        asyncio.ensure_future(
            broadcast_market_event(
                event.symbol,
                "funding_rate",
                event.model_dump(),
            )
        )

    from pnlclaw_market import MarketDataService as _MDS

    svc: _MDS = market_svc  # type: ignore[assignment]
    svc.on_ticker(_on_ticker)
    svc.on_kline(_on_kline)
    svc.on_orderbook(_on_orderbook)
    svc.on_large_trade(_on_large_trade)
    svc.on_large_order(_on_large_order)
    svc.on_liquidation(_on_liquidation)
    svc.on_liquidation_stats(_on_liquidation_stats)
    svc.on_funding_rate(_on_funding_rate)


def _bridge_price_to_paper(market_svc: object, paper_engine: object) -> None:
    """Forward real-time ticker prices to PaperExecutionEngine for fill simulation."""
    import asyncio

    from pnlclaw_market import MarketDataService as _MDS
    from pnlclaw_paper.paper_execution import PaperExecutionEngine as _PE
    from pnlclaw_types.market import TickerEvent

    svc: _MDS = market_svc  # type: ignore[assignment]
    engine: _PE = paper_engine  # type: ignore[assignment]

    def _on_ticker_for_paper(event: TickerEvent) -> None:
        asyncio.ensure_future(engine.on_price_tick(event.symbol, event.last_price))

    svc.on_ticker(_on_ticker_for_paper)


def _bridge_execution_events(engine: object) -> None:
    """Bridge ExecutionEngine callbacks to the trading WebSocket broadcast."""
    import asyncio

    from app.api.v1.ws import broadcast_trading_event
    from pnlclaw_types.trading import BalanceUpdate, Fill, Order, Position

    def _on_order(order: Order) -> None:
        asyncio.ensure_future(
            broadcast_trading_event(
                "orders",
                "order_update",
                order.model_dump(),
            )
        )

    def _on_fill(fill: Fill) -> None:
        asyncio.ensure_future(
            broadcast_trading_event(
                "orders",
                "fill",
                fill.model_dump(),
            )
        )
        asyncio.ensure_future(_paper_snapshot_after_fill(engine, fill))

    def _on_position(pos: Position) -> None:
        asyncio.ensure_future(
            broadcast_trading_event(
                "positions",
                "position_update",
                pos.model_dump(),
            )
        )

    def _on_balance(balances: list[BalanceUpdate]) -> None:
        asyncio.ensure_future(
            broadcast_trading_event(
                "balances",
                "balance_update",
                [b.model_dump() for b in balances],
            )
        )

    engine.on_order_update(_on_order)  # type: ignore[union-attr]
    engine.on_fill(_on_fill)  # type: ignore[union-attr]
    engine.on_position_update(_on_position)  # type: ignore[union-attr]
    engine.on_balance_update(_on_balance)  # type: ignore[union-attr]


def _bridge_paper_engine_events(engine: object) -> None:
    """Bridge PaperExecutionEngine callbacks to the paper WebSocket channel.

    Broadcasts order_update, fill, position_update, balance_update, and
    account_snapshot events so the frontend can operate without polling.
    """
    import asyncio

    from app.api.v1.ws import broadcast_paper_event
    from pnlclaw_types.trading import BalanceUpdate, Fill, Order, Position

    def _resolve_account_for_order(order_id: str) -> str | None:
        try:
            return engine._get_order_account(order_id)  # type: ignore[union-attr]
        except Exception:
            return None

    def _on_order(order: Order) -> None:
        aid = _resolve_account_for_order(order.id)
        if aid:
            asyncio.ensure_future(broadcast_paper_event(aid, "order_update", order.model_dump()))

    def _on_fill(fill: Fill) -> None:
        aid = _resolve_account_for_order(fill.order_id)
        if aid:
            asyncio.ensure_future(broadcast_paper_event(aid, "fill", fill.model_dump()))
            asyncio.ensure_future(_paper_snapshot_after_fill(engine, fill, aid))

    def _on_position_scoped(account_id: str, pos: Position) -> None:
        asyncio.ensure_future(
            broadcast_paper_event(
                account_id,
                "position_update",
                pos.model_dump(),
            )
        )

    def _on_balance_scoped(account_id: str, balances: list[BalanceUpdate]) -> None:
        asyncio.ensure_future(
            broadcast_paper_event(
                account_id,
                "balance_update",
                [b.model_dump() for b in balances],
            )
        )

    engine.on_order_update(_on_order)  # type: ignore[union-attr]
    engine.on_fill(_on_fill)  # type: ignore[union-attr]
    engine.on_position_update_scoped(_on_position_scoped)  # type: ignore[union-attr]
    engine.on_balance_update_scoped(_on_balance_scoped)  # type: ignore[union-attr]


async def _paper_snapshot_after_fill(engine: object, fill: object, account_id: str | None = None) -> None:
    """After a fill, broadcast account_snapshot only to the affected account."""
    try:
        from app.api.v1.paper import _record_equity
        from app.api.v1.ws import broadcast_paper_event
        from app.core.dependencies import get_paper_account_manager, get_paper_position_manager

        acct_mgr = get_paper_account_manager()
        pos_mgr = get_paper_position_manager()
        if not acct_mgr or not pos_mgr:
            return

        if account_id:
            target_accounts = [acct_mgr.get_account(account_id)]
            target_accounts = [a for a in target_accounts if a is not None]
        else:
            target_accounts = acct_mgr.list_accounts()

        for account in target_accounts:
            unrealized = sum(p.unrealized_pnl for p in pos_mgr.get_open_positions(account.id))
            wallet_bal = account.initial_balance + account.total_realized_pnl - account.total_fee
            equity = wallet_bal + unrealized

            snapshot = account.model_dump()
            snapshot["equity"] = equity
            snapshot["balance"] = account.current_balance
            snapshot["unrealized_pnl"] = unrealized
            snapshot["realized_pnl"] = account.total_realized_pnl

            positions = [p.model_dump() for p in pos_mgr.get_open_positions(account.id)]
            snapshot["positions"] = positions

            await broadcast_paper_event(account.id, "account_snapshot", snapshot)

            try:
                await _record_equity(account.id, equity)
                await broadcast_paper_event(
                    account.id,
                    "equity_point",
                    {
                        "timestamp": int(__import__("time").time() * 1000),
                        "equity": equity,
                    },
                )
            except Exception:
                logger.debug("Equity record/broadcast failed for %s", account.id, exc_info=True)
    except Exception:
        logger.debug("Paper snapshot after fill failed", exc_info=True)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    import os
    is_production = os.environ.get("PNLCLAW_ENV") == "production"
    app = FastAPI(
        title="PnLClaw Local API",
        description="Local-first crypto quantitative trading platform API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/api/v1/docs",
        redoc_url=None if is_production else "/api/v1/redoc",
        openapi_url=None if is_production else "/api/v1/openapi.json",
    )

    # Middleware (outermost first — order matters: request-id → rate-limit → ...)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # Security headers
    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        return response

    # CORS — allow desktop and admin frontends
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "tauri://localhost"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Session-ID", "X-Request-ID"],
        max_age=3600,
    )

    # GZip — compress JSON responses (500 klines ~150KB -> ~20KB)
    from fastapi.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Error handlers (must be installed before routers for catch-all to work)
    install_error_handlers(app)

    # Routers
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(markets_router, prefix="/api/v1")
    app.include_router(derivatives_router, prefix="/api/v1")
    app.include_router(strategies_router, prefix="/api/v1")
    app.include_router(backtests_router, prefix="/api/v1")
    app.include_router(paper_router, prefix="/api/v1")
    app.include_router(trading_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(chat_sessions_router, prefix="/api/v1")
    app.include_router(mcp_router, prefix="/api/v1")
    app.include_router(skills_router, prefix="/api/v1")
    app.include_router(polymarket_router, prefix="/api/v1")
    app.include_router(ws_router)

    return app


app = create_app()
