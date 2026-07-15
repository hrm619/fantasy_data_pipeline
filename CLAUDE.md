# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python pipeline for processing fantasy football rankings from multiple sources (FPTS, FantasyPros, JJ Zachariason, DraftShark, Hayden Winks, PFF), calculating advanced metrics like Value-Based Drafting (VBD), and consolidating rankings into unified output files.

**Key Feature**: For weekly and ROS rankings, the pipeline includes an **integrated web scraper** (`src/fantasy_pipeline/scraper/`) that automatically fetches Hayden Winks rankings from Underdog Network, eliminating the need for manual file downloads.

**Package Name**: `fantasy-pipeline` - installed as `fantasy_pipeline` Python package (see `pyproject.toml` for current version)

## Requirements

- **Python**: 3.9 or higher (`requires-python = ">=3.9"` in `pyproject.toml`; current package version is `0.3.0`)
- **Package Manager**: `uv` (recommended) or `pip`
- **Key Dependencies**: pandas, requests, beautifulsoup4, openpyxl, lxml, rapidfuzz
- **Data Directory Structure**: The pipeline expects this directory layout:
  ```
  data/
  └── rankings current/
      ├── update/           # Place new ranking files here
      ├── latest/           # Processed output appears here
      ├── agg archive/      # Archived output files
      └── raw archive/      # Archived input files
  ```

## Quick Start

```bash
# 1. Clone the repository and navigate to project directory
cd fantasy_data_pipeline

# 2. Install the package in editable mode
uv pip install -e .

# 3. Verify installation
uv run ff-rankings --help

# 4. Process rankings (place source files in data/rankings current/update/ first)
uv run ff-rankings --league-type weekly --week 8
```

## Development Commands

### Package Management
```bash
# Install dependencies (preferred method)
uv pip install -e .

# Alternative using pip
pip install -e .

# Install with dev tools
uv pip install -e ".[dev]"

# Install for notebook work
uv pip install -e ".[notebooks]"
```

### Running the Pipeline
```bash
# Process redraft rankings (default)
uv run ff-rankings

# Process bestball rankings
uv run ff-rankings --league-type bestball

# Process weekly rankings (requires week number)
uv run ff-rankings --league-type weekly --week 2

# Process rest-of-season (ROS) rankings
uv run ff-rankings --league-type ros

# Custom paths and quiet mode
uv run ff-rankings --data-path "custom/path" --quiet

# Generate historical stats
uv run ff-stats --season 2024 --min-games 10
```

### Testing & Quality
```bash
# Run the full test suite (~29 tests across 3 files)
pytest

# Run a single test file
pytest tests/test_rankings_processor.py

# Run a single test
pytest tests/test_player_utils.py::test_clean_player_names

# Run with coverage
pytest --cov=src

# Code formatting (ruff format — black-compatible drop-in)
ruff format src/ scripts/

# Linting
ruff check src/ scripts/

# Type checking (ty — Astral's checker, replaced mypy)
uvx ty check src/
```

**Test layout** (`tests/`): Unit tests only — no integration/pipeline-run tests yet.
- `test_rankings_processor.py` — RankingsProcessor init, league-type validation, `return_dataframe` API signature
- `test_data_loader.py` — CSV/Excel loading, README-sheet skipping, header auto-detection, unsupported types
- `test_player_utils.py` — name cleaning (Jr suffix, special chars), key mapping load, ID assignment, unknown-player handling
- `tests/conftest.py` provides fixtures: `tmp_csv`, `tmp_csv_with_metadata`, `tmp_excel`, `tmp_excel_with_readme`, `tmp_player_key`, `sample_player_df`

Note: `pyproject.toml` configures `[tool.pytest.ini_options]`, `[tool.ruff]`/`[tool.ruff.lint]`, and `[tool.ty]`. Tooling is all-Astral: `uv` (packaging), `ruff check` (lint), `ruff format` (formatting — replaced black; line-length inherited from `[tool.ruff]`), and `ty` (type checking — replaced mypy, run informationally, not yet a CI gate).

## Architecture Overview

### Core Design Pattern: BaseProcessor + Source-Specific Processors

The codebase follows a **unified processor pattern** that eliminates code duplication:

1. **BaseProcessor** (`src/fantasy_pipeline/core/base_processor.py`): Contains all common logic for ranking data processing
   - Creates/validates ranking columns
   - Calculates positional rankings
   - Handles league-type-specific logic (redraft, bestball, weekly)
   - Returns standardized output columns

2. **Source-specific processor functions** (`process_fpts_data`, `process_fantasypros_data`, etc.): Thin wrappers that instantiate BaseProcessor for each data source

3. **RankingsProcessor** (`src/fantasy_pipeline/core/rankings_processor.py`): Main orchestrator that:
   - Loads files from multiple sources
   - Standardizes column names via config mappings
   - Processes each source through BaseProcessor
   - Consolidates rankings into a single dataframe
   - Calculates averages and metrics (VBD, deltas, etc.)
   - Manages file archiving workflow

### Key Architectural Principles

**Configuration-Driven Design**: All source-specific details live in `src/fantasy_pipeline/config.py`:
- `COLUMN_MAPPINGS`: Maps raw column names to standardized names for each source (redraft/bestball)
- `WEEKLY_COLUMN_MAPPINGS`: Weekly-specific column mappings (different from draft)
- `ROS_COLUMN_MAPPINGS`: Rest-of-season specific column mappings
- `FILE_MAPPINGS`: File prefix patterns for locating source files (includes redraft, bestball, weekly, ros)
- `get_weekly_file_mappings(week)`: Generates dynamic file mappings for weekly rankings

**Player Key Dictionary**: Central player name standardization system
- `player_key_dict.json`: Master mapping of player names to unique IDs
- Handles name variations across different sources (e.g., "Patrick Mahomes" vs "Pat Mahomes")
- `src/fantasy_pipeline/data/player_utils.py`: Functions for loading and applying player mappings

