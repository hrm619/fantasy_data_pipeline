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
from src import RankingsProcessor

# Process rankings with simplified API
processor = RankingsProcessor('redraft')  # or 'bestball', 'weekly', 'ros'
output_file = processor.process_rankings()

print(f"Rankings saved to: {output_file}")
```

### Command Line Usage

```bash
# Process redraft rankings (default)
uv run app/rankings.py

# Process bestball rankings
uv run app/rankings.py --league-type bestball

# Process weekly rankings (requires week number)
uv run app/rankings.py --league-type weekly --week 7

# Process rest-of-season rankings
uv run app/rankings.py --league-type ros

# With custom paths and quiet mode
uv run app/rankings.py --data-path "custom/update/path" --quiet
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

For **weekly** and **ROS** rankings, the pipeline includes a built-in web scraper for Hayden Winks rankings:

- **Automatic**: Scraper runs automatically if `hw-week{N}.csv` or `hw-ros.csv` doesn't exist
- **Smart**: Skips scraping if file already exists (prevents redundant network calls)
- **Robust**: Continues processing with existing files if scraping fails
- **Player Matching**: Uses fuzzy matching to standardize player names to IDs
- **No Manual Downloads**: Eliminates need to manually download HW rankings from Underdog Network

The scraper is located in `src/hw_scraper/` module.

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
├── data/
│   └── rankings current/
│       ├── update/          # New ranking files to process
│       ├── latest/          # Most recent processed rankings
│       ├── agg archive/     # Historical output files
│       └── raw archive/     # Historical input files
├── src/
│   ├── rankings_processor.py     # Main processing pipeline
│   ├── hw_scraper_integration.py # HW scraper integration
│   ├── hw_scraper/              # Web scraper module
│   │   ├── __init__.py          # Module exports
│   │   └── scraper.py           # Web scraping and player matching
│   ├── base_processor.py         # Unified data processing
│   ├── data_loader.py           # File loading utilities
│   └── player_utils.py          # Player name standardization
├── app/
│   ├── rankings.py              # CLI entry point
│   └── player_stats.py          # Historical stats
├── notebooks/
│   ├── ff-data.ipynb            # Data analysis
│   ├── ff-player-key.ipynb      # Player key exploration
│   └── ff-rankings.ipynb        # Rankings analysis
└── player_key_dict.json         # Player name standardization
```

## Key Components

### Rankings Processor (`src/rankings_processor.py`)
- Loads and standardizes data from multiple sources
- Orchestrates auto-scraping for weekly/ROS rankings
- Calculates VBD metrics with position-specific baselines
- Creates consolidated rankings with multiple scoring systems
- Manages automated file archiving workflow

### HW Scraper Integration (`src/hw_scraper_integration.py`)
- Bridges hw_ranking_scraper with main pipeline
- Auto-triggers scraping when HW files don't exist
- Handles URL generation for Underdog Network
- Provides graceful fallback on scraping failures

### Base Processor (`src/base_processor.py`)
- Unified processing logic for all data sources
- Handles ranking calculations and standardization
- Preserves pre-existing POS RANK from scraper output

### Data Loading (`src/data_loader.py`)
- Handles various file formats (CSV, Excel)
- Auto-detects CSV headers (fixed bug with row misidentification)
- Provides consistent data loading interface

### Player Key Management
- `player_key_dict.json`: Master dictionary for player name standardization
- `src/player_utils.py`: Functions for player name cleaning and ID matching
- `src/update_player_key.py`: Tools for maintaining player mappings

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

## Notes

- **Weekly/ROS Rankings**: HW rankings are automatically scraped - no manual download needed
- **Redraft/Bestball Rankings**: All sources require manual file downloads to update folder
- Ensure player key dictionary is updated when new players are added
- Place new ranking files in the `update/` directory before processing
- The system preserves all historical data in timestamped archive folders
- VBD calculations can be adjusted by modifying baseline values in the code
- Processing typically takes 30-60 seconds depending on file sizes (plus scraping time if needed)

## Example Output

The processor generates consolidated rankings like:
```
PLAYER NAME    | POS | ADP ROUND | fpts_RK | fantasypros_RK | VBD
Christian McCaffrey | RB  | 1        | 2       | 1              | 67.2
Ja'Marr Chase      | WR  | 1        | 5       | 3              | 52.1
``` 