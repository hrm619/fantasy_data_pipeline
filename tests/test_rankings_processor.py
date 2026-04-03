import pytest
from fantasy_pipeline.core.rankings_processor import RankingsProcessor
from fantasy_pipeline.config import FILE_MAPPINGS


class TestRankingsProcessorInit:
    def test_default_redraft(self):
        proc = RankingsProcessor()
        assert proc.league_type == "redraft"
        assert proc.week is None

    def test_bestball(self):
        proc = RankingsProcessor("bestball")
        assert proc.league_type == "bestball"

    def test_weekly_requires_week(self):
        with pytest.raises(ValueError, match="Week number is required"):
            RankingsProcessor("weekly")

    def test_weekly_with_week(self):
        proc = RankingsProcessor("weekly", week=5)
        assert proc.league_type == "weekly"
        assert proc.week == 5

    def test_unsupported_league_type(self):
        with pytest.raises(ValueError, match="Unsupported league type"):
            RankingsProcessor("dynasty")

    def test_has_expected_processors(self):
        proc = RankingsProcessor()
        expected = {"fpts", "fp", "ds", "hw", "jj", "pff", "adp"}
        assert set(proc.processors.keys()) == expected

    def test_weekly_excludes_adp_processor(self):
        proc = RankingsProcessor("weekly", week=1)
        assert "adp" not in proc.processors

    def test_ros_excludes_adp_processor(self):
        proc = RankingsProcessor("ros", week=1)
        assert "adp" not in proc.processors


class TestProcessRankingsSignature:
    def test_return_dataframe_param_exists(self):
        proc = RankingsProcessor()
        import inspect
        sig = inspect.signature(proc.process_rankings)
        assert "return_dataframe" in sig.parameters
        assert sig.parameters["return_dataframe"].default is False

    def test_return_type_annotation(self):
        import inspect
        sig = inspect.signature(RankingsProcessor.process_rankings)
        assert sig.return_annotation == "str | pd.DataFrame"
