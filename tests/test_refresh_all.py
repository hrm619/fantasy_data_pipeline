"""Tests for the `ff-rankings refresh-all` orchestration (fetch all → consolidate).

Browser/network-free: the six fetchers and the consolidation processor are stubbed, so
these assert the wiring/resilience (run all, tolerate failures, honor flags), not the
real fetch logic (covered per-source elsewhere).
"""

import fantasy_pipeline
import fantasy_pipeline.scraper.fetch_rankings as fr
from fantasy_pipeline.cli.rankings import _refresh_all_command

FETCHER_NAMES = [
    "fetch_fantasypros_adp",
    "fetch_fantasypros_rankings",
    "fetch_draftsharks",
    "fetch_pff",
    "fetch_fpts",
    "fetch_jj",
]


def _stub_fetchers(monkeypatch, calls, failing=()):
    for name in FETCHER_NAMES:
        def make(n):
            def f(*args, **kwargs):
                calls.append(n)
                if n in failing:
                    raise RuntimeError(f"{n} boom (session expired)")
                return f"/x/{n}"
            return f
        monkeypatch.setattr(fr, name, make(name))


class _FakeProcessor:
    state = {}

    def __init__(self, league_type):
        _FakeProcessor.state["league"] = league_type

    def process_rankings(self, **kwargs):
        _FakeProcessor.state["consolidated"] = True
        _FakeProcessor.state["kwargs"] = kwargs
        return "/out/rankings_ready.csv"


def _stub_processor(monkeypatch):
    _FakeProcessor.state = {}
    monkeypatch.setattr(fantasy_pipeline, "RankingsProcessor", _FakeProcessor)


def _add_manual_hw(tmp_path):
    """Drop the manual Hayden Winks file the redraft pipeline requires."""
    (tmp_path / "tableDownload.csv").write_text("x")


def test_runs_all_fetchers_then_consolidates(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls)
    _stub_processor(monkeypatch)
    _add_manual_hw(tmp_path)

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert rc == 0
    assert sorted(calls) == sorted(FETCHER_NAMES)          # all six ran
    assert _FakeProcessor.state["league"] == "redraft"
    assert _FakeProcessor.state["consolidated"] is True


def test_skips_consolidation_when_manual_hw_missing(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls)
    _stub_processor(monkeypatch)
    # no tableDownload.csv in update/

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert sorted(calls) == sorted(FETCHER_NAMES)          # fetch still ran
    assert "consolidated" not in _FakeProcessor.state      # but consolidation was skipped
    assert rc == 1


def test_continues_on_fetcher_failure_but_returns_nonzero(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls, failing={"fetch_pff"})
    _stub_processor(monkeypatch)
    _add_manual_hw(tmp_path)

    rc = _refresh_all_command(["--data-path", str(tmp_path)])

    assert len(calls) == len(FETCHER_NAMES)                # a failure didn't stop the rest
    assert _FakeProcessor.state.get("consolidated") is True  # still consolidated
    assert rc == 1                                         # but signals partial failure


def test_no_consolidate_skips_processor(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls)
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path), "--no-consolidate"])

    assert sorted(calls) == sorted(FETCHER_NAMES)
    assert "consolidated" not in _FakeProcessor.state      # processor never invoked
    assert rc == 0


def test_strict_aborts_consolidation_on_failure(monkeypatch, tmp_path):
    calls = []
    _stub_fetchers(monkeypatch, calls, failing={"fetch_jj"})
    _stub_processor(monkeypatch)

    rc = _refresh_all_command(["--data-path", str(tmp_path), "--strict"])

    assert "consolidated" not in _FakeProcessor.state      # aborted before consolidating
    assert rc == 1


def test_auto_login_skips_paywalled_source_with_invalid_session(monkeypatch, tmp_path):
    import fantasy_pipeline.scraper.fetch_rankings as fr

    calls = []
    _stub_fetchers(monkeypatch, calls)
    _stub_processor(monkeypatch)
    _add_manual_hw(tmp_path)
    # jj can't re-auth (login not completed); the other paywalled sources are fine.
    monkeypatch.setattr(fr, "ensure_session", lambda s: s != "jj")

    rc = _refresh_all_command(["--data-path", str(tmp_path), "--auto-login"])

    assert "fetch_jj" not in calls                          # skipped, session invalid
    assert "fetch_pff" in calls and "fetch_fpts" in calls   # re-authed, ran
    assert "fetch_fantasypros_adp" in calls                 # free sources unaffected
    assert _FakeProcessor.state.get("consolidated") is True  # still consolidated
    assert rc == 1                                          # jj counted as a failure
