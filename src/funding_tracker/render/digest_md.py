from __future__ import annotations

from datetime import date as dt_date, timedelta
from typing import List, Set

from ..i18n import Translator
from ..models import Opportunity
from .digest_html import fmt_eur, group_by_cluster


def render_markdown(
    opps: List[Opportunity],
    *,
    new_ids: Set[str] | None = None,
    date: str = "",
    closing_soon_days: int = 30,
    threshold: float = 35,
    themes: List[dict] | None = None,
    lang: str = "en",
) -> str:
    tr = Translator(lang)
    new_ids = new_ids or set()
    today = dt_date.today()
    soon = today + timedelta(days=closing_soon_days)
    lines: List[str] = []

    portal = [o for o in opps if o.source == "portal"]
    lines.append("# " + tr("md_title", date=date))
    lines.append("")
    lines.append(tr("md_stats", portal=len(portal), m=sum(1 for o in opps if o.interest_for),
                    full=sum(1 for o in portal if o.is_full_rate), new=len(new_ids)))
    lines.append("")

    def row(o: Opportunity) -> str:
        flag = " 🆕" if o.id in new_ids else ""
        dl = f" ⏰ {o.deadline}" if o.deadline else ""
        budget = ""
        if o.contribution_max:
            budget = f" · ≤{fmt_eur(o.contribution_max)}/grant" + (f" ×{o.expected_grants}" if o.expected_grants else "")
        elif o.call_budget:
            budget = f" · call {fmt_eur(o.call_budget)}"
        rate = f" · 💯 {tr.rate(o.funding_rate)}" if o.is_full_rate else (f" · {tr.rate(o.funding_rate)}" if o.funding_rate else "")
        score = f" ⭐{o.fit_score}" if o.interest_for else ""
        return f"- [{o.title}]({o.url}) `{o.id}` — {o.action_type or o.programme}{rate}{budget}{dl}{flag}{score}"

    matches = sorted((o for o in opps if o.interest_for), key=lambda o: (-o.fit_score, o.id))
    if matches:
        lines.append(tr("md_matches", n=len(matches)))
        lines.append("")
        for t in themes or []:
            items = [o for o in matches if o.fit_theme == t["key"]]
            if not items:
                continue
            lines.append(f"### P{t['priority']} · {tr.theme_label(t)} ({len(items)})")
            lines.append("")
            for o in items:
                why = ", ".join(h.split(": ", 1)[-1] for h in o.interest_hits)
                lines.append(row(o) + f" — **{o.fit_score} {tr(o.fit_verdict)}** · {why}")
                if o.ai.get("applicable"):
                    lines.append(f"  - 🤖 AI {o.ai.get('ai_score')}: {o.ai.get('angle', '')} — {o.ai.get('next_step', '')}")
            lines.append("")

    closing = sorted(
        (o for o in opps if o.deadline and today <= o.deadline <= soon),
        key=lambda o: o.deadline,
    )
    if closing:
        lines.append(tr("md_soon", d=closing_soon_days))
        lines.append("")
        lines.extend(row(o) for o in closing)
        lines.append("")

    for label, items in group_by_cluster(portal).items():
        n_new = sum(1 for o in items if o.id in new_ids)
        badge = f" (+{n_new} new)" if n_new else ""
        lines.append(f"## {label}{badge}")
        lines.append("")
        lines.extend(row(o) for o in items)
        lines.append("")

    found_new = [o for o in opps if o.source != "portal" and o.id in new_ids]
    if found_new:
        lines.append(tr("md_found"))
        lines.append("")
        lines.extend(f"- [{o.title}]({o.url}) — {o.programme}" for o in found_new)
        lines.append("")

    lines.append("---")
    lines.append(tr("md_footer", date=date))
    return "\n".join(lines)
