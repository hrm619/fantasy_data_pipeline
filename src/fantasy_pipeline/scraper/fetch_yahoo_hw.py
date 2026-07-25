"""Fetch Hayden Winks' redraft rankings from Yahoo Sports.

Hayden Winks moved his season-long ("redraft") rankings from Underdog Network to Yahoo
Sports for 2026. Yahoo publishes them as a series of articles, each covering a 12-player
rank range ("... ranked 1-12 in Half-PPR", "... ranked 13-24 ...", and so on), released
incrementally through the preseason. This module discovers the published parts, parses each,
and writes a single pipeline-ready CSV for the redraft/bestball ``hw`` source.

Capability parity with the old manual Underdog ``tableDownload.csv``: for redraft only
``PLAYER NAME / TEAM / POS / POS RANK / RK`` from ``hw`` survive
``BaseProcessor._standardize_output`` — exactly what these articles provide. The remaining
six columns of ``COLUMN_MAPPINGS['hw']`` are emitted blank (they are discarded downstream), so
the pipeline's positional rename is satisfied without touching config's column mapping.

NOTE (weekly/ROS): the weekly "Blueprint" scraper (``hw_scraper.py``) still targets Underdog.
Winks' *weekly* content will need retargeting to Yahoo once the in-season articles start; there
is no weekly Yahoo article pattern to build against yet. This module is redraft-only.

Design notes:
- **Access.** Yahoo returns HTTP 999 to default library User-Agents, so a realistic desktop UA
  is sent and 999 is retried with backoff. Consent-redirect query params are stripped, and a
  redirect to ``guce.yahoo.com`` (the consent gate) is raised loudly rather than parsed as an
  article. Raw HTML is cached to disk keyed by article id, and requests are rate-limited.
- **Parsing.** Each player entry renders as its own single-item ``<ol>`` (so every list marker
  is "1"), and part 1 additionally has *no* ``<ol>`` at all — never derive rank from list markup.
  ``overall_rank = rank_range_start + document-order index`` and the entry count is asserted to
  equal the range span. ``parse_article`` is pure (HTML in, records out) so it is testable
  against saved fixtures with no network.
"""

import json
import os
import re
import time
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup, Tag

from fantasy_pipeline.config import CURRENT_SEASON, DEFAULT_PATHS


# A realistic desktop Chrome UA. Yahoo answers HTTP 999 to default requests/urllib UAs.
YAHOO_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

YAHOO_AUTHOR_URL = "https://sports.yahoo.com/author/hayden-winks/"

# The 11-column positional schema the redraft/bestball 'hw' source expects
# (must equal COLUMN_MAPPINGS['hw']). Only the first five survive standardization; the rest
# are placeholders emitted blank. The pipeline renames by *position*, so order is what matters.
HW_OUTPUT_COLUMNS = [
    "PLAYER NAME",
    "TEAM",
    "POS",
    "POS RANK",
    "RK",
    "UNDERDOG ADP",
    "PRIOR PER GAME",
    "PRIOR SEASON FINISH",
    "TEAM ID",
    "SPORT RADAR ID",
    "ID",
]

# Fallback article URLs per season, used when the author-page crawl finds nothing (layout
# drift, an empty page, or a network hiccup). Add new seasons here; within a season new parts
# are discovered automatically by the crawl, so this only needs the earliest known parts.
YAHOO_HW_KNOWN_ARTICLES = {
    2026: [
        "https://sports.yahoo.com/fantasy/article/2026-fantasy-football-rankings-analysis-for-players-ranked-1-12-in-half-ppr-170028428.html",
        "https://sports.yahoo.com/fantasy/article/2026-fantasy-football-rankings-analysis-for-players-ranked-13-24-in-half-ppr-160536658.html",
        "https://sports.yahoo.com/fantasy/article/2026-fantasy-football-rankings-analysis-for-players-ranked-25-36-in-half-ppr-140636820.html",
    ],
}

