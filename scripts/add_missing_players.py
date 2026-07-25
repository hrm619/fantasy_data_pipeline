#!/usr/bin/env python3
"""Record players the board had to mint a provisional `NEW:` id for.

`player_key_dict.json` is keyed by Pro-Football-Reference ids, which a player only has once
he has NFL history. Every incoming rookie is therefore absent from it, and since the board
joins its sources on PLAYER ID, an id-less player used to vanish from the board entirely —
75 skill players in 2026, 7 of them inside the top 150 (Jeremiyah Love at ECR 35).

The pipeline now mints a name-derived `NEW:` id for those players so they reach the board.
This script turns those provisional ids into recorded entries, and splits them into the two
cases that need opposite treatment:

  ROOKIE  — genuinely new. Gets its own `NEW:` entry in the dict. Nothing else to do; when
            PFR assigns a real id after his debut, re-run and it will surface as an ALIAS.
  ALIAS   — NOT new: a player the dict already knows under a different spelling. PFR calls
            him "Kenneth Gainwell" while all six sources write "Kenny Gainwell", so he minted
            a provisional id and silently lost his HIST_* stats (they live under GainKe00).
            The fix is to attach the spelling to the EXISTING id, not to keep a second one.

Aliases are suggested by fuzzy name match, which is exactly how the JaTavion Sanders /
Spencer Rattler collisions were created — a shared surname clears the threshold and one
player inherits another's stats. So every suggestion is checked against PFR ground truth and
a position mismatch is rejected outright (that alone would have caught Rattler-the-QB being
merged with Shrader-the-kicker), and aliases still require their own explicit flag to apply.

Run:
  uv run python scripts/add_missing_players.py                  # dry run, shows both lists
  uv run python scripts/add_missing_players.py --apply          # write ROOKIE entries only
  uv run python scripts/add_missing_players.py --apply-aliases  # also attach ALIAS spellings
"""

import argparse
import glob
import json
import os
import sys
from difflib import SequenceMatcher, get_close_matches
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from fantasy_pipeline.data.player_utils import is_provisional_id, strip_generational_suffix  # noqa: E402

PLAYER_KEY_PATH = "player_key_dict.json"
COMBINED_DATA_PATH = "data/fpts historical/combined_data.csv"
BOARD_GLOB = "data/rankings current/latest/df_rank_clean_*.csv"

# difflib ratio above which a minted name is treated as a possible respelling of a known
# player. Deliberately below add_player_ids' exactness: "Kenny Gainwell" vs "Kenneth
# Gainwell" is only ~0.85, and that is the case this exists to catch.
ALIAS_SIMILARITY_CUTOFF = 0.82


def latest_board(board_glob: str = BOARD_GLOB) -> str:
    """Path of the most recent consolidated board (timestamps sort chronologically)."""
    boards = sorted(glob.glob(board_glob))
    if not boards:
        raise FileNotFoundError(f"No consolidated board found matching {board_glob!r} — run ff-rankings first")
    return boards[-1]


def load_pfr_positions(combined_data_path: str = COMBINED_DATA_PATH) -> Dict[str, str]:
    """Return {player name: POS} from the raw PFR season exports (most recent season wins).

    Covers QB/RB/WR/TE only — a name PFR doesn't know is unverifiable, not wrong.
    """
    df = pd.read_csv(combined_data_path).sort_values("SEASON")
    return {
        str(name).strip(): str(pos).strip().upper()
        for name, pos in zip(df["PLAYER NAME"], df["POS"])
        if isinstance(name, str) and isinstance(pos, str)
    }


def load_pfr_ids(combined_data_path: str = COMBINED_DATA_PATH) -> Dict[str, Tuple[set, int]]:
    """Return {player name: ({PFR ids}, last season)} from the raw PFR season exports.

    PFR's own ID column is the authority — checked BEFORE any fuzzy matching, because a
    provisional id only means "the dict doesn't know this name", which is not the same as
    "this player is new". The 2026 board minted ids for Jahdae Walker, Jacob Saylors and
    Zavier Scott, all of whom played in 2025 and hold real PFR ids the dict simply never
    picked up; minting would have cost them their HIST_* stats.
    """
    df = pd.read_csv(combined_data_path)
    out: Dict[str, Tuple[set, int]] = {}
    for name, pid, season in zip(df["PLAYER NAME"], df["ID"], df["SEASON"]):
        if not (isinstance(name, str) and isinstance(pid, str)):
            continue
        ids, last = out.setdefault(name.strip(), (set(), 0))
        ids.add(pid)
        out[name.strip()] = (ids, max(last, int(season)))
    return out


