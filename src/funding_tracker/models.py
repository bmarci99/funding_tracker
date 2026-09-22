from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field


# Maps the identifier prefix (HORIZON-<X>-…) to a human label for grouping.
CLUSTER_LABELS = {
    "ERC": "ERC — European Research Council",
    "MSCA": "MSCA — Marie Skłodowska-Curie Actions",
    "INFRA": "Research Infrastructures",
    "CL1": "Cluster 1 — Health",
    "HLTH": "Cluster 1 — Health",
    "CL2": "Cluster 2 — Culture, Creativity & Inclusive Society",
    "CL3": "Cluster 3 — Civil Security for Society",
    "CL4": "Cluster 4 — Digital, Industry & Space",
    "CL5": "Cluster 5 — Climate, Energy & Mobility",
    "CL6": "Cluster 6 — Food, Bioeconomy, Natural Resources, Agriculture & Environment",
    "EIC": "EIC — European Innovation Council",
    "EIE": "European Innovation Ecosystems",
    "EIT": "EIT — European Institute of Innovation & Technology",
    "MISS": "EU Missions",
    "WIDERA": "Widening Participation & ERA",
    "JU": "Joint Undertakings",
    "EUROHPC": "EuroHPC JU",
    "NEB": "New European Bauhaus",
    "RAISE": "RAISE — AI in Science",
    "CID": "Clean Industrial Deal",
}


class Opportunity(BaseModel):
    """Canonical funding-opportunity record — one per portal topic or foundation call."""

    id: str                                    # e.g. "HORIZON-CL4-2026-DIGITAL-01-02" or "found:<hash>"
    title: str
    url: str
    source: str = "portal"                     # "portal" (EU Funding & Tenders) | "foundation"
    programme: str = "HORIZON"                 # portal programme abbreviation, or foundation name
    call_id: str = ""
    call_title: str = ""
    status: str = ""                           # "Open" / "Forthcoming"
    action_type: str = ""                      # e.g. "Research and Innovation Actions"
    deadline_model: str = ""                   # single-stage / two-stage / continuous
    opening_date: Optional[date] = None
    deadline: Optional[date] = None
    call_budget: Optional[float] = None        # EUR, indicative budget of the parent call
    contribution_min: Optional[float] = None
    contribution_max: Optional[float] = None
    expected_grants: Optional[int] = None
    funding_rate: str = ""                     # "100%", "70%", "up to 30%", "" = unknown
    funding_rate_note: str = ""                # where the rate came from / caveats
    tags: List[str] = Field(default_factory=list)
    summary: str = ""                          # first ~300 chars of the topic description
    country: str = ""                          # foundations only
    fit_score: int = 0                         # 0–100, see scoring.py
    fit_verdict: str = ""                      # "Strong fit" / "Good fit" / "Worth a look" / ""
    fit_theme: str = ""                        # key of the best-matching priority theme
    fit_theme_label: str = ""
    fit_breakdown: Dict[str, int] = Field(default_factory=dict)
    interest_score: float = 0.0                # = fit_score (kept for the renderers)
    interest_hits: List[str] = Field(default_factory=list)   # "title: humanoid", "body: oncology", "⚠ military"
    interest_for: List[str] = Field(default_factory=list)    # [theme label] when it is a match
    ai: Dict[str, Any] = Field(default_factory=dict)   # analyst.py output: applicable, ai_score, angle, entity, …
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = ""
    text: str = Field(default="", exclude=True)  # full description used for matching; not persisted

    AI_PICK_MIN: ClassVar[int] = 55

    @property
    def ai_pick(self) -> bool:
        """The analyst thinks we can apply and it is attractive (≥ AI_PICK_MIN)."""
        return bool(self.ai.get("applicable")) and int(self.ai.get("ai_score", 0)) >= self.AI_PICK_MIN

    @property
    def is_full_rate(self) -> bool:
        return self.funding_rate.replace(" ", "").startswith("100%")

    @property
    def cluster(self) -> str:
        """Group key: Horizon topics by cluster (HORIZON-CL4-… → 'CL4'), everything else by programme."""
        if self.source != "portal":
            return self.programme
        if self.programme not in ("HORIZON", "EURATOM"):
            return self.programme
        m = re.match(r"^(?:HORIZON-)?([A-Z0-9]+)", self.id)
        return m.group(1) if m else self.programme

    @property
    def cluster_label(self) -> str:
        if self.source != "portal":
            return self.programme
        return CLUSTER_LABELS.get(self.cluster, self.cluster)

    def compute_hash(self) -> str:
        """SHA-1 over the fields whose change is worth flagging."""
        blob = f"{self.id}|{self.title}|{self.status}|{self.deadline}|{self.call_budget}|{self.contribution_max}"
        self.content_hash = hashlib.sha1(blob.encode()).hexdigest()[:12]
        return self.content_hash