**Data Flow Pipeline**:
```
data/rankings current/update/     # Input: Place new ranking files here
         ↓ (processing)
data/rankings current/latest/     # Output: Consolidated rankings saved here
         ↓ (archiving)
data/rankings current/agg archive/   # Old output files archived with timestamps
data/rankings current/raw archive/   # Old input files archived with timestamps
```

**League Type Handling**: The system supports four league types with distinct behaviors:
- `redraft`: Standard draft with ADP, overall rankings, VBD calculations
- `bestball`: Similar to redraft with different file sources
- `weekly`: Focus on positional rankings only, excludes ADP and overall RK
- `ros`: Rest-of-season rankings, similar to weekly (positional focus, no ADP)

### Data Merging by League Type

**Redraft/Bestball**: Historical stats integration
- Season stats: Previous season fantasy points
- Weekly trends: First/second half comparisons
- Files: `rankings_ready_historical_stats_*.csv` in latest folder
- Generated by: `ff-stats` CLI command (uses `stats_aggregator.py`)

### Refreshing HIST_* (the `ff-stats` chain)

`ff-stats` consumes **two** inputs and does not ingest raw data itself. Both must be the **same
season** — `--season` filters the totals but the weekly file holds one season on its own:

| Input | Source | How to refresh |
|---|---|---|
| `combined_data.csv` (season totals) | raw PFR exports `s<year>.xlsx` | **manual** download → `ff-stats ingest` |
| `weekly_data.csv` (weekly half-PPR) | FantasyPros weekly-leaders report | `ff-stats fetch-weekly --year <N>` |

Full refresh:
```bash
# 1. drop s<year>.xlsx into data/fpts historical/ (manual — PFR 403s scripted access)
ff-stats ingest                     # rebuild combined_data.csv (seasons read from filenames)
ff-stats fetch-weekly --year 2025   # weekly data, stamped with SEASON
ff-stats --season 2025              # -> rankings_ready_historical_stats_<ts>.csv in latest/
ff-rankings --league-type redraft   # re-consolidate; the merge picks the NEWEST hist file
```

- **`s<year>.xlsx` must keep PFR's raw shape**: group row, real header row, then data, 34 columns,
  names still decorated (`Saquon Barkley*+` — the ingest strips them). The rename is **positional**;
  `load_season_file` raises on a width change rather than mislabel silently.
- **Seasons are discovered from filenames** (`s(\d{4})\.xlsx`). The old notebook carried a hardcoded
  list, so a newly added year was a silent no-op — that's why this is a CLI now.
- **`ff-stats fetch-weekly` needs the free `fp` session.** The weekly-leaders report is
  registration-fenced like ADP. Careful reading the fence: `registrationFence` is only present
  (`True`) for **anonymous** visitors and is **absent once logged in** — so `fence=None` means
  "authenticated", *not* "unfenced". Judge by row count: anonymous gets an **8-row teaser** vs ~734.
