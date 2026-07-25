"""Tests for the `ff-rankings refresh-all` orchestration (fetch all → consolidate).

Browser/network-free: the seven fetchers and the consolidation processor are stubbed, so
these assert the wiring/resilience (run all, tolerate failures, honor flags), not the
real fetch logic (covered per-source elsewhere).
"""

import importlib

import pytest

import fantasy_pipeline
import fantasy_pipeline.scraper.fetch_rankings as fr
from fantasy_pipeline.cli.rankings import _refresh_all_command
from fantasy_pipeline.config import FILE_MAPPINGS

# The scraper package re-exports a `fetch_yahoo_hw` *function* under the same name as the
# submodule, so grab the module explicitly (the package attribute is the shadowing function).
fyh = importlib.import_module("fantasy_pipeline.scraper.fetch_yahoo_hw")

# The six fetchers that live in fetch_rankings (Hayden Winks/Yahoo lives in its own module).
FETCHER_NAMES = [
    "fetch_draftsharks_adp",
    "fetch_fantasypros_rankings",
    "fetch_draftsharks",
    "fetch_pff",
    "fetch_fpts",
    "fetch_jj",
]
HW_NAME = "fetch_yahoo_hw"
ALL_FETCHERS = FETCHER_NAMES + [HW_NAME]


# Which pipeline source each fetcher supplies. The consolidation guard keys off the FILES on
# disk rather than which fetchers raised, so a successful stub has to land a real filename.
FETCHER_SOURCES = {
    "fetch_draftsharks_adp": "adp",
    "fetch_fantasypros_rankings": "fp",
    "fetch_draftsharks": "ds",
    "fetch_pff": "pff",
    "fetch_fpts": "fpts",
    "fetch_jj": "jj",
    HW_NAME: "hw",
}


def _land_file(tmp_path, source):
    """Write a file the processor's `startswith` matching would accept for `source`."""
    prefix = FILE_MAPPINGS["redraft"][source]
    prefix = prefix[0] if isinstance(prefix, (list, tuple)) else prefix
    path = tmp_path / f"{prefix}.csv"
    path.write_text("x")
    return str(path)


def _stub_fetchers(monkeypatch, calls, tmp_path, failing=()):
    """Stub all seven fetchers; a successful one lands its source's file in `tmp_path`."""
    for name in FETCHER_NAMES:

        def make(n):
            def f(*args, **kwargs):
                calls.append(n)
                if n in failing:
                    raise RuntimeError(f"{n} boom (session expired)")
                return _land_file(tmp_path, FETCHER_SOURCES[n])

            return f

        monkeypatch.setattr(fr, name, make(name))

    def hw(*args, **kwargs):
        calls.append(HW_NAME)
        if HW_NAME in failing:
            raise RuntimeError("hw boom (Yahoo throttled)")
        return _land_file(tmp_path, "hw")

    # The command does `from ...fetch_yahoo_hw import fetch_yahoo_hw` at call time, so patching
    # the module attribute takes effect.
    monkeypatch.setattr(fyh, "fetch_yahoo_hw", hw)


class _FakeProcessor:
    state = {}

    def __init__(self, league_type, skip_sources=None):
        _FakeProcessor.state["league"] = league_type
        _FakeProcessor.state["skip_sources"] = skip_sources

    def process_rankings(self, **kwargs):
        _FakeProcessor.state["consolidated"] = True
        _FakeProcessor.state["kwargs"] = kwargs
        return "/out/rankings_ready.csv"


def _stub_processor(monkeypatch):
    _FakeProcessor.state = {}
    monkeypatch.setattr(fantasy_pipeline, "RankingsProcessor", _FakeProcessor)


def test_runs_all_fetchers_then_consolidates(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path)
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert rc == 0
    assert sorted(calls) == sorted(ALL_FETCHERS)  # all seven ran
    assert _FakeProcessor.state["league"] == "redraft"
    assert _FakeProcessor.state["consolidated"] is True