def find_alias_target(
    name: str,
    pos: str,
    known_names: List[str],
    name_to_key: Dict[str, str],
    pfr_positions: Dict[str, str],
    cutoff: float = ALIAS_SIMILARITY_CUTOFF,
) -> Optional[Tuple[str, str, float]]:
    """Return (matched_name, existing_id, score) if `name` looks like a known player respelt.

    Returns None when nothing is close enough, or when PFR gives the candidate a different
    position — a shared surname across positions is a collision, not a spelling variant.
    """
    matches = get_close_matches(name, known_names, n=1, cutoff=cutoff)
    if not matches:
        return None
    matched = matches[0]

    matched_pos = pfr_positions.get(matched)
    if matched_pos and pos and matched_pos != pos.strip().upper():
        return None

    return matched, name_to_key[matched], SequenceMatcher(None, name, matched).ratio()


def classify(
    board: pd.DataFrame,
    player_key: Dict[str, List[str]],
    pfr_positions: Dict[str, str],
    pfr_ids: Dict[str, Tuple[set, int]],
    cutoff: float,
) -> Tuple[List[dict], List[dict], List[dict]]:
    """Split the board's provisional players into (rookies, pfr_known, alias_candidates).

    Order matters: PFR truth is consulted first, fuzzy matching only for what's left. A
    provisional id means the DICT doesn't know the name — PFR often does.
    """
    name_to_key: Dict[str, str] = {}
    for key, names in player_key.items():
        for n in names if isinstance(names, list) else [names]:
            name_to_key[n] = key
    known_names = list(name_to_key)

    rookies: List[dict] = []
    pfr_known: List[dict] = []
    aliases: List[dict] = []

    provisional = board[board["PLAYER ID"].map(is_provisional_id)]
    for _, row in provisional.iterrows():
        name, pos, pid = str(row["PLAYER NAME"]), str(row.get("POS", "")), str(row["PLAYER ID"])
        record = {"name": name, "pos": pos, "provisional_id": pid, "adp": row.get("ADP")}

        # 1. PFR knows this exact name -> use its real id, whatever the dict says.
        truth = pfr_ids.get(name)
        matched_name = name
        # Sources disagree about generational suffixes, and PFR is no exception: the board
        # says "Theo Wease Jr" where PFR says "Theo Wease" (WeasTh00, 3 games in 2025). Mirror
        # the suffix retry add_player_ids already does against the dict, but only across a
        # matching position — a bare surname collision must not resolve to the wrong player.
        if not truth:
            base = strip_generational_suffix(name)
            if base != name:
                candidate = pfr_ids.get(base)
                candidate_pos = pfr_positions.get(base)
                if candidate and (not candidate_pos or not pos or candidate_pos == pos.strip().upper()):
                    truth, matched_name = candidate, base

        if truth and len(truth[0]) == 1:
            real_id = next(iter(truth[0]))
            pfr_known.append(
                {
                    **record,
                    "existing_id": real_id,
                    "pfr_name": matched_name,
                    "last_season": truth[1],
                    "new_entry": real_id not in player_key,
                }
            )
            continue
        # A name PFR gives several ids is a real homonym — never auto-resolve it.
        if truth and len(truth[0]) > 1:
            record["note"] = f"PFR gives {len(truth[0])} ids — resolve by hand"

        # 2. Otherwise look for a respelling of someone the dict already knows.
        hit = find_alias_target(name, pos, known_names, name_to_key, pfr_positions, cutoff)
        if hit:
            matched, existing_id, score = hit
            aliases.append({**record, "matched": matched, "existing_id": existing_id, "score": score})
        else:
            rookies.append(record)

    return rookies, pfr_known, aliases


