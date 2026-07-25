# Documentation

Documentation for the `fantasy_data_pipeline` — a multi-source fantasy football rankings
processor. Start with the repo root [`README.md`](../README.md) for the overview.

## Contents

- **[Usage](usage.md)** — install, fetch sources, log in, and consolidate; league types and output.
- **[Data Sources](data-sources.md)** — the seven ranking sources, which are automated vs. manual,
  the `fetch-*` / `login` / `refresh-all` commands, schemas, and saved-session auth.
- **[API Reference](api/source-library.md)** — the `fantasy_pipeline` package: `RankingsProcessor`,
  the `return_dataframe` seam, fetchers, auth, and config.
- **[Expert Accuracy & Bias Analysis](expert-accuracy-analysis.md)** — scoring historical preseason
  rankings against real outcomes: schema, the rank/points/tier scoring design, conviction-vs-market
  analysis, and the statistical guardrails. Research workstream, separate from the pipeline.

## See also

- [`CLAUDE.md`](../CLAUDE.md) — architecture, design patterns, conventions, and gotchas (the
  most detailed reference).
- [`SCRAPER-PLAN.md`](../SCRAPER-PLAN.md) — per-source automation roadmap and status.
- [`TODO.md`](../TODO.md) — working backlog.
