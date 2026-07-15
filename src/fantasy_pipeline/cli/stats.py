#!/usr/bin/env python3
"""
Fantasy Football Historical Stats CLI Command

Generate and merge historical player statistics for rankings integration.

Subcommands (additive — the default flow is unchanged):
  ff-stats ingest         rebuild combined_data.csv from the raw s<year>.xlsx exports
  ff-stats fetch-weekly   fetch a season's weekly fantasy points (ff-stats' --weekly-data input)
  ff-stats [options]      aggregate the two inputs into the rankings-ready HIST_* dataset
"""

import sys
import argparse

from fantasy_pipeline.config import LAST_COMPLETED_SEASON


def _ingest_command(argv) -> int:
    """Rebuild combined_data.csv from the raw PFR season exports (`ff-stats ingest`)."""
    from fantasy_pipeline.core.season_data_builder import (
        DEFAULT_INPUT_DIR,
        DEFAULT_OUTPUT_PATH,
        build_combined_season_data,
    )

    parser = argparse.ArgumentParser(
        prog="ff-stats ingest",
        description=(
            "Rebuild the combined season-totals dataset from every s<year>.xlsx in the input "
            "directory. Seasons are discovered from filenames, so a newly added year is picked "
            "up automatically. PFR blocks scripted access, so those files are manual downloads "
            "from pro-football-reference.com/years/<year>/fantasy.htm."
        ),
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_DIR, help="Directory holding the s<year>.xlsx exports")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Path of the combined CSV to write")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    ns = parser.parse_args(argv)

    try:
        df = build_combined_season_data(input_dir=ns.input, output_path=ns.output, verbose=not ns.quiet)
        print(f"\n✅ Combined {len(df)} player-seasons into: {ns.output}")
        return 0
    except Exception as e:
        print(f"\n❌ Error building season data: {e}")
        return 1


def _fetch_weekly_command(argv) -> int:
    """Fetch a season's weekly fantasy points (`ff-stats fetch-weekly`)."""
    from fantasy_pipeline.scraper.fetch_rankings import WEEKLY_LEADERS_URLS, fetch_fp_weekly_leaders

    parser = argparse.ArgumentParser(
        prog="ff-stats fetch-weekly",
        description=(
            "Fetch a season's weekly fantasy points from FantasyPros' weekly-leaders report and "
            "write ff-stats' --weekly-data CSV. Needs the free FantasyPros session "
            "(`ff-rankings login fp`) — the report is registration-fenced. The output carries a "
            "SEASON column so the aggregator can reject a season mismatch."
        ),
    )
    parser.add_argument(
        "--output",
        default="data/fpts historical/weekly_data.csv",
        help="Path of the weekly CSV to write (default: the ff-stats --weekly-data default)",
    )
    parser.add_argument(
        "--year", type=int, default=LAST_COMPLETED_SEASON, help=f"Season to fetch (default: {LAST_COMPLETED_SEASON})"
    )
    parser.add_argument(
        "--scoring",
        default="half-ppr",
        choices=sorted(WEEKLY_LEADERS_URLS),
        help="Scoring format (default: half-ppr — what the pipeline uses)",
    )
    parser.add_argument(
        "--min-players", type=int, default=300, help="Coverage floor — fail if fewer rows parse (default: 300)"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    ns = parser.parse_args(argv)

    try:
        path = fetch_fp_weekly_leaders(ns.output, year=ns.year, scoring=ns.scoring, min_players=ns.min_players)
        print(f"\n✅ Weekly data saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching weekly data: {e}")
        return 1


def main(args=None):
    """
    Generate historical player statistics.

    Args:
        args: Parsed arguments from argparse (if called from main.py)
              If None, will parse sys.argv directly
    """
    # Import from core package
    from fantasy_pipeline.core.stats_aggregator import aggregate_player_historical_stats, create_rankings_ready_dataset

    # If called standalone, parse arguments
    if args is None:
        argv = sys.argv[1:]
        # Additive subcommands (the default aggregation flow is unchanged)
        if argv and argv[0] == "ingest":
            return _ingest_command(argv[1:])
        if argv and argv[0] == "fetch-weekly":
            return _fetch_weekly_command(argv[1:])

        parser = argparse.ArgumentParser(description="Generate historical player statistics for rankings")
        parser.add_argument(
            "--season-data", default="data/fpts historical/combined_data.csv", help="Path to season totals CSV file"
        )
        parser.add_argument(
            "--weekly-data",
            default="data/fpts historical/weekly_data.csv",
            help="Path to weekly fantasy points CSV file",
        )
        parser.add_argument("--player-key", default="player_key_dict.json", help="Path to player key dictionary")
        parser.add_argument(
            "--season",
            type=int,
            default=LAST_COMPLETED_SEASON,
            help=f"Season to filter (default: {LAST_COMPLETED_SEASON}, the last completed season)",
        )
        parser.add_argument("--min-games", type=int, default=10, help="Minimum games played (default: 10)")
        parser.add_argument(
            "--output", default="data/rankings current/latest/", help="Output directory for rankings-ready file"
        )
        parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
        args = parser.parse_args(argv)

    try:
        print("🏈 Generating Historical Player Statistics")
        print("=" * 60)

        # Step 1: Aggregate historical stats
        aggregated_stats = aggregate_player_historical_stats(
            season_data_path=args.season_data,
            weekly_data_path=args.weekly_data,
            player_key_path=args.player_key,
            season_filter=args.season,
            output_dir=None,  # Don't save intermediate file
            verbose=not args.quiet,
        )

        # Step 2: Create rankings-ready dataset
        rankings_ready = create_rankings_ready_dataset(
            aggregated_stats,
            current_season=str(args.season),
            min_games=args.min_games,
            output_dir=args.output,
            verbose=not args.quiet,
        )

        print(f"\n✅ Success! Generated stats for {len(rankings_ready)} players")
        print(f"   Output saved to: {args.output}")
        return 0

    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
        print("   Make sure data files exist at the specified paths")
        return 1
    except Exception as e:
        print(f"\n❌ Error generating stats: {str(e)}")
        if not args.quiet:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
