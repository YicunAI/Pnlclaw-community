"""pnlclaw_paper -- Paper trading state and execution simulation.

Public API:
    PaperAccount, AccountStatus, AccountManager   — account management
    PaperOrderManager, InvalidOrderTransition      — order lifecycle
    try_fill                                       — fill simulation
    PositionManager                                — position tracking
    calculate_pnl, calculate_account_pnl           — PnL calculation
    PaperState                                     — state persistence
    DecisionPipeline, PipelineResult, PipelineConfig — decision pipeline
"""

from pnlclaw_paper.accounts import AccountManager, AccountStatus, PaperAccount
from pnlclaw_paper.decision_pipeline import (
    DecisionPipeline,
    PipelineAction,
    PipelineConfig,
    PipelineResult,
)
from pnlclaw_paper.fills import try_fill
from pnlclaw_paper.orders import InvalidOrderTransition, PaperOrderManager
from pnlclaw_paper.pnl import calculate_account_pnl, calculate_pnl
from pnlclaw_paper.positions import PositionManager
from pnlclaw_paper.state import PaperState

__all__ = [
    "PaperAccount",
    "AccountStatus",
    "AccountManager",
    "PaperOrderManager",
    "InvalidOrderTransition",
    "try_fill",
    "PositionManager",
    "calculate_pnl",
    "calculate_account_pnl",
    "PaperState",
    "DecisionPipeline",
    "PipelineAction",
    "PipelineConfig",
    "PipelineResult",
]
