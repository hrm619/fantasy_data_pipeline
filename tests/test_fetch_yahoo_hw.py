"""Tests for the Yahoo Sports Hayden Winks redraft fetcher (scraper/fetch_yahoo_hw.py).

Network-free: every test runs against saved HTML fixtures (one per published article part +
the author page) under tests/fixtures/yahoo_hw/. The HTTP layer is exercised against a fake
session so the suite never touches Yahoo.
"""

import json
import os
from pathlib import Path

import pytest

from fantasy_pipeline.config import COLUMN_MAPPINGS
from fantasy_pipeline.scraper.fetch_yahoo_hw import (
    YAHOO_AUTHOR_URL,
    ConsentGateError,
    HW_OUTPUT_COLUMNS,
    article_id_from_url,
    discover_article_urls,
    discover_top300_url,
    fetch_html,
    fetch_yahoo_hw,
    load_player_key_index,
    normalize_player_name,
    parse_article,
    parse_top300_table,
    reconcile_player_names,
    records_to_rows,
    strip_tracking_params,
    validate_records,
)

FIXTURES = Path(__file__).parent / "fixtures" / "yahoo_hw"
PARTS = {
    (1, 12): "ranked-1-12-2026.html",
    (13, 24): "ranked-13-24-2026.html",
    (25, 36): "ranked-25-36-2026.html",
}


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _all_records() -> list[dict]:
    records: list[dict] = []
    for name in PARTS.values():
        _, recs = parse_article(_fixture(name))
        records.extend(recs)
    records.sort(key=lambda r: r["overall_rank"])
    return records


# ---------------------------------------------------------------------------- parse_article
class TestParseArticleMeta:
    def test_extracts_article_metadata(self):
        meta, _ = parse_article(_fixture(PARTS[(25, 36)]))
        assert meta["article_id"] == "140636820"
        assert meta["article_uuid"] == "aab0c7c9-1a75-4614-90b1-4b0c560f172c"
        assert meta["rank_range_start"] == 25
        assert meta["rank_range_end"] == 36
        assert meta["season"] == 2026
        assert meta["scoring_format"] == "half_ppr"
        assert meta["author"] == "Hayden Winks"
        assert meta["published_utc"] == "2026-07-23T14:06:36.000Z"


class TestParseArticleEntries:
    @pytest.mark.parametrize("rng,name", list(PARTS.items()))
    def test_exactly_twelve_contiguous_players(self, rng, name):
        start, end = rng
        _, recs = parse_article(_fixture(name))
        assert len(recs) == 12
        assert [r["overall_rank"] for r in recs] == list(range(start, end + 1))
        assert all(r["position"] in {"QB", "RB", "WR", "TE"} for r in recs)

    def test_part_one_strips_leading_rank_prefix(self):
        # Part 1 headers render as "1. Jahmyr Gibbs, RB1, Lions" — the "1. " must be dropped.
        _, recs = parse_article(_fixture(PARTS[(1, 12)]))
        assert recs[0]["player_name"] == "Jahmyr Gibbs"
        assert recs[0]["position"] == "RB" and recs[0]["position_rank"] == 1

    def test_special_character_names_preserved(self):
        names = {r["player_name"] for r in _all_records()}
        for expected in ["De'Von Achane", "Ja'Marr Chase", "Amon-Ra St. Brown", "Jaxon Smith-Njigba"]:
            assert expected in names

    def test_bare_name_entry_has_null_player_id(self):
        # Rashee Rice (rank 32) is name-dropped earlier, so his own header is bare text (no <a>).
        rice = next(r for r in _all_records() if r["player_name"] == "Rashee Rice")
        assert rice["yahoo_player_id"] is None
        assert rice["position"] == "WR" and rice["team"] == "Chiefs"

    def test_linked_entry_captures_player_and_team_ids(self):
        waddle = next(r for r in _all_records() if "Waddle" in r["player_name"])
        assert waddle["yahoo_player_id"] == "33394"
        assert waddle["team_slug"] == "denver"  # team is linked in this entry

    def test_analysis_excludes_ads_and_captures_captions(self):
        _, recs = parse_article(_fixture(PARTS[(1, 12)]))
        gibbs = recs[0]
        assert gibbs["analysis_text"]  # non-empty prose
        assert "Advertisement" not in gibbs["analysis_text"]
        assert gibbs["image_captions"]  # the chart caption was captured separately
        assert all(cap not in gibbs["analysis_text"] for cap in gibbs["image_captions"])

    def test_count_mismatch_raises(self):
        # Remove one player header so 11 remain against an expected 12 → hard failure.
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_fixture(PARTS[(13, 24)]), "html.parser")
        from fantasy_pipeline.scraper.fetch_yahoo_hw import _header_strongs

        _header_strongs(soup)[-1].decompose()
        with pytest.raises(ValueError, match="expected 12"):
            parse_article(str(soup))


