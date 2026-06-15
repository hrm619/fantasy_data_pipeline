"""Tests for the DraftSharks headless-browser rankings fetcher.

Pure parsing/mapping helpers and the schema contract are covered without a browser.
A single live-browser test is gated to skip when Playwright/Chromium is unavailable,
so CI stays green.
"""

import csv
import importlib.util

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    DS_EXPORT_HEADER,
    DS_OUTPUT_COLUMNS,
    DS_OUTPUT_FILENAME,
    _ds_dom_row_to_output,
    fetch_draftsharks,
)


# One real row from a manual DraftSharks "Export Rankings" CSV (column order matches
# the rendered DOM table), used to exercise the DOM-fallback mapping helper.
_SAMPLE_DOM_ROW = [
    "1",
    "PHI",
    "Saquon Barkley",
    "RB",
    "17",
    "1.03",
    "9",
    "-2.8%",
    "58%",
    "246.5",
    "284",
    "301",
    "345.7",
    "100",
]


class TestSchemaContract:
    def test_output_columns_equal_pipeline_ds_mapping(self):
        # Guard: the DOM-fallback layout must match the pipeline's positional rename.
        assert DS_OUTPUT_COLUMNS == COLUMN_MAPPINGS["ds"]

    def test_export_header_has_14_columns(self):
        assert len(DS_EXPORT_HEADER) == 14
        assert len(DS_OUTPUT_COLUMNS) == 14

    def test_output_filename_matches_pipeline_prefix(self):
        assert DS_OUTPUT_FILENAME == "rankings-half-ppr.csv"


class TestDomRowMapping:
    def test_maps_all_14_columns_in_order(self):
        row = _ds_dom_row_to_output(_SAMPLE_DOM_ROW)
        assert list(row.keys()) == DS_OUTPUT_COLUMNS
        assert row["RK"] == "1"
        assert row["TEAM"] == "PHI"
        assert row["PLAYER NAME"] == "Saquon Barkley"
        assert row["POS"] == "RB"
        assert row["DS ADP"] == "1.03"
        assert row["3D VALUE"] == "100"

    def test_strips_whitespace(self):
        padded = [
            "  2 ",
            " CIN ",
            " Ja'Marr Chase ",
            "WR",
            "17",
            "1.01",
            "10",
            "0.4%",
            "75%",
            "237.8",
            "272",
            "287",
            "329.5",
            "98.7",
        ]
        row = _ds_dom_row_to_output(padded)
        assert row["TEAM"] == "CIN"
        assert row["PLAYER NAME"] == "Ja'Marr Chase"  # apostrophe preserved

    def test_returns_none_for_non_numeric_rank(self):
        bad = ["Header"] + [""] * 13
        assert _ds_dom_row_to_output(bad) is None

    def test_returns_none_when_too_few_cells(self):
        assert _ds_dom_row_to_output(["1", "PHI", "Saquon Barkley"]) is None

    def test_extra_trailing_cells_are_ignored(self):
        row = _ds_dom_row_to_output(_SAMPLE_DOM_ROW + ["extra", "cols"])
        assert len(row) == 14
        assert row["3D VALUE"] == "100"


class TestCoverageFloor:
    def test_raises_when_too_few_players(self, monkeypatch, tmp_path):
        # Simulate a tiny capture (e.g. export gated / layout drift) and verify the guard.
        def fake_capture(output_path):
            with open(output_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(DS_EXPORT_HEADER)
                w.writerow(_SAMPLE_DOM_ROW)
            return 1

        monkeypatch.setattr(
            "fantasy_pipeline.scraper.fetch_rankings._ds_capture_export_csv",
            fake_capture,
        )
        with pytest.raises(RuntimeError, match="expected >= 150"):
            fetch_draftsharks(str(tmp_path), min_players=150)

    def test_passes_when_above_floor(self, monkeypatch, tmp_path):
        def fake_capture(output_path):
            with open(output_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(DS_EXPORT_HEADER)
                for i in range(200):
                    w.writerow([str(i + 1)] + _SAMPLE_DOM_ROW[1:])
            return 200

        monkeypatch.setattr(
            "fantasy_pipeline.scraper.fetch_rankings._ds_capture_export_csv",
            fake_capture,
        )
        path = fetch_draftsharks(str(tmp_path), min_players=150)
        assert path.endswith(DS_OUTPUT_FILENAME)
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
        assert [h.strip() for h in rows[0]] == DS_EXPORT_HEADER
        assert len(rows) - 1 == 200


def _chromium_available() -> bool:
    """True only if Playwright is importable AND a Chromium binary is installed."""
    if importlib.util.find_spec("playwright") is None:
        return False
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _chromium_available(),
    reason="Playwright/Chromium not installed (run: uv pip install -e '.[headless]' && playwright install chromium)",
)
class TestLiveFetch:
    def test_live_fetch_writes_pipeline_ready_csv(self, tmp_path):
        path = fetch_draftsharks(str(tmp_path), min_players=150)

        with open(path, newline="") as f:
            rows = list(csv.reader(f))

        header = [h.strip() for h in rows[0]]
        assert header == DS_EXPORT_HEADER
        assert len(header) == len(COLUMN_MAPPINGS["ds"])  # positional rename target
        assert len(rows) - 1 >= 150  # full board is ~300+
        # Spot-check that data rows have a numeric rank in column 0.
        assert rows[1][0].strip().isdigit()
