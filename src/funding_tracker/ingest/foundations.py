"""Generic index-page scraper for private foundations and national funders.

Each feed in config lists a page plus CSS selectors for the items and their titles
(ported from PBN Tender Radar). Foundation pages rarely expose structured deadlines,
so these records mainly feed the "new since last digest" section.
"""
from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..models import Opportunity
from .enrich import PageCache, clean_title, deadline_passed, enrich, is_generic_title
from ..util.logging import setup_logger

logger, _ = setup_logger()

_FUNDING_HREF = re.compile(
    r"call|grant|funding|foerder|förder|ausschreib|bewerb|stipend|fellowship|anslag|utlysning|ans[oø]g|"
    r"palyaz|pályáz|convocator|opportunit|programme|program|award|access|challenge|funke|wettbewerb|aufruf|"
    r"competition|prize|preis|tender|initiative",
    re.I,
)
# card teasers often glue status text onto the title: "Next Frontier Robotics Apply now We need…"
_TEASER_RX = re.compile(
    r"\s+(apply now|jetzt bewerben|1st stage|2nd stage|3rd stage|application period|we need|we are looking|open\b|"
    r"deadline|frist|ansøg nu|jelentkezz).*$",
    re.I,
)
_CLOSED_RX = re.compile(
    r"application period closed|closed for applications|challenge complete|funke complete|completed|"
    r"geschlossen|abgeschlossen|beendet|lezárult|afsluttet|avslutad",
    re.I,
)
_NAV_WORDS = re.compile(r"^(home|kontakt|contact|impressum|datenschutz|privacy|login|newsletter|english|deutsch|dansk|search)$", re.I)
_XML_START_RX = re.compile(rb"<(?:\?xml|rss|feed|rdf:RDF)\b")
_SLASHES_RX = re.compile(r"^(https?:)/{3,}", re.I)


def _norm_href(href: str) -> str:
    """'https:////www.host/x' (gesundheitsindustrie-bw.de) → 'https://www.host/x'; urljoin would turn the host into a path."""
    return _SLASHES_RX.sub(r"\1//", (href or "").strip())


def _xml_body(content: bytes) -> bytes:
    """Drop anything before the XML proper — Drupal theme-debug comments ahead of <?xml break the parser
    (clustercollaboration.eu)."""
    m = _XML_START_RX.search(content)
    return content[m.start():] if m else content


_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


