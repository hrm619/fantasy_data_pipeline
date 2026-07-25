"""Expert accuracy & bias analysis over a frozen snapshot of historical rankings.

Separate from the ranking pipeline: this reads `data/rankings_historical/` (a fixed
snapshot that will not change) plus PFR season outcomes, and writes its own tables.

See `docs/expert-accuracy-analysis.md` for the design and its statistical limits.
"""

from .historical import (
    EXPERT_KINDS,
    build_expert_rankings,
    build_player_outcomes,
    load_snapshot,
)
from .scorecard import (
    add_value_curve,
    conviction_calls,
    expert_scorecard,
    realized_value_curve,
)

__all__ = [
    "EXPERT_KINDS",
    "build_expert_rankings",
    "build_player_outcomes",
    "load_snapshot",
    "add_value_curve",
    "conviction_calls",
    "expert_scorecard",
    "realized_value_curve",
]
