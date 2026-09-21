"""Indicative funding rates (share of eligible costs reimbursed by the EU grant).

The portal only spells the rate out when it deviates from the programme default, so we
first look for an explicit statement in the topic conditions, then fall back to the
standard rate per type of action. Always double-check the call conditions before applying.
"""
from __future__ import annotations

import re
from typing import Tuple

# (programme, regex on the cleaned action-type string) → rate.  Order matters: first match wins.
_RULES: list[tuple[str, str, str]] = [
    # --- Horizon Europe / Euratom (Model Grant Agreement art. 5) ---
    ("HORIZON", r"research and innovation action", "100%"),
    ("HORIZON", r"coordination and support action", "100%"),
    ("HORIZON", r"training and mobility", "100%"),
    ("HORIZON", r"\bERC\b", "100%"),
    ("HORIZON", r"\bMSCA\b|marie", "100%"),
    ("HORIZON", r"pathfinder|transition", "100%"),
    ("HORIZON", r"accelerator", "70%"),
    ("HORIZON", r"equity", "equity"),
    ("HORIZON", r"pre-?commercial procurement", "100%"),
    ("HORIZON", r"public procurement of innovative", "50%"),
    ("HORIZON", r"innovation action", "70% (100% for non-profit)"),
    ("HORIZON", r"cofund", "up to 30%"),
    ("HORIZON", r"\bEIT\b|KIC", "varies"),
    ("EURATOM", r"research and innovation action|coordination and support", "100%"),
    ("EURATOM", r"innovation action", "70% (100% for non-profit)"),
    # --- other programmes (typical defaults) ---
    ("DIGITAL", r"coordination and support", "100%"),
    ("DIGITAL", r"simple grant", "50%"),
    ("DIGITAL", r"SME support", "75%"),
    ("EDF", r"research action", "100%"),
    ("EDF", r"development action", "20–100%"),
    ("LIFE", r".*", "60% (typ.)"),
    ("CEF", r".*", "30–50%"),
    ("ERASMUS", r".*", "lump sum"),
    ("CERV", r".*", "90%"),
    ("SMP", r".*", "varies"),
    ("I3", r".*", "70%"),
    ("EUBA", r".*", "varies"),
]

_EXPLICIT = re.compile(
    r"(?:funding|co-?financing|reimbursement)\s+rate\s+(?:is|of|will be|:)?\s*(up to\s*)?(\d{2,3})\s*%",
    re.I,
)


def infer_funding_rate(programme: str, action_type: str, conditions_text: str = "") -> Tuple[str, str]:
    """Return (rate, note)."""
    m = _EXPLICIT.search(conditions_text or "")
    if m:
        rate = f"{'up to ' if m.group(1) else ''}{m.group(2)}%"
        return rate, "stated in call conditions"

    prog = programme.upper().rstrip("0123456789")  # LIFE2027 → LIFE
    for rule_prog, pattern, rate in _RULES:
        if rule_prog == prog and re.search(pattern, action_type, re.I):
            return rate, f"standard rate for {rule_prog} {action_type}"
    return "", ""
