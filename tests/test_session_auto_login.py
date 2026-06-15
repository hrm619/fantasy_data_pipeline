"""Tests for session validation auto-login orchestration (`ensure_session`).

Browser-free: `validate_session` (the live probe) and `auth.login` (the headed window)
are stubbed, so these assert only the decision logic.
"""

import fantasy_pipeline.scraper.auth as auth
import fantasy_pipeline.scraper.fetch_rankings as fr


def test_valid_session_skips_login(monkeypatch):
    monkeypatch.setattr(fr, "validate_session", lambda s: True)
    logins = []
    monkeypatch.setattr(auth, "login", lambda *a, **k: logins.append(1))

    assert fr.ensure_session("pff") is True
    assert logins == []  # never opened a login window


def test_invalid_session_triggers_login_then_revalidates(monkeypatch):
    states = iter([False, True])  # expired, then valid after login
    monkeypatch.setattr(fr, "validate_session", lambda s: next(states))
    logins = []
    monkeypatch.setattr(auth, "login", lambda s, **k: logins.append(s))

    assert fr.ensure_session("fpts") is True
    assert logins == ["fpts"]  # opened the login window once


def test_no_autologin_returns_false_without_login(monkeypatch):
    monkeypatch.setattr(fr, "validate_session", lambda s: False)
    logins = []
    monkeypatch.setattr(auth, "login", lambda *a, **k: logins.append(1))

    assert fr.ensure_session("jj", auto_login=False) is False
    assert logins == []


def test_login_failure_returns_false(monkeypatch):
    monkeypatch.setattr(fr, "validate_session", lambda s: False)

    def boom(*a, **k):
        raise RuntimeError("login cancelled")

    monkeypatch.setattr(auth, "login", boom)
    assert fr.ensure_session("pff") is False
