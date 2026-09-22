"""Generic index-page scraper for private foundations and national funders.

Each feed in config lists a page plus CSS selectors for the items and their titles
(ported from PBN Tender Radar). Foundation pages rarely expose structured deadlines,
so these records mainly feed the "new since last digest" section.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..models import Opportunity
from .enrich import PageCache, enrich
from ..util.logging import setup_logger

logger, _ = setup_logger()

_SKIP_TITLES = {"read more", "more", "mehr", "weiterlesen", "læs mere", "tovább", "details", "learn more", "mehr informationen"}
_FUNDING_HREF = re.compile(
    r"call|grant|funding|foerder|förder|ausschreib|bewerb|stipend|fellowship|anslag|utlysning|ans[oø]g|"
    r"palyaz|pályáz|convocator|opportunit|programme|program|award|access",
    re.I,
)
_NAV_WORDS = re.compile(r"^(home|kontakt|contact|impressum|datenschutz|privacy|login|newsletter|english|deutsch|dansk|search)$", re.I)
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
            title=title[:200], url=url, source="foundation", programme=feed["name"], status="Open",
            funding_rate=feed.get("funding_rate", "100% (typ.)"),
            funding_rate_note="foundations and national programmes usually fund full project costs — check the call",
            country=feed.get("country", ""), tags=[feed["country"]] if feed.get("country") else [],
            summary=snippet[:300], text=snippet,
        )
        opp.compute_hash()
        return opp

    def _fetch_wp_json(self, client: httpx.Client, feed: Dict[str, Any]) -> List[Opportunity]:
        """WordPress REST API: {site}/wp-json/wp/v2/{post_type} — structured list, no scraping."""
        base = feed["url"].rstrip("/")
        post_type = feed.get("post_type", "posts")
        per_page = int(feed.get("per_page", 100))
        r = client.get(f"{base}/wp-json/wp/v2/{post_type}",
                       params={"per_page": per_page, "_fields": "id,link,title,excerpt,modified"})
        r.raise_for_status()
        out: List[Opportunity] = []
        for it in r.json():
            title = BeautifulSoup(it.get("title", {}).get("rendered", ""), "html.parser").get_text(" ", strip=True)
            url = it.get("link", "")
            if not title or not url:
                continue
            excerpt = BeautifulSoup((it.get("excerpt") or {}).get("rendered", ""), "html.parser").get_text(" ", strip=True)
            out.append(self._make(feed, title, url, excerpt))
        return out

    def _fetch_feed(self, client: httpx.Client, feed: Dict[str, Any]) -> List[Opportunity]:
        if feed.get("type") == "wp-json":
            return self._fetch_wp_json(client, feed)
        r = client.get(feed["url"])
        r.raise_for_status()
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
            link = node.find("a", href=True)
            if link:
                candidates.append((title, link[feed.get("link_attr", "href")], node.get_text(" ", strip=True)))
        link_rx = re.compile(feed["link_pattern"], re.I) if feed.get("link_pattern") else _FUNDING_HREF
        if len(candidates) < 3 or feed.get("link_pattern"):
            base_host = urlparse(str(r.url)).netloc
            for a in soup.find_all("a", href=True):
                href = urljoin(str(r.url), a["href"])
                title = " ".join(a.get_text(" ", strip=True).split())
                if urlparse(href).scheme not in ("http", "https") or urlparse(href).netloc != base_host \
                        or "#" in a["href"] or _NAV_WORDS.match(title):
                    continue
                if link_rx.search(href) or (link_rx is _FUNDING_HREF and link_rx.search(title)):
                    parent = a.find_parent(["li", "article", "div"]) or a
                    candidates.append((title, href, parent.get_text(" ", strip=True)))

        for title, href, snippet_raw in candidates:
            title = re.split(r"\s[©®]\s|\s©", title)[0].strip()   # drop trailing image credits
            if not title or len(title) < 12 or title.lower() in _SKIP_TITLES:
                continue
            url = urljoin(str(r.url), href)
            if url in out or url.rstrip("/") == str(r.url).rstrip("/"):
                continue
            snippet = " ".join(snippet_raw.split())[:600]
            opp = self._make(feed, title, url, snippet)
            out[url] = opp
            if len(out) >= limit:
                break
        return list(out.values())

    def fetch(self) -> List[Opportunity]:
        timeout = float(self.http_cfg.get("timeout_s", 30))
        delay = float(self.cfg.get("request_delay_s", 1.0))
        ua = _BROWSER_UA  # several foundations (Wellcome, KAW) reject non-browser agents
        all_items: List[Opportunity] = []
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": ua}) as client:
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
        return all_items

    def safe_fetch(self) -> List[Opportunity]:
        try:
            return self.fetch()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[red]foundations fetch failed:[/red] {exc}")
            return []
