# Fantasy Football Data Sources

This document details all data sources used by the pipeline, organized by league type.

## ROS (Rest of Season) Rankings

### Primary Ranking Sources

| Source | Key | URL | Format |
|--------|-----|-----|--------|
| **FantasyPros** | `fp` | https://www.fantasypros.com/nfl/rankings/ros-half-point-ppr-overall.php?signedin | CSV (header row 1) |
| **Fantasy Points** | `fpts` | https://www.fantasypoints.com/nfl/rankings/rest-of-season/rb-wr-te?season=2025#/ | CSV (separate QB file) |
| **Hayden Winks** | `hw` | https://underdognetwork.com/football/fantasy-rankings/week-6-fantasy-football-rankings-the-blueprint-2025 | CSV (tableDownload.csv) |
| **JJ Zachariason** | `jj` | https://www.patreon.com/posts/141197927?collection=47664 | Excel (sheet: "Rankings and Tiers") |
| **PFF** | `pff` | https://www.pff.com/fantasy/rankings/draft | CSV (header row 2) |
| **DraftShark** | `ds` | https://www.draftsharks.com/ros-rankings/half-ppr | CSV |

### Data Files (Contextual Metrics)

| Source | Key | Description | Fields |
|--------|-----|-------------|--------|
| **Hayden Winks Data** | `hw-data` | Performance projections | HPPR, EXP, DIFF |
| **Fantasy Points Data** | `fpts-data` | Advanced metrics | FPTS, XFP, TD, XTD, TGT, RUSH, etc. |

## Weekly Rankings

### Primary Ranking Sources

| Source | Key | URL Pattern | Format |
|--------|-----|-------------|--------|
| **FantasyPros** | `fp` | https://www.fantasypros.com/nfl/rankings/weekly-half-point-ppr.php | CSV (header row 2) |
| **Fantasy Points** | `fpts` | https://www.fantasypoints.com/nfl/rankings/week-{week} | CSV (The GURU export) |
| **Hayden Winks** | `hw` | https://underdognetwork.com/football/fantasy-rankings | CSV (tableDownload.csv) |
| **JJ Zachariason** | `jj` | https://www.patreon.com/jjzachariason | Excel (Week{X}_RankingsTiers) |
| **PFF** | `pff` | https://www.pff.com/fantasy/rankings/week-{week} | CSV (header row 2) |
| **DraftShark** | `ds` | https://www.draftsharks.com/weekly-rankings/half-ppr | CSV |

### Data Files (Contextual Metrics)

Same as ROS: `hw-data` and `fpts-data`

## Redraft Rankings

### Primary Ranking Sources

| Source | Key | URL | Format |
|--------|-----|-----|--------|
| **FantasyPros** | `fp` | https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php | CSV |
| **Fantasy Points** | `fpts` | https://www.fantasypoints.com/nfl/rankings/draft | CSV (Scott Barrett) |
| **Hayden Winks** | `hw` | https://underdognetwork.com/football/fantasy-rankings | CSV (tableDownload.csv) |
| **JJ Zachariason** | `jj` | https://www.patreon.com/jjzachariason | Excel (Redraft1QB_) |
| **PFF** | `pff` | https://www.pff.com/fantasy/rankings/draft | CSV |
| **DraftShark** | `ds` | https://www.draftsharks.com/rankings-half-ppr | CSV |

### ADP Source

| Source | Key | URL | Description |
|--------|-----|-----|-------------|
| **FantasyPros ADP** | `adp` | https://www.fantasypros.com/nfl/adp/ppr-overall.php | Average Draft Position data |

## Bestball Rankings

Similar to Redraft, but uses different file variants and Underdog ADP:

- **JJ**: Uses "1QBRankings_" instead of "Redraft1QB_"
- **ADP**: Uses "adp-rankings" (Underdog-specific ADP)

## File Naming Conventions

### ROS Files (in `data/rankings current/update/`)

```
2025 NFL Rest of Season Fantasy Rankings  Fantasy Points.csv       # FPTS QB
2025 NFL Rest of Season Fantasy Rankings  Fantasy Points-1.csv     # FPTS RB/WR/TE
FantasyPros_2025_Ros_ALL_Rankings.csv                              # FantasyPros
tableDownload.csv                                                   # Hayden Winks (hw + hw-data)
ROSRankings_Week7.xlsx                                              # JJ Zachariason
Draft-rankings-export-2025.csv                                      # PFF
ros-rankings-half-ppr.csv                                           # DraftShark
fpts-xfp-avg.csv                                                    # FPTS data file
```

### Weekly Files

```
FantasyPros_Week_{X}_Rankings.csv                                   # FantasyPros
The GURU - QB Week {X}.csv                                          # FPTS QB
The GURU - Skill Week {X}.csv                                       # FPTS RB/WR/TE
tableDownload.csv                                                   # Hayden Winks
Week{X}_RankingsTiers.xlsx                                          # JJ Zachariason
Week-{X}-rankings-export.csv                                        # PFF
weekly-rankings-half-ppr.csv                                        # DraftShark
fpts-xfp-avg.csv                                                    # FPTS data file
```

## Data Export Instructions

### FantasyPros
1. Navigate to the appropriate rankings page
2. Sign in to account (required for full data)
3. Export as CSV (button at top of page)
4. Rename to match expected file pattern

### Fantasy Points
1. Navigate to rankings page
2. Use export functionality (if available) or copy table
3. For ROS: Export QB separately from RB/WR/TE
4. Save with standard naming convention

### Hayden Winks (Underdog Network)
1. Navigate to rankings article
2. Use "Download" button on data table
3. File downloads as `tableDownload.csv`
4. Use same file for both `hw` and `hw-data`

### JJ Zachariason (Patreon)
1. Access Patreon post (requires subscription)
2. Download Excel file
3. Keep original filename (contains week/type info)
4. For ROS: Rankings are in second sheet "Rankings and Tiers"

### PFF
1. Navigate to PFF Fantasy rankings
2. Export data (subscription may be required)
3. Save as `Draft-rankings-export-{year}.csv` for ROS
4. Save as `Week-{X}-rankings-export.csv` for weekly

### DraftShark
1. Navigate to appropriate rankings page
2. Export as CSV
3. Save with appropriate filename pattern

## Data Update Frequency

- **Weekly Rankings**: Updated every Tuesday-Wednesday for upcoming week
- **ROS Rankings**: Updated weekly, reflects rest of season outlook
- **Redraft/Bestball**: Updated during draft season (July-August)
- **ADP Data**: Updates continuously during draft season

## Notes

- Some sources require paid subscriptions (PFF, JJ Zachariason, DraftShark)
- FantasyPros requires free account for full data access
- File formats may vary slightly; check column mappings in `src/config.py`
- Always verify column count matches expected mapping before processing
- Keep source URLs updated as websites may change their URL structure
