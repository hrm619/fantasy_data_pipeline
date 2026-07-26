"""Tests for the historical expert accuracy analysis.

The traps here are all "the number computes fine but means nothing":
  - comparing an expert's ranks against a realized rank drawn from a bigger universe
  - averaging signed rank error within a position, which is zero by construction
  - scoring an expert on players they never ranked
  - letting a shallow board look accurate because it only ranked the safe players
"""

import numpy as np
import pandas as pd
import pytest

from fantasy_pipeline.analysis.historical import (
    _collapse_duplicate_players,
    _derive_pos_ranks,
    _parse_positional,
    _value_over_replacement,
)
from fantasy_pipeline.analysis.scorecard import (
    add_value_curve,
    assign_tiers,
    bias_by_slice,
    conviction_calls,
    expert_scorecard,
    realized_value_curve,
)


def _outcomes(values, season=2024, pos="RB"):
    return pd.DataFrame(
        {
            "season": season,
            "player_id": [f"P{i}" for i in range(len(values))],
            "player_name": [f"Player {i}" for i in range(len(values))],
            "pos": pos,
            "team": "XXX",
            "games": 17,
            "fpts_half": [v * 17 for v in values],
            "ppg_half": values,
            "pos_finish_rank": pd.Series(values).rank(ascending=False, method="min").astype(int),
            "overall_finish_rank": pd.Series(values).rank(ascending=False, method="min").astype(int),
        }
    )


def _ranked(expert, ranks, season=2024, pos="RB", kind="expert"):
    return pd.DataFrame(
        {
            "season": season,
            "expert": expert,
            "expert_kind": kind,
            "rank_scope": "overall",
            "player_id": [f"P{i}" for i in range(len(ranks))],
            "name_as_published": [f"Player {i}" for i in range(len(ranks))],
            "pos_rank": ranks,
            "overall_rank": ranks,
        }
    )


class TestParsePositional:
    def test_parses_position_rank_strings(self):
        assert _parse_positional("RB1") == 1
        assert _parse_positional("WR23") == 23

    @pytest.mark.parametrize("bad", ["#REF!", "#NAME?", "", None, 5, float("nan")])
    def test_rejects_blanks_and_spreadsheet_errors(self, bad):
        assert _parse_positional(bad) is None


class TestCollapseDuplicatePlayers:
    """The 2025 snapshot predates the player-key collision fix and carries JaTavion Sanders
    16 times, because SandJa01 mapped to both the TE and kicker Jason Sanders."""

    def test_identical_copies_collapse(self):
        df = pd.DataFrame({"PLAYER ID": ["A", "A"], "PLAYER NAME": ["X", "X"], "ECR": [5, 5]})
        out = _collapse_duplicate_players(df, ["ECR"], 2025, verbose=False)
        assert len(out) == 1

    def test_conflicting_copies_are_dropped_not_guessed(self):
        # Two different players' ranks under one id. Picking one would score a kicker's
        # ranking as a tight end's.
        df = pd.DataFrame({"PLAYER ID": ["A", "A"], "PLAYER NAME": ["X", "X"], "ECR": [234, 254]})
        out = _collapse_duplicate_players(df, ["ECR"], 2025, verbose=False)
        assert out.empty

    def test_unaffected_players_survive(self):
        df = pd.DataFrame({"PLAYER ID": ["A", "A", "B"], "PLAYER NAME": ["X", "X", "Y"], "ECR": [1, 2, 3]})
        out = _collapse_duplicate_players(df, ["ECR"], 2025, verbose=False)
        assert list(out["PLAYER ID"]) == ["B"]


class TestDerivePosRanks:
    def test_derives_positional_rank_from_overall(self):
        df = pd.DataFrame(
            {
                "season": 2025,
                "expert": "fp",
                "pos": ["RB", "WR", "RB", "WR"],
                "overall_rank": [1.0, 2.0, 5.0, 9.0],
                "pos_rank": [np.nan] * 4,
            }
        )
        out = _derive_pos_ranks(df)
        assert list(out["pos_rank"]) == [1, 1, 2, 2]
        assert out["pos_rank_derived"].all()

    def test_published_rank_survives_when_no_overall(self):
        # 2024 Hayden Winks published positional ranks only.
        df = pd.DataFrame({"season": 2024, "expert": "hw", "pos": ["RB"], "overall_rank": [np.nan], "pos_rank": [4.0]})
        out = _derive_pos_ranks(df)
        assert out["pos_rank"].iloc[0] == 4.0
        assert not out["pos_rank_derived"].iloc[0]


