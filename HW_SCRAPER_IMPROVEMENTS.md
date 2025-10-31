# HW Scraper Name Matching Improvements

## Problem Summary

The Hayden Winks scraper was missing player names like:
- **James Cook III** (suffix matching)
- **Ja'Marr Chase** (apostrophe variations)
- **Amon-Ra St. Brown** (hyphen and period variations)

## Root Causes Identified

1. **Fuzzy matching threshold too strict (0.85)**: Names with suffixes like "III" scored 0.833, failing to match
2. **No name normalization**: Special characters (hyphens, apostrophes, periods) caused exact matches to fail
3. **Suboptimal fuzzy matching**: Used `difflib.SequenceMatcher` instead of the faster/better `rapidfuzz` library

## Changes Made

### 1. Added Name Normalization Function (`hw_scraper.py`)

```python
def normalize_player_name(name):
    """
    Normalize player name for matching by removing special characters.

    Examples:
    - "Amon-Ra St. Brown" -> "amonra st brown"
    - "Ja'Marr Chase" -> "jamarr chase"
    - "D'Andre Swift" -> "dandre swift"
    """
```

This removes periods, apostrophes, hyphens, and normalizes spacing, making matches more reliable.

### 2. Improved Matching Strategy (3-tier approach)

```python
def match_player_name(scraped_name, player_key):
    # Strategy 1: Exact match (case-insensitive, preserves formatting)
    # Strategy 2: Normalized exact match (removes special chars)
    # Strategy 3: Fuzzy matching with 0.80 threshold (lowered from 0.85)
```

**Benefits:**
- Fast exact matching for most cases (Strategies 1 & 2)
- Fuzzy fallback handles suffixes and variations (Strategy 3)
- Lowered threshold from 0.85 → 0.80 catches suffix variations like "James Cook" vs "James Cook III"

### 3. Added `rapidfuzz` Library

- **Added to `pyproject.toml`**: `rapidfuzz>=3.0.0`
- **Graceful fallback**: Uses `difflib.SequenceMatcher` if rapidfuzz not available
- **Performance benefit**: rapidfuzz is 10-100x faster and more accurate

## Testing Results

Tested with problematic player names:

| Player Name | Normalized | Match Result | Player ID |
|-------------|------------|--------------|-----------|
| James Cook | james cook | ✓ MATCHED | CookJa01 |
| James Cook III | james cook iii | ✓ MATCHED | CookJa01 |
| Ja'Marr Chase | jamarr chase | ✓ MATCHED | ChasJa00 |
| JaMarr Chase | jamarr chase | ✓ MATCHED | ChasJa00 |
| Amon-Ra St. Brown | amonra st brown | ✓ MATCHED | StxxAm00 |
| AmonRa St Brown | amonra st brown | ✓ MATCHED | StxxAm00 |
| D'Andre Swift | dandre swift | ✓ MATCHED | SwifDA00 |

**Match Rate: 7/7 (100%)** ✓

## How to Apply Changes

1. **Install rapidfuzz** (recommended for best performance):
   ```bash
   uv pip install -e .
   ```

2. **Re-run the scraper** to fetch HW rankings:
   ```bash
   uv run ff-rankings --league-type weekly --week 8
   ```

   The scraper will automatically use the improved matching logic.

3. **Verify results**: Check the output CSV for previously missing players.

## Files Modified

- ✏️ `src/fantasy_pipeline/scraper/hw_scraper.py` - Added normalization and improved matching
- ✏️ `pyproject.toml` - Added `rapidfuzz>=3.0.0` dependency
- ✏️ `CLAUDE.md` - Fixed dependency name (python-rapidfuzz → rapidfuzz)

## Future Recommendations

1. **Add unit tests** for the matching logic in `tests/test_hw_scraper.py`
2. **Log unmatched players** to help identify missing player key entries
3. **Consider creating a name variation generator** for the player key dictionary
4. **Monitor match rates** in verbose mode to catch new problematic patterns

## Questions?

If players are still being missed:
1. Check if they exist in `player_key_dict.json` with variations
2. Run with verbose mode: `uv run ff-rankings --verbose`
3. Inspect the scraped CSV to see what names are extracted vs matched
