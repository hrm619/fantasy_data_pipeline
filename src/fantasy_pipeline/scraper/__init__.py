"""
Web scraper for Hayden Winks rankings from Underdog Network.
"""

from .hw_scraper import scrape_fantasy_rankings, match_player_name, load_player_key
from .integration import (
    auto_scrape_if_needed,
    run_hw_scraper,
    check_hw_scraper_output_exists,
)
from .fetch_yahoo_hw import (
    fetch_yahoo_hw,
    fetch_yahoo_hw_top300,
    fetch_yahoo_hw_analysis,
    parse_article,
    parse_top300_table,
)

__all__ = [
    # Core scraper (weekly/ROS, Underdog Network)
    "scrape_fantasy_rankings",
    "match_player_name",
    "load_player_key",
    # Integration
    "auto_scrape_if_needed",
    "run_hw_scraper",
    "check_hw_scraper_output_exists",
    # Yahoo HW redraft fetcher
    "fetch_yahoo_hw",
    "fetch_yahoo_hw_top300",
    "fetch_yahoo_hw_analysis",
    "parse_article",
    "parse_top300_table",
]
