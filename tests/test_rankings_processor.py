import pytest
from fantasy_pipeline.core.rankings_processor import RankingsProcessor


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


class TestConsensusColumnExclusion:
    """avg_RK / sd_RK / avg_POS RANK must average EXPERT sources only.

    'adp_*' is market data. Including it made `ADP Delta = ADP - avg_RK` partly
    self-referential — ADP on both sides shrinks every delta toward zero, attenuating the
    divergence signal the board exists to measure.
    """

    def test_market_and_derived_prefixes_excluded(self):
        from fantasy_pipeline.core.rankings_processor import _is_derived_or_market_col

        assert _is_derived_or_market_col("adp_RK")
        assert _is_derived_or_market_col("adp_POS RANK")
        assert _is_derived_or_market_col("avg_RK")  # never let a derived col feed itself
        assert _is_derived_or_market_col("sd_RK")

    def test_expert_sources_not_excluded(self):
        from fantasy_pipeline.core.rankings_processor import _is_derived_or_market_col

        for col in ("pff_RK", "ds_RK", "hw_RK", "jj_RK", "fpts_RK", "pff_POS RANK"):
            assert not _is_derived_or_market_col(col)

    def test_avg_rk_ignores_adp_column(self):
        import pandas as pd

        proc = RankingsProcessor("redraft")
        # adp_RK is a wild outlier: if it leaked into the mean, avg_RK would not be 2.0.
        df = pd.DataFrame({"pff_RK": [1.0], "ds_RK": [3.0], "adp_RK": [99.0]})
        out = proc._calculate_average_rankings(df, verbose=False)
        assert out["avg_RK"].iloc[0] == 2.0

    def test_avg_pos_rank_ignores_adp_column(self):
        import pandas as pd

        proc = RankingsProcessor("redraft")
        df = pd.DataFrame({"pff_POS RANK": [1.0], "ds_POS RANK": [3.0], "adp_POS RANK": [99.0]})
        out = proc._calculate_average_rankings(df, verbose=False)
        assert out["avg_POS RANK"].iloc[0] == 2.0


class TestNumericFormatting:
    def test_ranks_and_tiers_become_nullable_ints(self):
        import pandas as pd

        proc = RankingsProcessor("redraft")
        df = pd.DataFrame(
            {
                "pff_RK": [1.0, None],  # NaN forces float64 on load; must stay integral
                "fp_TIER": [2.0, 3.0],
                "ds_POS RANK": [4.0, 5.0],
                "ADP ROUND": [1.0, 2.0],
                "ECR": [7.0, 8.0],
            }
        )
        out = proc._format_numeric_columns(df, verbose=False)
        for col in ("pff_RK", "fp_TIER", "ds_POS RANK", "ADP ROUND", "ECR"):
            assert str(out[col].dtype) == "Int64", col
        assert out["pff_RK"].iloc[0] == 1
        assert pd.isna(out["pff_RK"].iloc[1])  # gaps survive the int cast

    def test_calculated_floats_rounded_to_one_dp(self):
        import pandas as pd

        proc = RankingsProcessor("redraft")
        df = pd.DataFrame(
            {
                "sd_RK": [0.8944271909999159],
                "ADP Delta": [-0.3999999999999999],
                "avg_RK": [1.44444],
                "avg_POS RANK": [2.55555],
                "HIST_FPTS_PER_GAME": [19.8231],
            }
        )
        out = proc._format_numeric_columns(df, verbose=False)
        assert out["sd_RK"].iloc[0] == 0.9
        assert out["ADP Delta"].iloc[0] == -0.4
        assert out["avg_RK"].iloc[0] == 1.4
        assert out["avg_POS RANK"].iloc[0] == 2.6
        assert out["HIST_FPTS_PER_GAME"].iloc[0] == 19.8

    def test_non_numeric_columns_untouched(self):
        import pandas as pd

        proc = RankingsProcessor("redraft")
        df = pd.DataFrame({"PLAYER NAME": ["Jahmyr Gibbs"], "PLAYER ID": ["GibbJa01"], "POS": ["RB"]})
        out = proc._format_numeric_columns(df, verbose=False)
        assert out["PLAYER NAME"].iloc[0] == "Jahmyr Gibbs"
        assert out["PLAYER ID"].iloc[0] == "GibbJa01"


class TestSkipSources:
    """Every mapped source is required, so --skip-source is the supported way to omit one."""

    def test_skipped_source_removed_from_file_mapping(self):
        proc = RankingsProcessor("redraft", skip_sources=["fpts"])
        assert "fpts" not in proc.file_mapping
        assert "pff" in proc.file_mapping

    def test_default_keeps_all_sources(self):
        proc = RankingsProcessor("redraft")
        assert proc.skip_sources == []
        assert "fpts" in proc.file_mapping

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Cannot skip unknown source"):
            RankingsProcessor("redraft", skip_sources=["nonesuch"])

    def test_skip_does_not_mutate_shared_file_mappings(self):
        # FILE_MAPPINGS is module-level: filtering it in place would leak the skip into
        # every processor built afterwards.
        from fantasy_pipeline.config import FILE_MAPPINGS

        RankingsProcessor("redraft", skip_sources=["fpts"])
        assert "fpts" in FILE_MAPPINGS["redraft"]
        assert "fpts" in RankingsProcessor("redraft").file_mapping

    def test_multiple_skips(self):
        proc = RankingsProcessor("redraft", skip_sources=["fpts", "jj"])
        assert "fpts" not in proc.file_mapping and "jj" not in proc.file_mapping
        assert "adp" in proc.file_mapping
