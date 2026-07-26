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


def _in_set_curve(frame: pd.DataFrame, value_col: str, rank_col: str) -> pd.Series:
    """Assign each row the value its slot implied, pricing against THIS set only.

    The curve is the group's own realized values sorted descending; a row ranked r-th gets
    the r-th best outcome in the group. Ranks are re-densified (`method="first"`) so gaps and
    ties in the published board can't index off the end of the curve.

    Returns a Series over the scorable rows only — callers align it back by index.
    """
    ok = frame[value_col].notna() & frame[rank_col].notna()
    sub = frame[ok]
    if sub.empty:
        return pd.Series(dtype=float)
    curve = np.sort(sub[value_col].to_numpy(dtype=float))[::-1]
    slot = sub[rank_col].rank(method="first").astype(int).to_numpy()
    return pd.Series(curve[slot - 1], index=sub.index)


def add_in_set_curves(joined: pd.DataFrame, metric: str = "ppg_half") -> pd.DataFrame:
    """Price every board against ITSELF, positionally and overall.

    The league-wide curve (`realized_value_curve`) prices a ~250-player board against a
    ~620-player outcome universe, so `curve[r]` is the r-th best of everybody while `r` is a
    rank among a much smaller set. The r-th best of a superset beats the r-th best of the
    subset, so the resulting signed error is negative for every expert in every position —
    and its magnitude tracks BOARD DEPTH, not bias. PFF's 2025 board (426 scorable vs ~240
    for everyone else) reads as the least biased at WR purely for reaching deeper into the
    curve. This is the same defect `pos_finish_rank_in_set` fixes in rank space; points space
    never got the equivalent treatment.

    Two curves are attached, and the difference between them is the whole point:

    * `implied_value_in_set` / `points_error_in_set` — per (season, expert, pos). Correct for
      MAGNITUDE (`mae`), but its signed mean is **exactly zero by construction**: within a
      position the expert's ranks and the realized ranks are permutations of the same set.
      That is why `bias_by_slice` no longer reports a signed positional points error, and why
      the design doc's claim that signed points error "carries the answer" where signed rank
      error cannot was wrong — both are degenerate in exactly the same way.
    * `implied_vor` / `vor_error` — per (season, expert), on the OVERALL board in
      value-over-replacement units. Here the permutation constraint binds at board level
      rather than within a position, so the total is zero while the per-position means are
      free to move. That is the real bias signal: an expert who spends top overall slots on
      RBs runs negative on RB and positive elsewhere. VOR (not PPG) because anything keyed on
      overall rank mixes positions, and 18 PPG is replaceable for a QB and elite for an RB.
    """
    df = joined.copy()

    def _attach(keys: List[str], value_col: str, rank_col: str, out_col: str) -> None:
        # An explicit loop rather than groupby.apply: apply re-keys the result to a MultiIndex
        # when a group returns a shorter Series (which happens whenever a group has unscorable
        # rows), and the assignment back would silently misalign.
        df[out_col] = np.nan
        if df.empty or value_col not in df.columns or rank_col not in df.columns:
            return
        for _, group in df.groupby(keys, sort=False):
            priced = _in_set_curve(group, value_col, rank_col)
            if len(priced):
                df.loc[priced.index, out_col] = priced.to_numpy(dtype=float)

    _attach(["season", "expert", "pos"], metric, "pos_rank", "implied_value_in_set")
    df["points_error_in_set"] = df[metric] - df["implied_value_in_set"]

    _attach(["season", "expert"], "value_over_replacement", "overall_rank", "implied_vor")
    df["vor_error"] = (
        df["value_over_replacement"] - df["implied_vor"] if "value_over_replacement" in df.columns else np.nan
    )
    return df


