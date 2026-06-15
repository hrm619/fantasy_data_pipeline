"""Automated fetchers for ranking sources that support public access.

Each fetcher downloads data and saves it as a CSV in the pipeline's update/ directory
with the filename pattern expected by FILE_MAPPINGS in config.py.
"""

import csv
import io
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


# ---------------------------------------------------------------------------
# PFF (paywalled — saved-session headless fetcher)
# ---------------------------------------------------------------------------

PFF_RANKINGS_URL = "https://www.pff.com/fantasy/rankings/draft"

# The 9-col header row inside PFF's "Export"/"Download" CSV (the file the manual
# workflow already drops as Draft-rankings-export-<year>.csv). The pipeline finds this
# header row (the file has a title row above it) and renames POSITIONALLY into
# COLUMN_MAPPINGS['pff'].
PFF_EXPORT_HEADER = [
    "Overall Rank", "Full Name", "Team Abbreviation", "Position", "Position Rank",
    "Bye Week", "ADP", "Projected Points", "Auction Value",
]


def _pff_output_filename(year: int) -> str:
    """Filename matching FILE_MAPPINGS' 'Draft-rankings-export' prefix."""
    return f"Draft-rankings-export-{year}.csv"


def _click_pff_export(page) -> None:
    """Click PFF's rankings Export/Download control.

    PFF's exact selector isn't knowable without a logged-in DOM, so this tries the
    common patterns in order (role/text). Adjust here if the live page differs —
    keep the candidates list as the single place selectors live.
    """
    candidates = [
        lambda: page.get_by_role("button", name=re.compile(r"export", re.I)),
        lambda: page.get_by_role("link", name=re.compile(r"export", re.I)),
        lambda: page.get_by_role("button", name=re.compile(r"download", re.I)),
        lambda: page.get_by_text(re.compile(r"^\s*export\s*$", re.I)),
    ]
    last_exc = None
    for make in candidates:
        try:
            loc = make().first
            loc.wait_for(state="visible", timeout=8000)
            loc.click()
            return
        except Exception as exc:  # selector not present / not clickable — try next
            last_exc = exc
            continue
    raise RuntimeError(
        "Could not find PFF's Export/Download control. The page layout may have "
        f"changed — update _click_pff_export selectors. Last error: {last_exc}"
    )


