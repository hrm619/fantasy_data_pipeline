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
    _melt,
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


class TestMeltPositionalDtypes:
    """`_melt` must read published positional ranks ("RB1") whatever dtype pandas infers.

    The branch used to be `dtype == object`, which is how pandas 2 types a text column but
    NOT how pandas 3 does — it infers `str`. Under pandas 3 every "RB1" fell through to
    `to_numeric(errors="coerce")` and became NaN, so `pos_rank` came out empty for every
    expert publishing that format. Nothing raised; the table just lost a column of meaning.
    The pipeline already executes inside pandas-3 venvs (fantasy-data's), so this is pinned
    against the dtypes themselves rather than against whichever major is installed.
    """

    def _frame(self, pos_rank_series):
        return pd.DataFrame(
            {
                "PLAYER ID": ["P0", "P1"],
                "PLAYER NAME": ["Player 0", "Player 1"],
                "_pos": ["RB", "WR"],
                "POS RANK": pos_rank_series,
            }
        )

    def _melted(self, df):
        return _melt(df, 2025, "2025-08-01", "src.csv", {}, {"POS RANK": "jj"})

    @pytest.mark.parametrize("dtype", ["object", "str"])
    def test_published_strings_parse_under_either_string_dtype(self, dtype):
        df = self._frame(pd.Series(["RB1", "WR12"], dtype=dtype))
        out = self._melted(df)
        assert list(out["pos_rank"]) == [1, 12]

    def test_bare_numbers_still_take_the_numeric_path(self):
        df = self._frame(pd.Series([1, 12]))
        out = self._melted(df)
        assert list(out["pos_rank"]) == [1, 12]

    def test_spreadsheet_errors_drop_the_row_rather_than_parsing(self):
        # `#REF!` yields no rank, and on a positional-only board that means no row at all
        # (see `_melt`: absence is not a rank of NaN). The ranked player is unaffected.
        df = self._frame(pd.Series(["#REF!", "WR12"], dtype="str"))
        out = self._melted(df)
        assert list(out["player_id"]) == ["P1"]
        assert list(out["pos_rank"]) == [12]

    def test_a_positional_only_board_survives_as_rows(self):
        # The failure this guards is worse than a null column: with no overall-rank column,
        # a coerced-to-NaN pos_rank leaves both ranks null and `_melt` drops every row, so
        # the expert disappears from the table entirely rather than arriving empty.
        df = self._frame(pd.Series(["RB1", "WR12"], dtype="str"))
        out = self._melted(df)
        assert len(out) == 2
        assert set(out["rank_scope"]) == {"positional"}


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
    def test_reports_no_signed_error_in_either_space(self):
        """Neither signed rank error NOR signed points error may appear here.

        Both are exactly zero by construction within a position — the expert's ranks and the
        realized ranks are permutations of the same set. The design doc originally claimed
        signed POINTS error escaped this and "carried the answer"; it does not. The version
        that looked non-zero was priced against the league-wide curve and was measuring board
        depth. Signed bias belongs in `positional_bias`, cross-positionally, in VOR.
        """
        outcomes = _outcomes([float(20 - i) for i in range(12)])
        joined = _ranked("pff", list(range(1, 13))).merge(
            outcomes[["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]],
            on=["season", "player_id"],
        )
        out = bias_by_slice(add_value_curve(joined, outcomes))
        assert "mean_rank_error" not in out.columns
        assert "mean_points_error" not in out.columns
        assert "mae_points_in_set" in out.columns

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


# --------------------------------------------------------------------------------------
# In-set pricing: the fix for the board-depth artifact in points space.
# --------------------------------------------------------------------------------------


def _multi_pos_outcomes(spec, season=2024):
    """spec: {pos: [ppg, ...]}. Distinct player_ids across positions."""
    rows = []
    for pos, values in spec.items():
        for i, v in enumerate(values):
            rows.append(
                {
                    "season": season,
                    "player_id": f"{pos}{i}",
                    "player_name": f"{pos} {i}",
                    "pos": pos,
                    "team": "XXX",
                    "games": 17,
                    "fpts_half": v * 17,
                    "ppg_half": v,
                }
            )
    out = pd.DataFrame(rows)
    out["pos_finish_rank"] = out.groupby(["season", "pos"])["fpts_half"].rank(ascending=False, method="min").astype(int)
    out["overall_finish_rank"] = out.groupby("season")["fpts_half"].rank(ascending=False, method="min").astype(int)
    out["value_over_replacement"] = out["fpts_half"] - out.groupby("pos")["fpts_half"].transform("median")
    return out


def _rank_all(outcomes, expert, order, kind="expert"):
    """Rank the given player_ids 1..n overall; positional rank derived from that order."""
    df = pd.DataFrame({"player_id": order})
    df["season"] = outcomes["season"].iloc[0]
    df["expert"] = expert
    df["expert_kind"] = kind
    df["rank_scope"] = "overall"
    df["name_as_published"] = df["player_id"]
    df["overall_rank"] = range(1, len(df) + 1)
    df = df.merge(outcomes[["season", "player_id", "pos"]], on=["season", "player_id"])
    df["pos_rank"] = df.groupby("pos")["overall_rank"].rank(method="first").astype(int)
    return df


class TestInSetPricing:
    def test_signed_positional_points_error_is_zero_by_construction(self):
        """The load-bearing invariant. If this ever becomes non-zero, someone has
        reintroduced a cross-set comparison and the 'bias' it shows is board depth."""
        outcomes = _outcomes([float(30 - i) for i in range(20)])
        cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]
        for order in ([*range(1, 21)], [*reversed(range(1, 21))]):
            joined = _ranked("pff", order).merge(outcomes[cols], on=["season", "player_id"])
            enriched = add_value_curve(joined, outcomes)
            assert enriched["points_error_in_set"].mean() == pytest.approx(0.0, abs=1e-9)

    def test_in_set_pricing_is_invariant_to_board_coverage(self):
        """The defect this replaces, in miniature.

        Both experts rank their own players in the exactly correct order, so neither has made
        a mistake. But `sparse` covers only every other player, so against the LEAGUE-WIDE
        curve its slot-2 player is priced as the league's 2nd best when he is really the 3rd —
        and it reads as systematically pessimistic. Priced in-set, both correctly read zero.
        This is the PFF-2025 case: a 426-player board scored as least biased at WR purely for
        reaching further down a curve indexed on a different set.
        """
        outcomes = _outcomes([float(40 - i) for i in range(30)])
        cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]
        full = _ranked("full", list(range(1, 31)))
        sparse = _ranked("sparse", list(range(1, 31))).iloc[::2].copy()
        sparse["pos_rank"] = range(1, len(sparse) + 1)
        sparse["overall_rank"] = range(1, len(sparse) + 1)
        joined = pd.concat([full, sparse]).merge(outcomes[cols], on=["season", "player_id"])
        enriched = add_value_curve(joined, outcomes)

        in_set = enriched.groupby("expert")["points_error_in_set"].mean()
        assert in_set["full"] == pytest.approx(0.0, abs=1e-9)
        assert in_set["sparse"] == pytest.approx(0.0, abs=1e-9)

        # The league-wide version is exactly what does NOT hold — kept as the contrast.
        legacy = enriched.groupby("expert")["points_error"].mean()
        assert legacy["full"] == pytest.approx(0.0, abs=1e-9)
        assert legacy["sparse"] < -1.0, "coverage alone must be what moves the old metric"

    def test_vor_bias_sums_to_zero_across_positions_but_not_within(self):
        """Why the bias metric moved to the overall board in VOR: the permutation constraint
        binds at board level, so per-position means are free to be non-zero."""
        outcomes = _multi_pos_outcomes({"RB": [20.0, 18.0, 14.0, 9.0], "WR": [19.0, 15.0, 11.0, 7.0]})
        # An RB-heavy board: every RB taken before every WR.
        order = ["RB0", "RB1", "RB2", "RB3", "WR0", "WR1", "WR2", "WR3"]
        joined = _rank_all(outcomes, "rbheavy", order).merge(
            outcomes[["season", "player_id", "games", "ppg_half", "pos_finish_rank", "value_over_replacement"]],
            on=["season", "player_id"],
        )
        enriched = add_value_curve(joined, outcomes)
        assert enriched["vor_error"].mean() == pytest.approx(0.0, abs=1e-9)
        by_pos = enriched.groupby("pos")["vor_error"].mean()
        assert by_pos.abs().max() > 1e-6, "per-position VOR error must be free to move"


