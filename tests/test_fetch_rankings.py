"""Tests for the FantasyPros ADP fetcher's parsing + pipeline-schema output.

Uses an inline HTML fixture so the suite never hits the network.
"""

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    ADP_OUTPUT_COLUMNS,
    FP_OUTPUT_COLUMNS,
    _parse_fantasypros_adp,
    _parse_fantasypros_rankings,
    _parse_player_cell,
)


# Mirrors the live page's single consensus table: Rank | PlayerTeam(Bye) | POS | AVG
ADP_HTML = """
<html><body>
<table>
  <tr><th>Rank</th><th>PlayerTeam (Bye)</th><th>POS</th><th>AVG</th></tr>
  <tr><td>1</td><td>Jahmyr GibbsDET(6)</td><td>RB1</td><td>1.5</td></tr>
  <tr><td>2</td><td>Ja'Marr ChaseCIN(10)</td><td>WR1</td><td>3.0</td></tr>
  <tr><td>3</td><td>Saquon BarkleyPHI(9)O</td><td>RB2</td><td>4.2</td></tr>
</table>
</body></html>
"""


class TestParseFantasyProsADP:
    def test_parses_all_player_rows(self):
        rows = _parse_fantasypros_adp(ADP_HTML)
        assert len(rows) == 3

    def test_extracts_name_team_bye_pos_adp(self):
        gibbs = _parse_fantasypros_adp(ADP_HTML)[0]
        assert gibbs["PLAYER NAME"] == "Jahmyr Gibbs"
        assert gibbs["TEAM"] == "DET"
        assert gibbs["BYE"] == "6"
        assert gibbs["POS"] == "RB"  # positional-rank digit stripped from "RB1"
        assert gibbs["ADP"] == "1.5"

    def test_strips_injury_designation(self):
        saquon = _parse_fantasypros_adp(ADP_HTML)[2]
        assert saquon["PLAYER NAME"] == "Saquon Barkley"
        assert saquon["TEAM"] == "PHI"
        assert saquon["BYE"] == "9"

    def test_preserves_apostrophe_in_name(self):
        chase = _parse_fantasypros_adp(ADP_HTML)[1]
        assert chase["PLAYER NAME"] == "Ja'Marr Chase"

    def test_output_keys_match_pipeline_schema_order(self):
        row = _parse_fantasypros_adp(ADP_HTML)[0]
        assert list(row.keys()) == ADP_OUTPUT_COLUMNS

    def test_market_index_and_rt_are_blank_placeholders(self):
        row = _parse_fantasypros_adp(ADP_HTML)[0]
        assert row["MARKET INDEX"] == ""
        assert row["RT"] == ""

    def test_raises_when_table_missing(self):
        with pytest.raises(RuntimeError, match="Failed to parse ADP table"):
            _parse_fantasypros_adp("<html><body>no table here</body></html>")


class TestSchemaContract:
    def test_output_columns_equal_pipeline_adp_mapping(self):
        # Guard: fetcher output must stay aligned with the pipeline's positional rename.
        assert ADP_OUTPUT_COLUMNS == COLUMN_MAPPINGS["adp"]


class TestParsePlayerCell:
    def test_standard_cell(self):
        assert _parse_player_cell("Jahmyr GibbsDET(6)") == ("Jahmyr Gibbs", "DET", "6")

    def test_cell_with_injury_tag(self):
        assert _parse_player_cell("Saquon BarkleyPHI(9)O") == ("Saquon Barkley", "PHI", "9")

    def test_unparseable_cell_falls_back(self):
        assert _parse_player_cell("Weird Name") == ("Weird Name", "", "")


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
