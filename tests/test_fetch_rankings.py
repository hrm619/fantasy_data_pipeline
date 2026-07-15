"""Tests for the FantasyPros ADP fetcher's parsing + pipeline-schema output.

Uses inline HTML fixtures so the suite never hits the network.
"""

import json

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    ADP_OUTPUT_COLUMNS,
    FP_OUTPUT_COLUMNS,
    _parse_fantasypros_adp,
    _parse_fantasypros_rankings,
    _split_team_bye,
)


def _adp_html(rows, fenced=False):
    """Build a page embedding `window.FP.reportConfig`, as the live ADP report does."""
    config = {
        "type": "nfl_adp",
        "registrationFence": fenced,
        "table": {
            "fields": [{"key": "rank"}, {"key": "player"}, {"key": "pos"}, {"key": "avg"}],
            "rows": rows,
        },
    }
    # The trailing `;` and sibling assignment mirror the real page, where a naive
    # non-greedy regex could over/under-match.
    return (
        "<html><body><script>\n"
        "  window.FP = window.FP || {};\n"
        f"  window.FP.reportConfig = {json.dumps(config)};\n"
        '  window.FP.other = {"x": 1};\n'
        "</script></body></html>"
    )


def _row(rank, name, team, pos, avg):
    return {"id": rank, "rank": rank, "player": {"id": rank, "name": name, "team": team}, "pos": pos, "avg": avg}


ADP_ROWS = [
    _row(1, "Jahmyr Gibbs", "DET (6)", "RB1", 1.5),
    _row(2, "Ja'Marr Chase", "CIN (10)", "WR1", 3.0),
    _row(3, "Saquon Barkley", "PHI (9)", "RB2", 4.2),
]
ADP_HTML = _adp_html(ADP_ROWS)


class TestParseFantasyProsADP:
    def test_parses_all_player_rows(self):
        assert len(_parse_fantasypros_adp(ADP_HTML)) == 3

    def test_extracts_name_team_bye_pos_adp(self):
        gibbs = _parse_fantasypros_adp(ADP_HTML)[0]
        assert gibbs["PLAYER NAME"] == "Jahmyr Gibbs"
        assert gibbs["TEAM"] == "DET"
        assert gibbs["BYE"] == "6"
        assert gibbs["POS"] == "RB"  # positional-rank digit stripped from "RB1"
        assert gibbs["ADP"] == "1.5"

    def test_preserves_apostrophe_in_name(self):
        assert _parse_fantasypros_adp(ADP_HTML)[1]["PLAYER NAME"] == "Ja'Marr Chase"

    def test_output_keys_match_pipeline_schema_order(self):
        assert list(_parse_fantasypros_adp(ADP_HTML)[0].keys()) == ADP_OUTPUT_COLUMNS

    def test_market_index_and_rt_are_blank_placeholders(self):
        row = _parse_fantasypros_adp(ADP_HTML)[0]
        assert row["MARKET INDEX"] == ""
        assert row["RT"] == ""

    def test_skips_rows_without_a_player_name(self):
        html = _adp_html(ADP_ROWS + [{"rank": 4, "player": {}, "pos": "TE1", "avg": 9.9}])
        assert len(_parse_fantasypros_adp(html)) == 3

    def test_ignores_sibling_assignments_after_the_blob(self):
        # raw_decode must stop at the reportConfig object, not swallow `window.FP.other`.
        assert len(_parse_fantasypros_adp(ADP_HTML)) == 3

    def test_raises_when_report_config_missing(self):
        with pytest.raises(RuntimeError, match="reportConfig"):
            _parse_fantasypros_adp("<html><body>no data here</body></html>")

    def test_raises_on_registration_fenced_teaser(self):
        # Anonymous visitors get `registrationFence: true` plus a handful of rows; that must
        # surface as a login instruction, not silently become a 3-player ADP board.
        with pytest.raises(RuntimeError, match="registration-fenced"):
            _parse_fantasypros_adp(_adp_html(ADP_ROWS, fenced=True))

    def test_full_board_parses_even_when_fence_flag_set(self):
        # A logged-in session can still carry the flag while returning the full board.
        rows = [_row(i, f"Player {i}", "DET (6)", f"RB{i}", i) for i in range(1, 40)]
        assert len(_parse_fantasypros_adp(_adp_html(rows, fenced=True))) == 39


class TestSchemaContract:
    def test_output_columns_equal_pipeline_adp_mapping(self):
        # Guard: fetcher output must stay aligned with the pipeline's positional rename.
        assert ADP_OUTPUT_COLUMNS == COLUMN_MAPPINGS["adp"]


class TestSplitTeamBye:
    def test_standard_cell(self):
        assert _split_team_bye("DET (6)") == ("DET", "6")

    def test_two_letter_team(self):
        assert _split_team_bye("SF (14)") == ("SF", "14")

    def test_cell_without_bye_falls_back(self):
        assert _split_team_bye("FA") == ("FA", "")

    def test_empty_cell(self):
        assert _split_team_bye("") == ("", "")


