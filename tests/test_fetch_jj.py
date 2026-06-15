"""Tests for the JJ Zachariason (Patreon) fetcher's pure parse/adapt logic + schema contract.

Browser-free: the network/Cloudflare/API path is exercised only by the skip-gated live
test; everything else runs against in-memory bytes/rows.
"""

import csv
import io

import openpyxl
import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_rankings import (
    JJ_OUTPUT_COLUMNS,
    _jj_adapt_rows,
    _jj_data_row_count,
    _jj_is_redraft_title,
    _jj_output_filename,
    _jj_post_id_from_url,
    _jj_rows_from_attachment,
)


class TestRedraftTitleMatch:
    @pytest.mark.parametrize(
        "title",
        [
            "updated 1QB season-long rankings attached",
            "May 2026 1QB Redraft and Best Ball Rankings Update (5/11/26)",
            "August 2025 1QB Redraft and Best Ball Rankings",
        ],
    )
    def test_matches_1qb_redraft(self, title):
        assert _jj_is_redraft_title(title)

    @pytest.mark.parametrize(
        "title",
        [
            "August 2025 Superflex Redraft Rankings and Tiers",
            "Rest-of-Season Rankings Entering Week 7",
            "Hansen's Weekly Ranks",
            "",
        ],
    )
    def test_rejects_non_1qb_redraft(self, title):
        assert not _jj_is_redraft_title(title)


class TestPostIdFromUrl:
    def test_extracts_id(self):
        assert _jj_post_id_from_url("https://www.patreon.com/posts/159924611?collection=47664") == "159924611"

    def test_none_when_absent(self):
        assert _jj_post_id_from_url("https://www.patreon.com/collection/47664") is None


class TestRowsFromAttachment:
    def test_parses_csv_bytes(self):
        raw = "Overall,Player,Position,Pos Rank,Tier\n1,Gibbs,RB,1,1\n".encode("utf-8-sig")
        rows = _jj_rows_from_attachment("June26Redraft1QB.csv", raw)
        assert rows[0] == ["Overall", "Player", "Position", "Pos Rank", "Tier"]
        assert rows[1][1] == "Gibbs"

    def test_parses_xlsx_bytes(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Rankings and Tiers"
        ws.append(["Overall", "Player", "Position", "Pos Rank", "Tier", "Auction (Out of $200)"])
        ws.append([1, "Gibbs", "RB", 1, 1, 60])
        buf = io.BytesIO()
        wb.save(buf)
        rows = _jj_rows_from_attachment("Redraft1QB_2025.xlsx", buf.getvalue())
        assert rows[0][0] == "Overall"
        assert rows[1][1] == "Gibbs"

    def test_rejects_unknown_type(self):
        with pytest.raises(RuntimeError, match="Unexpected JJ attachment"):
            _jj_rows_from_attachment("foo.pdf", b"x")


class TestAdaptRows:
    def test_pads_5col_to_6col(self):
        rows = [["Overall", "Player", "Position", "Pos Rank", "Tier"], ["1", "Gibbs", "RB", "1", "1"]]
        out = _jj_adapt_rows(rows)
        assert all(len(r) == len(JJ_OUTPUT_COLUMNS) for r in out)
        assert out[1] == ["1", "Gibbs", "RB", "1", "1", ""]  # blank Auction appended

    def test_truncates_extra_columns(self):
        rows = [["a", "b", "c", "d", "e", "f", "g"], ["1", "x", "RB", "1", "1", "9", "extra"]]
        out = _jj_adapt_rows(rows)
        assert len(out[1]) == len(JJ_OUTPUT_COLUMNS)

    def test_skips_spacer_rows_and_requires_data(self):
        rows = [["Overall", "Player", "Position", "Pos Rank", "Tier"], [], [None]]
        with pytest.raises(RuntimeError, match="no usable rows"):
            _jj_adapt_rows(rows)


class TestDataRowCount:
    def test_counts_numeric_first_cell_after_header(self):
        rows = [
            JJ_OUTPUT_COLUMNS,
            ["1", "a", "RB", "1", "1", ""],
            ["2", "b", "WR", "1", "1", ""],
            ["", "spacer", "", "", "", ""],
        ]
        assert _jj_data_row_count(rows) == 2


class TestJjSchemaContract:
    def test_output_width_matches_pipeline_schema(self):
        assert len(JJ_OUTPUT_COLUMNS) == len(COLUMN_MAPPINGS["jj"])

    def test_output_filename_tracks_year_and_prefix(self):
        assert _jj_output_filename(2025).startswith("Redraft1QB_")
        assert _jj_output_filename(2025).endswith(".csv")
        assert "2026" in _jj_output_filename(2026)


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


def _has_jj_session():
    from fantasy_pipeline.scraper.auth import storage_state_path

    return storage_state_path("jj").exists()


@pytest.mark.skipif(
    not (_has_chromium() and _has_jj_session()),
    reason="needs Chromium + a saved JJ session (`ff-rankings login jj`)",
)
class TestJjLive:
    """Live end-to-end fetch with auto-discovery — skipped in CI, runs locally."""

    def test_fetch_jj_auto_discovers_and_loads(self, tmp_path):
        from fantasy_pipeline.scraper.fetch_rankings import fetch_jj

        path = fetch_jj(str(tmp_path), min_players=150)
        rows = list(csv.reader(open(path, encoding="utf-8-sig")))
        assert len(rows[0]) == len(JJ_OUTPUT_COLUMNS)
        data = [r for r in rows[1:] if r and r[0].strip().isdigit()]
        assert len(data) >= 150
