"""Integrity checks for player_key_dict.json, validated against PFR ground truth.

The dict maps one id to a player's NAME VARIATIONS ("Ja'Marr Chase" / "JaMarr Chase").
Fuzzy name matching (rapidfuzz at 85% in add_player_ids) also attached *different* players
sharing a first name — "Spencer Rattler" + "Spencer Shrader", "JaTavion Sanders" + "Jason
Sanders" — which joined two players' stats under one key and duplicated board rows.

PFR publishes its own name -> id in combined_data.csv's ID column, so these assert against
data rather than a guessed id scheme.
"""

import json
import os

import pytest

from scripts.fix_player_key_collisions import (
    COMBINED_DATA_PATH,
    PLAYER_KEY_PATH,
    apply_fixes,
    load_pfr_truth,
    validate_player_key,
)


@pytest.fixture(scope="module")
def player_key():
    with open(PLAYER_KEY_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def truth():
    if not os.path.exists(COMBINED_DATA_PATH):
        pytest.skip(f"needs {COMBINED_DATA_PATH} (built by `ff-stats ingest`)")
    return load_pfr_truth(COMBINED_DATA_PATH)


class TestPlayerKeyIntegrity:
    def test_no_names_contradict_pfr(self, player_key, truth):
        # Guards the real defect: a name mapped to another player's id.
        assert validate_player_key(player_key, truth) == []

    def test_known_collisions_stay_fixed(self, player_key):
        # Each of these paired two different people under one id.
        for pid, wrong_name in [
            ("SandJa01", "Jason Sanders"),  # kicker != JaTavion Sanders (TE)
            ("RattSp00", "Spencer Shrader"),  # kicker != Spencer Rattler (QB)
            ("FordIs00", "Isaiah Bond"),  # != Isaiah Ford
            ("SingDe00", "Devin Leary"),  # != Devin Singletary
            ("SandAc00", "Raheim Sanders"),  # != Ace Sanders
            ("BrayTy00", "Tyler Bass"),  # kicker != Tyler Bray
            ("ColeBr00", "Brandon McManus"),  # kicker != Brandon Coleman
        ]:
            assert wrong_name not in player_key.get(pid, []), f"{wrong_name!r} back under {pid}"

    def test_reassigned_names_have_their_pfr_id(self, player_key):
        assert player_key.get("BondIs00") == ["Isaiah Bond"]
        assert player_key.get("SandRa00") == ["Raheim Sanders"]

    def test_canonical_names_retained(self, player_key):
        # Repairing collisions must not evict the legitimate owner of the id.
        assert "JaTavion Sanders" in player_key["SandJa01"]
        assert "Spencer Rattler" in player_key["RattSp00"]
        assert "Isaiah Ford" in player_key["FordIs00"]
        assert "Devin Singletary" in player_key["SingDe00"]

    def test_legitimate_aliases_preserved(self, player_key):
        # Multiple names per id is the POINT of the dict — only collisions are wrong.
        assert "Ja'Marr Chase" in player_key["ChasJa00"]
        assert "JaMarr Chase" in player_key["ChasJa00"]
        assert "Hollywood Brown" in player_key["BrowMa04"]  # Marquise Brown, same player

    def test_real_homonyms_keep_separate_ids(self, player_key, truth):
        # Two different Alex Smiths exist; PFR gives them distinct ids and so must we.
        # A naive "duplicate name" check would flag these as bugs.
        for name in ("Alex Smith", "Mike Williams", "David Johnson"):
            ids = sorted(k for k, v in player_key.items() if name in v)
            assert len(ids) == 2, name
            assert set(ids) == truth[name], name


class TestValidator:
    def test_flags_a_name_mapped_to_another_players_id(self):
        problems = validate_player_key({"FordIs00": ["Isaiah Bond"]}, {"Isaiah Bond": {"BondIs00"}})
        assert len(problems) == 1
        assert "BondIs00" in problems[0]

    def test_accepts_pfr_confirmed_homonyms(self):
        pk = {"SmitAl02": ["Alex Smith"], "SmitAl03": ["Alex Smith"]}
        assert validate_player_key(pk, {"Alex Smith": {"SmitAl02", "SmitAl03"}}) == []

    def test_flags_duplicate_id_pfr_does_not_know(self):
        pk = {"JohnWi00": ["Will Johnson"], "JohnWi02": ["Will Johnson"]}
        problems = validate_player_key(pk, {"Will Johnson": {"JohnWi00"}})
        assert problems  # JohnWi02 is not PFR's

    def test_ignores_names_pfr_cannot_verify(self):
        # Kickers/non-fantasy players are absent from PFR's fantasy table — unverifiable,
        # not wrong.
        assert validate_player_key({"ShraSp00": ["Spencer Shrader"]}, {}) == []


class TestApplyFixes:
    def test_is_idempotent(self, player_key):
        # The repairs are already applied; re-running must be a no-op.
        fixed, log = apply_fixes(player_key)
        assert log == []
        assert fixed == player_key

    def test_removes_collision_and_keeps_owner(self):
        pk = {"RattSp00": ["Spencer Rattler", "Spencer Shrader"]}
        fixed, log = apply_fixes(pk)
        assert fixed["RattSp00"] == ["Spencer Rattler"]
        assert len(log) == 1

    def test_reassigns_to_pfr_id(self):
        pk = {"FordIs00": ["Isaiah Ford", "Isaiah Bond"]}
        fixed, _ = apply_fixes(pk)
        assert fixed["FordIs00"] == ["Isaiah Ford"]
        assert fixed["BondIs00"] == ["Isaiah Bond"]

    def test_drops_id_left_with_no_names(self):
        pk = {"SimmJo01": ["Joshua Simon"]}
        fixed, _ = apply_fixes(pk)
        assert "SimmJo01" not in fixed
