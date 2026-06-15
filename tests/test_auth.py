"""Tests for the saved-session auth helper (no browser, no network).

Covers path resolution, the AUTH_DIR override, and the friendly 'not logged in'
error. The interactive `login()` itself needs a real browser and is not unit-tested.
"""

import pytest

from fantasy_pipeline.scraper import auth


@pytest.fixture
def auth_dir(tmp_path, monkeypatch):
    """Point the auth helper at a temp dir (auto-reverted; no global reload)."""
    monkeypatch.setattr(auth, "AUTH_DIR", tmp_path)
    return tmp_path


class TestStorageStatePath:
    def test_path_for_known_source(self, auth_dir):
        assert auth.storage_state_path("pff") == auth_dir / "pff.json"

    def test_unknown_source_raises(self, auth_dir):
        with pytest.raises(ValueError, match="Unknown auth source"):
            auth.storage_state_path("espn")

    def test_all_login_sources_resolve(self, auth_dir):
        for source in auth.SOURCE_LOGIN_URLS:
            assert auth.storage_state_path(source).name == f"{source}.json"


class TestLoadStorageState:
    def test_missing_session_raises_with_login_hint(self, auth_dir):
        with pytest.raises(RuntimeError, match="ff-rankings login pff"):
            auth.load_storage_state("pff")

    def test_returns_path_when_session_exists(self, auth_dir):
        (auth_dir / "pff.json").write_text("{}")
        assert auth.load_storage_state("pff") == str(auth_dir / "pff.json")
