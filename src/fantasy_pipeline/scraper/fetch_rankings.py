"""Automated fetchers for ranking sources that support public access.

Each fetcher downloads data and saves it as a CSV in the pipeline's update/ directory
with the filename pattern expected by FILE_MAPPINGS in config.py.
"""

import csv
import json
import os
import re
from html.parser import HTMLParser

import requests

from fantasy_pipeline.config import CURRENT_SEASON


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class _TableParser(HTMLParser):
    """Simple HTML table parser — extracts all rows from the first data table."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.current_cell = ""
        self.table_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_depth += 1
            if self.table_depth == 1:
                self.in_table = True
        if self.in_table and tag == "tr":
            self.in_row = True
            self.current_row = []
        if self.in_row and tag in ("td", "th"):
            self.in_cell = True
            self.current_cell = ""

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data.strip()

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            self.current_row.append(self.current_cell)
        if tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        if tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_table = False


# Column layout the pipeline's 'adp' source expects (must equal COLUMN_MAPPINGS['adp']).
# MARKET INDEX / RT are positional placeholders the pipeline discards after the
# positional rename, so they are emitted blank. ADP holds the consensus AVG.
ADP_OUTPUT_COLUMNS = ["PLAYER NAME", "TEAM", "BYE", "POS", "ADP", "MARKET INDEX", "RT"]


def _parse_player_cell(cell: str) -> tuple[str, str, str]:
    """Split a 'PlayerNameTEAM(Bye)' cell into (name, team, bye).

    Handles a trailing injury designation (e.g. 'O'/'Q'/'IR') after the bye.
    Falls back to (cell, '', '') when the pattern doesn't match.
    """
    match = re.match(r"(.+?)([A-Z]{2,3})\((\d+)\)[A-Z]*$", cell.strip())
    if match:
        return match.group(1).strip(), match.group(2), match.group(3)
    return cell.strip(), "", ""


def _parse_fantasypros_adp(html: str) -> list[dict]:
    """Parse FantasyPros ADP HTML into rows keyed by ADP_OUTPUT_COLUMNS.

    The public page serves a single consensus table:
        Rank | PlayerTeam(Bye) | POS | AVG
    The consensus AVG becomes ADP; MARKET INDEX / RT are left blank (the page no
    longer exposes per-platform ADP, and the pipeline discards those columns anyway).
    """
    parser = _TableParser()
    parser.feed(html)

    if len(parser.rows) < 2:
        raise RuntimeError(f"Failed to parse ADP table — only {len(parser.rows)} rows found")

    players = []
    for row in parser.rows[1:]:
        if len(row) < 4:
            continue

        rank = row[0].strip()
        if not rank.isdigit():
            continue

        name, team, bye = _parse_player_cell(row[1])
        pos = re.sub(r"\d+$", "", row[2].strip())  # 'RB1' -> 'RB'
        adp = row[3].strip()                        # consensus AVG (last column)

        players.append({
            "PLAYER NAME": name,
            "TEAM": team,
            "BYE": bye,
            "POS": pos,
            "ADP": adp,
            "MARKET INDEX": "",
            "RT": "",
        })

    return players


def fetch_fantasypros_adp(output_dir: str, year: int = CURRENT_SEASON, min_players: int = 200) -> str:
    """Fetch FantasyPros consensus ADP and save a pipeline-ready CSV.

    Writes the 7-column layout the pipeline's 'adp' source expects
    (`FantasyPros_<year>_Overall_ADP_Rankings.csv`), using the consensus AVG as ADP.
    Per-platform ADP (e.g. Sleeper) is not exposed by the public page.

    Args:
        output_dir: Directory to save the CSV (the pipeline's update/ folder).
        year: Season year for the filename (the page always serves the live season).
        min_players: Coverage floor — raise if fewer rows parse (layout drift guard).

    Returns:
        Path to the saved CSV file.

    Raises:
        RuntimeError: if fewer than `min_players` rows parse.
    """
    url = "https://www.fantasypros.com/nfl/adp/ppr-overall.php"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    players = _parse_fantasypros_adp(response.text)
    if len(players) < min_players:
        raise RuntimeError(
            f"Only {len(players)} players parsed (expected >= {min_players}); "
            "FantasyPros ADP page layout may have changed"
        )

    filename = f"FantasyPros_{year}_Overall_ADP_Rankings.csv"
    output_path = os.path.join(output_dir, filename)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ADP_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(players)

    print(f"ADP fetched: {len(players)} players saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# FantasyPros expert consensus rankings (fp) — embedded ecrData JSON
# ---------------------------------------------------------------------------

# Column layout the pipeline's 'fp' source expects (must equal COLUMN_MAPPINGS['fp']).
# SOS / ECR VS ADP are discarded by the processor after the positional rename, so they
# are emitted blank. POS holds the bare position (the pipeline strips any rank digits).
FP_OUTPUT_COLUMNS = ["ECR", "TIER", "PLAYER NAME", "TEAM", "POS", "BYE", "SOS", "ECR VS ADP"]

# Scoring format -> FantasyPros cheatsheet URL. The cheatsheet pages embed the full
# rankings as a `var ecrData = {...}` JSON blob, available even in the offseason (when
# the /rankings/*-overall.php table pages 302-redirect to consensus-cheatsheets).
FP_CHEATSHEET_URLS = {
    "ppr": "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php",
    "half-ppr": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php",
    "standard": "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
}


def _parse_fantasypros_rankings(html: str) -> list[dict]:
    """Parse FantasyPros rankings from the embedded `ecrData` JSON into fp-schema rows.

    The cheatsheet page embeds `var ecrData = {... "players": [...] ...};`. Each player
    maps to the 8-col COLUMN_MAPPINGS['fp'] layout (SOS / ECR VS ADP left blank — the
    pipeline discards them).
    """
    match = re.search(r"var\s+ecrData\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not match:
        raise RuntimeError(
            "Could not find ecrData JSON on the FantasyPros rankings page — layout changed"
        )
    players = json.loads(match.group(1)).get("players", [])

    rows = []
    for p in players:
        rows.append({
            "ECR": p.get("rank_ecr", ""),
            "TIER": p.get("tier", ""),
            "PLAYER NAME": p.get("player_name", ""),
            "TEAM": p.get("player_team_id", ""),
            "POS": p.get("player_position_id", ""),
            "BYE": p.get("player_bye_week", ""),
            "SOS": "",
            "ECR VS ADP": "",
        })
    return rows


def fetch_fantasypros_rankings(output_dir: str, year: int = CURRENT_SEASON,
                               scoring: str = "ppr", min_players: int = 200) -> str:
    """Fetch FantasyPros expert consensus rankings (fp) and save a pipeline-ready CSV.

    Reads the embedded `ecrData` JSON from the cheatsheet page (works year-round, unlike
    the /rankings/*-overall.php table which 302-redirects in the offseason) and writes the
    8-col COLUMN_MAPPINGS['fp'] layout to `FantasyPros_<year>_Draft_ALL_Rankings.csv`.

    Args:
        output_dir: Directory to save the CSV (the pipeline's update/ folder).
        year: Season year for the filename (must match FILE_MAPPINGS' fp prefix).
        scoring: One of 'ppr' (default), 'half-ppr', 'standard'.
        min_players: Coverage floor — raise if fewer rows parse (layout drift guard).

    Returns:
        Path to the saved CSV file.

    Raises:
        ValueError: if `scoring` is unknown.
        RuntimeError: if the ecrData blob is missing or fewer than `min_players` parse.
    """
    if scoring not in FP_CHEATSHEET_URLS:
        raise ValueError(f"Unknown scoring {scoring!r}; choose from {sorted(FP_CHEATSHEET_URLS)}")

    response = requests.get(
        FP_CHEATSHEET_URLS[scoring], headers={"User-Agent": USER_AGENT}, timeout=30
    )
    response.raise_for_status()

    players = _parse_fantasypros_rankings(response.text)
    if len(players) < min_players:
        raise RuntimeError(
            f"Only {len(players)} players parsed (expected >= {min_players}); "
            "FantasyPros rankings page layout may have changed"
        )

    filename = f"FantasyPros_{year}_Draft_ALL_Rankings.csv"
    output_path = os.path.join(output_dir, filename)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FP_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(players)

    print(f"FP rankings fetched: {len(players)} players saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# DraftSharks (headless-browser fetcher)
# ---------------------------------------------------------------------------

DRAFTSHARKS_URL = "https://www.draftsharks.com/rankings/half-ppr"
DS_OUTPUT_FILENAME = "rankings-half-ppr.csv"

# The exact header DraftSharks' client-side "Export Rankings" CSV emits, in order.
# This is what the pipeline renames POSITIONALLY into COLUMN_MAPPINGS['ds'] (14 cols).
DS_EXPORT_HEADER = [
    "Rank", "Team", "Player", "Fantasy Position", "Games", "ADP", "Bye", "SOS",
    "InjuryRisk", "Floor Proj", "Consensus Proj", "DS Proj", "CeilingProj", "3D Value",
]

# Pipeline-facing column order (must equal COLUMN_MAPPINGS['ds']). Used only when we
# fall back to reading the rendered DOM and must assemble the export layout ourselves.
DS_OUTPUT_COLUMNS = [
    "RK", "TEAM", "PLAYER NAME", "POS", "G", "DS ADP", "BYE", "SOS",
    "INJURY RISK", "FLOOR PROJ", "CONS PROJ", "DS PROJ", "CEILING PROJ", "3D VALUE",
]

# A mobile UA + small viewport are what reveals the *ungated* export button. On
# desktop the only visible "Export Rankings" control is gated (href="/login"); the
# mobile-export-button instead runs the client-side `handleExport` Blob download,
# which produces the full board with no login.
_DS_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
_DS_MOBILE_VIEWPORT = {"width": 390, "height": 844}


def _require_playwright():
    """Import Playwright lazily; raise a friendly install hint if unavailable."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "DraftSharks fetch needs Playwright (optional 'headless' extra). Install it with:\n"
            '  uv pip install -e ".[headless]"\n'
            "  playwright install chromium"
        ) from exc
    from playwright.sync_api import sync_playwright
    return sync_playwright


def _ds_dom_row_to_output(cells: list[str]) -> dict | None:
    """Map a fully-rendered DOM ranking row (14 ordered cells) to the pipeline schema.

    Pure helper so the DOM-fallback path is unit-testable without a browser. The DOM
    table mirrors the export's column order, so cells map positionally onto
    DS_OUTPUT_COLUMNS. Returns None for non-player rows (e.g. a non-numeric rank).
    """
    cells = [c.strip() for c in cells]
    if len(cells) < len(DS_OUTPUT_COLUMNS):
        return None
    if not cells[0].lstrip().rstrip(".").isdigit():
        return None
    return dict(zip(DS_OUTPUT_COLUMNS, cells[: len(DS_OUTPUT_COLUMNS)]))


def _ds_capture_export_csv(output_path: str) -> int:
    """Drive a headless browser to click the ungated Export button and save its CSV.

    Returns the number of data rows written. Uses the mobile viewport/UA so the
    `handleExport` (Blob) export button is reachable rather than the gated /login one.
    """
    sync_playwright = _require_playwright()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # browser binary missing
            raise RuntimeError(
                "Could not launch Chromium. Install the browser with:\n"
                "  playwright install chromium"
            ) from exc
        try:
            context = browser.new_context(
                accept_downloads=True,
                viewport=_DS_MOBILE_VIEWPORT,
                user_agent=_DS_MOBILE_UA,
            )
            page = context.new_page()
            page.goto(DRAFTSHARKS_URL, wait_until="domcontentloaded", timeout=60000)

            # The ungated export is the mobile variant running the client-side
            # `handleExport` Blob download (the "Export" action — not "Print", and
            # not the gated auction-values export).
            export_btn = page.locator("a.mobile-export-button")
            export_btn.wait_for(state="attached", timeout=30000)

            with page.expect_download(timeout=30000) as download_info:
                export_btn.click()
            download = download_info.value
            download.save_as(output_path)
        finally:
            browser.close()

    with open(output_path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise RuntimeError("DraftSharks export produced an empty CSV")
    header = [h.strip() for h in rows[0]]
    if header != DS_EXPORT_HEADER:
        raise RuntimeError(
            "DraftSharks export header changed — expected "
            f"{DS_EXPORT_HEADER}, got {header}. The export layout may have changed."
        )
    return len(rows) - 1


def fetch_draftsharks(output_dir: str, min_players: int = 150) -> str:
    """Fetch DraftSharks half-PPR rankings via a headless browser and save a CSV.

    DraftSharks' rankings page is a JS-rendered SPA: static HTML exposes only ~25
    players with no projections, so a real browser is required. This drives the
    page's own client-side "Export Rankings" button (`handleExport`) and captures
    the resulting Blob download — that CSV is the exact 14-column layout the pipeline
    consumes (renamed positionally into COLUMN_MAPPINGS['ds']).

    Args:
        output_dir: Directory to save the CSV (the pipeline's update/ folder).
        min_players: Coverage floor — raise if fewer rows are captured (the full
            board is ~300+, so this guards against silent breakage).

    Returns:
        Path to the saved CSV file ('rankings-half-ppr.csv').

    Raises:
        RuntimeError: if Playwright/Chromium is unavailable, the export header
            drifts, or fewer than `min_players` rows are captured.
    """
    output_path = os.path.join(output_dir, DS_OUTPUT_FILENAME)
    row_count = _ds_capture_export_csv(output_path)

    if row_count < min_players:
        raise RuntimeError(
            f"Only {row_count} DraftSharks players captured (expected >= {min_players}); "
            "the export may be gated or the page layout may have changed"
        )

    print(f"DraftSharks fetched: {row_count} players saved to {output_path}")
    return output_path