class TestPositionalBias:
    def test_vs_ref_cancels_the_shared_baseline_offset(self):
        """Every board carries the same large TE/QB offset from the VOR baselines. An expert
        who ranks identically to the reference must read as zero bias, not as that offset."""
        from fantasy_pipeline.analysis.scorecard import positional_bias

        outcomes = _multi_pos_outcomes({"RB": [20.0, 18.0, 14.0, 9.0], "TE": [19.0, 15.0, 11.0, 7.0]})
        order = ["RB0", "TE0", "RB1", "TE1", "RB2", "TE2", "RB3", "TE3"]
        cols = ["season", "player_id", "games", "ppg_half", "pos_finish_rank", "value_over_replacement"]
        joined = pd.concat(
            [_rank_all(outcomes, "adp", order, kind="market"), _rank_all(outcomes, "clone", order)]
        ).merge(outcomes[cols], on=["season", "player_id"])
        enriched = add_value_curve(joined, outcomes)

        bias = positional_bias(enriched, reference="adp").set_index(["expert", "pos"])
        for pos in ("RB", "TE"):
            assert bias.loc[("clone", pos), "mean_vor_error_vs_ref"] == pytest.approx(0.0, abs=1e-9)

    def test_over_drafting_a_position_shows_up_as_negative_vs_ref(self):
        from fantasy_pipeline.analysis.scorecard import positional_bias

        outcomes = _multi_pos_outcomes({"RB": [20.0, 18.0, 14.0, 9.0], "WR": [19.0, 15.0, 11.0, 7.0]})
        alternating = ["RB0", "WR0", "RB1", "WR1", "RB2", "WR2", "RB3", "WR3"]
        rb_heavy = ["RB0", "RB1", "RB2", "RB3", "WR0", "WR1", "WR2", "WR3"]
        cols = ["season", "player_id", "games", "ppg_half", "pos_finish_rank", "value_over_replacement"]
        joined = pd.concat(
            [_rank_all(outcomes, "adp", alternating, kind="market"), _rank_all(outcomes, "rbheavy", rb_heavy)]
        ).merge(outcomes[cols], on=["season", "player_id"])
        enriched = add_value_curve(joined, outcomes)

        bias = positional_bias(enriched, reference="adp").set_index(["expert", "pos"])
        rb = bias.loc[("rbheavy", "RB"), "mean_vor_error_vs_ref"]
        wr = bias.loc[("rbheavy", "WR"), "mean_vor_error_vs_ref"]
        # Spending early overall slots on RBs => RBs returned less than those slots implied.
        assert rb < 0 < wr


