"""Ingester for the EU Funding & Tenders Portal search API (SEDIA)."""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import html as html_lib
import re

import httpx

from ..funding_rate import infer_funding_rate
from ..models import Opportunity
from ..util.logging import setup_logger

logger, _ = setup_logger()

STATUS_LABELS = {
    "31094501": "Forthcoming",
    "31094502": "Open",
    "31094503": "Closed",
}

# Portal frameworkProgramme IDs → abbreviation (from the portal's grantsTenders.json reference data)
PROGRAMME_IDS = {
    "43108390": "HORIZON",
    "43298916": "EURATOM",
    "43152860": "DIGITAL",
    "44181033": "EDF",
    "43252405": "LIFE",
    "43251567": "CEF",
    "43353764": "ERASMUS",
    "43251589": "CERV",
    "43254019": "ESF",
    "43251814": "CREA",
    "44416173": "I3",
    "43252368": "ISF",
    "44773066": "JTM",
    "45532249": "EUBA",
    "43252386": "JUST",
    "43637601": "PPPA",
    "43252476": "SMP",
    "43252517": "SOCPL",
    "43254037": "ESC",
    "43392145": "EMFAF",
    "43089234": "INNOVFUND",
    "45876777": "NDICI",
    "43253967": "RENEWFM",
}
PROGRAMME_LABELS = {
    "HORIZON": "Horizon Europe",
    "EURATOM": "Euratom",
    "DIGITAL": "Digital Europe",
    "EDF": "European Defence Fund",
    "LIFE": "LIFE — Environment & Climate",
    "CEF": "Connecting Europe Facility",
    "ERASMUS": "Erasmus+",
    "CERV": "Citizens, Equality, Rights & Values",
    "ESF": "European Social Fund+",
    "CREA": "Creative Europe",
    "I3": "Interregional Innovation Investments",
    "ISF": "Internal Security Fund",
    "JTM": "Just Transition Mechanism",
    "EUBA": "EU Bodies & Agencies",
    "JUST": "Justice Programme",
    "PPPA": "Pilot Projects & Preparatory Actions",
    "SMP": "Single Market Programme",
    "SOCPL": "Social Prerogative Lines",
    "ESC": "European Solidarity Corps",
    "EMFAF": "Maritime, Fisheries & Aquaculture Fund",
    "INNOVFUND": "Innovation Fund",
    "NDICI": "Global Europe (NDICI)",
    "RENEWFM": "Renewable Energy Financing Mechanism",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return " ".join(_TAG_RE.sub(" ", html_lib.unescape(s or "")).split())


TOPIC_URL = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
    "screen/opportunities/topic-details/{id}"
)


def _first(meta: Dict[str, Any], key: str, default: str = "") -> str:
    v = meta.get(key)
    if isinstance(v, list):
        return v[0] if v else default
    return v if v is not None else default


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None


def _clean_action(s: str) -> str:
    """'HORIZON  Research and Innovation Actions' → 'Research and Innovation Actions'."""
    s = " ".join(s.split())
    for prefix in ("HORIZON ", "EURATOM "):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def _parse_budget(raw: str, topic_id: str) -> Dict[str, Any]:
    """Flatten metadata.budgetOverview for ONE topic.

    The blob lists every topic of the parent call; each entry's ``action`` string
    starts with the topic identifier, and ``budgetYearMap`` is the *call-level*
    budget shared by all of them. So we keep only this topic's rows.
    """
    out: Dict[str, Any] = {}
    if not raw:
        return out
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return out

    rows = [
        a
        for actions in data.get("budgetTopicActionMap", {}).values()
        for a in actions
        if a.get("action", "").startswith(f"{topic_id} ")
    ]
    if not rows:
        return out

    call_budget = 0.0
    for v in rows[0].get("budgetYearMap", {}).values():
        try:
            call_budget += float(str(v).replace(",", ""))
        except ValueError:
            pass
    mins = [float(a["minContribution"]) for a in rows if a.get("minContribution")]
    maxs = [float(a["maxContribution"]) for a in rows if a.get("maxContribution")]
    grants = sum(int(a.get("expectedGrants") or 0) for a in rows)
    deadlines = sorted({d for a in rows for d in (a.get("deadlineDates") or [])})

    if call_budget:
        out["call_budget"] = call_budget
    if mins:
        out["contribution_min"] = min(mins)
    if maxs:
        out["contribution_max"] = max(maxs)
    if grants:
        out["expected_grants"] = grants
    if rows[0].get("deadlineModel"):
        out["deadline_model"] = rows[0]["deadlineModel"]
    if deadlines:
        out["deadline_dates"] = deadlines
    if rows[0].get("plannedOpeningDate"):
        out["opening_date"] = rows[0]["plannedOpeningDate"]
    return out