# Winks also publishes a single **full-board** article — his top-N overall (grows from top-250 to
# top-300+ over the preseason) — as one client-rendered <table>. This is the deep source
# (250+ players) vs the 12-at-a-time analysis articles (36 today). Its slug differs, so it needs
# its own discovery + a headless render (the table isn't in the server HTML).
YAHOO_HW_TOP300_KNOWN = {
    2026: "https://sports.yahoo.com/fantasy/article/2026-fantasy-football-rankings-hayden-winks-top-300-overall-players-for-half-ppr-143555896.html",
}
_TOP300_URL_RE = re.compile(
    r"/(?:fantasy/article|news)/(?P<season>\d{4})-fantasy-football-rankings-hayden-winks-"
    r"top-\d+-overall-players-for-half-ppr-(?P<id>\d+)\.html"
)
# Player cell renders "Jahmyr Gibbs\nDET - RB" — the second line is "<TEAM> - <POS>".
_TEAM_POS_RE = re.compile(r"([A-Z]{2,3})\s*-\s*([A-Za-z]+)")

# Header of a player entry, e.g. "De'Von Achane, RB7, Dolphins" (part 1 prefixes an overall
# rank, "1. Jahmyr Gibbs, RB1, Lions", stripped by _NAME_RANK_PREFIX_RE below).
_HEADER_RE = re.compile(r"^(?P<name>.+?),\s*(?P<pos>QB|RB|WR|TE)(?P<pos_rank>\d+),\s*(?P<team>.+)$")
_NAME_RANK_PREFIX_RE = re.compile(r"^\d+\.\s*")
_PLAYER_ID_RE = re.compile(r"/nfl/players/(\d+)/")
_TEAM_SLUG_RE = re.compile(r"/nfl/teams/([^/]+)/")
# Article slug: 2026-fantasy-football-rankings-analysis-for-players-ranked-<a>-<b>-in-half-ppr-<id>
_ARTICLE_URL_RE = re.compile(
    r"/fantasy/article/(?P<season>\d{4})-fantasy-football-rankings-analysis-for-players-"
    r"ranked-(?P<start>\d+)-(?P<end>\d+)-in-half-ppr-(?P<id>\d+)\.html"
)
_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.IGNORECASE)

SUPPORTED_POSITIONS = ("QB", "RB", "WR", "TE")


class ConsentGateError(RuntimeError):
    """Raised when Yahoo's consent gate (guce.yahoo.com) fires instead of serving the article."""


# --------------------------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------------------------
def strip_tracking_params(url: str) -> str:
    """Drop query params — Yahoo's guccounter/guce_* are consent-redirect artifacts that expire."""
    return url.split("?", 1)[0].split("#", 1)[0]


def article_id_from_url(url: str) -> Optional[str]:
    """Return the trailing numeric article id from a Yahoo article URL, or None.

    Keyed off the trailing ``-<digits>.html`` (used for cache filenames), so it works for any
    Yahoo article URL, not only the rank-range rankings slug.
    """
    match = re.search(r"-(\d+)\.html", url)
    return match.group(1) if match else None


