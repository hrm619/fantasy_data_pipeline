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
    MIN_GAMES_FOR_PPG,
    add_value_curve,
    bias_by_slice,
    conviction_calls,
    conviction_summary,
    expert_scorecard,
    positional_bias,
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
    # Sensitivity-checked over 4-14 and it is NOT load-bearing: spearman_ppg moves at most
    # 0.045 across floors 4-12 (inside the ~0.05 noise band), and the only ordering changes
    # are between pairs whose intervals already overlap completely. Exposed so that stays
    # checkable rather than becoming a buried assumption again.
    parser.add_argument(
        "--min-games",
        type=int,
        default=MIN_GAMES_FOR_PPG,
        help=f"games-played floor for per-game scoring (default {MIN_GAMES_FOR_PPG}; not load-bearing)",
    )
    ns = parser.parse_args(argv)

    joined, outcomes = _load_joined(ns.db)
    if ns.season:
        joined = joined[joined["season"] == ns.season]
        outcomes = outcomes[outcomes["season"] == ns.season]

    # Positional-only boards (2024 Hayden Winks) are scored on positional rank like everyone
    # else; the rank_scope column records that their overall rank was never published.
    enriched = add_value_curve(joined, outcomes, metric=ns.metric)

    def _display(card: pd.DataFrame) -> pd.DataFrame:
        """Fold the bootstrap bounds into readable [lo, hi] strings.

        The interval is shown NEXT TO the point estimate, never instead of it, because the
        whole point is that the gaps between experts are smaller than their intervals.
        """
        out = card.copy()
        for stat, lo, hi in (
            ("spearman_common", "spearman_common_lo", "spearman_common_hi"),
            ("tier_stability", "tier_stability_lo", "tier_stability_hi"),
        ):
            if lo in out.columns:
                out[f"{stat}_95ci"] = [
                    "n/a" if pd.isna(a) or pd.isna(b) else f"[{a:.2f}, {b:.2f}]" for a, b in zip(out[lo], out[hi])
                ]
        return out

    cols = [
        "season",
        "expert",
        "expert_kind",
        "n_ranked",
        "n_common",
        "spearman_common",
        "spearman_common_95ci",
        "spearman_ppg",
        "availability_effect",
        "mae_rank_common",
        "mae_points_common",
        "median_curve_slope",
    ]

    # Tier space is a PRESENTATION layer, not a result — §3c showed largest-gap segmentation
    # does not survive resampling, with point estimates falling outside their own stability
    # range. It is printed in its own block rather than beside the accuracy metrics, so a
    # readable-but-unreliable number cannot be mistaken for a load-bearing one.
    tier_cols = [
        "season",
        "expert",
        "n_ranked",
        "tier_hit_rate",
        "tier_stability_95ci",
        "tier_edge_median",
    ]

    print("=" * 78)
    print(f"EXPERT SCORECARD — all experts  (metric: {ns.metric})")
    print("=" * 78)
    print("  *_common columns are the fair head-to-head: same players for every expert.")
    print("  mae_rank grows with how many players you rank, so only the common one compares.")
    print("  spearman_common_95ci is a percentile bootstrap over players. Where two experts'")
    print("  intervals overlap, the gap between their point estimates is not evidence.")
    print("  mae_points is priced against each expert's OWN board, so a deeper board neither")
    print("  helps nor hurts. median_curve_slope is PPG per rank where that expert worked —")
    print("  a flat curve is why a big rank miss can cost almost nothing.")
    print()
    print(
        _display(expert_scorecard(enriched, outcomes, metric=ns.metric, min_games=ns.min_games))[cols]
        .round(3)
        .to_string(index=False)
    )

    # The cross-season set. Restricting the intersection to these gives a much larger common
    # subset than including a shallow board like Barrett's 99 players, which collapses it.
    # hw joined this set once hw-2024.csv supplied his overall ranks — the snapshot had him
    # positional-only, which is why the design doc lists him as a special case.
    overlap = ["fp", "pff", "ds", "hw", "adp"]
    print()
    print("=" * 78)
    print(f"EXPERT SCORECARD — cross-season overlap only ({', '.join(overlap)})")
    print("=" * 78)
    print("  2023 has only hw, so its 'common subset' is just hw's own board — not a")
    print("  head-to-head. Read the 2023 row as a solo accuracy record.")
    print()
    print(
        _display(expert_scorecard(enriched, outcomes, experts=overlap, metric=ns.metric, min_games=ns.min_games))[cols]
        .round(3)
        .to_string(index=False)
    )

    print()
    print("=" * 78)
    print("TIER SPACE  (presentation only — see the caveat)")
    print("=" * 78)
    print("  tier_stability_95ci is NOT a confidence interval. It is how far the hit rate moves")
    print("  when the tier breaks are re-derived from a resample, and the point estimate often")
    print("  falls OUTSIDE it. That is the finding: largest-gap segmentation is unstable, so")
    print("  tier hit-rate is a property of one particular set of breaks, not of the expert.")
    print("  tier_edge_median = median distance to the nearest break, in metric units; small")
    print("  means those hits rest on an arbitrary line. Prefer points space for anything")
    print("  load-bearing — it needs no boundaries and so cannot inherit this.")
    print()
    print(
        _display(expert_scorecard(enriched, outcomes, metric=ns.metric, min_games=ns.min_games))[tier_cols]
        .round(3)
        .to_string(index=False)
    )

    print()
    print("=" * 78)
    print("POSITIONAL BIAS  (signed, cross-positional, in value-over-replacement)")
    print("=" * 78)
    print("  READ THE _vs_ref COLUMN, NOT THE RAW ONE. Every expert and every market carries")
    print("  the same large shared offset (TE strongly positive, QB strongly negative) because")
    print("  the VOR baselines interact with how deep each position is drafted — that is the")
    print("  replacement levels talking, not anyone's judgement. Differencing against consensus")
    print("  ADP cancels it, on the players both ranked, so coverage cannot move it either.")
    print("  Positive = that position returned MORE than the overall slots the expert spent on")
    print("  it, i.e. the expert under-drafted it relative to the market.")
    print()
    print("  There is no signed POINTS error by position: within a position the expert's ranks")
    print("  and the realized ranks are permutations of the same set, so it is exactly zero by")
    print("  construction. The earlier non-zero version was measuring board depth.")
    print()
    print(positional_bias(enriched, reference="adp").round(2).to_string(index=False))

    print()
    print("=" * 78)
    print("ERROR MAGNITUDE BY POSITION")
    print("=" * 78)
    print()
    print(bias_by_slice(enriched, by="pos").round(3).to_string(index=False))

    # Two markets, reported separately and never pooled. `adp` is redraft consensus ADP;
    # `adp_underdog` is Underdog BEST-BALL ADP, which prices a different game (best-ball pays
    # for weekly spikes and never starts anyone, so it bids up high-variance pass-catchers).
    # They correlate 0.965 where both exist — close enough to be tempting, not close enough
    # to be the same bet. 2024 carries both, so the gap can be measured rather than assumed.
    #
    # `fp` rides along as a third reference: diverging from the expert CONSENSUS and diverging
    # from the MARKET are different bets, and only one of them is a price.
    references = (
        ("adp", "consensus redraft ADP — a market"),
        ("adp_underdog", "Underdog BEST-BALL ADP — a different market"),
        ("fp", "FantasyPros ECR — the expert consensus, not a price"),
    )
    for reference, label in references:
        calls = conviction_calls(enriched, outcomes, reference=reference, metric=ns.metric)
        print()
        print("=" * 78)
        print(f"CONVICTION vs {reference.upper()}  ({label})")
        print("=" * 78)
        if calls.empty:
            print("  (no scorable calls)")
            continue
        seasons = ", ".join(str(s) for s in sorted(calls["season"].unique()))
        print(f"  Top 20% of calls by VALUE of the disagreement. Seasons covered: {seasons}.")
        print("  Priced on the set both boards ranked, so value_added averages exactly zero")
        print("  over ALL calls and the sign test is a fair coin. NOT comparable across blocks.")
        print("  READ hit_rate_vs_pool, NOT hit_rate. The sign test gets mechanically easier as")
        print("  the disagreement grows — pooled over every expert it runs 0.38 / 0.53 / 0.62 /")
        print("  0.75 across |delta_value| quartiles — so selecting the top 20% puts everyone")
        print("  above a coin flip. Only the difference from the pooled rate is about the expert.")
        print()
        print(conviction_summary(calls, by=["expert"]).round(3).to_string(index=False))
        print()
        print("-- by expert x position --")
        print(conviction_summary(calls, by=["expert", "pos"]).round(3).to_string(index=False))
        print()
        print("-- by expert x draft region (reference's OVERALL pick, 12-team) --")
        region_summary = conviction_summary(calls, by=["expert", "region"])
        if region_summary.empty:
            print("  (no scorable calls with an overall rank on the reference board)")
        else:
            print(region_summary.round(3).to_string(index=False))

    print()
    print("⚠️  Three seasons, ~250 players each, four experts with comparable overall ranks")
    print("   in 2024-2025 (2023 is hw only). Differences this small are directional, not")
    print("   conclusive — check whether the 95% CIs overlap before believing an ordering.")
    print("   Rows marked sufficient=False are below the minimum cell size: anecdotes.")
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
