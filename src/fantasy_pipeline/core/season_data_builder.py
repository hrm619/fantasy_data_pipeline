"""Build the multi-season season-totals dataset from raw Pro-Football-Reference exports.

Ported from `notebooks/ff-data.ipynb` so the ingest is testable and CI-covered rather than
notebook-only. The notebook carried a hardcoded list of season strings, so dropping in a new
`s<year>.xlsx` did nothing until someone remembered to edit that list — a silent no-op. Seasons
are derived from the filenames here instead.

Input:  `data/fpts historical/s<year>.xlsx` — one raw PFR fantasy table per season
Output: `data/fpts historical/combined_data.csv` — every season concatenated, plus SEASON

PFR blocks scripted access (403), so these .xlsx files are manual once-a-year downloads from
pro-football-reference.com/years/<year>/fantasy.htm.
"""

import os
import re
from typing import Dict, Optional

import pandas as pd

# Column layout of PFR's fantasy season table, in order. The export has a TWO-row header (a
# group row: Games/Passing/Rushing..., then the real one: Rk/Player/Tm/...), so the names are
# imposed POSITIONALLY after dropping it — order matters far more than these labels.
PFR_SEASON_COLUMNS = [
    "OVERALL RK",
    "PLAYER NAME",
    "TEAM",
    "POS",
    "AGE",
    "G",
    "GS",
    "PASS CMP",
    "PASS ATT",
    "PASS YDS",
    "PASS TD",
    "PASS INT",
    "RUSH ATT",
    "RUSH YDS",
    "RUSH Y/A",
    "RUSH TD",
    "REC TGT",
    "REC REC",
    "REC YDS",
    "REC Y/R",
    "REC TD",
    "FMB",
    "FL",
    "TOT TD",
    "2PM",
    "2PP",
    "FANTPT",
    "PPR",
    "DKPT",
    "FDPT",
    "VBD",
    "POS RANK",
    "RK",
    "ID",
]

# Season files are named s<year>.xlsx (s2014.xlsx ... s2025.xlsx).
SEASON_FILE_RE = re.compile(r"^s(\d{4})\.xlsx$", re.IGNORECASE)

DEFAULT_INPUT_DIR = "data/fpts historical"
DEFAULT_OUTPUT_PATH = os.path.join(DEFAULT_INPUT_DIR, "combined_data.csv")


def discover_season_files(input_dir: str = DEFAULT_INPUT_DIR) -> Dict[int, str]:
    """Return {season: filepath} for every s<year>.xlsx in `input_dir`.

    Derived from filenames so a newly dropped season is picked up automatically.
    """
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Season data directory not found: {input_dir}")

    found = {}
    for name in os.listdir(input_dir):
        match = SEASON_FILE_RE.match(name)
        if match:
            found[int(match.group(1))] = os.path.join(input_dir, name)

    if not found:
        raise FileNotFoundError(
            f"No season files (s<year>.xlsx) found in {input_dir}. Download a season from "
            "pro-football-reference.com/years/<year>/fantasy.htm and save it as s<year>.xlsx."
        )
    return dict(sorted(found.items()))


def load_season_file(path: str, season: int) -> pd.DataFrame:
    """Load one raw PFR season export into the combined schema.

    read_excel takes the group row as the columns, so row 0 of the data is the *real* header
    ('Rk', 'Player', ...) — drop it, then impose PFR_SEASON_COLUMNS positionally.
    """
    df = pd.read_excel(path)
    df = df.drop(0).reset_index(drop=True)

    if len(df.columns) != len(PFR_SEASON_COLUMNS):
        raise ValueError(
            f"{os.path.basename(path)} has {len(df.columns)} columns, expected "
            f"{len(PFR_SEASON_COLUMNS)}. The names are applied positionally, so a width change "
            "would silently mislabel every column — check the PFR export layout."
        )

    df.columns = PFR_SEASON_COLUMNS
    # PFR decorates names with award markers ('Saquon Barkley*+') and accents; strip to letters
    # and spaces so they match the player key ('Amon-Ra St. Brown' -> 'AmonRa St Brown').
    df["PLAYER NAME"] = df["PLAYER NAME"].str.replace(r"[^a-zA-Z\s]", "", regex=True)
    df["SEASON"] = season
    return df


def build_combined_season_data(
    input_dir: str = DEFAULT_INPUT_DIR,
    output_path: Optional[str] = DEFAULT_OUTPUT_PATH,
    verbose: bool = True,
) -> pd.DataFrame:
    """Concatenate every s<year>.xlsx in `input_dir` into the combined season-totals dataset.

    Args:
        input_dir: Directory holding the raw s<year>.xlsx exports.
        output_path: Where to write the CSV (None to skip writing and just return the frame).
        verbose: Print per-season progress.

    Returns:
        The combined DataFrame (PFR_SEASON_COLUMNS + SEASON), season-ascending.
    """
    season_files = discover_season_files(input_dir)

    if verbose:
        print("📚 Building combined season data")
        print(f"   Input: {input_dir}")
        print(f"   Found {len(season_files)} season file(s): {', '.join(str(s) for s in season_files)}")

    frames = []
    for season, path in season_files.items():
        df = load_season_file(path, season)
        frames.append(df)
        if verbose:
            print(f"   ✓ {season}: {len(df)} players ({os.path.basename(path)})")

    combined = pd.concat(frames, ignore_index=True)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        combined.to_csv(output_path, index=False)
        if verbose:
            print(f"\n💾 Wrote {len(combined)} rows across {len(season_files)} seasons to: {output_path}")

    return combined
