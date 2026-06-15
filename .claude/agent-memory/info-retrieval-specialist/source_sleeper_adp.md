---
name: source-sleeper-adp
description: How to obtain Sleeper redraft ADP for the fantasy pipeline; verified endpoints and dead-ends as of 2026-06.
metadata:
  type: reference
---

Task: get Sleeper redraft ADP (~200-400 players), refreshable, automatable. Findings verified 2026-06-14.

Dead ends (verified):
- Sleeper public API (api.sleeper.app) has NO ADP endpoint and NO way to enumerate mock drafts. Draft endpoints are per-draft-id / per-league / per-user only (`/v1/draft/<id>`, `/v1/draft/<id>/picks`, `/v1/league/<id>/drafts`, `/v1/user/<id>/drafts/nfl/<season>`). Can't compute ADP at scale without discoverable draft_ids. Confirmed against docs.sleeper.com.
- FantasyPros sleeper-ppr.php 302-redirects to /nfl/adp/overall.php (consensus only). `?export=csv` also redirects. Per-platform Sleeper ADP is no longer publicly scrapable. (User's report confirmed.)
- FantasyPros api.fantasypros.com returns 403 without API key (partner key required).
- Fantasy Nerds API: paid, ~$74.95/yr.

Best free option: Fantasy Football Calculator JSON API (NOT Sleeper-specific, it's FFC's own aggregated mock-draft ADP, but free/public/clean):
- `https://fantasyfootballcalculator.com/api/v1/adp/ppr?teams=12&year=2026` (also standard|2qb|dynasty|half-ppr). Add `&format=csv` for CSV.
- Returns JSON: player_id,name,position,team,adp,adp_formatted,times_drafted,high,low,stdev,bye. ~171 players for 2026 PPR. Public, no auth. Rate: be polite.

Sleeper-LABELED aggregators (HTML scrape, more fragile, ToS risk):
- DraftSharks https://www.draftsharks.com/adp/sleeper — public 200, player data in HTML markup (no clean JSON blob), scrapable but fragile.
- FTN https://www.ftnfantasy.com/nfl/tools/sleeper-fantasy-football-adp — 403 to bots; updated daily 9am ET from Sleeper drafts; needs headless browser.
- BeatADP https://www.beatadp.com/platform-adp/sleeper/redraft/ppr — has "Export as CSV" button (client-side JS), 225 players, off-season shows projections placeholder.
