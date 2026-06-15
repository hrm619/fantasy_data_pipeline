---
name: draftsharks-export
description: DraftSharks rankings export — how to capture the full ungated board via headless browser (mobile viewport gate)
metadata:
  type: project
---

DraftSharks half-PPR rankings (`draftsharks.com/rankings/half-ppr`) is a JS-rendered SPA. Static HTML exposes only ~25 players with no projections. The pipeline fetcher `fetch_rankings.fetch_draftsharks` (CLI `ff-rankings fetch-ds`) uses Playwright to capture the page's own client-side "Export Rankings" CSV.

**Why:** the export is the cleanest path — the downloaded CSV is the exact 14-column layout (`Rank,Team,Player,"Fantasy Position",Games,ADP,Bye,SOS,InjuryRisk,"Floor Proj","Consensus Proj","DS Proj",CeilingProj,"3D Value"`) that `load_data` + positional rename into `COLUMN_MAPPINGS['ds']` consumes directly.

**How to apply:**
- The page has TWO export controls. The DESKTOP-visible one is GATED: `<a class="menu-item export-button gated" href="/login" title="Export Rankings">` — clicking it never fires a download.
- The UNGATED export is `a.mobile-export-button` (`<a @click="handleExport" download ...>`), a client-side Blob download. It is hidden on desktop viewports. You MUST use a mobile UA + viewport (390x844) for it to be visible/clickable.
- Capture with `page.expect_download()` around `locator("a.mobile-export-button").click()`. On mobile the click fires the download directly — no Print/Export submenu appears in the headless DOM.
- Do NOT use the separate gated "Export Auction Values" button.
- Live-verified 2026-06-14: full board = ~558 players. Coverage floor guard set to 150.
- Playwright is the optional `headless` extra (not core deps). Install: `uv pip install -e ".[headless]"` then `playwright install chromium`.
