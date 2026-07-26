# Expert Accuracy & Bias Analysis

**Status:** built. `ff-expert-analysis build` loads the tables; `ff-expert-analysis report` prints the
scorecards. Tracked here because it is a research workstream, not pipeline work — it reads a frozen
snapshot and writes its own tables.

```bash
uv run ff-expert-analysis build            # adapters -> ~/.fantasy-data/fantasy_data.db
uv run ff-expert-analysis report           # scorecard, tiers, bias, conviction
uv run ff-expert-analysis report --metric fpts_half --season 2024
uv run ff-expert-analysis report --min-games 12    # sensitivity: it barely moves, see §8
```

**Three columns carry health warnings and are the ones people misread.** `hit_rate` must be read as
`hit_rate_vs_pool` (§4), positional bias must be read as `mean_vor_error_vs_ref` (§3b-bis), and
`tier_stability_95ci` is a stability range, not a confidence interval (§3c).

Code: `src/fantasy_pipeline/analysis/{historical,scorecard}.py`, tests in
`tests/test_expert_analysis.py`.

Goal: score historical preseason expert rankings against what players actually did, and surface
systematic bias. The dataset is a **snapshot** — three seasons that will not change — so the build
is a one-shot drop-and-recreate, not an incremental pipeline. Adding a season is an adapter entry
plus a rebuild; `SUPPLEMENTAL_BOARDS` exists so that is a few lines, not a new code path.

---

## 1. Source data

`data/rankings_historical/` (gitignored, local only). Two kinds of input: the wide **snapshots**,
and per-expert **supplemental boards** that carry one expert's board better than a snapshot did.

| File | Rows | Shape |
|---|---|---|
| `2024 Pre-Season Rankings (August 20 2024).csv` | 217 | Hand-built spreadsheet, bespoke schema |
| `2025 Pre-Season Rankings (August 22 2025).csv` | 270 | This pipeline's own output + extra columns |
| `hw-2023.csv` | 254 | Underdog export — the only 2023 board |
| `hw-2024.csv` | 273 | Underdog export — overall ranks the snapshot lacked |
| `pff-2025.csv` | 512 | PFF's own export, recovered from `raw archive/` |

Every file gets its own adapter. Supplemental boards **override** the snapshot for their
(season, expert) rather than adding a second copy of one expert's opinion — see
`SUPPLEMENTAL_BOARDS` in `analysis/historical.py`.

### Experts and coverage

| Expert | key | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| FantasyPros ECR | `fp` | — | 217 | 254 |
| PFF | `pff` | — | 216 | 448 |
| DraftSharks | `ds` | — | 147 | 245 |
| Hayden Winks | `hw` | 253 | 273 | 242 |
| 4 For 4 | `4for4` | — | 183 | — |
| The Ringer | `ringer` | — | 145 | — |
| Scott Barrett | `fpts` | — | — | 100 |
| JJ Zachariason | `jj` | — | — | 231 |
| Consensus redraft ADP (market) | `adp` | — | 217 | 254 |
| Underdog best-ball ADP (market) | `adp_underdog` | 253 | 273 | — |

**`fp`, `pff`, `ds` and `hw` have comparable overall ranks in 2024 and 2025.** `hw` joined that set
once `hw-2024.csv` supplied his overall ranks — the snapshot carried him positionally only
(`"RB1"`). **2023 is `hw` alone**, so it is a solo accuracy record, not a head-to-head.

These counts are rows **loaded**. The scorecard reports `n_ranked`, which is rows that also join to a
realized outcome, so it is slightly lower — `pff` 2025 loads 448 and scores 426; `hw` loads 253/273
for 2023/2024 and scores 248/271. The gap is players with no PFR outcome row (no NFL snap that
season), not a matching failure.

Excluded by decision: personal/league-mate columns (`HankRank`, `My Rank`, `TARGET`, and the
`SCOTT`/`RYAN`/`JJ`/`HAYDEN`/`JOSH` columns, which exported as 262 rows of `#NAME?` anyway).

### The two markets are not one market

`adp` is **consensus redraft ADP**; `adp_underdog` is **Underdog best-ball ADP**. Best-ball pays for
weekly spikes and never starts anyone, so it systematically bids up high-variance pass-catchers —
a different game at different prices. Where both exist they correlate **0.965**: close enough to be
tempting, not close enough to be the same bet.