def add_value_curve(joined: pd.DataFrame, outcomes: pd.DataFrame, metric: str = "ppg_half") -> pd.DataFrame:
    """Attach, per ranked player: the value their slot implied, and the error against it.

    `implied_value` is `curve[expert's positional rank]` against the LEAGUE-WIDE outcome
    curve, and `points_error` is the mispricing against it. Both are retained because the
    league curve is the right reference for "what was available at this slot in the whole
    population" — but neither is safe to average signed, because the expert's rank and the
    curve's index are on different scales. See `add_in_set_curves`, which is applied here and
    supplies the depth-invariant versions the scorecard actually reports.
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
    return add_in_set_curves(df, metric=metric)


def _spearman(a: pd.Series, b: pd.Series) -> float:
    ok = a.notna() & b.notna()
    if ok.sum() < 3:
        return float("nan")
    return float(a[ok].rank().corr(b[ok].rank()))


def _spearman_ci(a: pd.Series, b: pd.Series, n_boot: int, rng, alpha: float = 0.05):
    """Percentile bootstrap interval for Spearman, resampling PLAYERS with replacement.

    Without this the scorecard prints a clean descending ranking of experts whose whole
    spread sits inside the noise band the design doc already warns about (differences below
    ~0.05 are indistinguishable at this sample size). A point estimate invites exactly the
    conclusion the data cannot support; the interval makes the overlap impossible to miss.
    """
    ok = a.notna() & b.notna()
    x, y = a[ok].to_numpy(dtype=float), b[ok].to_numpy(dtype=float)
    n = len(x)
    if n < 5:
        return float("nan"), float("nan")

    stats = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        xs, ys = x[idx], y[idx]
        # A resample can draw a constant vector; corrcoef would emit a divide warning and NaN.
        if len(np.unique(xs)) < 2 or len(np.unique(ys)) < 2:
            stats[i] = np.nan
            continue
        stats[i] = np.corrcoef(_rankdata(xs), _rankdata(ys))[0, 1]

    good = stats[~np.isnan(stats)]
    if len(good) < max(10, n_boot // 10):
        return float("nan"), float("nan")
    return float(np.quantile(good, alpha / 2)), float(np.quantile(good, 1 - alpha / 2))


def _rankdata(values: np.ndarray) -> np.ndarray:
    """Average-tie ranks, equivalent to scipy.stats.rankdata (scipy is not a dependency)."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(1, len(values) + 1, dtype=float)
    # Average ranks within tied runs so ties don't get an arbitrary order-dependent rank.
    sorted_vals = values[order]
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or sorted_vals[i] != sorted_vals[start]:
            if i - start > 1:
                ranks[order[start:i]] = ranks[order[start:i]].mean()
            start = i
    return ranks


