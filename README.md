# Fantasy Football Data Pipeline

A comprehensive Python pipeline for processing fantasy football rankings data from multiple sources, calculating advanced metrics like Value-Based Drafting (VBD), and managing data workflows.

## Features

- **Multi-Source Data Processing**: Integrates rankings from FPTS, FantasyPros, JJ Zachariason, DraftShark, Hayden Winks, and PFF
- **Automated Web Scraping**: Built-in scraper automatically fetches Hayden Winks rankings from Underdog Network for weekly/ROS rankings
- **Multiple League Types**: Supports redraft, bestball, weekly, and rest-of-season (ROS) rankings
- **Automated File Management**: Handles data flow between update, latest, and archive folders
- **Advanced Analytics**: Calculates Value-Based Drafting (VBD) with position-specific baselines
- **Player Key Matching**: Standardizes player names across different data sources
- **Consolidated Rankings**: Creates unified ranking files with multiple ranking systems
- **Contextual Data Integration**: Merges performance metrics (HPPR, FPTS, XFP) for weekly/ROS rankings
- **Historical Data Preservation**: Archives processed files with timestamps
- **Jupyter Notebook Analysis**: Includes notebooks for data exploration and analysis

## 📚 Documentation

Complete documentation is available in the repository:

- **[📖 API Reference](docs/api/source-library.md)** - Complete source library documentation
- **[🛠 Development Docs](docs/development/)** - Architecture and consolidation details
- **[🌐 Data Sources](DATA_SOURCES.md)** - Complete list of data source URLs and export instructions
- **[💻 Claude Code Guide](CLAUDE.md)** - Development patterns and architecture for AI assistants
- **[📝 Documentation Index](docs/README.md)** - Full documentation navigation

## Installation

Install dependencies using uv (recommended):
```bash
uv pip install -e .

# With development tools
uv pip install -e ".[dev]"

# With notebook support
uv pip install -e ".[notebooks]"
```

## Usage

### Rankings Processor

The main functionality is the unified rankings processor that consolidates multiple ranking sources:

```python
from fantasy_pipeline import RankingsProcessor

# Process rankings with simplified API
processor = RankingsProcessor('redraft')  # or 'bestball', 'weekly', 'ros'
output_file = processor.process_rankings()

print(f"Rankings saved to: {output_file}")
```

### Command Line Usage

```bash
# Process redraft rankings (default)
uv run ff-rankings

# Process bestball rankings
uv run ff-rankings --league-type bestball

# Process weekly rankings (requires week number)
uv run ff-rankings --league-type weekly --week 7

# Process rest-of-season rankings
uv run ff-rankings --league-type ros

# With custom paths and quiet mode
uv run ff-rankings --data-path "custom/update/path" --quiet

# Generate historical stats for rankings
uv run ff-stats --season 2024 --min-games 10
```

### Data Workflow

The pipeline follows this automated workflow:

1. **Auto-Scraping** (Weekly/ROS only): If HW rankings don't exist, automatically scrape from Underdog Network
2. **Input**: Place new ranking files in `data/rankings current/update/`
3. **Archive Management**: Existing files in `latest/` are moved to `agg archive/`
4. **Processing**: Rankings are processed, cleaned, and consolidated
5. **Output**: Final rankings saved to `data/rankings current/latest/`
6. **Cleanup**: Source files moved from `update/` to `raw archive/`

## Data Structure

### Input Sources

The pipeline integrates data from six primary ranking sources:

- **FPTS (Fantasy Points)**: Fantasy points projections with detailed stats
- **FantasyPros**: Consensus expert rankings (ECR)
- **JJ Zachariason**: Late Round Podcast rankings and tiers
- **DraftShark**: Rankings with projections (floor, ceiling, consensus)
- **Hayden Winks**: Expert rankings with HPPR projections *(auto-scraped for weekly/ROS)*
- **PFF (Pro Football Focus)**: Rankings and projections

For complete data source URLs, export instructions, and file naming conventions, see **[DATA_SOURCES.md](DATA_SOURCES.md)**.

### Automated Web Scraping

For **weekly** and **ROS** rankings, the pipeline includes a built-in web scraper for Hayden Winks rankings from Underdog Network:

**Features:**
- **Automatic**: Scraper runs automatically if `hw-week{N}.csv` or `hw-ros.csv` doesn't exist
- **Smart**: Skips scraping if file already exists (prevents redundant network calls)
- **Robust**: Continues processing with existing files if scraping fails
- **Player Matching**: Uses fuzzy matching (85% threshold) to standardize player names to IDs
- **No Manual Downloads**: Eliminates need to manually download HW rankings from Underdog Network

