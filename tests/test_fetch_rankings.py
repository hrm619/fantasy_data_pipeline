"""Tests for the ADP + FantasyPros rankings fetchers' parsing and pipeline-schema output.

Uses inline fixtures so the suite never hits the network.
"""

import json

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    ADP_OUTPUT_COLUMNS,
    FP_OUTPUT_COLUMNS,
    _assert_ds_adp_board,
    _parse_ds_adp_export,
    _parse_fantasypros_rankings,
    _round_pick_to_overall,
    ds_adp_page_url,
)


# DraftSharks' ADP export. The 4th header is an echo of the `adp1_name` we send, not a
# fixed label — the parser must key on position, not on this text.
DS_ADP_CSV = (
    '"Player Name", "Player Team", "Player Position", Sleeper: Redraft 0.5 PPR ADP, "Market Index 1",\n'
    '"Bijan Robinson","ATL","RB","1.1","-2",\n'
    '"Ja\'Marr Chase","CIN","WR","1.10","-1",\n'
    '"Ashton Jeanty","LVR","RB","2.1","1",\n'
    '"Deep Sleeper","NYJ","TE","25.12","4",\n'
)


class TestRoundPickToOverall:
    def test_first_pick(self):
        assert _round_pick_to_overall("1.1", 12) == 1

    def test_pick_ten_is_not_one_point_one(self):
        # The whole reason this conversion exists: '1.10' floats to 1.1, colliding with
        # '1.1' and sorting below '1.2'. As an overall pick it is unambiguous.
        assert _round_pick_to_overall("1.10", 12) == 10
        assert _round_pick_to_overall("1.1", 12) == 1

    def test_round_boundary(self):
        assert _round_pick_to_overall("1.12", 12) == 12
        assert _round_pick_to_overall("2.1", 12) == 13

    def test_last_pick_of_a_25_round_draft(self):
        assert _round_pick_to_overall("25.12", 12) == 300

    def test_ordering_is_monotonic_unlike_float_parsing(self):
        picks = ["1.1", "1.2", "1.10", "1.11", "1.12", "2.1"]
        overall = [_round_pick_to_overall(p, 12) for p in picks]
        assert overall == sorted(overall)
        # float() would order these wrongly, which is exactly the silent corruption.
        assert [float(p) for p in picks] != sorted(float(p) for p in picks)

    def test_respects_league_size(self):
        assert _round_pick_to_overall("2.1", 10) == 11

    @pytest.mark.parametrize("value", ["", "   ", "N/A", "-", "abc"])
    def test_unparseable_returns_none(self, value):
        assert _round_pick_to_overall(value, 12) is None

    def test_pick_beyond_league_size_raises(self):
        # A pick of 13 in a 12-team league means the board isn't the size we asked for;
        # converting anyway would silently produce wrong overall picks.
        with pytest.raises(RuntimeError, match="league size"):
            _round_pick_to_overall("1.13", 12)


