"""Scoring expert rankings against realized outcomes.

Three error spaces, because rank error alone is misleading: ranks are not equally spaced in
value. Missing by four ranks at RB3 is a different mistake from missing by four at RB30, and
an expert can be right about a player's tier of production while wrong on the literal rank.

  rank space    what they literally claimed  (Spearman, MAE, top-N hit rate)
  points space  what the claim was worth     (error vs the realized value curve, in PPG)
  tier space    the readable version         (did they land the right tier)

See `docs/expert-accuracy-analysis.md` for the design and its statistical limits — in
particular, this module reports coverage next to every metric because comparing experts who
ranked different numbers of players is the easiest way to get a wrong answer here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# A player must clear this to get a per-game score. Placeholder — sensitivity-check it.
MIN_GAMES_FOR_PPG = 8

# Cells thinner than this report as insufficient rather than as a number. expert x position
# x draft-region over two seasons produces very small groups.
MIN_CELL_SIZE = 10

# Draft regions in overall-pick terms (12-team).
DRAFT_REGIONS = [("rounds 1-3", 1, 36), ("rounds 4-8", 37, 96), ("rounds 9+", 97, 10_000)]


def realized_value_curve(outcomes: pd.DataFrame, metric: str = "ppg_half") -> pd.DataFrame:
    """The realized outcome at each positional rank, per (season, position).

    `curve[k]` is what the k-th best player at that position actually produced. This is the
    thing an expert is implicitly forecasting when they rank a player k-th: not "this exact
    player" but "a player who returns the k-th best outcome".

    Also returns `slope` — the local change in value per rank. That is precisely the quantity
    that makes rank error and points error diverge: where slope is ~0 a large rank miss costs
    nothing (the "spiritually correct" case), where it is steep a small miss is expensive.
    """
    frames = []
    for _, group in outcomes.groupby(["season", "pos"], sort=False):
        ordered = group.sort_values(metric, ascending=False).reset_index(drop=True)
        curve = pd.DataFrame(
            {
                "season": group["season"].iloc[0],
                "pos": group["pos"].iloc[0],
                "curve_rank": np.arange(1, len(ordered) + 1),
                "curve_value": ordered[metric].to_numpy(),
            }
        )
        # Central difference where possible; value lost per one rank of slippage.
        values = curve["curve_value"].to_numpy(dtype=float)
        slope = np.full(len(values), np.nan)
        if len(values) > 2:
            slope[1:-1] = (values[:-2] - values[2:]) / 2.0
            slope[0] = values[0] - values[1]
            slope[-1] = values[-2] - values[-1]
        elif len(values) == 2:
            slope[:] = values[0] - values[1]
        curve["slope"] = slope
        frames.append(curve)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def assign_tiers(outcomes: pd.DataFrame, metric: str = "ppg_half", max_tiers: int = 8) -> pd.DataFrame:
    """Segment realized outcomes into tiers per (season, position) by largest gaps.

    Tiers are derived from OUTCOMES, after the fact — never hand-picked, which would let the
    boundaries be chosen to produce a conclusion. Breaks go at the largest drops in the sorted
    value curve.

    `boundary_distance` is returned alongside because tier membership is knife-edge: a player
    a tenth of a point from a break flips tiers, and a tier-hit rate reads as far more precise
    than it is. Treat a small boundary_distance as "this player's tier is arbitrary".
    """
    frames = []
    for _, group in outcomes.groupby(["season", "pos"], sort=False):
        ordered = group.sort_values(metric, ascending=False).copy()
        values = ordered[metric].to_numpy(dtype=float)
        if len(values) < 2:
            ordered["tier"] = 1
            ordered["boundary_distance"] = np.nan
            frames.append(ordered[["season", "player_id", "tier", "boundary_distance"]])
            continue

        gaps = values[:-1] - values[1:]
        n_breaks = min(max_tiers - 1, max(1, len(values) // 12))
        break_idx = sorted(np.argsort(gaps)[-n_breaks:])

        tier = np.ones(len(values), dtype=int)
        for b in break_idx:
            tier[b + 1 :] += 1
        ordered["tier"] = tier

        # Distance to whichever break (above or below) is nearest in value terms.
        edges = [values[b] for b in break_idx] + [values[b + 1] for b in break_idx]
        ordered["boundary_distance"] = [min(abs(v - e) for e in edges) if edges else np.nan for v in values]
        frames.append(ordered[["season", "player_id", "tier", "boundary_distance"]])

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def add_value_curve(joined: pd.DataFrame, outcomes: pd.DataFrame, metric: str = "ppg_half") -> pd.DataFrame:
    """Attach, per ranked player: the value their slot implied, and the error against it.

    `implied_value` is `curve[expert's positional rank]`. `points_error` is what the player
    actually produced minus that — the mispricing in metric units. Positive means the player
    beat the slot he was put in.
    """
    curve = realized_value_curve(outcomes, metric=metric)
    tiers = assign_tiers(outcomes, metric=metric)

    df = joined.copy()
    df = df.merge(
        curve.rename(columns={"curve_rank": "pos_rank", "curve_value": "implied_value", "slope": "curve_slope"}),
        on=["season", "pos", "pos_rank"],
        how="left",
    )
    df = df.merge(tiers.rename(columns={"tier": "realized_tier"}), on=["season", "player_id"], how="left")

    # The tier the expert's own slot implied: whatever tier the player who actually finished
    # at that rank landed in.
    slot_tier = (
        outcomes.merge(tiers, on=["season", "player_id"])
        .rename(columns={"pos_finish_rank": "pos_rank", "tier": "implied_tier"})[
            ["season", "pos", "pos_rank", "implied_tier"]
        ]
        .drop_duplicates(["season", "pos", "pos_rank"])
    )
    df = df.merge(slot_tier, on=["season", "pos", "pos_rank"], how="left")

    df["points_error"] = df[metric] - df["implied_value"]

    # Realized rank WITHIN the set this expert ranked. Comparing against the league-wide
    # pos_finish_rank is not like-for-like: experts rank ~217 players while the outcome
    # universe is ~620, so a player placed WR30 "finishes WR45 of 180" and every expert looks
    # uniformly optimistic by ~10 ranks. Both sides must be permutations of the same set.
    df["pos_finish_rank_in_set"] = (
        df[df[metric].notna()].groupby(["season", "expert", "pos"])[metric].rank(ascending=False, method="min")
    )
    df["rank_error"] = df["pos_rank"] - df["pos_finish_rank_in_set"]
    df["tier_hit"] = (df["implied_tier"] == df["realized_tier"]).where(
        df["implied_tier"].notna() & df["realized_tier"].notna()
    )
    return df


def _spearman(a: pd.Series, b: pd.Series) -> float:
    ok = a.notna() & b.notna()
    if ok.sum() < 3:
        return float("nan")
    return float(a[ok].rank().corr(b[ok].rank()))


def expert_scorecard(
    joined: pd.DataFrame,
    outcomes: pd.DataFrame,
    experts: Optional[List[str]] = None,
    min_games: int = MIN_GAMES_FOR_PPG,
) -> pd.DataFrame:
    """One row per (season, expert): accuracy in all three spaces, on two player sets.

    Metrics are reported twice over in two independent ways:

    * TOTAL vs PER-GAME. The gap between them is the availability effect — it isolates who
      systematically over- or under-rates injury-prone players (CMC 2024: ranked ~1, played 4).
    * FULL board vs COMMON subset. `*_full` uses everything the expert ranked; `*_common`
      restricts to players every compared expert ranked. Only the latter is a fair head-to-head:
      DraftSharks ranked 147 of 217 in 2024 while FantasyPros ranked all 217, and ranking fewer
      players means ranking the safer ones, which flatters raw error.

    `experts` limits which boards define the common subset. That matters — Scott Barrett ranked
    only 98 players in 2025, so including him collapses the intersection for everyone else.
    """
    rows: List[Dict] = []

    for season, season_block in joined.groupby("season"):
        scored = season_block[season_block["pos_rank"].notna() & season_block["pos_finish_rank_in_set"].notna()]
        if experts:
            scored = scored[scored["expert"].isin(experts)]
        per_expert = [set(g["player_id"]) for _, g in scored.groupby("expert")]
        subset_ids = set.intersection(*per_expert) if per_expert else set()

        for expert, block in scored.groupby("expert"):
            comp = block[block["player_id"].isin(subset_ids)]
            played_full = block[block["games"] >= min_games]
            played_comp = comp[comp["games"] >= min_games]

            spearman_total = _spearman(block["pos_rank"], block["pos_finish_rank_in_set"])
            spearman_ppg = _spearman(played_full["pos_rank"], played_full["pos_finish_rank_in_set"])
            rows.append(
                {
                    "season": season,
                    "expert": expert,
                    "expert_kind": block["expert_kind"].iloc[0],
                    "rank_scope": block["rank_scope"].iloc[0],
                    "n_ranked": len(block),
                    "n_common": len(comp),
                    "n_ppg_eligible": len(played_full),
                    # rank space
                    "spearman_full": spearman_total,
                    "spearman_common": _spearman(comp["pos_rank"], comp["pos_finish_rank_in_set"]),
                    "spearman_ppg": spearman_ppg,
                    "mae_rank": block["rank_error"].abs().mean(),
                    "mae_rank_common": comp["rank_error"].abs().mean(),
                    # points space — the "spiritually correct" view
                    "mae_points": block["points_error"].abs().mean(),
                    "mae_points_common": comp["points_error"].abs().mean(),
                    "bias_points": block["points_error"].mean(),
                    # tier space
                    "tier_hit_rate": block["tier_hit"].mean(),
                    # availability: how much better they look once injuries are removed
                    "availability_effect": (
                        spearman_ppg - spearman_total
                        if pd.notna(spearman_ppg) and pd.notna(spearman_total)
                        else float("nan")
                    ),
                    "_ppg_common": _spearman(played_comp["pos_rank"], played_comp["pos_finish_rank_in_set"]),
                }
            )

    out = pd.DataFrame(rows).drop(columns=["_ppg_common"])
    return out.sort_values(["season", "spearman_common"], ascending=[True, False]).reset_index(drop=True)


def bias_by_slice(joined: pd.DataFrame, by: str = "pos", min_cell: int = MIN_CELL_SIZE) -> pd.DataFrame:
    """Error per (season, expert, slice), for detecting systematic lean.

    Note there is deliberately no signed RANK error here: within a position, the expert's ranks
    and the realized ranks are permutations of the same set, so the signed mean is exactly zero
    by construction and would read as "no bias" for everyone. Signed **points** error is the
    one that carries the answer — it compares each slot against what that slot actually
    returned, and is free to be non-zero.

    `mean_points_error` is in the metric's units for that position, so it compares cleanly
    ACROSS EXPERTS within a position. Comparing across positions needs care: 1 PPG means more
    to a TE than to a QB. `mean_implied_value` is included so the scale is visible.

    Cells below `min_cell` are flagged `sufficient=False` rather than dropped, so a thin slice
    is visibly thin instead of quietly absent.
    """
    grouped = joined.groupby(["season", "expert", by])
    out = grouped.agg(
        n=("player_id", "size"),
        mae_rank=("rank_error", lambda s: s.abs().mean()),
        mean_points_error=("points_error", "mean"),
        mean_implied_value=("implied_value", "mean"),
        tier_hit_rate=("tier_hit", "mean"),
    ).reset_index()
    out["sufficient"] = out["n"] >= min_cell
    return out


def draft_region(overall_rank: float) -> Optional[str]:
    if pd.isna(overall_rank):
        return None
    for label, lo, hi in DRAFT_REGIONS:
        if lo <= overall_rank <= hi:
            return label
    return None


def conviction_calls(
    joined: pd.DataFrame,
    outcomes: pd.DataFrame,
    reference: str = "adp",
    metric: str = "ppg_half",
    top_quantile: float = 0.8,
) -> pd.DataFrame:
    """Where an expert departed sharply from the market, and whether it paid.

    The delta is measured in VALUE, not ranks: `curve[reference_rank] - curve[expert_rank]`.
    Ten ranks at the top of the board is a large claim; ten ranks at pick 150 is rounding.
    Selecting big calls by rank distance would over-sample the late rounds and make every
    expert look boldest exactly where it matters least.

    `value_added` is the player's realized value minus what the reference's slot implied, so a
    call is `correct` when the expert leaned the direction the outcome went.
    """
    ref = joined[joined["expert"] == reference][["season", "player_id", "pos_rank", "implied_value"]].rename(
        columns={"pos_rank": "ref_pos_rank", "implied_value": "ref_implied_value"}
    )
    df = joined[joined["expert"] != reference].merge(ref, on=["season", "player_id"], how="inner")

    df["delta_rank"] = df["ref_pos_rank"] - df["pos_rank"]  # positive = expert higher than market
    df["delta_value"] = df["implied_value"] - df["ref_implied_value"]
    df["value_added"] = df[metric] - df["ref_implied_value"]
    df["correct"] = np.sign(df["value_added"]) == np.sign(df["delta_rank"])
    df["region"] = df["ref_pos_rank"].map(draft_region)

    scored = df[df["delta_value"].notna() & df[metric].notna()].copy()
    if scored.empty:
        return scored

    # Take the threshold among actual DISAGREEMENTS. Players an expert placed exactly where
    # the market did carry delta_value == 0; leaving them in the basis drags the quantile
    # toward zero and promotes trivial calls into "big" ones.
    disagreements = scored.loc[scored["delta_value"] != 0, "delta_value"].abs()
    cutoff = disagreements.quantile(top_quantile) if not disagreements.empty else float("inf")
    scored["is_big_call"] = (scored["delta_value"].abs() >= cutoff) & (scored["delta_value"] != 0)
    return scored


def conviction_summary(calls: pd.DataFrame, by: Optional[List[str]] = None, min_cell: int = MIN_CELL_SIZE):
    """Hit rate and mean value added per big call, sliced.

    Small cells are flagged, not hidden: expert x position x region over two seasons is where
    this analysis most easily manufactures a confident wrong answer.
    """
    by = by or ["expert"]
    big = calls[calls["is_big_call"]]
    out = (
        big.groupby(by)
        .agg(
            n_calls=("player_id", "size"),
            hit_rate=("correct", "mean"),
            mean_value_added=("value_added", "mean"),
            mean_delta_value=("delta_value", "mean"),
        )
        .reset_index()
    )
    out["sufficient"] = out["n_calls"] >= min_cell
    return out.sort_values("hit_rate", ascending=False).reset_index(drop=True)