**How It Works:**
1. Constructs URL based on week number (e.g., `week-8-fantasy-football-rankings-the-blueprint-2025`)
2. Fetches article HTML from Underdog Network
3. Uses CSS selector to locate post body section
4. Parses position sections (QB, RB, WR, TE) using regex
5. Extracts player data: "Player Name - XX.X yards/points in Underdog Pick'em"
6. Handles Unicode characters (curly quotes: `'` instead of `'`)
7. Matches players to standardized IDs from `player_key_dict.json`
8. Extracts analysis/details text for each player
9. Saves to `data/rankings current/update/hw-week{N}.csv` or `hw-ros.csv`

**Output Columns:** `Player Name`, `Player ID`, `Standardized Name`, `Position`, `Position Rank`, `Yards Stat`, `Details`

The scraper module is located in `src/fantasy_pipeline/scraper/`.

### Output Format
The consolidated rankings include:

**All League Types:**
- Player ID and standardized names
- Position and team information
- Multiple ranking systems (6 sources)
- Position-specific ranks from each source
- Averaged positional rankings

**Redraft/Bestball Only:**
- ADP data (round, pick, rank)
- VBD calculations (Value-Based Drafting)
- Historical season stats (if available)

**Weekly/ROS Only:**
- HPPR, EXP, DIFF fields from Hayden Winks
- Performance metrics: FPTS, XFP, TGT, TD, etc.
- Game-level context data

### VBD Baselines
- **QB**: Top 6 (1QB leagues)
- **RB**: Top 24 (2 RB + 1 Flex)
- **WR**: Top 30 (2 WR + 1 Flex)
- **TE**: Top 12 (1 TE)

## Directory Structure

```
fantasy_data_pipeline/
├── src/
│   └── fantasy_pipeline/         # Main Python package
│       ├── core/                 # Core processing logic
│       │   ├── rankings_processor.py
│       │   ├── base_processor.py
│       │   ├── season_stats_processor.py
│       │   ├── weekly_stats_processor.py
│       │   └── stats_aggregator.py
│       ├── data/                 # Data utilities
│       │   ├── loader.py
│       │   └── player_utils.py
│       ├── scraper/              # Web scraping
│       │   ├── hw_scraper.py
│       │   └── integration.py
│       ├── cli/                  # Command-line interface
│       │   ├── main.py
│       │   ├── rankings.py
│       │   └── stats.py
│       ├── config.py             # Configuration
│       └── utils.py              # Utilities
├── data/
│   └── rankings current/
│       ├── update/               # New ranking files to process
│       ├── latest/               # Most recent processed rankings
│       ├── agg archive/          # Historical output files
│       └── raw archive/          # Historical input files
├── scripts/
│   └── update_player_key.py     # Player key maintenance
├── notebooks/
│   ├── ff-data.ipynb            # Data analysis
│   ├── ff-player-key.ipynb      # Player key exploration
│   └── ff-rankings.ipynb        # Rankings analysis
└── player_key_dict.json         # Player name standardization
```

## Key Components

### Rankings Processor (`src/fantasy_pipeline/core/rankings_processor.py`)
- Loads and standardizes data from multiple sources
- Orchestrates auto-scraping for weekly/ROS rankings
- Calculates VBD metrics with position-specific baselines
- Creates consolidated rankings with multiple scoring systems
- Manages automated file archiving workflow

### HW Scraper (`src/fantasy_pipeline/scraper/hw_scraper.py`)
- Core web scraping logic using BeautifulSoup and requests
- CSS selector-based HTML parsing (`div.styles_postLayoutBody__MYNJ_`)
- Regex pattern matching for player entries with Unicode support
- Fuzzy player name matching (85% similarity threshold)
- Handles position sections (QB, RB, WR, TE)
- Extracts yards/points stats and analysis details

### HW Scraper Integration (`src/fantasy_pipeline/scraper/integration.py`)
- Integrates web scraper with main pipeline
- Auto-triggers scraping when HW files don't exist
- Handles URL generation for Underdog Network (week-based URLs)
- Provides graceful fallback on scraping failures
- Checks for existing files to prevent redundant scraping

### Base Processor (`src/fantasy_pipeline/core/base_processor.py`)
- Unified processing logic for all data sources
- Handles ranking calculations and standardization
- Preserves pre-existing POS RANK from scraper output