def _tier_cuts(sorted_desc: np.ndarray, max_tiers: int) -> np.ndarray:
    """Tier boundaries as midpoints of the largest gaps — the same rule as `assign_tiers`."""
    if len(sorted_desc) < 2:
        return np.array([], dtype=float)
    gaps = sorted_desc[:-1] - sorted_desc[1:]
    n_breaks = min(max_tiers - 1, max(1, len(sorted_desc) // 12))
    break_idx = np.argsort(gaps)[-n_breaks:]
    return np.array([(sorted_desc[b] + sorted_desc[b + 1]) / 2.0 for b in break_idx], dtype=float)


def tier_hit_stability_range(
    joined: pd.DataFrame,
    outcomes: pd.DataFrame,
    metric: str = "ppg_half",
    n_boot: int = 300,
    seed: int = 0,
    alpha: float = 0.05,
    max_tiers: int = 8,
) -> pd.DataFrame:
    """How far tier hit-rate moves when the BOUNDARIES are re-derived from a resample.

    Read this as a stability range, **not** a confidence interval, and do not report it as
    one. The point estimate routinely falls outside it — 2024 `ds` scores 0.500 against a
    range of [0.25, 0.41] — which would be incoherent for a sampling CI and is exactly the
    intended signal here: largest-gap segmentation is not stable, so the hit rate is a
    property of one particular set of breaks rather than of the expert.

    Why it moves so much: a bootstrap resample of n values contains only ~63% of the
    distinct originals, and the missing ones merge adjacent gaps in the dense low tail. The
    largest-gap rule then relocates the breaks entirely — 2024 RB cuts sit at 12.2-20.5 on
    the real data and wander to 5.9-9.2 under resampling. Deduplicating first does not help
    (tied values have zero gaps and are never selected as breaks).

    Deliberately NOT a resample of players against fixed boundaries: that measures sampling
    error while treating the breaks as known, which is the assumption actually in doubt.
    Where this range is wide — it always is — prefer points space (§3b), which needs no
    boundaries at all.
    """
    rng = np.random.default_rng(seed)
    scored = joined[joined[metric].notna() & joined["implied_value"].notna()]
    if scored.empty:
        return pd.DataFrame(columns=pd.Index(["season", "expert", "tier_stability_lo", "tier_stability_hi"]))

    pool = {key: g[metric].dropna().to_numpy(dtype=float) for key, g in outcomes.groupby(["season", "pos"])}
    # Precompute group slices once; rebuilding them inside the bootstrap loop dominates runtime.
    blocks = [
        (pool.get(key), g.index.to_numpy(), g[metric].to_numpy(dtype=float), g["implied_value"].to_numpy(dtype=float))
        for key, g in scored.groupby(["season", "pos"])
    ]
    keys = scored[["season", "expert"]]

    per_boot = []
    for _ in range(n_boot):
        hit = np.full(len(scored), np.nan)
        pos_of = {idx: i for i, idx in enumerate(scored.index)}
        for values, idx, realized, implied in blocks:
            if values is None or len(values) < 2:
                continue
            sample = np.sort(rng.choice(values, size=len(values), replace=True))[::-1]
            cuts = np.sort(_tier_cuts(sample, max_tiers))
            if len(cuts) == 0:
                continue
            # searchsorted gives each value's tier index under the resampled breaks; equality
            # of the two indices is exactly "landed in the tier the slot implied".
            same = np.searchsorted(cuts, realized, side="right") == np.searchsorted(cuts, implied, side="right")
            hit[[pos_of[i] for i in idx]] = same.astype(float)
        per_boot.append(pd.Series(hit, index=scored.index).groupby([keys["season"], keys["expert"]]).mean())

    draws = pd.concat(per_boot, axis=1)
    out = pd.DataFrame(
        {
            "tier_stability_lo": draws.quantile(alpha / 2, axis=1),
            "tier_stability_hi": draws.quantile(1 - alpha / 2, axis=1),
        }
    ).reset_index()
    return out


def expert_scorecard(
    joined: pd.DataFrame,
    outcomes: pd.DataFrame,
    experts: Optional[List[str]] = None,
    min_games: int = MIN_GAMES_FOR_PPG,
    metric: str = "ppg_half",
    n_boot: int = 300,
    seed: int = 0,
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
    rng = np.random.default_rng(seed)

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
            lo, hi = _spearman_ci(comp["pos_rank"], comp["pos_finish_rank_in_set"], n_boot, rng)
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
                    "spearman_common_lo": lo,
                    "spearman_common_hi": hi,
                    "spearman_ppg": spearman_ppg,
                    "mae_rank": block["rank_error"].abs().mean(),
                    "mae_rank_common": comp["rank_error"].abs().mean(),
                    # Points space — the "spiritually correct" view. Priced IN-SET, so it is
                    # not moved by how deep the board goes. There is deliberately no signed
                    # counterpart: within a position it is zero by construction, so bias is
                    # reported cross-positionally in VOR by `positional_bias` instead.
                    "mae_points": block["points_error_in_set"].abs().mean(),
                    "mae_points_common": comp["points_error_in_set"].abs().mean(),
                    # How steep the curve is where this expert was working — the quantity that
                    # makes rank error and points error diverge. A flat curve means a large
                    # rank miss cost almost nothing ("spiritually correct"); a steep one means
                    # a small miss was expensive.
                    "median_curve_slope": block["curve_slope"].median(),
                    # tier space. `tier_edge_median` is the median distance from a scored
                    # player to the nearest tier break, in metric units — a small value means
                    # this expert's tier hits are resting on an arbitrary line.
                    "tier_hit_rate": block["tier_hit"].mean(),
                    "tier_edge_median": (
                        block["boundary_distance"].median() if "boundary_distance" in block.columns else float("nan")
                    ),
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

    scope = joined[joined["expert"].isin(experts)] if experts else joined
    tier_ci = tier_hit_stability_range(scope, outcomes, metric=metric, n_boot=n_boot, seed=seed)
    if not tier_ci.empty:
        out = out.merge(tier_ci, on=["season", "expert"], how="left")

    return out.sort_values(["season", "spearman_common"], ascending=[True, False]).reset_index(drop=True)


def bias_by_slice(joined: pd.DataFrame, by: str = "pos", min_cell: int = MIN_CELL_SIZE) -> pd.DataFrame:
    """Error MAGNITUDE per (season, expert, slice). Signed bias lives in `positional_bias`.

    There is deliberately no signed error column here, in either space. Within a position the
    expert's ranks and the realized ranks are permutations of the same set, so a signed mean
    is exactly zero by construction — that is true of signed RANK error, and (contrary to the
    design doc's original claim) equally true of signed POINTS error once the curve is priced
    in-set. The version that appeared non-zero was measuring the offset between a ~250-player
    board and a ~620-player league curve, i.e. board depth. See `add_in_set_curves`.

    Magnitudes are still informative and are what this reports. `mae_points_in_set` is in the
    metric's units for that position, so it compares across experts within a position;
    comparing across positions needs care, since 1 PPG means more to a TE than to a QB.

    Cells below `min_cell` are flagged `sufficient=False` rather than dropped, so a thin slice
    is visibly thin instead of quietly absent.
    """
    grouped = joined.groupby(["season", "expert", by])
    out = grouped.agg(
        n=("player_id", "size"),
        mae_rank=("rank_error", lambda s: s.abs().mean()),
        mae_points_in_set=("points_error_in_set", lambda s: s.abs().mean()),
        tier_hit_rate=("tier_hit", "mean"),
    ).reset_index()
    out["sufficient"] = out["n"] >= min_cell
    return out


def positional_bias(
    joined: pd.DataFrame,
    reference: str = "adp",
    min_cell: int = MIN_CELL_SIZE,
) -> pd.DataFrame:
    """Signed cross-positional bias, in VOR, net of a reference series.

    `mean_vor_error` is the expert's own signed VOR error per position (see
    `add_in_set_curves`): positive means that position returned more than the overall slots
    this expert spent on it. It sums to ~zero ACROSS positions, not within one, which is what
    makes it a usable bias signal where the positional points error is degenerate.

    **Read the `_vs_ref` column, not the raw one.** Every expert AND every market carries the
    same large shared offset — TE ≈ +50, QB ≈ −40 on the 2024-25 boards — because the VOR
    baselines (QB 6, TE 12) interact with how deep each position is drafted. That is a
    property of the replacement levels, not of anyone's judgement, and differencing against a
    reference cancels it. The difference is taken per player on the set the expert and the
    reference BOTH ranked, so coverage cannot move it through the player mix either.

    It is then **centred within (season, expert)**, which is load-bearing and not cosmetic.
    Each board's `vor_error` sums to zero over ITS OWN players, so when two boards differ in
    size the two zero-sums are taken over different populations and the raw difference
    inherits a global per-expert offset that tracks board size — 2024 `ds` (146 players) came
    out +18.96 and `ringer` (144) +20.14 across *every* position, while `fp` and `pff` (214,
    the same size as `adp`) came out at exactly 0.00. That is arithmetic, not judgement.
    Centring removes it, leaving a tilt that sums to ~zero across positions: the question
    "which positions did this expert favour relative to the market", which is the only thing
    the comparison can answer.

    Cells below `min_cell` are flagged rather than dropped.
    """
    needed = {"vor_error", "expert", "season", "pos", "player_id"}
    if not needed.issubset(joined.columns) or joined.empty:
        return pd.DataFrame(
            columns=pd.Index(["season", "expert", "pos", "n", "mean_vor_error", "mean_vor_error_vs_ref", "sufficient"])
        )

    scored = joined[joined["vor_error"].notna()]
    out = (
        scored.groupby(["season", "expert", "pos"])
        .agg(n=("player_id", "size"), mean_vor_error=("vor_error", "mean"))
        .reset_index()
    )

    ref = scored[scored["expert"] == reference][["season", "player_id", "vor_error"]].rename(
        columns={"vor_error": "ref_vor_error"}
    )
    paired = scored[scored["expert"] != reference].merge(ref, on=["season", "player_id"], how="inner")
    if paired.empty:
        out["mean_vor_error_vs_ref"] = np.nan
        out["n_vs_ref"] = 0
    else:
        raw_diff = paired["vor_error"] - paired["ref_vor_error"]
        paired["vor_error_vs_ref"] = raw_diff - raw_diff.groupby([paired["season"], paired["expert"]]).transform("mean")
        rel = (
            paired.groupby(["season", "expert", "pos"])
            .agg(n_vs_ref=("player_id", "size"), mean_vor_error_vs_ref=("vor_error_vs_ref", "mean"))
            .reset_index()
        )
        out = out.merge(rel, on=["season", "expert", "pos"], how="left")

    out["sufficient"] = out["n"] >= min_cell
    return out.sort_values(["season", "expert", "pos"]).reset_index(drop=True)


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

    **Everything is priced against one curve, built on the players the expert and the
    reference BOTH ranked.** Pricing against the league-wide curve made `value_added`
    systematically negative — the r-th best of a ~620-player universe beats the r-th best of a
    ~250-player board — which tilts `sign(value_added)` toward "the expert was right to fade
    him" no matter who the expert is. On the common set both ranks are permutations of the
    same slots, so `value_added` averages to zero by construction and the sign test is a fair
    coin. Re-ranking within the common set is also what makes the two boards commensurable at
    all: raw positional ranks come from boards of different depths.
    """
    ref = joined[joined["expert"] == reference][["season", "player_id", "pos_rank", "overall_rank"]].rename(
        columns={"pos_rank": "ref_pos_rank_raw", "overall_rank": "ref_overall_rank"}
    )
    df = joined[joined["expert"] != reference].merge(ref, on=["season", "player_id"], how="inner")
    df = df[df["pos_rank"].notna() & df["ref_pos_rank_raw"].notna() & df[metric].notna()].copy()
    if df.empty:
        return df.assign(delta_rank=None, delta_value=None, value_added=None, correct=None, is_big_call=None)

    # Re-rank both sides within the common set, then price both off that set's own curve.
    keys = ["season", "expert", "pos"]
    df["exp_slot"] = df.groupby(keys)["pos_rank"].rank(method="first")
    df["ref_slot"] = df.groupby(keys)["ref_pos_rank_raw"].rank(method="first")
    # The common set's own realized values, descending: slot r is priced at the r-th best.
    ordered = {k: np.sort(g[metric].to_numpy(dtype=float))[::-1] for k, g in df.groupby(keys, sort=False)}

    def _lookup(col: str) -> np.ndarray:
        vals = np.full(len(df), np.nan)
        for k, g in df.groupby(keys, sort=False):
            arr = ordered[k]
            slots = g[col].astype(int).to_numpy()
            ok = (slots >= 1) & (slots <= len(arr))
            pos_in_df = df.index.get_indexer(g.index[ok])
            vals[pos_in_df] = arr[slots[ok] - 1]
        return vals

    df["implied_value_common"] = _lookup("exp_slot")
    df["ref_implied_value"] = _lookup("ref_slot")

    df["delta_rank"] = df["ref_slot"] - df["exp_slot"]  # positive = expert higher than market
    df["delta_value"] = df["implied_value_common"] - df["ref_implied_value"]
    df["value_added"] = df[metric] - df["ref_implied_value"]
    df["correct"] = np.sign(df["value_added"]) == np.sign(df["delta_rank"])
    # Draft region is defined in OVERALL-pick terms (rounds 1-3 = picks 1-36), so it must be
    # read off the reference's overall rank. Mapping a POSITIONAL rank through those cutoffs
    # put every position's top 36 in "rounds 1-3" — TE36 is not a third-round pick.
    df["region"] = df["ref_overall_rank"].map(draft_region)

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

    # DO NOT compare `hit_rate` against 0.5 — the correct null is `hit_rate_vs_pool`.
    # The sign test gets mechanically easier as the disagreement grows: pooled across every
    # expert, hit rate climbs monotonically with |delta_value| (0.38 in the smallest half of
    # calls, 0.53, 0.62, then 0.75 in the top 5%). Selecting the top 20% by construction lands
    # everyone well above a coin flip, so an expert at 0.68 has done nothing but make big
    # calls. Differencing against the pooled rate over the SAME selected set removes the
    # gradient and leaves the part that is about the expert.
    #
    # The pool is computed WITHIN each non-expert slice level, because the same gradient
    # recurs one level down: late-round calls hit far more often than early ones, so a global
    # pool would rank every expert's "rounds 9+" cell above its "rounds 1-3" cell and read as
    # "everyone is better late". Comparing experts is only meaningful inside a slice.
    slice_keys = [k for k in by if k != "expert"]
    if len(big) == 0:
        out["hit_rate_vs_pool"] = float("nan")
    elif slice_keys:
        pool = big.groupby(slice_keys)["correct"].mean().rename("_pool")
        out = out.merge(pool, left_on=slice_keys, right_index=True, how="left")
        out["hit_rate_vs_pool"] = out["hit_rate"] - out["_pool"]
        out = out.drop(columns=["_pool"])
    else:
        out["hit_rate_vs_pool"] = out["hit_rate"] - big["correct"].mean()
    out["sufficient"] = out["n_calls"] >= min_cell
    # Sort by the column callers are told to read. Sorting on raw `hit_rate` ordered the
    # region slice by how easy each region is, putting every expert's "rounds 9+" cell above
    # its "rounds 1-3" cell — the exact reading `hit_rate_vs_pool` exists to prevent.
    return out.sort_values("hit_rate_vs_pool", ascending=False).reset_index(drop=True)