class TestParseDSADPExport:
    def test_parses_all_player_rows(self):
        assert len(_parse_ds_adp_export(DS_ADP_CSV, 12)) == 4

    def test_extracts_name_team_pos_and_overall_adp(self):
        bijan = _parse_ds_adp_export(DS_ADP_CSV, 12)[0]
        assert bijan["PLAYER NAME"] == "Bijan Robinson"
        assert bijan["TEAM"] == "ATL"
        assert bijan["POS"] == "RB"
        assert bijan["ADP"] == 1
        assert bijan["MARKET INDEX"] == "-2"

    def test_adp_is_converted_to_overall_pick(self):
        rows = {r["PLAYER NAME"]: r["ADP"] for r in _parse_ds_adp_export(DS_ADP_CSV, 12)}
        assert rows["Ja'Marr Chase"] == 10  # '1.10'
        assert rows["Ashton Jeanty"] == 13  # '2.1'
        assert rows["Deep Sleeper"] == 300  # '25.12'

    def test_preserves_apostrophe_in_name(self):
        assert _parse_ds_adp_export(DS_ADP_CSV, 12)[1]["PLAYER NAME"] == "Ja'Marr Chase"

    def test_output_keys_match_pipeline_schema_order(self):
        assert list(_parse_ds_adp_export(DS_ADP_CSV, 12)[0].keys()) == ADP_OUTPUT_COLUMNS

    def test_bye_and_rt_are_blank_placeholders(self):
        # DraftSharks' export carries no bye; the processor discards both anyway.
        row = _parse_ds_adp_export(DS_ADP_CSV, 12)[0]
        assert row["BYE"] == ""
        assert row["RT"] == ""

    def test_ignores_the_echoed_adp_column_label(self):
        # The 4th header is whatever adp1_name we sent, so a different label must still parse.
        renamed = DS_ADP_CSV.replace("Sleeper: Redraft 0.5 PPR ADP", "Anything At All")
        assert len(_parse_ds_adp_export(renamed, 12)) == 4

    def test_skips_rows_without_a_usable_adp(self):
        csv_text = DS_ADP_CSV + '"No ADP Guy","SF","WR","",""\n'
        names = [r["PLAYER NAME"] for r in _parse_ds_adp_export(csv_text, 12)]
        assert "No ADP Guy" not in names

    def test_skips_rows_without_a_name(self):
        csv_text = DS_ADP_CSV + '"","SF","WR","3.1","0",\n'
        assert len(_parse_ds_adp_export(csv_text, 12)) == 4

    def test_drops_team_aggregate_rows(self):
        # DraftSharks emits a TQB (team-QB) row per team, named after the team — so it
        # collides with that team's DEF row. Two rows under one name is the duplicate-row
        # bug waiting to happen, and TQB isn't a position this pipeline drafts.
        csv_text = DS_ADP_CSV + '"Detroit Lions","DET","TQB","12.8","0",\n"Detroit Lions","DET","DEF","23.3","-58",\n'
        rows = _parse_ds_adp_export(csv_text, 12)
        lions = [r for r in rows if r["PLAYER NAME"] == "Detroit Lions"]
        assert len(lions) == 1
        assert lions[0]["POS"] == "DEF"
        assert lions[0]["ADP"] == 267

    def test_keeps_every_drafted_position(self):
        csv_text = DS_ADP_CSV.splitlines()[0] + "\n"
        for i, pos in enumerate(["QB", "RB", "WR", "TE", "K", "DEF"], start=1):
            csv_text += f'"Player {i}","SF","{pos}","{i}.1","0",\n'
        assert len(_parse_ds_adp_export(csv_text, 12)) == 6

    def test_raises_when_header_layout_drifts(self):
        with pytest.raises(RuntimeError, match="layout changed"):
            _parse_ds_adp_export('"Name","Squad","Spot","ADP"\n"X","SF","WR","1.1"\n', 12)

    def test_raises_on_empty_export(self):
        with pytest.raises(RuntimeError, match="empty"):
            _parse_ds_adp_export("", 12)

    def test_header_only_export_yields_no_players(self):
        # An unknown board id returns HTTP 200 + a bare header; the coverage floor in the
        # fetcher is what turns this into an error, so the parser just returns nothing.
        header = DS_ADP_CSV.splitlines()[0]
        assert _parse_ds_adp_export(header + "\n", 12) == []


class TestAssertDSADPBoard:
    def test_accepts_the_requested_board(self):
        _assert_ds_adp_board("Sleeper: Redraft 0.5 PPR ADP", "sleeper", "half-ppr")

    def test_rejects_a_different_platform(self):
        # The export happily serves a full, plausible board for the wrong platform if the
        # ids drift, so a label naming ESPN must never be saved as Sleeper ADP.
        with pytest.raises(RuntimeError, match="does not name 'sleeper'"):
            _assert_ds_adp_board("ESPN: Redraft 0.5 PPR ADP", "sleeper", "half-ppr")

    def test_rejects_a_different_scoring(self):
        with pytest.raises(RuntimeError, match="0.5 ppr"):
            _assert_ds_adp_board("Sleeper: Redraft PPR ADP", "sleeper", "half-ppr")

    def test_rejects_an_empty_label(self):
        with pytest.raises(RuntimeError, match="does not name 'sleeper'"):
            _assert_ds_adp_board("", "sleeper", "half-ppr")

    def test_is_case_insensitive(self):
        _assert_ds_adp_board("SLEEPER: REDRAFT 0.5 PPR ADP", "sleeper", "half-ppr")


class TestDSADPPageURL:
    def test_defaults_to_the_sleeper_12_team_half_ppr_board(self):
        assert ds_adp_page_url() == "https://www.draftsharks.com/adp/half-ppr/sleeper/12"

    def test_builds_other_boards(self):
        assert ds_adp_page_url("espn", "ppr", 10) == "https://www.draftsharks.com/adp/ppr/espn/10"


class TestSchemaContract:
    def test_output_columns_equal_pipeline_adp_mapping(self):
        # Guard: fetcher output must stay aligned with the pipeline's positional rename.
        assert ADP_OUTPUT_COLUMNS == COLUMN_MAPPINGS["adp"]


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
