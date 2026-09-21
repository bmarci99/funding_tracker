from __future__ import annotations

from datetime import date as dt_date, timedelta
from typing import List, Set

from ..models import Opportunity
from .digest_html import fmt_eur, group_by_cluster


def render_markdown(
    opps: List[Opportunity],
    *,
    new_ids: Set[str] | None = None,
    date: str = "",
    closing_soon_days: int = 30,
) -> str:
    new_ids = new_ids or set()
    today = dt_date.today()
    soon = today + timedelta(days=closing_soon_days)
    lines: List[str] = []

    lines.append(f"# Horizon Funding Digest — {date}")
    lines.append("")
    lines.append(f"**{len(opps)}** topics tracked · **{len(new_ids)}** new")
    lines.append("")

    def row(o: Opportunity) -> str:
        flag = " 🆕" if o.id in new_ids else ""
        dl = f" ⏰ {o.deadline}" if o.deadline else ""
        budget = ""
        if o.contribution_max:
            budget = f" · ≤{fmt_eur(o.contribution_max)}/grant" + (f" ×{o.expected_grants}" if o.expected_grants else "")
        elif o.call_budget:
            budget = f" · call {fmt_eur(o.call_budget)}"
        return f"- [{o.title}]({o.url}) `{o.id}` — {o.action_type or o.status}{budget}{dl}{flag}"

    closing = sorted(
        (o for o in opps if o.deadline and today <= o.deadline <= soon),
        key=lambda o: o.deadline,
    )
    if closing:
        lines.append(f"## ⏰ Closing within {closing_soon_days} days")
        lines.append("")
        lines.extend(row(o) for o in closing)
        lines.append("")

    for label, items in group_by_cluster(opps).items():
        n_new = sum(1 for o in items if o.id in new_ids)
        badge = f" (+{n_new} new)" if n_new else ""
        lines.append(f"## {label}{badge}")
        lines.append("")
        lines.extend(row(o) for o in items)
        lines.append("")

    lines.append("---")
    lines.append(f"_Generated {date} by Funding Tracker · source: EU Funding & Tenders Portal_")
    return "\n".join(lines)
