"""Season-rollover contract: every season-specific filename/URL must derive from
the single `CURRENT_SEASON` constant, so a rollover is a one-line bump.

These guards fail if anyone re-hardcodes a literal year into a FILE_MAPPINGS prefix,
a fetcher's `year` default, or the HW scraper URL slug.
"""

import inspect
import os

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


class TestProjectRootResolution:
    """Defaults used to be CWD-relative strings, so the pipeline only worked when invoked
    from the repo root. That broke every programmatic caller: `fantasy-data ingest rankings`
    runs from the sibling repo and failed on "Data directory not found", and a scheduler
    would hit the same wall."""

    def test_defaults_are_absolute(self):
        from fantasy_pipeline.config import DEFAULT_PATHS, HISTORICAL_DATA_DIR

        for key, path in DEFAULT_PATHS.items():
            assert os.path.isabs(path), f"{key} is not absolute: {path}"
        assert os.path.isabs(HISTORICAL_DATA_DIR)

    def test_defaults_point_at_the_real_project(self):
        from fantasy_pipeline.config import DEFAULT_PATHS

        assert os.path.exists(DEFAULT_PATHS["player_key_file"])

    def test_env_var_overrides(self, tmp_path, monkeypatch):
        from fantasy_pipeline.config import project_root

        monkeypatch.setenv("FANTASY_PIPELINE_HOME", str(tmp_path))
        assert project_root() == tmp_path

    def test_cwd_wins_when_it_looks_like_the_project(self, tmp_path, monkeypatch):
        # Preserves the historical behaviour for anyone already running from a checkout —
        # including a different checkout than the installed package.
        from fantasy_pipeline.config import PLAYER_KEY_FILENAME, project_root

        monkeypatch.delenv("FANTASY_PIPELINE_HOME", raising=False)
        (tmp_path / PLAYER_KEY_FILENAME).write_text("{}")
        monkeypatch.chdir(tmp_path)
        assert project_root() == tmp_path

    def test_falls_back_to_the_package_root_from_an_unrelated_cwd(self, tmp_path, monkeypatch):
        # The case that makes running from anywhere work.
        from fantasy_pipeline.config import PLAYER_KEY_FILENAME, project_root

        monkeypatch.delenv("FANTASY_PIPELINE_HOME", raising=False)
        monkeypatch.chdir(tmp_path)  # no player_key_dict.json here
        root = project_root()
        assert (root / PLAYER_KEY_FILENAME).exists()