class TestNormalizeName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Travis Etienne Jr.", "travis etienne"),
            ("A.J. Brown", "aj brown"),
            ("Amon-Ra St. Brown", "amonra st brown"),
            ("De'Von Achane", "devon achane"),
        ],
    )
    def test_strips_punctuation_and_suffixes(self, raw, expected):
        assert normalize_player_name(raw) == expected


# ------------------------------------------------------------------------------ discovery
class TestDiscovery:
    def test_author_page_yields_three_ordered_absolute_urls(self):
        urls = discover_article_urls(_fixture("author-page.html"), season=2026)
        assert len(urls) == 3
        assert all(u.startswith("https://sports.yahoo.com/") for u in urls)
        # ordered by rank-range start: 1-12, 13-24, 25-36
        assert "ranked-1-12-" in urls[0]
        assert "ranked-13-24-" in urls[1]
        assert "ranked-25-36-" in urls[2]

    def test_other_seasons_excluded(self):
        assert discover_article_urls(_fixture("author-page.html"), season=2025) == []


# -------------------------------------------------------------------------------- adapter
class TestAdapter:
    def test_rows_match_positional_hw_schema(self):
        rows = records_to_rows(_all_records())
        assert len(rows) == 36
        # The pipeline renames the redraft 'hw' source by *position*, and only fires when the
        # column count matches — so parity depends on emitting exactly this 11-col layout.
        assert list(rows[0].keys()) == HW_OUTPUT_COLUMNS
        assert HW_OUTPUT_COLUMNS == COLUMN_MAPPINGS["hw"]

    def test_rk_and_pos_rank_carried_through(self):
        rows = records_to_rows(_all_records())
        assert rows[0]["RK"] == 1 and rows[0]["POS RANK"] == 1
        assert rows[0]["PLAYER NAME"] == "Jahmyr Gibbs" and rows[0]["POS"] == "RB"

    def test_validate_rejects_rank_gap(self):
        recs = _all_records()
        recs[5]["overall_rank"] = 999
        with pytest.raises(ValueError, match="not contiguous"):
            validate_records(recs, verbose=False)

    def test_validate_rejects_bad_position(self):
        recs = _all_records()
        recs[0]["position"] = "K"
        with pytest.raises(ValueError, match="Unsupported position"):
            validate_records(recs, verbose=False)


# ------------------------------------------------------------------------- reconciliation
class TestReconciliation:
    KEY = {
        "BrowAJ00": ["AJ Brown"],
        "AchaDe00": ["DeVon Achane"],
        "SmitAl02": ["Alex Smith"],  # homonym half
        "SmitAl03": ["Alex Smith"],  # homonym half → ambiguous normalized form
    }

    def _write_key(self, tmp_path):
        p = tmp_path / "key.json"
        p.write_text(json.dumps(self.KEY), encoding="utf-8")
        return str(p)

    def test_index_drops_ambiguous_homonyms(self, tmp_path):
        index = load_player_key_index(self._write_key(tmp_path))
        assert index["aj brown"] == "AJ Brown"
        assert "alex smith" not in index  # owned by two ids → refused

    def test_reconcile_rewrites_to_canonical_spelling(self, tmp_path):
        rows = [{"PLAYER NAME": "A.J. Brown"}, {"PLAYER NAME": "De'Von Achane"}]
        changed = reconcile_player_names(rows, self._write_key(tmp_path), verbose=False)
        assert changed == 2
        assert rows[0]["PLAYER NAME"] == "AJ Brown"
        assert rows[1]["PLAYER NAME"] == "DeVon Achane"

    def test_reconcile_leaves_unknown_names_untouched(self, tmp_path):
        rows = [{"PLAYER NAME": "Some Rookie"}]
        assert reconcile_player_names(rows, self._write_key(tmp_path), verbose=False) == 0
        assert rows[0]["PLAYER NAME"] == "Some Rookie"

    def test_missing_key_file_is_noop(self, tmp_path):
        rows = [{"PLAYER NAME": "A.J. Brown"}]
        assert reconcile_player_names(rows, str(tmp_path / "nope.json"), verbose=False) == 0


# --------------------------------------------------------------------------- HTTP helpers
class TestUrlHelpers:
    def test_strip_tracking_params(self):
        url = "https://sports.yahoo.com/fantasy/article/x-140636820.html?guccounter=1&guce_referrer=abc"
        assert strip_tracking_params(url) == "https://sports.yahoo.com/fantasy/article/x-140636820.html"

    def test_article_id_from_url(self):
        url = "https://sports.yahoo.com/fantasy/article/2026-fantasy-football-rankings-analysis-for-players-ranked-25-36-in-half-ppr-140636820.html"
        assert article_id_from_url(url) == "140636820"