They are therefore loaded as **separate market series and never pooled**. Conviction is reported
once per market, in its own block, labelled with the seasons it covers. 2024 carries both precisely
so the divergence can be *measured* rather than assumed. (The 2024 snapshot's own `Underdog` column
was originally excluded as "not an expert ranking" — correct, but it is a legitimate *market*, and
it is what makes 2023's conviction numbers interpretable at all.)

### Known defects — carry these into every result

1. ~~**PFF's 2025 #1 is missing.**~~ **Recovered.** `pff_RK` started at 2 in the snapshot — the
   documented `read_csv` header-detection bug (a blank line before the header meant the first data
   row was consumed as column names), which cost PFF its single highest-conviction call. The
   original export was still sitting in `data/rankings current/raw archive/processed_20250822_1914/`
   from the same day, so it was never actually unrecoverable — nobody had looked there. It now loads
   as the `pff-2025` supplemental board: **Bijan Robinson at rank 1**, and 448 scorable skill players
   instead of 245. Read through the pipeline's own `load_data`, whose fixed header detection is what
   makes rank 1 readable in the first place.
2. **Empty columns.** All six talent/situation grade columns are 0 non-null. `Underdog ADP Pos Rank`
   is 217 `#REF!`.
3. **The 2025 snapshot is pipeline output**, so any pipeline defect live in Aug 2025 is baked in.
4. The 2024 file's `Sum of FPTS` / `FTPS / G` columns are **2023** actuals (prior-season context),
   not outcomes. Verified: CMC 358 = his 2023 half-PPR.

### Outcomes

`data/fpts historical/combined_data.csv` — 2023 (632 rows), 2024 (630) and 2025 (643), with `PPR`,
`FANTPT`, `G`, `VBD`, `POS RANK`. Half-PPR is derived as `(FANTPT + PPR) / 2`. After the skill-position
filter and PFR de-duplication this yields 615 / 620 / 631 scorable outcomes.

Finish ranks are **recomputed on half-PPR** rather than taken from PFR's `POS RANK`/`RK`/`VBD`, which
are computed on PFR's own scoring — otherwise outcomes would be measured in different units than the
board.

---

## 2. Schema (`~/.fantasy-data/fantasy_data.db`)

**`expert_rankings_historical`** — one row per (season, expert, player). Long/tidy, so adding a season
or an expert never changes the schema.

`season`, `as_of_date`, `expert`, `expert_kind`, `player_id`, `overall_rank`, `pos_rank`,
`rank_scope`, `name_as_published`, `source_file` — PK `(season, expert, player_id)`.

- `expert_kind` ∈ `expert` | `consensus` (fp/ECR) | `market` (`adp`, `adp_underdog`). Keeps the
  aggregate and the markets out of expert-vs-expert averages — same reasoning as
  `_NON_CONSENSUS_PREFIXES` on the live board. Note `market` covers **two** series that must not be
  pooled with each other either; see §1.
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

**The curve must be priced IN-SET, and this is the single easiest way to get a wrong answer here.**
The league-wide curve indexes a ~620-player outcome universe while `r` is a rank within a ~250-player
board. The r-th best of a superset beats the r-th best of the subset, so the signed error came out
negative for every expert, in every position, in every season — including the markets — and its
*magnitude tracked board depth*. PFF's 2025 board (426 scorable vs ~240 for everyone else) read as
the least biased at WR purely for reaching further down the curve. This is the same defect
`pos_finish_rank_in_set` fixes in rank space (§7); points space did not get the equivalent treatment
until later. `add_in_set_curves` now prices each board against itself, so `mae_points` is
depth-invariant. Pinned by `test_in_set_pricing_is_invariant_to_board_coverage`.

Once priced in-set the assigned `curve` values are a permutation of the group's own outcomes, which
makes the aggregate an assignment cost rather than a free parameter — and has a consequence, below.

**The diagnostic that explains the gap:** report the **local slope** of the curve — PPG per rank at
each point. That is exactly the quantity that makes rank error and points error diverge, and it turns
"this expert's rank error is bad but points error is fine" into an explanation rather than a puzzle.

**Cross-position comparability.** PPG is not comparable across positions — 18 PPG is replaceable for a
QB and elite for an RB. Any analysis that mixes positions (i.e. anything keyed on *overall* rank)
must first convert to **value over replacement**, using the pipeline's documented baselines (QB 6,
RB 24, WR 30, TE 12). Positional analyses can use raw PPG.

