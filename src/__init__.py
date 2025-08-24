"""
Fantasy Football Data Processing Library

Comprehensive library for processing fantasy football data including rankings,
statistics, and data management utilities.
"""

# Configuration and constants
from .config import COLUMN_MAPPINGS, FILE_MAPPINGS, SUPPORTED_POSITIONS, DEFAULT_PATHS

# Data loading and utilities
from .data_loader import load_data
from .player_utils import clean_player_names, load_player_key_mapping, add_player_ids

# Base processors for all ranking data sources
from .base_processor import (
    BaseProcessor,
    process_fpts_data, process_fantasypros_data, process_hw_data,
    process_jj_data, process_pff_data, process_draftshark_rank_data, 
    process_fantasypros_adp_data
)

# Main rankings processor
from .rankings_processor import RankingsProcessor, process_redraft_rankings, process_bestball_rankings, process_fantasy_rankings_redraft

# Historical stats processors
from .season_stats_processor import calculate_season_stats, get_season_stats_summary, validate_season_stats
from .weekly_stats_processor import calculate_weekly_trends, get_weekly_trends_summary, validate_weekly_trends, compare_half_season_performance

# Player key utilities
from .update_player_key import update_player_key_dict

__version__ = "2.0.0"

__all__ = [
    # Configuration
    'COLUMN_MAPPINGS', 'FILE_MAPPINGS', 'SUPPORTED_POSITIONS', 'DEFAULT_PATHS',
    
    # Data utilities
    'load_data', 'clean_player_names', 'load_player_key_mapping', 'add_player_ids',
    
    # Base processor
    'BaseProcessor',
    
    # Ranking processors
    'process_fpts_data', 'process_fantasypros_data', 'process_hw_data',
    'process_jj_data', 'process_pff_data', 'process_draftshark_rank_data', 
    'process_fantasypros_adp_data',
    
    # Main rankings processor
    'RankingsProcessor', 'process_redraft_rankings', 'process_bestball_rankings', 'process_fantasy_rankings_redraft',
    
    # Historical stats processors
    'calculate_season_stats', 'get_season_stats_summary', 'validate_season_stats',
    'calculate_weekly_trends', 'get_weekly_trends_summary', 'validate_weekly_trends', 'compare_half_season_performance',
    
    # Player key utilities
    'update_player_key_dict',
] 