def test_consolidates_without_a_source_that_did_not_land(monkeypatch, tmp_path):
    """A late-publishing source must not cost you the other six.

    Barrett's board is routinely unpublished through the early preseason, and the fetcher
    correctly refuses to save last season's ranks under this season's name. Every source in
    file_mapping is required, so that used to abort the whole consolidation.
    """
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path, failing={"fetch_fpts"})
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert sorted(calls) == sorted(ALL_FETCHERS)  # a failure didn't stop the rest
    assert _FakeProcessor.state["consolidated"] is True  # board still built
    assert _FakeProcessor.state["skip_sources"] == ["fpts"]  # without the missing source
    assert rc == 1  # but a partial board still signals non-zero


def test_hw_failure_no_longer_blocks_the_board(monkeypatch, tmp_path):
    # HW used to be special-cased into skipping consolidation entirely; it is now just
    # another skippable expert source.
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path, failing={HW_NAME})
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert _FakeProcessor.state["consolidated"] is True
    assert _FakeProcessor.state["skip_sources"] == ["hw"]
    assert rc == 1


@pytest.mark.parametrize("fetcher,source", [("fetch_fantasypros_rankings", "fp"), ("fetch_draftsharks_adp", "adp")])
def test_missing_structural_source_blocks_consolidation(monkeypatch, tmp_path, fetcher, source):
    """fp and adp aren't one opinion among several.

    The board's universe and every player's name/position/team come from fp, and
    _organize_final_dataframe drops rows on ADP (skipping adp raises KeyError: ['ADP']).
    Skipping either doesn't produce a thinner board — it produces no board.
    """
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path, failing={fetcher})
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert sorted(calls) == sorted(ALL_FETCHERS)  # fetch still ran
    assert "consolidated" not in _FakeProcessor.state  # but consolidation was skipped
    assert rc == 1


def test_a_stale_file_still_counts_as_landed(monkeypatch, tmp_path):
    # Keyed off files on disk, not which fetchers raised: if a usable file from an earlier
    # run is sitting in update/, use it rather than skipping the source.
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path, failing={"fetch_pff"})
    _land_file(tmp_path, "pff")  # left over from a previous refresh
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert _FakeProcessor.state["consolidated"] is True
    assert _FakeProcessor.state["skip_sources"] is None  # nothing skipped — the file was there
    assert rc == 1  # the fetch itself still failed


def test_no_consolidate_skips_processor(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path)
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path), "--no-consolidate"])

    assert sorted(calls) == sorted(ALL_FETCHERS)
    assert "consolidated" not in _FakeProcessor.state  # processor never invoked
    assert rc == 0


def test_strict_aborts_consolidation_on_failure(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path, failing={"fetch_jj"})
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path), "--strict"])

    assert "consolidated" not in _FakeProcessor.state  # aborted before consolidating
    assert rc == 1


def test_auto_login_skips_paywalled_source_with_invalid_session(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path)
    _stub_processor(monkeypatch)
    # jj can't re-auth (login not completed); the other paywalled sources are fine.
    monkeypatch.setattr(fr, "ensure_session", lambda s: s != "jj")

    rc = _refresh_all_command(["--data-path", str(tmp_path), "--auto-login"])

    assert "fetch_jj" not in calls  # skipped, session invalid
    assert "fetch_pff" in calls and "fetch_fpts" in calls  # re-authed, ran
    assert "fetch_fantasypros_rankings" in calls  # the one account-free source, unaffected
    assert HW_NAME in calls  # HW needs no session; ran and landed its file
    assert _FakeProcessor.state.get("consolidated") is True  # still consolidated
    assert rc == 1  # jj counted as a failure


def test_adp_rides_the_ds_session(monkeypatch, tmp_path):
    """ADP comes from DraftSharks now, so a dead 'ds' session must skip it too.

    Guards the wiring that used to map adp -> the FantasyPros 'fp' session.
    """
    calls = []
    _stub_fetchers(monkeypatch, calls, tmp_path)
    _stub_processor(monkeypatch)
    monkeypatch.setattr(fr, "ensure_session", lambda s: s != "ds")

    rc = _refresh_all_command(["--data-path", str(tmp_path), "--auto-login"])

    assert "fetch_draftsharks_adp" not in calls  # gated behind the same login as ds
    assert "fetch_draftsharks" not in calls
    assert "fetch_fantasypros_rankings" in calls  # needs no account
    assert rc == 1
