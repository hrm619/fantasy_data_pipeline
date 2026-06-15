"""
Configuration module for fantasy football data processing.

Centralizes all column mappings, file lookups, and constants.
"""

from typing import Optional

# Shared column layouts reused across weekly and ROS mappings (identical formats).
# Defined once here to keep WEEKLY_COLUMN_MAPPINGS and ROS_COLUMN_MAPPINGS in sync.

# Hayden Winks rankings as scraped from Underdog Network
_HW_SCRAPER_COLUMNS = ["PLAYER NAME", "PLAYER ID", "STANDARDIZED NAME", "POS", "POS RANK", "YARDS STAT", "DETAILS"]

# HW data for merging (tableDownload.csv) - provides HPPR, EXP, DIFF
_HW_DATA_COLUMNS = ["PLAYER NAME", "POS", "TEAM", "NOTES", "HPPR RANK", "EXP RANK", "HPPR", "EXP", "DIFF"]

# FPTS data for merging (fpts-xfp-avg.csv) - numeric performance fields
_FPTS_DATA_COLUMNS = [
    "RK",
    "PLAYER NAME",
    "TEAM",
    "POS",
    "GP",
    "FPTS",
    "XFP",
    "FPTS_DIFF",  # FPTS - XFP difference
    "TD",
    "XTD",
    "TD_DIFF",  # TD - XTD difference
    "OPP5",
    "OPP10",
    "OPP20",
    "RUSH",
    "AIRYDS",
    "TGT",
    "EZTGT",
    "DEEPTGT",
]

# Standard column names for different data sources
COLUMN_MAPPINGS = {
    # FPTS data (Scott Barrett)
    "fpts": ["RK", "PLAYER NAME", "POS", "TEAM", "BYE", "TIER", "EXODIA"],
    # FantasyPros data
    "fp": ["ECR", "TIER", "PLAYER NAME", "TEAM", "POS", "BYE", "SOS", "ECR VS ADP"],
    # JJ Zachariason data
    "jj": ["RK", "PLAYER NAME", "POS", "POS RANK", "TIER", "AUCTION"],
    # DraftShark rankings
    "ds": [
        "RK",
        "TEAM",
        "PLAYER NAME",
        "POS",
        "G",
        "DS ADP",
        "BYE",
        "SOS",
        "INJURY RISK",
        "FLOOR PROJ",
        "CONS PROJ",
        "DS PROJ",
        "CEILING PROJ",
        "3D VALUE",
    ],
    # Hayden Winks data
    "hw": ["PLAYER NAME", "RK", "UNDERDOG ADP", "DIFF", "FINISH-2024", "TEAM", "POS", "POS RANK", "NOTES", "ID"],
    # PFF data
    "pff": ["RK", "PLAYER NAME", "TEAM", "POS", "POS RANK", "BYE", "PFF ADP", "PROJ", "AUCTION"],
    # ADP data
    "adp": ["PLAYER NAME", "TEAM", "BYE", "POS", "ADP", "MARKET INDEX", "RT"],
}

# Weekly-specific column mappings (different from draft mappings)
WEEKLY_COLUMN_MAPPINGS = {
    # FPTS data (The GURU) - weekly format
    "fpts": ["RK", "PLAYER NAME", "POS", "TEAM", "OPP", "UP", "DOWN", "WW"],
    # FantasyPros weekly data
    "fp": ["RK", "PLAYER NAME", "TEAM", "POS", "OPP", "UPSIDE", "BUST", "MATCHUP"],
    # JJ Zachariason weekly data (concatenated FLEX sections)
    "jj": [
        "RK",  # Rank column
        "PLAYER NAME",  # FLEX column (player name)
        "TEAM",  # Team
        "OPP",  # Opponent
        "TOTAL",  # Total points
        "POS",  # Position
        "MATCHUP",  # Matchup rating
    ],
    # DraftShark weekly data
    "ds": [
        "RK",
        "TEAM",
        "PLAYER NAME",
        "POS",
        "MATCHUP",
        "SOS",
        "BYE",
        "FLOOR",
        "CONS",
        "PROJ",
        "CEIL",
        "3D PROJ",
        "FANDUEL SALARY",
        "FANDUEL $/PT",
        "DRAFTKINGS SALARY",
        "DRAFTKINGS $/PT",
    ],
    # Hayden Winks weekly data (scraped from Underdog Network)
    "hw": _HW_SCRAPER_COLUMNS,
    # PFF weekly data (header in second row)
    "pff": ["RK", "PLAYER NAME", "TEAM", "POS", "POS RANK", "BYE", "STATUS"],
    # HW data for merging (tableDownload.csv)
    "hw-data": _HW_DATA_COLUMNS,
    # FPTS data for merging (fpts-xfp-avg.csv)
    "fpts-data": _FPTS_DATA_COLUMNS,
}

