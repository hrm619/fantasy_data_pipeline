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


def _ensure_session_if_requested(auto_login: bool, source: str) -> bool:
    """If --auto-login is set, re-auth the source (pops a login window on expiry).

    Returns True if it's OK to proceed with the fetch, False if a needed login wasn't completed.
    """
    if not auto_login:
        return True
    from fantasy_pipeline.scraper.fetch_rankings import ensure_session
    if ensure_session(source):
        return True
    print(f"\n❌ '{source}' session invalid and login not completed.")
    return False


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
    parser.add_argument('--auto-login', action='store_true',
                        help='Open a login window if the PFF session has expired')
    ns = parser.parse_args(argv)

    try:
        if not _ensure_session_if_requested(ns.auto_login, 'pff'):
            return 1
        os.makedirs(ns.output, exist_ok=True)
        path = fetch_pff(ns.output, year=ns.year, min_players=ns.min_players)
        print(f"\n✅ PFF rankings saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching PFF rankings: {e}")
        return 1


def _refresh_all_command(argv) -> int:
    """Fetch every redraft source into update/, then consolidate (`ff-rankings refresh-all`).

    Convenience wrapper over the six redraft fetchers + the consolidation pipeline. Fetchers
    run independently: a failure (e.g. an expired paywalled session) is reported but does not
    stop the others, and consolidation still runs on whatever landed (use --strict to abort).

    Note: redraft consolidation also requires Hayden Winks (tableDownload.csv), which has no
    automated fetcher (no stable URL) and must be downloaded manually into update/. If it's
    absent, the fetch still runs and consolidation is skipped with instructions.
    """
    from fantasy_pipeline.config import DEFAULT_PATHS, CURRENT_SEASON
    from fantasy_pipeline import RankingsProcessor
    from fantasy_pipeline.scraper.fetch_rankings import (
        fetch_fantasypros_adp,
        fetch_fantasypros_rankings,
        fetch_draftsharks,
        fetch_pff,
        fetch_fpts,
        fetch_jj,
    )

    parser = argparse.ArgumentParser(
        prog='ff-rankings refresh-all',
        description='Fetch all redraft sources into update/, then consolidate into latest/'
    )
    parser.add_argument('--data-path', default=None,
                        help='Update directory the fetchers write to and the pipeline reads '
                             '(default: the standard update/ folder)')
    parser.add_argument('--base-data-dir', default=None,
                        help='Base data dir containing latest/update/archive folders')
    parser.add_argument('--year', type=int, default=CURRENT_SEASON,
                        help='Season year for source filenames')
    parser.add_argument('--no-consolidate', action='store_true',
                        help='Only fetch the sources; skip the consolidation step')
    parser.add_argument('--strict', action='store_true',
                        help='Abort before consolidating if any fetcher failed')
    parser.add_argument('--auto-login', action='store_true',
                        help='For paywalled sources, auto-open a login window if the session expired')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress verbose consolidation output')
    ns = parser.parse_args(argv)

    update_dir = ns.data_path or DEFAULT_PATHS['update_dir']
    os.makedirs(update_dir, exist_ok=True)

    # (label, source, thunk) — each thunk writes one source file into update_dir. `source`
    # is the paywalled-session key (None for free sources). These are the redraft fetchers;
    # weekly/ROS HW is auto-scraped by the pipeline itself.
    fetchers = [
        ('adp  (FantasyPros ADP)',       None,   lambda: fetch_fantasypros_adp(update_dir, year=ns.year)),
        ('fp   (FantasyPros rankings)',  None,   lambda: fetch_fantasypros_rankings(update_dir, year=ns.year)),
        ('ds   (DraftSharks)',           None,   lambda: fetch_draftsharks(update_dir)),
        ('pff  (PFF)',                   'pff',  lambda: fetch_pff(update_dir, year=ns.year)),
        ('fpts (FantasyPoints/Barrett)', 'fpts', lambda: fetch_fpts(update_dir, year=ns.year)),
        ('jj   (JJ Zachariason)',        'jj',   lambda: fetch_jj(update_dir, year=ns.year)),
    ]

    print(f"🔄 Refreshing {len(fetchers)} redraft sources into: {update_dir}\n")
    results = []
    for label, source, thunk in fetchers:
        # With --auto-login, re-auth a paywalled source up front if its session expired
        # (pops a login window) so the fetch below doesn't fail on a stale session.
        if source and ns.auto_login:
            from fantasy_pipeline.scraper.fetch_rankings import ensure_session
            if not ensure_session(source):
                results.append((label, False, 'session invalid; login not completed'))
                print(f"   ❌ {label} — session invalid; skipped")
                continue
        try:
            thunk()
            results.append((label, True, ''))
            print(f"   ✅ {label}")
        except Exception as e:
            detail = str(e).splitlines()[0] if str(e) else type(e).__name__
            results.append((label, False, detail))
            print(f"   ❌ {label} — {detail}")

    failed = [(label, detail) for label, ok, detail in results if not ok]
    print(f"\n📥 Fetched {len(results) - len(failed)}/{len(results)} sources.")
    if failed:
        if any(kw in d.lower() for _, d in failed for kw in ('session', 'login', 'timeout')):
            print("   Tip: paywalled sources may need a fresh session — "
                  "`ff-rankings login <pff|fpts|jj>`.")

    if ns.no_consolidate:
        print("\n⏭  --no-consolidate set; leaving the fetched files in update/ (not consolidating).")
        return 1 if failed else 0
    if failed and ns.strict:
        print("\n⛔ --strict set and some fetchers failed; not consolidating.")
        return 1

    # Redraft consolidation also needs Hayden Winks (tableDownload.csv), which has no
    # automated fetcher (no stable redraft URL) and must be downloaded manually. Check it
    # up front so we fail helpfully instead of with a cryptic "No file found for key 'hw'".
    if not any(f.startswith("tableDownload") for f in os.listdir(update_dir)):
        print("\n⚠️  Can't consolidate yet — redraft requires a manual source with no fetcher:")
        print("     - hw (Hayden Winks) → tableDownload.csv")
        print("   It has no automated fetcher (no stable Underdog URL). Download it from")
        print("   Underdog ('Table Download') as tableDownload.csv into update/, then run:")
        print("     ff-rankings --league-type redraft")
        print("\n⏭  The 6 automated sources are fetched and waiting in update/; skipping consolidation.")
        return 1

    print("\n🧮 Consolidating redraft rankings...")
    try:
        processor = RankingsProcessor('redraft')
        output_file = processor.process_rankings(
            data_path=ns.data_path,
            base_data_dir=ns.base_data_dir,
            verbose=not ns.quiet,
        )
        print(f"\n✅ Combined rankings saved to: {output_file}")
        return 1 if failed else 0
    except Exception as e:
        print(f"\n❌ Consolidation failed: {e}")
        return 1


