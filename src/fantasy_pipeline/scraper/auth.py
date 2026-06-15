"""Saved-session auth for the paywalled ranking sources (fpts, pff, jj).

Strategy: the user logs in **once** per source in a real (headed) browser via
`ff-rankings login <source>`; we persist that browser context's cookies/localStorage
("storage state") to a file **outside the repo** so passwords are never stored or seen.
The headless fetchers then reuse that storage state to reach the logged-in export.

Secrets location: ``~/.fantasy_pipeline/auth/<source>.json`` (outside the git tree by
design — nothing to .gitignore). Re-run `login` when a session expires.
"""

import os
from pathlib import Path

# Login pages for each paywalled source. The fetchers own their rankings/export URLs;
# this maps only the page to land on for the one-time interactive login.
SOURCE_LOGIN_URLS = {
    "pff": "https://www.pff.com/login",
    "fpts": "https://www.fantasypoints.com/login",
    "jj": "https://www.patreon.com/login",
}

# Where persisted sessions live — deliberately outside the repo working tree.
AUTH_DIR = Path(os.environ.get("FANTASY_PIPELINE_AUTH_DIR",
                               Path.home() / ".fantasy_pipeline" / "auth"))


def storage_state_path(source: str) -> Path:
    """Return the path to ``<source>``'s persisted Playwright storage-state file."""
    if source not in SOURCE_LOGIN_URLS:
        raise ValueError(
            f"Unknown auth source '{source}'. Known: {sorted(SOURCE_LOGIN_URLS)}"
        )
    return AUTH_DIR / f"{source}.json"


def load_storage_state(source: str) -> str:
    """Return the storage-state path for ``source`` as a str, or raise if not logged in.

    The fetchers pass this to ``browser.new_context(storage_state=...)``.
    """
    path = storage_state_path(source)
    if not path.exists():
        raise RuntimeError(
            f"No saved session for '{source}'. Log in once with:\n"
            f"  ff-rankings login {source}\n"
            f"(opens a browser; the session is saved to {path})"
        )
    return str(path)


def login(source: str, timeout_minutes: int = 10) -> str:
    """Open a headed browser for a one-time interactive login and persist the session.

    Navigates to the source's login page, waits for you to log in manually (handles
    2FA / SSO / OAuth — whatever the site requires), then saves the browser context's
    storage state. Press Enter in the terminal once you're logged in.

    Args:
        source: One of ``SOURCE_LOGIN_URLS`` (pff, fpts, jj).
        timeout_minutes: How long the login page stays open before auto-closing.

    Returns:
        Path to the saved storage-state JSON.
    """
    # Lazy import keeps Playwright an optional ('headless') dependency.
    from fantasy_pipeline.scraper.fetch_rankings import _require_playwright

    login_url = SOURCE_LOGIN_URLS.get(source)
    if login_url is None:
        raise ValueError(
            f"Unknown auth source '{source}'. Known: {sorted(SOURCE_LOGIN_URLS)}"
        )

    out_path = storage_state_path(source)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sync_playwright = _require_playwright()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

            print(f"\nA browser window opened at: {login_url}")
            print(f"Log in to {source.upper()} in that window (2FA/SSO is fine).")
            print(
                "When you're fully logged in and can see your account, return here "
                f"and press Enter to save the session (auto-closes in {timeout_minutes} min)."
            )
            try:
                _wait_for_enter(timeout_minutes * 60)
            except KeyboardInterrupt:
                print("\nLogin cancelled — no session saved.")
                raise

            context.storage_state(path=str(out_path))
        finally:
            browser.close()

    print(f"\n✅ Session for '{source}' saved to: {out_path}")
    return str(out_path)


def _wait_for_enter(timeout_seconds: int) -> None:
    """Block until the user presses Enter, or the timeout elapses (whichever first)."""
    import select
    import sys

    print(f"\n[waiting up to {timeout_seconds}s] Press Enter once logged in... ", end="", flush=True)
    ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
    if ready:
        sys.stdin.readline()
        print("saving session.")
    else:
        print("\nTimeout reached — saving whatever session exists now.")
