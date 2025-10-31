# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python pipeline for processing fantasy football rankings from multiple sources (FPTS, FantasyPros, JJ Zachariason, DraftShark, Hayden Winks, PFF), calculating advanced metrics like Value-Based Drafting (VBD), and consolidating rankings into unified output files.

**Key Feature**: For weekly and ROS rankings, the pipeline includes an **integrated web scraper** (`src/fantasy_pipeline/scraper/`) that automatically fetches Hayden Winks rankings from Underdog Network, eliminating the need for manual file downloads.

**Package Name**: `fantasy-pipeline` - installed as `fantasy_pipeline` Python package (see `pyproject.toml` for current version)

## Requirements

- **Python**: 3.10 or higher
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
# Run tests (when test suite exists)
pytest

# Run with coverage
pytest --cov=src

# Code formatting
black src/ scripts/

# Linting
ruff check src/ scripts/

# Type checking
mypy src/
```

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
    │   └── integration.py   # HW scraper integration (auto-scraping)
    └── cli/                 # Command-line interface
        ├── __init__.py
        ├── main.py          # Main CLI entry point
        ├── rankings.py      # Rankings command
        └── stats.py         # Stats generation command

scripts/
└── update_player_key.py     # Player key maintenance tools

docs/
├── api/source-library.md    # Complete API reference
└── development/             # Architecture documentation
```

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
