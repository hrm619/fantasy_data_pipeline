# Fantasy Football Data Processors

This directory contains modular data processors for the fantasy football rankings pipeline. Each processor handles a specific data source and transformation.

## 🏗️ Architecture

The code has been refactored into specialized modules for better maintainability and reusability:

```
src/
├── __init__.py                 # Package initialization and exports
├── fpts_processor.py           # FPTS/VBD calculations
├── fantasypros_processor.py    # FantasyPros rankings processing
├── draftshark_adp_processor.py # DraftShark ADP processing
├── draftshark_rank_processor.py # DraftShark rankings processing
├── utils.py                    # Common utility functions
├── test_processors.py          # Test suite for all processors
└── README.md                   # This file
```

## 📊 Data Processors

### 1. FPTS Processor (`fpts_processor.py`)

**Purpose**: Handles Value-Based Drafting (VBD) calculations for fantasy points data.

**Key Features**:
- Position-specific baseline calculations (QB: 6, RB: 24, WR: 30, TE: 12)
- VBD score calculation relative to replacement level
- QB adjustment (50% VBD reduction to account for position scarcity)
- Overall and positional ranking generation

**Functions**:
- `process_fpts_data(df, verbose=True)`: Main processing function
- `get_baseline_info(df)`: Returns baseline player information by position

### 2. FantasyPros Processor (`fantasypros_processor.py`)

**Purpose**: Processes FantasyPros ranking data with position standardization.

**Key Features**:
- Cleans position data (removes numbers like "WR1" → "WR")
- Calculates positional rankings based on overall ranks
- Provides position-based summary statistics

**Functions**:
- `process_fantasypros_data(df, verbose=True)`: Main processing function
- `get_position_summary(df)`: Returns summary statistics by position

### 3. DraftShark ADP Processor (`draftshark_adp_processor.py`)

**Purpose**: Handles DraftShark Average Draft Position (ADP) data processing.

**Key Features**:
- Converts ADP values to draft round calculations
- Calculates pick position within each round (12-team league assumed)
- Assigns overall ADP rankings
- Provides round-by-round breakdowns

**Functions**:
- `process_draftshark_adp_data(df, verbose=True)`: Main processing function
- `get_adp_summary(df)`: Returns ADP summary statistics
- `calculate_adp_round_pick(adp_rank, league_size=12)`: Utility for round/pick calculations

### 4. DraftShark Rank Processor (`draftshark_rank_processor.py`)

**Purpose**: Processes DraftShark ranking data with rank assignments.

**Key Features**:
- Assigns overall rankings based on data order
- Calculates positional rankings within each position
- Validates ranking data for consistency
- Provides comprehensive ranking summaries

**Functions**:
- `process_draftshark_rank_data(df, verbose=True)`: Main processing function
- `get_ranking_summary(df)`: Returns ranking summary by position
- `validate_rankings(df)`: Validates ranking data integrity

## 🔧 Utilities (`utils.py`)

Common utility functions used across processors:

- `validate_dataframe(df, required_columns)`: Validates DataFrame structure
- `clean_player_names(df, column_name)`: Cleans player name formatting
- `get_position_breakdown(df, pos_column)`: Generates position summaries
- `filter_main_positions(df, pos_column)`: Filters to main fantasy positions
- `calculate_match_rate(df, column_name)`: Calculates data matching rates
- `print_processing_summary(df, source_name)`: Prints processing summaries
- `safe_numeric_conversion(series, target_type)`: Safely converts data types

## 🧪 Testing

Run the test suite to validate all processors:

```bash
cd src
python test_processors.py
```

The test script creates sample data and validates each processor's functionality.

## 📦 Usage

### Direct Import

```python
from src.fpts_processor import process_fpts_data
from src.fantasypros_processor import process_fantasypros_data
from src.draftshark_adp_processor import process_draftshark_adp_data
from src.draftshark_rank_processor import process_draftshark_rank_data

# Process individual data sources
fpts_data = process_fpts_data(fpts_df, verbose=True)
fantasypros_data = process_fantasypros_data(fp_df, verbose=True)
adp_data = process_draftshark_adp_data(adp_df, verbose=True)
rank_data = process_draftshark_rank_data(rank_df, verbose=True)
```

### Package Import

```python
from src import (
    process_fpts_data,
    process_fantasypros_data,
    process_draftshark_adp_data,
    process_draftshark_rank_data
)
```

## 🔄 Integration

The main `rankings_processor.py` in the `app/` directory has been updated to use these modular processors instead of inline processing code. This provides:

- **Better maintainability**: Each processor can be updated independently
- **Easier testing**: Individual processors can be tested in isolation
- **Code reusability**: Processors can be used in other parts of the pipeline
- **Clear separation of concerns**: Each processor has a single responsibility

## 📈 Benefits

1. **Modularity**: Each data source has its own dedicated processor
2. **Testability**: Individual processors can be tested independently
3. **Maintainability**: Easier to update and debug specific transformations
4. **Reusability**: Processors can be used in other scripts or notebooks
5. **Documentation**: Clear documentation for each processor's purpose and usage
6. **Type Safety**: Proper type hints for better code clarity

## 🚀 Future Enhancements

- Add configuration files for processor settings
- Implement data validation schemas
- Add more comprehensive error handling
- Create additional utility functions for common operations
- Add support for different league sizes in ADP calculations 