class TestValueOverReplacement:
    def test_measures_against_the_positional_baseline(self):
        # RB baseline is the 24th back; with 24 players the last one is replacement level.
        out = _outcomes([30 - i for i in range(24)])
        vor = _value_over_replacement(out)
        assert vor.max() == pytest.approx((30 - 7) * 17, abs=0.01)
        assert vor.min() == pytest.approx(0.0, abs=0.01)

    def test_short_group_falls_back_to_last_player(self):
        out = _outcomes([20.0, 10.0], pos="RB")  # far fewer than the 24 baseline
        vor = _value_over_replacement(out)
        assert vor.min() == pytest.approx(0.0, abs=0.01)


class TestRealizedValueCurve:
    def test_curve_is_the_sorted_outcome(self):
        curve = realized_value_curve(_outcomes([10.0, 30.0, 20.0]))
        assert list(curve["curve_value"]) == [30.0, 20.0, 10.0]
        assert list(curve["curve_rank"]) == [1, 2, 3]

    def test_slope_is_flat_where_outcomes_are_flat(self):
        # The whole point of points-space scoring: a rank miss inside a flat band is cheap.
        curve = realized_value_curve(_outcomes([20.0, 12.0, 12.0, 12.0, 4.0]))
        assert curve.loc[curve["curve_rank"] == 3, "slope"].iloc[0] == pytest.approx(0.0)
        assert curve.loc[curve["curve_rank"] == 1, "slope"].iloc[0] > 0


class TestPointsSpaceScoring:
    """The 'spiritually correct' case: being wrong on the rank but right on the value."""

    def test_flat_region_miss_costs_almost_nothing(self):
        outcomes = _outcomes([30.0, 12.2, 12.1, 12.0, 11.9, 4.0])
        # Expert inverted the four players inside the flat band (ranks 2-5).
        joined = _ranked("pff", [1, 5, 4, 3, 2, 6]).merge(
            outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
            on=["season", "player_id"],
        )
        scored = add_value_curve(joined, outcomes)
        flat = scored[scored["pos_rank"].between(2, 5)]
        assert flat["rank_error"].abs().max() >= 3  # badly wrong on rank
        assert flat["points_error"].abs().max() < 0.3  # but barely wrong on value

    def test_steep_region_miss_is_expensive(self):
        outcomes = _outcomes([30.0, 10.0, 9.0, 8.0])
        joined = _ranked("pff", [2, 1, 3, 4]).merge(
            outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
            on=["season", "player_id"],
        )
        scored = add_value_curve(joined, outcomes)
        # One rank of error across the cliff costs 20 PPG, not "one rank".
        assert scored["points_error"].abs().max() == pytest.approx(20.0, abs=0.01)


class TestTiers:
    def test_breaks_go_at_the_largest_gaps(self):
        outcomes = _outcomes([30.0, 29.0, 28.0] + [10.0, 9.0, 9.0] * 4)
        tiers = assign_tiers(outcomes)
        merged = outcomes.merge(tiers, on=["season", "player_id"])
        top = merged[merged["ppg_half"] > 20]["tier"].unique()
        bottom = merged[merged["ppg_half"] < 20]["tier"].unique()
        assert len(top) == 1 and len(bottom) == 1
        assert top[0] != bottom[0]

    def test_boundary_distance_flags_knife_edge_players(self):
        outcomes = _outcomes([30.0, 29.0, 28.0] + [10.0, 9.0, 9.0] * 4)
        tiers = assign_tiers(outcomes)
        # Somebody sits right on the break, and the metric must say so.
        assert tiers["boundary_distance"].min() == pytest.approx(0.0, abs=0.01)


class TestScorecard:
    def test_realized_rank_is_computed_within_the_ranked_set(self):
        """Comparing against a league-wide finish rank made every expert look ~10 ranks
        optimistic, because experts rank ~217 players out of a ~620 outcome universe."""
        outcomes = _outcomes([float(30 - i) for i in range(40)])
        ranked_ids = [f"P{i}" for i in range(10)]  # expert only ranked the top 10
        joined = _ranked("pff", list(range(1, 11)))
        joined = joined[joined["player_id"].isin(ranked_ids)].merge(
            outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
            on=["season", "player_id"],
        )
        scored = add_value_curve(joined, outcomes)
        # A perfect ranking of a subset must show zero error, not a constant offset.
        assert scored["rank_error"].abs().max() == 0

    def test_perfect_ranking_scores_one(self):
        outcomes = _outcomes([float(20 - i) for i in range(12)])
        joined = _ranked("pff", list(range(1, 13))).merge(
            outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
            on=["season", "player_id"],
        )
        card = expert_scorecard(add_value_curve(joined, outcomes), outcomes)
        assert card["spearman_full"].iloc[0] == pytest.approx(1.0)

    def test_common_subset_restricts_to_shared_players(self):
        # A shallow board must not be compared on a different, easier set of players.
        outcomes = _outcomes([float(20 - i) for i in range(12)])
        cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]
        deep = _ranked("fp", list(range(1, 13)))
        shallow = _ranked("ds", list(range(1, 6))).head(5)
        joined = pd.concat([deep, shallow]).merge(outcomes[cols], on=["season", "player_id"])
        card = expert_scorecard(add_value_curve(joined, outcomes), outcomes).set_index("expert")
        assert card.loc["fp", "n_ranked"] == 12
        assert card.loc["fp", "n_common"] == 5  # judged only on what both ranked
        assert card.loc["ds", "n_common"] == 5


