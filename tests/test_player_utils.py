import pytest
import pandas as pd
from fantasy_pipeline.data.player_utils import clean_player_names, load_player_key_mapping, add_player_ids


class TestCleanPlayerNames:
    def test_normalizes_jr_suffix(self):
        df = pd.DataFrame({"PLAYER NAME": ["Marvin Harrison Jr.", "Patrick Mahomes"]})
        result = clean_player_names(df)
        assert result["PLAYER NAME"].iloc[0] == "Marvin Harrison Jr"

    def test_removes_special_chars(self):
        df = pd.DataFrame({"PLAYER NAME": ["Ja'Marr Chase", "D.K. Metcalf"]})
        result = clean_player_names(df)
        assert result["PLAYER NAME"].iloc[0] == "JaMarr Chase"
        assert result["PLAYER NAME"].iloc[1] == "DK Metcalf"

    def test_strips_whitespace(self):
        df = pd.DataFrame({"PLAYER NAME": ["  Patrick  Mahomes  "]})
        result = clean_player_names(df)
        assert result["PLAYER NAME"].iloc[0] == "Patrick Mahomes"

    def test_missing_column_returns_unchanged(self):
        df = pd.DataFrame({"NAME": ["Alice"]})
        result = clean_player_names(df)
        assert list(result.columns) == ["NAME"]

    def test_does_not_mutate_original(self):
        df = pd.DataFrame({"PLAYER NAME": ["Ja'Marr Chase"]})
        clean_player_names(df)
        assert df["PLAYER NAME"].iloc[0] == "Ja'Marr Chase"


class TestLoadPlayerKeyMapping:
    def test_loads_and_creates_reverse_mapping(self, tmp_player_key, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        player_key, name_to_key = load_player_key_mapping(tmp_player_key)
        assert "MahomPa01" in player_key
        assert name_to_key["Patrick Mahomes"] == "MahomPa01"
        assert name_to_key["Pat Mahomes"] == "MahomPa01"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_player_key_mapping("/nonexistent/path.json")

    def test_skip_save_reverse_mapping(self, tmp_player_key, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        player_key, name_to_key = load_player_key_mapping(tmp_player_key, save_reverse_mapping=False)
        assert len(name_to_key) > 0


class TestAddPlayerIds:
    def test_maps_known_players(self, sample_player_df, tmp_player_key, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _, name_to_key = load_player_key_mapping(tmp_player_key)
        result = add_player_ids(sample_player_df, name_to_key, verbose=False)
        assert result.loc[0, "PLAYER ID"] == "MahomPa01"
        assert result.loc[1, "PLAYER ID"] == "HillTy01"

    def test_unknown_players_get_nan(self, sample_player_df, tmp_player_key, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _, name_to_key = load_player_key_mapping(tmp_player_key)
        result = add_player_ids(sample_player_df, name_to_key, verbose=False)
        assert pd.isna(result.loc[2, "PLAYER ID"])

    def test_does_not_mutate_original(self, sample_player_df, tmp_player_key, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _, name_to_key = load_player_key_mapping(tmp_player_key)
        add_player_ids(sample_player_df, name_to_key, verbose=False)
        assert "PLAYER ID" not in sample_player_df.columns
