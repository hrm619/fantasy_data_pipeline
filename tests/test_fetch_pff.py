"""Tests for the PFF fetcher's CSV validation + pipeline-schema contract.

Browser-free: exercises the pure validation/parse path against fixture CSVs that
mirror PFF's real export (title row + 'Overall Rank' header + data rows).
"""

import csv

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    PFF_EXPORT_HEADER,
    _pff_output_filename,
    _validate_pff_csv,
)


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


# Mirrors the real export: a title row, a blank row, the 9-col header, then players.
GOOD_ROWS = [
    ["Draft-rankings-export-2025"],
    [],
    PFF_EXPORT_HEADER,
    ["1", "Bijan Robinson", "ATL", "RB", "1", "5", "3.3", "283.68", "57"],
    ["2", "Ja'Marr Chase", "CIN", "WR", "1", "10", "4.1", "270.0", "55"],
]


class TestValidatePffCsv:
    def test_counts_data_rows_after_header(self, tmp_path):
        p = tmp_path / "pff.csv"
        _write_csv(p, GOOD_ROWS)
        assert _validate_pff_csv(str(p)) == 2

    def test_ignores_title_and_blank_rows(self, tmp_path):
        # Extra leading blank lines must not be counted as players.
        p = tmp_path / "pff.csv"
        _write_csv(p, [["title"], [], []] + GOOD_ROWS[2:])
        assert _validate_pff_csv(str(p)) == 2

    def test_missing_header_raises(self, tmp_path):
        p = tmp_path / "pff.csv"
        _write_csv(p, [["title"], [], ["Wrong", "Header"]])
        with pytest.raises(RuntimeError, match="Overall Rank"):
            _validate_pff_csv(str(p))

    def test_drifted_header_raises(self, tmp_path):
        p = tmp_path / "pff.csv"
        bad = GOOD_ROWS[:2] + [PFF_EXPORT_HEADER[:-1] + ["Renamed Col"]] + GOOD_ROWS[3:]
        _write_csv(p, bad)
        with pytest.raises(RuntimeError, match="header changed"):
            _validate_pff_csv(str(p))

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "pff.csv"
        _write_csv(p, [])
        with pytest.raises(RuntimeError, match="empty"):
            _validate_pff_csv(str(p))


class TestPffSchemaContract:
    def test_export_header_width_matches_pipeline_schema(self):
        # The pipeline renames positionally, so column COUNT must match exactly.
        assert len(PFF_EXPORT_HEADER) == len(COLUMN_MAPPINGS["pff"])

    def test_output_filename_tracks_year(self):
        assert _pff_output_filename(2025) == "Draft-rankings-export-2025.csv"
        assert _pff_output_filename(2026) == "Draft-rankings-export-2026.csv"


def _has_chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


def _has_pff_session():
    from fantasy_pipeline.scraper.auth import storage_state_path
    return storage_state_path("pff").exists()


@pytest.mark.skipif(
    not (_has_chromium() and _has_pff_session()),
    reason="needs Chromium + a saved PFF session (`ff-rankings login pff`)",
)
class TestPffLive:
    """Live end-to-end fetch — skipped in CI (no session/browser), runs locally."""

    def test_fetch_pff_captures_full_board(self, tmp_path):
        from fantasy_pipeline.scraper.fetch_rankings import fetch_pff

        path = fetch_pff(str(tmp_path), min_players=200)
        rows = list(csv.reader(open(path, encoding="utf-8-sig")))
        header = next(r for r in rows if r and r[0].strip() == "Overall Rank")
        assert header == PFF_EXPORT_HEADER
        data = [r for r in rows if r and r[0].strip().isdigit()]
        assert len(data) >= 200