### 3b-bis. Bias has to be measured ACROSS positions, not within one

Within a position, an in-set curve makes the signed points error **exactly zero by construction** —
the expert's ranks and the realized ranks are permutations of the same set, so the assigned and
realized multisets are identical. That is the same degeneracy §7 records for signed *rank* error, and
it kills the design's original escape hatch: signed points error does **not** "carry the answer".
Both are zero. The version that appeared non-zero was measuring board depth, per above.

So signed bias lives on the **overall** board, in **VOR** (`positional_bias`). There the permutation
constraint binds at board level rather than within a position, so the total is zero while the
per-position means are free to move — an expert who spends early overall slots on RBs runs negative
on RB and positive elsewhere. Two corrections are needed before it means anything:

1. **Difference against a reference.** Every expert *and* every market carries the same large shared
   offset (TE ≈ +50, QB ≈ −40 on the 2024–25 boards) because the VOR baselines interact with how deep
   each position is drafted. That is the replacement levels talking, not judgement.
2. **Then centre within (season, expert).** Each board's VOR error sums to zero over *its own*
   players, so when two boards differ in size the two zero-sums are taken over different populations
   and the raw difference inherits a global offset that tracks board size: 2024 `ds` (146 players)
   came out **+18.96 across every position** and `ringer` (144) **+20.14**, while `fp` and `pff` — both
   214, exactly `adp`'s size — came out at **0.00**. Arithmetic, not judgement. Centring leaves a tilt
   summing to ~zero across positions, which is the only question the comparison can answer: *which
   positions did this expert favour relative to the market.*

Read `mean_vor_error_vs_ref`, never the raw column.

### 3c. Tier space — the human-readable question

Tiers are derived **from realized outcomes** (ex post), per (season, position), by natural-breaks /
largest-gap segmentation of the PPG distribution — never by hand-picked cutoffs, which would let the
boundaries be chosen to produce a conclusion.

`tier_hit` = did the expert's rank imply the tier the player actually landed in?

**This metric is knife-edge and must be reported as such.** A player 0.1 PPG from a boundary flips
tiers, so tier hit-rate reads as precise while resting on an arbitrary line. Two mitigations now
ship: `tier_edge_median` (median distance from a scored player to the nearest break, in metric
units) and `tier_stability_95ci`.

**The stability result: largest-gap segmentation does not survive resampling.** Re-deriving the
breaks from a bootstrap sample and re-scoring gives ranges that routinely *exclude* the point
estimate — 2024 `ds` scores 0.500 against a range of [0.25, 0.41]. That would be incoherent for a
sampling CI, which is why it is **reported as a stability range and explicitly not as a confidence
interval**. The cause is mechanical: a resample of n values contains only ~63% of the distinct
originals, and the missing ones merge adjacent gaps in the dense low tail, so the largest-gap rule
relocates the breaks wholesale — 2024 RB cuts sit at 12.2–20.5 on the real data and wander to
5.9–9.2 under resampling. Deduplicating first does not help (tied values have zero gaps and are
never chosen as breaks).

**Practical consequence: tier space is now a PRESENTATION layer, not a result.** It needs boundaries
and the boundaries do not survive resampling, so it prints in its own labelled block rather than
beside the accuracy metrics, where a readable-but-unreliable number could be mistaken for a
load-bearing one. Points space (§3b) needs no boundaries and cannot inherit this — use it for
anything that carries weight. Trying 1-D k-means or Fisher–Jenks was considered and dropped: it would
change *which* arbitrary boundaries are used without making tier membership less knife-edge, and the
`tier_edge_median` column already exposes how close to a line each expert's hits sit.

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

Reported as conviction hit-rate and mean value added per call, sliced by **expert**, **expert ×
position**, and **expert × draft region** (rounds 1-3 / 4-8 / 9+). Three references are reported:
`adp`, `adp_underdog`, and **`fp`** — "diverging from the expert consensus" and "diverging from the
market" are different bets, and only one of them is a price.

