"""`ff-expert-analysis` — build and report the historical expert accuracy dataset.

    ff-expert-analysis build [--db PATH] [--no-load]
    ff-expert-analysis report [--db PATH] [--season N]

The snapshot is frozen, so `build` is a drop-and-recreate rather than an incremental load.
See `docs/expert-accuracy-analysis.md`.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from ..analysis.historical import (
    HOME_DB_PATH,
    build_expert_rankings,
    build_player_outcomes,
    load_snapshot,
)
from ..analysis.scorecard import (
    add_value_curve,
    bias_by_slice,
    conviction_calls,
    conviction_summary,
    expert_scorecard,
)


def _build(argv) -> int:
    parser = argparse.ArgumentParser(prog="ff-expert-analysis build")
    parser.add_argument("--db", default=None, help=f"SQLite path (default: {HOME_DB_PATH})")
    parser.add_argument("--no-load", action="store_true", help="Build in memory and report only; don't write the DB")
    ns = parser.parse_args(argv)

    print("📥 Building expert ranking facts...")
    rankings = build_expert_rankings()
    print("\n📊 Building realized outcomes...")
    outcomes = build_player_outcomes()

    if ns.no_load:
        print("\n⏭  --no-load set; not writing to SQLite.")
        return 0

    print("\n💾 Loading to SQLite...")
    load_snapshot(rankings, outcomes, db_path=ns.db)
    print("\n✅ Done. Query via the MCP server or:")
    print(f"   sqlite3 {ns.db or HOME_DB_PATH} 'SELECT * FROM v_expert_rank_vs_outcome LIMIT 5'")
    return 0


def _load_joined(db_path) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = Path(db_path) if db_path else HOME_DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `ff-expert-analysis build` first")
    with sqlite3.connect(path) as conn:
        joined = pd.read_sql("SELECT * FROM v_expert_rank_vs_outcome", conn)
        outcomes = pd.read_sql("SELECT * FROM player_season_outcomes", conn)
    return joined, outcomes


def _report(argv) -> int:
    parser = argparse.ArgumentParser(prog="ff-expert-analysis report")
    parser.add_argument("--db", default=None)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--metric", default="ppg_half", choices=["ppg_half", "fpts_half"])
    ns = parser.parse_args(argv)

    joined, outcomes = _load_joined(ns.db)
    if ns.season:
        joined = joined[joined["season"] == ns.season]
        outcomes = outcomes[outcomes["season"] == ns.season]

    # Positional-only boards (2024 Hayden Winks) are scored on positional rank like everyone
    # else; the rank_scope column records that their overall rank was never published.
    enriched = add_value_curve(joined, outcomes, metric=ns.metric)

    cols = [
        "season",
        "expert",
        "expert_kind",
        "n_ranked",
        "n_common",
        "spearman_full",
        "spearman_common",
        "spearman_ppg",
        "availability_effect",
        "mae_rank_common",
        "mae_points_common",
        "tier_hit_rate",
    ]

    print("=" * 78)
    print(f"EXPERT SCORECARD — all experts  (metric: {ns.metric})")
    print("=" * 78)
    print("  *_common columns are the fair head-to-head: same players for every expert.")
    print("  mae_rank grows with how many players you rank, so only the common one compares.")
    print()
    print(expert_scorecard(enriched, outcomes)[cols].round(3).to_string(index=False))

    # The cross-season set. Restricting the intersection to these gives a much larger common
    # subset than including a shallow board like Barrett's 99 players, which collapses it.
    overlap = ["fp", "pff", "ds", "hw", "adp"]
    print()
    print("=" * 78)
    print(f"EXPERT SCORECARD — cross-season overlap only ({', '.join(overlap)})")
    print("=" * 78)
    print(expert_scorecard(enriched, outcomes, experts=overlap)[cols].round(3).to_string(index=False))

    print()
    print("=" * 78)
    print("BIAS BY POSITION  (negative points error = the slot returned less than implied)")
    print("=" * 78)
    print("  No signed RANK error column: within a position it is zero by construction.")
    print()
    bias = bias_by_slice(enriched, by="pos")
    print(bias.round(3).to_string(index=False))

    print()
    print("=" * 78)
    print("CONVICTION vs ADP  (top 20% of calls by VALUE of the disagreement)")
    print("=" * 78)
    calls = conviction_calls(enriched, outcomes, metric=ns.metric)
    if calls.empty:
        print("  (no scorable calls)")
    else:
        print(conviction_summary(calls, by=["expert"]).round(3).to_string(index=False))
        print()
        print("-- by expert x position --")
        print(conviction_summary(calls, by=["expert", "pos"]).round(3).to_string(index=False))

    print()
    print("⚠️  Two seasons, ~200 players, three experts with comparable overall ranks in both.")
    print("   Differences this small are directional, not conclusive. Rows marked")
    print("   sufficient=False are below the minimum cell size — read them as anecdotes.")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    command, rest = argv[0], argv[1:]
    if command == "build":
        return _build(rest)
    if command == "report":
        return _report(rest)
    print(f"Unknown command '{command}'. Use 'build' or 'report'.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