class TestConvictionPricing:
    def test_value_added_is_centred_on_the_common_set(self):
        """Priced against the league curve, value_added was systematically negative and the
        sign test favoured 'the expert was right to fade him' regardless of skill."""
        outcomes = _outcomes([float(30 - i) for i in range(20)])
        cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]
        market = _ranked("adp", list(range(1, 21)), kind="market")
        expert = _ranked("pff", [*range(5, 21), 1, 2, 3, 4])
        joined = pd.concat([market, expert]).merge(outcomes[cols], on=["season", "player_id"])
        enriched = add_value_curve(joined, outcomes)

        calls = conviction_calls(enriched, outcomes)
        assert not calls.empty
        assert calls["value_added"].mean() == pytest.approx(0.0, abs=1e-9)

    def test_region_is_read_from_overall_rank_not_positional_rank(self):
        """DRAFT_REGIONS is in overall-pick terms. Mapping a positional rank through it put
        every position's top 36 in 'rounds 1-3' — TE36 is not a third-round pick."""
        # 40 RBs first, so every TE sits past overall pick 36 while its POSITIONAL rank is
        # still 1-30 — the range where the two mappings disagree.
        outcomes = _multi_pos_outcomes({"RB": [20.0 - i for i in range(40)], "TE": [19.0 - i for i in range(30)]})
        order = [f"RB{i}" for i in range(40)] + [f"TE{i}" for i in range(30)]
        cols = ["season", "player_id", "games", "ppg_half", "pos_finish_rank", "value_over_replacement"]
        shifted = order[10:] + order[:10]
        joined = pd.concat(
            [_rank_all(outcomes, "adp", order, kind="market"), _rank_all(outcomes, "pff", shifted)]
        ).merge(outcomes[cols], on=["season", "player_id"])
        enriched = add_value_curve(joined, outcomes)

        from fantasy_pipeline.analysis.scorecard import draft_region

        calls = conviction_calls(enriched, outcomes)
        # Region must be a pure function of the reference's OVERALL rank.
        expected = calls["ref_overall_rank"].map(draft_region)
        assert calls["region"].equals(expected)

        # The specific bug: TEs 1-30 positionally all sit past overall pick 30 here, so a
        # positional-rank mapping would have called the early ones round 1-3 picks.
        te = calls[calls["pos"] == "TE"]
        assert (te["ref_pos_rank_raw"] <= 36).all(), "fixture must exercise the confusable range"
        assert not (te["region"] == "rounds 1-3").any()


