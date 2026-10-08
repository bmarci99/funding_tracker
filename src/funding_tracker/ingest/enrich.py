"""Detail-page enrichment for foundation / national-funder calls.

Index pages give us a title and a link. To score a call properly we need its text, deadline and
amount, so we fetch each candidate's page (politely, with a 30-day cache committed alongside
history.json), keep the main content, and extract:

  - text      main article text (nav/header/footer stripped), used for scoring
  - deadline  first date after a deadline keyword (EN/DE/DK/SE/HU), else earliest future date
  - amount    largest money figure on the page, converted to EUR (rough FX)
  - title     the page's <h1> / og:title — replaces generic link text ("View challenge", "Read more")

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
    r"apply|application|deadline|grant|funding|call for|announcement of opportunit|förder|foerder|frist|bewerb|antrag|ausschreib|"
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


def _all_dates(text: str) -> List[Tuple[int, date]]:
    found: List[Tuple[int, date]] = []               # (position, date)
    for i, pat in enumerate(DATE_PATTERNS):
        for m in pat.finditer(text):
            d = _parse_date_match(i, m.groups())
            if d:
                found.append((m.start(), d))
    return found


def deadline_passed(text: str, today: Optional[date] = None) -> bool:
    """True when a teaser card states a deadline that is over and mentions no future date at all
    ("Application deadline 03 Apr 2024 …" on an archive of past calls)."""
    today = today or date.today()
    found = _all_dates(text)
    if not found or any(d >= today for _, d in found):
        return False
    for kw in DEADLINE_KW.finditer(text):
        near = [d for pos, d in found if 0 <= pos - kw.start() <= 60]
        if near:
            return True
    return False


def extract_deadline(text: str, today: Optional[date] = None) -> Optional[date]:
    today = today or date.today()
    found = [(pos, d) for pos, d in _all_dates(text) if today <= d <= today + timedelta(days=730)]
    if not found:
        return None
    # prefer a date that follows a deadline keyword within 160 chars
    for kw in DEADLINE_KW.finditer(text):
        near = [d for pos, d in found if 0 <= pos - kw.start() <= 160]
        if near:
            return min(near)
    return min(d for _, d in found)


# A figure this large on a foundation / agency page is a programme or fund total ("€80M Innovationsfonds",
# "FORTIS €314m"), not what one grant pays — it goes to call_budget, never contribution_max.
PROGRAMME_TOTAL_EUR = 20e6
# "an indicative total budget of €3.1M" / "Gesamtbudget" / "keretösszeg" → the call's pot, not one grant
TOTAL_CTX_RX = re.compile(r"total|overall|indicative budget|call budget|budget of the call|gesamt|insgesamt|"
                          r"fördervolumen|keretösszeg|samlet|totalt|split|allocat|earmark|reserved for|aufgeteilt", re.I)


# a stated per-grant cap beats any heuristic: "up to €250,000 per project", "bis zu 100.000 EUR", "legfeljebb 50 millió Ft"
GRANT_CAP_RX = re.compile(r"up to|maximum|max\.?|at most|bis zu|höchstens|maximal|legfeljebb|op til|upp till", re.I)
PER_GRANT_RX = re.compile(r"\s*(?:per|pro|/)\s*(?:project|projekt|grant|applicant|antrag|vorhaben|team)|\s*projektenként", re.I)


def extract_amount_eur(text: str, max_eur: float = 5e9, skip_totals: bool = False) -> Optional[float]:
    """Largest money figure in EUR within [5k, max_eur]; skip_totals ignores figures introduced as a call total."""
    best, cap, prev_end = 0.0, 0.0, 0
    for m in MONEY_RX.finditer(text):
        lead, prev_end = text[max(prev_end, m.start() - 50):m.start()], m.end()   # only this figure's own lead-in
        if skip_totals and TOTAL_CTX_RX.search(lead):
            continue
        cur, num, mult = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(4), m.group(5))
        mult = (mult or "").lower().rstrip(".")
        try:
            digits = re.sub(r"\s", "", num)
            if mult and re.fullmatch(r"\d+[.,]\d{1,2}", digits):
                n = float(digits.replace(",", "."))           # "3.14 million", "2,5 Mio." — decimal, not thousands
            elif "," in digits and "." in digits:             # "3,142,746.92" / "3.142.746,92": the last one is the decimal
                cut = max(digits.rfind(","), digits.rfind("."))
                n = float(re.sub(r"[.,]", "", digits[:cut]) + "." + digits[cut + 1:])
            elif num.count(",") == 1 and len(num.split(",")[1]) <= 2:
                n = float(re.sub(r"[\s.]", "", num).replace(",", "."))
            else:
                n = float(re.sub(r"[\s.,]", "", num))
        except ValueError:
            continue
        if mult in ("mio", "million", "millions", "millió", "mill", "m"):
            n *= 1e6
        elif mult in ("mrd", "billion", "milliárd"):
            n *= 1e9
        elif mult == "k":
            n *= 1e3
        n *= FX_TO_EUR.get(cur.lower(), 1.0)
        if 5_000 <= n <= max_eur:
            best = max(best, n)
            if skip_totals and (GRANT_CAP_RX.search(lead[-25:]) or PER_GRANT_RX.match(text, m.end())):
                cap = max(cap, n)
    return (cap or best) or None


_CREDIT_RX = re.compile(r"©\s?[^.]{0,60}?(?:stock\.adobe\.com|shutterstock|getty images|unsplash|istock)\S*", re.I)


# Link texts that say nothing about the call ("View challenge" on every SPRIND card). Such items get
# the detail page's <h1> as title instead — one central fix for every feed type.
GENERIC_TITLE_RX = re.compile(
    r"^(?:(?:read|learn|find out|see|view|show|discover|explore)(?: more)?(?: about)?(?: (?:the|this|all|our))?"
    r"(?: (?:more|details?|challenges?|calls?|programmes?|programs?|projects?|opportunit(?:y|ies)|funding|offer|here))?|"
    r"more|more info(?:rmation)?|details?|click here|apply|apply now|to the (?:call|challenge|programme)|"
    r"mehr|mehr erfahren|mehr lesen|mehr informationen|weitere informationen|weiterlesen|weiter|details ansehen|"
    r"kurzbeschreibung(?: programm)?|auss?chreibung (?:&|und) bewerbung|"
    r"zu[mr] (?:(?:laufenden|aktuellen|offenen) )?(?:förderangebot|aufruf|programm|wettbewerb|projekt|ausschreibung|challenge|förderung|bewerbung|"
    r"antrag|call)\b.{0,40}|"
    r"læs mere|se mere|læs videre|läs mer|lue lisää|lisätietoja|"
    r"tovább|bővebben|részletek|olvass tovább|további részletek)$",
    re.I,
)
# Labels and deadlines glued in front of the real title: SPRIND h1 "Your Challenge: Next Frontier…",
# DLR "Frist: 22. November 2026 Ideenaufruf …", DLR-PT "30.11.2026 BMFTR Richtlinie …".
_LABEL_PREFIX_RX = re.compile(
    r"^(?:your (?:challenge|call)|(?:antrags|einreichungs|bewerbungs)?frist|deadline|bewerbungsschluss)\s*:\s*", re.I)
_LEADING_DATE_RX = re.compile(
    rf"^(?:{DATE_PATTERNS[0].pattern}|{DATE_PATTERNS[1].pattern}|{DATE_PATTERNS[3].pattern})\s*[:|–—-]?\s+", re.I)
_SITE_SUFFIX_RX = re.compile(r" (?:\||–|—|·|::|-) [^|–—·]{2,60}$")   # "Call X | SPRIND" → "Call X" (text is pre-collapsed)


def clean_title(title: str) -> str:
    """Strip leading label / deadline prefixes; keeps the original if nothing would be left."""
    t = " ".join((title or "").split())
    out = _LEADING_DATE_RX.sub("", _LABEL_PREFIX_RX.sub("", t))
    return out or t


def is_generic_title(title: str, min_len: int = 12) -> bool:
    """Link text that names nothing. Short index link texts are mostly buttons ("Apply", "Details"); a page's own
    <h1> may legitimately be short ("CZS Plus"), so _page_title passes a lower min_len."""
    t = " ".join((title or "").split()).strip(" .:›»→>…")
    return len(t) < min_len or bool(GENERIC_TITLE_RX.match(t))


def _page_title(soup: BeautifulSoup) -> str:
    """<h1> (inside main/article if possible), else og:title / <title> without the ' | Site' suffix."""
    scope = soup.find("main") or soup.find("article") or soup
    for h1 in [*scope.find_all("h1"), *soup.find_all("h1")]:
        t = clean_title(h1.get_text(" ", strip=True))
        if t and not is_generic_title(t, min_len=6):
            return t
    og = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
    for raw in ((og.get("content") if og else ""), (soup.title.get_text() if soup.title else "")):
        t = " ".join((raw or "").split())
        head = _SITE_SUFFIX_RX.sub("", t)
        t = head if len(head) >= 8 else t
        if t and not is_generic_title(t, min_len=6):
            return t
    return ""


# "related content" blocks after the article tease *other* pages (SPRIND: a humanoid-robot podcast under every
# challenge, "More Challenges and Funken" listing the anti-drone call) and pollute the fit score — cut there.
_RELATED_RX = re.compile(
    r"\b(?:more about this topic|more challenges and funken|related (?:articles|news|content|posts)|you might also like|"
    r"weitere artikel|ähnliche artikel|das könnte sie auch interessieren)\b",
    re.I,
)


# Archived rounds say so on the detail page (G-BA, Interaktive Technologien keep every past Bekanntmachung online).
# Only trusted when the page names no future date — "1st round closed, 2nd round until 1 March 2027" stays.
PAGE_CLOSED_RX = re.compile(
    r"(?:einreichungs|antrags|bewerbungs|skizzen)?frist (?:ist |wurde )?(?:bereits )?abgelaufen|"
    r"frist abgelaufen|application period (?:is |has )?(?:now )?closed|this call (?:is|has) (?:now )?closed|"
    r"call (?:is |has )?(?:now )?closed for (?:applications|submissions)|\blezárult\b",
    re.I,
)


def page_closed(text: str, today: Optional[date] = None) -> bool:
    return bool(PAGE_CLOSED_RX.search(text)) and extract_deadline(text, today) is None


def cut_related(text: str, min_keep: int = 150) -> str:
    """Text up to the first related-content heading (only if real content precedes it). Also applied to
    cached entries, which were stored before this cut existed."""
    m = next((m for m in _RELATED_RX.finditer(text) if m.start() >= min_keep), None)
    return text[: m.start()].rstrip() if m else text


def parse_page(html: str) -> Tuple[str, str]:
    """(main text, page title) from one parse; the title is read before <header> is stripped."""
    soup = BeautifulSoup(html, "html.parser")
    title = _page_title(soup)
    for t in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        t.decompose()
    node = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup
    for fig in node.find_all(["figcaption", "figure"]):
        fig.decompose()
    return cut_related(" ".join(_CREDIT_RX.sub("", node.get_text(" ", strip=True)).split())), title


def main_text(html: str) -> str:
    return parse_page(html)[0]


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
        # failed fetches (timeouts, 5xx) are retried next run instead of hiding the call for 30 days
        ttl = self.ttl if e and e.get("ok", True) else timedelta(days=1)
        if e and datetime.fromisoformat(e["fetched"]) > datetime.now(timezone.utc) - ttl:
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
           per_feed_override: Optional[Dict[str, int]] = None, delay_s: float = 1.0, max_chars: int = 5000) -> List[Opportunity]:
    """Fetch detail pages for foundation items; drop pages without any funding signal."""
    kept: List[Opportunity] = []
    per_feed_count: Dict[str, int] = {}
    fetched = 0
    for o in opps:
        n = per_feed_count.get(o.programme, 0)
        if n >= (per_feed_override or {}).get(o.programme, per_feed):
            continue
        per_feed_count[o.programme] = n + 1
        generic = is_generic_title(o.title)
        entry = cache.get(o.url)
        if entry is not None and generic and entry.get("ok") and "title" not in entry:
            entry = None                           # cached before titles were stored: re-fetch once
        if entry is None:
            try:
                r = client.get(o.url)
                r.raise_for_status()
                text, page_title = parse_page(r.text)
                entry = {"text": text[:max_chars], "title": page_title[:200], "ok": True}
            except Exception as exc:  # noqa: BLE001
                entry = {"text": "", "ok": False, "error": f"{type(exc).__name__}"}
            cache.put(o.url, entry)
            fetched += 1
            time.sleep(delay_s)
        if generic and entry.get("title"):
            o.title = clean_title(entry["title"])
        text = cut_related(entry.get("text", ""))
        if not entry.get("ok") or not FUNDING_SIGNAL.search(f"{o.title} {text}") or page_closed(text):
            continue
        o.text = f"{o.title} {text}"
        o.summary = text[:300]
        o.deadline = extract_deadline(text)
        total = extract_amount_eur(text)
        grant = extract_amount_eur(text, max_eur=PROGRAMME_TOTAL_EUR - 1, skip_totals=True)
        if total and total != grant and (total >= PROGRAMME_TOTAL_EUR or total > (grant or 0)):
            o.call_budget = total
        o.contribution_max = grant or o.contribution_max
        o.compute_hash()
        kept.append(o)
    logger.info(f"  enriched {len(kept)} foundation calls ({fetched} pages fetched, {len(opps) - len(kept)} dropped as non-calls)")
    return kept
