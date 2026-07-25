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

from scripts.add_missing_players import classify, find_alias_target


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
