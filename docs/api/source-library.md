# `fantasy_pipeline` API Reference

The package lives in `src/fantasy_pipeline/`. Public API is exported from the package root;
deeper internals are importable from the subpackages.

```
src/fantasy_pipeline/
├── __init__.py          # public API exports
├── config.py            # COLUMN_MAPPINGS, FILE_MAPPINGS, CURRENT_SEASON, paths
├── core/
│   ├── base_processor.py        # BaseProcessor (unified per-source processing)
│   ├── rankings_processor.py    # RankingsProcessor (orchestrator)
│   ├── season_stats_processor.py
│   ├── weekly_stats_processor.py
│   └── stats_aggregator.py
├── data/
│   ├── loader.py        # load_data (CSV/Excel, header detection)
│   └── player_utils.py  # name cleaning + player-ID mapping
├── scraper/
│   ├── hw_scraper.py    # Hayden Winks article scraper (weekly/ROS)
│   ├── integration.py   # auto_scrape_if_needed (pipeline hook)
│   ├── fetch_rankings.py# fetch_* source fetchers + session validation
│   └── auth.py          # saved-session login / storage state
└── cli/
    ├── rankings.py      # ff-rankings entry point
    └── stats.py         # ff-stats entry point
```

## Public API

```python
from fantasy_pipeline import (
    RankingsProcessor,
    process_redraft_rankings,
    process_weekly_rankings,
    load_player_key_mapping,
    add_player_ids,
)
```

### `RankingsProcessor`

The orchestrator. One instance per league type.

```python
RankingsProcessor(league_type: str, week: int | None = None)
```
- `league_type`: `"redraft" | "bestball" | "weekly" | "ros"`.
- `week`: required for `weekly`/`ros`.

```python
process_rankings(
    data_path: str = None,          # the update/ folder (default: standard layout)
    player_key_path: str = None,    # player_key_dict.json
    base_data_dir: str = None,      # parent of latest/update/archive
    week: int = None,
    verbose: bool = True,
    return_dataframe: bool = False,
) -> str | pandas.DataFrame
```
- `return_dataframe=False` (default): writes the consolidated CSV to `latest/` and returns its **path**.
- `return_dataframe=True`: returns the consolidated **DataFrame** directly (the integration seam the
  sibling `fantasy-data` repo consumes — treat its columns as a downstream contract).

## Data utilities (`fantasy_pipeline.data`)

```python
from fantasy_pipeline.data import load_data, clean_player_names, load_player_key_mapping, add_player_ids

df = load_data(filepath, header_row=None, sheet_name=None)   # CSV/Excel, auto header/sheet detection
player_key_dict, name_to_key = load_player_key_mapping("player_key_dict.json")
df = add_player_ids(df, name_to_key, verbose=True)
```

## Source fetchers (`fantasy_pipeline.scraper.fetch_rankings`)

Each writes a pipeline-ready file into the given directory (see [data-sources.md](../data-sources.md)).

```python
fetch_fantasypros_adp(output_dir, year=CURRENT_SEASON, min_players=200)
fetch_fantasypros_rankings(output_dir, year=CURRENT_SEASON, scoring="ppr", min_players=200)
fetch_draftsharks(output_dir, min_players=150)                       # headless (Playwright)
fetch_pff(output_dir, year=CURRENT_SEASON, min_players=200)          # saved session
fetch_fpts(output_dir, year=CURRENT_SEASON, min_players=90, rankings_url=...)   # saved session
fetch_jj(output_dir, post_url=None, year=CURRENT_SEASON, min_players=150)       # Patreon API
```

Session validation / auto-login:
```python
validate_session(source) -> bool          # cheap live "still logged in?" probe
ensure_session(source, auto_login=True)   # probe; open login window if expired, then re-validate
```

## Saved-session auth (`fantasy_pipeline.scraper.auth`)

```python
from fantasy_pipeline.scraper.auth import login, load_storage_state, storage_state_path

login(source, timeout_minutes=10)     # headed one-time login → ~/.fantasy_pipeline/auth/<source>.json
load_storage_state(source) -> str     # path for browser.new_context(storage_state=...); raises if absent
```
Override the secrets dir with the `FANTASY_PIPELINE_AUTH_DIR` env var.

## HW scraper hook (`fantasy_pipeline.scraper`)

```python
from fantasy_pipeline.scraper import auto_scrape_if_needed, scrape_fantasy_rankings
```
`auto_scrape_if_needed` is called by `RankingsProcessor` for weekly/ROS to fetch Hayden Winks when the
file is absent. `scrape_fantasy_rankings(url)` runs the article scraper standalone.

## Configuration (`fantasy_pipeline.config`)

- `COLUMN_MAPPINGS` / `WEEKLY_COLUMN_MAPPINGS` / `ROS_COLUMN_MAPPINGS` — per-source positional schemas.
- `FILE_MAPPINGS` + `get_weekly_file_mappings(week)` / `get_ros_file_mappings(week)` — filename prefixes.
- `CURRENT_SEASON` — single source of truth for season-specific filenames/URLs.
- `DEFAULT_PATHS` — the `data/rankings current/` layout.

Adding a source is config-only: add a `COLUMN_MAPPINGS` entry and a `FILE_MAPPINGS` prefix;
`BaseProcessor` handles the rest. See [`CLAUDE.md`](../../CLAUDE.md) for the design patterns.