# Mirrors the `var ecrData = {...}` JSON blob embedded on FantasyPros cheatsheet pages.
FP_HTML = """
<html><body><script>
var ecrData = {"sport":"NFL","players":[
  {"rank_ecr":1,"tier":1,"player_name":"Ja'Marr Chase","player_team_id":"CIN","player_position_id":"WR","player_bye_week":"6"},
  {"rank_ecr":2,"tier":1,"player_name":"Bijan Robinson","player_team_id":"ATL","player_position_id":"RB","player_bye_week":"11"}
]};
var other = {"x": 1};
</script></body></html>
"""


class TestParseFantasyProsRankings:
    def test_parses_all_players(self):
        assert len(_parse_fantasypros_rankings(FP_HTML)) == 2

    def test_maps_ecr_tier_name_team_pos_bye(self):
        chase = _parse_fantasypros_rankings(FP_HTML)[0]
        assert chase["ECR"] == 1
        assert chase["TIER"] == 1
        assert chase["PLAYER NAME"] == "Ja'Marr Chase"
        assert chase["TEAM"] == "CIN"
        assert chase["POS"] == "WR"
        assert chase["BYE"] == "6"

    def test_output_keys_match_pipeline_schema_order(self):
        row = _parse_fantasypros_rankings(FP_HTML)[0]
        assert list(row.keys()) == FP_OUTPUT_COLUMNS

    def test_sos_and_ecr_vs_adp_blank(self):
        row = _parse_fantasypros_rankings(FP_HTML)[0]
        assert row["SOS"] == ""
        assert row["ECR VS ADP"] == ""

    def test_raises_when_ecrdata_missing(self):
        with pytest.raises(RuntimeError, match="ecrData"):
            _parse_fantasypros_rankings("<html><body>no data</body></html>")


class TestFpSchemaContract:
    def test_output_columns_equal_pipeline_fp_mapping(self):
        assert FP_OUTPUT_COLUMNS == COLUMN_MAPPINGS["fp"]


# ---------------------------------------------------------------------------
# FantasyPros weekly leaders (ff-stats' --weekly-data input)
# ---------------------------------------------------------------------------

WEEKLY_ROWS = [
    {
        "id": 1,
        "rank": 1,
        "player": {"id": 1, "name": "Josh Allen", "team": "BUF"},
        "pos": "QB",
        "games": 17,
        **{f"wk_{w}": (float(w) if w != 7 else "BYE") for w in range(1, 19)},
        "avg": 22.0,
        "points": 374.6,
    }
]


def _weekly_html(rows):
    config = {"type": "nfl_leaders", "table": {"fields": [{"key": "rank"}], "rows": rows}}
    return f"<html><body><script>window.FP.reportConfig = {json.dumps(config)};</script></body></html>"


class TestParseFpWeeklyLeaders:
    def test_maps_to_weekly_data_schema(self):
        from fantasy_pipeline.scraper.fetch_rankings import WEEKLY_LEADERS_COLUMNS, _parse_fp_weekly_leaders

        row = _parse_fp_weekly_leaders(_weekly_html(WEEKLY_ROWS), 2025)[0]
        assert list(row.keys()) == WEEKLY_LEADERS_COLUMNS
        assert row["#"] == 1
        assert row["PLAYER NAME"] == "Josh Allen"
        assert row["POS"] == "QB"
        assert row["TEAM"] == "BUF"
        assert row["AVG"] == 22.0
        assert row["TOTAL"] == 374.6

    def test_stamps_the_season(self):
        # The legacy hand-downloaded file had no season, which is how weekly trends and
        # season totals silently drifted apart.
        from fantasy_pipeline.scraper.fetch_rankings import _parse_fp_weekly_leaders

        assert _parse_fp_weekly_leaders(_weekly_html(WEEKLY_ROWS), 2025)[0]["SEASON"] == 2025

    def test_bye_weeks_pass_through_as_literal_string(self):
        from fantasy_pipeline.scraper.fetch_rankings import _parse_fp_weekly_leaders

        row = _parse_fp_weekly_leaders(_weekly_html(WEEKLY_ROWS), 2025)[0]
        assert row["7"] == "BYE"
        assert row["1"] == 1.0

    def test_all_18_week_columns_present(self):
        from fantasy_pipeline.scraper.fetch_rankings import _parse_fp_weekly_leaders

        row = _parse_fp_weekly_leaders(_weekly_html(WEEKLY_ROWS), 2025)[0]
        for week in range(1, 19):
            assert str(week) in row

    def test_skips_rows_without_a_player_name(self):
        from fantasy_pipeline.scraper.fetch_rankings import _parse_fp_weekly_leaders

        rows = WEEKLY_ROWS + [{"rank": 2, "player": {}, "pos": "RB", "avg": 1, "points": 1}]
        assert len(_parse_fp_weekly_leaders(_weekly_html(rows), 2025)) == 1

    def test_unknown_scoring_raises(self):
        from fantasy_pipeline.scraper.fetch_rankings import fetch_fp_weekly_leaders

        with pytest.raises(ValueError, match="Unknown scoring"):
            fetch_fp_weekly_leaders("/tmp/x.csv", year=2025, scoring="bogus")