def test_conviction_hit_rate_is_reported_against_the_pooled_rate():
    """`hit_rate` alone cannot be compared to 0.5: selecting the top 20% of calls by
    |delta_value| lands everyone above a coin flip mechanically. The pooled difference is
    the comparable number, and it must sum to ~zero across experts by construction."""
    from fantasy_pipeline.analysis.scorecard import conviction_summary

    outcomes = _outcomes([float(30 - i) for i in range(20)])
    cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]
    market = _ranked("adp", list(range(1, 21)), kind="market")
    a = _ranked("a", [*range(5, 21), 1, 2, 3, 4])
    b = _ranked("b", [*range(3, 21), 1, 2])
    joined = pd.concat([market, a, b]).merge(outcomes[cols], on=["season", "player_id"])
    calls = conviction_calls(add_value_curve(joined, outcomes), outcomes)

    summary = conviction_summary(calls)
    assert "hit_rate_vs_pool" in summary.columns
    weighted = (summary["hit_rate_vs_pool"] * summary["n_calls"]).sum()
    assert weighted == pytest.approx(0.0, abs=1e-9)


def test_conviction_pool_is_computed_within_each_slice():
    """The size gradient recurs one level down — late-round calls hit far more often than
    early ones. A global pool would rank every expert's late cell above its early one and
    read as 'everyone is better late'. Within each slice level the difference must net out."""
    from fantasy_pipeline.analysis.scorecard import conviction_summary

    calls = pd.DataFrame(
        {
            "player_id": [f"P{i}" for i in range(12)],
            "expert": ["a"] * 3 + ["b"] * 3 + ["a"] * 3 + ["b"] * 3,
            "region": ["rounds 1-3"] * 6 + ["rounds 9+"] * 6,
            # Early region is hard (2/6 correct); late region is easy (5/6).
            "correct": [True, False, False, True, False, False, True, True, True, True, True, False],
            "value_added": 0.0,
            "delta_value": 1.0,
            "is_big_call": True,
        }
    )
    out = conviction_summary(calls, by=["expert", "region"], min_cell=1)
    for region, group in out.groupby("region"):
        weighted = (group["hit_rate_vs_pool"] * group["n_calls"]).sum()
        assert weighted == pytest.approx(0.0, abs=1e-9), f"{region} must net out within its own slice"


# --------------------------------------------------------------------------------------
# The 2023 boards: fp and pff arriving turned 2023 into a real head-to-head.
# --------------------------------------------------------------------------------------


class TestSupplementalPosFromPosRank:
    def test_position_is_parsed_from_the_positional_rank_prefix(self, tmp_path):
        """fp-2023 has no plain position column — only "WR1"/"RB12"."""
        from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

        (tmp_path / "fp-test.csv").write_text(
            "EXPERT RANKING,PLAYER NAME,POSITION RANK,ECR VS. ADP\n"
            "1,Christian McCaffrey,RB1,0\n"
            "2,CeeDee Lamb,WR1,2\n"
            "3,Justin Tucker,K1,0\n"
        )
        spec = SupplementalBoard(
            season=2023,
            expert="fp",
            filename="fp-test.csv",
            as_of_date="2023-08-01",
            name_col="PLAYER NAME",
            pos_col="POSITION RANK",
            pos_from="posrank_prefix",
            rank_col="EXPERT RANKING",
        )
        out = _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)
        assert set(out["pos"]) == {"RB", "WR"}, "K must be filtered like any other non-skill row"

    def test_positional_rank_is_derived_not_read_from_the_published_column(self, tmp_path):
        """We take the position LETTER from "WR12" but never the NUMBER — published
        positional columns are not dependable (the 2025 snapshot's POS ECR is all 1s)."""
        from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

        # Published positional ranks are deliberately nonsense; derived ones must be 1,2.
        (tmp_path / "fp-test.csv").write_text(
            "EXPERT RANKING,PLAYER NAME,POSITION RANK\n1,Christian McCaffrey,RB77\n2,Breece Hall,RB99\n"
        )
        spec = SupplementalBoard(
            season=2023,
            expert="fp",
            filename="fp-test.csv",
            as_of_date="2023-08-01",
            name_col="PLAYER NAME",
            pos_col="POSITION RANK",
            pos_from="posrank_prefix",
            rank_col="EXPERT RANKING",
        )
        out = _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)
        assert sorted(out["pos_rank"].tolist()) == [1, 2]
        assert out["pos_rank_derived"].all()

    def test_unknown_pos_from_raises(self, tmp_path):
        from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

        (tmp_path / "x.csv").write_text("R,PLAYER NAME,P\n1,Christian McCaffrey,RB1\n")
        spec = SupplementalBoard(
            season=2023,
            expert="fp",
            filename="x.csv",
            as_of_date="2023-08-01",
            name_col="PLAYER NAME",
            pos_col="P",
            pos_from="nonsense",
            rank_col="R",
        )
        with pytest.raises(ValueError, match="pos_from"):
            _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)


