#!/usr/bin/env python3
"""One-off repair for player-key ID collisions, plus a reusable validator.

`player_key_dict.json` maps one ID to a list of NAME VARIATIONS for a single player
("Ja'Marr Chase" / "JaMarr Chase"). Fuzzy name matching (rapidfuzz at 85% in
`add_player_ids`) also attached *different* players who merely share a first name —
"Spencer Rattler" + "Spencer Shrader", "JaTavion Sanders" + "Jason Sanders". Every
collision found had that same signature.

Why it matters: two players under one ID join to each other's stats. JaTavion Sanders
(TE) carried kicker Jason Sanders' weekly trends, and appeared 8x in the board (2
ranking rows x 2 HIST rows) because both sides multiplied on the shared ID.

The fix is validated against ground truth rather than guessed: PFR publishes its own
name -> ID in `combined_data.csv`'s ID column.

  - Name known to PFR      -> reassign to PFR's ID (BondIs00, SandRa00).
  - Name unknown to PFR    -> drop the variation. These are kickers and fringe players;
                              PFR's fantasy table is the only source of HIST_*, so they
                              can never have history, and the board filters to
                              QB/RB/WR/TE. Leaving them attached actively corrupts a
                              real player, which is strictly worse than dropping them.

Run:  uv run python scripts/fix_player_key_collisions.py [--dry-run]
Validate any time:  validate_player_key(...) — also enforced by tests.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

import pandas as pd

PLAYER_KEY_PATH = "player_key_dict.json"
COMBINED_DATA_PATH = "data/fpts historical/combined_data.csv"

# Name variations wrongly attached to another player's ID, with the ID they were taken from.
# Each was confirmed a distinct person (not a spelling variant) against PFR + the 2026 sources.
COLLISIONS_TO_REMOVE: List[Tuple[str, str]] = [
    ("SingDe00", "Devin Leary"),  # != Devin Singletary
    ("ColeBr00", "Brandon McManus"),  # kicker != Brandon Coleman
    ("RattSp00", "Spencer Shrader"),  # kicker != Spencer Rattler
    ("BrayTy00", "Tyler Bass"),  # kicker != Tyler Bray
    ("SimmJo01", "Joshua Simon"),  # != Josh Simmons
    ("HarrMa10", "Marcus Yarns"),  # != Marcus Harris
    ("FitzLa00", "Ryan Fitzgerald"),  # kicker != Larry Fitzgerald
    ("BailSt01", "Emani Bailey"),  # != Stedman Bailey
    ("SandJa01", "Jason Sanders"),  # kicker != JaTavion Sanders (the 8x board duplicate)
    ("JackJh00", "JaQuinden Jackson"),  # != JhaQuan Jackson
]

# Names PFR knows: move them to their real ID instead of dropping them (both are
# draft-relevant in 2026 and would otherwise vanish from the board).
COLLISIONS_TO_REASSIGN: List[Tuple[str, str, str]] = [
    ("FordIs00", "Isaiah Bond", "BondIs00"),  # WR CLE; != Isaiah Ford
    ("SandAc00", "Raheim Sanders", "SandRa00"),  # RB CLE; != Ace Sanders
]

# Duplicate IDs holding the same single name. PFR's ID wins; the other is removed so a
# name maps to exactly one key.
DUPLICATE_IDS_TO_DROP: List[Tuple[str, str]] = [
    ("JohnWi02", "JohnWi00"),  # both ['Will Johnson']; PFR says JohnWi00
]


def load_pfr_truth(combined_data_path: str = COMBINED_DATA_PATH) -> Dict[str, set]:
    """Return {player name: {PFR ids}} from the raw PFR season exports.

    PFR's own ID column is the authority for any player in its fantasy table. Note it
    covers QB/RB/WR/TE only — kickers and non-fantasy players are absent, so a missing
    name means "unverifiable", not "wrong".
    """
    df = pd.read_csv(combined_data_path)
    truth: Dict[str, set] = {}
    for name, pid in zip(df["PLAYER NAME"], df["ID"]):
        if isinstance(name, str) and isinstance(pid, str):
            truth.setdefault(name.strip(), set()).add(pid)
    return truth


def validate_player_key(player_key: Dict[str, List[str]], truth: Dict[str, set]) -> List[str]:
    """Return a list of problems: names PFR assigns to a different ID, or spurious duplicates.

    Only names PFR knows are checked — anything else (kickers, non-fantasy players) is
    unverifiable, not a failure.

    A name under several IDs is NOT automatically wrong: real homonyms exist and PFR gives
    them distinct IDs (two Alex Smiths -> SmitAl02/SmitAl03; nine such names in the data).
    Flag only IDs PFR does not corroborate — otherwise every homonym reads as a bug.
    """
    problems = []

    for pid, names in player_key.items():
        for name in names:
            known = truth.get(name.strip())
            if known and pid not in known:
                problems.append(f"{name!r} is mapped to {pid} but PFR says {sorted(known)}")

    by_name: Dict[str, List[str]] = {}
    for pid, names in player_key.items():
        for name in names:
            by_name.setdefault(name.strip(), []).append(pid)

    for name, pids in by_name.items():
        if len(pids) < 2:
            continue
        known = truth.get(name)
        if not known:
            continue  # unverifiable — can't tell a homonym from a mistake
        extra = sorted(set(pids) - known)
        if extra:
            problems.append(f"{name!r} maps to {sorted(pids)} but PFR only knows {sorted(known)}")

    return problems


def apply_fixes(player_key: Dict[str, List[str]]) -> Tuple[Dict[str, List[str]], List[str]]:
    """Apply the collision repairs; return the new dict and a log of what changed."""
    fixed = {pid: list(names) for pid, names in player_key.items()}
    log = []

    for pid, name in COLLISIONS_TO_REMOVE:
        if pid in fixed and name in fixed[pid]:
            fixed[pid].remove(name)
            log.append(f"removed {name!r} from {pid} (different player)")

    for pid, name, correct_id in COLLISIONS_TO_REASSIGN:
        if pid in fixed and name in fixed[pid]:
            fixed[pid].remove(name)
            fixed.setdefault(correct_id, [])
            if name not in fixed[correct_id]:
                fixed[correct_id].append(name)
            log.append(f"moved {name!r} from {pid} -> {correct_id} (PFR ground truth)")

    for dup_id, keep_id in DUPLICATE_IDS_TO_DROP:
        if dup_id in fixed:
            names = fixed.pop(dup_id)
            log.append(f"dropped duplicate id {dup_id} {names} (kept {keep_id})")

    empty = [pid for pid, names in fixed.items() if not names]
    for pid in empty:
        del fixed[pid]
        log.append(f"dropped {pid} (no names left)")

    return fixed, log


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair player_key_dict.json ID collisions")
    parser.add_argument("--player-key", default=PLAYER_KEY_PATH)
    parser.add_argument("--combined-data", default=COMBINED_DATA_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    ns = parser.parse_args()

    if not os.path.exists(ns.player_key):
        print(f"❌ Player key not found: {ns.player_key}")
        return 1

    with open(ns.player_key) as f:
        player_key = json.load(f)

    truth = load_pfr_truth(ns.combined_data)
    before = validate_player_key(player_key, truth)
    print(f"🔍 Before: {len(player_key)} ids, {sum(len(v) for v in player_key.values())} names")
    print(f"   PFR-contradicted / duplicate names: {len(before)}")
    for p in before:
        print(f"     - {p}")

    fixed, log = apply_fixes(player_key)
    print(f"\n🔧 Applying {len(log)} fix(es):")
    for entry in log:
        print(f"   - {entry}")

    after = validate_player_key(fixed, truth)
    print(f"\n✅ After: {len(fixed)} ids, {sum(len(v) for v in fixed.values())} names")
    print(f"   Remaining problems: {len(after)}")
    for p in after:
        print(f"     - {p}")

    if ns.dry_run:
        print("\n⏭  --dry-run: not writing.")
        return 0

    with open(ns.player_key, "w") as f:
        json.dump(fixed, f, indent=2)
        f.write("\n")
    print(f"\n💾 Wrote {ns.player_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
