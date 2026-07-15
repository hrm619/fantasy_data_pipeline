import pytest
import pandas as pd
from fantasy_pipeline.data.player_utils import (
    add_player_ids,
    build_suffix_fallback_index,
    clean_player_names,
    load_player_key_mapping,
    strip_generational_suffix,
)


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


class TestStripGenerationalSuffix:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("James Cook III", "James Cook"),
            ("Chris Godwin Jr", "Chris Godwin"),
            ("Kyle Pitts Sr", "Kyle Pitts"),
            ("David Sills V", "David Sills"),
            ("Patrick Mahomes II", "Patrick Mahomes"),
            ("Marvin Harrison IV", "Marvin Harrison"),
        ],
    )
    def test_strips_suffixes(self, name, expected):
        assert strip_generational_suffix(name) == expected

    def test_is_case_insensitive(self):
        assert strip_generational_suffix("James Cook iii") == "James Cook"

    @pytest.mark.parametrize("name", ["James Cook", "Ja'Marr Chase", "Amon-Ra St. Brown"])
    def test_leaves_plain_names_alone(self, name):
        assert strip_generational_suffix(name) == name

    def test_only_strips_a_trailing_suffix(self):
        # 'V' mid-name is part of the name, not a generational marker.
        assert strip_generational_suffix("V Jackson") == "V Jackson"

    def test_does_not_strip_a_bare_i(self):
        # 'I' is not in the suffix set — it would eat a trailing initial.
        assert strip_generational_suffix("Mister I") == "Mister I"


class TestBuildSuffixFallbackIndex:
    def test_indexes_by_stripped_name(self):
        idx = build_suffix_fallback_index({"Patrick Mahomes II": "MahoPa00", "James Cook": "CookJa01"})
        assert idx["Patrick Mahomes"] == "MahoPa00"  # dict has suffix, source may not
        assert idx["James Cook"] == "CookJa01"  # dict has no suffix, source may add one

    def test_refuses_ambiguous_base_names(self):
        # Real homonyms get distinct PFR ids (two Alex Smiths). Guessing between them is how
        # a player inherits another's stats, so the base is dropped from the index entirely.
        idx = build_suffix_fallback_index({"Alex Smith": "SmitAl02", "Alex Smith Jr": "SmitAl03"})
        assert "Alex Smith" not in idx

    def test_keeps_unambiguous_aliases_of_one_player(self):
        # Two spellings of the SAME id are not ambiguous.
        idx = build_suffix_fallback_index({"Odell Beckham": "BeckOd00", "Odell Beckham Jr": "BeckOd00"})
        assert idx["Odell Beckham"] == "BeckOd00"


class TestAddPlayerIdsSuffixFallback:
    """`fp` is the pipeline's only source of POS and the board drops rows without one, so an
    unmatched fp name deletes the player from the board silently."""

    def test_recovers_a_source_that_adds_a_suffix(self):
        # FantasyPros says 'James Cook III'; the key dict (and PFR) say 'James Cook'.
        df = pd.DataFrame({"PLAYER NAME": ["James Cook III"]})
        out = add_player_ids(df, {"James Cook": "CookJa01"}, verbose=False)
        assert out["PLAYER ID"].iloc[0] == "CookJa01"

    def test_recovers_a_source_that_omits_a_suffix(self):
        # The mismatch runs both ways: the dict carries 54 suffixed names.
        df = pd.DataFrame({"PLAYER NAME": ["Patrick Mahomes"]})
        out = add_player_ids(df, {"Patrick Mahomes II": "MahoPa00"}, verbose=False)
        assert out["PLAYER ID"].iloc[0] == "MahoPa00"

    def test_exact_match_wins_over_the_fallback(self):
        # Strictly additive: a name that already matches must never be re-pointed.
        mapping = {"James Cook III": "CookJa99", "James Cook": "CookJa01"}
        df = pd.DataFrame({"PLAYER NAME": ["James Cook III"]})
        out = add_player_ids(df, mapping, verbose=False)
        assert out["PLAYER ID"].iloc[0] == "CookJa99"

    def test_ambiguous_name_stays_unmatched(self):
        df = pd.DataFrame({"PLAYER NAME": ["Alex Smith II"]})
        out = add_player_ids(df, {"Alex Smith": "SmitAl02", "Alex Smith Jr": "SmitAl03"}, verbose=False)
        assert pd.isna(out["PLAYER ID"].iloc[0])

    def test_genuinely_unknown_player_still_unmatched(self):
        df = pd.DataFrame({"PLAYER NAME": ["Nobody At All Jr"]})
        out = add_player_ids(df, {"James Cook": "CookJa01"}, verbose=False)
        assert pd.isna(out["PLAYER ID"].iloc[0])

    def test_both_spellings_in_one_source_resolve_to_the_same_id(self):
        # Documents a real (currently theoretical) edge: if ONE source ever lists a player
        # under both spellings, they now resolve to one id instead of the suffixed row
        # silently going unmatched — and two rows sharing an id duplicates the board row on
        # merge. No source does this today (fp/ds/adp all yield 0 duplicate ids); if one
        # starts, dedupe here rather than reverting the fallback.
        df = pd.DataFrame({"PLAYER NAME": ["James Cook", "James Cook III"]})
        out = add_player_ids(df, {"James Cook": "CookJa01"}, verbose=False)
        assert list(out["PLAYER ID"]) == ["CookJa01", "CookJa01"]