class TestMarketFromDelta:
    def test_market_is_reconstructed_as_rank_plus_delta_then_ranked(self, tmp_path):
        """FantasyPros' 2023 export has no ADP column, only `ECR VS. ADP`. The market is
        `rank + delta`, and it must be RANKED: the reconstructed values are integral but not
        dense (the real 2023 board spans 1..193 over 150 players), so the raw value is not a
        rank any more than Underdog's decimal ADP was."""
        from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

        (tmp_path / "fp-test.csv").write_text(
            "EXPERT RANKING,PLAYER NAME,POSITION RANK,ECR VS. ADP\n"
            "1,Christian McCaffrey,RB1,0\n"  # market 1
            "2,Travis Kelce,TE1,-1\n"  # market 1 -> ties CMC on raw value
            "3,CeeDee Lamb,WR1,50\n"  # market 53 -> far from dense
        )
        spec = SupplementalBoard(
            season=2023,
            expert="fp",
            filename="fp-test.csv",
            as_of_date="2023-08-01",
            name_col="PLAYER NAME",
            pos_col="POSITION RANK",
            pos_from="posrank_prefix",
            rank_col="EXPERT RANKING",
            market_col="ADP",
            market_expert="adp",
            market_from_delta_col="ECR VS. ADP",
        )
        out = _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)
        market = out[out["expert"] == "adp"]
        assert set(out["expert"]) == {"fp", "adp"}
        assert market["overall_rank"].max() == 3, "a rank, not the raw 53"
        # CMC and Kelce both reconstruct to 1, so min-ranking gives them 1 and 1, Lamb 3.
        assert sorted(market["overall_rank"].tolist()) == [1, 1, 3]

    def test_delta_column_takes_precedence_over_a_missing_market_col(self, tmp_path):
        from fantasy_pipeline.analysis.historical import SupplementalBoard, _load_supplemental_board

        (tmp_path / "f.csv").write_text("R,PLAYER NAME,P,D\n1,Christian McCaffrey,RB1,0\n2,Breece Hall,RB2,1\n")
        spec = SupplementalBoard(
            season=2023,
            expert="fp",
            filename="f.csv",
            as_of_date="2023-08-01",
            name_col="PLAYER NAME",
            pos_col="P",
            pos_from="posrank_prefix",
            rank_col="R",
            market_col="ADP",  # absent from the file
            market_expert="adp",
            market_from_delta_col="D",
        )
        out = _load_supplemental_board(spec, str(tmp_path), "player_key_dict.json", verbose=False)
        assert "adp" in set(out["expert"])


def test_2023_adp_is_not_scored_against_fp_that_built_it():
    """2023's market is reconstructed from FantasyPros' own ECR-VS-ADP column, so fp's
    'disagreement' with it is that column. True by arithmetic, not judgement."""
    from fantasy_pipeline.analysis.scorecard import SELF_REFERENTIAL_CALLS

    assert (2023, "fp") in SELF_REFERENTIAL_CALLS["adp"]


def test_conviction_exclude_is_scoped_to_the_named_season():
    """Excluding 2023 fp must not touch fp in any other season."""
    outcomes = _outcomes([float(30 - i) for i in range(20)])
    cols = ["season", "player_id", "pos", "games", "ppg_half", "pos_finish_rank"]
    frames = []
    for season in (2023, 2024):
        frames.append(_ranked("adp", list(range(1, 21)), season=season, kind="market"))
        frames.append(_ranked("fp", [*range(5, 21), 1, 2, 3, 4], season=season))
    joined = pd.concat(frames).merge(
        pd.concat([outcomes.assign(season=s) for s in (2023, 2024)])[cols],
        on=["season", "player_id"],
    )
    enriched = add_value_curve(joined, outcomes.assign(season=2023))
    calls = conviction_calls(enriched, outcomes, exclude=[(2023, "fp")])
    assert 2023 not in set(calls[calls["expert"] == "fp"]["season"])
    assert 2024 in set(calls[calls["expert"] == "fp"]["season"])