def _fetch_jj_command(argv) -> int:
    """Fetch JJ Zachariason's redraft xlsx into the update folder (`ff-rankings fetch-jj`)."""
    from fantasy_pipeline.config import DEFAULT_PATHS, CURRENT_SEASON
    from fantasy_pipeline.scraper.fetch_rankings import fetch_jj

    parser = argparse.ArgumentParser(
        prog='ff-rankings fetch-jj',
        description="Download JJ Zachariason's Patreon redraft xlsx (saved session) into the update folder"
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_PATHS['update_dir'],
        help='Directory to save the JJ xlsx (default: the pipeline update folder)'
    )
    parser.add_argument('--post-url', default=None,
                        help='Specific Patreon post URL (default: auto-discover the latest 1QB redraft)')
    parser.add_argument('--year', type=int, default=CURRENT_SEASON, help='Season year for the filename')
    parser.add_argument('--min-players', type=int, default=150,
                        help='Coverage floor — fail if fewer players are found (default: 150)')
    parser.add_argument('--auto-login', action='store_true',
                        help='Open a login window if the Patreon session has expired')
    ns = parser.parse_args(argv)

    try:
        if not _ensure_session_if_requested(ns.auto_login, 'jj'):
            return 1
        os.makedirs(ns.output, exist_ok=True)
        path = fetch_jj(ns.output, post_url=ns.post_url, year=ns.year, min_players=ns.min_players)
        print(f"\n✅ JJ rankings saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching JJ rankings: {e}")
        return 1


def _fetch_fpts_command(argv) -> int:
    """Fetch FantasyPoints (Scott Barrett) rankings into the update folder (`ff-rankings fetch-fpts`)."""
    from fantasy_pipeline.config import DEFAULT_PATHS, CURRENT_SEASON
    from fantasy_pipeline.scraper.fetch_rankings import fetch_fpts, FPTS_RANKINGS_URL

    parser = argparse.ArgumentParser(
        prog='ff-rankings fetch-fpts',
        description='Fetch FantasyPoints (Scott Barrett) rankings (saved session) into the update folder'
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_PATHS['update_dir'],
        help='Directory to save the FantasyPoints CSV (default: the pipeline update folder)'
    )
    parser.add_argument('--year', type=int, default=CURRENT_SEASON, help='Season year for the filename')
    parser.add_argument('--min-players', type=int, default=90,
                        help='Coverage floor — fail if fewer players are captured (default: 90)')
    parser.add_argument('--url', default=FPTS_RANKINGS_URL,
                        help='Rankings page to export from (override for live verification)')
    parser.add_argument('--auto-login', action='store_true',
                        help='Open a login window if the FantasyPoints session has expired')
    ns = parser.parse_args(argv)

    try:
        if not _ensure_session_if_requested(ns.auto_login, 'fpts'):
            return 1
        os.makedirs(ns.output, exist_ok=True)
        path = fetch_fpts(ns.output, year=ns.year, min_players=ns.min_players, rankings_url=ns.url)
        print(f"\n✅ FantasyPoints rankings saved to: {path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error fetching FantasyPoints rankings: {e}")
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
        # Additive subcommand: `ff-rankings fetch-fpts ...` (FantasyPoints/Scott Barrett export)
        if argv and argv[0] == 'fetch-fpts':
            return _fetch_fpts_command(argv[1:])
        # Additive subcommand: `ff-rankings fetch-jj ...` (JJ Zachariason Patreon xlsx)
        if argv and argv[0] == 'fetch-jj':
            return _fetch_jj_command(argv[1:])
        # Additive subcommand: `ff-rankings refresh-all ...` (fetch every source + consolidate)
        if argv and argv[0] == 'refresh-all':
            return _refresh_all_command(argv[1:])
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
