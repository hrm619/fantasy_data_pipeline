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

- ⬜ **Season-rollover audit** — `2025` is hardcoded across `FILE_MAPPINGS` prefixes and the fetchers'
  `year` defaults; the live `fp`/`adp` data is already 2026-season. Centralize on `CURRENT_SEASON`
  (added in `config.py`) so one bump rolls filenames + URL slugs together. *Highest-leverage cleanup.*
- ⬜ **Verify the manual-source guide** (`docs/auto-ranking-refresh-assessment/manual_source_guide.md`)
  for #5–#7 — filenames, scoring, sheet names — before/while automating them.
- ⬜ **Reconcile `docs/auto-ranking-refresh-assessment/`** with reality (it predates the fetchers:
  remove stale claims, fix player counts, reflect the JSON/headless approaches actually used).

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

- ⬜ **`fp` duplicate `ECR` column** — `BaseProcessor._standardize_output` emits `ECR` twice for the `fp`
  source; the pipeline dedups it in `_organize_final_dataframe`. Harmless; clean up if convenient.
- ⬜ **fantasy-data `test_models.py::test_table_count`** — pre-existing failing test (stale table-count
  assertion), unrelated to the DraftShark sharp reclassification. Verified failing on a clean tree.
