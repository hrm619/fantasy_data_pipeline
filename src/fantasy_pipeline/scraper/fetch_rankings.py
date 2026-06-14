"""Automated fetchers for ranking sources that support public access.

Each fetcher downloads data and saves it as a CSV in the pipeline's update/ directory
with the filename pattern expected by FILE_MAPPINGS in config.py.
"""

import csv
import os
import re
from datetime import datetime
from html.parser import HTMLParser

import requests


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


def fetch_fantasypros_adp(output_dir: str, year: int = 2025) -> str:
    """Fetch FantasyPros ADP data and save as CSV.

    Scrapes the public ADP page which has ~989 player rows with
    rankings from ESPN, Sleeper, CBS, NFL, RTSports.

    Args:
        output_dir: Directory to save the CSV (pipeline's update/ folder).
        year: Season year for filename.

    Returns:
        Path to the saved CSV file.
    """
    url = "https://www.fantasypros.com/nfl/adp/ppr-overall.php"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    parser = _TableParser()
    parser.feed(response.text)

    if len(parser.rows) < 2:
        raise RuntimeError(f"Failed to parse ADP table — only {len(parser.rows)} rows found")

    # Parse player data from table rows
    # Header: Rank | Player+Team(Bye) | POS | ESPN | Sleeper | CBS | NFL | RTSports
    header = parser.rows[0]
    players = []

    for row in parser.rows[1:]:
        if len(row) < 3:
            continue

        rank = row[0].strip()
        if not rank.isdigit():
            continue

        # Player cell contains "PlayerNameTEAM(Bye)" or "PlayerNameTEAM(Bye)O"
        # where O/Q/D/IR are injury designations
        player_cell = row[1]
        match = re.match(r"(.+?)([A-Z]{2,3})\((\d+)\)[A-Z]*$", player_cell)
        if match:
            player_name = match.group(1).strip()
            team = match.group(2)
            bye = match.group(3)
        else:
            player_name = player_cell.strip()
            team = ""
            bye = ""

        # Pos cell contains positional rank like "WR1", "RB12" — strip the number
        pos_raw = row[2].strip() if len(row) > 2 else ""
        pos = re.sub(r"\d+$", "", pos_raw)

        # ADP values from various platforms
        adp_values = row[3:] if len(row) > 3 else []

        players.append({
            "Rank": rank,
            "Player": player_name,
            "Team": team,
            "Pos": pos,
            "Bye": bye,
            "AVG": _compute_avg(adp_values),
        })

    # Save as CSV with expected filename pattern
    filename = f"FantasyPros_{year}_Overall_ADP_Rankings.csv"
    output_path = os.path.join(output_dir, filename)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Rank", "Player", "Team", "Pos", "Bye", "AVG"])
        writer.writeheader()
        writer.writerows(players)

    print(f"ADP fetched: {len(players)} players saved to {output_path}")
    return output_path


def _compute_avg(values: list[str]) -> str:
    """Compute average from a list of ADP string values, skipping blanks."""
    nums = []
    for v in values:
        v = v.strip()
        if v and v.replace(".", "").isdigit():
            nums.append(float(v))
    if not nums:
        return ""
    return f"{sum(nums) / len(nums):.1f}"


def fetch_draftsharks(output_dir: str) -> str:
    """Fetch DraftShark rankings and save as CSV.

    Note: Only captures the ~60 players visible in initial HTML.
    Full rankings may require JS rendering.

    Args:
        output_dir: Directory to save the CSV.

    Returns:
        Path to the saved CSV file.
    """
    url = "https://www.draftsharks.com/rankings/half-ppr"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    parser = _TableParser()
    parser.feed(response.text)

    if len(parser.rows) < 2:
        raise RuntimeError(f"Failed to parse DraftShark table — only {len(parser.rows)} rows found")

    players = []
    for row in parser.rows[1:]:
        if len(row) < 3:
            continue

        rank = row[0].strip()
        if not rank.isdigit():
            continue

        # DraftShark cell 2 has concatenated player info — extract name and position
        player_cell = row[2] if len(row) > 2 else ""
        # Try to extract "PlayerNameTEAMPOS_RANK" pattern
        match = re.match(r"(.+?)([A-Z]{2,3})(QB|RB|WR|TE|K|DEF)(\d+)", player_cell)
        if match:
            player_name = match.group(1).strip()
            team = match.group(2)
            pos = match.group(3)
        else:
            player_name = player_cell.strip()
            team = ""
            pos = ""

        adp = row[5].strip() if len(row) > 5 else ""

        players.append({
            "RK": rank,
            "PLAYER NAME": player_name,
            "TEAM": team,
            "POS": pos,
            "ADP": adp,
        })

    filename = "rankings-half-ppr.csv"
    output_path = os.path.join(output_dir, filename)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["RK", "PLAYER NAME", "TEAM", "POS", "ADP"])
        writer.writeheader()
        writer.writerows(players)

    print(f"DraftShark fetched: {len(players)} players saved to {output_path}")
    return output_path
