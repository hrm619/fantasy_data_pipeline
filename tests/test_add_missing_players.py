"""Classification tests for scripts/add_missing_players.py.

A provisional `NEW:` id means "player_key_dict.json doesn't know this name" — which is NOT
the same as "this player is new". Three of the 2026 board's minted players (Jahdae Walker,
Jacob Saylors, Zavier Scott) held real PFR ids the dict had simply never picked up, and a
fourth (Theo Wease Jr) differed from PFR only by a generational suffix. Recording any of
them as a rookie would have stranded them on a `NEW:` id and cost them their HIST_* stats.

So PFR ground truth is consulted BEFORE fuzzy matching, which is only for spellings PFR
itself doesn't carry ("Kenny" vs PFR's "Kenneth Gainwell").
"""

import pandas as pd

from scripts.add_missing_players import classify, find_alias_target, sync_from_pfr


def _board(rows):
    """rows: (player_id, name, pos)"""
    return pd.DataFrame(
        [{"PLAYER ID": pid, "PLAYER NAME": n, "POS": p, "ADP": 100.0} for pid, n, p in rows],
    )


class TestClassify:
    def test_rookie_unknown_to_both_gets_a_new_entry(self):
        board = _board([("NEW:JeremiyahLove", "Jeremiyah Love", "RB")])
        rookies, pfr_known, aliases = classify(board, {}, {}, {}, 0.82)
        assert [r["name"] for r in rookies] == ["Jeremiyah Love"]
        assert not pfr_known and not aliases

    def test_pfr_known_player_is_not_called_a_rookie(self):
        # Played in 2025 and holds a real id; the dict just never picked him up.
        board = _board([("NEW:JahdaeWalker", "Jahdae Walker", "WR")])
        pfr_ids = {"Jahdae Walker": ({"WalkJa03"}, 2025)}
        rookies, pfr_known, aliases = classify(board, {}, {"Jahdae Walker": "WR"}, pfr_ids, 0.82)
        assert not rookies
        assert pfr_known[0]["existing_id"] == "WalkJa03"
        assert pfr_known[0]["new_entry"] is True  # id absent from the dict entirely

    def test_pfr_truth_beats_a_fuzzy_alias(self):
        # A close dict name must not win over PFR's own record for the exact name.
        board = _board([("NEW:ScottyMiller", "Scotty Miller", "WR")])
        pfr_ids = {"Scotty Miller": ({"MillSc01"}, 2025)}
        player_key = {"MillSc01": ["Scott Miller"]}
        rookies, pfr_known, aliases = classify(board, player_key, {"Scotty Miller": "WR"}, pfr_ids, 0.82)
        assert not rookies and not aliases
        assert pfr_known[0]["existing_id"] == "MillSc01"
        assert pfr_known[0]["new_entry"] is False  # id already in the dict

    def test_generational_suffix_still_resolves_to_pfr(self):
        # The board says "Theo Wease Jr"; PFR says "Theo Wease" (WeasTh00).
        board = _board([("NEW:TheoWeaseJr", "Theo Wease Jr", "WR")])
        pfr_ids = {"Theo Wease": ({"WeasTh00"}, 2025)}
        rookies, pfr_known, aliases = classify(board, {}, {"Theo Wease": "WR"}, pfr_ids, 0.82)
        assert not rookies
        assert pfr_known[0]["existing_id"] == "WeasTh00"
        assert pfr_known[0]["pfr_name"] == "Theo Wease"

    def test_suffix_match_requires_the_same_position(self):
        # A bare-surname collision across positions must not resolve to the wrong player.
        board = _board([("NEW:SomeKickerJr", "Some Kicker Jr", "TE")])
        pfr_ids = {"Some Kicker": ({"KickSo00"}, 2025)}
        rookies, pfr_known, _ = classify(board, {}, {"Some Kicker": "QB"}, pfr_ids, 0.82)
        assert not pfr_known
        assert [r["name"] for r in rookies] == ["Some Kicker Jr"]

    def test_homonym_pfr_gives_two_ids_is_never_auto_resolved(self):
        board = _board([("NEW:AlexSmith", "Alex Smith", "QB")])
        pfr_ids = {"Alex Smith": ({"SmitAl02", "SmitAl03"}, 2025)}
        rookies, pfr_known, _ = classify(board, {}, {"Alex Smith": "QB"}, pfr_ids, 0.82)
        assert not pfr_known
        assert "resolve by hand" in rookies[0]["note"]

    def test_alias_catches_a_spelling_pfr_does_not_carry(self):
        # PFR says "Kenneth Gainwell"; every source says "Kenny".
        board = _board([("NEW:KennyGainwell", "Kenny Gainwell", "RB")])
        player_key = {"GainKe00": ["Kenneth Gainwell"]}
        pfr_positions = {"Kenneth Gainwell": "RB"}
        rookies, pfr_known, aliases = classify(board, player_key, pfr_positions, {}, 0.82)
        assert not rookies and not pfr_known
        assert aliases[0]["existing_id"] == "GainKe00"

    def test_players_with_real_ids_are_ignored(self):
        board = _board([("CookJa01", "James Cook", "RB")])
        rookies, pfr_known, aliases = classify(board, {}, {}, {}, 0.82)
        assert not (rookies or pfr_known or aliases)


