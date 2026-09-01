from .common import router as common_router
from .deals import router as deals_router
from .game import router as game_router
from .rules_help import router as rules_help_router
from .ux import router as ux_router

__all__ = [
    "rules_help_router",
    "ux_router",
    "common_router",
    "deals_router",
    "game_router",
]