def _print_table(title: str, rows: List[dict], columns: List[Tuple[str, str]]) -> None:
    print(f"\n{title} ({len(rows)})")
    if not rows:
        print("  (none)")
        return

    def cell(row: dict, key: str) -> str:
        value = row.get(key)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return f"{value:.2f}" if isinstance(value, float) else str(value)

    widths = [max(len(label), max(len(cell(r, key)) for r in rows)) for label, key in columns]
    print("  " + "  ".join(f"{label:<{w}}" for (label, _), w in zip(columns, widths)))
    for r in rows:
        print("  " + "  ".join(f"{cell(r, key):<{w}}" for (_, key), w in zip(columns, widths)).rstrip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--board", default=None, help="Consolidated board CSV (default: newest in latest/)")
    parser.add_argument("--player-key", default=PLAYER_KEY_PATH)
    parser.add_argument("--combined-data", default=COMBINED_DATA_PATH)
    parser.add_argument("--cutoff", type=float, default=ALIAS_SIMILARITY_CUTOFF, help="Alias similarity threshold")
    parser.add_argument("--apply", action="store_true", help="Write ROOKIE entries into the player key")
    parser.add_argument(
        "--apply-aliases",
        action="store_true",
        help="Also attach ALIAS spellings to their existing id (review the list first)",
    )
    ns = parser.parse_args()

    board_path = ns.board or latest_board()
    board = pd.read_csv(board_path)
    with open(ns.player_key) as f:
        player_key: Dict[str, List[str]] = json.load(f)
    pfr_positions = load_pfr_positions(ns.combined_data)
    pfr_ids = load_pfr_ids(ns.combined_data)

    print(f"Board:      {board_path}  ({len(board)} players)")
    print(f"Player key: {ns.player_key}  ({len(player_key)} ids)")

    rookies, pfr_known, aliases = classify(board, player_key, pfr_positions, pfr_ids, ns.cutoff)

    if not (rookies or pfr_known or aliases):
        print("\n✅ No provisional ids on the board — nothing to record.")
        return 0

    _print_table(
        "PFR-KNOWN — NOT new: PFR has history under this exact name; use its real id",
        pfr_known,
        [
            ("PLAYER NAME", "name"),
            ("POS", "pos"),
            ("PFR NAME", "pfr_name"),
            ("REAL ID", "existing_id"),
            ("LAST SEASON", "last_season"),
            ("NEW DICT ENTRY", "new_entry"),
        ],
    )
    _print_table(
        "ROOKIE — unknown to both the key dict and PFR; will get its own NEW: entry",
        rookies,
        [("PROVISIONAL ID", "provisional_id"), ("PLAYER NAME", "name"), ("POS", "pos"), ("ADP", "adp"), ("", "note")],
    )
    _print_table(
        "ALIAS — looks like a known player respelt; attaching restores their HIST_* stats",
        aliases,
        [
            ("PLAYER NAME", "name"),
            ("POS", "pos"),
            ("MATCHES", "matched"),
            ("EXISTING ID", "existing_id"),
            ("SCORE", "score"),
        ],
    )

    if not (ns.apply or ns.apply_aliases):
        print("\nDry run — nothing written. Re-run with --apply (PFR-known + rookies) and/or --apply-aliases.")
        return 0

    written = 0
    if ns.apply:
        # PFR-known first: ground truth, and it restores HIST_* the provisional id was losing.
        recorded = 0
        for p in pfr_known:
            names = player_key.setdefault(p["existing_id"], [])
            if p["name"] not in names:
                names.append(p["name"])
                recorded += 1
        written += recorded
        print(f"\n✓ Recorded {recorded} players under their real PFR id")

        rookie_count = 0
        for r in rookies:
            player_key.setdefault(r["provisional_id"], [])
            if r["name"] not in player_key[r["provisional_id"]]:
                player_key[r["provisional_id"]].append(r["name"])
                rookie_count += 1
        written += rookie_count
        print(f"✓ Recorded {rookie_count} rookie entries")

    if ns.apply_aliases:
        attached = 0
        for a in aliases:
            names = player_key.setdefault(a["existing_id"], [])
            if a["name"] not in names:
                names.append(a["name"])
                attached += 1
        written += attached
        print(f"✓ Attached {attached} alias spellings to existing ids")

    if written:
        with open(ns.player_key, "w") as f:
            json.dump(player_key, f, indent=4, sort_keys=True)
        print(f"✓ Wrote {ns.player_key}")
        print("\nRe-run ff-rankings to pick these up. Then validate:")
        print("  uv run python scripts/fix_player_key_collisions.py --dry-run")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