# ROS (Rest of Season) column mappings
# Data sources:
# - fp: https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php?signedin
# - fpts: https://www.fantasypoints.com/nfl/rankings/rest-of-season/rb-wr-te?season=2025#/
# - hw: https://underdognetwork.com/football/fantasy-rankings/week-6-fantasy-football-rankings-the-blueprint-2025
# - jj: https://www.patreon.com/posts/141197927?collection=47664
# - pff: https://www.pff.com/fantasy/rankings/draft
# - ds: https://www.draftsharks.com/ros-rankings/half-ppr
ROS_COLUMN_MAPPINGS = {
    # FPTS data (2025 NFL Rest of Season) - two files: QB and WR/RB/TE
    "fpts": ["RK", "PLAYER NAME", "POS", "TEAM", "BYE"],
    # JJ Zachariason ROS data (second sheet "Rankings and Tiers")
    "jj": ["RK", "PLAYER NAME", "POS", "POS RANK", "TIER", "TEAM", "ROS", "NEXT 4", "PPG", "BYE"],
    # Hayden Winks ROS data (scraped from Underdog Network)
    "hw": _HW_SCRAPER_COLUMNS,
    # FantasyPros ROS data (FantasyPros_ format, header in first row)
    "fp": ["RK", "PLAYER NAME", "TEAM", "POS", "SOS SEASON", "SOS PLAYOFFS", "ECR VS ADP"],
    # PFF ROS data (Draft-rankings-export format)
    "pff": ["RK", "PLAYER NAME", "TEAM", "POS", "POS RANK", "BYE", "ADP", "PROJ", "AUCTION"],
    # DraftShark ROS data (ros-rankings-half-ppr format)
    "ds": [
        "RK",
        "TEAM",
        "PLAYER NAME",
        "POS",
        "G",
        "SOS",
        "BYE",
        "INJURY RISK",
        "FLOOR PROJ",
        "CONS PROJ",
        "DS PROJ",
        "CEILING PROJ",
        "3D VALUE",
    ],
    # HW data for merging (tableDownload.csv)
    "hw-data": _HW_DATA_COLUMNS,
    # FPTS data for merging (fpts-xfp-avg.csv)
    "fpts-data": _FPTS_DATA_COLUMNS,
}

# Current NFL season — the single source of truth for season-specific filenames and URLs.
# Bump this one constant at season rollover and it propagates to:
#   - FILE_MAPPINGS 'fp'/'adp' prefixes and the ROS 'fpts' file pattern (below)
#   - the fetcher filename defaults (fetch_rankings.py imports it as the `year` default)
#   - the CLI `--year` defaults (cli/rankings.py)
#   - the HW scraper article slug (get_hw_scraper_url's `season` default)
CURRENT_SEASON = 2025

# File lookup patterns for different league types
FILE_MAPPINGS = {
    "redraft": {
        "fpts": "Scott Barrett",
        "fp": f"FantasyPros_{CURRENT_SEASON}_Draft_ALL_Rankings",
        "jj": "Redraft1QB_",
        "ds": "rankings-half-ppr",
        "hw": "tableDownload",
        "pff": "Draft-rankings-export",
        "adp": f"FantasyPros_{CURRENT_SEASON}_Overall_ADP_Rankings",
    },
    "bestball": {
        "fpts": "Scott Barrett",
        "fp": f"FantasyPros_{CURRENT_SEASON}_Draft_ALL_Rankings",
        "jj": "1QBRankings_",
        "ds": "rankings-half-ppr",
        "hw": "tableDownload",
        "pff": "Draft-rankings-export",
        "adp": "adp-rankings",
    },
    "weekly": {
        # Weekly mappings are generated dynamically by get_weekly_file_mappings()
        # This placeholder ensures 'weekly' is recognized as a valid league type
    },
    # NOTE: ROS file lookups are generated dynamically at runtime by
    # get_ros_file_mappings(week); this static entry is retained only for
    # league-type validation (`league_type not in FILE_MAPPINGS`). Keep it in
    # sync with that function — the authoritative HW prefix is hw-week{week}.
    "ros": {
        "fpts": [str(CURRENT_SEASON)],  # Multiple files: QB and WR/RB/TE
        "jj": "ROSRankings_",
        "hw": "hw-week",  # Scraped HW rankings -> hw-week{week}.csv (same prefix as weekly)
        "fp": "FantasyPros_",
        "pff": "Draft-rankings-export",
        "ds": "ros-rankings-half-ppr",
        # Data files for merging
        "hw-data": "tableDownload",  # HW data for merging (HPPR, Exp, Diff)
        "fpts-data": "fpts-xfp-avg",  # FPTS data for merging (numeric fields)
    },
}

