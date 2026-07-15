"""Tests for the historical-stats aggregation guards.

Covers the two silent failure modes this module had: pairing weekly data from one season with
season totals from another, and pandas cross-joining rows whose join key is null.
"""

import numpy as np
import pandas as pd
import pytest

from fantasy_pipeline.core.stats_aggregator import _merge_season_and_weekly_data, _verify_weekly_season


def _weekly(season=2025, rows=2):
    df = pd.DataFrame(
        {
            "PLAYER NAME": [f"Player {i}" for i in range(rows)],
            "AVG": [10.0] * rows,
            "TOTAL": [170.0] * rows,
        }
    )
    if season is not None:
        df["SEASON"] = season
    return df


class TestVerifyWeeklySeason:
    """The weekly file holds ONE unlabelled season while the totals are filtered by SEASON.

    Nothing tied them together, so updating one and not the other mixed seasons inside HIST_*
    silently. Files from `ff-stats fetch-weekly` carry SEASON so a mismatch is an error.
    """

    def test_passes_and_drops_season_when_matching(self):
        out = _verify_weekly_season(_weekly(2025), 2025, "w.csv", verbose=False)
        # SEASON must not survive: downstream merges against season data that has its own.
        assert "SEASON" not in out.columns
        assert len(out) == 2

    def test_raises_on_season_mismatch(self):
        with pytest.raises(ValueError, match="Season mismatch"):
            _verify_weekly_season(_weekly(2024), 2025, "w.csv", verbose=False)

    def test_raises_when_season_column_missing(self):
        with pytest.raises(ValueError, match="no SEASON column"):
            _verify_weekly_season(_weekly(season=None), 2025, "w.csv", verbose=False)

    def test_raises_when_weekly_spans_multiple_seasons(self):
        df = _weekly(2025)
        df.loc[1, "SEASON"] = 2024
        with pytest.raises(ValueError, match="spans seasons"):
            _verify_weekly_season(df, 2025, "w.csv", verbose=False)

    def test_no_season_filter_accepts_any_stamped_season(self):
        out = _verify_weekly_season(_weekly(2024), None, "w.csv", verbose=False)
        assert "SEASON" not in out.columns


class TestMergeNullPlayerIds:
    """pandas joins null == null; SQL does not.

    Unmatched players carry PLAYER_ID = None on both sides, so an ID merge cross-joined every
    unmatched season player against every unmatched weekly player, pairing unrelated players'
    stats. It stayed hidden while one side had zero unmatched rows (2024), then produced 6936
    phantom rows the moment 2025 brought players missing from the player key.
    """

    def _frames(self, season_ids, weekly_ids):
        season = pd.DataFrame(
            {
                "PLAYER NAME": [f"S{i}" for i in range(len(season_ids))],
                "PLAYER_ID": season_ids,
                "TOTAL_FPTS": [100.0] * len(season_ids),
            }
        )
        weekly = pd.DataFrame(
            {
                "PLAYER NAME": [f"W{i}" for i in range(len(weekly_ids))],
                "PLAYER_ID": weekly_ids,
                "FIRST_HALF_AVG": [5.0] * len(weekly_ids),
            }
        )
        return season, weekly

    def test_null_ids_do_not_cross_join(self):
        season, weekly = self._frames(["A", None, None], ["A", None, None, None])
        out = _merge_season_and_weekly_data(season, weekly, {}, verbose=False)
        # One row per season player — never 1 + (2 x 3).
        assert len(out) == 3

    def test_matched_ids_still_merge(self):
        season, weekly = self._frames(["A", "B"], ["A", "B"])
        out = _merge_season_and_weekly_data(season, weekly, {}, verbose=False)
        assert len(out) == 2
        assert out["FIRST_HALF_AVG"].notna().all()

    def test_unmatched_season_player_keeps_row_with_null_weekly(self):
        season, weekly = self._frames(["A", None], ["A"])
        out = _merge_season_and_weekly_data(season, weekly, {}, verbose=False)
        assert len(out) == 2
        # The null-ID season player survives, just without weekly trends.
        assert out["FIRST_HALF_AVG"].isna().sum() == 1

    def test_every_season_row_survives_when_no_weekly_matches(self):
        season, weekly = self._frames([None, None], [None])
        out = _merge_season_and_weekly_data(season, weekly, {}, verbose=False)
        assert len(out) == 2
        assert out["FIRST_HALF_AVG"].isna().all()

    def test_regression_shape_matches_documented_explosion(self):
        # 2 unmatched season x 3 unmatched weekly = 6 phantom rows under the old behaviour.
        season, weekly = self._frames(["A", None, None], [None, None, None])
        out = _merge_season_and_weekly_data(season, weekly, {}, verbose=False)
        assert len(out) == 3
        assert not np.isclose(len(out), 1 + 2 * 3)


