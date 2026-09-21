"""Detail-page enrichment for foundation / national-funder calls.

Index pages give us a title and a link. To score a call properly we need its text, deadline and
amount, so we fetch each candidate's page (politely, with a 30-day cache committed alongside
history.json), keep the main content, and extract:

  - text      main article text (nav/header/footer stripped), used for scoring
  - deadline  first date after a deadline keyword (EN/DE/DK/SE/HU), else earliest future date
  - amount    largest money figure on the page, converted to EUR (rough FX)

Pages with no funding signal at all (no apply/deadline/grant vocabulary) are dropped — that is
how we get rid of navigation headings the index scraper picked up.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..models import Opportunity
from ..util.logging import setup_logger

logger, _ = setup_logger()

FUNDING_SIGNAL = re.compile(
    r"apply|application|deadline|grant|funding|call for|förder|foerder|frist|bewerb|antrag|ausschreib|"
    r"ansøg|ansog|bevilling|utlysning|ansök|pályáz|palyaz|támogat|tamogat|határidő|hatarido|felhívás|felhivas",
    re.I,
)
DEADLINE_KW = re.compile(
    r"deadline|closing date|closes|submission|apply by|due|frist|einreich|bewerbungsschluss|ansøgningsfrist|"
    r"sista ansökningsdag|határidő|hatarido|benyújt|benyujt",
    re.I,
)

_MONTHS = {
    # en
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # de
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "mai": 5, "juni": 6, "juli": 7, "oktober": 10, "dezember": 12,
    # da / sv
    "januari": 1, "februari": 2, "marts": 3, "maj": 5, "augusti": 8, "oktober_": 10,
    # hu
    "január": 1, "február": 2, "március": 3, "április": 4, "május": 5, "június": 6, "július": 7, "augusztus": 8,
    "szeptember": 9, "október": 10, "december_": 12,
}
_MONTH_RX = "|".join(sorted((re.escape(m.rstrip("_")) for m in _MONTHS), key=len, reverse=True))
DATE_PATTERNS = [
    re.compile(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b"),                                        # 2026-10-15
    re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d\d)\b"),                                  # 15.10.2026
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b"),                                          # 15/10/2026
    re.compile(rf"\b(\d{{1,2}})\.?\s+({_MONTH_RX})\.?,?\s+(20\d\d)\b", re.I),                 # 15 October 2026 / 15. Oktober 2026
    re.compile(rf"\b({_MONTH_RX})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I),     # October 15, 2026
    re.compile(rf"\b(20\d\d)\.\s?({_MONTH_RX})\s+(\d{{1,2}})\.?\b", re.I),                    # 2026. október 15.
]
FX_TO_EUR = {"€": 1.0, "eur": 1.0, "euro": 1.0, "euros": 1.0, "dkk": 0.134, "kr": 0.134, "kr.": 0.134, "sek": 0.087,
             "nok": 0.087, "huf": 0.0025, "ft": 0.0025, "chf": 1.05, "£": 1.17, "gbp": 1.17, "$": 0.92, "usd": 0.92}
MONEY_RX = re.compile(
    r"(?:(€|£|\$|EUR|DKK|SEK|NOK|HUF|CHF|GBP|USD|kr\.?|Ft)\s?(\d[\d.,\s]{0,14}\d|\d)\s?(mio\.?|million|millions|millió|mill\.?|mrd\.?|billion|milliárd|k|m|M)?"
    r"|(\d[\d.,\s]{0,14}\d|\d)\s?(mio\.?|million|millions|millió|mill\.?|mrd\.?|billion|milliárd|k|m|M)?\s?(€|£|\$|EUR|DKK|SEK|NOK|HUF|CHF|GBP|USD|euro|euros|kr\.?|Ft))",
    re.I,
)


def _month(s: str) -> Optional[int]:
    return _MONTHS.get(s.lower()) or _MONTHS.get(s.lower() + "_")


def _parse_date_match(pat_idx: int, g: Tuple[str, ...]) -> Optional[date]:
    try:
        if pat_idx == 0:
            return date(int(g[0]), int(g[1]), int(g[2]))
        if pat_idx in (1, 2):
            return date(int(g[2]), int(g[1]), int(g[0]))
        if pat_idx == 3:
            m = _month(g[1]); return date(int(g[2]), m, int(g[0])) if m else None
        if pat_idx == 4:
            m = _month(g[0]); return date(int(g[2]), m, int(g[1])) if m else None
        if pat_idx == 5:
            m = _month(g[1]); return date(int(g[0]), m, int(g[2])) if m else None
    except ValueError:
        return None
    return None


def extract_deadline(text: str, today: Optional[date] = None) -> Optional[date]:
    today = today or date.today()
    found: List[Tuple[int, date]] = []               # (position, date)
    for i, pat in enumerate(DATE_PATTERNS):
        for m in pat.finditer(text):
            d = _parse_date_match(i, m.groups())
            if d and today <= d <= today + timedelta(days=730):
                found.append((m.start(), d))
    if not found:
        return None
    # prefer a date that follows a deadline keyword within 160 chars
    for kw in DEADLINE_KW.finditer(text):
        near = [d for pos, d in found if 0 <= pos - kw.start() <= 160]
        if near:
            return min(near)
    return min(d for _, d in found)


def extract_amount_eur(text: str) -> Optional[float]:
    best = 0.0
    for m in MONEY_RX.finditer(text):
        cur, num, mult = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(4), m.group(5))
        try:
            n = float(re.sub(r"[\s.]", "", num).replace(",", ".")) if num.count(",") == 1 and len(num.split(",")[1]) <= 2 \
                else float(re.sub(r"[\s.,]", "", num))
        except ValueError:
            continue
        mult = (mult or "").lower().rstrip(".")
        if mult in ("mio", "million", "millions", "millió", "mill", "m"):
            n *= 1e6
        elif mult in ("mrd", "billion", "milliárd"):
            n *= 1e9
        elif mult == "k":
            n *= 1e3
        n *= FX_TO_EUR.get(cur.lower(), 1.0)
        if 5_000 <= n <= 5e9:
            best = max(best, n)
    return best or None


_CREDIT_RX = re.compile(r"©\s?[^.]{0,60}?(?:stock\.adobe\.com|shutterstock|getty images|unsplash|istock)\S*", re.I)


def main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        t.decompose()
    node = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup
    for fig in node.find_all(["figcaption", "figure"]):
        fig.decompose()
    return _CREDIT_RX.sub("", " ".join(node.get_text(" ", strip=True).split()))


class PageCache:
    def __init__(self, path: str, ttl_days: int = 30):
        self.path = Path(path)
        self.ttl = timedelta(days=ttl_days)
        try:
            self.data: Dict[str, Dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        except json.JSONDecodeError:
            self.data = {}

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        e = self.data.get(url)
        if e and datetime.fromisoformat(e["fetched"]) > datetime.now(timezone.utc) - self.ttl:
            return e
        return None

    def put(self, url: str, entry: Dict[str, Any]) -> None:
        entry["fetched"] = datetime.now(timezone.utc).isoformat()
        self.data[url] = entry

    def save(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.ttl
        self.data = {u: e for u, e in self.data.items() if datetime.fromisoformat(e["fetched"]) > cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def enrich(opps: List[Opportunity], client: httpx.Client, cache: PageCache, *, per_feed: int = 12,
           delay_s: float = 1.0, max_chars: int = 5000) -> List[Opportunity]:
    """Fetch detail pages for foundation items; drop pages without any funding signal."""
    kept: List[Opportunity] = []
    per_feed_count: Dict[str, int] = {}
    fetched = 0
    for o in opps:
        n = per_feed_count.get(o.programme, 0)
        if n >= per_feed:
            continue
        per_feed_count[o.programme] = n + 1
        entry = cache.get(o.url)
        if entry is None:
            try:
                r = client.get(o.url)
                r.raise_for_status()
                text = main_text(r.text)[:max_chars]
                entry = {"text": text, "ok": True}
            except Exception as exc:  # noqa: BLE001
                entry = {"text": "", "ok": False, "error": f"{type(exc).__name__}"}
            cache.put(o.url, entry)
            fetched += 1
            time.sleep(delay_s)
        text = entry.get("text", "")
        if not entry.get("ok") or not FUNDING_SIGNAL.search(f"{o.title} {text}"):
            continue
        o.text = f"{o.title} {text}"
        o.summary = text[:300]
        o.deadline = extract_deadline(text)
        amt = extract_amount_eur(text)
        if amt:
            o.contribution_max = amt
        o.compute_hash()
        kept.append(o)
    logger.info(f"  enriched {len(kept)} foundation calls ({fetched} pages fetched, {len(opps) - len(kept)} dropped as non-calls)")
    return kept
