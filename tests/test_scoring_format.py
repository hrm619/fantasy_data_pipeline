"""Every redraft source must be pinned to the same scoring format: HALF-PPR.

A format mismatch is invisible downstream. Each source emits the same columns of plausible
integer ranks whatever format it was pulled in, so a PPR board and a half-PPR board are
indistinguishable on disk — it surfaces only as a subtly skewed consensus. Two sources were
silently on full PPR before these tests existed:

- `fp` defaulted to `scoring="ppr"`, and `refresh-all` passes no scoring.
- `pff`'s rankings page defaults to PPR and its CSV export follows the on-page dropdown,
  which the fetcher never touched. This one also fed `avg_RK` (only adp_/fp_/avg_/sd_ are
  excluded from the consensus math), so it skewed every ADP Delta on the board.

These are constant-level guards, not live checks — the live assertions are in the fetchers
themselves (`_select_pff_scoring`, `_assert_ds_adp_board`).
"""

from fantasy_pipeline.scraper.fetch_rankings import (
    DRAFTSHARKS_URL,
    DS_ADP_SCORING,
    FP_CHEATSHEET_URLS,
    FP_DEFAULT_SCORING,
    PFF_SCORING_LABEL,
    fetch_fantasypros_rankings,
)


class TestHalfPprIsTheBoardFormat:
    def test_fp_defaults_to_half_ppr(self):
        assert FP_DEFAULT_SCORING == "half-ppr"

    def test_fp_default_resolves_to_the_half_point_cheatsheet(self):
        """The default must reach the half-point URL, not merely be named 'half-ppr'."""
        assert "half-point-ppr" in FP_CHEATSHEET_URLS[FP_DEFAULT_SCORING]

    def test_fp_fetcher_signature_carries_the_half_ppr_default(self):
        """`refresh-all` calls this with no `scoring`, so the default is what ships."""
        import inspect

        default = inspect.signature(fetch_fantasypros_rankings).parameters["scoring"].default
        assert default == FP_DEFAULT_SCORING == "half-ppr"

    def test_pff_targets_half_ppr(self):
        """Must match PFF's dropdown option text exactly — selection is an exact match."""
        assert PFF_SCORING_LABEL == "Half PPR"

    def test_draftsharks_sources_are_half_ppr(self):
        assert DS_ADP_SCORING == "half-ppr"
        assert DRAFTSHARKS_URL.endswith("/half-ppr")
