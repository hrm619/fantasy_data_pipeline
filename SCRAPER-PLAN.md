# Scraper Plan — Automating Ranking Source Refresh

**Goal:** move each ranking source from "manual download" toward "automated fetch that drops
directly into `data/rankings current/update/` in the exact schema the pipeline expects."

**Last verified:** 2026-06-14 (live fetch test + code review). See
`docs/auto-ranking-refresh-assessment/` for the original feasibility investigation.

**Active backlog:** [`TODO.md`](TODO.md) — next task is automating the paywalled sources (#5–#7).

## How to use this doc
- We work **one source at a time**, top of the priority list down.
- Each source has a fixed template: **Current state → Target → Gaps → Tasks → Acceptance → Decision needed**.
- Status legend: ✅ done · 🟡 in progress · ⬜ not started · ⛔ blocked / deferred · 🔒 manual-only (by design)
- A source is "done" only when a fetched file passes **end-to-end**: fetch → lands in `update/` →
  `ff-rankings` consumes it without a column-count mismatch or player-ID crash.

## The two scraper subsystems (context)
1. **`scraper/hw_scraper.py` + `integration.py`** — Hayden Winks article scraper. Mature, auto-triggered
   for weekly/ROS, fuzzy player matching. *Leave working code alone.*
2. **`scraper/fetch_rankings.py`** — standalone HTTP fetchers (FantasyPros ADP, DraftShark). Prototype:
   runs, but output is **not** pipeline-consumable, DraftShark is broken, and nothing is CLI-wired.

## Pipeline contract every fetcher must satisfy
The pipeline standardizes a source by **column count, then renames by position**
(`rankings_processor._load_and_standardize_data`):
```python
if len(df.columns) == len(expected_cols):
    df.columns = expected_cols      # positional rename
else:
    # logs "column count mismatch" and SKIPS standardization → later crashes on missing 'PLAYER NAME'
```
So a fetched CSV must have **the same column count and left-to-right order** as the relevant
`COLUMN_MAPPINGS[<key>]` (redraft/bestball), `WEEKLY_COLUMN_MAPPINGS`, or `ROS_COLUMN_MAPPINGS` entry.
Prefix of the filename must match `FILE_MAPPINGS[<league>][<key>]`.

---

## Priority order / status
1. ✅ FantasyPros ADP (`adp`) — consensus shipped (`ff-rankings fetch-adp`); Sleeper option deferred
2. ✅ DraftShark (`ds`) — headless Playwright fetcher shipped (`ff-rankings fetch-ds`); reclassified sharp in fantasy-data
3. ✅ Hayden Winks (`hw`) — weekly/ROS automated + hardened (season param, fail-loud guard); redraft manual by design
4. ✅ FantasyPros rankings (`fp`) — shipped via embedded `ecrData` JSON (`ff-rankings fetch-fp`); works year-round
5. 🔒 FantasyPoints / Barrett (`fpts`) — paywall, manual by design
6. 🔒 PFF (`pff`) — paywall, manual by design
7. 🔒 JJ Zachariason (`jj`) — Patreon, manual by design

**All automatable sources are done.** Remaining open items are cross-cutting (season-rollover audit;
doc reconciliation) and verifying the manual-source guide for #5–#7.

---

## 0. Shared infrastructure
Status: ✅ (built across sources #1–#4)

- ✅ **Schema-adapter pattern** — each fetcher emits its exact `COLUMN_MAPPINGS[key]` layout via a module
  constant (`ADP_OUTPUT_COLUMNS`, `FP_OUTPUT_COLUMNS`, `DS_OUTPUT_COLUMNS`), with a per-source
  schema-contract test asserting it equals the config. Unavailable columns emitted blank.
- ✅ **CLI wiring** — additive `ff-rankings fetch-adp | fetch-ds | fetch-fp` dispatch in `cli/rankings.py`
  (the default `--league-type` flow is unchanged).
- ✅ **Network-free tests** — fixture/JSON-string based parser tests for each fetcher; the DraftSharks live
  browser test is skip-gated when Chromium is unavailable, so CI stays green.
- ✅ **Coverage sanity check** — every fetcher has a `min_players` floor that raises on layout drift.
- 🟡 **Harden `_TableParser`** — still used only by the ADP fetcher (fp uses JSON, ds uses Playwright). The
  text-node fusion edge case hasn't bitten ADP in practice; left as-is. Revisit only if ADP names break.

---

## 1. FantasyPros ADP — `adp`
**Status:** ✅ consensus shipped & pipeline-consumable · ⬜ Sleeper option pending source hunt
**Code:** `fetch_rankings.fetch_fantasypros_adp` · CLI `ff-rankings fetch-adp` · **URL:** `fantasypros.com/nfl/adp/ppr-overall.php`

### ✅ Done (2026-06-14)
- Fetcher rewritten for the live 4-col table; emits the exact 7-col `COLUMN_MAPPINGS['adp']` schema
  (consensus AVG → ADP; MARKET INDEX/RT blank placeholders).
- `ff-rankings fetch-adp` CLI command added (additive; existing `ff-rankings --league-type` unchanged).
- Coverage floor (`min_players=200`) guards layout drift.
- Tests: `tests/test_fetch_rankings.py` (fixture-based, no network) incl. a schema-contract guard
  (`ADP_OUTPUT_COLUMNS == COLUMN_MAPPINGS['adp']`).
- Verified end-to-end live: 411 players → loads → positional rename → processor emits ADP/ADP ROUND.

### ⬜ Remaining
- Sleeper `--platform` option — blocked on finding a Sleeper redraft ADP source (investigation running).

### Current state (verified 2026-06-14)
- Fetch runs, returns **411 players**, clean data: `1, Jahmyr Gibbs, DET, RB, 6, 1.5`.
- Output columns: `[Rank, Player, Team, Pos, Bye, AVG]` (6).
- **Decided:** consensus ADP by default, with an option to select a single platform (Sleeper = primary).
- **⚠️ Blocker for the platform option:** FantasyPros redraft ADP pages now serve a **single 4-col
  consensus table** (`Rank, Player, POS, AVG`); `sleeper-*overall.php` 302-redirects to `overall.php`,
  and `?source=Sleeper` is ignored. Best-ball ADP exposes platforms (BB10/RTSports/Underdog/Drafters/
  DraftKings) but **not Sleeper**. → **Sleeper redraft ADP is not scrapable from FantasyPros static HTML.**
  Consensus is available now; Sleeper needs a different source (Sleeper API, logged-in FP export, or headless).

### Target
- Fetched CSV named `FantasyPros_2025_Overall_ADP_Rankings.csv` lands in `update/` and `ff-rankings`
  consumes it as the `adp` source with no manual edits.

### Gaps
- ❌ Schema: 6 cols vs `COLUMN_MAPPINGS['adp']` = 7 `[PLAYER NAME, TEAM, BYE, POS, ADP, MARKET INDEX, RT]`.
- ❌ Column names/order differ (`Player`→`PLAYER NAME`, `AVG`→`ADP`, no `MARKET INDEX`/`RT`).
- ❌ No CLI command (docs reference a nonexistent `ff-rankings fetch-adp`).
- ⚠️ Coverage dropped 989 → 411 (page/default-view change) — no monitoring.

### Tasks
- ⬜ Map fetched fields → 7-col `adp` schema via the shared adapter (`MARKET INDEX`/`RT` blank or derived).
- ⬜ Confirm positional order matches config exactly; verify with a real `ff-rankings` redraft dry run.
- ⬜ Add `ff-rankings fetch-adp` CLI command writing to `update/`.
- ⬜ Add coverage floor (e.g. warn if `< 300`).
- ⬜ Fixture-based unit tests (parse + adapt + count).

### Acceptance
- Fetched file passes end-to-end through `ff-rankings --league-type redraft` with `adp` recognized
  (no "column count mismatch", ADP-derived columns like `POS ADP`/`ADP Delta` populate).

### Decision needed
- `MARKET INDEX` / `RT` aren't on the public ADP page. OK to leave blank, or derive/drop? (Affects whether
  downstream consumers expect them.)

---

## 2. DraftShark — `ds`
**Status:** ✅ working (headless, Option A) — live-verified 2026-06-14
**Code:** `fetch_rankings.fetch_draftsharks` · CLI `ff-rankings fetch-ds` · **URL:** `draftsharks.com/rankings/half-ppr`

### Implemented (Option A — headless browser)
Replaced the broken static fetcher with a **Playwright** fetcher. It drives the page's own client-side
**"Export Rankings"** button (`handleExport`, a Blob download) and captures the CSV via `page.expect_download()`.
That CSV is the **exact 14-column layout** the pipeline consumes (`Rank,Team,Player,"Fantasy Position",...`),
which `load_data` reads and the pipeline renames positionally into `COLUMN_MAPPINGS['ds']`.

- **Output:** `rankings-half-ppr.csv` in the update folder (matches `FILE_MAPPINGS` redraft/bestball `ds` prefix).
- **Live result:** captured **558 players** (full board), header matches the manual export sample exactly,
  positional rename to the 14-col `ds` schema confirmed.
- **CLI:** `ff-rankings fetch-ds [--output DIR] [--min-players N]` (additive; existing flows unchanged).
- **Dependency:** Playwright added as the optional `headless` extra (not in core deps). Lazy import with a
  friendly install hint. Run: `uv pip install -e ".[headless]"` then `playwright install chromium`.

### Key gating discovery
- The page exposes **two** export controls. The **desktop**-visible one is **gated**
  (`class="export-button gated" href="/login"`). The ungated client-side export is the
  `a.mobile-export-button` (`@click="handleExport"`) variant, reachable only under a **mobile UA + viewport
  (390x844)**. The fetcher uses a mobile context for this reason. The separate "Export Auction Values" button
  is gated and intentionally **not** used.
- Clicking the mobile export fires the Blob download directly (the "Export" action) — no Print/Export submenu
  appears in the headless mobile DOM, so there is no Print/Export ambiguity to resolve there.

### Hardening
- **Coverage floor** (`min_players`, default 150): raises if fewer rows are captured (full board ~300+).
- **Header validation**: raises if the exported header drifts from the expected 14 columns.
- **DOM fallback helper** (`_ds_dom_row_to_output`): pure, unit-tested mapper from a 14-cell rendered DOM row
  to the `ds` schema, available if the export ever becomes uncapturable.

### Tests
- `tests/test_fetch_draftsharks.py`: schema contract, DOM-row mapping, coverage-floor guard (browser-free),
  plus one live-browser test gated to **skip when Playwright/Chromium is unavailable** (keeps CI green).

### Acceptance
- Either no broken fetcher remains (B), or DS fetch yields a clean full board consumable by `ff-rankings` (A).

---

## 3. Hayden Winks — `hw`
**Status:** ✅ weekly/ROS automated + hardened (2026-06-14) · 🔒 redraft manual (by design)
**Code:** `hw_scraper.py`, `integration.py`, `config.get_hw_scraper_url`

### Current state
- Weekly/ROS auto-scraped from Underdog Network, fuzzy player matching, auto-triggered by
  `auto_scrape_if_needed`. Works.
- Redraft: no predictable URL pattern → manual `tableDownload.csv`. **Decided: stays manual permanently.**

### ✅ Done (2026-06-14 hardening)
- **Season parameterized:** added `CURRENT_SEASON = 2025` constant in `config.py`; `get_hw_scraper_url`
  takes a `season` param (default `CURRENT_SEASON`). Season rollover = bump one constant, no code edits.
- **Fail-loud guard:** `scrape_fantasy_rankings` now raises `RuntimeError` if 0 players parse (selector/
  format drift) instead of silently returning an empty DataFrame. The pipeline's `auto_scrape_if_needed`
  still catches it and continues with existing files, so the pipeline doesn't crash.
- **Tests:** `tests/test_hw_scraper.py` — URL builder (default/custom season, ros==weekly, validation) +
  the empty-result guard (monkeypatched `requests.get`, no network).

### Remaining (low priority)
- ⚠️ CSS-selector/article-format coupling (`div.styles_postLayoutBody__MYNJ_`, position-header regex) is
  still inherently fragile to a site redesign — but now fails loudly via the guard above.
- Redraft HW automation: not pursued (no stable URL). Manual by design.

---

## 4. FantasyPros Rankings — `fp`
**Status:** ✅ shipped & live-verified (2026-06-14)
**Code:** `fetch_rankings.fetch_fantasypros_rankings` · CLI `ff-rankings fetch-fp` · **Source:** cheatsheet `ecrData` JSON

### Key discovery — JSON blob beats table scraping
The `/rankings/*-overall.php` table pages still 302-redirect to `consensus-cheatsheets.php` in the
offseason (no table). **But** every cheatsheet page embeds the full rankings as a `var ecrData = {...}`
JSON blob — available **year-round**. The fetcher parses that JSON instead of scraping a table, so it
works now and is far more robust than HTML parsing.

### ✅ Done
- `fetch_fantasypros_rankings(output_dir, year=2025, scoring='ppr', min_players=200)` parses `ecrData`
  → emits the exact 8-col `COLUMN_MAPPINGS['fp']` layout (`ECR, TIER, PLAYER NAME, TEAM, POS, BYE, SOS,
  ECR VS ADP`; SOS / ECR VS ADP blank — pipeline discards them) → `FantasyPros_<year>_Draft_ALL_Rankings.csv`.
- **Scoring:** defaults to `ppr` — confirmed by evidence (live PPR #1 = Ja'Marr Chase matches the on-disk
  manual export's #1). `--scoring {ppr,half-ppr,standard}` selects the cheatsheet.
- CLI: `ff-rankings fetch-fp [--output --year --scoring --min-players]` (additive).
- Coverage floor + "ecrData missing" guard for layout drift.
- Tests: `tests/test_fetch_rankings.py` (JSON-string fixture, no network) incl. schema-contract guard
  (`FP_OUTPUT_COLUMNS == COLUMN_MAPPINGS['fp']`).
- **Live-verified:** 490 players → loads → positional rename → `process_fantasypros_data` emits ECR/POS ECR/TIER.

### Notes
- Live data is already 2026-season (byes updated); filename keeps `year=2025` to match the current
  `FILE_MAPPINGS['fp']` prefix. The 2025→2026 prefix rename is the season-rollover audit (cross-cutting).
- Pre-existing quirk (not from this work): the fp processor emits `ECR` twice in `_standardize_output`;
  the pipeline dedups it in `_organize_final_dataframe`. Harmless. Noted in case it's cleaned up later.

---

## 5. FantasyPoints / Barrett — `fpts`
**Status:** 🔒 manual (by design)
**URL:** `fantasypoints.com/nfl/rankings/...` (subscription, JS-rendered)

- Paywalled + JS-rendered; no public endpoint found. **Keep manual** (`Scott Barrett*.csv`).
- ⬜ Verify the manual guide lists the correct filename prefix(es) and column expectations.

---

## 6. PFF — `pff`
**Status:** 🔒 manual (by design)
**URL:** `pff.com/fantasy/rankings/draft` (premium subscription)

- Requires PFF subscription; export is the only path. **Keep manual** (`Draft-rankings-export.csv`).
- ⬜ Verify manual guide accuracy (filename, second-row-header quirk for weekly/ROS).

---

## 7. JJ Zachariason — `jj`
**Status:** 🔒 manual (by design)
**URL:** Patreon post (subscription)

- Patreon-gated Excel download; cannot automate. **Keep manual** (`Redraft1QB_*.xlsx`, "Rankings and Tiers" sheet).
- ⬜ Verify manual guide accuracy (filename prefix per league type, sheet name).

---

## Cross-cutting cleanup (track separately)
- ⬜ Reconcile `docs/auto-ranking-refresh-assessment/` with reality (remove the nonexistent
  `ff-rankings fetch-adp` claim until built; fix "989 players" → current count; mark DS status).
- ✅ Season-rollover audit (2026-06-15): `CURRENT_SEASON` in `config.py` is now the single source of
  truth — `FILE_MAPPINGS` `fp`/`adp` prefixes + ROS `fpts` pattern, both fetcher `year` defaults, the
  CLI `--year` defaults, and `get_hw_scraper_url`'s slug all derive from it. Byte-identical at 2025;
  guarded by `tests/test_config.py`. Bumping to 2026 is a one-line change (do it when 2026 source files land).

---

## Transparency / working-tree notes (2026-06-14)

Recorded so nothing is misattributed at commit time. This work spanned two repos.

### `fantasy-data` (DraftShark → sharp reclassification)
- **Changed by this work** (intentional): `src/fantasy_data/ingest/ingest_rankings.py` (`SHARP_SOURCES`,
  `SHARP_POS_COLUMNS` += `ds`), `src/fantasy_data/viz/player_profile.py` (`SHARP_SOURCES` += `DraftShark (ds)`),
  `tests/test_ingest_rankings.py` (recomputed sharp values: WR Alpha 1.25→1.2, source counts 4→5 / 2→3,
  QB Star divergence −0.25→−0.2), `README.md` and monorepo `CLAUDE.md` ("4 sharp sources" → "5 … DraftSharks").
- **NOT changed by this work** (already modified in the working tree — left untouched): `src/fantasy_data/db.py`
  and `uv.lock`. `db.py` appears to be in-flight work and is the likely cause of the pre-existing failure below.
- **Pre-existing test failure (not caused by this work):** `tests/test_models.py::TestAllTablesCreated::test_table_count`.
  Verified it fails identically on a clean tree (stashed these changes, reran, popped). It's a stale table-count
  assertion, unrelated to rankings. Full suite after the change: **137 passed, 1 failed (this pre-existing one)**;
  `tests/test_ingest_rankings.py` → **15 passed**; ruff clean on changed files.

### `fantasy_data_pipeline` (DraftShark fetcher, built via the playwright agent)
- Live-verified the headless DraftShark fetcher (558 players, 14-col schema). Suite: **51 passed**, ruff clean.
- `playwright` + the Chromium binary were installed into the local `.venv` to run the live verification. This is
  an **environment-only** change — `playwright` is declared solely as the optional `headless` extra in
  `pyproject.toml`, never in core dependencies.

### Earlier in this session
- `docs/` is being actively reorganized by the user; treated as off-limits. An accidental `git restore docs/`
  (mistaking the live edits for an errant process) may have reverted some in-flight edits to tracked docs —
  flagged at the time.
