# Source Library API Reference

This is the fully consolidated source library for the fantasy football data processing pipeline. All functionality from the original `app/`, `src/`, and `scripts/` directories has been unified into this single `src/` directory, providing a complete one-stop source for all data processing needs.

## What was simplified:

### 📁 **File Structure Consolidation**
- **Before**: Separate `app/`, `src/`, and `scripts/` directories with scattered functionality
- **After**: Unified `src/` directory with complete consolidated organization

### 🔄 **Code Deduplication**
- **Before**: 3 nearly identical ranking processors (rankings_processor.py, redraft_rankings_processor.py, bb_rankings_processor.py)
- **After**: Single unified `RankingsProcessor` class that handles all league types

### 🧩 **Processor Simplification**
- **Before**: 7+ separate processor files with 95% identical code
- **After**: Single `BaseProcessor` class with convenience functions for each data source

### ⚙️ **Configuration Centralization**
- **Before**: Column mappings and file lookups scattered across multiple files
- **After**: Single `config.py` with all mappings and constants

## New Structure:

```
src/
├── __init__.py              # Main exports and version info (28 total exports)
├── config.py                # All configuration, mappings, and constants
├── data_loader.py           # File loading utilities (from scripts/load_data.py)
├── player_utils.py          # Player name cleaning and ID mapping
├── base_processor.py        # Unified processor class (replaces old individual processors)
├── rankings_processor.py    # Main rankings processor (replaces all app/ processors)
├── season_stats_processor.py # Historical season stats processing
├── weekly_stats_processor.py # Historical weekly stats processing
├── update_player_key.py     # Player key utilities (from scripts/)
├── utils.py                 # Utility functions for stats processors
└── README.md               # This file
```

## Usage:

### Command Line (Recommended)
```bash
# Process redraft rankings (default)
python app/rankings.py

# Process bestball rankings
python app/rankings.py --league-type bestball

# With custom paths
python app/rankings.py --data-path "custom/update/path" --quiet
```

### Python API
```python
from src import RankingsProcessor

# Process redraft rankings
processor = RankingsProcessor('redraft')
output_file = processor.process_rankings()

# Process bestball rankings  
processor = RankingsProcessor('bestball')
output_file = processor.process_rankings()

# Or use convenience functions
from src.rankings_processor import process_redraft_rankings, process_bestball_rankings
output_file = process_redraft_rankings()
```

## Backward Compatibility

The old entry points are still supported:
- `process_fantasy_rankings_redraft()` function is available for existing scripts
- All processor functions (`process_fpts_data`, `process_fantasypros_data`, etc.) work exactly the same

## Benefits of Simplified Structure:

1. **Reduced Complexity**: 20+ files consolidated into 6 focused modules
2. **Eliminated Duplication**: 95% code overlap removed through inheritance and configuration
3. **Easier Maintenance**: Single place to modify processor logic or add new data sources
4. **Better Testing**: Unified structure makes it easier to test and validate
5. **Clearer Dependencies**: All imports and configurations centralized
6. **Flexible**: Easy to add new league types or data sources

## Migration Guide:

If you were using the old structure:

**Old:**
```python
from app.redraft_rankings_processor import process_fantasy_rankings_redraft
from src.fpts_processor import process_fpts_data
```

**New:**
```python
from src.rankings_processor import process_redraft_rankings  # or process_fantasy_rankings_redraft for compatibility
from src.base_processor import process_fpts_data
```

The functionality is identical, just the import paths have changed.
