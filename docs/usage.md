# Usage

Running the pipeline end to end: install, gather source files, and consolidate them into a
single ranked file. For where the data comes from, see [data-sources.md](data-sources.md).

## Install

```bash
uv pip install -e .            # core
uv pip install -e ".[headless]" && playwright install chromium   # for fetch-ds / paywalled fetchers
uv run ff-rankings --help
```

## The two steps

Sourcing and consolidation are **separate**. Fetchers drop files into
`data/rankings current/update/`; consolidation reads `update/`, writes the combined file to
`latest/`, and archives the inputs.

### 1. Gather sources

```bash
# Everything at once (redraft): fetch all six automated sources, then consolidate.
ff-rankings refresh-all --auto-login
```
`refresh-all` runs each fetcher independently — one failure (e.g. an expired session) is reported
but doesn't stop the others. Flags: `--no-consolidate` (fetch only), `--strict` (abort consolidation
if any fetch failed), `--auto-login`, `--year`, `--data-path`, `--base-data-dir`, `--quiet`.

Or fetch sources individually:
```bash
ff-rankings fetch-fp         # free
ff-rankings login ds         # one-time; covers BOTH fetch-ds and fetch-adp
ff-rankings fetch-ds
ff-rankings fetch-adp --auto-login   # DraftSharks Sleeper 12-team half-PPR ADP
ff-rankings login pff        # one-time per paywalled source
ff-rankings fetch-pff --auto-login
ff-rankings fetch-fpts --auto-login
ff-rankings fetch-jj --auto-login
```
Redraft also needs the manual Hayden Winks file (`tableDownload.csv`) in `update/` — see
[data-sources.md](data-sources.md).

### 2. Consolidate

```bash
ff-rankings --league-type redraft       # default; also: bestball, weekly, ros
```
Output: `data/rankings current/latest/df_rank_clean_<timestamp>_<league>.csv`. Previous outputs are
moved to `agg archive/`, and the consumed `update/` files to `raw archive/`, both timestamped.

## League types

| Type | Command | Notes |
|------|---------|-------|
| `redraft` | `ff-rankings --league-type redraft` | Default. ADP + overall RK + VBD. Needs all 7 sources. |
| `bestball` | `ff-rankings --league-type bestball` | Like redraft; different `jj`/`adp` file prefixes. |
| `weekly` | `ff-rankings --league-type weekly --week N` | Positional rankings only (no ADP/overall RK). HW auto-scraped. |
| `ros` | `ff-rankings --league-type ros --week N` | Rest-of-season; positional focus. HW auto-scraped. |

`--week` is required for `weekly` and `ros`. For those types the pipeline auto-scrapes Hayden Winks
from Underdog Network if `hw-week{N}.csv` isn't already present (weekly and ROS share this filename).

Useful flags: `--data-path` (the `update/` folder), `--base-data-dir` (parent of latest/update/archive),
`--player-key-path`, `--quiet`, `--verbose`.

## Programmatic use

```python
from fantasy_pipeline import RankingsProcessor

# Write the combined CSV and return its path:
path = RankingsProcessor("redraft").process_rankings(verbose=True)

# Or get the consolidated DataFrame directly (the seam the sibling `fantasy-data` repo uses):
df = RankingsProcessor("redraft").process_rankings(return_dataframe=True)
```
See [api/source-library.md](api/source-library.md) for the full package API.

## Troubleshooting

- **"No file found for key '…'":** a required source file isn't in `update/` (wrong prefix, or a
  manual source like HW redraft is missing). Check prefixes against `FILE_MAPPINGS`.
- **"column count mismatch" / crash on `PLAYER NAME`:** a source file's column count doesn't match its
  `COLUMN_MAPPINGS` entry. Re-fetch, or check the file's layout.
- **Fetch fails with a session/timeout error:** the paywalled session expired — re-run
  `ff-rankings login <source>`, or use `--auto-login`.
- **`fetch-ds` / paywalled fetch errors about Playwright:** install the extra —
  `uv pip install -e ".[headless]"` then `playwright install chromium`.
