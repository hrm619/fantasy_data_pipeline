# Weekly Rankings Setup Guide

## Overview
The weekly rankings option has been successfully added to the fantasy data pipeline. This document outlines what you need to configure to complete the setup.

## What's Been Implemented

### ✅ Completed Features
1. **Configuration Structure** - Added weekly league type to `src/config.py`
2. **Processor Logic** - Updated `src/base_processor.py` to handle weekly-specific processing
3. **Rankings Logic** - Modified `src/rankings_processor.py` to exclude ADP and focus on POS RANK
4. **CLI Interface** - Updated `app/rankings.py` to include weekly as a choice option

### 🔧 Key Differences for Weekly Rankings
- **No ADP Processing** - Weekly rankings exclude all ADP-related data and calculations
- **POS RANK Focus** - Only positional rankings are calculated and averaged
- **No Overall RK** - Skips overall ranking calculations, focusing on position-based rankings
- **Different Sorting** - Sorts by `avg_POS RANK` instead of ADP

## What You Need to Configure

### 1. File Mappings in `src/config.py`
**Location**: `get_weekly_file_mappings()` function in `src/config.py` (around line 149)

**Current Function**:
```python
def get_weekly_file_mappings(week: int) -> dict:
    return {
        "fpts": ["The GURU"],  # List of file prefixes for multiple position files
        "fp": "FantasyPros_",  # Will be combined with week info  
        "jj": f"Week{week}_RankingsTiers",  # Week2_RankingsTiers, Week3_RankingsTiers, etc.
        "ds": "weekly-rankings",  # Static file prefix - update if needed
        "hw": "tableDownload",  # Static file prefix - update if needed
        "pff": f"Week-{week}-rankings",  # Week-2-rankings, Week-3-rankings, etc.
    }
```

**What to do**: Update the file prefixes in the `get_weekly_file_mappings()` function. You can use three approaches:

1. **Static prefixes** (for single files that don't change by week):
   - `"hw": "tableDownload"` - if the file is always named the same regardless of week

2. **Dynamic prefixes with f-strings** (for files that include week numbers):
   - `f"Week{week}_RankingsTiers"` - will become "Week2_RankingsTiers" for week 2, "Week3_RankingsTiers" for week 3, etc.
   - `f"Week-{week}-rankings"` - will become "Week-2-rankings" for week 2, "Week-3-rankings" for week 3, etc.

3. **Multiple file prefixes** (for sources with multiple files per position):
   - `["The GURU"]` - will load ALL files that start with "The GURU" and concatenate them
   - `["QB_Rankings", "RB_Rankings", "WR_Rankings", "TE_Rankings"]` - for position-specific files

**Examples**:
- **Single file**: If your weekly FantasyPros file is "FantasyPros_Week2_Rankings.csv", use `f"FantasyPros_Week{week}_Rankings"`
- **Multiple files**: If you have "The_GURU_QB.csv", "The_GURU_RB.csv", "The_GURU_WR.csv", "The_GURU_TE.csv", use `["The_GURU"]`
- **Position-specific**: If you have separate files like "Week2_QB_Rankings.csv", "Week2_RB_Rankings.csv", etc., use `[f"Week{week}_QB_Rankings", f"Week{week}_RB_Rankings", f"Week{week}_WR_Rankings", f"Week{week}_TE_Rankings"]`

### 2. Column Mappings (Optional)
If your weekly ranking files have different column structures than the existing sources, you may need to add weekly-specific column mappings to the `COLUMN_MAPPINGS` dictionary in `src/config.py`.

## How to Use

### Command Line Usage
```bash
# Process weekly rankings (week parameter is required)
python app/rankings.py --league-type weekly --week 2

# Process different weeks
python app/rankings.py --league-type weekly --week 3
python app/rankings.py --league-type weekly --week 4

# With custom paths
python app/rankings.py --league-type weekly --week 2 --data-path /path/to/weekly/files --base-data-dir /path/to/output
```

### Programmatic Usage
```python
from src.rankings_processor import process_weekly_rankings

# Process weekly rankings (week parameter is required)
output_file = process_weekly_rankings(
    week=2,
    data_path='data/rankings current/update/',
    verbose=True
)

# Process different weeks
output_file = process_weekly_rankings(week=3, verbose=True)
output_file = process_weekly_rankings(week=4, verbose=True)
```

## Expected Output

### Weekly Rankings Will Include:
- **Base Info**: PLAYER ID, PLAYER NAME, POS, TEAM
- **Positional Rankings**: Individual source POS RANK columns (e.g., `fpts_POS RANK`, `fp_POS RANK`)
- **Average POS RANK**: `avg_POS RANK` calculated from all source positional rankings
- **Tiers**: TIER columns from sources that provide them
- **ECR Data**: ECR and POS ECR from FantasyPros if available

### Weekly Rankings Will NOT Include:
- **Overall Rankings**: No RK columns or avg_RK calculations
- **ADP Data**: No ADP, ADP ROUND, or POS ADP columns
- **ADP-based Calculations**: No ADP Delta or ECR ADP Delta

## File Structure
The weekly rankings will be saved with week-specific naming:
- Format: `df_rank_clean_{timestamp}_weekly_week{X}.csv` (e.g., `df_rank_clean_20250913_1430_weekly_week2.csv`)
- Location: `data/rankings current/latest/`

## Testing the Implementation
1. Add your weekly file mappings to `src/config.py`
2. Place your weekly ranking files in `data/rankings current/update/`
3. Run: `python app/rankings.py --league-type weekly --week 2 --verbose`
4. Check the output file in `data/rankings current/latest/`

## Troubleshooting

### Common Issues:
1. **File Not Found**: Ensure your file prefixes in `FILE_MAPPINGS['weekly']` match your actual file names
2. **No Data**: Check that your weekly files contain the expected columns (PLAYER NAME, POS, TEAM, etc.)
3. **Empty Output**: Verify that players have valid POS RANK data in at least one source

### Debug Mode:
Run with `--verbose` flag to see detailed processing information and identify where issues occur.

## Next Steps
1. Update the file mappings in `src/config.py` with your actual weekly file prefixes
2. Test with a small set of weekly ranking files
3. Verify the output contains the expected positional ranking data
4. Optionally add weekly-specific column mappings if needed

The weekly rankings pipeline is now ready for use once you configure the file mappings!