# Supported fantasy positions
SUPPORTED_POSITIONS = ["QB", "RB", "WR", "TE"]

# Default paths
DEFAULT_PATHS = {
    "data_dir": "data/rankings current/",
    "update_dir": "data/rankings current/update/",
    "latest_dir": "data/rankings current/latest/",
    "agg_archive_dir": "data/rankings current/agg archive/",
    "raw_archive_dir": "data/rankings current/raw archive/",
    "player_key_file": "player_key_dict.json",
}

# Standardized output columns for all processors
STANDARD_OUTPUT_COLUMNS = {
    "base": ["PLAYER NAME", "PLAYER ID", "POS", "TEAM"],
    "ranking": ["RK", "POS RANK"],
    "optional": ["TIER", "ADP", "ECR", "POS ECR", "ADP ROUND"],
}

# Weekly-specific output columns (excludes ADP and overall RK)
WEEKLY_OUTPUT_COLUMNS = {
    "base": ["PLAYER NAME", "PLAYER ID", "POS", "TEAM"],
    "ranking": ["POS RANK"],  # Only positional rankings for weekly
    "optional": ["TIER", "ECR", "POS ECR"],  # No ADP-related columns for weekly
}

# ROS-specific output columns (similar to weekly, focus on positional rankings)
ROS_OUTPUT_COLUMNS = {
    "base": ["PLAYER NAME", "PLAYER ID", "POS", "TEAM"],
    "ranking": ["POS RANK"],  # Only positional rankings for ROS
    "optional": ["TIER", "ECR", "POS ECR"],  # No ADP-related columns for ROS
}


def get_weekly_file_mappings(week: int) -> dict:
    """
    Generate weekly file mappings with the specified week number.

    Args:
        week (int): Week number to use in file mappings

    Returns:
        dict: File mappings with week number dynamically generated
    """
    return {
        "fpts": ["The GURU"],  # List of file prefixes for multiple position files
        "fp": "FantasyPros_",  # Will be combined with week info
        "jj": f"Week{week}_RankingsTiers",  # Week2_RankingsTiers, Week3_RankingsTiers, etc.
        "ds": "weekly-rankings",  # Static file prefix - update if needed
        "hw": f"hw-week{week}",  # Scraped HW rankings from Underdog Network
        "pff": f"Week-{week}-rankings",  # Week-2-rankings, Week-3-rankings, etc.
        # Note: No ADP mapping for weekly - ADP not relevant for weekly rankings
        # Data files for merging
        "hw-data": "tableDownload",  # HW data for merging (HPPR, Exp, Diff)
        "fpts-data": "fpts-xfp-avg",  # FPTS data for merging (numeric fields)
    }


def get_ros_file_mappings(week: int) -> dict:
    """
    Generate ROS file mappings with the specified week number.

    Args:
        week (int): Week number to use in file mappings

    Returns:
        dict: File mappings with week number dynamically generated
    """
    return {
        "fpts": [str(CURRENT_SEASON)],  # Multiple files: QB and WR/RB/TE
        "jj": "ROSRankings_",
        "hw": f"hw-week{week}",  # Scraped HW rankings from Underdog Network (same as weekly)
        "fp": "FantasyPros_",
        "pff": "Draft-rankings-export",
        "ds": "ros-rankings-half-ppr",
        # Data files for merging
        "hw-data": "tableDownload",  # HW data for merging (HPPR, Exp, Diff)
        "fpts-data": "fpts-xfp-avg",  # FPTS data for merging (numeric fields)
    }


def get_hw_scraper_url(week: Optional[int] = None, league_type: str = "weekly", season: int = CURRENT_SEASON) -> str:
    """
    Generate the Underdog Network URL for HW rankings scraper.

    Args:
        week (int): Week number for weekly/ROS rankings
        league_type (str): League type ('weekly' or 'ros')
        season (int): NFL season year used in the article slug (default: CURRENT_SEASON).
                      Bump CURRENT_SEASON (or pass season) at season rollover.

    Returns:
        str: URL for the HW rankings article
    """
    if league_type in ["weekly", "ros"] and week:
        # Both weekly and ROS use the same URL pattern with week number + season
        return (
            "https://underdognetwork.com/football/fantasy-rankings/"
            f"week-{week}-fantasy-football-rankings-the-blueprint-{season}"
        )
    else:
        raise ValueError(f"Invalid parameters for HW scraper URL: league_type={league_type}, week={week}")