class _FakeResponse:
    def __init__(self, status_code, url, text=""):
        self.status_code = status_code
        self.url = url
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, allow_redirects=True, timeout=None):
        self.calls += 1
        resp = self._responses.pop(0)
        # Default the response URL to the requested URL unless the fake forces a redirect.
        if resp.url is None:
            resp.url = url
        return resp


class TestFetchHtml:
    URL = "https://sports.yahoo.com/fantasy/article/x-140636820.html"

    def test_retries_on_999_then_succeeds(self):
        session = _FakeSession([_FakeResponse(999, None), _FakeResponse(200, None, "<html>ok</html>")])
        html = fetch_html(self.URL, session=session, sleep=lambda _s: None, rate_limit_s=0)
        assert html == "<html>ok</html>"
        assert session.calls == 2

    def test_gives_up_after_max_retries(self):
        session = _FakeSession([_FakeResponse(999, None) for _ in range(4)])
        with pytest.raises(RuntimeError, match="999"):
            fetch_html(self.URL, session=session, sleep=lambda _s: None, rate_limit_s=0, max_retries=4)

    def test_consent_gate_raises(self):
        session = _FakeSession([_FakeResponse(200, "https://guce.yahoo.com/consent?x=1")])
        with pytest.raises(ConsentGateError):
            fetch_html(self.URL, session=session, sleep=lambda _s: None, rate_limit_s=0)

    def test_cache_hit_skips_network(self, tmp_path):
        session = _FakeSession([_FakeResponse(200, None, "<html>fresh</html>")])
        first = fetch_html(self.URL, session=session, cache_dir=str(tmp_path), sleep=lambda _s: None, rate_limit_s=0)
        assert first == "<html>fresh</html>" and session.calls == 1
        assert os.path.exists(tmp_path / "140636820.html")
        # Second call: empty session — must be served from disk, not the network.
        second = fetch_html(self.URL, session=_FakeSession([]), cache_dir=str(tmp_path), sleep=lambda _s: None)
        assert second == "<html>fresh</html>"


# ------------------------------------------------------ end-to-end parity vs the real dict
class TestConsolidationParity:
    """Capability-parity check: the emitted HW names resolve to player IDs like the old source.

    Uses the real player_key_dict.json + the real loader semantics (positional rename to
    COLUMN_MAPPINGS['hw']) so a name-matching regression would fail here.
    """

    def test_emitted_board_resolves_and_loads(self, tmp_path):
        import pandas as pd

        from fantasy_pipeline.data import add_player_ids, load_player_key_mapping

        key_path = Path(__file__).resolve().parents[1] / "player_key_dict.json"
        rows = records_to_rows(_all_records())
        reconcile_player_names(rows, str(key_path), verbose=False)
        df = pd.DataFrame(rows, columns=HW_OUTPUT_COLUMNS)

        # The loader only standardizes when the column count matches the mapping.
        assert len(df.columns) == len(COLUMN_MAPPINGS["hw"])

        _, name_to_key = load_player_key_mapping(str(key_path))
        resolved = add_player_ids(df.copy(), name_to_key, verbose=False)
        matched = resolved["PLAYER ID"].notna().sum()
        # 35/36 in the current top-36 (only rookie Jeremiah Love, absent from the dict, misses).
        assert matched >= 35
        # RK is the overall board rank and must stay contiguous.
        assert list(df["RK"]) == list(range(1, 37))


# -------------------------------------------------- full-board (top-N) table parsing
class TestParseTop300Table:
    def _records(self):
        return parse_top300_table(_fixture("top300-table-2026.html"))

    def test_parses_skill_players_and_drops_k_dst(self):
        recs = self._records()
        # 300 rows in the table; K/DST removed → 250 QB/RB/WR/TE.
        assert len(recs) == 250
        assert {r["position"] for r in recs} == {"QB", "RB", "WR", "TE"}

    def test_overall_rank_preserved_with_gaps(self):
        recs = self._records()
        ranks = [r["overall_rank"] for r in recs]
        assert ranks[0] == 1
        assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)  # strictly increasing, unique
        assert ranks[-1] > len(recs)  # gaps exist where K/DST were removed

    def test_position_rank_computed_within_position(self):
        recs = self._records()
        first = {r["position"]: r for r in recs if r["position_rank"] == 1}
        assert first["RB"]["player_name"] == "Jahmyr Gibbs"
        assert first["WR"]["player_name"] == "Ja'Marr Chase"
        assert first["QB"]["player_name"] == "Josh Allen"
        # position_rank is dense 1..N within each position
        for pos in ("QB", "RB", "WR", "TE"):
            prs = sorted(r["position_rank"] for r in recs if r["position"] == pos)
            assert prs == list(range(1, len(prs) + 1))

    def test_captures_team_abbrev_and_player_id(self):
        gibbs = next(r for r in self._records() if r["player_name"] == "Jahmyr Gibbs")
        assert gibbs["team"] == "DET"
        assert gibbs["yahoo_player_id"] == "40059"

    def test_empty_table_raises(self):
        with pytest.raises(ValueError, match="0 rows"):
            parse_top300_table("<table><tr><th>#</th><th>Player</th></tr></table>")