- **Season defaults** come from `LAST_COMPLETED_SEASON` (`CURRENT_SEASON - 1` in config.py) — they were
  hardcoded to 2024 and so silently rebuilt a stale season after the rollover. `create_rankings_ready_dataset`'s
  `current_season` arg is **dead** (unused in the body; kept because it's public API) — the season is
  selected upstream by `season_filter`.
- The merge takes `sorted(...)[-1]` of `rankings_ready_historical_stats_*` in `latest/`, and these files
  are **not archived** across runs — so old ones pile up harmlessly (timestamps sort chronologically, so
  the newest always wins), but a *failed* run leaves its output there too. Check the row count.

**Weekly/ROS**: Contextual data integration
- HW data (`hw-data`): HPPR, EXP, DIFF fields from Hayden Winks
- FPTS data (`fpts-data`): Numeric performance fields (FPTS, XFP, TGT, etc.)
- Files loaded but not processed - merged directly after averaging rankings
- No historical stats merged for weekly/ROS league types

### JJ Weekly File Processing (Special Handling)

JJ Zachariason weekly files have a unique multi-position wide format with two FLEX sections side-by-side:
- **File format**: Excel with "Rankings and Tiers" sheet containing position-specific columns (QB, RB, WR, TE, Defense) followed by two FLEX sections
- **FLEX sections**: Two separate player lists (FLEX and FLEX.1) that need to be concatenated
- **Processing logic** (see `_load_jj_weekly_file()` method in `src/fantasy_pipeline/core/rankings_processor.py`):
  1. Load "Rankings and Tiers" sheet
  2. Find first FLEX column (typically column 34)
  3. Extract Section 1: Columns before first FLEX through first FLEX section (7 columns: Rank, FLEX, Team, Opponent, Total, Pos, Matchup)
  4. Extract Section 2: Next 7 columns (Rank, FLEX.1, Team, Opponent, Total, Pos, Matchup)
  5. Rename both sections to standard column names
  6. Concatenate vertically (typically 50 + 50 = 100 players)
- **Column mapping**: `WEEKLY_COLUMN_MAPPINGS['jj']` expects 7 columns after concatenation
- **Note**: This special handling is ONLY for weekly league type; ROS uses standard sheet loading

### File Loading Intelligence

`src/fantasy_pipeline/data/loader.py` handles:
- Auto-detection of CSV header rows (handles files with metadata rows). **Detection must index against
  NON-BLANK lines**: `read_csv` defaults to `skip_blank_lines=True` and drops blank lines *before*
  applying `header=N`, so counting them offsets the header one row down and silently consumes the first
  data row as column names. PFF's export (title / blank / header / data) hit this exactly — it ate
  overall rank 1 from every board built since at least 2025 (`pff_RK` started at 2). Regression test:
  `test_auto_detects_header_after_blank_line`.
- Excel files with "Read Me" sheets (skips to data sheet)
- Weekly: FP and PFF files have header in second row
- Weekly: JJ files require special FLEX section extraction and concatenation (see "JJ Weekly File Processing" above)
- ROS: Only PFF files have header in second row (FP uses first row)
- ROS: JJ files require loading second Excel sheet "Rankings and Tiers"
- Multi-file sources (e.g., FPTS has separate QB/RB/WR/TE files)

## Common Development Patterns

### Adding a New Data Source

1. Add column mapping to `COLUMN_MAPPINGS` in `src/fantasy_pipeline/config.py`
2. Add file prefix to `FILE_MAPPINGS` for each league type
3. No processor code needed - BaseProcessor handles all sources automatically
4. If source has unique logic, extend `BaseProcessor._handle_special_cases()` in `src/fantasy_pipeline/core/base_processor.py`

### Adding a New League Type

1. Add file mappings to `FILE_MAPPINGS` in `src/fantasy_pipeline/config.py`
2. If weekly-style (no ADP), add column mappings to separate mapping dict (e.g., `ROS_COLUMN_MAPPINGS`)
3. Update `RankingsProcessor.__init__()` to exclude ADP processor if needed
4. Update `RankingsProcessor._load_and_standardize_data()` to use correct column mappings
5. Add league type choice to `src/fantasy_pipeline/cli/rankings.py` argparse
6. If data merge needed, add logic to `_merge_weekly_ros_data()` or create new merge method

### Modifying Output Columns

1. Update `STANDARD_OUTPUT_COLUMNS` or `WEEKLY_OUTPUT_COLUMNS` in `src/fantasy_pipeline/config.py`
2. Modify `RankingsProcessor._organize_final_dataframe()` in `src/fantasy_pipeline/core/rankings_processor.py` for column ordering
3. Update `BaseProcessor._standardize_output()` in `src/fantasy_pipeline/core/base_processor.py` if changing processor outputs

### Working with Player Keys

```python
from fantasy_pipeline import load_player_key_mapping, add_player_ids

# Load mappings
player_key_dict, player_name_to_key = load_player_key_mapping('player_key_dict.json')

# Add player IDs to dataframe
df = add_player_ids(df, player_name_to_key, verbose=True)
```

## Important Implementation Details

### Silent traps in the stats aggregation

All produced plausible output and none raised — check these before trusting `HIST_*`:

1. **Season mixing.** The totals are filtered by SEASON, but `weekly_data.csv` holds ONE season and
   carried no season of its own. Update one input and not the other and `HIST_TOTAL_FPTS` came from one
   year while `HIST_FIRST_HALF_AVG` came from another. `ff-stats fetch-weekly` now stamps SEASON and
   `_verify_weekly_season` rejects a mismatch (then drops the column, so nothing downstream sees it).
2. **pandas joins null == null; SQL does not.** Unmatched players carry `PLAYER_ID = None` on both sides,
   so the ID merge in `_merge_season_and_weekly_data` cross-joined every unmatched season player against
   every unmatched weekly player. It lay dormant for years because it needs unmatched rows on *both*
   sides and 2024 happened to have **zero** on the season side; 2025 brought 51 players missing from
   `player_key_dict` × 136 weekly → **6936 phantom rows** (7529 instead of 643), each pairing one
   player's season stats with an unrelated player's weekly trends. Null-ID rows are now excluded from the
   join key. **Any `.merge(on=...)` here needs the same guard.**

3. **Duplicate player rows** (fixed — two independent causes, both now guarded):
   - **Player-key collisions.** `player_key_dict.json` maps one ID to a player's *name variations*
     ("Ja'Marr Chase" / "JaMarr Chase"), but fuzzy matching (rapidfuzz at 85% in `add_player_ids`) also
     attached **different players sharing a first name**: `RattSp00 → ['Spencer Rattler', 'Spencer
     Shrader']` (QB + kicker), `SandJa01 → ['JaTavion Sanders', 'Jason Sanders']` (TE + kicker). 13 such
     entries. Two players under one ID join to each other's stats *and* multiply rows — JaTavion Sanders
     appeared **8×** in the board (2 ranking rows × 2 HIST rows), carrying the kicker's weekly trends.
     Repaired by `scripts/fix_player_key_collisions.py`; `tests/test_player_key_integrity.py` keeps it
     fixed.
   - **PFR per-team fragments.** A traded player is normally one row marked `2TM`/`3TM`/`4TM`, but PFR
     rarely also emits the per-team rows (21 player-seasons in 2014–2025). `_dedupe_season_rows` keeps
     the most-games row, which picks the combined `nTM` row where one exists and the team actually
     played for otherwise (Elijah Moore 2025: BUF 9 games over DEN 0).

**Validating the player key:** don't guess PFR's ID scheme (`surname[:4]+first[:2]+NN`) — it has padding
quirks (`CJ Ham → HamxC.00`) and legitimate aliases (`Robbie Chosen` = Robbie Anderson) that make naive
checks cry wolf. Validate against **ground truth** instead: PFR's own `ID` column in `combined_data.csv`
(`load_pfr_truth`). Two rules that matter:
- A name PFR doesn't know (kickers, non-fantasy players) is **unverifiable, not wrong**.
- A name under several IDs is **not** automatically a bug — real homonyms exist and PFR gives them
  distinct IDs (two Alex Smiths → `SmitAl02`/`SmitAl03`; 9 such names). Flag only IDs PFR doesn't
  corroborate.

### Consensus columns exclude market + derived data

`avg_RK`, `sd_RK`, and `avg_POS RANK` average **expert sources only**. `_is_derived_or_market_col`
(`core/rankings_processor.py`) excludes the `adp_` / `avg_` / `sd_` prefixes:

- **`adp_` is market data, not an expert ranking.** `ADP Delta = ADP - avg_RK`, so letting ADP into
  `avg_RK` puts it on *both sides* — biasing every delta toward zero. Including it narrowed the
  `ADP Delta` spread ~27% (std 54.0 → 39.4), attenuating the exact divergence signal the board exists
  to measure. Same reasoning for `sd_RK` (dispersion across a set containing the market it's compared
  to) and `avg_POS RANK` vs `adp_POS RANK`.
- `adp_RK` / `adp_POS RANK` are still **emitted** as columns — the exclusion is from the *math*, not
  the board. `rk_columns` in `_organize_final_dataframe` intentionally still includes them (it drives
  column order).

### Output numeric formatting

`_format_numeric_columns` runs at the end of `_organize_final_dataframe`:
- **Ints** (nullable `Int64`): `*_RK`, `*_TIER`, `*POS RANK*`, `ADP ROUND`, `POS ADP`, `ECR`, `POS ECR`.
  They're conceptually integers but arrive as `float64` because a source that omits a player leaves NaN.
  `Int64` keeps them integral while holding the gaps (written to CSV as `1`, blank for missing).
- **Floats, 1dp**: everything else numeric — `avg_RK`, `sd_RK`, the deltas, `ADP`, `HIST_*`. Drops
  artifacts like `sd_RK=0.8944271909999159` / `ADP Delta=-0.3999999999999999`.
- Re-reading the CSV shows `float64` for int columns that have gaps — that's `read_csv` inference, not a
  formatting bug. Check the raw file text.

### Skipping a source (`--skip-source`)

Every source in `file_mapping` is **required** — a missing file is a hard `ValueError`. To build a board
without one: `ff-rankings --league-type redraft --skip-source fpts` (repeatable), or
`RankingsProcessor(..., skip_sources=["fpts"])`. Consensus columns then average only what remains, so a
skip changes their meaning — the run prints a loud warning naming the skipped sources. Use it when a
source is unavailable or its data is untrustworthy; prefer it over shipping bad data.

### VBD Calculation Baselines
- QB: Top 6 (1QB leagues)
- RB: Top 24 (2 RB + 1 Flex)
- WR: Top 30 (2 WR + 1 Flex)
- TE: Top 12 (1 TE)
- QB has 50% adjustment factor

### Weekly Rankings Specifics
- No ADP data or calculations
- No overall RK columns
- Focuses on POS RANK averaging
- Sorted by `avg_POS RANK` instead of ADP
- File mapping uses `get_weekly_file_mappings(week)` for dynamic week numbers
- Merges hw-data and fpts-data for contextual performance metrics
- **Auto-scrapes HW rankings** from Underdog Network if not present in update folder

### ROS Rankings Specifics
- Similar to weekly: no ADP, no overall RK, positional focus only
- Uses `ROS_COLUMN_MAPPINGS` for source-specific column formats
- File mappings in `FILE_MAPPINGS['ros']` use different prefixes than weekly
- FantasyPros ROS files use first row as header (unlike weekly which uses second row)
- JJ files require loading Excel sheet "Rankings and Tiers"
- Merges hw-data and fpts-data like weekly rankings
- **Auto-scrapes HW rankings** from Underdog Network if not present in update folder

### Data Source URLs

**ROS Rankings:**
- **fp (FantasyPros)**: https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php?signedin
- **fpts (Fantasy Points)**: https://www.fantasypoints.com/nfl/rankings/rest-of-season/rb-wr-te?season=2025#/
- **hw (Hayden Winks)**: Auto-scraped from https://underdognetwork.com/football/fantasy-rankings (URL varies by week)
- **jj (JJ Zachariason)**: https://www.patreon.com/posts/141197927?collection=47664
- **pff (PFF)**: https://www.pff.com/fantasy/rankings/draft
- **ds (DraftShark)**: https://www.draftsharks.com/ros-rankings/half-ppr

**Data Files for ROS/Weekly:**
- **hw-data**: Manual download from Underdog Network (tableDownload.csv export) - provides HPPR, EXP, DIFF fields
- **fpts-data**: Performance metrics from Fantasy Points (fpts-xfp-avg.csv)

**Underdog reshuffled the redraft `tableDownload` export for 2026** (`COLUMN_MAPPINGS['hw']`, 10 → 11 cols):

| | Columns |
|---|---|
| Old | `Player, Rank, ADP, Diff, Finish2024, Team, Pos, PosRank, Notes, Id` |
| New | `Player, Team, Pos, PosRank, Rank, ADP, Per Game <yr>, Season <yr>, Team_id, Sport_radar_id, Id` |

The rename is **positional**, so order matters more than names: only `PLAYER NAME/TEAM/POS/POS RANK/RK`
survive `BaseProcessor._standardize_output` — the rest are discarded and their labels are arbitrary. Keep the
ADP column named **`UNDERDOG ADP`**, *not* `ADP`: `ADP` is in `STANDARD_OUTPUT_COLUMNS['optional']`, so that
rename would promote HW's ADP into the output and collide with the FantasyPros `adp` source. A count mismatch
here is quiet — `rankings_processor.py` logs a warning and `continue`s past standardization (only under
`--verbose`), leaving raw columns to flow downstream. **Verify a remap by correlating `hw_RK` against
`adp_RK`/`pff_RK`** (expect ~0.95+); a wrong order still populates the column, just with nonsense.

### Column Naming Conventions
- Source prefixes: `fpts_`, `fp_`, `jj_`, `hw_`, `ds_`, `pff_`
- Rankings: `RK`, `POS RANK`, `ECR`, `POS ECR`
- Averages: `avg_RK`, `avg_POS RANK`
- Deltas: `ADP Delta`, `ECR Delta`, `ECR ADP Delta`
- Historical: `HIST_` prefix for all historical stat columns

### Player Key Dictionary Updates

The `player_key_dict.json` file maps Player IDs to player names (including name variations):
- **Structure**: `{"PlayerID": ["Player Name", "Alternate Name", ...]}`
- **Updates**: Use `player_key_update.csv` with columns `PLAYER NAME, PLAYER ID`
- **Script**: Automated comparison and update using `scripts/update_player_key.py`
- **Usage**: See `src/fantasy_pipeline/data/player_utils.py` for loading and applying mappings

### File Archiving
- Existing files in `latest/` → moved to `agg archive/{timestamp}/`
- Processed files in `update/` → moved to `raw archive/{timestamp}/`
- Historical stats files stay in `latest/` (not archived)
- Timestamps: `YYYYMMDD_HHMM` format

### Debugging and Logging

**Verbose Mode**: Enable detailed logging for troubleshooting
```bash
# Add verbose flag to see detailed processing information
uv run ff-rankings --league-type weekly --week 8 --verbose
```

**Common Debugging Steps**:
1. **File loading issues**: Check that files exist in `data/rankings current/update/` and match expected prefixes in `FILE_MAPPINGS`
2. **Column mapping errors**: Verify column counts match between source files and `COLUMN_MAPPINGS` entries
3. **Player matching issues**: Enable verbose mode to see which players couldn't be matched to player IDs
4. **Scraper failures**: Check network connectivity and inspect the Underdog Network page structure
5. **Data merge problems**: Verify that hw-data and fpts-data files exist and have correct column names

**Output Files**:
- Consolidated rankings saved to `data/rankings current/latest/`
- Check these files for the final processed output
- Archives in `agg archive/` and `raw archive/` contain historical runs

## Code Organization

```
src/
└── fantasy_pipeline/         # Main Python package
    ├── __init__.py          # Public API exports
    ├── config.py            # All configuration and mappings
    ├── utils.py             # Shared utilities
    ├── core/                # Core processing logic
    │   ├── __init__.py
    │   ├── base_processor.py         # Unified processing logic
    │   ├── rankings_processor.py     # Main orchestrator class
    │   ├── season_stats_processor.py # Historical season stats
    │   ├── weekly_stats_processor.py # Historical weekly trends
    │   └── stats_aggregator.py       # Player stats aggregation
    ├── data/                # Data utilities
    │   ├── __init__.py
    │   ├── loader.py        # File loading utilities
    │   └── player_utils.py  # Player name standardization
    ├── scraper/             # Web scraper module
    │   ├── __init__.py
    │   ├── hw_scraper.py    # Web scraping logic and player matching
    │   ├── fetch_rankings.py # HTTP fetchers for public sources (FantasyPros ADP, DraftShark)
    │   └── integration.py   # HW scraper integration (auto-scraping)
    └── cli/                 # Command-line interface
        ├── __init__.py
        ├── rankings.py      # Rankings command (ff-rankings entry point)
        └── stats.py         # Stats generation command (ff-stats entry point)

scripts/
├── update_player_key.py            # Player key maintenance tools
└── fix_player_key_collisions.py    # Repair + validate player-key ID collisions (vs PFR truth)

docs/
├── README.md                   # Docs index
├── usage.md                    # Install → fetch → login → consolidate; league types
├── data-sources.md             # The 7 sources: automated vs manual, fetch-*/login/refresh-all, schemas
└── api/source-library.md       # fantasy_pipeline package API reference

tests/
├── conftest.py              # Shared pytest fixtures (temp CSV/Excel/player-key files)
├── test_rankings_processor.py · test_data_loader.py · test_player_utils.py · test_config.py
├── test_fetch_rankings.py · test_fetch_draftsharks.py · test_fetch_pff.py · test_fetch_fpts.py · test_fetch_jj.py
└── test_auth.py · test_session_auto_login.py · test_refresh_all.py · test_hw_scraper.py
```

Notebooks for exploratory work live in `notebooks/` (`ff-data.ipynb`, `ff-player-key.ipynb`, `ff-rankings.ipynb`).

## Python Package Usage

### Importing the Package

```python
# Main API - recommended imports
from fantasy_pipeline import (
    RankingsProcessor,
    process_redraft_rankings,
    process_weekly_rankings,
    load_player_key_mapping,
    add_player_ids,
)

# Direct module imports
from fantasy_pipeline.core import BaseProcessor
from fantasy_pipeline.data import load_data
from fantasy_pipeline.scraper import auto_scrape_if_needed

# Example usage
processor = RankingsProcessor('redraft')
output_file = processor.process_rankings(verbose=True)
```

### `return_dataframe` API (quant-edge / fantasy-data integration)

`RankingsProcessor.process_rankings()` accepts `return_dataframe: bool = False`
(defined in `src/fantasy_pipeline/core/rankings_processor.py`):

- `return_dataframe=False` (default) → writes the consolidated CSV to `latest/` and returns its **path (str)**.
- `return_dataframe=True` → returns the consolidated **`pandas.DataFrame`** directly without requiring the caller to read a file back.

This is the integration seam consumed by the sibling **`fantasy-data`** repo, which calls
`RankingsProcessor.process_rankings(return_dataframe=True)` to seed its `players` table. When changing
output columns or processing behavior, treat this DataFrame as a downstream contract.

The `data` subpackage (`from fantasy_pipeline.data import ...`) exports `load_data`,
`clean_player_names`, `load_player_key_mapping`, and `add_player_ids`.

### Standalone Source Fetchers (`scraper/fetch_rankings.py`)

Separate from the HW scraper, `fetch_rankings.py` provides fetchers for the draft sources:
- `fetch_fantasypros_adp(output_dir, year=CURRENT_SEASON, min_players=200)` — **saved-session** fetcher for
  the FantasyPros consensus ADP (~412 players), writing the **7-column `COLUMN_MAPPINGS['adp']` schema**
  directly → `FantasyPros_{year}_Overall_ADP_Rankings.csv`. CLI: **`ff-rankings fetch-adp [--output DIR]
  [--year N] [--min-players N] [--auto-login]`**. Per-platform ADP (e.g. Sleeper) is not exposed — only the
  consensus AVG.
  - **Registration-fenced (2026)**: the page no longer renders an HTML `<table>`; the report is embedded as
    a **`window.FP.reportConfig = {...}` JSON blob** (the same migration the rankings page made to `ecrData`),
    carrying `registrationFence: true`. Anonymous requests get a **5-row teaser** — across *every* scoring,
    position, and past-season variant — so the fetcher needs the **free** `fp` account
    (`ff-rankings login fp`). The parser raises a login instruction rather than emitting a 5-player board.
  - Extraction uses `json.JSONDecoder().raw_decode` (brace matching), **not** a non-greedy `(\{.*?\});`
    regex like `ecrData`'s: the blob nests braces and `};` inside strings, so a lazy match can stop early.
  - **Do not** substitute the `fp` cheatsheet's `rank_ave` for ADP. Despite the name it is the average
    *expert rank*, not average *draft position*; `ECR ADP Delta` is `ADP - ECR`, so feeding an ECR-derived
    value in as ADP drives that metric to ~0 by construction and silently destroys the divergence signal.
- `fetch_fantasypros_rankings(output_dir, year=2025, scoring="ppr", min_players=200)` — parses the
  **embedded `ecrData` JSON** from the FantasyPros cheatsheet page (works year-round; the
  `/rankings/*-overall.php` table 302-redirects in the offseason) and writes the **8-column
  `COLUMN_MAPPINGS['fp']` schema** → `FantasyPros_{year}_Draft_ALL_Rankings.csv`. Defaults to PPR;
  `scoring` ∈ `{ppr, half-ppr, standard}`. CLI: **`ff-rankings fetch-fp [--output DIR] [--year N]
  [--scoring S] [--min-players N]`**.
- `fetch_draftsharks(output_dir, min_players=150)` — **saved-session headless-browser** fetcher for
  DraftSharks half-PPR rankings. The page is a JS-rendered SPA (the DOM renders only ~25 players with no
  projections), so it uses **Playwright** to drive the page's own client-side **Export** button
  (`handleExport`, a Blob download) and captures the CSV via `page.expect_download()`. That CSV is the exact
  14-column layout the pipeline consumes (renamed positionally into `COLUMN_MAPPINGS['ds']`) →
  `rankings-half-ppr.csv`. Captures the **full ~558-player board**. CLI:
  **`ff-rankings fetch-ds [--output DIR] [--min-players N] [--auto-login]`**.
  - **Now login-gated (2026)**: this fetcher used to need *no account* — the export was reachable anonymously
    via `a.mobile-export-button` on a mobile UA + 390x844 viewport. **DraftSharks deleted that button.**
    Logged out, the only control left is `a.export-button.gated` → `/login`, so a `ds` session is required
    (`ff-rankings login ds`) and the mobile-viewport hack is gone.
  - **Selector**: the page (Alpine.js) renders **two** `div.export-button` variants toggled on
    `exportContainerOptionPrint` — one wraps a Print/Export dropdown, the other calls `handleExport` directly.
    `_DS_EXPORT_SELECTOR` targets the latter by its **`@click` handler**, which keeps it off the `Print`
    sibling. Wait for **`visible`**, not `attached`: the hidden dropdown variant satisfies `attached` even
    when logged out.
  - **Optional dependency**: Playwright is the `headless` extra. Install with
    `uv pip install -e ".[headless]"` then `playwright install chromium`. The import is lazy and raises a
    friendly install hint if missing.
  - **Coverage floor**: raises if fewer than `min_players` (default 150) rows are captured, and validates the
    export header to catch layout drift.
- `fetch_pff(output_dir, year=CURRENT_SEASON, min_players=200)` — **saved-session** headless fetcher for the
  paywalled PFF draft rankings. Reuses a persisted login session (see below) to drive the rankings page's own
  CSV export and capture it → `Draft-rankings-export-<year>.csv`, the exact `COLUMN_MAPPINGS['pff']`
  9-col layout the pipeline already consumes. CLI: **`ff-rankings fetch-pff [--output DIR] [--year N]
  [--min-players N] [--auto-login]`**. Validates the `Overall Rank` header (the export has a title row above
  it) + coverage floor.
  - **Selector**: `PFF_CSV_BUTTON_SELECTOR` = `button[data-testid="csvDownloadButton"]`. Use the
    **`data-testid`** — the accessible name is `"Download CSV"` while the visible text is only `"CSV"`, so
    name/text matching is brittle.
  - **Entitlement ≠ login**: an account that is logged in *but not subscribed* still renders the button —
    wearing a **lock icon** (`data-testid="lockIcon"`) and redirecting to `/subscribe?referrer=rankings-csv-download`
    on click. This surfaced as a bare `download` **timeout**. `_pff_export_is_locked` now detects the lock so
    the fetcher fails with an actionable message, and `_validate_pff_session` checks it too — previously it
    returned `True` for a locked button (it matched `name=/download/i`), reporting an unusable session as
    VALID. If the subscription is active but the export is locked, the saved session predates it: re-run
    `ff-rankings login pff`.
- `fetch_fpts(output_dir, year=CURRENT_SEASON, min_players=90, rankings_url=FPTS_RANKINGS_URL)` —
  **saved-session** headless fetcher for the paywalled FantasyPoints (Scott Barrett) redraft rankings. The
  redraft page (`/nfl/rankings/redraft`) is an SPA defaulting to Hansen's board; the fetcher clicks the
  **"BARRETT'S RANKINGS"** tab (asserting the title switches, so it never exports Hansen's by mistake), then
  the DataTables **"Download as CSV"** button → `Scott Barrett <year> Redraft Rankings.csv` (exact 7-col
  `COLUMN_MAPPINGS['fpts']`). CLI: **`ff-rankings fetch-fpts [--output DIR] [--year N] [--min-players N]
  [--url URL]`** (`--url` overrides the rankings page for live re-verification).
  - **NEVER trust `document.title` for the season.** FantasyPoints templates the title to the *current*
    year while the body still serves the previous season's board. In the 2026 preseason the title read
    "Scott Barrett's **2026** Redraft Fantasy Football Rankings" above an `<h1>` of "Scott Barrett's
    **2025** NFL Redraft Rankings" (updated 2025-08-30) — so the fetcher happily saved last season's ranks
    as `Scott Barrett 2026 Redraft Rankings.csv`, silently contaminating `avg_RK` for ~97 players.
    (Detection: bye weeks matched the 2025 archive 95/95 and 2026 truth only 6/95.)
  - `_assert_fpts_season(page, year)` reads the **`<h1>`** (the only trustworthy season signal) and raises
    *before* download, so a stale board never reaches disk. **Barrett publishes late — expect this to fire
    through the early preseason**; it is not a bug. Use `--year 2025` to pull an older board deliberately.
    Note the title check in `_select_fpts_barrett` is still valid for *whose* board, just not *which season*.
- `fetch_jj(output_dir, post_url=None, year=CURRENT_SEASON, min_players=150)` — **saved-session** fetcher
  for JJ Zachariason's Patreon-gated 1QB redraft rankings (collection 47664). **Patreon post HTML is
  Cloudflare-Turnstile gated** for the headless browser, so attachments are read via the Patreon **JSON
  API** (`/api/posts/<id>?include=attachments_media`), which the session reaches un-gated. By default it
  **auto-discovers** the latest 1QB redraft post from the collection page (`_jj_is_redraft_title`);
  `post_url` targets a specific post. The source is now a **5-col CSV** (the old `.xlsx`'s `Auction` column
  was dropped) — `_jj_adapt_rows` pads it back to the 6-col `COLUMN_MAPPINGS['jj']` width (both `.csv` and
  `.xlsx` attachments are handled) → `Redraft1QB_<year>.csv`. CLI: **`ff-rankings fetch-jj [--output DIR]
  [--post-url URL] [--year N] [--min-players N]`**.

### Saved-session auth for account-gated sources (`scraper/auth.py`)

**Five of the six draft fetchers now need an account** — only `fp` (expert consensus rankings) is open.
`SOURCE_LOGIN_URLS` is the single registry; all use a **saved-session** strategy — no passwords in code or env:
- **`ff-rankings login <source>`** (`{fp, ds, pff, fpts, jj}`) opens a **headed** browser for a one-time manual
  login (2FA/SSO/OAuth all fine). On Enter, the browser context's cookies/localStorage ("storage state")
  persist to `~/.fantasy_pipeline/auth/<source>.json` — **outside the repo**, so there is nothing to gitignore.
- Headless fetchers call `load_storage_state(source)` (raises a friendly "run `ff-rankings login <source>`"
  if absent) and pass it to `browser.new_context(storage_state=...)`.
- `load_cookies(source, domain_contains=...)` returns `{name: value}` for use with **`requests`** — reuse a
  session with **no browser** when the page is server-rendered. `fetch-adp` takes this path.
- **Login keys are per-site, not per-fetcher**: `fp` covers the FantasyPros account, but only the *ADP*
  report is fenced — `fetch-fp` itself needs no session. `refresh-all` maps `adp → fp` for this reason.
- Override the secrets dir with `FANTASY_PIPELINE_AUTH_DIR`. Re-run `login` when a session expires.
- Live fetch tests are **skip-gated** on Chromium + a saved session, so CI stays green.

**Gating drifts — check access before debugging parsers.** In the 2026 preseason all three then-broken
fetchers turned out to be **access changes, not code bugs**: FantasyPros fenced ADP behind free registration,
DraftSharks deleted its ungated export button, and PFF moved CSV export behind a subscription the saved
session predated. Symptoms are misleading (a `0 rows` parse error, a `wait_for` timeout, a `download`
timeout), so probe the live DOM for locks/fences/redirects first.

**Auto-login + session longevity** (so you rarely run `login` manually):
- **`validate_session(source)`** (in `fetch_rankings.py`) is a cheap live probe — loads the source's page
  (or hits Patreon's `current_user` API for `jj`, or FantasyPros' ADP JSON for `fp`) and checks for a
  logged-in signal. **`ensure_session(source, auto_login=True)`** runs that probe and, if expired, opens the
  headed login window for you, then re-validates.
  - Validators must assert the session is **usable**, not merely present — see the `_validate_pff_session`
    lock bug above. `_validate_fp_session` checks row count > `FP_ADP_TEASER_ROWS` (not just that the page
    loads); `_validate_ds_session` requires the `handleExport` control to be **visible**.
- Pass **`--auto-login`** to `refresh-all` or any gated `fetch-*` to use it: the login window pops
  **only** when a session is actually expired; otherwise the fetch proceeds untouched. No stored passwords.
- **Sliding sessions:** after each successful authenticated fetch, `auth.save_context_state(context, source)`
  re-persists the context's cookies, so any rotated tokens extend the session's life on each use.
- The `login` prompt nudges you to tick "Remember me" for longer-lived cookies. For guaranteed weeks-long
  sessions independent of site behavior, a persistent browser profile (user-data-dir) is the next lever.

### End-to-end refresh (`ff-rankings refresh-all`)

`_refresh_all_command` (in `cli/rankings.py`) is the one-command convenience wrapper: it runs all six
redraft fetchers into `update/`, then runs the redraft consolidation (`RankingsProcessor`). Fetchers run
**independently** — a failure (e.g. an expired session) is reported but doesn't stop the others,
and consolidation still runs on whatever landed (`--strict` aborts instead; `--no-consolidate` fetches only).
**Caveat:** redraft consolidation also requires Hayden Winks (`tableDownload.csv`), which has **no fetcher**
(no stable redraft URL) and must be downloaded manually into `update/`; `refresh-all` checks for it up front
and, if absent, fetches the six sources and skips consolidation with instructions rather than failing
cryptically. Flags: `--data-path`, `--base-data-dir`, `--year`, `--no-consolidate`, `--strict`, `--quiet`.

See `SCRAPER-PLAN.md` for the per-source automation roadmap and current status.

## HW Scraper Integration

The `src/fantasy_pipeline/scraper/` module is a web scraper that automatically fetches Hayden Winks rankings for weekly and ROS pipelines.

### How It Works

1. **Automatic Triggering**: When running weekly or ROS rankings, the pipeline checks if `hw-week{N}.csv` exists in the update folder (weekly and ROS share this filename — keyed on the `--week` you run)
2. **Smart Scraping**: If the file doesn't exist, the scraper automatically:
   - Constructs the URL based on week number (e.g., `week-8-fantasy-football-rankings-the-blueprint-2025`)
   - Fetches the article from Underdog Network using HTTP requests
   - Uses CSS selector (`div.styles_postLayoutBody__MYNJ_`) to locate the post body section
   - Parses position-based sections (QB, RB, WR, TE) using regex patterns
   - Extracts player data from "Player Name - XX.X yards/points in Underdog Pick'em" format
   - Handles Unicode characters (curly quotes like `'` instead of `'`)
   - Matches player names to standardized IDs using fuzzy matching (85% threshold)
   - Extracts analysis/details text for each player
   - Saves output to `data/rankings current/update/hw-week{N}.csv` (both weekly and ROS)
3. **Skip on Exists**: If the file already exists, scraping is skipped (prevents redundant network calls)
4. **Graceful Failure**: If scraping fails, the pipeline continues with existing files

### Key Files

- **`src/fantasy_pipeline/scraper/integration.py`**: Bridge between scraper and main pipeline
  - `auto_scrape_if_needed()`: Main entry point, checks if scraping needed
  - `run_hw_scraper()`: Executes scraper and saves output
  - `check_hw_scraper_output_exists()`: Checks if scraped file already exists
- **`src/fantasy_pipeline/config.py`**:
  - `get_hw_scraper_url()`: Generates Underdog Network URL from week number
  - `ROS_COLUMN_MAPPINGS['hw']`: Maps scraper output columns to pipeline format
- **`src/fantasy_pipeline/scraper/hw_scraper.py`**: Core scraping logic with player matching

### Manual Scraper Usage

You can also use the scraper standalone:

```python
from fantasy_pipeline.scraper import scrape_fantasy_rankings

# Scrape specific week
url = "https://underdognetwork.com/football/fantasy-rankings/week-7-fantasy-football-rankings-the-blueprint-2025"
df = scrape_fantasy_rankings(url)
df.to_csv("hw-week7.csv", index=False)
```

### Important Notes

- **Scraper Output**: Includes `Player Name`, `Player ID`, `Standardized Name`, `Position`, `Position Rank`, `Yards Stat`, `Details`
- **Player IDs**: Pre-matched using scraper's own player_key_dict.json (shared with main pipeline)
- **Player Key Path**: The scraper loads `player_key_dict.json` from project root using relative path navigation (3 levels up from `src/fantasy_pipeline/scraper/hw_scraper.py`)
- **No TEAM Column**: HW scraper doesn't extract team info; TEAM is filled from other sources during merge
- **POS RANK Preservation**: BaseProcessor skips recalculating POS RANK if already present from scraper

## Common Gotchas

**File Naming**: File prefixes in `data/rankings current/update/` must exactly match the patterns defined in `FILE_MAPPINGS`. Common mistakes:
- Using wrong week format (e.g., `week8` instead of `week-8`)
- Incorrect file extensions (expecting `.csv` but file is `.xlsx`)
- Extra spaces or special characters in filenames

**Column Order Matters**: When adding new data sources, the order of columns in `COLUMN_MAPPINGS` must match the exact column order in the source file (left to right)

**League Type Differences**: Weekly and ROS use different column mappings (`WEEKLY_COLUMN_MAPPINGS`, `ROS_COLUMN_MAPPINGS`) than redraft/bestball (`COLUMN_MAPPINGS`). Don't mix them up.

**Player Name Standardization**: Player names from different sources may vary (e.g., "Pat Mahomes" vs "Patrick Mahomes"). Always update `player_key_dict.json` when adding new players.

**Excel Sheet Names**: Some sources (like JJ) use specific Excel sheet names. The loader expects "Rankings and Tiers" for JJ ROS files. Verify sheet names if you encounter Excel loading errors.

**HW Scraper Dependencies**: The scraper requires `beautifulsoup4`, `requests`, and `rapidfuzz`. If scraping fails, verify these packages are installed.

## Troubleshooting

**File Not Found Errors**: Check that file prefixes in `FILE_MAPPINGS` match actual filenames in `data/rankings current/update/`

**Column Count Mismatches**: Verify `COLUMN_MAPPINGS` entry has same number of columns as source file

**Missing Player IDs**: Update `player_key_dict.json` with new player name variations using `scripts/update_player_key.py`.
Adding names via fuzzy matching is what produced the ID collisions above — a shared first name clears the 85%
threshold. After any bulk update run `uv run python scripts/fix_player_key_collisions.py --dry-run` (or just
`pytest tests/test_player_key_integrity.py`) to check nothing was mapped onto another player's ID.

**Weekly Rankings Issues**: Ensure `--week` parameter is provided and file mappings in `get_weekly_file_mappings()` are correct

**JJ Weekly Column Mismatch**: If JJ weekly processing fails with column count errors:
- Verify FLEX section extraction is working (should produce 100 rows from 2 sections of 50)
- Check that `WEEKLY_COLUMN_MAPPINGS['jj']` has 7 columns: RK, PLAYER NAME, TEAM, OPP, TOTAL, POS, MATCHUP
- Inspect Excel file to confirm FLEX column position (typically column 34)
- Ensure both FLEX sections are being concatenated (check `_load_jj_weekly_file()` method in `src/fantasy_pipeline/core/rankings_processor.py`)

**HW Scraper Failures**:
- Check URL pattern in `get_hw_scraper_url()` matches current Underdog Network article naming (format: `week-{N}-fantasy-football-rankings-the-blueprint-2025`)
- Verify CSS selector `div.styles_postLayoutBody__MYNJ_` still targets the post body (Next.js class names may change)
- Ensure position headers still use format "Week {N} {POS} Rankings" (e.g., "Week 8 RB Rankings")
- Check player entry format: "Player Name - XX.X yards/points in Underdog Pick'em" (note: curly quote `'` not straight `'`)
- Use `force=True` in `auto_scrape_if_needed()` to re-scrape even if file exists
- Check network connectivity and Underdog Network availability
- If 0 players scraped, inspect page source to verify text content structure hasn't changed

**Missing HW Rankings Data**:
- Verify scraped file was created in update folder (check for `hw-week{N}.csv`)
- Check `src/fantasy_pipeline/data/loader.py` CSV header detection (handles files with metadata rows)
- Ensure BaseProcessor doesn't recalculate POS RANK when already present from scraper