class TestFindAliasTarget:
    def test_position_mismatch_is_rejected(self):
        # The JaTavion Sanders / Jason Sanders class of collision: a shared surname clears
        # the fuzzy threshold, and PFR's position is what proves they're different people.
        hit = find_alias_target(
            "JaTavion Sanders",
            "TE",
            ["Jason Sanders"],
            {"Jason Sanders": "SandJa01"},
            {"Jason Sanders": "K"},
        )
        assert hit is None

    def test_matching_position_is_accepted(self):
        hit = find_alias_target(
            "Kenny Gainwell",
            "RB",
            ["Kenneth Gainwell"],
            {"Kenneth Gainwell": "GainKe00"},
            {"Kenneth Gainwell": "RB"},
        )
        assert hit is not None and hit[1] == "GainKe00"

    def test_unrelated_name_is_not_matched(self):
        hit = find_alias_target("Jeremiyah Love", "RB", ["James Cook"], {"James Cook": "CookJa01"}, {})
        assert hit is None


class TestSyncFromPfr:
    """Nothing kept player_key_dict.json in step with new combined_data.csv rows, so the dict
    lagged PFR by a season: after the 2025 ingest it was missing 50 ids, ALL last seen in
    2025. Those players then reached the board as unknown names and were minted provisional
    ids, losing the HIST_* PFR was holding under the id the dict never recorded."""

    def test_records_a_player_the_dict_never_picked_up(self):
        additions, ambiguous = sync_from_pfr({}, {"Jahdae Walker": ({"WalkJa03"}, 2025)})
        assert not ambiguous
        assert additions[0]["existing_id"] == "WalkJa03"
        assert additions[0]["new_entry"] is True

    def test_skips_players_already_known(self):
        player_key = {"CookJa01": ["James Cook"]}
        additions, _ = sync_from_pfr(player_key, {"James Cook": ({"CookJa01"}, 2025)})
        assert additions == []

    def test_adds_a_new_name_to_an_id_the_dict_already_has(self):
        # PFR renamed Scott Miller to "Scotty Miller" in 2025 under the same id.
        player_key = {"MillSc01": ["Scott Miller"]}
        additions, _ = sync_from_pfr(player_key, {"Scotty Miller": ({"MillSc01"}, 2025)})
        assert additions[0]["existing_id"] == "MillSc01"
        assert additions[0]["new_entry"] is False  # id present, name is not

    def test_homonyms_are_reported_not_synced(self):
        # Two real Alex Smiths. Adding the name to both ids makes the reverse name->id
        # mapping arbitrary, so it is never done automatically.
        additions, ambiguous = sync_from_pfr({}, {"Alex Smith": ({"SmitAl02", "SmitAl03"}, 2025)})
        assert additions == []
        assert ambiguous[0]["name"] == "Alex Smith"

    def test_does_not_mutate_the_player_key(self):
        player_key = {"CookJa01": ["James Cook"]}
        sync_from_pfr(player_key, {"Jahdae Walker": ({"WalkJa03"}, 2025)})
        assert player_key == {"CookJa01": ["James Cook"]}
