"""
Fantasy Football Data Processors

This module now contains only historical stats processors.
Main ranking processors have been consolidated into lib/base_processor.py.
"""

from .season_stats_processor import calculate_season_stats, get_season_stats_summary, validate_season_stats
from .weekly_stats_processor import calculate_weekly_trends, get_weekly_trends_summary, validate_weekly_trends, compare_half_season_performance

# Note: Ranking processors have been moved to lib/base_processor.py
# For backward compatibility, you can import them as:
# from lib.base_processor import process_fpts_data, process_fantasypros_data, etc.

__all__ = [
    # Season stats processor
    'calculate_season_stats',
    'get_season_stats_summary',
    'validate_season_stats',
    
    # Weekly stats processor
    'calculate_weekly_trends',
    'get_weekly_trends_summary',
    'validate_weekly_trends',
    'compare_half_season_performance',
] 