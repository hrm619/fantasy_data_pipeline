# Scraper Plan — Automating Ranking Source Refresh

**Goal:** move each ranking source from "manual download" toward "automated fetch that drops
directly into `data/rankings current/update/` in the exact schema the pipeline expects."

**Last verified:** 2026-06-15. User-facing docs: [`docs/data-sources.md`](docs/data-sources.md)
and [`docs/usage.md`](docs/usage.md).

**Active backlog:** [`TODO.md`](TODO.md). All seven sources are automated; see the status below.

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
5. ✅ FantasyPoints / Barrett (`fpts`) — saved-session export shipped (`ff-rankings fetch-fpts`); live-verified 99 players
6. ✅ PFF (`pff`) — saved-session headless export shipped (`ff-rankings fetch-pff`); live-verified 512 players
7. ✅ JJ Zachariason (`jj`) — saved-session Patreon API + auto-discovery (`ff-rankings fetch-jj`); live-verified 250 players

**🎉 ALL SEVEN SOURCES ARE AUTOMATED.** Each `update/` source now refreshes with one command
(`fetch-adp`, `fetch-fp`, `fetch-ds`, weekly/ROS HW auto-scrape, `fetch-fpts`, `fetch-pff`, `fetch-jj`),
with paywalled sources behind a one-time `ff-rankings login <source>`. The **`ff-rankings refresh-all`**
wrapper runs all six redraft fetchers + the consolidation in one pass (live-verified end-to-end: 6/6 sources
→ 306-player combined file). **Caveat:** redraft also needs the manual Hayden Winks `tableDownload.csv`
(no fetcher — no stable redraft URL); `refresh-all` checks for it and skips consolidation with instructions
if absent. Remaining items are cross-cutting (doc reconciliation — largely done) and the known loader bug below.

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
- ✅ **Saved-session auth** (`scraper/auth.py`) — `ff-rankings login <source>` opens a headed browser for a
  one-time manual login and persists the session to `~/.fantasy_pipeline/auth/<source>.json` (outside the
  repo). Headless fetchers reuse it via `load_storage_state(source)`; no passwords stored/handled. Built
  for the paywalled sources (#5–#7); proven by `pff`.
- ✅ **`_TableParser` retired** — nothing hand-parses HTML tables any more: `fp` reads embedded JSON,
  `ds`/`pff`/`fpts` drive real exports, and `adp` now parses DraftSharks' export CSV.

---

## 1. ADP — `adp` (DraftSharks, Sleeper)
**Status:** ✅ shipped & pipeline-consumable — Sleeper-specific, replacing FantasyPros consensus
**Code:** `fetch_rankings.fetch_draftsharks_adp` · CLI `ff-rankings fetch-adp` · **URL:** `draftsharks.com/adp/half-ppr/sleeper/12`

### ✅ Done (2026-07-14) — closes the long-blocked "Sleeper option pending source hunt"
- **Source switched** FantasyPros consensus → **DraftSharks Sleeper 12-team half-PPR**. The old source was
  an *expert consensus*, not the platform the league drafts on; `ADP Delta` is only a market-divergence
  signal if ADP is the actual market.
- Emits the exact 7-col `COLUMN_MAPPINGS['adp']` schema → `DraftSharks_<season>_Sleeper_ADP.csv`.
- Rides the existing **`ds`** session (`refresh-all` maps `adp → ds`); `fp` now gates only `ff-stats
  fetch-weekly`, so `_validate_fp_session` was repointed at the weekly-leaders report.
- `--source/--scoring/--teams` expose other boards (e.g. `--source espn --teams 10`).
- Verified end-to-end live: **287 players** → loads → positional rename → processor emits ADP/ADP ROUND,
  with exactly 12 players in round 1 and rounds spanning 1–25.

### Two traps absorbed (see CLAUDE.md for the long version)
- **`round.pick` ≠ overall pick.** DraftSharks publishes `1.10` for "round 1, pick 10"; it floats to `1.1`,
  colliding with pick 1 and sorting below `1.2`. Converted via `(round - 1) * teams + pick`, verified
  against the page's own `overall_pick_number` (318/318 exact).
- **`/adp/export` has no provenance.** It echoes back the `adp1_name` you send as the column header, serves
  a full board for the *wrong* platform on a wrong id, and returns HTTP 200 + a bare header for an unknown
  id. Board ids are therefore read off the live page's export link and its label asserted before writing.
  **Never hardcode `adp1=18::107::12`.**
- Also drops the 31 `TQB` team-aggregate rows, which collide by name with each team's `DEF` row.

### ⬜ Remaining
- Nothing blocking. Optional: monitor coverage (287) for silent drift; `min_players=200` is the floor.

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
**Status:** ✅ shipped & live-verified (2026-06-15) via saved-session headless fetch
**Code:** `fetch_rankings.fetch_fpts` · CLI `ff-rankings fetch-fpts` · **URL:** `fantasypoints.com/nfl/rankings/redraft`

### Implemented (saved-session + Playwright)
- **Auth:** reuses the shared saved-session pattern — `ff-rankings login fpts` → `~/.fantasy_pipeline/auth/fpts.json`.
- **Flow (discovered live):** the redraft rankings SPA defaults to Hansen's board; `_select_fpts_barrett`
  clicks the **"BARRETT'S RANKINGS"** tab (and asserts the page title switches to Barrett's, so we never
  silently export Hansen's), then `_click_fpts_csv_download` clicks the DataTables **"Download as CSV"**
  button (`button.buttons-csv`), captured via `page.expect_download()`.
- **Output:** `Scott Barrett <year> Redraft Rankings.csv` in `update/` (matches `FILE_MAPPINGS` 'Scott Barrett' prefix).
- **Live result:** **99 players**, exact 7-col header (`Overall,NAME,POS,TEAM,BYE,TIER,EXODIA`); loads
  through `data/loader` to the exact `COLUMN_MAPPINGS['fpts']` width (no off-by-one — header is row 1).
- **Hardening:** `_validate_fpts_csv` asserts the 7-col header; `min_players=90` floor (board is ~100).
  `--url` flag overrides the rankings page for future live re-verification.
- **Tests:** `tests/test_fetch_fpts.py` (fixture validation + schema-contract guard) + a skip-gated live test.

### URL note
`/nfl/rankings/draft`, `/half-ppr`, `/ppr/overall` all return a 404/maintenance shell; the working redraft
page is `/nfl/rankings/redraft` (an SPA at `#/`). `/nfl/rankings/redraft` + the Barrett tab is the path.

---

## 6. PFF — `pff`
**Status:** ✅ shipped & live-verified (2026-06-15) via saved-session headless fetch
**Code:** `fetch_rankings.fetch_pff` · CLI `ff-rankings fetch-pff` · **URL:** `pff.com/fantasy/rankings/draft`

### Implemented (saved-session + Playwright)
- **Auth:** one-time `ff-rankings login pff` opens a headed browser; the session (cookies/localStorage)
  is persisted to `~/.fantasy_pipeline/auth/pff.json` (outside the repo — see `scraper/auth.py`). No
  password is ever stored or handled in code. `fetch_pff` reuses that session headlessly.
- **Fetch:** drives the rankings page's own Export/Download (`_click_pff_export` tries role/text
  selector variants; isolated in one place for easy adjustment) and captures the CSV via
  `page.expect_download()`.
- **Output:** `Draft-rankings-export-<CURRENT_SEASON>.csv` in `update/` (matches `FILE_MAPPINGS` pff prefix).
- **Live result:** captured **512 players** — structurally identical (header + 9 cols + row count) to the
  on-disk manual export; loads through `data/loader` to the exact `COLUMN_MAPPINGS['pff']` width.
- **Hardening:** `_validate_pff_csv` locates the `Overall Rank` header (the export has a title row above
  it), validates the 9 columns, and counts data rows; `min_players=200` coverage floor.
- **Tests:** `tests/test_fetch_pff.py` (fixture-based validation + schema-contract guard) and a live
  end-to-end test gated to **skip without Chromium + a saved session** (CI stays green).

### ⚠️ Pre-existing loader bug surfaced (not introduced here, not PFF-specific to the fetch)
- `data/loader.load_data` mis-detects the header on the PFF export (title row + blank + real header):
  it skips the `Overall Rank` row and consumes the **RK=1 player (Gibbs)** as the header, so PFF's #1
  overall is silently dropped (512 → 511 rows). **Identical on the manual file** — the fetcher faithfully
  reproduces the manual input. Tracked as a known issue in `TODO.md`; fix is a small loader follow-up.

---

## 7. JJ Zachariason — `jj`
**Status:** ✅ shipped & live-verified (2026-06-15) via saved-session Patreon **API** + auto-discovery
**Code:** `fetch_rankings.fetch_jj` · CLI `ff-rankings fetch-jj` · **Source:** Patreon collection 47664

### Implemented (saved-session + Patreon JSON API)
- **Auth:** shared saved-session pattern — `ff-rankings login jj` → `~/.fantasy_pipeline/auth/jj.json`.
- **Cloudflare workaround (key discovery):** Patreon **post HTML pages are Cloudflare-Turnstile gated**
  and flag the headless browser ("Verify you are human"). The Patreon **JSON API** (same session cookies)
  is **not** gated, so we read attachments via the API (`/api/posts/<id>?include=attachments_media`) instead
  of clicking HTML. The collection *list* page does load, so we use it for discovery.
- **Auto-discovery (no URL needed):** `_jj_discover_post_id` loads the collection page, takes the newest
  post whose title matches 1QB redraft (`_jj_is_redraft_title`: has "1qb" + "redraft"/"season-long", not
  superflex/ROS/weekly). `--post-url` overrides to target a specific post.
- **Format change handled:** the attachment is now a **5-col CSV** (`Overall,Player,Position,Pos Rank,Tier`)
  — the old `.xlsx`'s **Auction column was dropped**. `_jj_adapt_rows` pads 5→6 to the
  `COLUMN_MAPPINGS['jj']` width (source order already matches), and the fetcher handles both `.csv` and
  `.xlsx` attachments. Output: **`Redraft1QB_<year>.csv`** (CSV now, not xlsx; prefix still matches).
- **Live result:** auto-discovered the latest post, **250 players**, loads through `data/loader` to the
  exact `jj` schema width.
- **Tests:** `tests/test_fetch_jj.py` — title matcher, post-id parse, csv/xlsx parse, 5→6 adapt, row count,
  schema-contract guard (browser-free) + a skip-gated live auto-discovery test.

---

## Cross-cutting cleanup (track separately)
- ✅ Docs refreshed (2026-06-15): the stale `docs/auto-ranking-refresh-assessment/`, `DATA_SOURCES.md`,
  and `WEEKLY_RANKINGS_SETUP.md` were replaced by current docs — [`docs/data-sources.md`](docs/data-sources.md),
  [`docs/usage.md`](docs/usage.md), and a rewritten API reference.
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
