"""
Web scraper for Hayden Winks rankings from Underdog Network.
"""

from .hw_scraper import scrape_fantasy_rankings, match_player_name, load_player_key
from .integration import (
    auto_scrape_if_needed,
    run_hw_scraper,
    check_hw_scraper_output_exists,
)

__all__ = [
    # Core scraper
    "scrape_fantasy_rankings",
    "match_player_name",
    "load_player_key",
    # Integration
    "auto_scrape_if_needed",
    "run_hw_scraper",
    "check_hw_scraper_output_exists",
]