class FTPortalIngester:
    def __init__(self, cfg: Dict[str, Any], http_cfg: Dict[str, Any]):
        self.cfg = cfg
        self.http_cfg = http_cfg

    # ---- HTTP -------------------------------------------------------------

    def _query(self) -> Dict[str, Any]:
        return {
            "bool": {
                "must": [
                    {"terms": {"type": ["1", "2"]}},  # 1 = topic, 2 = call (tender types excluded)
                    {"terms": {"status": self.cfg["statuses"]}},
                    {"term": {"programmePeriod": self.cfg["programme_period"]}},
                    {"terms": {"frameworkProgramme": self.cfg["framework_programmes"]}},
                ]
            }
        }

    def _fetch_page(self, client: httpx.Client, page: int) -> Dict[str, Any]:
        params = {
            "apiKey": self.cfg["api_key"],
            "text": "***",
            "pageSize": self.cfg["page_size"],
            "pageNumber": page,
        }
        files = {
            "query": (None, json.dumps(self._query()), "application/json"),
            "languages": (None, '["en"]', "application/json"),
            # identifier is unique → deterministic paging (sortStatus alone shuffles ties between pages)
            "sort": (None, '{"field":"identifier","order":"ASC"}', "application/json"),
        }
        retries = int(self.http_cfg.get("max_retries", 3))
        backoff = float(self.http_cfg.get("backoff_factor", 1.5))
        for attempt in range(retries + 1):
            try:
                r = client.post(self.cfg["api_url"], params=params, files=files)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt >= retries:
                    raise
                wait = backoff * (2 ** attempt)
                logger.warning(f"page {page}: {exc} — retry in {wait:.0f}s")
                time.sleep(wait)
        return {}

    # ---- mapping ----------------------------------------------------------

    def _to_opportunity(self, hit: Dict[str, Any]) -> Optional[Opportunity]:
        meta = hit.get("metadata", {})
        ident = _first(meta, "identifier")
        if not ident:
            return None

        budget = _parse_budget(_first(meta, "budgetOverview"), ident)
        programme = PROGRAMME_IDS.get(_first(meta, "frameworkProgramme"), _first(meta, "frameworkProgramme"))
        action = _clean_action(_first(meta, "typesOfAction"))
        description = _strip_html(" ".join(meta.get("descriptionByte", []) or []))
        conditions = _strip_html(" ".join(meta.get("topicConditions", []) or []))
        rate, rate_note = infer_funding_rate(programme, action, conditions)
        deadline = _parse_date(_first(meta, "deadlineDate"))
        # For multi-deadline topics, prefer the next future date from budget info
        if budget.get("deadline_dates"):
            today = date.today().isoformat()
            future = [d for d in budget["deadline_dates"] if d >= today]
            if future:
                deadline = _parse_date(future[0])

        opp = Opportunity(
            id=ident,
            title=(_first(meta, "title") or hit.get("summary", ident)).strip(),
            url=TOPIC_URL.format(id=ident),  # hit["url"] is sometimes a raw .json data link
            programme=programme,
            call_id=_first(meta, "callIdentifier"),
            call_title=_first(meta, "callTitle"),
            status=STATUS_LABELS.get(_first(meta, "status"), _first(meta, "status")),
            action_type=action,
            deadline_model=_first(meta, "deadlineModel") or budget.get("deadline_model", ""),
            opening_date=_parse_date(_first(meta, "startDate") or budget.get("opening_date", "")),
            deadline=deadline,
            call_budget=budget.get("call_budget"),
            contribution_min=budget.get("contribution_min"),
            contribution_max=budget.get("contribution_max"),
            expected_grants=budget.get("expected_grants"),
            funding_rate=rate,
            funding_rate_note=rate_note,
            tags=[t for t in meta.get("tags", []) if t],
            summary=description[:300],
            text=description,
        )
        opp.compute_hash()
        return opp

    # ---- public -----------------------------------------------------------

    def fetch(self) -> List[Opportunity]:
        timeout = float(self.http_cfg.get("timeout_s", 60))
        out: Dict[str, Opportunity] = {}
        with httpx.Client(timeout=timeout, headers={"User-Agent": "funding-tracker/0.1"}) as client:
            page = 1
            total: Optional[int] = None
            while page <= int(self.cfg.get("max_pages", 20)):
                data = self._fetch_page(client, page)
                results = data.get("results", [])
                if total is None:
                    total = int(data.get("totalResults", 0))
                    logger.info(f"portal reports [bold]{total}[/bold] topics")
                for hit in results:
                    opp = self._to_opportunity(hit)
                    if opp:
                        out[opp.id] = opp  # dedupe by identifier
                if not results or len(out) >= (total or 0):
                    break
                page += 1
        logger.info(f"fetched [bold]{len(out)}[/bold] unique topics")
        return list(out.values())

    def safe_fetch(self) -> List[Opportunity]:
        try:
            return self.fetch()
        except Exception as exc:  # noqa: BLE001 — isolate the pipeline from one bad source
            logger.error(f"[red]FT portal fetch failed:[/red] {exc}")
            return []
