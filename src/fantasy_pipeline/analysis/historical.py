"""Adapters that turn the historical ranking snapshot into tidy facts.

The two snapshot files share no schema — the 2024 board is a hand-built spreadsheet, the
2025 board is this pipeline's own output — so each gets its own adapter, and both emit the
same long/tidy shape: one row per (season, expert, player).

Outcomes come from PFR (`combined_data.csv`), scored in half-PPR to match the board.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ..core.stats_aggregator import _dedupe_season_rows
from ..data.player_utils import add_player_ids, clean_player_names, load_player_key_mapping

HISTORICAL_DIR = "data/rankings_historical"
COMBINED_DATA_PATH = "data/fpts historical/combined_data.csv"
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
    "pff": "expert",
    "ds": "expert",
    "hw": "expert",
    "fpts": "expert",
    "jj": "expert",
    "4for4": "expert",
    "ringer": "expert",
}

SNAPSHOTS = {
    2024: ("2024 Pre-Season Rankings (August 20 2024).csv", "2024-08-20"),
    2025: ("2025 Pre-Season Rankings (August 22 2025).csv", "2025-08-22"),
}

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
            parsed = df[col].map(_parse_positional) if df[col].dtype == object else _numeric(df[col])
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


def build_expert_rankings(
    historical_dir: str = HISTORICAL_DIR,
    player_key_path: str = "player_key_dict.json",
    verbose: bool = True,
) -> pd.DataFrame:
    """Read both snapshot files and return the tidy expert-ranking fact table."""
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
    out["overall_rank"] = pd.to_numeric(out["overall_rank"], errors="coerce").astype("Int64")
    out["pos_rank"] = pd.to_numeric(out["pos_rank"], errors="coerce").astype("Int64")

    dupes = out.duplicated(["season", "expert", "player_id"]).sum()
    if dupes:
        raise ValueError(f"{dupes} duplicate (season, expert, player_id) rows — a source lists a player twice")
    return out


def build_player_outcomes(
    combined_data_path: str = COMBINED_DATA_PATH,
    seasons: Tuple[int, ...] = tuple(SNAPSHOTS),
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
