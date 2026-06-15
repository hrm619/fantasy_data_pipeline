# TODO — fantasy_data_pipeline

Working backlog. Detailed per-source plan and status live in [`SCRAPER-PLAN.md`](SCRAPER-PLAN.md).
Status legend: ⬜ not started · 🟡 in progress · ✅ done · 🔒 needs credentials

---

## 🔜 NEXT TASK — Automate the paywalled sources (#5–#7)

The four free/public sources are automated (ADP, DraftSharks, Hayden Winks, FantasyPros rankings).
The remaining three are behind logins/paywalls and were previously "manual by design." **Next up:
automate them via authenticated browser sessions** (Playwright, same pattern as the DraftSharks
fetcher) so the whole `update/` folder can be refreshed with one command.

Shared prerequisite: an **auth strategy** — secure handling of the user's credentials (env vars /
secret store), logged-in Playwright context, and ToS-aware, polite request rates. No credentials in code.

- 🔒 **#5 FantasyPoints / Barrett (`fpts`)** — subscription, JS-rendered rankings.
  - Goal: logged-in Playwright fetch → emit the `COLUMN_MAPPINGS['fpts']` schema → `Scott Barrett*.csv`.
  - Confirm scoring/format and the exact column layout against a real manual export before building.
- 🔒 **#6 PFF (`pff`)** — premium subscription; the rankings page has an Export/Download.
  - Goal: logged-in Playwright fetch → `COLUMN_MAPPINGS['pff']` schema → `Draft-rankings-export.csv`.
  - Note the second-row-header quirk for weekly/ROS PFF files.
- 🔒 **#7 JJ Zachariason / LateRound (`jj`)** — Patreon-gated Excel attachment.
  - Goal: authenticated Patreon download of the latest `Redraft1QB_*.xlsx` ("Rankings and Tiers" sheet).
  - Hardest auth (Patreon login + locating the latest post); may stay manual if auth proves too brittle.

Acceptance for each: fetched file lands in `update/` and `ff-rankings` consumes it end-to-end
(no column-count mismatch / player-ID crash), with a coverage floor + a network-free schema test.

---

## Cross-cutting cleanup

- ✅ **Season-rollover audit** — `CURRENT_SEASON` (in `config.py`) is now the single source of truth:
  `FILE_MAPPINGS` `fp`/`adp` prefixes + ROS `fpts` pattern, both fetcher `year` defaults, the two
  CLI `--year` defaults, and the HW URL slug all derive from it. Bumping 2025→2026 is now a one-line
  change. Behavior is byte-identical at 2025; locked by `tests/test_config.py` (re-hardcoding fails CI).
  *Note: live `fp`/`adp` data is already 2026-season — bump `CURRENT_SEASON` when the 2026 source files land.*
- ✅ **Verify the manual-source guide** (`docs/auto-ranking-refresh-assessment/manual_source_guide.md`)
  for #5–#7 — filenames/scoring/sheet names checked against `COLUMN_MAPPINGS`/`FILE_MAPPINGS`; added the
  per-source expected-columns lists, JJ per-league prefixes, and the PFF weekly/ROS second-row-header note.
- ✅ **Reconcile `docs/auto-ranking-refresh-assessment/`** with reality — fixed the stale claims (DS/fp
  now automated, not manual/deferred), corrected the ADP count (989→~411 consensus), and documented the
  `ecrData` JSON + headless-Playwright approaches actually shipped. *Note: these two files are duplicated
  at `docs/` root (in-flight reorg) — I synced both copies; pick one canonical location when convenient.*

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
