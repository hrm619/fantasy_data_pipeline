# Fantasy Football Rankings Processor

A clean, comprehensive Python function that processes fantasy football rankings data from multiple sources and creates a consolidated ranking file.

## Overview

The `process_fantasy_rankings()` function takes the complex notebook logic from `ff-rankings.ipynb` and packages it into a reusable, well-documented function that:

1. **Loads ranking files** from multiple sources (FPTS, FantasyPros, JJ Zachariason, DraftShark, etc.)
2. **Standardizes data** with consistent column names and player IDs
3. **Calculates advanced metrics** like Value-Based Drafting (VBD) and positional rankings
4. **Creates consolidated rankings** combining all sources
5. **Outputs clean CSV file** with timestamp for tracking

## Features

- **Verbose logging** - Detailed progress information during processing
- **Error handling** - Clear error messages for missing files or data issues
- **Flexible paths** - Configurable input and output directories
- **Type hints** - Full type annotations for better code clarity
- **Comprehensive documentation** - Detailed docstrings and comments

## Usage

### Basic Usage

```python
from src.rankings_processor import process_fantasy_rankings

# Process rankings with default settings
output_file = process_fantasy_rankings()
print(f"Rankings saved to: {output_file}")
```

### Custom Configuration

```python
# Process with custom paths and settings
output_file = process_fantasy_rankings(
    data_path="../data/rankings current/update/",
    player_key_path="../player_key_dict.json",
    output_dir="./output/",
    verbose=True
)
```

### Command Line Usage

```bash
# Run from the src directory
python rankings_processor.py

# Or run the example script
python example_usage.py
```

## Function Parameters

- `data_path` (str): Path to directory containing ranking files
- `player_key_path` (str): Path to player key dictionary JSON file  
- `output_dir` (str): Directory to save output CSV file
- `verbose` (bool): Whether to print detailed progress information

## Data Processing Steps

The function performs these key processing steps:

### 1. File Loading & Validation
- Scans the update directory for ranking files
- Maps files to data sources based on filename patterns
- Validates that required files are present

### 2. Data Standardization
- Applies consistent column names using `scripts/clean_cols.py`
- Adds player IDs using the player key dictionary
- Reports match rates for each data source

### 3. FPTS Processing with VBD
- Calculates Value-Based Drafting (VBD) metrics
- Uses position-specific baselines (QB: 6, RB: 24, WR: 30, TE: 12)
- Applies QB adjustment (50% VBD reduction)
- Creates overall and positional rankings

### 4. Source-Specific Processing
- **FantasyPros**: Cleans position codes and calculates positional ranks
- **DraftShark ADP**: Parses ADP format and creates round/pick columns
- **DraftShark Rankings**: Ranks by 3D Value with positional breakdowns
- **Other sources**: Preserves existing rankings and tiers

### 5. Consolidation & Output
- Merges all ranking sources on player ID
- Organizes columns logically (player info → ADP → rankings → tiers)
- Filters to main positions (QB, RB, WR, TE)
- Saves timestamped CSV file

## Output File Structure

The generated CSV contains:

- **Player Info**: ID, Name, Position
- **ADP Data**: Round, Pick, Overall Rank
- **Rankings**: Overall and positional ranks from each source
- **Tiers**: Tier assignments where available

Example columns:
```
PLAYER ID, PLAYER NAME, POS, ADP ROUND, ADP RANK, 
fpts_RK, fantasypros_RK, jj_RK, draftshark_rank_RK,
fpts_POS RANK, fantasypros_POS RANK, jj_POS RANK,
fpts_TIER, fantasypros_TIER, jj_TIER
```

## Requirements

- Python 3.7+
- pandas
- numpy
- Existing project structure with:
  - `scripts/load_data.py`
  - `scripts/clean_cols.py`
  - `player_key_dict.json`
  - Data files in `../data/rankings current/update/`

## Error Handling

The function includes comprehensive error handling for:
- Missing data directories or files
- Invalid file formats
- Player key dictionary issues
- Data processing errors

All errors include descriptive messages to help with troubleshooting.

## Performance

The function is designed to be efficient and provides progress feedback:
- File loading progress
- Player matching statistics
- Processing step completion
- Final output summary

Typical processing time: 10-30 seconds depending on data size. 