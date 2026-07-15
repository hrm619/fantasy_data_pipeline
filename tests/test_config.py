"""Season-rollover contract: every season-specific filename/URL must derive from
the single `CURRENT_SEASON` constant, so a rollover is a one-line bump.

These guards fail if anyone re-hardcodes a literal year into a FILE_MAPPINGS prefix,
a fetcher's `year` default, or the HW scraper URL slug.
"""

import inspect

from fantasy_pipeline import config as c
from fantasy_pipeline.scraper.fetch_rankings import (
    fetch_draftsharks_adp,
    fetch_fantasypros_rankings,
)


class TestSeasonCentralization:
    def test_redraft_fp_prefix_tracks_current_season(self):
        assert str(c.CURRENT_SEASON) in c.FILE_MAPPINGS["redraft"]["fp"]
        assert c.FILE_MAPPINGS["redraft"]["fp"] == (f"FantasyPros_{c.CURRENT_SEASON}_Draft_ALL_Rankings")

    def test_redraft_adp_prefix_tracks_current_season(self):
        assert c.FILE_MAPPINGS["redraft"]["adp"] == (f"DraftSharks_{c.CURRENT_SEASON}_Sleeper_ADP")

    def test_bestball_fp_prefix_tracks_current_season(self):
        assert c.FILE_MAPPINGS["bestball"]["fp"] == (f"FantasyPros_{c.CURRENT_SEASON}_Draft_ALL_Rankings")

    def test_ros_fpts_file_pattern_tracks_current_season(self):
        assert c.FILE_MAPPINGS["ros"]["fpts"] == [str(c.CURRENT_SEASON)]
        assert c.get_ros_file_mappings(6)["fpts"] == [str(c.CURRENT_SEASON)]

    def test_fetcher_year_defaults_track_current_season(self):
        adp_default = inspect.signature(fetch_draftsharks_adp).parameters["year"].default
        fp_default = inspect.signature(fetch_fantasypros_rankings).parameters["year"].default
        assert adp_default == c.CURRENT_SEASON
        assert fp_default == c.CURRENT_SEASON

    def test_hw_scraper_url_slug_tracks_current_season(self):
        url = c.get_hw_scraper_url(week=8, league_type="weekly")
        assert url.endswith(f"the-blueprint-{c.CURRENT_SEASON}")
