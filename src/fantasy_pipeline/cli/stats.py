#!/usr/bin/env python3
"""
Fantasy Football Historical Stats CLI Command

Generate and merge historical player statistics for rankings integration.
"""

import sys
import os
import argparse
from pathlib import Path


def main(args=None):
    """
    Generate historical player statistics.

    Args:
        args: Parsed arguments from argparse (if called from main.py)
              If None, will parse sys.argv directly
    """
    # Import from core package
    from fantasy_pipeline.core.stats_aggregator import (
        aggregate_player_historical_stats,
        create_rankings_ready_dataset
    )

    # If called standalone, parse arguments
    if args is None:
        parser = argparse.ArgumentParser(
            description='Generate historical player statistics for rankings'
        )
        parser.add_argument(
            '--season-data',
            default="data/fpts historical/combined_data.csv",
            help='Path to season totals CSV file'
        )
        parser.add_argument(
            '--weekly-data',
            default="data/fpts historical/weekly_data.csv",
            help='Path to weekly fantasy points CSV file'
        )
        parser.add_argument(
            '--player-key',
            default="player_key_dict.json",
            help='Path to player key dictionary'
        )
        parser.add_argument(
            '--season',
            type=int,
            default=2024,
            help='Season to filter (default: 2024)'
        )
        parser.add_argument(
            '--min-games',
            type=int,
            default=10,
            help='Minimum games played (default: 10)'
        )
        parser.add_argument(
            '--output',
            default="data/rankings current/latest/",
            help='Output directory for rankings-ready file'
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress verbose output'
        )
        args = parser.parse_args()

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
            verbose=not args.quiet
        )

        # Step 2: Create rankings-ready dataset
        rankings_ready = create_rankings_ready_dataset(
            aggregated_stats,
            current_season=str(args.season),
            min_games=args.min_games,
            output_dir=args.output,
            verbose=not args.quiet
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
