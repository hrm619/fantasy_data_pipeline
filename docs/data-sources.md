# Ranking Data Sources

How the pipeline gets its source files, which are automated, and how they map into
processing. This is the source-of-truth for sources; deep architecture lives in the repo
root [`CLAUDE.md`](../CLAUDE.md) and the automation roadmap in [`SCRAPER-PLAN.md`](../SCRAPER-PLAN.md).

## How sourcing works

The pipeline reads source files from `data/rankings current/update/` and matches each to a
source by **filename prefix** (`FILE_MAPPINGS` in `src/fantasy_pipeline/config.py`). It then
standardizes columns **positionally** — a file must have the same column count and order as
that source's `COLUMN_MAPPINGS` entry, or it's skipped. So every fetcher writes a file with
the exact prefix and column layout the pipeline expects.

```
fetch sources  →  data/rankings current/update/  →  ff-rankings --league-type … (consolidate)
                                                  →  data/rankings current/latest/  (combined file)
```

## Source status (redraft)

| Source | Key | Automated? | Command | Auth | Output prefix |
|--------|-----|-----------|---------|------|---------------|
| FantasyPros ADP | `adp` | ✅ Yes | `ff-rankings fetch-adp` | none | `FantasyPros_<season>_Overall_ADP_Rankings.csv` |
| FantasyPros rankings | `fp` | ✅ Yes | `ff-rankings fetch-fp` | none | `FantasyPros_<season>_Draft_ALL_Rankings.csv` |
| DraftSharks | `ds` | ✅ Yes (headless) | `ff-rankings fetch-ds` | none | `rankings-half-ppr.csv` |
| PFF | `pff` | ✅ Yes (saved session) | `ff-rankings fetch-pff` | login | `Draft-rankings-export-<season>.csv` |
| FantasyPoints / Barrett | `fpts` | ✅ Yes (saved session) | `ff-rankings fetch-fpts` | login | `Scott Barrett <season> Redraft Rankings.csv` |
| JJ Zachariason | `jj` | ✅ Yes (Patreon API) | `ff-rankings fetch-jj` | login | `Redraft1QB_<season>.csv` |
| Hayden Winks | `hw` | ⚠️ Manual (redraft) | — | none | `tableDownload.csv` |

**Redraft consolidation requires all seven sources.** Six are automated; **Hayden Winks
redraft is manual** — it has no stable Underdog URL, so download it from Underdog Network
("Table Download" → `tableDownload.csv`) into `update/` yourself. (For **weekly/ROS**, HW is
auto-scraped by the pipeline at run time — see [usage](usage.md).)

## Quick start

```bash
# One command: fetch all six automated sources, then consolidate.
# --auto-login pops a login window only if a paywalled session has expired.
ff-rankings refresh-all --auto-login
```
Keep the manual `tableDownload.csv` (Hayden Winks) in `update/`; if it's absent, `refresh-all`
fetches the six and skips consolidation with instructions.

## Per-source detail

Column layouts below are the positional schema the pipeline renames to (`COLUMN_MAPPINGS[key]`).

### FantasyPros ADP (`adp`) — automated
- **Fetch:** `ff-rankings fetch-adp` (HTTP scrape of the consensus ADP table).
- **Schema (7):** `PLAYER NAME, TEAM, BYE, POS, ADP, MARKET INDEX, RT` (last two emitted blank).

### FantasyPros rankings (`fp`) — automated
- **Fetch:** `ff-rankings fetch-fp [--scoring ppr|half-ppr|standard]` — parses the cheatsheet's
  embedded `ecrData` JSON, so it works year-round.
- **Schema (8):** `ECR, TIER, PLAYER NAME, TEAM, POS, BYE, SOS, ECR VS ADP`.

### DraftSharks (`ds`) — automated (headless)
- **Fetch:** `ff-rankings fetch-ds` — drives the page's own "Export Rankings" button via Playwright.
  Needs the `headless` extra: `uv pip install -e ".[headless]"` then `playwright install chromium`.
- **Schema (14):** `RK, TEAM, PLAYER NAME, POS, G, DS ADP, BYE, SOS, INJURY RISK, FLOOR PROJ,
  CONS PROJ, DS PROJ, CEILING PROJ, 3D VALUE`.

### PFF (`pff`) — automated (saved session)
- **One-time:** `ff-rankings login pff`. **Fetch:** `ff-rankings fetch-pff [--auto-login]`.
- **Schema (9):** `RK, PLAYER NAME, TEAM, POS, POS RANK, BYE, PFF ADP, PROJ, AUCTION`
  (the export has a title row above the real header; the loader handles it).

### FantasyPoints / Scott Barrett (`fpts`) — automated (saved session)
- **One-time:** `ff-rankings login fpts`. **Fetch:** `ff-rankings fetch-fpts [--auto-login]`.
  Selects the "BARRETT'S RANKINGS" board on the redraft page, then "Download as CSV".
- **Schema (7):** `RK, PLAYER NAME, POS, TEAM, BYE, TIER, EXODIA`.

### JJ Zachariason / LateRound (`jj`) — automated (Patreon API)
- **One-time:** `ff-rankings login jj`. **Fetch:** `ff-rankings fetch-jj [--auto-login]` —
  auto-discovers the latest 1QB redraft post in the LateRound collection and downloads its
  attachment via the Patreon JSON API (post HTML is Cloudflare-gated). `--post-url` targets a
  specific post.
- **Schema (6):** `RK, PLAYER NAME, POS, POS RANK, TIER, AUCTION`. The current source dropped the
  Auction column, so the fetcher pads it back to 6.

### Hayden Winks (`hw`) — manual for redraft, automated for weekly/ROS
- **Redraft:** no stable URL → download `tableDownload.csv` from Underdog Network manually.
- **Weekly/ROS:** auto-scraped from the Underdog "Blueprint" article at pipeline run time
  (`scraper/hw_scraper.py`); no manual step.

## Saved-session auth (paywalled sources)

PFF, FantasyPoints, and JJ use a **saved-session** strategy — no passwords stored anywhere:

- `ff-rankings login <pff|fpts|jj>` opens a browser; you log in once (2FA/SSO/OAuth fine). The
  session persists to `~/.fantasy_pipeline/auth/<source>.json` (outside the repo).
- Fetchers reuse it headlessly. Pass **`--auto-login`** to a fetcher or `refresh-all` to have the
  login window appear **only** when the session has actually expired.
- Sessions "slide" — they're re-saved after each successful fetch — and ticking "Remember me" at
  login extends them further. Re-run `login` only when a fetch reports an expired session.

## Bestball / weekly / ROS

- **Bestball** uses the same automated fetchers as redraft, with a couple of different prefixes
  (`jj` → `1QBRankings_`, `adp` → `adp-rankings`).
- **Weekly/ROS** focus on positional rankings (no ADP). HW is auto-scraped; the other sources are
  currently manual for these league types. See [usage](usage.md) for running them.