**Everything is priced on the set both boards ranked.** Against the league-wide curve `value_added`
was systematically negative (same defect as §3b), which tilts `sign(value_added)` toward "the expert
was right to fade him" no matter who the expert is. Re-ranking both sides within the common set and
pricing off that set's own curve makes `value_added` average **exactly zero** over all calls, so the
sign test is a fair coin. Re-ranking is also what makes two boards of different depths commensurable
at all. Pinned by `test_value_added_is_centred_on_the_common_set`.

**Draft region is read from the reference's OVERALL rank.** `DRAFT_REGIONS` is defined in overall-pick
terms (rounds 1-3 = picks 1-36); it was being fed a *positional* rank, which put every position's top
36 in "rounds 1-3" — TE36 is not a third-round pick.

### Do not compare conviction hit-rate to 0.5

The sign test gets **mechanically easier as the disagreement grows**. Pooled across every expert, hit
rate climbs monotonically with `|delta_value|`:

| `|delta_value|` quantile | 0.00–0.50 | 0.50–0.80 | 0.80–0.95 | 0.95–1.00 |
|---|---|---|---|---|
| hit rate | 0.380 | 0.528 | 0.615 | 0.750 |

Selecting the top 20% by construction lands *everyone* well above a coin flip — an expert at 0.68 has
done nothing but make big calls. `hit_rate_vs_pool` differences against the pooled rate over the same
selected set, which removes the gradient and leaves the part that is about the expert. It sums to
~zero across experts by construction. **Read that column, not `hit_rate`.**

