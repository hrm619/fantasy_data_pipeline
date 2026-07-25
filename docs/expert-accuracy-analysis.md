# Expert Accuracy & Bias Analysis

**Status:** built. `ff-expert-analysis build` loads the tables; `ff-expert-analysis report` prints the
scorecards. Tracked here because it is a research workstream, not pipeline work — it reads a frozen
snapshot and writes its own tables.

```bash
uv run ff-expert-analysis build            # adapters -> ~/.fantasy-data/fantasy_data.db
uv run ff-expert-analysis report           # scorecard, bias, conviction
uv run ff-expert-analysis report --metric fpts_half --season 2024
```

Code: `src/fantasy_pipeline/analysis/{historical,scorecard}.py`, tests in
`tests/test_expert_analysis.py`.

Goal: score historical preseason expert rankings against what players actually did, and surface
systematic bias. The dataset is a **snapshot** — two seasons that will not change — so the build is
a one-shot drop-and-recreate, not an incremental pipeline.

---

## 1. Source data

`data/rankings_historical/` (gitignored, local only):

| File | Rows | Shape |
|---|---|---|
| `2024 Pre-Season Rankings (August 20 2024).csv` | 217 | Hand-built spreadsheet, bespoke schema |
| `2025 Pre-Season Rankings (August 22 2025).csv` | 270 | This pipeline's own output + extra columns |

The two files share no schema, so each gets its own adapter.

### Experts and coverage

| Expert | key | 2024 | 2025 |
|---|---|---|---|
| FantasyPros ECR | `fp` | 217 | 270 |
| PFF | `pff` | 216 | 261 |
| DraftSharks | `ds` | 147 | 261 |
| Hayden Winks | `hw` | 217 *(positional only)* | 257 |
| 4 For 4 | `4for4` | 183 | — |
| The Ringer | `ringer` | 145 | — |
| Scott Barrett | `fpts` | — | 100 |
| JJ Zachariason | `jj` | — | 243 |
| ADP (market) | `adp` | 217 | 270 |

**Only `fp`, `pff` and `ds` have comparable overall ranks in both seasons.** `hw` overlaps but 2024
is positional-only (`"RB1"`), so it is comparable at positional granularity only. Everything else is
single-season and usable for within-year work.

Excluded by decision: personal/league-mate columns (`HankRank`, `My Rank`, `TARGET`, and the
`SCOTT`/`RYAN`/`JJ`/`HAYDEN`/`JOSH` columns, which exported as 262 rows of `#NAME?` anyway), and the
2024 `Underdog` column — that is **best-ball ADP, not an expert ranking**.

### Known defects — carry these into every result

1. **PFF's 2025 #1 is missing.** `pff_RK` starts at 2. This is the documented `read_csv`
   header-detection bug (a blank line before the header meant the first data row was consumed as
   column names). Surviving ranks are **true, not shifted** — one player is simply absent, and it is
   PFF's single highest-conviction call. Unrecoverable from these files.
2. **Empty columns.** All six talent/situation grade columns are 0 non-null. `Underdog ADP Pos Rank`
   is 217 `#REF!`.
3. **The 2025 snapshot is pipeline output**, so any pipeline defect live in Aug 2025 is baked in.
4. The 2024 file's `Sum of FPTS` / `FTPS / G` columns are **2023** actuals (prior-season context),
   not outcomes. Verified: CMC 358 = his 2023 half-PPR.

### Outcomes

`data/fpts historical/combined_data.csv` — 2024 (630 rows) and 2025 (643 rows), with `PPR`,
`FANTPT`, `G`, `VBD`, `POS RANK`. Half-PPR is derived as `(FANTPT + PPR) / 2`.

Finish ranks are **recomputed on half-PPR** rather than taken from PFR's `POS RANK`/`RK`/`VBD`, which
are computed on PFR's own scoring — otherwise outcomes would be measured in different units than the
board.

---

## 2. Schema (`~/.fantasy-data/fantasy_data.db`)

**`expert_rankings_historical`** — one row per (season, expert, player). Long/tidy, so adding a season
or an expert never changes the schema.

`season`, `as_of_date`, `expert`, `expert_kind`, `player_id`, `overall_rank`, `pos_rank`,
`rank_scope`, `name_as_published`, `source_file` — PK `(season, expert, player_id)`.

- `expert_kind` ∈ `expert` | `consensus` (fp/ECR) | `market` (adp). Keeps the aggregate and the
  market out of expert-vs-expert averages — same reasoning as `_NON_CONSENSUS_PREFIXES` on the live
  board.
