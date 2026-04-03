"""
Fantasy Football Data Pipeline

A comprehensive Python pipeline for processing fantasy football rankings data
from multiple sources with automated web scraping.
"""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

try:
    __version__ = _pkg_version("fantasy-pipeline")
except PackageNotFoundError:
    __version__ = "0.3.0"

# Core processing
from .core.rankings_processor import (
    RankingsProcessor,
    process_redraft_rankings,
    process_bestball_rankings,
    process_weekly_rankings,
    process_ros_rankings,
)

# Data utilities
from .data.player_utils import (
    load_player_key_mapping,
    add_player_ids,
    clean_player_names,
)
from .data.loader import load_data

# Scraper
from .scraper.integration import (
    auto_scrape_if_needed,
    run_hw_scraper,
)

__all__ = [
    # Version
    "__version__",
    # Core processors
    "RankingsProcessor",
    "process_redraft_rankings",
    "process_bestball_rankings",
    "process_weekly_rankings",
    "process_ros_rankings",
    # Data utilities
    "load_player_key_mapping",
    "add_player_ids",
    "clean_player_names",
    "load_data",
    # Scraper
    "auto_scrape_if_needed",
    "run_hw_scraper",
]
