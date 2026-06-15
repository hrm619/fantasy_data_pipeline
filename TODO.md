# TODO — fantasy_data_pipeline

Working backlog. Detailed per-source plan and status live in [`SCRAPER-PLAN.md`](SCRAPER-PLAN.md).
Status legend: ⬜ not started · 🟡 in progress · ✅ done · 🔒 needs credentials

---

## ✅ DONE — Automate the paywalled sources (#5–#7)

All seven ranking sources are now automated. The four free/public ones (ADP, DraftSharks, Hayden Winks,
FantasyPros rankings) plus the three paywalled ones (FantasyPoints, PFF, JJ) — each `update/` source
refreshes with one `ff-rankings fetch-*` command. The whole folder can be refreshed in one pass.

**Auth strategy (decided & built):** saved-session. `ff-rankings login <source>` opens a headed browser
for a one-time manual login; the session persists to `~/.fantasy_pipeline/auth/<source>.json` (outside the
repo) and headless fetchers reuse it via `scraper/auth.load_storage_state`. No passwords in code/env.

- ✅ **#5 FantasyPoints / Barrett (`fpts`)** — saved-session export shipped: `ff-rankings login fpts` +
  `ff-rankings fetch-fpts`. Live-verified 99 players; exact 7-col `COLUMN_MAPPINGS['fpts']` schema. Flow:
  redraft SPA → click "BARRETT'S RANKINGS" tab (title-switch guard) → "Download as CSV". `--url` override
  for re-verification. Fixture + schema-contract + skip-gated live tests.
- ✅ **#6 PFF (`pff`)** — saved-session headless export shipped: `ff-rankings login pff` + `ff-rankings
  fetch-pff`. Live-verified 512 players; structurally identical to the manual export; loads to the exact
  `COLUMN_MAPPINGS['pff']` width. Fixture + schema-contract + skip-gated live tests.
- ✅ **#7 JJ Zachariason / LateRound (`jj`)** — saved-session Patreon **API** fetch + auto-discovery:
  `ff-rankings login jj` + `ff-rankings fetch-jj` (no URL needed — finds the latest 1QB redraft post;
  `--post-url` overrides). Patreon post HTML is Cloudflare-gated, so attachments are read via the JSON API.
  Source changed to a 5-col CSV (Auction dropped) → adapted to the 6-col `COLUMN_MAPPINGS['jj']` width →
  `Redraft1QB_<year>.csv`. Live-verified 250 players. Pure-function + schema-contract + skip-gated live tests.

Acceptance for each: fetched file lands in `update/` and `ff-rankings` consumes it end-to-end
(no column-count mismatch / player-ID crash), with a coverage floor + a network-free schema test.

**✅ #5–#7 COMPLETE — all seven sources now automate via `ff-rankings fetch-*` (paywalled ones behind a
one-time `ff-rankings login <source>`).**

---

## Cross-cutting cleanup

- ✅ **Season-rollover audit** — `CURRENT_SEASON` (in `config.py`) is now the single source of truth:
  `FILE_MAPPINGS` `fp`/`adp` prefixes + ROS `fpts` pattern, both fetcher `year` defaults, the two
  CLI `--year` defaults, and the HW URL slug all derive from it. Bumping 2025→2026 is now a one-line
  change. Behavior is byte-identical at 2025; locked by `tests/test_config.py` (re-hardcoding fails CI).
  *Note: live `fp`/`adp` data is already 2026-season — bump `CURRENT_SEASON` when the 2026 source files land.*
- ✅ **Docs refreshed altogether** (2026-06-15) — the stale source docs (`DATA_SOURCES.md`,
  `WEEKLY_RANKINGS_SETUP.md`, the `manual_source_guide`/`source_feasibility` pair, the
  `auto-ranking-refresh-assessment/` dir, and the historical `docs/development/` summaries) were replaced
  by current, accurate docs: [`docs/data-sources.md`](docs/data-sources.md), [`docs/usage.md`](docs/usage.md),
  a rewritten [`docs/api/source-library.md`](docs/api/source-library.md), and a refreshed `docs/README.md`.

---

## Deferred / optional

- ⬜ **Sleeper ADP option for #1** — no free true-Sleeper source exists (Sleeper API has no ADP endpoint;
  FantasyPros dropped per-platform). Options if revisited: DraftSharks `/adp/sleeper` scrape (Sleeper-labeled,
  fragile), FantasyPros logged-in export (needs creds), or FFC API (platform-agnostic proxy, not true Sleeper).
- 🟡 **Harden `_TableParser`** — only the ADP fetcher still uses it (fp uses JSON, ds uses Playwright). The
  text-node fusion edge case hasn't bitten ADP; revisit only if ADP names break.
- ⬜ **Redraft Hayden Winks** — no predictable Underdog URL; stays manual unless one emerges.

---

## Known issues (pre-existing, not introduced by the scraper work)

- ✅ **`fp` duplicate `ECR` column** — fixed at the source: `_standardize_output`'s optional-column loop
  now skips columns already promoted into `ranking_columns` (fp's `ECR`/`POS ECR`), so they're emitted
  once. Column order unchanged; no-op for non-fp sources. Downstream dedup in `_organize_final_dataframe`
  is now redundant for this case (left in place as a harmless safety net).
- ⬜ **fantasy-data `test_models.py::test_table_count`** — pre-existing failing test (stale table-count
  assertion), unrelated to the DraftShark sharp reclassification. Verified failing on a clean tree.
- ⬜ **PFF loader drops the #1 overall player** — `data/loader.load_data` mis-detects the header on the
  PFF export (title row + blank + real `Overall Rank` header): it skips the real header and consumes the
  RK=1 row (e.g. Gibbs) as column names, so PFF loses its #1 overall (512 → 511 rows). **Pre-existing** —
  identical on the manual file and the `fetch-pff` output (surfaced during #6, not caused by it). Fix is a
  small header-detection tweak in `loader.py` for the title-row case.
