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

# Code formatting
black src/ scripts/

# Linting
ruff check src/ scripts/

# Type checking
mypy src/
```

**Test layout** (`tests/`): Unit tests only — no integration/pipeline-run tests yet.
- `test_rankings_processor.py` — RankingsProcessor init, league-type validation, `return_dataframe` API signature
- `test_data_loader.py` — CSV/Excel loading, README-sheet skipping, header auto-detection, unsupported types
- `test_player_utils.py` — name cleaning (Jr suffix, special chars), key mapping load, ID assignment, unknown-player handling
- `tests/conftest.py` provides fixtures: `tmp_csv`, `tmp_csv_with_metadata`, `tmp_excel`, `tmp_excel_with_readme`, `tmp_player_key`, `sample_player_df`

Note: there is no `[tool.pytest]`/`[tool.ruff]`/`[tool.black]`/`[tool.mypy]` config in `pyproject.toml` — all tools run with defaults.

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
- Auto-detection of CSV header rows (handles files with metadata rows)
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
└── update_player_key.py     # Player key maintenance tools

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

Separate from the HW scraper, `fetch_rankings.py` provides HTTP fetchers for sources with public web tables:
- `fetch_fantasypros_adp(output_dir, year=2025, min_players=200)` — scrapes the FantasyPros overall ADP
  table (consensus AVG; ~400 players) and writes the **7-column `COLUMN_MAPPINGS['adp']` schema** directly,
  so the output drops straight into the pipeline → `FantasyPros_{year}_Overall_ADP_Rankings.csv`.
  Also exposed as a CLI command: **`ff-rankings fetch-adp [--output DIR] [--year N] [--min-players N]`**
  (writes to the update folder by default). Per-platform ADP (e.g. Sleeper) is no longer exposed by the
  public page — only the consensus AVG.
- `fetch_fantasypros_rankings(output_dir, year=2025, scoring="ppr", min_players=200)` — parses the
  **embedded `ecrData` JSON** from the FantasyPros cheatsheet page (works year-round; the
  `/rankings/*-overall.php` table 302-redirects in the offseason) and writes the **8-column
  `COLUMN_MAPPINGS['fp']` schema** → `FantasyPros_{year}_Draft_ALL_Rankings.csv`. Defaults to PPR;
  `scoring` ∈ `{ppr, half-ppr, standard}`. CLI: **`ff-rankings fetch-fp [--output DIR] [--year N]
  [--scoring S] [--min-players N]`**.
- `fetch_draftsharks(output_dir, min_players=150)` — **headless-browser** fetcher for DraftSharks half-PPR
  rankings. The page is a JS-rendered SPA (static HTML exposes only ~25 players with no projections), so it
  uses **Playwright** to drive the page's own client-side **"Export Rankings"** button (`handleExport`, a Blob
  download) and captures the resulting CSV via `page.expect_download()`. That CSV is the exact 14-column layout
  the pipeline consumes (renamed positionally into `COLUMN_MAPPINGS['ds']`) → `rankings-half-ppr.csv`.
  Captures the **full ~558-player board**. Also exposed as a CLI command:
  **`ff-rankings fetch-ds [--output DIR] [--min-players N]`** (writes to the update folder by default).
  - **Mobile viewport required**: on the *desktop* viewport the only visible "Export Rankings" control is
    **gated** (`class="export-button gated" href="/login"`). The ungated export is the `a.mobile-export-button`
    variant (`@click="handleExport"`), reachable only with a mobile UA + small viewport (390x844). Do **not**
    use the separate gated "Export Auction Values" button.
  - **Optional dependency**: Playwright is the `headless` extra. Install with
    `uv pip install -e ".[headless]"` then `playwright install chromium`. The import is lazy and raises a
    friendly install hint if missing.
  - **Coverage floor**: raises if fewer than `min_players` (default 150) rows are captured, and validates the
    export header to catch layout drift.
- `fetch_pff(output_dir, year=CURRENT_SEASON, min_players=200)` — **saved-session** headless fetcher for the
  paywalled PFF draft rankings. Reuses a persisted login session (see below) to drive the rankings page's own
  Export/Download and capture the CSV → `Draft-rankings-export-<year>.csv`, the exact `COLUMN_MAPPINGS['pff']`
  9-col layout the pipeline already consumes. CLI: **`ff-rankings fetch-pff [--output DIR] [--year N]
  [--min-players N]`**. Validates the `Overall Rank` header (the export has a title row above it) + coverage floor.
- `fetch_fpts(output_dir, year=CURRENT_SEASON, min_players=90, rankings_url=FPTS_RANKINGS_URL)` —
  **saved-session** headless fetcher for the paywalled FantasyPoints (Scott Barrett) redraft rankings. The
  redraft page (`/nfl/rankings/redraft`) is an SPA defaulting to Hansen's board; the fetcher clicks the
  **"BARRETT'S RANKINGS"** tab (asserting the title switches, so it never exports Hansen's by mistake), then
  the DataTables **"Download as CSV"** button → `Scott Barrett <year> Redraft Rankings.csv` (exact 7-col
  `COLUMN_MAPPINGS['fpts']`). CLI: **`ff-rankings fetch-fpts [--output DIR] [--year N] [--min-players N]
  [--url URL]`** (`--url` overrides the rankings page for live re-verification).
- `fetch_jj(output_dir, post_url=None, year=CURRENT_SEASON, min_players=150)` — **saved-session** fetcher
  for JJ Zachariason's Patreon-gated 1QB redraft rankings (collection 47664). **Patreon post HTML is
  Cloudflare-Turnstile gated** for the headless browser, so attachments are read via the Patreon **JSON
  API** (`/api/posts/<id>?include=attachments_media`), which the session reaches un-gated. By default it
  **auto-discovers** the latest 1QB redraft post from the collection page (`_jj_is_redraft_title`);
  `post_url` targets a specific post. The source is now a **5-col CSV** (the old `.xlsx`'s `Auction` column
  was dropped) — `_jj_adapt_rows` pads it back to the 6-col `COLUMN_MAPPINGS['jj']` width (both `.csv` and
  `.xlsx` attachments are handled) → `Redraft1QB_<year>.csv`. CLI: **`ff-rankings fetch-jj [--output DIR]
  [--post-url URL] [--year N] [--min-players N]`**.

### Saved-session auth for paywalled sources (`scraper/auth.py`)

All three paywalled sources (PFF, FantasyPoints, JJ/Patreon) use a **saved-session** strategy — no
passwords in code or env:
- **`ff-rankings login <source>`** (`{pff, fpts, jj}`) opens a **headed** browser for a one-time manual
  login (2FA/SSO/OAuth all fine). On Enter, the browser context's cookies/localStorage ("storage state")
  persist to `~/.fantasy_pipeline/auth/<source>.json` — **outside the repo**, so there is nothing to gitignore.
- Headless fetchers call `load_storage_state(source)` (raises a friendly "run `ff-rankings login <source>`"
  if absent) and pass it to `browser.new_context(storage_state=...)`.
- Override the secrets dir with `FANTASY_PIPELINE_AUTH_DIR`. Re-run `login` when a session expires.
- Live fetch tests are **skip-gated** on Chromium + a saved session, so CI stays green.

**Auto-login + session longevity** (so you rarely run `login` manually):
- **`validate_session(source)`** (in `fetch_rankings.py`) is a cheap live probe — loads the source's page
  (or hits Patreon's `current_user` API for `jj`) and checks for a logged-in signal (the export control /
  a user id). **`ensure_session(source, auto_login=True)`** runs that probe and, if expired, opens the
  headed login window for you, then re-validates.
- Pass **`--auto-login`** to `refresh-all` or any paywalled `fetch-*` to use it: the login window pops
  **only** when a session is actually expired; otherwise the fetch proceeds untouched. No stored passwords.
- **Sliding sessions:** after each successful authenticated fetch, `auth.save_context_state(context, source)`
  re-persists the context's cookies, so any rotated tokens extend the session's life on each use.
- The `login` prompt nudges you to tick "Remember me" for longer-lived cookies. For guaranteed weeks-long
  sessions independent of site behavior, a persistent browser profile (user-data-dir) is the next lever.

### End-to-end refresh (`ff-rankings refresh-all`)

`_refresh_all_command` (in `cli/rankings.py`) is the one-command convenience wrapper: it runs all six
redraft fetchers into `update/`, then runs the redraft consolidation (`RankingsProcessor`). Fetchers run
**independently** — a failure (e.g. an expired paywalled session) is reported but doesn't stop the others,
and consolidation still runs on whatever landed (`--strict` aborts instead; `--no-consolidate` fetches only).
**Caveat:** redraft consolidation also requires Hayden Winks (`tableDownload.csv`), which has **no fetcher**
(no stable redraft URL) and must be downloaded manually into `update/`; `refresh-all` checks for it up front
and, if absent, fetches the six sources and skips consolidation with instructions rather than failing
cryptically. Flags: `--data-path`, `--base-data-dir`, `--year`, `--no-consolidate`, `--strict`, `--quiet`.

See `SCRAPER-PLAN.md` for the per-source automation roadmap and current status.

## HW Scraper Integration

The `src/fantasy_pipeline/scraper/` module is a web scraper that automatically fetches Hayden Winks rankings for weekly and ROS pipelines.

### How It Works

1. **Automatic Triggering**: When running weekly or ROS rankings, the pipeline checks if `hw-week{N}.csv` or `hw-ros.csv` exists in the update folder
2. **Smart Scraping**: If the file doesn't exist, the scraper automatically:
   - Constructs the URL based on week number (e.g., `week-8-fantasy-football-rankings-the-blueprint-2025`)
   - Fetches the article from Underdog Network using HTTP requests
   - Uses CSS selector (`div.styles_postLayoutBody__MYNJ_`) to locate the post body section
   - Parses position-based sections (QB, RB, WR, TE) using regex patterns
   - Extracts player data from "Player Name - XX.X yards/points in Underdog Pick'em" format
   - Handles Unicode characters (curly quotes like `'` instead of `'`)
   - Matches player names to standardized IDs using fuzzy matching (85% threshold)
   - Extracts analysis/details text for each player
   - Saves output to `data/rankings current/update/hw-week{N}.csv` or `hw-ros.csv`
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

**Missing Player IDs**: Update `player_key_dict.json` with new player name variations using `scripts/update_player_key.py`

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
- Verify scraped file was created in update folder (check for `hw-week{N}.csv` or `hw-ros.csv`)
- Check `src/fantasy_pipeline/data/loader.py` CSV header detection (handles files with metadata rows)
- Ensure BaseProcessor doesn't recalculate POS RANK when already present from scraper