def new_session() -> requests.Session:
    """A persistent session so Yahoo's A1/A3/GUC cookies carry across requests."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": YAHOO_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def fetch_html(
    url: str,
    session: Optional[requests.Session] = None,
    cache_dir: Optional[str] = None,
    max_retries: int = 4,
    rate_limit_s: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
    force_refresh: bool = False,
) -> str:
    """Fetch a Yahoo article's raw HTML, with 999 backoff, consent-gate detection, and caching.

    Args:
        url: Article URL (tracking params are stripped automatically).
        session: Reused persistent session (one is created if omitted).
        cache_dir: If set, HTML is cached here keyed by article id; a cache hit skips the network
            entirely (so re-parsing never re-fetches and the rate limit is never paid twice).
        max_retries: Attempts before giving up on an HTTP 999 (retryable throttle response).
        rate_limit_s: Minimum spacing between live requests (skipped on cache hit).
        sleep: Injectable sleep (tests pass a no-op).
        force_refresh: Ignore any cached copy and re-fetch (still overwrites the cache). Used to
            recover from a transient partial page that was cached before it could be validated.

    Raises:
        ConsentGateError: if the response redirects to Yahoo's consent gate.
        RuntimeError: on repeated 999s or other non-OK statuses.
    """
    url = strip_tracking_params(url)
    article_id = article_id_from_url(url)

    cache_path = None
    if cache_dir and article_id:
        cache_path = os.path.join(cache_dir, f"{article_id}.html")
        if not force_refresh and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as fh:
                return fh.read()

    session = session or new_session()

    last_status = None
    for attempt in range(max_retries):
        if attempt > 0 or rate_limit_s:
            sleep(rate_limit_s if attempt == 0 else rate_limit_s * (attempt + 1))
        response = session.get(url, allow_redirects=True, timeout=30)
        last_status = response.status_code

        # A redirect to the consent gate means we got the interstitial, not the article.
        if "guce.yahoo.com" in response.url:
            raise ConsentGateError(
                f"Yahoo consent gate fired for {url} (landed on {response.url}). "
                "Cookies were not accepted; cannot parse the interstitial as an article."
            )

        if response.status_code == 999:
            continue  # retryable throttle — back off and try again
        if response.status_code == 200:
            html = response.text
            if cache_path:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as fh:
                    fh.write(html)
            return html
        response.raise_for_status()

    raise RuntimeError(f"Yahoo returned HTTP {last_status} for {url} after {max_retries} attempts")


# --------------------------------------------------------------------------------------------
# Parsing (pure — no network)
# --------------------------------------------------------------------------------------------
def normalize_player_name(name: str) -> str:
    """casefold + strip punctuation and generational suffixes (Jr., Sr., II, III, IV, V).

    The source is internally inconsistent (writes both "Devonta Smith" and "DeVonta Smith" on
    the same page), so a normalized form is provided for downstream matching/deduplication.
    """
    text = _SUFFIX_RE.sub(" ", name)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _attr_str(el, name: str) -> Optional[str]:
    """Return a bs4 element attribute as a plain string (bs4 can hand back a list), or None."""
    if el is None:
        return None
    value = el.get(name)
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return value


def _extract_article_meta(soup: BeautifulSoup) -> dict:
    """Pull article-level fields from meta tags / ld+json / the canonical URL."""
    canonical_url = _attr_str(soup.select_one('link[rel="canonical"]'), "href")
    title = _attr_str(soup.select_one('meta[property="og:title"]'), "content")

    # article_uuid + id + rank range from the canonical URL / al:ios:url deep link.
    article_uuid = None
    ios_content = _attr_str(soup.select_one('meta[property="al:ios:url"]'), "content")
    if ios_content:
        uuid_match = re.search(r"articleUuid=([0-9a-f-]+)", ios_content)
        if uuid_match:
            article_uuid = uuid_match.group(1)

    article_id = start = end = season = None
    if canonical_url:
        url_match = _ARTICLE_URL_RE.search(canonical_url)
        if url_match:
            article_id = url_match.group("id")
            start = int(url_match.group("start"))
            end = int(url_match.group("end"))
            season = int(url_match.group("season"))

    # Fall back to the title for the rank range if the canonical URL was missing/odd.
    if start is None and title:
        range_match = re.search(r"ranked\s+(\d+)-(\d+)", title)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))

    author = published_utc = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text() or "")
        except (ValueError, TypeError):
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "NewsArticle":
                published_utc = published_utc or item.get("datePublished")
                author_field = item.get("author")
                if isinstance(author_field, dict):
                    author = author or author_field.get("name")

    return {
        "article_id": article_id,
        "article_uuid": article_uuid,
        "canonical_url": canonical_url,
        "title": title,
        "author": author,
        "published_utc": published_utc,
        "rank_range_start": start,
        "rank_range_end": end,
        "season": season,
        "scoring_format": "half_ppr",
    }


def _header_strongs(soup: BeautifulSoup) -> list:
    """Return the entry-header <strong> elements in document order.

    Non-player strongs ("Join or create a Yahoo Fantasy league", "My warning", ...) are
    excluded because they don't match the "Name, POS#, Team" header shape.
    """
    return [s for s in soup.find_all("strong") if _HEADER_RE.match(s.get_text(" ", strip=True))]


def _entry_analysis(header, next_header) -> tuple[str, list[str]]:
    """Collect analysis paragraphs and image captions between two entry headers.

    Walks document order from ``header`` to (but not including) ``next_header``. ``<figcaption>``
    text becomes image_captions; "Advertisement" nodes and any "(Hayden Winks)" attribution
    lines are dropped from the prose.
    """
    paragraphs: list[str] = []
    captions: list[str] = []
    for el in header.find_all_next(["p", "figcaption", "strong"]):
        if next_header is not None and el is next_header:
            break
        if el.name == "strong":
            continue  # a nested/bold run inside prose — not a boundary
        text = el.get_text(" ", strip=True)
        if not text or text == "Advertisement":
            continue
        if el.name == "figcaption" or text.endswith("(Hayden Winks)"):
            captions.append(text)
            continue
        paragraphs.append(text)
    return "\n\n".join(paragraphs), captions


def parse_article(html: str) -> tuple[dict, list[dict]]:
    """Parse one Yahoo HW article's raw HTML into (article_meta, [player_records]).

    Pure and network-free — the testable core. ``overall_rank`` is computed from the rank range
    plus document-order index (never from list markup), and the entry count is asserted to equal
    the range span so a truncated/expanded article fails loudly instead of shipping wrong ranks.

    Raises:
        ValueError: if the rank range can't be determined, or the entry count doesn't match it.
    """
    soup = BeautifulSoup(html, "html.parser")
    meta = _extract_article_meta(soup)

    start, end = meta["rank_range_start"], meta["rank_range_end"]
    if start is None or end is None:
        raise ValueError("Could not determine the article's rank range (canonical URL and title both unparseable)")

    headers = _header_strongs(soup)
    expected = end - start + 1
    if len(headers) != expected:
        raise ValueError(
            f"Article for ranks {start}-{end} has {len(headers)} player entries, expected {expected}. "
            "Yahoo's layout likely changed — check the entry-header <strong> shape in parse_article()."
        )

    records: list[dict] = []
    for index, header in enumerate(headers):
        next_header = headers[index + 1] if index + 1 < len(headers) else None
        match = _HEADER_RE.match(header.get_text(" ", strip=True))
        if match is None:  # guaranteed by _header_strongs' filter; guard keeps the types honest
            continue
        name = _NAME_RANK_PREFIX_RE.sub("", match.group("name")).strip()
        pos = match.group("pos")
        pos_rank = int(match.group("pos_rank"))
        team = match.group("team").strip()

        # Player/team links, when present (Yahoo links only a player's first mention on the page,
        # so name-dropped players appear as bare text in their own entry — hence nullable).
        yahoo_player_id = team_slug = None
        for anchor in header.find_all("a", href=True):
            href = _attr_str(anchor, "href") or ""
            pid = _PLAYER_ID_RE.search(href)
            if pid:
                yahoo_player_id = pid.group(1)
            tslug = _TEAM_SLUG_RE.search(href)
            if tslug:
                team_slug = tslug.group(1)

        analysis_text, captions = _entry_analysis(header, next_header)

        records.append(
            {
                "overall_rank": start + index,
                "player_name": name,
                "player_name_normalized": normalize_player_name(name),
                "position": pos,
                "position_rank": pos_rank,
                "team": team,
                "yahoo_player_id": yahoo_player_id,
                "team_slug": team_slug,
                "analysis_text": analysis_text,
                "image_captions": captions,
            }
        )

    return meta, records


# --------------------------------------------------------------------------------------------
# Full-board (top-N) table parsing — pure, no network
# --------------------------------------------------------------------------------------------
def parse_top300_table(table_html: str) -> list[dict]:
    """Parse Winks' rendered full-board ``<table>`` into player records.

    Each data row is ``[overall_rank, player_cell]`` where the player cell holds a linked name and
    a "``TEAM - POS``" line (e.g. "Jahmyr Gibbs" / "DET - RB"). Kickers and defenses (K/DST) are
    dropped — the pipeline only carries QB/RB/WR/TE. ``position_rank`` is computed within each
    position from overall-rank order (Winks doesn't print it in this table); ``overall_rank`` is
    kept as his true board rank (so removing K/DST leaves gaps, which is correct — hw_RK is the
    overall placement).

    Raises:
        ValueError: if no usable rows parse (layout drift).
    """
    soup = BeautifulSoup(table_html, "html.parser")
    records: list[dict] = []
    for row in soup.find_all("tr"):
        if not isinstance(row, Tag):
            continue
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        rank_text = cells[0].get_text(" ", strip=True)
        player_cell = cells[1]
        if not rank_text.isdigit() or not isinstance(player_cell, Tag):
            continue  # header row / spacer
        anchor = player_cell.find("a", href=True)
        # Name: the link text, or the first line of the cell if unlinked.
        name = anchor.get_text(" ", strip=True) if anchor else player_cell.get_text("\n", strip=True).split("\n")[0]
        tp = _TEAM_POS_RE.search(player_cell.get_text("\n", strip=True))
        if not name or not tp:
            continue
        team, pos = tp.group(1), tp.group(2).upper()
        if pos not in SUPPORTED_POSITIONS:
            continue  # drop K / DST
        yahoo_player_id = None
        if anchor:
            pid = _PLAYER_ID_RE.search(_attr_str(anchor, "href") or "")
            yahoo_player_id = pid.group(1) if pid else None
        records.append(
            {
                "overall_rank": int(rank_text),
                "player_name": name,
                "player_name_normalized": normalize_player_name(name),
                "position": pos,
                "position_rank": None,  # filled below
                "team": team,
                "yahoo_player_id": yahoo_player_id,
                "team_slug": None,
                "analysis_text": "",
                "image_captions": [],
            }
        )

    if not records:
        raise ValueError(
            "Parsed 0 rows from the Yahoo HW top-N table — layout likely changed "
            "(check the <table> row shape in parse_top300_table())."
        )

    records.sort(key=lambda r: r["overall_rank"])
    pos_counter: dict[str, int] = {}
    for rec in records:
        pos_counter[rec["position"]] = pos_counter.get(rec["position"], 0) + 1
        rec["position_rank"] = pos_counter[rec["position"]]
    return records


# --------------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------------
def discover_top300_url(html: str, season: int) -> Optional[str]:
    """Return the absolute full-board (top-N) article URL for ``season`` from the author page."""
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = _attr_str(anchor, "href") or ""
        match = _TOP300_URL_RE.search(href)
        if match and int(match.group("season")) == season:
            return href if href.startswith("http") else "https://sports.yahoo.com" + strip_tracking_params(href)
    return None


def discover_article_urls(html: str, season: int) -> list[str]:
    """Return absolute article URLs for ``season`` found on the author page, ordered by rank start.

    Matches the rank-range slug against every href (unpublished future parts appear only as
    unlinked plain text and are intentionally ignored). De-duplicated by article id.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, tuple[int, str]] = {}
    for anchor in soup.find_all("a", href=True):
        href = _attr_str(anchor, "href") or ""
        match = _ARTICLE_URL_RE.search(href)
        if not match or int(match.group("season")) != season:
            continue
        if href.startswith("/"):
            href = "https://sports.yahoo.com" + href
        found[match.group("id")] = (int(match.group("start")), strip_tracking_params(href))
    return [url for _start, url in sorted(found.values())]


