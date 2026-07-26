"""Tests for the PFF fetcher's CSV validation + pipeline-schema contract.

Browser-free: exercises the pure validation/parse path against fixture CSVs that
mirror PFF's real export (title row + 'Overall Rank' header + data rows).
"""

import csv
import inspect

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    PFF_EXPORT_HEADER,
    PFF_SCORING_LABEL,
    PFF_SCORING_OPTIONS,
    _pff_capture_export_csv,
    _pff_output_filename,
    _pff_response_scoring_type,
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


class _FakeResponse:
    """Minimal stand-in for a Playwright Response (url + ok are all we read)."""

    def __init__(self, url, ok=True):
        self.url = url
        self.ok = ok


_PFF_BOARD_URL = (
    "https://consumer-api.pff.com/football/v1/fantasy/rankings?page=1&leagueType=standard&scoringType=REDRAFT_HALF_PPR"
)
# Fires on the SAME page load and also carries a scoringType param — the reason the URL
# match is anchored on netloc+path rather than a substring.
_PFF_WEEKLY_URL = "https://consumer-api.pff.com/football/v1/fantasy/weekly-rankings?week=1&scoringType=ppr"


class TestPffResponseScoringType:
    """The board request is the only trustworthy signal of which scoring the page loaded.

    The dropdown label is optimistic client state: it flips before the request goes out and
    flips identically when the request fails, so asserting it let a full-PPR board export
    under a 'Half PPR' label. Nothing downstream could detect that — the export has no
    scoring column and an identical header/row count either way.
    """

    def test_reads_scoring_type_from_the_board_request(self):
        assert _pff_response_scoring_type(_FakeResponse(_PFF_BOARD_URL)) == "REDRAFT_HALF_PPR"

    def test_versioned_path_still_matches(self):
        assert _pff_response_scoring_type(_FakeResponse(_PFF_BOARD_URL.replace("/v1/", "/v2/"))) == "REDRAFT_HALF_PPR"

    def test_ignores_the_weekly_rankings_decoy(self):
        assert _pff_response_scoring_type(_FakeResponse(_PFF_WEEKLY_URL)) is None

    def test_ignores_failed_responses(self):
        assert _pff_response_scoring_type(_FakeResponse(_PFF_BOARD_URL, ok=False)) is None

    def test_ignores_unrelated_hosts(self):
        assert _pff_response_scoring_type(_FakeResponse("https://heapanalytics.com/h?scoringType=REDRAFT_PPR")) is None

    def test_board_request_without_scoring_type_is_none(self):
        url = "https://consumer-api.pff.com/football/v1/fantasy/rankings?page=1"
        assert _pff_response_scoring_type(_FakeResponse(url)) is None


class TestPffScoringOptions:
    def test_the_target_label_is_mapped(self):
        assert PFF_SCORING_LABEL in PFF_SCORING_OPTIONS

    def test_target_label_resolves_to_the_half_ppr_board(self):
        _, scoring_type = PFF_SCORING_OPTIONS[PFF_SCORING_LABEL]
        assert scoring_type == "REDRAFT_HALF_PPR"

    def test_options_are_targeted_by_testid_not_accessible_name(self):
        """The trigger's accessible name IS its current selection, so name-matching is
        ambiguous: with the drawer open, name='PPR' matches both the trigger and the PPR
        option, and .first resolves to the trigger. Only the testid distinguishes them."""
        for testid, _ in PFF_SCORING_OPTIONS.values():
            assert testid.startswith("fantasyTools.dropdownOption.")

    def test_export_path_selects_and_then_verifies(self):
        """Pins the call site. Without this, deleting either call leaves the suite green
        while every export silently reverts to PPR — which is how the first version of this
        guard shipped looking finished."""
        source = inspect.getsource(_pff_capture_export_csv)
        assert "_select_pff_scoring(" in source
        assert "_assert_pff_board_loaded(" in source
        # The watcher must be installed before navigation, or a session that already has
        # Half PPR selected fires no request and has nothing to verify against.
        assert source.index("_PffBoardWatcher(") < source.index("page.goto(")


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