class TestBiasBySlice:
    def test_reports_no_signed_rank_error(self):
        # It would be zero by construction within a position and read as "no bias".
        outcomes = _outcomes([float(20 - i) for i in range(12)])
        joined = _ranked("pff", list(range(1, 13))).merge(
            outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
            on=["season", "player_id"],
        )
        out = bias_by_slice(add_value_curve(joined, outcomes))
        assert "mean_rank_error" not in out.columns
        assert "mean_points_error" in out.columns

    def test_flags_thin_cells(self):
        outcomes = _outcomes([float(20 - i) for i in range(4)])
        joined = _ranked("pff", [1, 2, 3, 4]).merge(
            outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
            on=["season", "player_id"],
        )
        out = bias_by_slice(add_value_curve(joined, outcomes))
        assert not out["sufficient"].any()


class TestConviction:
    def test_big_calls_are_selected_by_value_not_rank_distance(self):
        """Ten ranks at the top of the board is a large claim; ten ranks at pick 150 is
        rounding. Selecting on rank distance over-samples the late rounds."""
        # Steep at the top, flat at the bottom.
        values = [40.0, 30.0, 20.0] + [5.0 - i * 0.01 for i in range(20)]
        outcomes = _outcomes(values)
        cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]

        market = list(range(1, len(values) + 1))
        expert = market.copy()
        expert[0], expert[2] = 3, 1  # 2-rank disagreement at the very top
        expert[10], expert[20] = 21, 11  # 10-rank disagreement deep in the flat tail

        joined = pd.concat([_ranked("adp", market, kind="market"), _ranked("pff", expert)]).merge(
            outcomes[cols], on=["season", "player_id"]
        )
        calls = conviction_calls(add_value_curve(joined, outcomes), outcomes)
        top_call = calls[calls["player_id"] == "P0"].iloc[0]
        tail_call = calls[calls["player_id"] == "P10"].iloc[0]
        assert abs(top_call["delta_value"]) > abs(tail_call["delta_value"])
        assert top_call["is_big_call"]
        assert not tail_call["is_big_call"]


# --------------------------------------------------------------------------------------
# Supplemental boards: files that carry an expert's board better than the snapshot did.
# --------------------------------------------------------------------------------------


def _write_supplemental(tmp_path, name, rows, header="Player,Team,Pos,Rank,ADP\n"):
    path = tmp_path / name
    path.write_text(header + "".join(rows))
    return path


def test_supplemental_underdog_adp_is_ranked_not_passed_through(tmp_path):
    """Underdog publishes best-ball ADP as a decimal (1.2, 2.3) and overall_rank is Int64.

    Passing the raw value through truncates 1.2 and 1.9 to the same 1, manufacturing ties
    and scrambling the top of the board. The market series must carry a RANK.
    """
    from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

    _write_supplemental(
        tmp_path,
        "hw-test.csv",
        [
            "Christian McCaffrey,SF,RB,1,1.2\n",
            "CeeDee Lamb,DAL,WR,2,1.9\n",
            "Breece Hall,NYJ,RB,3,6.4\n",
        ],
    )
    spec = SupplementalBoard(
        season=2024,
        expert="hw",
        filename="hw-test.csv",
        as_of_date="2024-08-20",
        name_col="Player",
        pos_col="Pos",
        rank_col="Rank",
        market_col="ADP",
    )
    out = _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)

    market = out[out["expert"] == "adp_underdog"].sort_values("overall_rank")
    assert list(market["overall_rank"]) == [1, 2, 3], "decimal ADP must become a distinct rank"
    assert market["overall_rank"].nunique() == 3, "1.2 and 1.9 must not collapse to the same rank"


def test_supplemental_market_is_a_separate_expert_from_adp(tmp_path):
    """Underdog best-ball ADP must never merge into the redraft consensus `adp` series."""
    from fantasy_pipeline.analysis.historical import EXPERT_KINDS, SupplementalBoard, _load_supplemental_board

    _write_supplemental(tmp_path, "hw-test.csv", ["Christian McCaffrey,SF,RB,1,1.2\nCeeDee Lamb,DAL,WR,2,2.3\n"])
    spec = SupplementalBoard(
        season=2024,
        expert="hw",
        filename="hw-test.csv",
        as_of_date="2024-08-20",
        name_col="Player",
        pos_col="Pos",
        rank_col="Rank",
        market_col="ADP",
    )
    out = _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)

    assert set(out["expert"]) == {"hw", "adp_underdog"}
    assert "adp" not in set(out["expert"])
    assert EXPERT_KINDS["adp_underdog"] == "market"
    assert EXPERT_KINDS["adp"] == "market"