**The pool is computed within each non-expert slice level**, because the gradient recurs one level
down: late-round calls hit far more often than early ones (`rounds 9+` runs ~0.63–0.91 against
`rounds 1-3`'s ~0.23–0.73). A single global pool would put every expert's `rounds 9+` cell above its
`rounds 1-3` cell and read as "everyone is better late", which is a property of the region, not of
anyone. Comparing experts is only meaningful *inside* a slice — and the tables sort on
`hit_rate_vs_pool` for the same reason.

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
- **Multiple comparisons.** ~4 comparable experts × 4 positions × 3 regions ≈ 48 cells; at α = 0.05
  roughly two will look "significant" by chance. Results are **hypothesis-generating** and are
  reported with intervals rather than p-values. There is deliberately **no formal testing and no FDR
  control**: with three seasons and intervals that already overlap completely (below), a p-value
  would add ceremony rather than information, and formalising the testing would invite exactly the
  "which cell is significant" reading this section exists to prevent. Removed as a stated goal rather
  than left as an unbuilt promise.
- **Sample size, plainly.** Three seasons, ~250 players each, four comparable experts in 2024–2025
  and one in 2023. Spearman differences below ~0.05 are indistinguishable from noise. This can rank
  experts *directionally* and surface patterns worth watching. It cannot establish that one expert is
  better than another, and no amount of slicing will change that — slicing makes it worse.
- **The intervals confirm this, and they are the point.** `spearman_common_95ci` is a percentile
  bootstrap over players. On the 2024 board the five experts span 0.675–0.727 with intervals like
  [0.59, 0.76] and [0.64, 0.79] — **total overlap**. The scorecard prints a clean descending ordering
  and that ordering is noise. Read the intervals before believing any ranking; where they overlap,
  the gap between point estimates is not evidence.
- **Post-hoc tiers.** See §3c.
- **Board depth is not skill.** Any metric that prices one board against a curve indexed on a
  different set will rank the deepest board best. See §3b — this had actually happened.
- **Survivorship.** Players ranked but who never played are documented exclusions, not silent drops.
  (PFF's missing #1 was in this list until the original export was recovered; see §1.)

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
6. Report — `ff-expert-analysis report`. (There is no notebook and none is planned; the CLI report is
   the deliverable. `--season`, `--metric` and `--min-games` cover the slicing a notebook would.)

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
  read as "no bias" for every expert. ~~Signed **points** error carries the answer instead.~~
  **That second half was wrong**, and stayed wrong for a while because it produced plausible numbers:
  signed points error is zero by construction too, for exactly the same reason, once the curve is
  priced in-set. The non-zero values it was printing came from pricing a ~250-player board against a
  ~620-player league curve and were a measure of board depth. Signed bias moved to the overall board
  in VOR — see §3b-bis, which also covers the two corrections it needs.
- **Positional ranks are derived from overall ranks**, not read from the published columns. Most
  experts publish an overall board only, and the published positional columns are not dependable —
  the 2025 snapshot's `POS ECR` is all 1s. A published positional rank is used only where the expert
  gave no overall rank (2024 Hayden Winks).
- **Conviction thresholds are taken among actual disagreements.** Players an expert placed exactly
  where the market did carry `delta_value == 0`; leaving them in the quantile basis drags the cutoff to
  zero and promotes trivial calls into "big" ones.

### Discovered while folding in the supplemental boards

- **Underdog publishes best-ball ADP as a decimal (`1.2`, `2.3`, `6.4`), and `overall_rank` is
  stored as `Int64`.** Passing the raw value through truncates `1.2` and `1.9` to the same `1`,
  manufacturing ties and quietly scrambling the top of the board. The market series therefore carries
  a **rank of the ADP**, not the ADP itself. The snapshot's own ADP column happens to be integral, so
  this trap appears only on the Underdog files — pinned by
  `test_supplemental_underdog_adp_is_ranked_not_passed_through`. (Same family as the DraftSharks
  `round.pick` trap in the main pipeline: numeric-looking, plausible, and wrong.)
- **`hw-2024.csv` is the same board as the snapshot's HW column, not a different vintage.** Derived
  positional ranks correlate **0.994** against the snapshot's published ones. That is what justifies
  overriding rather than treating it as a second source — checked before the swap, not assumed.
- **Two name aliases were blocking real players.** `Devon Achane` (the file's spelling; PFR and the
  dict say `DeVon Achane`, `AchaDe00`) and `Mitch Trubisky` (PFR: `Mitchell Trubisky`, `TrubMi00`) —
  both verified against PFR ground truth and position-checked before being added to
  `player_key_dict.json`. `DeWayne McBride` remains unmatched and correctly so: PFR has no such
  player, only Tre and Trey McBride, who are different people. Unverifiable is not wrong.

## 8. Open questions

- ~~Games-played floor for PPG: 8 is a placeholder; sensitivity check it.~~ **Answered: it is not
  load-bearing.** Swept 1/4/6/8/10/12/14. `spearman_ppg` moves at most **0.045** across floors 4–12 —
  inside the ~0.05 noise band §5 already documents — and the only ordering changes are swaps between
  pairs whose intervals overlap completely (2024 `fp`/`pff`, 2025 `adp`/`hw`). 8 stays as the default
  and is now exposed as `--min-games` so the check is repeatable rather than a buried assumption.
- ~~Tier segmentation method — pick by stability under bootstrap.~~ **Answered, badly:** largest-gap
  is *not* stable (§3c). **Resolved by demotion**: tier space is a presentation layer, printed in its
  own block, and nothing load-bearing reads it. k-means/Fisher–Jenks was dropped as a non-fix — it
  changes which arbitrary boundaries are used without making membership less knife-edge.
- ~~Should `hw` 2024 (positional-only) be included in positional analyses?~~ **Resolved** —
  `hw-2024.csv` supplies overall ranks, so `hw` is now scored exactly like every other expert in all
  three seasons and needs no special case.
- ~~Is a third season available?~~ **2023 is in**, via `hw-2023.csv`. But it is **one expert**, so it
  strengthens HW's individual record and adds a third value curve without enabling any new
  head-to-head. A 2023 board for `fp`/`pff`/`ds` would be worth more than anything else on this list.
- ~~Does `adp_underdog` belong in the cross-season overlap set?~~ **Resolved: no, and neither does
  forcing the question.** It has 2023+2024, `adp` has 2024+2025 — neither market spans all three
  seasons, so admitting either shrinks the overlap for a series that is not an expert opinion anyway.
  The overlap set stays `fp, pff, ds, hw, adp` and each market is reported beside it in its own
  conviction block, which is where the market comparison actually belongs.
- **Still the highest-value item: a 2023 board for `fp`/`pff`/`ds`.** It is what converts 2023 from a
  solo record into a third head-to-head, and it is data acquisition rather than code. Worth checking
  `data/rankings current/raw archive/` the way `pff-2025` was recovered.