class TestTop300Discovery:
    def test_finds_full_board_url_on_author_page(self):
        url = discover_top300_url(_fixture("author-page.html"), season=2026)
        assert url is not None
        assert "top-300-overall-players-for-half-ppr" in url and url.startswith("https://")

    def test_wrong_season_returns_none(self):
        assert discover_top300_url(_fixture("author-page.html"), season=2025) is None


class TestValidateFullBoard:
    def test_non_contiguous_allowed_when_not_required(self):
        recs = parse_top300_table(_fixture("top300-table-2026.html"))
        validate_records(recs, verbose=False, require_contiguous=False)  # gaps OK

    def test_duplicate_rank_rejected(self):
        recs = parse_top300_table(_fixture("top300-table-2026.html"))
        recs[1]["overall_rank"] = recs[0]["overall_rank"]
        with pytest.raises(ValueError, match="strictly increasing"):
            validate_records(recs, verbose=False, require_contiguous=False)


# ---------------------------------------------------- full fetch orchestration (no network)
class _FixtureSession:
    """Serves the saved fixtures: the author page and each article by its id."""

    def __init__(self):
        self.calls = 0

    def get(self, url, allow_redirects=True, timeout=None):
        self.calls += 1
        if url.rstrip("/") == YAHOO_AUTHOR_URL.rstrip("/"):
            body = _fixture("author-page.html")
        else:
            aid = article_id_from_url(url)
            name = {"170028428": PARTS[(1, 12)], "160536658": PARTS[(13, 24)], "140636820": PARTS[(25, 36)]}[aid]
            body = _fixture(name)
        return _FakeResponse(200, url, body)


class _FlakySession(_FixtureSession):
    """Like _FixtureSession, but serves a truncated 25-36 page on its FIRST hit for it."""

    def __init__(self):
        super().__init__()
        self._served_bad = False

    def get(self, url, allow_redirects=True, timeout=None):
        if article_id_from_url(url) == "140636820" and not self._served_bad:
            self._served_bad = True
            self.calls += 1
            # A partial page: only the intro strong, no player entries.
            return _FakeResponse(200, url, "<html><body><strong>My warning</strong></body></html>")
        return super().get(url, allow_redirects, timeout)


class TestFetchYahooHwAnalysisPath:
    """The analysis-article assembly (full_board=False → no browser, deterministic from fixtures)."""

    def test_retries_transient_partial_page_and_recovers(self, tmp_path):
        # The 25-36 article first returns a truncated body (parse fails), then the full page.
        out = fetch_yahoo_hw(
            str(tmp_path),
            season=2026,
            session=_FlakySession(),
            cache_dir=str(tmp_path / "cache"),
            sleep=lambda _s: None,
            player_key_path=str(tmp_path / "no-key.json"),  # skip reconciliation
            full_board=False,
            verbose=False,
        )
        import pandas as pd

        df = pd.read_csv(out)
        assert len(df) == 36 and list(df["RK"]) == list(range(1, 37))

    def test_discovers_parses_and_writes_board(self, tmp_path):
        import pandas as pd

        key_path = Path(__file__).resolve().parents[1] / "player_key_dict.json"
        out = fetch_yahoo_hw(
            str(tmp_path),
            season=2026,
            session=_FixtureSession(),
            cache_dir=str(tmp_path / "cache"),
            sleep=lambda _s: None,
            player_key_path=str(key_path),
            full_board=False,
            verbose=False,
        )
        assert out == str(tmp_path / "hw-yahoo-2026.csv")

        df = pd.read_csv(out)
        assert list(df.columns) == HW_OUTPUT_COLUMNS
        assert len(df) == 36
        assert list(df["RK"]) == list(range(1, 37))
        # Reconciliation ran: Yahoo's "A.J. Brown" is stored as the dict's "AJ Brown".
        assert "AJ Brown" in set(df["PLAYER NAME"])
        assert df.loc[df["RK"] == 1, "PLAYER NAME"].iloc[0] == "Jahmyr Gibbs"