def test_supplemental_board_drops_non_skill_positions(tmp_path):
    from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

    _write_supplemental(
        tmp_path,
        "hw-test.csv",
        ["Christian McCaffrey,SF,RB,1,1.2\nJustin Tucker,BAL,K,2,2.3\n"],
    )
    spec = SupplementalBoard(
        season=2024,
        expert="hw",
        filename="hw-test.csv",
        as_of_date="2024-08-20",
        name_col="Player",
        pos_col="Pos",
        rank_col="Rank",
    )
    out = _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)
    assert set(out["pos"]) <= {"QB", "RB", "WR", "TE"}


def test_supplemental_board_missing_file_raises(tmp_path):
    from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

    spec = SupplementalBoard(
        season=2024,
        expert="hw",
        filename="nope.csv",
        as_of_date="2024-08-20",
        name_col="Player",
        pos_col="Pos",
        rank_col="Rank",
    )
    with pytest.raises(FileNotFoundError):
        _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)


def test_analysis_seasons_include_2023():
    """2023 has no snapshot, only a supplemental HW board — but PFR carries its outcomes."""
    from fantasy_pipeline.analysis.historical import ANALYSIS_SEASONS

    assert 2023 in ANALYSIS_SEASONS


# --------------------------------------------------------------------------------------
# Bootstrap intervals
# --------------------------------------------------------------------------------------


def test_rankdata_averages_ties():
    from fantasy_pipeline.analysis.scorecard import _rankdata

    assert list(_rankdata(np.array([10.0, 20.0, 20.0, 40.0]))) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_ci_brackets_the_point_estimate():
    """A real percentile CI must contain the statistic it is an interval for."""
    from fantasy_pipeline.analysis.scorecard import _spearman, _spearman_ci

    rng = np.random.default_rng(0)
    a = pd.Series(np.arange(1, 61, dtype=float))
    b = a + pd.Series(rng.normal(0, 5, 60))
    point = _spearman(a, b)
    lo, hi = _spearman_ci(a, b, n_boot=200, rng=rng)
    assert lo <= point <= hi
    assert lo < hi


def test_spearman_ci_returns_nan_when_too_few_players():
    from fantasy_pipeline.analysis.scorecard import _spearman_ci

    rng = np.random.default_rng(0)
    lo, hi = _spearman_ci(pd.Series([1.0, 2.0]), pd.Series([2.0, 1.0]), n_boot=50, rng=rng)
    assert np.isnan(lo) and np.isnan(hi)


def test_tier_stability_range_is_ordered_and_bounded():
    """It is a stability range, not a CI — but it still must be a valid [lo, hi] in [0, 1]."""
    from fantasy_pipeline.analysis.scorecard import tier_hit_stability_range

    values = [30.0, 28.0, 27.5, 20.0, 19.5, 19.0, 12.0, 11.5, 11.0, 5.0, 4.5, 4.0]
    outcomes = _outcomes(values)
    joined = _ranked("pff", list(range(1, len(values) + 1))).merge(
        outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
        on=["season", "player_id"],
    )
    enriched = add_value_curve(joined, outcomes)

    rng_out = tier_hit_stability_range(enriched, outcomes, n_boot=40, seed=0)
    assert not rng_out.empty
    row = rng_out.iloc[0]
    assert 0.0 <= row["tier_stability_lo"] <= row["tier_stability_hi"] <= 1.0


def test_scorecard_reports_intervals_and_tier_edge():
    from fantasy_pipeline.analysis.scorecard import expert_scorecard as _sc

    values = [30.0, 28.0, 27.5, 20.0, 19.5, 19.0, 12.0, 11.5, 11.0, 5.0, 4.5, 4.0]
    outcomes = _outcomes(values)
    cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]
    joined = pd.concat(
        [
            _ranked("pff", list(range(1, len(values) + 1))).merge(outcomes[cols], on=["season", "player_id"]),
            _ranked("ds", list(reversed(range(1, len(values) + 1)))).merge(outcomes[cols], on=["season", "player_id"]),
        ],
        ignore_index=True,
    )
    enriched = add_value_curve(joined, outcomes)
    card = _sc(enriched, outcomes, n_boot=40, seed=0)

    for col in ("spearman_common_lo", "spearman_common_hi", "tier_edge_median"):
        assert col in card.columns
    assert (card["spearman_common_lo"] <= card["spearman_common_hi"]).all()
