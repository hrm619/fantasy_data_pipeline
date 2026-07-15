"""Tests for the season-totals ingest (raw PFR exports -> combined_data.csv).

Ported from notebooks/ff-data.ipynb; these lock in the behaviours that made the notebook
version fragile — a hardcoded season list and a positional rename with no width check.
"""

import pandas as pd
import pytest

from fantasy_pipeline.core.season_data_builder import (
    PFR_SEASON_COLUMNS,
    build_combined_season_data,
    discover_season_files,
    load_season_file,
)


def _write_pfr_export(path, rows):
    """Write an .xlsx shaped like PFR's fantasy export: group row, header row, then data."""
    group = [None, None, None, None, None, "Games", "Games", "Passing"] + [None] * (len(PFR_SEASON_COLUMNS) - 8)
    header = ["Rk", "Player", "Tm", "FantPos", "Age", "G", "GS", "Cmp"] + [
        f"c{i}" for i in range(len(PFR_SEASON_COLUMNS) - 8)
    ]
    body = [group, header, *rows]
    pd.DataFrame(body).to_excel(path, index=False, header=False)


def _player_row(rank, name):
    return [rank, name, "DET", "RB", 26] + [0] * (len(PFR_SEASON_COLUMNS) - 5)


class TestDiscoverSeasonFiles:
    def test_finds_season_files_and_parses_years(self, tmp_path):
        for year in (2024, 2025):
            (tmp_path / f"s{year}.xlsx").write_text("")
        assert sorted(discover_season_files(str(tmp_path))) == [2024, 2025]

    def test_ignores_unrelated_files(self, tmp_path):
        (tmp_path / "s2025.xlsx").write_text("")
        (tmp_path / "combined_data.csv").write_text("")
        (tmp_path / "draft_2025.csv").write_text("")
        (tmp_path / "weekly_data.csv").write_text("")
        assert list(discover_season_files(str(tmp_path))) == [2025]

    def test_returns_seasons_ascending(self, tmp_path):
        for year in (2025, 2014, 2020):
            (tmp_path / f"s{year}.xlsx").write_text("")
        assert list(discover_season_files(str(tmp_path))) == [2014, 2020, 2025]

    def test_raises_when_no_season_files(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No season files"):
            discover_season_files(str(tmp_path))

    def test_raises_when_dir_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            discover_season_files(str(tmp_path / "nope"))


class TestLoadSeasonFile:
    def test_applies_schema_and_stamps_season(self, tmp_path):
        p = tmp_path / "s2025.xlsx"
        _write_pfr_export(p, [_player_row(1, "Jonathan Taylor")])
        df = load_season_file(str(p), 2025)
        assert list(df.columns) == PFR_SEASON_COLUMNS + ["SEASON"]
        assert df["SEASON"].tolist() == [2025]
        assert df["PLAYER NAME"].tolist() == ["Jonathan Taylor"]

    def test_drops_the_real_header_row_not_a_player(self, tmp_path):
        # read_excel consumes the group row as columns, so row 0 of the data is the header.
        p = tmp_path / "s2025.xlsx"
        _write_pfr_export(p, [_player_row(1, "Jonathan Taylor"), _player_row(2, "Bijan Robinson")])
        df = load_season_file(str(p), 2025)
        assert len(df) == 2
        assert "Rk" not in df["OVERALL RK"].astype(str).tolist()

    def test_strips_pfr_award_markers_and_punctuation(self, tmp_path):
        # PFR decorates names ('Saquon Barkley*+'); the player key expects letters/spaces only.
        p = tmp_path / "s2025.xlsx"
        _write_pfr_export(p, [_player_row(1, "Saquon Barkley*+"), _player_row(2, "Amon-Ra St. Brown")])
        df = load_season_file(str(p), 2025)
        assert df["PLAYER NAME"].tolist() == ["Saquon Barkley", "AmonRa St Brown"]

    def test_raises_on_column_width_change(self, tmp_path):
        # Names are applied positionally, so a width change would silently mislabel every
        # column rather than fail — check it loudly instead.
        p = tmp_path / "s2025.xlsx"
        short = [[None] * 5, ["Rk", "Player", "Tm", "FantPos", "Age"], [1, "X", "DET", "RB", 26]]
        pd.DataFrame(short).to_excel(p, index=False, header=False)
        with pytest.raises(ValueError, match="columns, expected"):
            load_season_file(str(p), 2025)


class TestBuildCombinedSeasonData:
    def test_concatenates_all_seasons(self, tmp_path):
        _write_pfr_export(tmp_path / "s2024.xlsx", [_player_row(1, "Old Guy")])
        _write_pfr_export(tmp_path / "s2025.xlsx", [_player_row(1, "New Guy"), _player_row(2, "Rookie")])
        df = build_combined_season_data(input_dir=str(tmp_path), output_path=None, verbose=False)
        assert len(df) == 3
        assert sorted(df["SEASON"].unique()) == [2024, 2025]

    def test_picks_up_a_newly_added_season_without_config(self, tmp_path):
        # The notebook carried a hardcoded season list, so a new s<year>.xlsx was a silent
        # no-op until someone edited it. Seasons come from filenames now.
        _write_pfr_export(tmp_path / "s2024.xlsx", [_player_row(1, "Old Guy")])
        first = build_combined_season_data(input_dir=str(tmp_path), output_path=None, verbose=False)
        assert sorted(first["SEASON"].unique()) == [2024]

        _write_pfr_export(tmp_path / "s2025.xlsx", [_player_row(1, "New Guy")])
        second = build_combined_season_data(input_dir=str(tmp_path), output_path=None, verbose=False)
        assert sorted(second["SEASON"].unique()) == [2024, 2025]

    def test_writes_csv_when_output_path_given(self, tmp_path):
        _write_pfr_export(tmp_path / "s2025.xlsx", [_player_row(1, "New Guy")])
        out = tmp_path / "out" / "combined_data.csv"
        build_combined_season_data(input_dir=str(tmp_path), output_path=str(out), verbose=False)
        assert out.exists()
        assert list(pd.read_csv(out).columns) == PFR_SEASON_COLUMNS + ["SEASON"]