class TestDedupeSeasonRows:
    """PFR normally emits ONE row per traded player (TEAM='2TM'), but rarely also emits the
    per-team fragments alongside it. Those extras are partial (fewer games, blank points) and
    give a player two HIST_ rows, which then multiply his board rows on merge.
    """

    def _frame(self, rows):
        return pd.DataFrame(rows, columns=["PLAYER NAME", "TEAM", "G", "PPR", "ID"])

    def test_keeps_the_combined_multi_team_row(self):
        from fantasy_pipeline.core.stats_aggregator import _dedupe_season_rows

        df = self._frame([["Ben Tate", "3TM", 11, 76.1, "TateBe00"], ["Ben Tate", "PIT", 0, np.nan, "TateBe00"]])
        out = _dedupe_season_rows(df, verbose=False)
        assert len(out) == 1
        assert out.iloc[0]["TEAM"] == "3TM"

    def test_keeps_the_team_actually_played_for_when_no_combined_row(self):
        from fantasy_pipeline.core.stats_aggregator import _dedupe_season_rows

        # Elijah Moore 2025: BUF 9 games, DEN 0 games, no 2TM row.
        df = self._frame([["Elijah Moore", "BUF", 9, 28.6, "MoorEl00"], ["Elijah Moore", "DEN", 0, np.nan, "MoorEl00"]])
        out = _dedupe_season_rows(df, verbose=False)
        assert len(out) == 1
        assert out.iloc[0]["TEAM"] == "BUF"

    def test_tie_on_games_prefers_the_row_with_points(self):
        from fantasy_pipeline.core.stats_aggregator import _dedupe_season_rows

        df = self._frame([["X Y", "ARI", 4, np.nan, "XxxxYy00"], ["X Y", "2TM", 4, 12.0, "XxxxYy00"]])
        out = _dedupe_season_rows(df, verbose=False)
        assert len(out) == 1
        assert out.iloc[0]["TEAM"] == "2TM"

    def test_leaves_unduplicated_data_untouched(self):
        from fantasy_pipeline.core.stats_aggregator import _dedupe_season_rows

        df = self._frame([["A B", "DET", 17, 300.0, "AbcdAb00"], ["C D", "ATL", 17, 280.0, "CdefCd00"]])
        out = _dedupe_season_rows(df, verbose=False)
        assert len(out) == 2
        assert list(out["PLAYER NAME"]) == ["A B", "C D"]  # original order preserved

    def test_rows_without_an_id_are_all_kept(self):
        from fantasy_pipeline.core.stats_aggregator import _dedupe_season_rows

        # No id means we can't tell them apart — dropping them would lose real players.
        df = self._frame([["A B", "DET", 5, 1.0, None], ["C D", "ATL", 5, 2.0, None]])
        assert len(_dedupe_season_rows(df, verbose=False)) == 2

    def test_no_id_column_is_a_noop(self):
        from fantasy_pipeline.core.stats_aggregator import _dedupe_season_rows

        df = pd.DataFrame({"PLAYER NAME": ["A B"], "G": [1]})
        assert len(_dedupe_season_rows(df, verbose=False)) == 1
