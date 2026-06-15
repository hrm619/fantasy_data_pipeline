"""Tests for the FantasyPoints (Scott Barrett) fetcher's CSV validation + schema contract.

Browser-free: exercises the pure validation/parse path against fixture CSVs that mirror
the real export (7-col header on row 1, then players).
"""

import csv

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    FPTS_EXPORT_HEADER,
    _fpts_output_filename,
    _validate_fpts_csv,
)


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


# Mirrors the real export: 7-col header on row 1, then players (no title row).
GOOD_ROWS = [
    FPTS_EXPORT_HEADER,
    ["1", "Ja'Marr Chase", "WR", "CIN", "10", "1", "-"],
    ["2", "Bijan Robinson", "RB", "ATL", "5", "2", "-"],
]


class TestValidateFptsCsv:
    def test_counts_data_rows(self, tmp_path):
        p = tmp_path / "fpts.csv"
        _write_csv(p, GOOD_ROWS)
        assert _validate_fpts_csv(str(p)) == 2

    def test_drifted_header_raises(self, tmp_path):
        p = tmp_path / "fpts.csv"
        _write_csv(p, [FPTS_EXPORT_HEADER[:-1] + ["Renamed"]] + GOOD_ROWS[1:])
        with pytest.raises(RuntimeError, match="header changed"):
            _validate_fpts_csv(str(p))

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "fpts.csv"
        _write_csv(p, [])
        with pytest.raises(RuntimeError, match="empty"):
            _validate_fpts_csv(str(p))


class TestFptsSchemaContract:
    def test_export_header_width_matches_pipeline_schema(self):
        # The pipeline renames positionally, so column COUNT must match exactly.
        assert len(FPTS_EXPORT_HEADER) == len(COLUMN_MAPPINGS["fpts"])

    def test_output_filename_tracks_year_and_prefix(self):
        # Must start with the FILE_MAPPINGS 'Scott Barrett' prefix.
        assert _fpts_output_filename(2025).startswith("Scott Barrett")
        assert "2025" in _fpts_output_filename(2025)
        assert "2026" in _fpts_output_filename(2026)


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


def _has_fpts_session():
    from fantasy_pipeline.scraper.auth import storage_state_path
    return storage_state_path("fpts").exists()


@pytest.mark.skipif(
    not (_has_chromium() and _has_fpts_session()),
    reason="needs Chromium + a saved FantasyPoints session (`ff-rankings login fpts`)",
)
class TestFptsLive:
    """Live end-to-end fetch — skipped in CI (no session/browser), runs locally."""

    def test_fetch_fpts_captures_board(self, tmp_path):
        from fantasy_pipeline.scraper.fetch_rankings import fetch_fpts

        path = fetch_fpts(str(tmp_path), min_players=90)
        rows = list(csv.reader(open(path, encoding="utf-8-sig")))
        assert [h.strip() for h in rows[0]] == FPTS_EXPORT_HEADER
        data = [r for r in rows[1:] if r and r[0].strip().isdigit()]
        assert len(data) >= 90