- `rank_scope` ∈ `overall` | `positional`. This is how 2024 Hayden Winks coexists with 2025 `hw_RK`
  without pretending they are the same measurement.

**`player_season_outcomes`** — one row per (season, player_id): `pos`, `team`, `games`, `fpts_half`,
`ppg_half`, `pos_finish_rank`, `overall_finish_rank`, `value_over_replacement`, plus raw
`fpts_ppr`/`fpts_std`/`vbd`.

**`v_expert_rank_vs_outcome`** — the join every analysis reads. Metric definitions live in code, not
in the DB, so they can change without a rebuild.

---

## 3. Scoring: three error spaces, not one

Rank error alone is misleading, because **ranks are not equally spaced in value**. Missing by four
ranks at RB3 is a different mistake from missing by four ranks at RB30. An expert can be "spiritually
correct" — wrong on the literal rank, right about the player's tier of production — and pure rank
error punishes that identically to a real miss.

So every expert is scored in three spaces. All three are reported; they answer different questions.

### 3a. Rank space — the literal question

Spearman ρ, MAE and median absolute rank error, top-12/24/36 precision and recall. This is "how
close was the stated rank", and it stays because it is what people actually claim.

### 3b. Points space — the "spiritually correct" question

The core construction is the **realized value curve**. For each (season, position), sort players by
realized half-PPR PPG descending; `curve[k]` is the k-th best outcome.

An expert who ranked a player at positional rank *r* was forecasting `curve[r]` — the production of
the r-th best player at that position. So:

```
points_error(p) = actual_ppg(p) - curve[rank_expert(p)]
```

This is the mispricing in **PPG**, and it makes "spiritually correct" fall out automatically with no
arbitrary tier boundaries: where the curve is flat, a large rank miss costs almost nothing; where it
is steep, a small rank miss is expensive.

Because ranks are a permutation over a fixed set of slots, the assigned `curve` values are the same
multiset for every expert who ranked the same players — so the aggregate is a fair comparison (it is
an assignment cost, not a free parameter).

**The diagnostic that explains the gap:** report the **local slope** of the curve — PPG per rank at
each point. That is exactly the quantity that makes rank error and points error diverge, and it turns
"this expert's rank error is bad but points error is fine" into an explanation rather than a puzzle.

**Cross-position comparability.** PPG is not comparable across positions — 18 PPG is replaceable for a
QB and elite for an RB. Any analysis that mixes positions (i.e. anything keyed on *overall* rank)
must first convert to **value over replacement**, using the pipeline's documented baselines (QB 6,
RB 24, WR 30, TE 12). Positional analyses can use raw PPG.

### 3c. Tier space — the human-readable question

Tiers are derived **from realized outcomes** (ex post), per (season, position), by natural-breaks /
largest-gap segmentation of the PPG distribution — never by hand-picked cutoffs, which would let the
boundaries be chosen to produce a conclusion.

`tier_hit` = did the expert's rank imply the tier the player actually landed in?

**This metric is knife-edge and must be reported as such.** A player 0.1 PPG from a boundary flips
tiers, so tier hit-rate reads as precise while resting on an arbitrary line. Mitigation: report each
player's **distance to the nearest tier boundary**, and bootstrap the boundaries to give a hit-rate
interval rather than a point estimate. Where the interval is wide, prefer 3b.

### 3d. Availability — run everything twice

All of the above is computed against **realized total** and against **PPG** (with a games-played
floor, ≥8). The gap between them is the availability effect and is reported as a first-class number:
it isolates who systematically over- or under-rates injury-prone players. CMC in 2024 is the
canonical case — ranked ~1, played 4 games, 47.8 points.

---

## 4. Conviction: big deltas vs the market

The question: when an expert departed sharply from ADP, did it pay? Was one expert routinely right
about a position, or about a slice of the draft?

```
delta_rank  = adp_rank - expert_rank                    # positive = expert higher than market
delta_value = curve[adp_rank] - curve[expert_rank]      # what the disagreement actually claims
```

**Select "big" deltas by `delta_value`, not `delta_rank`.** Ten ranks at the top of the board is a
large claim; ten ranks at pick 150 is rounding. Ranking by `delta_rank` would over-sample the late
rounds and make every expert look boldest exactly where it matters least.

Did it pay:

```
value_added = actual_value(p) - curve[adp_rank]         # vs what the market implied
correct     = sign(value_added) == sign(delta_rank)     # right direction, not just right magnitude
```

