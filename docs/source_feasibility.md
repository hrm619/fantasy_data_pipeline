# Source Fetch Feasibility — Investigation Results
**Date:** April 2026

## Summary

| Source | Automated? | Method | Auth Required | Notes |
|--------|-----------|--------|---------------|-------|
| **FantasyPros ADP** | **Yes** | HTML table scrape | No | 989 players, clean table structure, public page |
| **FantasyPros rankings (fp)** | **Offseason redirect** | HTML table scrape when active | Likely login for CSV export | Currently redirects to cheatsheets (offseason). Table available during season. |
| **DraftShark (ds)** | **No** | Manual CSV | No | Only 25 players in HTML, names are duplicated/malformed. Needs JS rendering for full list. Manual export is cleaner. |
| **Underdog/HW (hw)** | **Weekly/ROS only** | hw_scraper.py | No | Existing scraper works for weekly/ROS. No redraft URL pattern. Redraft = manual. |
| **FantasyPoints (fpts)** | **No** | Manual CSV export | Paid subscription | JS-rendered paywall |
| **PFF rankings (pff)** | **No** | Manual CSV export | Paid subscription | Requires PFF subscription |
| **JJ Zachariason (jj)** | **No** | Manual Patreon download | Patreon paywall | Cannot automate |

## Detailed Findings

### FantasyPros ADP (automatable)
- **URL:** `https://www.fantasypros.com/nfl/adp/ppr-overall.php`
- **HTTP 200**, 596KB page, public access
- **Table structure:** `Rank | Player+Team | POS | ESPN | Sleeper | CBS | NFL | RTSports`
- **989 player rows** — comprehensive coverage
- **Approach:** `requests` + `BeautifulSoup` or simple HTML parser. Parse `<tr>` rows from the main table. Extract player name, team (embedded in cell), position, and ADP values.

### FantasyPros Rankings (offseason — deferred)
- **URL:** `https://www.fantasypros.com/nfl/rankings/ppr-overall.php`
- **Currently redirects** (HTTP 302) to `/nfl/rankings/consensus-cheatsheets.php` — rankings are not active during offseason
- Rankings page becomes available during preseason (typically late June/July)
- Cheatsheets page has "download" links but they appear to require login
- **Approach:** Revisit when rankings go live. Likely same table scrape pattern as ADP.

### DraftShark (partial — top players only)
- **URL:** `https://www.draftsharks.com/rankings/half-ppr`
- **HTTP 200**, 597KB page, public access
- **Only 38-62 rows visible** in initial HTML — likely JS loads more or uses pagination
- Table structure is messy (inline SVG team logos, concatenated player info)
- **Approach:** If full rankings needed, may require Playwright/headless browser. For MVP, the visible ~60 players cover the draft-relevant range. Parse with BeautifulSoup + cleanup regex.

### Underdog/HW (weekly/ROS automated, redraft manual)
- **Weekly/ROS:** `hw_scraper.py` + `get_hw_scraper_url()` already work. URL pattern: `week-{N}-fantasy-football-rankings-the-blueprint-2025`
- **Redraft:** No URL pattern in config. Underdog Network publishes preseason rankings as blog posts with varying titles — not scrapable with a predictable URL.
- **Approach:** Keep existing scraper for weekly/ROS. Redraft HW rankings are manual CSV download.

### FantasyPoints, PFF, JJ (manual only)
- All behind paywalls (subscription or Patreon)
- CSV export is the only option
- No API endpoints discovered

## Recommendation

### Build fetchers for:
1. **FantasyPros ADP** — highest value, public, clean data, 989 players
2. **DraftShark** — public, partial data, worth building for the top ~60 players

### Keep manual for:
3. **FantasyPros rankings** — revisit when rankings go live (July)
4. **HW redraft** — manual CSV, weekly/ROS use existing scraper
5. **FantasyPoints** — manual CSV export from subscription
6. **PFF** — manual CSV export from subscription
7. **JJ** — manual Patreon download

### Manual Source Guide
For each manual source, users need:
- URL to navigate to
- How to export (CSV button, copy-paste, etc.)
- Expected filename pattern for the pipeline's `update/` directory
- Which columns the pipeline expects
