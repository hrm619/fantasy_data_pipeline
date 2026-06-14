"""Tests for the HW scraper URL builder and the empty-result guard.

The empty-result test monkeypatches requests.get so it never hits the network.
"""

import pytest

from fantasy_pipeline.config import get_hw_scraper_url, CURRENT_SEASON
from fantasy_pipeline.scraper import hw_scraper


class TestGetHwScraperUrl:
    def test_weekly_url_uses_default_season(self):
        url = get_hw_scraper_url(week=8, league_type="weekly")
        assert url.endswith(
            f"week-8-fantasy-football-rankings-the-blueprint-{CURRENT_SEASON}"
        )

    def test_ros_uses_same_pattern_as_weekly(self):
        assert get_hw_scraper_url(week=5, league_type="ros") == get_hw_scraper_url(
            week=5, league_type="weekly"
        )

    def test_season_is_parameterized(self):
        url = get_hw_scraper_url(week=1, league_type="weekly", season=2026)
        assert "the-blueprint-2026" in url
        assert "2025" not in url

    def test_requires_week(self):
        with pytest.raises(ValueError):
            get_hw_scraper_url(week=None, league_type="weekly")

    def test_rejects_redraft(self):
        with pytest.raises(ValueError):
            get_hw_scraper_url(week=8, league_type="redraft")


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


class TestEmptyResultGuard:
    def test_raises_when_no_players_parsed(self, monkeypatch):
        # A page with no recognizable player entries → parser yields 0 rows → must raise.
        monkeypatch.setattr(
            hw_scraper.requests,
            "get",
            lambda *a, **k: _FakeResponse(b"<html><body><p>No rankings here</p></body></html>"),
        )
        with pytest.raises(RuntimeError, match="0 players"):
            hw_scraper.scrape_fantasy_rankings("https://example.com/fake")
