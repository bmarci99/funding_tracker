"""Keyword-pack relevance scoring (ported from PBN Tender Radar's company packs).

Each company pack has strong / medium / soft / negative keyword lists. For every
opportunity we count *distinct* keyword hits per tier in (id + title + call title +
action + tags + description) and score:

    3.0 × min(strong, 3) + 1.5 × min(medium, 3) + 0.5 × min(soft, 3) − 5.0 × negative

The opportunity's score is the best company score; `interest_for` lists every company
that clears the threshold. Free-form `interests` regexes (e.g. humanoid / space from
HORIZONS) are scored like strong hits.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .models import Opportunity

WEIGHTS = {"strong": 3.0, "medium": 1.5, "soft": 0.5}
CAP = 3
NEGATIVE_PENALTY = 5.0


def _kw_regex(kw: str) -> re.Pattern:
    # word-boundary match, tolerant to hyphen/space variants ("human-robot" ~ "human robot")
    esc = re.escape(kw.lower()).replace(r"\-", "[-\\s]").replace(r"\ ", "[-\\s]")
    return re.compile(rf"(?<![a-z0-9]){esc}(?![a-z0-9])", re.I)


class InterestScorer:
    def __init__(self, cfg: Dict[str, Any]):
        self.threshold = float(cfg.get("threshold", 3.0))
        demote = {k.lower() for k in cfg.get("demote", []) or []}
        self.companies: Dict[str, Dict[str, List[Tuple[str, re.Pattern]]]] = {}
        for key, comp in (cfg.get("companies") or {}).items():
            packs = comp.get("keywords", {}) or {}
            tiers: Dict[str, List[Tuple[str, re.Pattern]]] = {t: [] for t in ("strong", "medium", "soft", "negative")}
            for tier in tiers:
                for kw in packs.get(tier, []) or []:
                    target = "soft" if (tier != "negative" and kw.lower() in demote) else tier
                    tiers[target].append((kw, _kw_regex(kw)))
            self.companies[comp.get("name", key)] = tiers
        self.interests = [(i["label"], re.compile(i["pattern"], re.I)) for i in cfg.get("interests", []) or []]

    def _blob(self, o: Opportunity) -> str:
        return " ".join([o.id, o.title, o.call_title, o.action_type, " ".join(o.tags), o.text or o.summary]).lower()

    def score(self, o: Opportunity) -> None:
        blob = self._blob(o)
        best, best_hits, matched = 0.0, [], []

        for name, tiers in self.companies.items():
            hits: Dict[str, List[str]] = {t: [kw for kw, rx in tiers[t] if rx.search(blob)] for t in tiers}
            s = sum(WEIGHTS[t] * min(len(hits[t]), CAP) for t in WEIGHTS)
            s -= NEGATIVE_PENALTY * len(hits["negative"])
            if s >= self.threshold:
                matched.append(name)
            if s > best:
                best = s
                best_hits = hits["strong"][:4] + hits["medium"][:3] + hits["soft"][:2]

        for label, rx in self.interests:
            if rx.search(blob):
                best = max(best, WEIGHTS["strong"]) + WEIGHTS["strong"]
                best_hits = [f"★ {label}"] + best_hits
                if label not in matched:
                    matched.append(label)

        o.interest_score = round(best, 1)
        o.interest_hits = best_hits[:8]
        o.interest_for = matched

    def score_all(self, opps: List[Opportunity]) -> None:
        for o in opps:
            self.score(o)