def _pff_capture_export_csv(output_path: str, storage_state: str) -> int:
    """Drive a logged-in headless browser to export PFF rankings; save the CSV.

    Reuses the saved session (`storage_state`) so no password is handled here.
    Returns the number of data rows written (rows after the 'Overall Rank' header).
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
                storage_state=storage_state,
            )
            page = context.new_page()
            page.goto(PFF_RANKINGS_URL, wait_until="domcontentloaded", timeout=60000)

            with page.expect_download(timeout=30000) as download_info:
                _click_pff_export(page)
            download = download_info.value
            download.save_as(output_path)
        finally:
            browser.close()

    return _validate_pff_csv(output_path)


def _validate_pff_csv(output_path: str) -> int:
    """Validate the saved PFF CSV's header and return its data-row count.

    The export carries a title row above the real header, so we locate the
    'Overall Rank' row and validate the 9 columns there.
    """
    with open(output_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise RuntimeError("PFF export produced an empty CSV")

    header_idx = next(
        (i for i, r in enumerate(rows) if r and r[0].strip() == "Overall Rank"),
        None,
    )
    if header_idx is None:
        raise RuntimeError(
            "PFF export missing the 'Overall Rank' header row — not logged in, "
            "or the export layout changed"
        )
    header = [h.strip() for h in rows[header_idx]]
    if header != PFF_EXPORT_HEADER:
        raise RuntimeError(
            f"PFF export header changed — expected {PFF_EXPORT_HEADER}, got {header}"
        )
    data_rows = [r for r in rows[header_idx + 1:] if r and r[0].strip()]
    return len(data_rows)


def fetch_pff(output_dir: str, year: int = CURRENT_SEASON, min_players: int = 200) -> str:
    """Fetch PFF draft rankings via a saved logged-in session and save a CSV.

    PFF's rankings are behind a premium subscription. This reuses the session saved by
    `ff-rankings login pff` (no password handled here) to drive the page's own
    Export/Download, capturing the exact CSV the pipeline already consumes
    (renamed positionally into COLUMN_MAPPINGS['pff']) → Draft-rankings-export-<year>.csv.

    Args:
        output_dir: Directory to save the CSV (the pipeline's update/ folder).
        year: Season year for the filename (matches FILE_MAPPINGS' pff prefix).
        min_players: Coverage floor — raise if fewer rows are captured.

    Returns:
        Path to the saved CSV file.

    Raises:
        RuntimeError: if there is no saved session, Playwright/Chromium is unavailable,
            the export header drifts, or fewer than `min_players` rows are captured.
    """
    from fantasy_pipeline.scraper.auth import load_storage_state

    storage_state = load_storage_state("pff")
    output_path = os.path.join(output_dir, _pff_output_filename(year))
    row_count = _pff_capture_export_csv(output_path, storage_state)

    if row_count < min_players:
        raise RuntimeError(
            f"Only {row_count} PFF players captured (expected >= {min_players}); "
            "the session may have expired or the export may be gated"
        )

    print(f"PFF fetched: {row_count} players saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# FantasyPoints / Scott Barrett (paywalled — saved-session headless fetcher)
# ---------------------------------------------------------------------------

# Redraft rankings SPA. The page defaults to Hansen's rankings; a "BARRETT'S RANKINGS"
# tab switches to Scott Barrett's board (the one the manual workflow uses). Overridable
# via --url for live verification.
FPTS_RANKINGS_URL = "https://www.fantasypoints.com/nfl/rankings/redraft"

# The 7-col header FantasyPoints' "Download as CSV" emits (the file the manual workflow
# drops as "Scott Barrett*.csv"). The pipeline renames POSITIONALLY into COLUMN_MAPPINGS['fpts'].
FPTS_EXPORT_HEADER = ["Overall", "NAME", "POS", "TEAM", "BYE", "TIER", "EXODIA"]


def _fpts_output_filename(year: int) -> str:
    """Filename matching FILE_MAPPINGS' 'Scott Barrett' prefix."""
    return f"Scott Barrett {year} Redraft Rankings.csv"


def _select_fpts_barrett(page) -> None:
    """Switch the redraft rankings SPA from Hansen's board to Scott Barrett's.

    The page loads Hansen's rankings by default; clicking the "BARRETT'S RANKINGS" tab
    re-renders the table with Barrett's data (page title gains "Barrett's").
    """
    tab = page.locator("a:has-text(\"BARRETT'S RANKINGS\")").first
    tab.wait_for(state="visible", timeout=20000)
    tab.click()
    # Confirm the board actually switched before exporting (guards against silently
    # downloading Hansen's rankings under the Barrett filename).
    try:
        page.wait_for_function(
            "() => /barrett/i.test(document.title)", timeout=15000
        )
    except Exception as exc:
        raise RuntimeError(
            "Clicked 'BARRETT'S RANKINGS' but the page title never switched to Barrett's "
            "board — the rankings SPA may have changed."
        ) from exc


def _click_fpts_csv_download(page) -> None:
    """Click the DataTables 'Download as CSV' button (fires a client-side Blob download)."""
    btn = page.locator("button.buttons-csv, button:has-text('Download as CSV')").first
    btn.wait_for(state="visible", timeout=15000)
    btn.click()


def _fpts_capture_export_csv(output_path: str, storage_state: str, rankings_url: str) -> int:
    """Drive a logged-in headless browser to export Barrett's rankings; save the CSV.

    Reuses the saved session (`storage_state`); no password handled here. Selects
    Barrett's board, then captures its "Download as CSV". Returns the data-row count.
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
                storage_state=storage_state,
                viewport={"width": 1400, "height": 1000},
            )
            page = context.new_page()
            page.goto(rankings_url, wait_until="networkidle", timeout=60000)

            _select_fpts_barrett(page)
            with page.expect_download(timeout=30000) as download_info:
                _click_fpts_csv_download(page)
            download = download_info.value
            download.save_as(output_path)
        finally:
            browser.close()

    return _validate_fpts_csv(output_path)


def _validate_fpts_csv(output_path: str) -> int:
    """Validate the saved FantasyPoints CSV header (row 1) and return its data-row count."""
    with open(output_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise RuntimeError("FantasyPoints export produced an empty CSV")

    header = [h.strip() for h in rows[0]]
    if header != FPTS_EXPORT_HEADER:
        raise RuntimeError(
            f"FantasyPoints export header changed — expected {FPTS_EXPORT_HEADER}, got {header}. "
            "Not logged in, wrong page, or the export layout changed."
        )
    data_rows = [r for r in rows[1:] if r and r[0].strip()]
    return len(data_rows)


def fetch_fpts(output_dir: str, year: int = CURRENT_SEASON, min_players: int = 90,
               rankings_url: str = FPTS_RANKINGS_URL) -> str:
    """Fetch FantasyPoints (Scott Barrett) redraft rankings via a saved session; save a CSV.

    FantasyPoints is behind a subscription. This reuses the session saved by
    `ff-rankings login fpts` (no password handled here) to drive the page's own
    Export/Download, capturing the CSV the pipeline already consumes (renamed positionally
    into COLUMN_MAPPINGS['fpts']) → "Scott Barrett <year> Redraft Rankings.csv".

    Args:
        output_dir: Directory to save the CSV (the pipeline's update/ folder).
        year: Season year for the filename.
        min_players: Coverage floor — raise if fewer rows are captured (the redraft
            board is ~100, so the default 90 catches breakage with a little margin).
        rankings_url: Rankings page to export from (overridable for live verification).

    Returns:
        Path to the saved CSV file.

    Raises:
        RuntimeError: if there is no saved session, Playwright/Chromium is unavailable,
            the export header drifts, or fewer than `min_players` rows are captured.
    """
    from fantasy_pipeline.scraper.auth import load_storage_state

    storage_state = load_storage_state("fpts")
    output_path = os.path.join(output_dir, _fpts_output_filename(year))
    row_count = _fpts_capture_export_csv(output_path, storage_state, rankings_url)

    if row_count < min_players:
        raise RuntimeError(
            f"Only {row_count} FantasyPoints players captured (expected >= {min_players}); "
            "the session may have expired or the export may be gated"
        )

    print(f"FantasyPoints fetched: {row_count} players saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# JJ Zachariason / LateRound (Patreon — saved-session API attachment fetcher)
# ---------------------------------------------------------------------------
#
# JJ's redraft rankings are a downloadable attachment on a Patreon post (collection
# 47664). Two live realities shape this fetcher:
#   1. Patreon post *pages* are gated by a Cloudflare Turnstile challenge that flags the
#      headless browser — but the Patreon *JSON API* (same session cookies) is not. So we
#      read attachments via the API instead of clicking the HTML.
#   2. The attachment is now a 5-col CSV (`Overall,Player,Position,Pos Rank,Tier`) — the
#      `Auction` column the old .xlsx had was dropped. We pad it back to the 6-col width
#      the pipeline renames POSITIONALLY into COLUMN_MAPPINGS['jj'] (source order already
#      matches: RK, PLAYER NAME, POS, POS RANK, TIER, AUCTION).
JJ_COLLECTION_URL = "https://www.patreon.com/collection/47664"
JJ_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 6-col output header; the pipeline renames it positionally into COLUMN_MAPPINGS['jj'].
JJ_OUTPUT_COLUMNS = ["Overall", "Player", "Position", "Pos Rank", "Tier", "Auction"]


def _jj_output_filename(year: int) -> str:
    """Filename matching FILE_MAPPINGS' redraft 'Redraft1QB_' prefix (CSV now, not xlsx)."""
    return f"Redraft1QB_{year}.csv"


def _jj_is_redraft_title(title: str) -> bool:
    """True if a collection post title is the 1QB redraft (not superflex/ROS/weekly)."""
    t = (title or "").lower()
    return (
        "1qb" in t
        and ("redraft" in t or "season-long" in t)
        and not re.search(r"superflex|rest-of-season|weekly", t)
    )


def _jj_post_id_from_url(url: str) -> str | None:
    """Extract the numeric Patreon post id from a post URL, or None."""
    m = re.search(r"/posts/(\d+)", url or "")
    return m.group(1) if m else None


def _jj_adapt_rows(rows: list) -> list:
    """Normalize attachment rows to the 6-col COLUMN_MAPPINGS['jj'] width.

    The current source has 5 cols (no Auction); older xlsx had 6. Pad 5→6 (blank Auction),
    truncate any extras, and drop spacer rows. Header is row 0.
    """
    width = len(JJ_OUTPUT_COLUMNS)  # 6
    out = []
    for r in rows:
        cells = ["" if c is None else c for c in r]
        if len(cells) == width - 1:
            cells = cells + [""]          # pad the dropped Auction column
        if len(cells) >= width:
            out.append([str(c) for c in cells[:width]])
        # too-short / blank spacer rows are skipped
    if len(out) < 2:
        raise RuntimeError("JJ attachment had no usable rows after adapting to 6 columns")
    return out


def _jj_data_row_count(rows: list) -> int:
    """Count data rows (after the header) whose first cell is a numeric rank."""
    return sum(1 for r in rows[1:] if r and str(r[0]).strip().isdigit())


def _jj_rows_from_attachment(file_name: str, raw: bytes) -> list:
    """Parse the downloaded attachment (.csv or .xlsx) into a list of rows."""
    name = (file_name or "").lower()
    if name.endswith(".csv"):
        return list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    if name.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
        try:
            sheet = "Rankings and Tiers" if "Rankings and Tiers" in wb.sheetnames else wb.sheetnames[-1]
            return [list(r) for r in wb[sheet].iter_rows(values_only=True)]
        finally:
            wb.close()
    raise RuntimeError(f"Unexpected JJ attachment type: {file_name!r} (want .csv/.xlsx)")


def _jj_api_json(context, url: str) -> dict:
    """GET a Patreon JSON API URL via the session's request context; raise if blocked."""
    r = context.request.get(url, headers={"Accept": "application/json"})
    body = r.text()
    if r.status != 200 or not body.strip().startswith("{"):
        raise RuntimeError(
            f"Patreon API returned {r.status} for {url} — the session may have expired "
            "or be blocked. Re-run `ff-rankings login jj`."
        )
    return json.loads(body)


def _jj_discover_post_id(page) -> str:
    """Find the latest 1QB redraft post id from the collection page (newest-first)."""
    page.goto(JJ_COLLECTION_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    for _ in range(3):  # lazy-loaded list — scroll to surface more posts
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1200)
    posts = page.evaluate(
        r"""() => {
          const seen = new Set(), out = [];
          document.querySelectorAll('a[href*="/posts/"]').forEach(a => {
            const m = (a.getAttribute('href') || '').match(/\/posts\/(\d+)/);
            if (!m || seen.has(m[1])) return;
            seen.add(m[1]);
            out.push({id: m[1], title: (a.innerText || '').replace(/\s+/g, ' ').trim()});
          });
          return out;
        }"""
    )
    pick = next((p for p in posts if _jj_is_redraft_title(p["title"])), None)
    if not pick:
        raise RuntimeError(
            "No 1QB redraft post found in the LateRound collection "
            f"({JJ_COLLECTION_URL}) — pass --post-url with the current post explicitly."
        )
    return pick["id"]


def _jj_attachment(context, post_id: str) -> tuple:
    """Return (file_name, download_url) of the post's Redraft1QB .csv/.xlsx attachment."""
    api = (
        f"https://www.patreon.com/api/posts/{post_id}"
        "?include=attachments_media&fields[media]=file_name,download_url,mimetype"
        "&json-api-version=1.0"
    )
    data = _jj_api_json(context, api)
    media = [m["attributes"] for m in data.get("included", []) if m.get("type") == "media"]
    target = next(
        (m for m in media
         if "redraft1qb" in (m.get("file_name") or "").lower()
         and (m.get("file_name") or "").lower().endswith((".csv", ".xlsx"))),
        None,
    )
    if not target:
        raise RuntimeError(
            f"Post {post_id} has no Redraft1QB .csv/.xlsx attachment "
            f"(found: {[m.get('file_name') for m in media]})"
        )
    return target["file_name"], target["download_url"]


def _jj_fetch_rows(storage_state: str, post_url: str | None) -> list:
    """Discover (or use) the post, download its Redraft1QB attachment via the API, adapt.

    Returns adapted 6-col rows (header + data). Uses the API for attachments because the
    Patreon post HTML is Cloudflare-gated for the headless browser.
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
                storage_state=storage_state,
                user_agent=JJ_UA,
                viewport={"width": 1400, "height": 1200},
            )
            page = context.new_page()
            post_id = _jj_post_id_from_url(post_url) if post_url else _jj_discover_post_id(page)
            if not post_id:
                raise RuntimeError(f"Could not parse a post id from --post-url {post_url!r}")
            file_name, download_url = _jj_attachment(context, post_id)
            raw = context.request.get(download_url).body()
        finally:
            browser.close()

    return _jj_adapt_rows(_jj_rows_from_attachment(file_name, raw))


def fetch_jj(output_dir: str, post_url: str = None, year: int = CURRENT_SEASON,
             min_players: int = 150) -> str:
    """Fetch JJ Zachariason's 1QB redraft rankings from Patreon via a saved session.

    Reuses the session from `ff-rankings login jj` (no password handled). By default it
    auto-discovers the latest 1QB redraft post in the LateRound collection; pass
    `post_url` to target a specific post. The attachment is downloaded through the Patreon
    JSON API (the post HTML is Cloudflare-gated), adapted to the 6-col COLUMN_MAPPINGS['jj']
    width (the current source dropped the Auction column), and written as a CSV.

    Args:
        output_dir: Directory to save the CSV (the pipeline's update/ folder).
        post_url: Optional Patreon post URL; if omitted, the latest 1QB redraft post is found.
        year: Season year for the filename.
        min_players: Coverage floor — raise if fewer rows are found (the board is ~250).

    Returns:
        Path to the saved CSV file ('Redraft1QB_<year>.csv').

    Raises:
        RuntimeError: if there is no saved session, Playwright/Chromium is unavailable, the
            session is blocked, no redraft post/attachment is found, or coverage is low.
    """
    from fantasy_pipeline.scraper.auth import load_storage_state

    storage_state = load_storage_state("jj")
    rows = _jj_fetch_rows(storage_state, post_url)
    count = _jj_data_row_count(rows)
    if count < min_players:
        raise RuntimeError(
            f"Only {count} JJ players found (expected >= {min_players}); "
            "the session may have expired or the wrong attachment was downloaded"
        )

    output_path = os.path.join(output_dir, _jj_output_filename(year))
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    print(f"JJ fetched: {count} players saved to {output_path}")
    return output_path
