"""Fit scoring: how well does an opportunity match *your* roadmap?

Score is 0–100 and decomposes into four explainable parts (see `FitBreakdown`):

    theme        0–60  vocabulary match against the priority themes in config.profile.themes.
                       Terms have tiers (anchor 4 · core 2 · context 0.75); a hit in the title or
                       call title counts ×2, in tags ×1.5, in the body ×1. Distinct terms only,
                       saturating: 60·(1−e^(−raw/8)). A theme is *active* only with ≥1 anchor hit,
                       a core hit in the title, or ≥3 core hits — context words never make a match.
                       Best theme + 25 % of the runner-up, then × the theme's priority weight.
                       Two axes: the theme flagged `capability: true` (humanoid / social robot / HRI)
                       is what you build; the others are application domains. A domain theme that
                       fires WITHOUT any capability signal (e.g. a pure clinical-trials call) is
                       halved and capped below "Good fit" — it is a place to bring a robot, not a
                       robot call.
    packs        0–15  the company keyword packs (PBN, am-LAB …) as a secondary signal.
    instrument   0–15  does the type of action fit a small robotics team applying with partners?
                       (RIA / IA / Pathfinder = full marks; ERC & individual fellowships ≈ none)
    conditions   0–10  100 % funding rate and a sensible grant size.
    penalty      ≤ 0   negative vocabulary (defence / military / gambling) unless the veterans
                       theme is the one that matched.

Verdicts: ≥ 70 Strong fit · ≥ 50 Good fit · ≥ 35 Worth a look · below → not shown as a match.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import Opportunity

TIER_WEIGHT = {"anchor": 4.0, "core": 2.0, "context": 0.75}
LOC_WEIGHT = {"title": 2.0, "tags": 1.5, "body": 1.0}
THEME_MAX, PACK_MAX, INSTR_MAX, COND_MAX = 60.0, 15.0, 15.0, 10.0
VERDICTS = [(70, "Strong fit"), (50, "Good fit"), (35, "Worth a look")]

# instrument fit for a small robotics company / lab applying in a consortium (0–1)
_INSTRUMENT_FIT: List[Tuple[str, float]] = [
    (r"research and innovation action", 1.0),
    (r"\binnovation action", 1.0),
    (r"pathfinder", 1.0),
    (r"transition", 0.85),
    (r"accelerator", 0.8),
    (r"EIC grants?", 0.9),
    (r"coordination and support", 0.55),
    (r"doctoral network|staff exchange", 0.5),
    (r"cofund", 0.3),
    (r"pre-?commercial|public procurement", 0.4),
    (r"postdoctoral|fellowship", 0.15),
    (r"\bERC\b", 0.15),
    (r"equity", 0.4),
    (r"simple grant|project grant", 0.7),
    (r"lump sum", 0.6),
]


def _term_regex(term: str) -> re.Pattern:
    if term.startswith("re:"):
        return re.compile(term[3:], re.I)
    esc = re.escape(term.lower()).replace(r"\-", "[-\\s]").replace(r"\ ", "[-\\s]")
    # terms of 7+ letters may continue into a compound / inflection ("robotik|lösungen", "humanoid|e", "patient|innen")
    tail = "" if len(term.replace(" ", "")) >= 7 else "(?![a-z0-9])"
    return re.compile(rf"(?<![a-z0-9]){esc}{tail}", re.I)


@dataclass
class Theme:
    key: str
    label: str
    priority: int
    weight: float
    terms: Dict[str, List[Tuple[str, re.Pattern]]]     # tier → [(term, regex)]
    color: str = "#0ea5e9"
    capability: bool = False                            # the "what we build" axis
    labels: Dict[str, str] = field(default_factory=dict)  # label_<lang> from config


@dataclass
class FitBreakdown:
    theme: float = 0.0
    packs: float = 0.0
    instrument: float = 0.0
    conditions: float = 0.0
    penalty: float = 0.0
    hits: List[str] = field(default_factory=list)      # "title: humanoid", "body: oncology"
    themes: List[Tuple[str, float]] = field(default_factory=list)   # (key, raw score) active themes

    @property
    def total(self) -> float:
        return max(0.0, min(100.0, self.theme + self.packs + self.instrument + self.conditions + self.penalty))


class FitScorer:
    def __init__(self, profile: Dict[str, Any], packs_cfg: Optional[Dict[str, Any]] = None):
        self.themes: List[Theme] = []
        for key, t in (profile.get("themes") or {}).items():
            self.themes.append(Theme(
                key=key, label=t.get("label", key), priority=int(t.get("priority", 3)),
                weight=float(t.get("weight", {1: 1.0, 2: 0.85, 3: 0.7}.get(int(t.get("priority", 3)), 0.7))),
                terms={tier: [(w, _term_regex(w)) for w in t.get(tier, []) or []] for tier in TIER_WEIGHT},
                color=t.get("color", "#0ea5e9"),
                capability=bool(t.get("capability", False)),
                labels={k[6:]: v for k, v in t.items() if k.startswith("label_")},
            ))
        self.themes.sort(key=lambda t: t.priority)
        self.negatives = [(w, _term_regex(w)) for w in profile.get("negative", []) or []]
        self.negative_exempt = set(profile.get("negative_exempt_themes", []) or [])
        self.min_grant = float(profile.get("min_grant_eur", 250_000))

        packs_cfg = packs_cfg or {}
        demote = {k.lower() for k in packs_cfg.get("demote", []) or []}
        self.packs: Dict[str, Dict[str, List[Tuple[str, re.Pattern]]]] = {}
        for k, comp in (packs_cfg.get("companies") or {}).items():
            tiers: Dict[str, List[Tuple[str, re.Pattern]]] = {"strong": [], "medium": [], "soft": []}
            for tier in tiers:
                for kw in (comp.get("keywords", {}) or {}).get(tier, []) or []:
                    tiers["soft" if kw.lower() in demote else tier].append((kw, _term_regex(kw)))
            self.packs[comp.get("name", k)] = tiers

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _fields(o: Opportunity) -> Dict[str, str]:
        return {
            "title": f"{o.title} {o.call_title}",
            "tags": " ".join(o.tags),
            "body": f"{o.id} {o.text or o.summary}",
        }

    def _theme_raw(self, theme: Theme, fields: Dict[str, str]) -> Tuple[float, bool, List[str], float]:
        """→ (raw score, active?, top hits, raw from anchor+core only — the part that counts as a real signal)"""
        raw, hits, n_anchor, n_core, core_in_title, strong_raw = 0.0, [], 0, 0, False, 0.0
        for tier, terms in theme.terms.items():
            for term, rx in terms:
                best_loc = next((loc for loc in ("title", "tags", "body") if rx.search(fields[loc])), None)
                if not best_loc:
                    continue
                raw += TIER_WEIGHT[tier] * LOC_WEIGHT[best_loc]
                if tier != "context":
                    strong_raw += TIER_WEIGHT[tier] * LOC_WEIGHT[best_loc]
                n_anchor += tier == "anchor"
                n_core += tier == "core"
                core_in_title |= tier == "core" and best_loc == "title"
                hits.append((TIER_WEIGHT[tier] * LOC_WEIGHT[best_loc], f"{best_loc}: {term.removeprefix('re:')}"))
        # a core term in the *title* is as good as an anchor: a call named "…Robotik…" is a robotics call
        active = n_anchor >= 1 or core_in_title or n_core >= 3
        hits.sort(key=lambda h: -h[0])
        return raw, active, [h[1] for h in hits[:6]], strong_raw

    def _instrument(self, o: Opportunity) -> float:
        if o.source != "portal":
            return 0.55 * INSTR_MAX                      # unknown instrument → neutral
        for pat, fit in _INSTRUMENT_FIT:
            if re.search(pat, o.action_type, re.I):
                return fit * INSTR_MAX
        return 0.5 * INSTR_MAX

    def _conditions(self, o: Opportunity) -> float:
        pts = 0.0
        if o.is_full_rate:
            pts += 6
        elif o.funding_rate and o.funding_rate[0].isdigit():
            pts += 3
        elif o.source != "portal":
            pts += 2
        size = o.contribution_max or o.call_budget
        if size is None:
            pts += 2
        elif size >= self.min_grant:
            pts += 4
        return min(COND_MAX, pts)

    # ------------------------------------------------------------------ public
    def score(self, o: Opportunity) -> FitBreakdown:
        fields = self._fields(o)
        bd = FitBreakdown()

        # --- themes (two axes: capability = what we build, domains = where we bring it)
        active: List[Tuple[Theme, float, List[str]]] = []
        capability_raw = 0.0
        for t in self.themes:
            raw, is_active, hits, strong_raw = self._theme_raw(t, fields)
            if t.capability:
                capability_raw = max(capability_raw, strong_raw)   # context words ("ai") are not a robot signal
            if is_active:
                active.append((t, raw, hits))
        active.sort(key=lambda x: -(x[1] * x[0].weight))
        domain_only = False
        if active:
            best_t, best_raw, best_hits = active[0]
            sat = lambda r: THEME_MAX * (1 - math.exp(-r / 8))
            theme_pts = sat(best_raw) * best_t.weight
            if len(active) > 1:
                theme_pts += 0.25 * sat(active[1][1]) * active[1][0].weight
            domain_only = not best_t.capability and capability_raw < TIER_WEIGHT["core"]
            if domain_only:
                theme_pts *= 0.5
                best_hits = best_hits + ["(no robot / HRI signal)"]
            bd.theme = min(THEME_MAX, theme_pts)
            bd.hits = best_hits
            bd.themes = [(t.key, round(r, 1)) for t, r, _ in active]

        # --- packs (secondary)
        best_pack = 0.0
        for name, tiers in self.packs.items():
            blob = " ".join(fields.values())
            s = sum(w * min(sum(1 for _, rx in tiers[tier] if rx.search(blob)), 3)
                    for tier, w in (("strong", 3.0), ("medium", 1.5), ("soft", 0.5)))
            best_pack = max(best_pack, s)
        bd.packs = min(PACK_MAX, best_pack * (PACK_MAX / 12))

        # --- instrument & conditions only matter once a theme fired
        if active:
            bd.instrument = self._instrument(o)
            bd.conditions = self._conditions(o)

        # --- negatives
        neg = [w for w, rx in self.negatives if rx.search(" ".join(fields.values()))]
        if neg and not (active and active[0][0].key in self.negative_exempt):
            bd.penalty = -12.0 * len(neg)
            bd.hits = bd.hits + [f"⚠ {w}" for w in neg[:2]]

        # --- write back
        o.fit_score = round(min(bd.total, 49) if domain_only else bd.total)
        o.fit_theme = active[0][0].key if active else ""
        o.fit_theme_label = active[0][0].label if active else ""
        o.fit_verdict = next((v for th, v in VERDICTS if o.fit_score >= th), "")
        o.fit_breakdown = {"theme": round(bd.theme), "packs": round(bd.packs), "instrument": round(bd.instrument),
                           "conditions": round(bd.conditions), "penalty": round(bd.penalty)}
        o.interest_hits = bd.hits
        o.interest_score = float(o.fit_score)
        o.interest_for = [active[0][0].label] if o.fit_verdict else []
        return bd

    def score_all(self, opps: List[Opportunity]) -> None:
        for o in opps:
            self.score(o)

    def theme_meta(self) -> List[Dict[str, Any]]:
        return [{"key": t.key, "label": t.label, "priority": t.priority, "color": t.color,
                 **{f"label_{k}": v for k, v in t.labels.items()}} for t in self.themes]
