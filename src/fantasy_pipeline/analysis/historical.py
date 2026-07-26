"""Adapters that turn the historical ranking snapshot into tidy facts.

The two snapshot files share no schema — the 2024 board is a hand-built spreadsheet, the
2025 board is this pipeline's own output — so each gets its own adapter, and both emit the
same long/tidy shape: one row per (season, expert, player).

A third input sits alongside them: SUPPLEMENTAL_BOARDS, single-expert files that carry a
board more completely than the snapshot did. They OVERRIDE the snapshot for their
(season, expert) rather than adding a second copy of the same opinion.

Outcomes come from PFR (`combined_data.csv`), scored in half-PPR to match the board.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from pandas.api.types import is_numeric_dtype

from ..config import DEFAULT_PATHS, HISTORICAL_DATA_DIR, project_root
from ..core.stats_aggregator import _dedupe_season_rows
from ..data.loader import load_data
from ..data.player_utils import add_player_ids, clean_player_names, load_player_key_mapping

HISTORICAL_DIR = os.path.join(str(project_root()), "data", "rankings_historical")
COMBINED_DATA_PATH = os.path.join(HISTORICAL_DATA_DIR, "combined_data.csv")
HOME_DB_PATH = Path.home() / ".fantasy-data" / "fantasy_data.db"

# Positions the board carries. FB and anything else is dropped from the analysis universe.
ANALYSIS_POSITIONS = ("QB", "RB", "WR", "TE")

# Replacement level per position, as ranked by realized points — the pipeline's documented
# VBD baselines (1QB, 2RB+1FLEX, 2WR+1FLEX, 1TE over 12 teams). Used to put positions on a
# common scale, since 18 PPG is replaceable for a QB and elite for an RB.
REPLACEMENT_BASELINES = {"QB": 6, "RB": 24, "WR": 30, "TE": 12}

# `expert` = an individual's board. `consensus` = an aggregate of experts (FantasyPros ECR).
# `market` = where the field actually drafted. The three must not be averaged together —
# same reasoning as _NON_CONSENSUS_PREFIXES on the live board.
EXPERT_KINDS: Dict[str, str] = {
    "fp": "consensus",
    "adp": "market",
    "adp_underdog": "market",
    "pff": "expert",
    "ds": "expert",
    "hw": "expert",
    "fpts": "expert",
    "jj": "expert",
    "4for4": "expert",
    "ringer": "expert",
}

# Two markets, deliberately kept apart. `adp` is redraft consensus ADP; `adp_underdog` is
# Underdog BEST-BALL ADP, which is a different game — best-ball pays for weekly spikes and
# never starts anyone, so it systematically bids up high-variance pass-catchers. They
# correlate 0.965 where both exist, which is close enough to be tempting and not close
# enough to be the same thing. Anything that compares an expert to "the market" must say
# WHICH market; 2024 carries both precisely so the gap can be measured rather than assumed.
MARKET_EXPERTS = ("adp", "adp_underdog")

SNAPSHOTS = {
    2024: ("2024 Pre-Season Rankings (August 20 2024).csv", "2024-08-20"),
    2025: ("2025 Pre-Season Rankings (August 22 2025).csv", "2025-08-22"),
}

# Seasons the analysis covers. 2023 has no snapshot — it exists only as a supplemental HW
# board — but PFR carries its outcomes, so it is a real season for accuracy work.
ANALYSIS_SEASONS: Tuple[int, ...] = (2023, 2024, 2025)


@dataclass(frozen=True)
class SupplementalBoard:
    """One expert's board, read from its own file, overriding the snapshot's version.

    These exist because the snapshot lost information the original export had:

    * `pff-2025` — the snapshot's `pff_RK` starts at 2. That is the documented `read_csv`
      header-detection bug (a blank line before the header meant the first data row was
      eaten as column names), and it cost PFF its single highest-conviction call. The
      original export was still in `raw archive/` from the same day, so it IS recoverable —
      the design doc's "unrecoverable" note predates anyone looking there.
    * `hw-2024` — the snapshot carried Winks positionally only ("RB1"), which made him
      incomparable to his own 2025 overall ranks. The Underdog export has overall ranks;
      derived-vs-published positional ranks correlate 0.994, confirming it is the same
      board and not a different vintage.
    * `hw-2023` — no snapshot exists for 2023 at all.
    * `fp-2023` / `pff-2023` — likewise. Together with `hw-2023` they make 2023 the third
      head-to-head season rather than a solo record. (`ds` has no 2023 board and could not be
      obtained, so 2023 compares three experts where 2024-25 compare four.)

    `market_col`, where present, is a market series riding along in the same file. It loads
    as its own market expert and is never merged into another one.

    `pos_from` says where the position comes from:

    * `"column"` — `pos_col` names a plain position column ("RB").
    * `"posrank_prefix"` — `pos_col` names a POSITIONAL RANK column ("WR1") and the position
      is its letter prefix. Only the prefix is used: the positional *number* is still derived
      from overall rank by `_derive_pos_ranks`, because published positional columns are not
      dependable (§7 — the 2025 snapshot's `POS ECR` is all 1s). Do not "simplify" this into
      reading the number that is sitting right there.

    `market_from_delta_col`, where present, reconstructs a market from a DELTA against this
    board's own rank: `market = rank_col + delta`. FantasyPros' 2023 export carries
    `ECR VS. ADP`, which is the only route to a 2023 redraft ADP. Verified against known 2023
    ADPs before use — Kelce 5, Bijan 9, Pollard 17, Henry 16, A.J. Brown 13.
    """

    season: int
    expert: str
    filename: str
    as_of_date: str
    name_col: str
    pos_col: str
    rank_col: str
    market_col: Optional[str] = None
    market_expert: str = "adp_underdog"
    pos_from: str = "column"
    market_from_delta_col: Optional[str] = None


SUPPLEMENTAL_BOARDS: Tuple[SupplementalBoard, ...] = (
    SupplementalBoard(
        season=2023,
        expert="hw",
        filename="hw-2023.csv",
        as_of_date="2023-08-01",
        name_col="Player",
        pos_col="Pos",
        rank_col="Rank",
        market_col="ADP",
    ),
    SupplementalBoard(
        season=2024,
        expert="hw",
        filename="hw-2024.csv",
        as_of_date="2024-08-20",
        name_col="Player",
        pos_col="Pos",
        rank_col="Rank",
        market_col="ADP",
    ),
    SupplementalBoard(
        season=2025,
        expert="pff",
        filename="pff-2025.csv",
        as_of_date="2025-08-22",
        name_col="Full Name",
        pos_col="Position",
        rank_col="Overall Rank",
    ),
    SupplementalBoard(
        season=2023,
        expert="pff",
        filename="pff-2023.csv",
        as_of_date="2023-08-01",
        name_col="Name",
        pos_col="Position",
        rank_col="Rank",
    ),
    SupplementalBoard(
        season=2023,
        expert="fp",
        filename="fp-2023.csv",
        as_of_date="2023-08-01",
        name_col="PLAYER NAME",
        # No plain position column — the position is the prefix of "WR1"/"RB12".
        pos_col="POSITION RANK",
        pos_from="posrank_prefix",
        rank_col="EXPERT RANKING",
        market_col="ADP",
        market_expert="adp",
        market_from_delta_col="ECR VS. ADP",
    ),
)

# 2024 hand-built sheet: source column -> (expert, scope). `Underdog` is best-ball ADP, not
# an expert board, and is deliberately absent; so are the personal columns (HankRank, My
# Rank) and `Underdog ADP Pos Rank`, which exported as 217 #REF!.
_2024_OVERALL = {
    "ECR": "fp",
    "PFF": "pff",
    "Draft Sharks": "ds",
    "4 FOR 4": "4for4",
    "Ringer": "ringer",
    "ADP": "adp",
}
# Positional ranks are only read where the expert published NO overall rank — everywhere else
# they are derived from the overall rank (see `_derive_pos_ranks`). Deriving is both more
# comparable across experts and more reliable: the 2025 snapshot's `POS ECR` column is all 1s.
_2024_POSITIONAL = {
    # Winks published positional ranks only this year ("RB1"), so hw is not comparable to
    # its 2025 overall ranks except at positional granularity. rank_scope records that.
    "Hayden Winks Pos Rank": "hw",
}

# 2025 pipeline output: expert -> overall rank column.
_2025_OVERALL = {
    "ECR": "fp",
    "pff_RK": "pff",
    "ds_RK": "ds",
    "hw_RK": "hw",
    "fpts_RK": "fpts",
    "jj_RK": "jj",
    "ADP": "adp",
}

_POS_RANK_RE = re.compile(r"^([A-Z]{2,3})\s*(\d+)$")


def _parse_positional(value) -> Optional[int]:
    """'RB1' -> 1. Returns None for blanks and spreadsheet errors (#REF!, #NAME?)."""
    if not isinstance(value, str):
        return None
    m = _POS_RANK_RE.match(value.strip())
    return int(m.group(2)) if m else None


def _numeric(series: pd.Series) -> pd.Series:
    """Coerce to numeric, turning spreadsheet error strings into NaN."""
    return pd.to_numeric(series, errors="coerce")


def _resolve_player_ids(df: pd.DataFrame, player_key_path: str, name_col: str) -> pd.DataFrame:
    """Attach PFR ids by name. All 217 names in the 2024 sheet resolve to real ids."""
    _, name_to_key = load_player_key_mapping(player_key_path, save_reverse_mapping=False)
    renamed = df.rename(columns={name_col: "PLAYER NAME"})
    # mint_missing=False on purpose: an unresolvable name here means we cannot join the
    # player to an outcome, so a provisional id would only manufacture a row that can never
    # be scored. Better to surface it as unmatched.
    return add_player_ids(clean_player_names(renamed), name_to_key, verbose=False)


def _collapse_duplicate_players(df: pd.DataFrame, rank_cols: List[str], season: int, verbose: bool) -> pd.DataFrame:
    """Collapse repeated rows for one player; drop the player if they disagree.

    The 2025 snapshot predates the player-key collision fix, so it carries JaTavion Sanders
    16 times — `SandJa01` mapped to both the TE and kicker Jason Sanders, and the board's
    left-merge multiplied him out. The copies disagree (ECR 234 on some rows, 254 on others)
    because they are literally two different players' rankings under one id.

    Identical copies collapse to one row. Disagreeing copies are DROPPED, not resolved: there
    is no way to tell which rank belongs to the TE, and picking one risks scoring a kicker's
    ranking as a tight end's.
    """
    dupes = df["PLAYER ID"].notna() & df["PLAYER ID"].duplicated(keep=False)
    if not dupes.any():
        return df

    keep_idx, dropped = [], []
    for pid, group in df[dupes].groupby("PLAYER ID"):
        present = [c for c in rank_cols if c in group.columns]
        if group[present].drop_duplicates().shape[0] == 1:
            keep_idx.append(group.index[0])
        else:
            dropped.append((pid, str(group["PLAYER NAME"].iloc[0]), len(group)))

    if verbose and dropped:
        for pid, name, n in dropped:
            print(f"   ⚠️  {season}: dropped {name} ({pid}) — {n} conflicting rows (player-key collision in snapshot)")

    return df[~dupes | df.index.isin(keep_idx)]


def _melt(
    df: pd.DataFrame,
    season: int,
    as_of: str,
    source_file: str,
    overall: Dict[str, str],
    positional: Dict[str, str],
) -> pd.DataFrame:
    """Melt wide expert columns into one row per (season, expert, player)."""
    ranks: Dict[Tuple[str, str], pd.Series] = {}
    for col, expert in overall.items():
        if col in df.columns:
            ranks[(expert, "overall_rank")] = _numeric(df[col])
    for col, expert in positional.items():
        if col in df.columns:
            # Ask whether the column is NUMERIC, not whether it is `object`. Positional ranks
            # arrive either as published strings ("RB1") or as bare numbers, and the old test
            # was `dtype == object` — true for strings under pandas 2, but **false under pandas
            # 3**, whose default inference gives a text column the `str` dtype instead. Every
            # "RB1" would then take the numeric branch, and `to_numeric(errors="coerce")` turns
            # it into NaN: not a crash, just a silently empty `pos_rank` for every expert whose
            # sheet publishes positional ranks that way. `is_numeric_dtype` is the same answer
            # under both majors, and non-numeric extension dtypes still reach `_parse_positional`
            # (which returns None for anything that isn't a str, so a mixed column degrades
            # exactly as it did before).
            series = df[col]
            parsed = _numeric(series) if is_numeric_dtype(series) else series.map(_parse_positional)
            ranks[(expert, "pos_rank")] = pd.Series(parsed, index=df.index)

    experts = sorted({e for e, _ in ranks})
    frames: List[pd.DataFrame] = []
    for expert in experts:
        overall_rank = ranks.get((expert, "overall_rank"))
        pos_rank = ranks.get((expert, "pos_rank"))
        block = pd.DataFrame(
            {
                "season": season,
                "as_of_date": as_of,
                "expert": expert,
                "expert_kind": EXPERT_KINDS.get(expert, "expert"),
                "player_id": df["PLAYER ID"],
                "name_as_published": df["PLAYER NAME"],
                "pos": df["_pos"],
                "overall_rank": overall_rank if overall_rank is not None else pd.NA,
                "pos_rank": pos_rank if pos_rank is not None else pd.NA,
                "source_file": source_file,
            }
        )
        # Coerce before concat: an expert with no positional column leaves an all-NA object
        # column, which makes the concatenated dtypes depend on expert order.
        block["overall_rank"] = pd.to_numeric(block["overall_rank"], errors="coerce")
        block["pos_rank"] = pd.to_numeric(block["pos_rank"], errors="coerce")
        # An expert who didn't rank a player contributes no row at all — absence is not a
        # rank of NaN, and counting it as one would silently punish deep boards.
        block = block[block["overall_rank"].notna() | block["pos_rank"].notna()]
        frames.append(block)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if out.empty:
        return out
    # An expert with no overall rank is a positional-only board (2024 Hayden Winks). Recorded
    # explicitly so nothing later compares it against overall ranks by accident.
    out["rank_scope"] = out["overall_rank"].notna().map({True: "overall", False: "positional"})
    return _derive_pos_ranks(out)


def _derive_pos_ranks(out: pd.DataFrame) -> pd.DataFrame:
    """Fill `pos_rank` from `overall_rank` by ranking within (season, expert, position).

    Most experts publish an overall board only, and an overall ranking already *implies* a
    positional one. Scoring needs positional rank because the realized value curve is
    positional (18 PPG is replaceable for a QB and elite for an RB).

    Derived ranks are preferred over published ones wherever an overall rank exists — they are
    computed identically for every expert, and the published columns are not dependable (the
    2025 snapshot's `POS ECR` is all 1s). A published positional rank survives only where the
    expert gave no overall rank at all.
    """
    out = out.copy()
    out["pos_rank_derived"] = False
    has_overall = out["overall_rank"].notna() & out["pos"].notna()
    if has_overall.any():
        derived = out[has_overall].groupby(["season", "expert", "pos"])["overall_rank"].rank(method="min").astype(int)
        out.loc[has_overall, "pos_rank"] = derived
        out.loc[has_overall, "pos_rank_derived"] = True
    return out


def _load_supplemental_board(
    spec: SupplementalBoard,
    historical_dir: str,
    player_key_path: str,
    verbose: bool,
) -> pd.DataFrame:
    """Read one single-expert board file into the same tidy shape as the snapshots.

    Uses the pipeline's `load_data` rather than a bare `read_csv` because the PFF export
    carries a title row and a blank line above its header — auto-detecting that header is
    precisely the fix that makes rank 1 recoverable in the first place.
    """
    path = os.path.join(historical_dir, spec.filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Supplemental board not found: {path}")

    raw = load_data(path)
    df = raw.rename(columns={spec.name_col: "PLAYER NAME"})
    df["PLAYER NAME"] = df["PLAYER NAME"].astype(str).str.strip()

    if spec.pos_from == "posrank_prefix":
        # "WR1" -> "WR". Only the prefix; the number is derived from overall rank later.
        df["_pos"] = df[spec.pos_col].astype(str).str.extract(r"^\s*([A-Za-z]+)", expand=False).str.upper()
    elif spec.pos_from == "column":
        df["_pos"] = df[spec.pos_col].astype(str).str.upper().str.strip()
    else:
        raise ValueError(f"Unknown pos_from {spec.pos_from!r} for {spec.filename}")
    df = df[df["_pos"].isin(ANALYSIS_POSITIONS)].copy()

    df = _resolve_player_ids(df, player_key_path, name_col="PLAYER NAME")
    unmatched = df["PLAYER ID"].isna().sum()
    if unmatched and verbose:
        names = ", ".join(df.loc[df["PLAYER ID"].isna(), "PLAYER NAME"].head(5))
        print(f"   ⚠️  {spec.season} {spec.expert}: {unmatched} name(s) unmatched — excluded ({names})")
    df = df[df["PLAYER ID"].notna()].copy()

    def _block(expert: str, ranks: pd.Series) -> pd.DataFrame:
        block = pd.DataFrame(
            {
                "season": spec.season,
                "as_of_date": spec.as_of_date,
                "expert": expert,
                "expert_kind": EXPERT_KINDS.get(expert, "expert"),
                "player_id": df["PLAYER ID"],
                "name_as_published": df["PLAYER NAME"],
                "pos": df["_pos"],
                "overall_rank": pd.to_numeric(ranks, errors="coerce"),
                "pos_rank": pd.NA,
                "source_file": spec.filename,
            }
        )
        block["pos_rank"] = pd.to_numeric(block["pos_rank"], errors="coerce")
        return block[block["overall_rank"].notna()]

    frames = [_block(spec.expert, df[spec.rank_col])]

    market: Optional[pd.Series] = None
    if spec.market_from_delta_col and spec.market_from_delta_col in df.columns:
        # Reconstruct the market from its delta against this board's own rank. FantasyPros'
        # 2023 export publishes `ECR VS. ADP` and no ADP column, and this is the only route
        # to a 2023 redraft ADP. Verified against known 2023 ADPs before being trusted:
        # Kelce 5, Bijan 9, Pollard 17, Henry 16, A.J. Brown 13.
        base = pd.to_numeric(df[spec.rank_col], errors="coerce")
        delta = pd.to_numeric(df[spec.market_from_delta_col], errors="coerce")
        market = base + delta
    elif spec.market_col and spec.market_col in df.columns:
        market = pd.to_numeric(df[spec.market_col], errors="coerce")

    if market is not None:
        # RANK the market values rather than passing them through as the rank. Underdog
        # publishes best-ball ADP as a decimal average (1.2, 2.3, 6.4) and `overall_rank`
        # is stored as Int64 — passing the raw value through truncates 1.2 and 1.9 to the
        # same 1, manufacturing ties and quietly scrambling the top of the board. A derived
        # market has the mirror-image problem: it is integral but NOT dense (the 2023 ADP
        # spans 1..193 over 150 players), so the raw value is not a rank either. Ranking is
        # correct for both and is the invariant that keeps a new market file safe.
        frames.append(_block(spec.market_expert, market.rank(method="min")))

    out = pd.concat(frames, ignore_index=True)
    out["rank_scope"] = "overall"
    return _derive_pos_ranks(out)


def build_expert_rankings(
    historical_dir: str = HISTORICAL_DIR,
    player_key_path: str = DEFAULT_PATHS["player_key_file"],
    verbose: bool = True,
) -> pd.DataFrame:
    """Read the snapshots plus the supplemental boards, and return the tidy fact table."""
    frames = []

    for season, (filename, as_of) in SNAPSHOTS.items():
        path = os.path.join(historical_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Snapshot not found: {path}")
        raw = pd.read_csv(path)

        if season == 2024:
            df = _resolve_player_ids(raw, player_key_path, name_col="Player")
            unmatched = df["PLAYER ID"].isna().sum()
            if unmatched and verbose:
                print(f"   ⚠️  {season}: {unmatched} name(s) unmatched — excluded (cannot join an outcome)")
            df = df[df["PLAYER ID"].notna()].copy()
            df["_pos"] = df["Position"].astype(str).str.upper().str.strip()
            df = _collapse_duplicate_players(df, list(_2024_OVERALL) + list(_2024_POSITIONAL), season, verbose)
            block = _melt(df, season, as_of, filename, _2024_OVERALL, _2024_POSITIONAL)
        else:
            df = raw.copy()
            df["_pos"] = df["POS"].astype(str).str.upper().str.strip()
            df = _collapse_duplicate_players(df, list(_2025_OVERALL), season, verbose)
            block = _melt(df, season, as_of, filename, _2025_OVERALL, {})

        if verbose:
            per_expert = block.groupby("expert").size().to_dict()
            print(f"   ✓ {season}: {len(block)} rows — {per_expert}")
        frames.append(block)

    out = pd.concat(frames, ignore_index=True)

    for spec in SUPPLEMENTAL_BOARDS:
        supp = _load_supplemental_board(spec, historical_dir, player_key_path, verbose)
        # Override, don't append. These files carry a board the snapshot already has a worse
        # copy of, so keeping both would double-count one expert's opinion and — because the
        # two copies disagree — make the duplicate check below fail for the right reason at
        # the wrong place.
        replaced = out[(out["season"] == spec.season) & (out["expert"].isin(supp["expert"].unique()))]
        out = out.drop(index=replaced.index)
        out = pd.concat([out, supp], ignore_index=True)
        if verbose:
            per_expert = supp.groupby("expert").size().to_dict()
            was = f"replacing {len(replaced)} snapshot row(s)" if len(replaced) else "new to the analysis"
            print(f"   ✓ {spec.season} supplemental {spec.filename}: {per_expert} — {was}")

    out["overall_rank"] = pd.to_numeric(out["overall_rank"], errors="coerce").astype("Int64")
    out["pos_rank"] = pd.to_numeric(out["pos_rank"], errors="coerce").astype("Int64")

    dupes = out.duplicated(["season", "expert", "player_id"]).sum()
    if dupes:
        raise ValueError(f"{dupes} duplicate (season, expert, player_id) rows — a source lists a player twice")
    return out.sort_values(["season", "expert", "overall_rank"]).reset_index(drop=True)


def build_player_outcomes(
    combined_data_path: str = COMBINED_DATA_PATH,
    seasons: Tuple[int, ...] = ANALYSIS_SEASONS,
    verbose: bool = True,
) -> pd.DataFrame:
    """Realized half-PPR outcomes per (season, player), from PFR.

    Half-PPR is `(FANTPT + PPR) / 2` — PPR minus FANTPT is exactly receptions, so the midpoint
    is the half-point-per-reception total. Finish ranks are RECOMPUTED on half-PPR rather than
    taken from PFR's own POS RANK / RK / VBD, which are computed on PFR's scoring: using those
    would measure the outcome in different units than the board being scored.
    """
    df = pd.read_csv(combined_data_path)
    df = df[df["SEASON"].isin(seasons)].copy()

    # Same guard the stats aggregation uses: PFR occasionally emits per-team fragments
    # alongside the combined nTM row, which would give a player two outcome rows.
    df = pd.concat([_dedupe_season_rows(g, verbose=False) for _, g in df.groupby("SEASON")], ignore_index=True)

    df["POS"] = df["POS"].astype(str).str.upper().str.strip()
    df = df[df["POS"].isin(ANALYSIS_POSITIONS)]

    # PFR leaves the points columns blank for a player who scored nothing, not null-as-unknown.
    fantpt = pd.to_numeric(df["FANTPT"], errors="coerce").fillna(0.0)
    ppr = pd.to_numeric(df["PPR"], errors="coerce").fillna(0.0)
    games = pd.to_numeric(df["G"], errors="coerce").fillna(0).astype(int)

    out = pd.DataFrame(
        {
            "season": df["SEASON"].astype(int),
            "player_id": df["ID"],
            "player_name": df["PLAYER NAME"].astype(str).str.strip(),
            "pos": df["POS"],
            "team": df["TEAM"],
            "games": games,
            "fpts_half": ((fantpt + ppr) / 2).round(2),
            "fpts_ppr": ppr.round(2),
            "fpts_std": fantpt.round(2),
        }
    )
    out["ppg_half"] = (out["fpts_half"] / out["games"].where(out["games"] > 0)).round(3)

    out["pos_finish_rank"] = out.groupby(["season", "pos"])["fpts_half"].rank(ascending=False, method="min").astype(int)
    out["overall_finish_rank"] = out.groupby("season")["fpts_half"].rank(ascending=False, method="min").astype(int)

    # Value over replacement puts positions on one scale for anything keyed on overall rank.
    out["value_over_replacement"] = _value_over_replacement(out)

    if verbose:
        for season in sorted(out["season"].unique()):
            s = out[out["season"] == season]
            print(f"   ✓ {season}: {len(s)} player outcomes ({s['games'].gt(0).sum()} played a game)")
    return out


def _value_over_replacement(out: pd.DataFrame) -> pd.Series:
    """Half-PPR points above the positional replacement level (see REPLACEMENT_BASELINES)."""
    vor = pd.Series(index=out.index, dtype=float)
    for _, group in out.groupby(["season", "pos"], sort=False):
        baseline = REPLACEMENT_BASELINES.get(group["pos"].iloc[0])
        if baseline is None:
            continue
        ordered = group["fpts_half"].sort_values(ascending=False).to_list()
        # Short position group: fall back to its last player rather than indexing off the end.
        replacement = ordered[baseline - 1] if len(ordered) >= baseline else (ordered[-1] if ordered else 0.0)
        vor.loc[group.index] = (group["fpts_half"] - replacement).round(2)
    return vor


def load_snapshot(
    rankings: pd.DataFrame,
    outcomes: pd.DataFrame,
    db_path: Optional[str] = None,
    verbose: bool = True,
) -> str:
    """Write both tables to SQLite, replacing whatever is there.

    Drop-and-recreate is right here: the snapshot is frozen, so there is no incremental
    state to preserve, and a rebuild should never leave half of a previous run behind.

    The tables are additive — fantasy-data's SQLAlchemy models don't know about them, and
    the names don't collide with anything it manages.
    """
    path = Path(db_path) if db_path else HOME_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        rankings.to_sql("expert_rankings_historical", conn, if_exists="replace", index=False)
        outcomes.to_sql("player_season_outcomes", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_erh_season_expert ON expert_rankings_historical(season, expert)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_erh_player ON expert_rankings_historical(season, player_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_pso_player ON player_season_outcomes(season, player_id)")
        conn.execute("DROP VIEW IF EXISTS v_expert_rank_vs_outcome")
        conn.execute(
            """
            CREATE VIEW v_expert_rank_vs_outcome AS
            SELECT r.season, r.as_of_date, r.expert, r.expert_kind, r.rank_scope,
                   r.player_id, r.name_as_published, r.overall_rank, r.pos_rank,
                   r.pos_rank_derived, r.pos AS pos_published,
                   o.player_name, o.pos, o.team, o.games,
                   o.fpts_half, o.ppg_half, o.value_over_replacement,
                   o.pos_finish_rank, o.overall_finish_rank
            FROM expert_rankings_historical r
            LEFT JOIN player_season_outcomes o
              ON o.season = r.season AND o.player_id = r.player_id
            """
        )

    if verbose:
        print(f"   ✓ Wrote {len(rankings)} ranking rows and {len(outcomes)} outcome rows to {path}")
    return str(path)