def discover_article_urls_live(
    season: int = CURRENT_SEASON,
    session: Optional[requests.Session] = None,
    cache_dir: Optional[str] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Crawl the author page for ``season``'s articles; fall back to the known list if empty."""
    session = session or new_session()
    try:
        html = fetch_html(YAHOO_AUTHOR_URL, session=session, cache_dir=None, sleep=sleep)
        urls = discover_article_urls(html, season)
        if urls:
            return urls
    except (requests.RequestException, ConsentGateError, RuntimeError):
        pass
    return list(YAHOO_HW_KNOWN_ARTICLES.get(season, []))


# --------------------------------------------------------------------------------------------
# Adapter: parsed records -> pipeline CSV
# --------------------------------------------------------------------------------------------
def records_to_rows(records: list[dict]) -> list[dict]:
    """Map parsed player records to the 11-column HW_OUTPUT_COLUMNS schema (5 real, 6 blank)."""
    rows = []
    for rec in records:
        row = {col: "" for col in HW_OUTPUT_COLUMNS}
        row["PLAYER NAME"] = rec["player_name"]
        row["TEAM"] = rec["team"]
        row["POS"] = rec["position"]
        row["POS RANK"] = rec["position_rank"]
        row["RK"] = rec["overall_rank"]
        rows.append(row)
    return rows


def load_player_key_index(player_key_path: str) -> dict[str, str]:
    """Build a {normalized_name -> canonical dict name} index for punctuation-safe reconciliation.

    Yahoo writes proper punctuation ("Amon-Ra St. Brown", "A.J. Brown", "De'Von Achane") while
    ``player_key_dict.json`` carries the old Underdog-era stripped spellings ("AmonRa St Brown",
    "AJ Brown", "DeVon Achane"). Since the redraft board matches HW by *exact* name
    (``add_player_ids``), that drift would silently cost those stars their hw_RK. Mapping by
    normalized form fixes it without editing the dict.

    Only *unambiguous* normalized forms are kept — a normalized string owned by two player ids
    (real homonyms, e.g. two Alex Smiths) is dropped, exactly like ``build_suffix_fallback_index``,
    so reconciliation never guesses one player into another's identity.
    """
    from collections import defaultdict

    with open(player_key_path, "r", encoding="utf-8") as fh:
        player_key = json.load(fh)

    norm_to_ids: dict[str, set] = defaultdict(set)
    id_to_primary: dict[str, str] = {}
    for pid, names in player_key.items():
        if not names:
            continue
        id_to_primary[pid] = names[0]
        for name in names:
            norm_to_ids[normalize_player_name(name)].add(pid)
    return {norm: id_to_primary[next(iter(ids))] for norm, ids in norm_to_ids.items() if len(ids) == 1}


def reconcile_player_names(rows: list[dict], player_key_path: str, verbose: bool = True) -> int:
    """Rewrite each row's PLAYER NAME to the dict's canonical spelling when they normalize equal.

    In-place. Returns the number of names rewritten. A no-op for names already canonical, absent
    from the dict (rookies — left as-is for a later player-key update), or ambiguous.
    """
    try:
        index = load_player_key_index(player_key_path)
    except (OSError, ValueError):
        if verbose:
            print(f"   ⚠️  Player key not found at {player_key_path}; skipping name reconciliation")
        return 0

    changed = 0
    for row in rows:
        canonical = index.get(normalize_player_name(row["PLAYER NAME"]))
        if canonical and canonical != row["PLAYER NAME"]:
            row["PLAYER NAME"] = canonical
            changed += 1
    if verbose and changed:
        print(f"   ✓ Reconciled {changed} player name(s) to the player-key spelling")
    return changed


def _fetch_and_parse(
    url: str,
    session: Optional[requests.Session],
    cache_dir: Optional[str],
    sleep: Callable[[float], None],
    attempts: int = 3,
) -> tuple[dict, list[dict]]:
    """Fetch + parse one article, retrying on a parse failure with a forced re-fetch.

    Yahoo intermittently serves a partial/throttled page (a 200 whose body is missing the entry
    list), which trips parse_article's entry-count assertion. Because fetch_html caches the 200
    *before* the body is validated, a naive retry would just re-read the poisoned cache — so the
    retry passes ``force_refresh`` to re-fetch live and overwrite it. Failing loudly after N tries
    is still preferred over silently shipping a truncated board.
    """
    last_err: Optional[ValueError] = None
    for i in range(attempts):
        html = fetch_html(url, session=session, cache_dir=cache_dir, sleep=sleep, force_refresh=(i > 0))
        try:
            return parse_article(html)
        except ValueError as exc:  # count mismatch / unparseable range → likely a partial page
            last_err = exc
    assert last_err is not None
    raise last_err


def _output_filename(season: int) -> str:
    return f"hw-yahoo-{season}.csv"


def validate_records(records: list[dict], verbose: bool = True, require_contiguous: bool = True) -> None:
    """Hard-fail on an out-of-set position or bad rank ordering; warn on null Yahoo ids.

    ``require_contiguous`` (analysis-article path): overall ranks must be gapless — a gap means a
    missing/failed 12-player part. The full-board table path passes ``False`` (K/DST are dropped,
    which legitimately leaves gaps) and only requires strictly increasing, unique ranks.
    """
    ranks = [r["overall_rank"] for r in records]
    if require_contiguous:
        if ranks != list(range(ranks[0], ranks[0] + len(ranks))):
            raise ValueError(f"Overall ranks are not contiguous: {ranks}")
    elif any(b <= a for a, b in zip(ranks, ranks[1:])):
        raise ValueError("Overall ranks are not strictly increasing (duplicate or out-of-order rows)")
    for rec in records:
        if rec["position"] not in SUPPORTED_POSITIONS:
            raise ValueError(f"Unsupported position {rec['position']!r} for {rec['player_name']!r}")
    if verbose:
        missing = [r["player_name"] for r in records if not r["yahoo_player_id"]]
        if missing:
            preview = ", ".join(missing[:5]) + (", ..." if len(missing) > 5 else "")
            print(
                f"   ⚠️  {len(missing)}/{len(records)} entries had no Yahoo player id (name-dropped elsewhere): {preview}"
            )


def _write_hw_csv(
    records: list[dict], output_dir: str, season: int, player_key_path: Optional[str], verbose: bool
) -> str:
    """Reconcile names and write ``records`` to ``hw-yahoo-<season>.csv`` (the positional schema)."""
    import pandas as pd

    rows = records_to_rows(records)
    reconcile_player_names(rows, player_key_path or DEFAULT_PATHS["player_key_file"], verbose=verbose)
    # records_to_rows builds each dict in HW_OUTPUT_COLUMNS order, so the frame's columns already
    # match the pipeline's positional schema (asserted here — the CSV column order is a contract).
    df = pd.DataFrame(rows)
    assert list(df.columns) == HW_OUTPUT_COLUMNS

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, _output_filename(season))
    df.to_csv(output_path, index=False)
    if verbose:
        print(f"   ✓ Saved {len(df)} players to: {output_path}")
    return output_path


