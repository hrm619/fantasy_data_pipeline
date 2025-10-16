# Migration Guide: v0.2.0 → v0.3.0

## 🎉 Project Restructuring Complete

The fantasy football data pipeline has been modernized with a professional Python package structure, clean CLI commands, and improved organization.

---

## Summary of Changes

### ✅ Package Structure
- **New package name**: `fantasy-pipeline` → `fantasy_pipeline` (Python import)
- **Version**: 0.2.0 → 0.3.0
- **Structure**: Reorganized into logical subdirectories

### ✅ Directory Changes

**Before:**
```
src/
├── rankings_processor.py
├── base_processor.py
├── data_loader.py
├── player_utils.py
├── hw_scraper/
└── ...
app/
├── rankings.py
└── player_stats.py
```

**After:**
```
src/
└── fantasy_pipeline/          # Main package
    ├── core/                  # Processing logic
    ├── data/                  # Data utilities
    ├── scraper/               # Web scraping
    └── cli/                   # CLI commands
scripts/
└── update_player_key.py       # Maintenance tools
app/
└── player_stats.py            # Legacy (still works)
```

### ✅ CLI Commands

**Before:**
```bash
uv run app/rankings.py --league-type ros
```

**After:**
```bash
uv run ff-rankings --league-type ros
uv run ff-stats --season 2024
```

### ✅ Python Imports

**Before:**
```python
from src import RankingsProcessor
from src.player_utils import load_player_key_mapping
```

**After:**
```python
from fantasy_pipeline import RankingsProcessor
from fantasy_pipeline.data import load_player_key_mapping
```

---

## Migration Steps

### For Users

1. **Reinstall the package:**
   ```bash
   uv pip install -e .
   ```

2. **Update your scripts:**
   - Change `from src import X` → `from fantasy_pipeline import X`
   - Change `uv run app/rankings.py` → `uv run ff-rankings`

3. **Test your workflow:**
   ```bash
   uv run ff-rankings --help
   uv run python -c "from fantasy_pipeline import RankingsProcessor; print('OK')"
   ```

### For Notebooks

Update notebook imports:
```python
# Old
from src import RankingsProcessor, load_player_key_mapping

# New
from fantasy_pipeline import RankingsProcessor
from fantasy_pipeline.data import load_player_key_mapping
```

---

## Breaking Changes

### ❌ Removed
- `app/rankings.py` - replaced by `ff-rankings` CLI command
- `app/__init__.py` - no longer needed
- Old `src/*.py` files - moved to `src/fantasy_pipeline/`

### ⚠️ Deprecated but Still Works
- `app/player_stats.py` - still functional, but use `ff-stats` CLI command instead

---

## Benefits of New Structure

### 1. **Professional Python Package**
- Follows modern Python packaging standards
- Proper `__init__.py` with exports
- Clear module organization

### 2. **Clean CLI**
- Proper entry points via `pyproject.toml`
- No more `sys.path` manipulation
- Standard command naming: `ff-rankings`, `ff-stats`

### 3. **Better Organization**
- Logical grouping: `core/`, `data/`, `scraper/`, `cli/`
- Easier to navigate and understand
- Scalable for future features

### 4. **Improved Imports**
- Clean relative imports within package
- No path hacking needed
- Better IDE support

---

## New File Locations Reference

| Old Location | New Location |
|-------------|--------------|
| `src/rankings_processor.py` | `src/fantasy_pipeline/core/rankings_processor.py` |
| `src/base_processor.py` | `src/fantasy_pipeline/core/base_processor.py` |
| `src/data_loader.py` | `src/fantasy_pipeline/data/loader.py` |
| `src/player_utils.py` | `src/fantasy_pipeline/data/player_utils.py` |
| `src/hw_scraper/scraper.py` | `src/fantasy_pipeline/scraper/hw_scraper.py` |
| `src/hw_scraper_integration.py` | `src/fantasy_pipeline/scraper/integration.py` |
| `app/rankings.py` | `src/fantasy_pipeline/cli/rankings.py` |
| `src/update_player_key.py` | `scripts/update_player_key.py` |

---

## Testing the Migration

Run these commands to verify everything works:

```bash
# 1. Test package installation
uv pip install -e .

# 2. Test Python imports
uv run python -c "from fantasy_pipeline import RankingsProcessor; print('✅ Imports work')"

# 3. Test CLI commands
uv run ff-rankings --help
uv run ff-stats --help

# 4. Test actual processing (with real data)
uv run ff-rankings --league-type weekly --week 2
uv run ff-rankings --league-type ros
```

### ✅ Migration Verified

All tests passed successfully:
- ✅ Package installation working
- ✅ Python imports functional
- ✅ CLI commands operational
- ✅ Weekly pipeline tested with real data (567 players processed)
- ✅ Auto-scraper working (HW rankings from Underdog Network)
- ✅ Multi-source data processing (8 sources integrated)
- ✅ File archiving functional

---

## Rollback Instructions

If you need to rollback:

```bash
# Revert to previous git commit
git log --oneline  # Find the commit before migration
git reset --hard <commit-hash>

# Reinstall
uv pip install -e .
```

---

## Questions or Issues?

- Check the updated documentation: `CLAUDE.md`, `README.md`
- Review the code organization section in `CLAUDE.md`
- Open an issue if you encounter problems

---

**Migration completed**: October 15, 2024
**Version**: 0.3.0