Reported as conviction hit-rate and mean value added per call, sliced by **expert × position ×
draft region** (rounds 1-3 / 4-8 / 9+), in value-over-replacement units so positions are comparable.

Also worth running against `fp` (the consensus) as the reference instead of `adp`, since "diverging
from the expert consensus" and "diverging from the market" are different bets.

---

## 5. Statistical guardrails

These matter more than any individual metric. The analyses in §4 are exactly the shape that
manufactures confident nonsense.

- **Common-subset restriction.** Head-to-head comparison runs only on players *all compared experts
  ranked*. DraftSharks ranked 147 of 217 in 2024 while FantasyPros ranked all 217 — and ranking fewer
  players means ranking the *safer* ones, which flatters raw error. Coverage is reported next to
  every metric.
- **Minimum cell size.** `expert × position × draft region` over two seasons produces tiny cells.
  "Best at late-round WRs" may be 5–10 players. Cells below a floor (n ≥ 10) report as *insufficient*
  rather than as a number.
- **Multiple comparisons.** ~3 comparable experts × 4 positions × 3 regions ≈ 36 cells; at α = 0.05
  roughly two will look "significant" by chance. Results are **hypothesis-generating**, reported with
  confidence intervals rather than bare p-values, with FDR control where testing is formalised.
- **Sample size, plainly.** Two seasons, ~200 players, three truly comparable experts. Spearman
  differences below ~0.05 are indistinguishable from noise. This can rank experts *directionally* and
  surface patterns worth watching. It cannot establish that one expert is better than another, and no
  amount of slicing will change that — slicing makes it worse.
- **Post-hoc tiers.** See §3c.
- **Survivorship.** Players ranked but who never played, and the missing PFF #1, are documented
  exclusions, not silent drops.

The single highest-value improvement is **more seasons**, not more metrics. The schema is built so
adding one is an adapter plus a load.

---

## 6. Build order

1. Two adapters → `expert_rankings_historical` (2024 names resolve 217/217 to real PFR ids; 2025
   already carries them).
2. `player_season_outcomes` from `combined_data.csv`, half-PPR, recomputed finish ranks.
3. Load to SQLite (drop-and-recreate) + the join view.
4. Scorecard module: §3 metrics with coverage and CIs.
5. Conviction analysis: §4.
6. Notebook / report.

## 7. Things the build discovered

Two defects surfaced only once the data was actually joined. Both are recorded in code with the
reasoning, because both produce plausible numbers rather than errors.

- **JaTavion Sanders appears 16 times in the 2025 snapshot.** That board predates the player-key
  collision fix, and `SandJa01` mapped to both the TE and kicker Jason Sanders. The copies *disagree*
  (ECR 234 on some rows, 254 on others) because they are two different players' rankings under one id.
  `_collapse_duplicate_players` collapses identical copies and **drops disagreeing ones** — there is no
  way to tell which rank is the TE's, and picking one would score a kicker's ranking as a tight end's.
- **Realized rank must be computed within the set the expert ranked.** Scoring against the league-wide
  `pos_finish_rank` made *every* expert look uniformly ~10 ranks optimistic, because experts rank ~217
  players out of a ~620-player outcome universe: a player placed WR30 "finishes WR45 of 180". Both
  sides have to be permutations of the same set (`pos_finish_rank_in_set`).

Two design corrections followed from it:

- **No signed rank error by position.** Within a position the expert's ranks and the realized ranks are
  permutations of the same set, so the signed mean is *exactly zero by construction* — it would have
  read as "no bias" for every expert. Signed **points** error carries the answer instead.
- **Positional ranks are derived from overall ranks**, not read from the published columns. Most
  experts publish an overall board only, and the published positional columns are not dependable —
  the 2025 snapshot's `POS ECR` is all 1s. A published positional rank is used only where the expert
  gave no overall rank (2024 Hayden Winks).
- **Conviction thresholds are taken among actual disagreements.** Players an expert placed exactly
  where the market did carry `delta_value == 0`; leaving them in the quantile basis drags the cutoff to
  zero and promotes trivial calls into "big" ones.

## 8. Open questions

- Games-played floor for PPG: 8 is a placeholder; sensitivity check it.
- Tier segmentation method: natural breaks vs largest-gap vs 1-D k-means — pick by stability under
  bootstrap, not by which looks tidiest.
- Should `hw` 2024 (positional-only) be included in positional analyses, or excluded entirely for
  consistency with its 2025 overall ranks?
- Is a third season available from anywhere (2023 or earlier)? It would do more for confidence than
  any modelling choice here.