def _render_top300_html(
    url: str,
    sleep: Callable[[float], None] = time.sleep,
    timeout_ms: int = 45000,
    min_rows: int = 200,
    headless: bool = True,
) -> str:
    """Headless-render the full-board article and return the ranking ``<table>``'s outerHTML.

    The board is client-rendered (absent from the server HTML), so Playwright drives it: load,
    scroll until the row count stops growing (the table lazy-fills), then return the largest table.
    Playwright is the optional ``headless`` extra (shared with ds/pff/fpts).
    """
    from fantasy_pipeline.scraper.fetch_rankings import _require_playwright

    sync_playwright = _require_playwright()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless)
        except Exception as exc:
            raise RuntimeError("Could not launch Chromium. Install it with:\n  playwright install chromium") from exc
        try:
            page = browser.new_context(user_agent=YAHOO_USER_AGENT, viewport={"width": 1400, "height": 2200}).new_page()
            page.goto(strip_tracking_params(url), wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector("table tr", timeout=timeout_ms)
            # Scroll until the row count stabilizes (lazy-rendered rows), capped to avoid looping.
            prev = -1
            for _ in range(30):
                count = page.eval_on_selector_all("table tr", "els => els.length")
                if count == prev:
                    break
                prev = count
                page.mouse.wheel(0, 6000)
                sleep(0.4)
            # Pick the table with the most rows (the board, not an ad/related widget).
            table_html = page.eval_on_selector_all(
                "table",
                "tables => tables.map(t => [t.querySelectorAll('tr').length, t.outerHTML])"
                ".sort((a,b)=>b[0]-a[0]).map(x=>x[1])[0] || ''",
            )
        finally:
            browser.close()

    if not table_html:
        raise RuntimeError("No ranking table found on the Yahoo HW full-board page after render")
    row_count = table_html.count("<tr")
    if row_count < min_rows:
        raise RuntimeError(f"Full-board table rendered only {row_count} rows (< {min_rows}); render likely incomplete")
    return table_html


def fetch_yahoo_hw_top300(
    output_dir: str,
    season: int = CURRENT_SEASON,
    min_players: int = 150,
    session: Optional[requests.Session] = None,
    cache_dir: Optional[str] = None,
    sleep: Callable[[float], None] = time.sleep,
    player_key_path: Optional[str] = None,
    headless: bool = True,
    verbose: bool = True,
) -> str:
    """Fetch Winks' full top-N overall board (one rendered table, 250+ players) into the HW CSV.

    Discovers the full-board article from the author page (falls back to YAHOO_HW_TOP300_KNOWN),
    headless-renders its table, drops K/DST, and writes ``hw-yahoo-<season>.csv``. This is the deep
    source; ``fetch_yahoo_hw`` prefers it and falls back to the 12-at-a-time analysis articles.
    """
    session = session or new_session()

    url = None
    try:
        author_html = fetch_html(YAHOO_AUTHOR_URL, session=session, cache_dir=None, sleep=sleep)
        url = discover_top300_url(author_html, season)
    except (requests.RequestException, ConsentGateError, RuntimeError):
        pass
    url = url or YAHOO_HW_TOP300_KNOWN.get(season)
    if not url:
        raise RuntimeError(f"No Hayden Winks full-board article found for {season}")

    if verbose:
        print(f"\n🕷️  Yahoo HW full board: rendering {url.split('/')[-1]}")
    records = parse_top300_table(_render_top300_html(url, sleep=sleep, headless=headless))
    validate_records(records, verbose=verbose, require_contiguous=False)
    if len(records) < min_players:
        raise RuntimeError(f"Only {len(records)} players parsed from the full board (< min_players={min_players})")
    if verbose:
        print(f"   ✓ Parsed {len(records)} skill players (QB/RB/WR/TE; K/DST dropped)")
    return _write_hw_csv(records, output_dir, season, player_key_path, verbose)


def fetch_yahoo_hw_analysis(
    output_dir: str,
    season: int = CURRENT_SEASON,
    min_players: int = 12,
    session: Optional[requests.Session] = None,
    cache_dir: Optional[str] = None,
    sleep: Callable[[float], None] = time.sleep,
    player_key_path: Optional[str] = None,
    verbose: bool = True,
) -> str:
    """Assemble the HW board from the 12-at-a-time analysis articles (the shallow, prose source).

    Discovers every published rank-range part, parses each, and writes ``hw-yahoo-<season>.csv``.
    Coverage grows through the preseason (36 today); a partial board is fine — redraft is driven by
    ``fp``, so players HW hasn't ranked simply lack hw_RK. Used as the fallback when the full-board
    render is unavailable (e.g. Playwright not installed).
    """
    session = session or new_session()
    if cache_dir is None:
        cache_dir = os.path.join(DEFAULT_PATHS["data_dir"], ".yahoo_hw_cache")

    urls = discover_article_urls_live(season, session=session, cache_dir=cache_dir, sleep=sleep)
    if not urls:
        raise RuntimeError(
            f"No Hayden Winks articles found for {season} (author-page crawl empty and no known "
            f"fallback). Add the first part to YAHOO_HW_KNOWN_ARTICLES[{season}]."
        )
    if verbose:
        print(f"\n🕷️  Yahoo HW analysis articles: {len(urls)} part(s) for {season}")

    all_records: list[dict] = []
    for url in urls:
        meta, records = _fetch_and_parse(url, session=session, cache_dir=cache_dir, sleep=sleep)
        if verbose:
            print(f"   ✓ ranks {meta['rank_range_start']}-{meta['rank_range_end']}: {len(records)} players")
        all_records.extend(records)

    all_records.sort(key=lambda r: r["overall_rank"])
    validate_records(all_records, verbose=verbose)
    if len(all_records) < min_players:
        raise RuntimeError(
            f"Only {len(all_records)} players assembled (< min_players={min_players}). "
            "Either few parts are published yet or a fetch failed — check the article coverage."
        )
    return _write_hw_csv(all_records, output_dir, season, player_key_path, verbose)


def fetch_yahoo_hw(
    output_dir: str,
    season: int = CURRENT_SEASON,
    min_players: int = 12,
    session: Optional[requests.Session] = None,
    cache_dir: Optional[str] = None,
    sleep: Callable[[float], None] = time.sleep,
    player_key_path: Optional[str] = None,
    full_board: bool = True,
    headless: bool = True,
    verbose: bool = True,
) -> str:
    """Fetch Hayden Winks' redraft board into ``hw-yahoo-<season>.csv`` (the pipeline HW source).

    Prefers the **full top-N board** (one rendered table, 250+ players via
    ``fetch_yahoo_hw_top300``); if that's unavailable — Playwright not installed, the article not
    published, or a render failure — it **falls back** to assembling the 12-at-a-time analysis
    articles (``fetch_yahoo_hw_analysis``, 36 today). Set ``full_board=False`` to force the analysis
    path (no browser needed).

    Args:
        output_dir: Where to write the CSV (normally the pipeline's update/ folder).
        season: NFL season to fetch.
        min_players: Coverage floor for the *analysis* fallback (the full board has its own 150 floor).
        session/cache_dir/sleep: Injection seams (see fetch_html).
        player_key_path: player_key_dict.json for name reconciliation (defaults to the pipeline key).
        full_board: Prefer the deep table (True) or force the analysis articles (False).
        headless: Run the browser headless (full-board path only).
        verbose: Print progress.

    Returns:
        Path to the written CSV.
    """
    if full_board:
        try:
            return fetch_yahoo_hw_top300(
                output_dir,
                season=season,
                session=session,
                cache_dir=cache_dir,
                sleep=sleep,
                player_key_path=player_key_path,
                headless=headless,
                verbose=verbose,
            )
        except Exception as exc:
            if verbose:
                print(f"   ⚠️  Full board unavailable ({str(exc).splitlines()[0]}); falling back to analysis articles")

    return fetch_yahoo_hw_analysis(
        output_dir,
        season=season,
        min_players=min_players,
        session=session,
        cache_dir=cache_dir,
        sleep=sleep,
        player_key_path=player_key_path,
        verbose=verbose,
    )
