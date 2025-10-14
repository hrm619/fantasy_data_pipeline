# Fantasy Football Data Pipeline

A comprehensive Python pipeline for processing fantasy football rankings data from multiple sources, calculating advanced metrics like Value-Based Drafting (VBD), and managing data workflows.

## Features

- **Multi-Source Data Processing**: Integrates rankings from FPTS, FantasyPros, JJ Zachariason, DraftShark, Hayden Winks, and PFF
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

1. **Input**: Place new ranking files in `data/rankings current/update/`
2. **Archive Management**: Existing files in `latest/` are moved to `agg archive/`
3. **Processing**: Rankings are processed, cleaned, and consolidated
4. **Output**: Final rankings saved to `data/rankings current/latest/`
5. **Cleanup**: Source files moved from `update/` to `raw archive/`

## Data Structure

### Input Sources

The pipeline integrates data from six primary ranking sources:

- **FPTS (Fantasy Points)**: Fantasy points projections with detailed stats
- **FantasyPros**: Consensus expert rankings (ECR)
- **JJ Zachariason**: Late Round Podcast rankings and tiers
- **DraftShark**: Rankings with projections (floor, ceiling, consensus)
- **Hayden Winks**: Expert rankings with HPPR projections
- **PFF (Pro Football Focus)**: Rankings and projections

For complete data source URLs, export instructions, and file naming conventions, see **[DATA_SOURCES.md](DATA_SOURCES.md)**.

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
│   ├── rankings_processor.py  # Main processing pipeline
│   └── example_usage.py      # Usage examples
├── scripts/
│   ├── load_data.py          # Data loading utilities
│   ├── clean_cols.py         # Column standardization
│   └── update_player_key.py  # Player key management
├── notebooks/
│   ├── ff-data.ipynb         # Data analysis
│   ├── ff-player-key.ipynb   # Player key exploration
│   └── ff-rankings.ipynb     # Rankings analysis
└── player_key_dict.json     # Player name standardization
```

## Key Components

### Rankings Processor (`src/rankings_processor.py`)
- Loads and standardizes data from multiple sources
- Calculates VBD metrics with position-specific baselines
- Creates consolidated rankings with multiple scoring systems
- Manages automated file archiving workflow

### Data Loading (`scripts/load_data.py`)
- Handles various file formats (CSV, Excel)
- Provides consistent data loading interface

### Column Standardization (`scripts/clean_cols.py`)
- Maps column names across different data sources
- Ensures consistent field naming

### Player Key Management
- `player_key_dict.json`: Master dictionary for player name standardization
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
- `json` - Player key dictionary management
- `datetime` - Timestamp generation
- `shutil` - File operations

## Notes

- Ensure player key dictionary is updated when new players are added
- Place new ranking files in the `update/` directory before processing
- The system preserves all historical data in timestamped archive folders
- VBD calculations can be adjusted by modifying baseline values in the code
- Processing typically takes 30-60 seconds depending on file sizes

## Example Output

The processor generates consolidated rankings like:
```
PLAYER NAME    | POS | ADP ROUND | fpts_RK | fantasypros_RK | VBD
Christian McCaffrey | RB  | 1        | 2       | 1              | 67.2
Ja'Marr Chase      | WR  | 1        | 5       | 3              | 52.1
``` 