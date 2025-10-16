"""
Core processing modules for fantasy football rankings.
"""

from .rankings_processor import (
    RankingsProcessor,
    process_redraft_rankings,
    process_bestball_rankings,
    process_weekly_rankings,
    process_ros_rankings,
)
from .base_processor import (
    BaseProcessor,
    process_fpts_data,
    process_fantasypros_data,
    process_hw_data,
    process_jj_data,
    process_pff_data,
    process_draftshark_rank_data,
    process_fantasypros_adp_data,
)
from .season_stats_processor import calculate_season_stats
from .weekly_stats_processor import calculate_weekly_trends
from .stats_aggregator import (
    aggregate_player_historical_stats,
    create_rankings_ready_dataset,
    merge_with_redraft_rankings,
)

__all__ = [
    # Main processor
    "RankingsProcessor",
    "process_redraft_rankings",
    "process_bestball_rankings",
    "process_weekly_rankings",
    "process_ros_rankings",
    # Base processor
    "BaseProcessor",
    "process_fpts_data",
    "process_fantasypros_data",
    "process_hw_data",
    "process_jj_data",
    "process_pff_data",
    "process_draftshark_rank_data",
    "process_fantasypros_adp_data",
    # Stats processors
    "calculate_season_stats",
    "calculate_weekly_trends",
    # Stats aggregator
    "aggregate_player_historical_stats",
    "create_rankings_ready_dataset",
    "merge_with_redraft_rankings",
]
