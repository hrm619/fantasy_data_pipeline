# Manual Source Download Guide
## fantasy_data_pipeline — Ranking Source Files

All source files must be placed in `data/rankings current/update/` before running the pipeline.
The pipeline auto-detects files by **prefix matching** from `FILE_MAPPINGS` in `config.py`, so filenames
must start with the prefix shown below. Season-specific prefixes derive from `CURRENT_SEASON`
(currently `2025`) — bump that one constant at season rollover.

> Status of automation per source lives in [`SCRAPER-PLAN.md`](../SCRAPER-PLAN.md).

---

## Automated Sources (no manual download needed)

### FantasyPros ADP (adp)
- **Command:** `ff-rankings fetch-adp` (writes to `update/`)
- **Filename:** `FantasyPros_2025_Overall_ADP_Rankings.csv`
- **Fallback manual URL:** https://www.fantasypros.com/nfl/adp/ppr-overall.php

### FantasyPros Rankings (fp)
- **Command:** `ff-rankings fetch-fp [--scoring ppr|half-ppr|standard]` (writes to `update/`)
- **Method:** parses the cheatsheet's embedded `ecrData` JSON — works year-round (the
  `/rankings/*-overall.php` table redirects to cheatsheets in the offseason).
- **Filename:** `FantasyPros_2025_Draft_ALL_Rankings.csv`
- **Fallback manual URL:** https://www.fantasypros.com/nfl/rankings/ppr-overall.php (login required for CSV export)

### DraftShark (ds)
- **Command:** `ff-rankings fetch-ds` (headless browser; needs the `headless` extra + Chromium)
- **Method:** drives the page's own client-side "Export Rankings" button (mobile viewport) and captures
  the CSV download — full ~558-player board.
- **Filename:** `rankings-half-ppr.csv`
- **Fallback manual URL:** https://www.draftsharks.com/ros-rankings/half-ppr (use the "Export Rankings" button)

### Hayden Winks / Underdog (hw)
- **Weekly/ROS:** Automated via `hw_scraper.py` — auto-triggered by the pipeline when the file is absent.
- **Redraft:** Manual. Navigate to the Underdog Network preseason rankings article → "Table Download".
- **Filename (redraft):** `tableDownload.csv`

---

### FantasyPoints / Barrett (fpts) — ✅ now automated via saved session
- **One-time login:** `ff-rankings login fpts` (session saved to `~/.fantasy_pipeline/auth/fpts.json`).
- **Fetch:** `ff-rankings fetch-fpts` (selects Barrett's redraft board, clicks "Download as CSV").
- **Filename:** `Scott Barrett <year> Redraft Rankings.csv` (matches the `Scott Barrett` prefix).
- **Columns:** `Overall, NAME, POS, TEAM, BYE, TIER, EXODIA` (~100 players).
- **Manual fallback:** https://www.fantasypoints.com/nfl/rankings/redraft → "BARRETT'S RANKINGS" tab →
  "Download as CSV" (subscription required).

### PFF (pff) — ✅ now automated via saved session
- **One-time login:** `ff-rankings login pff` (opens a browser; session saved to
  `~/.fantasy_pipeline/auth/pff.json`, outside the repo).
- **Fetch:** `ff-rankings fetch-pff` (reuses the saved session headlessly; writes to `update/`).
- **Filename:** `Draft-rankings-export-2025.csv` · **Columns:** `Overall Rank, Full Name,
  Team Abbreviation, Position, Position Rank, Bye Week, ADP, Projected Points, Auction Value`.
- **Manual fallback:** https://www.pff.com/fantasy/rankings/draft → Export/Download (subscription required).
- **Note (weekly/ROS):** the PFF export has a title row above the real header — the loader handles it.

---

## Manual Sources (paywalled — automation tracked as TODO #7)

### JJ Zachariason / LateRound (jj)
- **URL:** https://www.patreon.com/posts/ (latest ranking post; subscription required)
- **Export:** Download the attached Excel file from the Patreon post.
- **Filename (redraft):** Must start with `Redraft1QB_` (e.g., `Redraft1QB_2025.xlsx`). Other league types
  use different prefixes — bestball `1QBRankings_`, ROS `ROSRankings_`, weekly `Week{N}_RankingsTiers`.
- **Format:** Excel file with a **"Rankings and Tiers"** sheet.

---

## File Placement

All files go in:
```
data/rankings current/update/
```

After processing, source files are moved to `data/rankings current/raw archive/{timestamp}/`.
