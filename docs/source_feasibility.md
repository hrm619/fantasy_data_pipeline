# Source Fetch Feasibility — Investigation Results
**Original investigation:** April 2026 · **Reconciled with shipped code:** 2026-06-15

> **Status update:** This was the original feasibility investigation. Four fetchers have since
> **shipped** and the findings below are corrected to match. The live source of truth for per-source
> status is [`SCRAPER-PLAN.md`](../SCRAPER-PLAN.md); the working backlog is [`TODO.md`](../TODO.md).
> Notably the original investigation was wrong on two counts: DraftShark *is* automatable (via a
> headless browser driving the page's own export), and FantasyPros rankings are automatable
> **year-round** (via the embedded `ecrData` JSON, not the offseason-redirecting table).

## Summary (current)

| Source | Automated? | Method | Auth | Notes |
|--------|-----------|--------|------|-------|
| **FantasyPros ADP** | **✅ Yes** | HTML table scrape (`ff-rankings fetch-adp`) | No | Live page now serves a single 4-col consensus table (~411 players). Per-platform ADP (Sleeper) no longer exposed. |
| **FantasyPros rankings (fp)** | **✅ Yes** | Embedded `ecrData` JSON (`ff-rankings fetch-fp`) | No | Parses the cheatsheet's `var ecrData={...}` blob — works year-round (the `/rankings/*-overall.php` table 302-redirects in the offseason). Defaults to PPR. |
| **DraftShark (ds)** | **✅ Yes** | Headless Playwright export (`ff-rankings fetch-ds`) | No | Drives the page's own client-side "Export Rankings" (Blob download); captures the full ~558-player board in the exact 14-col schema. Requires the `headless` extra + Chromium. |
| **Underdog/HW (hw)** | **Weekly/ROS only** | `hw_scraper.py` (auto-triggered) | No | Existing scraper works for weekly/ROS. No redraft URL pattern → redraft stays manual. |
| **FantasyPoints (fpts)** | **🔒 No** | Manual CSV export | Paid subscription | JS-rendered paywall. Automation candidate via authenticated Playwright (TODO #5). |
| **PFF rankings (pff)** | **🔒 No** | Manual CSV export | Paid subscription | Requires PFF subscription. Automation candidate (TODO #6). |
| **JJ Zachariason (jj)** | **🔒 No** | Manual Patreon download | Patreon paywall | Excel attachment. Hardest auth; may stay manual (TODO #7). |

## Detailed Findings

### FantasyPros ADP (✅ shipped)
- **URL:** `https://www.fantasypros.com/nfl/adp/ppr-overall.php`
- **HTTP 200**, public access.
- **Original investigation found** a wide multi-platform table (`Rank | Player+Team | POS | ESPN |
  Sleeper | CBS | NFL | RTSports`) with ~989 rows. **The live page has since changed** to a single
  4-col consensus table (`Rank | Player | POS | AVG`, ~411 rows); per-platform columns (incl. Sleeper)
  are gone.
- **Shipped approach:** `fetch_fantasypros_adp` parses the consensus table and emits the exact 7-col
  `COLUMN_MAPPINGS['adp']` schema (consensus AVG → ADP; `MARKET INDEX`/`RT` blank). Coverage floor
  `min_players=200` guards layout drift.

### FantasyPros Rankings (✅ shipped — JSON, not table)
- **URL (table):** `https://www.fantasypros.com/nfl/rankings/ppr-overall.php` — **302-redirects** to
  `consensus-cheatsheets.php` in the offseason (no table), which is why the original investigation
  deferred this.
- **Key discovery:** every cheatsheet page embeds the full rankings as a `var ecrData = {...}` JSON
  blob, available **year-round**. The fetcher parses that JSON instead of scraping a table — robust and
  not season-gated.
- **Shipped approach:** `fetch_fantasypros_rankings` → exact 8-col `COLUMN_MAPPINGS['fp']` schema.
  Defaults to PPR; `--scoring {ppr,half-ppr,standard}`.

### DraftShark (✅ shipped — headless, not manual)
- **URL:** `https://www.draftsharks.com/rankings/half-ppr`
- **Original investigation found** only ~25–62 rows in static HTML with malformed names and concluded
  manual export was cleaner. **That was wrong:** the page is a JS-rendered SPA with its own client-side
  CSV export.
- **Shipped approach:** `fetch_draftsharks` uses **Playwright** to drive the page's ungated
  `a.mobile-export-button` "Export Rankings" control (`handleExport`, a Blob download) and captures the
  resulting CSV via `page.expect_download()` — the exact 14-col layout the pipeline consumes, full
  ~558-player board. Mobile UA + viewport (390x844) required (the desktop export control is gated).
  Optional `headless` extra (`uv pip install -e ".[headless]"` + `playwright install chromium`).

### Underdog/HW (weekly/ROS automated, redraft manual)
- **Weekly/ROS:** `hw_scraper.py` + `get_hw_scraper_url()` work, auto-triggered by `auto_scrape_if_needed`.
  URL slug now derives from `CURRENT_SEASON` (e.g. `week-{N}-fantasy-football-rankings-the-blueprint-2025`).
- **Redraft:** no predictable URL → manual `tableDownload.csv`. Stays manual by design.

### FantasyPoints, PFF, JJ (manual — automation candidates)
- All behind paywalls (subscription or Patreon); CSV/Excel export is the current path.
- No public API endpoints discovered. Authenticated-Playwright automation is tracked as TODO #5–#7
  (needs a credential/auth strategy before building).

## Recommendation (as executed)

### Built fetchers for (all ✅ done):
1. **FantasyPros ADP** — public, clean consensus table.
2. **FantasyPros rankings (fp)** — via `ecrData` JSON (year-round).
3. **DraftShark** — headless export, full board.
4. **HW weekly/ROS** — existing scraper (hardened: season param + fail-loud guard).

### Still manual:
5. **FantasyPoints** — paywall; automation candidate (TODO #5).
6. **PFF** — paywall; automation candidate (TODO #6).
7. **JJ** — Patreon; automation candidate (TODO #7).
8. **HW redraft** — no stable URL; manual by design.

### Manual Source Guide
For each manual source, see [`manual_source_guide.md`](manual_source_guide.md): URL, how to export,
expected `update/` filename prefix, and the columns the pipeline expects.
