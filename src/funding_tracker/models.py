from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import List, Optional

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
    "EURATOM": "Euratom",
}


class Opportunity(BaseModel):
    """Canonical funding-opportunity record (one per portal topic)."""

    id: str                                    # e.g. "HORIZON-CL4-2026-DIGITAL-01-02"
    title: str
    url: str
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
    tags: List[str] = Field(default_factory=list)
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = ""

    @property
    def cluster(self) -> str:
        """Group key derived from the identifier: HORIZON-CL4-… → 'CL4'."""
        m = re.match(r"^(?:HORIZON-)?([A-Z0-9]+)", self.id)
        key = m.group(1) if m else "OTHER"
        # JU calls look like HORIZON-JU-CBE-…, HORIZON-JU-IHI-… — fold them together
        if key == "JU":
            return "JU"
        return key

    @property
    def cluster_label(self) -> str:
        return CLUSTER_LABELS.get(self.cluster, self.cluster)

    def compute_hash(self) -> str:
        """SHA-1 over the fields whose change is worth flagging."""
        blob = f"{self.id}|{self.title}|{self.status}|{self.deadline}|{self.call_budget}|{self.contribution_max}"
        self.content_hash = hashlib.sha1(blob.encode()).hexdigest()[:12]
        return self.content_hash
