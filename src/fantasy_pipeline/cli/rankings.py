#!/usr/bin/env python3
"""
Fantasy Football Rankings CLI Command

Process fantasy football rankings from multiple sources.
"""

import argparse
import os
import sys
from fantasy_pipeline import RankingsProcessor


def _build_rankings_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the default rankings command."""
    parser = argparse.ArgumentParser(description='Process fantasy football rankings')
    parser.add_argument(
        '--league-type',
        choices=['redraft', 'bestball', 'weekly', 'ros'],
        default='redraft',
        help='Type of league to process (default: redraft)'
    )
    parser.add_argument(
        '--week',
        type=int,
        help='Week number for weekly/ROS rankings (required when league-type is weekly or ros)'
    )
    parser.add_argument(
        '--data-path',
        help='Path to update directory containing ranking files'
    )
    parser.add_argument(
        '--player-key-path',
        help='Path to player key dictionary JSON file'
    )
    parser.add_argument(
        '--base-data-dir',
        help='Base directory containing latest, update, archive folders'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress verbose output'
    )
    return parser


def _fetch_adp_command(argv) -> int:
    """Fetch FantasyPros consensus ADP into the update folder (`ff-rankings fetch-adp`)."""
    from fantasy_pipeline.config import DEFAULT_PATHS, CURRENT_SEASON
    from fantasy_pipeline.scraper.fetch_rankings import fetch_fantasypros_adp

    parser = argparse.ArgumentParser(
        prog='ff-rankings fetch-adp',
        description='Fetch FantasyPros consensus ADP and save it to the update folder'
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_PATHS['update_dir'],
        help='Directory to save the ADP CSV (default: the pipeline update folder)'
    )
    parser.add_argument('--year', type=int, default=CURRENT_SEASON, help='Season year for the filename')
    parser.add_argument('--min-players', type=int, default=200,
                        help='Coverage floor — fail if fewer players parse (default: 200)')
    ns = parser.parse_args(argv)

    try:
        os.makedirs(ns.output, exist_ok=True)
        path = fetch_fantasypros_adp(ns.output, year=ns.year, min_players=ns.min_players)
        print(f"\n✅ ADP saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching ADP: {e}")
        return 1


def _fetch_ds_command(argv) -> int:
    """Fetch DraftSharks half-PPR rankings into the update folder (`ff-rankings fetch-ds`)."""
    from fantasy_pipeline.config import DEFAULT_PATHS
    from fantasy_pipeline.scraper.fetch_rankings import fetch_draftsharks

    parser = argparse.ArgumentParser(
        prog='ff-rankings fetch-ds',
        description='Fetch DraftSharks half-PPR rankings (headless browser) into the update folder'
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_PATHS['update_dir'],
        help='Directory to save the DraftSharks CSV (default: the pipeline update folder)'
    )
    parser.add_argument('--min-players', type=int, default=150,
                        help='Coverage floor — fail if fewer players are captured (default: 150)')
    ns = parser.parse_args(argv)

    try:
        os.makedirs(ns.output, exist_ok=True)
        path = fetch_draftsharks(ns.output, min_players=ns.min_players)
        print(f"\n✅ DraftSharks rankings saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching DraftSharks rankings: {e}")
        return 1


def _fetch_fp_command(argv) -> int:
    """Fetch FantasyPros consensus rankings into the update folder (`ff-rankings fetch-fp`)."""
    from fantasy_pipeline.config import DEFAULT_PATHS, CURRENT_SEASON
    from fantasy_pipeline.scraper.fetch_rankings import fetch_fantasypros_rankings

    parser = argparse.ArgumentParser(
        prog='ff-rankings fetch-fp',
        description='Fetch FantasyPros expert consensus rankings into the update folder'
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_PATHS['update_dir'],
        help='Directory to save the rankings CSV (default: the pipeline update folder)'
    )
    parser.add_argument('--year', type=int, default=CURRENT_SEASON, help='Season year for the filename')
    parser.add_argument('--scoring', choices=['ppr', 'half-ppr', 'standard'], default='ppr',
                        help='Scoring format (default: ppr)')
    parser.add_argument('--min-players', type=int, default=200,
                        help='Coverage floor — fail if fewer players parse (default: 200)')
    ns = parser.parse_args(argv)

    try:
        os.makedirs(ns.output, exist_ok=True)
        path = fetch_fantasypros_rankings(
            ns.output, year=ns.year, scoring=ns.scoring, min_players=ns.min_players
        )
        print(f"\n✅ FantasyPros rankings saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching FantasyPros rankings: {e}")
        return 1


def _fetch_pff_command(argv) -> int:
    """Fetch PFF draft rankings into the update folder (`ff-rankings fetch-pff`)."""
    from fantasy_pipeline.config import DEFAULT_PATHS, CURRENT_SEASON
    from fantasy_pipeline.scraper.fetch_rankings import fetch_pff

    parser = argparse.ArgumentParser(
        prog='ff-rankings fetch-pff',
        description='Fetch PFF draft rankings (saved session) into the update folder'
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_PATHS['update_dir'],
        help='Directory to save the PFF CSV (default: the pipeline update folder)'
    )
    parser.add_argument('--year', type=int, default=CURRENT_SEASON, help='Season year for the filename')
    parser.add_argument('--min-players', type=int, default=200,
                        help='Coverage floor — fail if fewer players are captured (default: 200)')
    ns = parser.parse_args(argv)

    try:
        os.makedirs(ns.output, exist_ok=True)
        path = fetch_pff(ns.output, year=ns.year, min_players=ns.min_players)
        print(f"\n✅ PFF rankings saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching PFF rankings: {e}")
        return 1


def _login_command(argv) -> int:
    """Interactive one-time login that persists a session (`ff-rankings login <source>`)."""
    from fantasy_pipeline.scraper.auth import login, SOURCE_LOGIN_URLS

    parser = argparse.ArgumentParser(
        prog='ff-rankings login',
        description='Log in once to a paywalled source and save the session for headless fetches'
    )
    parser.add_argument('source', choices=sorted(SOURCE_LOGIN_URLS),
                        help='Paywalled source to log in to')
    parser.add_argument('--timeout-minutes', type=int, default=10,
                        help='How long the login window stays open (default: 10)')
    ns = parser.parse_args(argv)

    try:
        login(ns.source, timeout_minutes=ns.timeout_minutes)
        return 0
    except Exception as e:
        print(f"\n❌ Login failed: {e}")
        return 1


def main(args=None):
    """
    Process fantasy football rankings.

    Args:
        args: Parsed arguments (if already parsed). If None, parses sys.argv.
              The `fetch-adp` subcommand is dispatched before rankings parsing.
    """
    # If called standalone, parse arguments
    if args is None:
        argv = sys.argv[1:]
        # Additive subcommand: `ff-rankings fetch-adp ...` (default flow is unchanged)
        if argv and argv[0] == 'fetch-adp':
            return _fetch_adp_command(argv[1:])
        # Additive subcommand: `ff-rankings fetch-ds ...` (DraftSharks headless fetch)
        if argv and argv[0] == 'fetch-ds':
            return _fetch_ds_command(argv[1:])
        # Additive subcommand: `ff-rankings fetch-fp ...` (FantasyPros consensus rankings)
        if argv and argv[0] == 'fetch-fp':
            return _fetch_fp_command(argv[1:])
        # Additive subcommand: `ff-rankings login <source> ...` (save a paywalled session)
        if argv and argv[0] == 'login':
            return _login_command(argv[1:])
        # Additive subcommand: `ff-rankings fetch-pff ...` (PFF draft rankings export)
        if argv and argv[0] == 'fetch-pff':
            return _fetch_pff_command(argv[1:])
        args = _build_rankings_parser().parse_args(argv)

    # Validate week parameter for weekly and ROS league types
    if args.league_type in ['weekly', 'ros'] and args.week is None:
        print(f"Error: --week parameter is required when --league-type is '{args.league_type}'")
        return 1

    try:
        processor = RankingsProcessor(args.league_type, args.week)

        output_file = processor.process_rankings(
            data_path=args.data_path,
            player_key_path=args.player_key_path,
            base_data_dir=args.base_data_dir,
            week=args.week,
            verbose=not args.quiet
        )

        print(f"\n✅ Success! Rankings saved to: {output_file}")
        return 0

    except Exception as e:
        print(f"\n❌ Error processing rankings: {str(e)}")
        if not args.quiet:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
