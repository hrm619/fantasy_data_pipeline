# Manual Source Download Guide
## fantasy_data_pipeline — Ranking Source Files

All source files must be placed in `data/rankings current/update/` before running the pipeline.

---

## Automated Sources

### FantasyPros ADP
- **Automated:** Yes — use `ff-rankings fetch-adp` or the Python API
- **Filename:** `FantasyPros_2025_Overall_ADP_Rankings.csv`
- **Fallback manual URL:** https://www.fantasypros.com/nfl/adp/ppr-overall.php (export button when logged in)

---

## Manual Sources

### FantasyPros Rankings (fp)
- **URL:** https://www.fantasypros.com/nfl/rankings/ppr-overall.php (active during preseason, ~late June onward)
- **Login:** Required for CSV export
- **Export:** Click "Export" button at top of rankings table → downloads CSV
- **Filename:** `FantasyPros_2025_Draft_ALL_Rankings.csv`
- **Note:** During offseason this page redirects to cheatsheets. Rankings go live when preseason begins.

### FantasyPoints / Barrett (fpts)
- **URL:** https://www.fantasypoints.com/nfl/rankings/half-ppr (requires subscription)
- **Login:** FantasyPoints subscription required
- **Export:** Navigate to rankings page → export/download CSV
- **Filename:** Must start with `Scott Barrett` (e.g., `Scott Barrett 2025 Rankings.csv`)
- **Note:** Multiple position-specific files may be needed. Check FILE_MAPPINGS config.

### DraftShark (ds)
- **URL:** https://www.draftsharks.com/rankings/half-ppr
- **Login:** Not required, but full list may require scrolling/loading
- **Export:** No built-in CSV export. Use browser table-copy or inspect network requests.
- **Filename:** `rankings-half-ppr.csv`
- **Columns expected:** RK, PLAYER NAME, TEAM, POS, and additional rank columns

### Hayden Winks / Underdog (hw)
- **Redraft URL:** Navigate to Underdog Network → find preseason rankings article
- **Weekly/ROS:** Automated via `hw_scraper.py` — no manual step needed
- **Export:** For redraft, use the "Table Download" button if available
- **Filename:** `tableDownload.csv`
- **Note:** Weekly/ROS scraping is handled automatically by the pipeline when files aren't found.

### PFF (pff)
- **URL:** https://www.pff.com/fantasy/rankings/draft (requires PFF subscription)
- **Login:** PFF premium subscription required
- **Export:** Click "Export" or "Download" on the rankings page
- **Filename:** `Draft-rankings-export.csv`

### JJ Zachariason / LateRound (jj)
- **URL:** https://www.patreon.com/posts/ (check latest ranking post)
- **Login:** Patreon subscription required
- **Export:** Download the attached Excel file from the Patreon post
- **Filename:** Must start with `Redraft1QB_` (e.g., `Redraft1QB_2025.xlsx`)
- **Format:** Excel file with "Rankings and Tiers" sheet

---

## File Placement

All files go in:
```
data/rankings current/update/
```

The pipeline auto-detects files by prefix matching from `FILE_MAPPINGS` in `config.py`.
After processing, source files are moved to `data/rankings current/raw archive/`.
