---
name: pff-scoring-and-export
description: PFF fantasy rankings page — the scoring dropdown label is optimistic client state, not proof the board loaded; use the rankings API response as ground truth
metadata:
  type: project
---

PFF's draft rankings page (`pff.com/fantasy/rankings/draft`) is a React (react-native-web) SPA.
The CSV export serialises **client store state and fires no network request of its own**, so
nothing observable at export time tells you which scoring board you are about to download.

**Why this matters:** the page defaults to full PPR, the pipeline wants Half PPR, and the two
CSVs are byte-compatible (same 9 columns, 512 rows, plausible integers). A wrong board is
invisible on disk and contaminates `avg_RK`.

**How to apply:**
- **The dropdown label is a liar.** Clicking an option flips
  `button[data-testid="fantasyTools.filters.scoringTypeDropdown"]` innerText at ~0.28s from
  optimistic React state — *before* and *even entirely without* a successful fetch.
  Live-verified 2026-07-26: aborting the API left the label reading "Half PPR" while the export
  emitted the full PPR board (Jahmyr Gibbs proj 342.88 = PPR vs 306.52 = half-PPR).
  A `wait_for_function` on the label + a fixed sleep therefore proves nothing.
- **Ground truth is the page's own fetch**:
  `GET consumer-api.pff.com/football/v1/fantasy/rankings?page=1&leagueType=standard&scoringType=REDRAFT_HALF_PPR`.
  Attach a `page.on("response", ...)` watcher **before `page.goto`** (the initial load counts) and
  require a 200 whose `scoringType` query param equals the target. Returns in ~1-2s, faster and
  deterministic vs a 3s sleep.
  - Anchor the endpoint match — `/fantasy/weekly-rankings` is a **decoy that also carries a
    `scoringType` param** (lowercase `ppr`). Regex `fantasy/rankings\Z` over netloc+path excludes it.
  - One request returns the **whole 512-row board** despite `page=1`; no pagination to chase.
- **Options are their own buttons with stable testids** —
  `fantasyTools.dropdownOption.REDRAFT_{PPR,HALF_PPR,NON_PPR,2QB_PPR,IDP}` plus a `DYNASTY_*`
  group. Target these, **not** `get_by_role("button", name=..., exact=True)`: the accessible name
  `"PPR"` matches **two** nodes (the dropdown trigger *and* the PPR option) and `.first` resolves
  in DOM order to the trigger. The option overlay is conditionally rendered — absent from the DOM
  until the trigger is clicked, so there is no hidden-node risk, but also nothing to wait on early.
- **Re-clicking the already-selected option fires no request**, so "always click and wait for a
  response" deadlocks. The early-exit branch must stay; satisfy it from a previously observed
  response instead.
- **Sync-API trap:** never poll a `page.on("response")` watcher with `time.sleep` — the sync
  driver only dispatches queued events while pumped. Use `page.wait_for_timeout()`. `time.sleep`
  made a working watcher time out while its own error message (which called `inner_text()`, and so
  pumped the driver) printed the value it had been waiting for.
- No scoring preference is persisted in the saved session's cookies/localStorage, so the page
  loads as PPR on every run. Don't assume the previous run's selection survived.

Related: [[draftsharks-export]] — same family of "the export follows an on-page control that the
downloaded file doesn't record" problem.