### Data Loading (`src/fantasy_pipeline/data/loader.py`)
- Handles various file formats (CSV, Excel)
- Auto-detects CSV headers (fixed bug with row misidentification)
- Provides consistent data loading interface

### Player Key Management
- `player_key_dict.json`: Master dictionary for player name standardization
- `src/fantasy_pipeline/data/player_utils.py`: Functions for player name cleaning and ID matching
- `scripts/update_player_key.py`: Tools for maintaining player mappings

## Advanced Features

### Value-Based Drafting (VBD)
- Calculates positional value relative to replacement level
- Accounts for league-specific roster requirements
- Applies QB adjustment factor (50% reduction)

### File Management
- Timestamped archiving prevents data loss
- Automated cleanup of processing directories
- Maintains historical data for analysis

### Multi-Format Support
- Handles CSV, Excel, and other common formats
- Flexible data loading with error handling

## Dependencies

- `pandas` - Data manipulation and analysis
- `numpy` - Numerical computations
- `openpyxl` - Excel file support
- `beautifulsoup4` - HTML parsing for web scraping
- `requests` - HTTP requests for web scraping
- `json` - Player key dictionary management
- `datetime` - Timestamp generation
- `shutil` - File operations

## Troubleshooting

### HW Scraper Issues

**If scraper returns 0 players:**
1. Check URL format in `get_hw_scraper_url()` - should be `week-{N}-fantasy-football-rankings-the-blueprint-2025`
2. Verify CSS selector `div.styles_postLayoutBody__MYNJ_` still targets post body (Next.js class names may change)
3. Check position headers use format "Week {N} {POS} Rankings" (e.g., "Week 8 RB Rankings")
4. Verify player entry format: "Player Name - XX.X yards/points in Underdog Pick'em"
5. Note: Uses curly quote `'` (U+2019) not straight apostrophe `'`

**To force re-scraping:**
```python
from fantasy_pipeline.scraper import auto_scrape_if_needed
auto_scrape_if_needed(week=8, league_type='weekly', force=True)
```

**Manual debugging:**
```python
from fantasy_pipeline.scraper import scrape_fantasy_rankings
url = "https://underdognetwork.com/football/fantasy-rankings/week-8-fantasy-football-rankings-the-blueprint-2025"
df = scrape_fantasy_rankings(url)
print(f"Scraped {len(df)} players")
```

### Other Common Issues

- **Column Count Mismatches**: Data source file format changed - update `COLUMN_MAPPINGS` in `config.py`
- **Missing Player IDs**: Add name variations to `player_key_dict.json` using `scripts/update_player_key.py`
- **File Not Found**: Check file prefixes in `FILE_MAPPINGS` match actual filenames in update folder

## Notes

- **Weekly/ROS Rankings**: HW rankings are automatically scraped - no manual download needed
- **Redraft/Bestball Rankings**: All sources require manual file downloads to update folder
- Ensure player key dictionary is updated when new players are added
- Place new ranking files in the `update/` directory before processing
- The system preserves all historical data in timestamped archive folders
- VBD calculations can be adjusted by modifying baseline values in the code
- Processing typically takes 30-60 seconds depending on file sizes (plus scraping time if needed)
- Scraping adds 3-5 seconds for HW rankings fetch and parsing

## Testing

Test the pipeline with real data:

```bash
# Test weekly rankings (Week 2)
uv run ff-rankings --league-type weekly --week 2

# Test ROS rankings
uv run ff-rankings --league-type ros

# Test redraft rankings
uv run ff-rankings --league-type redraft
```

Expected output:
- Consolidated rankings file in `data/rankings current/latest/`
- Archived source files in `raw archive/`
- Multiple ranking sources integrated
- Auto-scraped HW rankings (for weekly/ROS)

## Example Output

### Redraft Rankings
```
PLAYER NAME         | POS | ADP ROUND | fpts_RK | fantasypros_RK | VBD
Christian McCaffrey | RB  | 1         | 2       | 1              | 67.2
Ja'Marr Chase       | WR  | 1         | 5       | 3              | 52.1
```

### Weekly Rankings
```
PLAYER NAME    | POS | avg_POS RANK | fpts_POS RANK | fp_POS RANK | HPPR
Trey McBride   | TE  | 1.0          | 1             | 1           | 9.1
Lamar Jackson  | QB  | 1.5          | 3             | 1           | -
Ja'Marr Chase  | WR  | 1.5          | 3             | 1           | 3.6
``` 