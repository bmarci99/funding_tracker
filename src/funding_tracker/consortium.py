"""Can one organisation apply alone? → Opportunity.consortium = "solo" | "optional" | "required" | "" (unknown).

Evidence, strongest first:
  1. EU portal: the programme rules — Horizon Europe RIA / IA need three independent entities from three
     countries, CSAs one; ERC, MSCA postdoctoral fellowships, EIC Accelerator and prizes are single-applicant
  2. the call text says so ("single applicant", "Einzelvorhaben", "consortium of 3 entities minimum",
     "Verbundprojekt" …) — the main evidence for foundations and national funders
  3. the AI analyst's reading of the call (foundations and national funders, where 1 and 2 are often silent)
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple

from .models import Opportunity

SOLO, OPTIONAL, REQUIRED = "solo", "optional", "required"

_OPTIONAL_RX = re.compile(
    r"single (?:applicants?|entit(?:y|ies)|organi[sz]ations?|beneficiar(?:y|ies)) or (?:a |in )?consorti|"
    r"alone or (?:in|with|as)|individually or (?:in|as|with)|on (?:your|their) own or (?:in|with)|"
    r"einzel- (?:oder|und) verbund|einzel- oder kooperations|önállóan vagy konzorcium",
    re.I)
_REQUIRED_RX = re.compile(
    r"consortium of at least|consortia of at least|at least (?:two|three|four|2|3|4) (?:independent )?(?:legal )?"
    r"(?:entities|partners|organi[sz]ations|applicants|beneficiaries)|minimum of (?:two|three|2|3) (?:partners|entities)|"
    r"partners from at least|transnational consortia|(?:a|the) consortium (?:is|must be) required|"
    r"(?:must be )?submitted by (?:a |an )?(?:[\w-]+ )?consorti|must apply as a consortium|every consortium must|"
    r"consorti(?:um|a) of (?:\d|two|three|four)|\b(?:\d|two|three) (?:entities|partners|organi[sz]ations) minimum|"
    r"minimum (?:of )?(?:\d|two|three) (?:entities|partners|organi[sz]ations)|verbundprojekt|verbundvorhaben|im verbund mit|"
    r"konsortium aus mindestens|konzorciumban|konzorcium formájában|konzorciumi tagok",
    re.I)
_SOLO_RX = re.compile(
    r"single applicant|single beneficiary|mono-?beneficiary|single legal entity|individual applicants?|"
    r"apply (?:alone|individually|on (?:your|their) own)|einzelvorhaben|einzelantrag|einzelprojekt|"
    r"egyéni pályázó|önálló pályázó",
    re.I)

# (pattern on "id | action type | title", verdict) — Horizon Europe General Annex A + programme guides
_PROGRAMME_RULES: Tuple[Tuple[re.Pattern, str], ...] = tuple((re.compile(p, re.I), v) for p, v in (
    (r"^ERC-|ERC Grants", SOLO),
    (r"Postdoctoral Fellowships", SOLO),
    (r"EIC-(?:\d{4}-)?ACCELERATOR|EIC Accelerator", SOLO),
    (r"-PRIZE|Recognition Prize|Inducement Prize", SOLO),
    (r"EIC-(?:\d{4}-)?(?:PATHFINDERCHALLENGES|TRANSITION)", OPTIONAL),
    (r"EIC-(?:\d{4}-)?PATHFINDEROPEN", REQUIRED),
    (r"Coordination and Support|\(CSA\)", OPTIONAL),
    (r"Doctoral Networks|Staff Exchanges|Cofund|Pre-commercial Procurement|Public Procurement of Innovat", REQUIRED),
    (r"Research and Innovation Action|\bInnovation Actions?\b|\((?:RIA|IA)\)", REQUIRED),
))


def from_text(text: str) -> str:
    if _OPTIONAL_RX.search(text):
        return OPTIONAL
    solo, required = bool(_SOLO_RX.search(text)), bool(_REQUIRED_RX.search(text))
    if solo and required:
        return OPTIONAL
    return SOLO if solo else REQUIRED if required else ""


def from_programme(o: Opportunity) -> str:
    if o.source != "portal":
        return ""
    key = f"{o.id} | {o.action_type} | {o.title}"      # some listings only say "(IA)" in the title
    return next((v for rx, v in _PROGRAMME_RULES if rx.search(key)), "")


def classify(o: Opportunity) -> str:
    """Fill o.consortium from the strongest available evidence; returns it.

    EU portal topics: the programme's eligibility rule wins — topic texts talk about *other* applicants
    ("SMEs, alone or within a team" = who a booster will sub-fund), which would mislead the text rules."""
    ai = str(o.ai.get("consortium", "")).lower() if o.ai else ""
    o.consortium = (from_programme(o) or from_text(f"{o.title} {o.text or o.summary}")
                    or (ai if ai in (SOLO, OPTIONAL, REQUIRED) else ""))
    return o.consortium


def classify_all(opps: Iterable[Opportunity]) -> None:
    for o in opps:
        classify(o)


def solo_bonus(o: Opportunity, bonus: float) -> float:
    """Ranking bonus: full for solo calls, half when partners are optional, none when a consortium is required."""
    return {SOLO: bonus, OPTIONAL: bonus / 2}.get(o.consortium, 0.0)
