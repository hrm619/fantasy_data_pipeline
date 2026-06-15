"""
HW Ranking Scraper Integration Module

Integrates the hw_scraper module into the main fantasy data pipeline.
Automatically scrapes HW rankings from Underdog Network and saves them to the
update folder for processing.
"""

import os
from typing import Optional

from .hw_scraper import scrape_fantasy_rankings
from ..config import get_hw_scraper_url, DEFAULT_PATHS


def _hw_output_filename(week: int) -> str:
    """Return the scraped HW rankings filename (both weekly and ROS use this format)."""
    return f"hw-week{week}.csv"


def run_hw_scraper(
    week: Optional[int] = None, league_type: str = "weekly", data_path: Optional[str] = None, verbose: bool = True
) -> str:
    """
    Run the HW ranking scraper and save output to the update folder.

    Args:
        week (int): Week number for weekly rankings (required for weekly league type)
        league_type (str): League type ('weekly' or 'ros')
        data_path (str): Path to update directory where scraped file will be saved
        verbose (bool): Whether to print progress information

    Returns:
        str: Path to the saved CSV file

    Raises:
        ValueError: If week is not provided for weekly league type
        Exception: If scraping fails
    """
    # HW scraping always keys its output on a week (weekly and ROS both use hw-week{N}.csv)
    if week is None:
        raise ValueError(f"Week number is required for HW scraping ({league_type})")

    # Use default data path if not provided
    data_path = data_path or DEFAULT_PATHS["update_dir"]

    # Ensure data path exists
    os.makedirs(data_path, exist_ok=True)

    # Get URL for scraping
    url = get_hw_scraper_url(week, league_type)

    if verbose:
        print("\n🕷️  Running HW Rankings Scraper...")
        print(f"   League Type: {league_type.upper()}")
        if week:
            print(f"   Week: {week}")
        print(f"   URL: {url}")

    try:
        # Run the scraper
        if verbose:
            print("   Fetching and parsing data...")

        df = scrape_fantasy_rankings(url)

        if verbose:
            print(f"   ✓ Scraped {len(df)} players")
            print("   Position breakdown:")
            for pos in ["QB", "RB", "WR", "TE"]:
                count = len(df[df["Position"] == pos])
                if count > 0:
                    print(f"     {pos}: {count} players")

        # Determine output filename (both weekly and ros use hw-week{N}.csv format)
        output_path = os.path.join(data_path, _hw_output_filename(week))

        # Save to CSV
        df.to_csv(output_path, index=False)

        if verbose:
            print(f"   ✓ Saved to: {output_path}")

        return output_path

    except Exception as e:
        if verbose:
            print(f"   ✗ Scraping failed: {e}")
        raise


def check_hw_scraper_output_exists(
    week: Optional[int] = None, league_type: str = "weekly", data_path: Optional[str] = None
) -> bool:
    """
    Check if HW scraper output already exists in the update folder.

    Args:
        week (int): Week number for weekly rankings
        league_type (str): League type ('weekly' or 'ros')
        data_path (str): Path to update directory

    Returns:
        bool: True if file exists, False otherwise
    """
    if week is None:
        raise ValueError(f"Week number is required for HW scraping ({league_type})")

    data_path = data_path or DEFAULT_PATHS["update_dir"]

    file_path = os.path.join(data_path, _hw_output_filename(week))
    return os.path.exists(file_path)


def auto_scrape_if_needed(
    week: Optional[int] = None,
    league_type: str = "weekly",
    data_path: Optional[str] = None,
    force: bool = False,
    verbose: bool = True,
) -> str:
    """
    Automatically run HW scraper if output doesn't exist in update folder.

    Args:
        week (int): Week number for weekly rankings
        league_type (str): League type ('weekly' or 'ros')
        data_path (str): Path to update directory
        force (bool): Force re-scraping even if file exists
        verbose (bool): Whether to print progress information

    Returns:
        str: Path to the HW scraper output file
    """
    if week is None:
        raise ValueError(f"Week number is required for HW scraping ({league_type})")

    data_path = data_path or DEFAULT_PATHS["update_dir"]

    # Check if file already exists
    if not force and check_hw_scraper_output_exists(week, league_type, data_path):
        file_path = os.path.join(data_path, _hw_output_filename(week))

        if verbose:
            print(f"\n✓ HW scraper output already exists: {file_path}")
            print("  Skipping scraping (use force=True to re-scrape)")

        return file_path

    # File doesn't exist or force flag is set - run scraper
    return run_hw_scraper(week, league_type, data_path, verbose)