class FoundationsIngester:
    def __init__(self, cfg: Dict[str, Any], http_cfg: Dict[str, Any]):
        self.cfg = cfg
        self.http_cfg = http_cfg

    def _make(self, feed: Dict[str, Any], title: str, url: str, snippet: str) -> Opportunity:
        opp = Opportunity(
            id=f"found:{hashlib.sha1(url.encode()).hexdigest()[:10]}",
            title=clean_title(title)[:200], url=url, source="foundation", programme=feed["name"], status="Open",
            funding_rate=feed.get("funding_rate", "100% (typ.)"),
            funding_rate_note="foundations and national programmes usually fund full project costs — check the call",
            country=feed.get("country", ""), tags=[feed["country"]] if feed.get("country") else [],
            summary=snippet[:300], text=snippet,
        )
        opp.compute_hash()
        return opp

    @staticmethod
    def _get(client: httpx.Client, feed: Dict[str, Any], url: str, **kw: Any) -> httpx.Response:
        """GET with optional per-feed `timeout_s` / `retries` (slow or flaky government CMSs, e.g. BMFTR)."""
        tries = 1 + int(feed.get("retries", 0))
        for n in range(tries):
            try:
                r = client.get(url, timeout=float(feed["timeout_s"]), **kw) if feed.get("timeout_s") else client.get(url, **kw)
                r.raise_for_status()
                return r
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if n + 1 >= tries or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500):
                    raise
        raise RuntimeError("unreachable")

    def _fetch_wp_json(self, client: httpx.Client, feed: Dict[str, Any]) -> List[Opportunity]:
        """WordPress REST API: {site}/wp-json/wp/v2/{post_type} — structured list, no scraping."""
        base = feed["url"].rstrip("/")
        post_type = feed.get("post_type", "posts")
        params: Dict[str, Any] = {"per_page": int(feed.get("per_page", 100)), "_fields": "id,link,title,excerpt,modified"}
        if feed.get("max_age_days"):    # archives that never mark old posts closed (ESA AOs): recent posts only
            since = datetime.now(timezone.utc) - timedelta(days=int(feed["max_age_days"]))
            params["after"] = since.strftime("%Y-%m-%dT%H:%M:%S")
        r = self._get(client, feed, f"{base}/wp-json/wp/v2/{post_type}", params=params)
        out: List[Opportunity] = []
        for it in r.json():
            title = BeautifulSoup(it.get("title", {}).get("rendered", ""), "html.parser").get_text(" ", strip=True)
            url = it.get("link", "")
            if not title or not url:
                continue
            excerpt = BeautifulSoup((it.get("excerpt") or {}).get("rendered", ""), "html.parser").get_text(" ", strip=True)
            out.append(self._make(feed, title, url, excerpt))
        return out

    def _fetch_rss(self, client: httpx.Client, feed: Dict[str, Any]) -> List[Opportunity]:
        """RSS 2.0 or Atom: <item>/<entry> with title, link and description/summary."""
        r = self._get(client, feed, feed["url"])
        root = ET.fromstring(_xml_body(r.content))

        def local(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        def child(node: ET.Element, *names: str) -> Optional[ET.Element]:
            return next((c for c in node if local(c.tag) in names), None)

        out: List[Opportunity] = []
        for node in root.iter():
            if local(node.tag) not in ("item", "entry"):
                continue
            t, ln = child(node, "title"), child(node, "link")
            title = " ".join("".join(t.itertext()).split()) if t is not None else ""
            url = ((ln.get("href") or (ln.text or "")).strip()) if ln is not None else ""
            desc = child(node, "description", "summary", "content")
            snippet = BeautifulSoup("".join(desc.itertext()), "html.parser").get_text(" ", strip=True) if desc is not None else ""
            if title and url:
                out.append(self._make(feed, title, urljoin(feed["url"], _norm_href(url)), " ".join(snippet.split())[:600]))
        return out

    def _fetch_feed(self, client: httpx.Client, feed: Dict[str, Any]) -> List[Opportunity]:
        items = self._fetch_feed_raw(client, feed)
        if feed.get("title_pattern"):                  # keep only call-like titles (news / RSS feeds)
            rx = re.compile(feed["title_pattern"], re.I)
            items = [o for o in items if rx.search(o.title)]
        return items[: int(self.cfg.get("max_items_per_feed", 50))]

    def _fetch_feed_raw(self, client: httpx.Client, feed: Dict[str, Any]) -> List[Opportunity]:
        if feed.get("type") == "wp-json":
            return self._fetch_wp_json(client, feed)
        if feed.get("type") == "rss":
            return self._fetch_rss(client, feed)
        r = self._get(client, feed, feed["url"])
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header"]):
            t.decompose()
        limit = int(self.cfg.get("max_items_per_feed", 50))
        out: Dict[str, Opportunity] = {}

        # (title, url, snippet) candidates: configured selectors first, generic link heuristic as fallback
        candidates = []
        for node in soup.select(feed.get("item_selector", "article")):
            title_node = node.select_one(feed.get("title_selector", "h2, h3")) or node
            title = " ".join(title_node.get_text(" ", strip=True).split())
            link = node if node.name == "a" and node.get("href") else node.find("a", href=True)   # card may be one <a>
            if link:
                candidates.append((title, _norm_href(link[feed.get("link_attr", "href")]), node.get_text(" ", strip=True)))
        link_rx = re.compile(feed["link_pattern"], re.I) if feed.get("link_pattern") else _FUNDING_HREF
        n_selected = len(candidates) if feed.get("item_selector") else 0   # cards the config explicitly targets
        if len(candidates) < 3 or feed.get("link_pattern"):
            base_host = urlparse(str(r.url)).netloc
            for a in soup.find_all("a", href=True):
                href = urljoin(str(r.url), _norm_href(a["href"]))
                title = " ".join(a.get_text(" ", strip=True).split())
                if urlparse(href).scheme not in ("http", "https") or urlparse(href).netloc != base_host \
                        or "#" in a["href"] or _NAV_WORDS.match(title):
                    continue
                if link_rx.search(href) or (link_rx is _FUNDING_HREF and link_rx.search(title)):
                    parent = a.find_parent(["li", "article", "div"]) or a
                    candidates.append((title, href, parent.get_text(" ", strip=True)))

        for i, (title, href, snippet_raw) in enumerate(candidates):
            title = re.split(r"\s[©®]\s|\s©", title)[0].strip()   # drop trailing image credits
            snippet = " ".join(snippet_raw.split())[:600]
            if _CLOSED_RX.search(title) or deadline_passed(snippet):   # archive cards of past calls
                continue
            title = _TEASER_RX.sub("", title).strip() or title
            # generic link text ("View challenge") is kept only where the config vouches for the URL (link_pattern
            # or a configured item_selector) — enrich() then swaps in the detail page's <h1>; from the bare
            # link heuristic it is mostly navigation noise
            generic = is_generic_title(title)
            vouched = bool(feed.get("link_pattern")) or i < n_selected
            if not title or (generic and not vouched) or _CLOSED_RX.search(title):
                continue
            url = urljoin(str(r.url), href)
            if url in out:
                if is_generic_title(out[url].title) and not generic:   # card image/button came first
                    out[url].title = title[:200]
                    out[url].compute_hash()
                continue
            if url.rstrip("/") == str(r.url).rstrip("/"):
                continue
            opp = self._make(feed, title, url, snippet)
            out[url] = opp
            if len(out) >= limit:
                break
        return list(out.values())

    def client(self) -> httpx.Client:
        # several foundations (Wellcome, KAW) reject non-browser agents
        return httpx.Client(timeout=float(self.http_cfg.get("timeout_s", 30)), follow_redirects=True,
                            headers={"User-Agent": _BROWSER_UA})

    def fetch(self) -> List[Opportunity]:
        delay = float(self.cfg.get("request_delay_s", 1.0))
        all_items: List[Opportunity] = []
        with self.client() as client:
            for feed in self.cfg.get("feeds", []):
                if not feed.get("enabled", True):
                    continue
                try:
                    items = self._fetch_feed(client, feed)
                    logger.info(f"  {feed['name']}: {len(items)} items")
                    all_items.extend(items)
                except Exception as exc:  # noqa: BLE001 — one dead site must not kill the run
                    logger.warning(f"  {feed['name']}: [yellow]{type(exc).__name__}: {str(exc)[:80]}[/yellow]")
                time.sleep(delay)

            if self.cfg.get("fetch_details", True):
                cache = PageCache(self.cfg.get("page_cache", "outputs/page_cache.json"),
                                  int(self.cfg.get("cache_days", 30)))
                per_feed = {f["name"]: int(f["detail_pages"]) for f in self.cfg.get("feeds", []) if f.get("detail_pages")}
                all_items = enrich(all_items, client, cache,
                                   per_feed=int(self.cfg.get("detail_pages_per_feed", 12)), per_feed_override=per_feed,
                                   delay_s=delay)
                cache.save()
                # tripwire feeds that keep awarded rounds online without saying "closed" (Interaktive Technologien):
                # only a page with a future deadline counts as an open call
                need_dl = {f["name"] for f in self.cfg.get("feeds", []) if f.get("require_deadline")}
                all_items = [o for o in all_items if o.deadline or o.programme not in need_dl]
        return all_items

    def safe_fetch(self) -> List[Opportunity]:
        try:
            return self.fetch()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[red]foundations fetch failed:[/red] {exc}")
            return []
