---
name: draftsharks-export
description: DraftSharks rankings export — capturing the full board via headless browser; now login-gated (the ungated mobile button was removed)
metadata:
  type: project
---

DraftSharks half-PPR rankings (`draftsharks.com/rankings/half-ppr`) is a JS-rendered SPA. Static HTML exposes only ~25 players with no projections. The pipeline fetcher `fetch_rankings.fetch_draftsharks` (CLI `ff-rankings fetch-ds`) uses Playwright to capture the page's own client-side "Export Rankings" CSV.

**Why:** the export is the cleanest path — the downloaded CSV is the exact 14-column layout (`Rank,Team,Player,"Fantasy Position",Games,ADP,Bye,SOS,InjuryRisk,"Floor Proj","Consensus Proj","DS Proj",CeilingProj,"3D Value"`) that `load_data` + positional rename into `COLUMN_MAPPINGS['ds']` consumes directly.

**How to apply:**
- **SUPERSEDED (2026): the export is now login-gated.** DraftSharks DELETED the ungated
  `a.mobile-export-button`, so the mobile-UA/390x844 viewport hack is gone and a saved `ds` session
  is required (`ff-rankings login ds`). Logged out, the only control left is `a.export-button.gated`
  → `/login`.
- The page renders TWO `div.export-button` variants (Alpine.js) toggled on
  `exportContainerOptionPrint`: one wraps a Print/Export dropdown, the other calls `handleExport`
  directly. Target the latter by its `@click` handler to stay off the Print sibling.
- Wait for **`visible`**, not `attached` — the hidden dropdown variant satisfies `attached` even when
  logged out, so an expired session would look fine and then time out on the download.
- Capture with `page.expect_download()` around that control's `.click()`.
- Do NOT use the separate gated "Export Auction Values" button.
- Live-verified 2026-06-14: full board = ~558 players. Coverage floor guard set to 150.
- Playwright is the optional `headless` extra (not core deps). Install: `uv pip install -e ".[headless]"` then `playwright install chromium`.
