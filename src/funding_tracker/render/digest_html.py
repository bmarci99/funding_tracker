from __future__ import annotations

from datetime import date as dt_date, timedelta
from pathlib import Path
from typing import Dict, List, Set

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..i18n import Translator
from ..models import Opportunity

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def fmt_eur(v: float | None) -> str:
    """1500000 → '€1.5M', 200000 → '€200k'."""
    if not v:
        return "—"
    if v >= 1_000_000:
        s = f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"€{s}M"
    if v >= 1_000:
        return f"€{v / 1_000:.0f}k"
    return f"€{v:.0f}"


def days_left(d: dt_date | None, today: dt_date) -> int | None:
    return (d - today).days if d else None


def render_html(
    opps: List[Opportunity],
    *,
    new_ids: Set[str] | None = None,
    date: str = "",
    closing_soon_days: int = 30,
    max_per_cluster: int = 0,
    archive_url: str = "",
    compact: bool = False,
    max_rows: int = 40,
    threshold: float = 35,
    themes: List[Dict] | None = None,
    max_per_theme: int = 10,
    lang: str = "en",
    ai_pick_min: int = 55,
    foundation_rows: int = 12,
) -> str:
    """Render the digest.

    compact=True  → email version: closing-soon + new + one summary row per cluster
                    (keeps the mail well under Gmail's ~100 KB clipping limit).
    compact=False → full archive page with every topic listed per cluster.
    """
    new_ids = new_ids or set()
    today = dt_date.today()
    soon = today + timedelta(days=closing_soon_days)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    tr = Translator(lang)
    env.filters["eur"] = fmt_eur
    env.filters["rate"] = tr.rate
    env.globals["t"] = tr
    env.filters["days_left"] = lambda d: days_left(d, today)
    tmpl = env.get_template("email.html")

    portal = [o for o in opps if o.source == "portal"]
    foundations = [o for o in opps if o.source != "portal"]

    by_deadline = sorted(portal, key=lambda o: (o.deadline or dt_date.max, o.id))
    matches = sorted((o for o in opps if o.interest_for),
                     key=lambda o: (-o.fit_score, o.deadline or dt_date.max, o.id))
    closing_soon = [o for o in by_deadline if o.deadline and today <= o.deadline <= soon]
    new_items = [o for o in by_deadline if o.id in new_ids]
    new_foundations = sorted((o for o in foundations if o.id in new_ids), key=lambda o: (o.programme, o.title))
    matches_total, closing_soon_total, new_total, new_found_total = len(matches), len(closing_soon), len(new_items), len(new_foundations)
    if compact and max_rows:
        matches, closing_soon, new_items, new_foundations = (
            matches[:max_rows], closing_soon[:max_rows], new_items[:max_rows], new_foundations[:max_rows])

    grouped = group_by_cluster(portal)
    found_grouped = group_by_cluster(foundations)

    # matches grouped by theme, themes in priority order, each theme's rows by score
    themes = themes or []
    theme_order = [t["key"] for t in themes]
    theme_info = {t["key"]: t for t in themes}
    by_theme: Dict[str, List[Opportunity]] = {}
    for o in matches:
        by_theme.setdefault(o.fit_theme, []).append(o)
    match_groups = [
        {"key": k, "label": tr.theme_label(theme_info.get(k, {"key": k})), "color": theme_info.get(k, {}).get("color", "#7c3aed"),
         "priority": theme_info.get(k, {}).get("priority", 9),
         "items": by_theme[k][:max_per_theme] if compact and max_per_theme else by_theme[k],
         "total": sum(1 for o in opps if o.interest_for and o.fit_theme == k)}
        for k in sorted(by_theme, key=lambda k: (theme_order.index(k) if k in theme_order else 99))
    ]
    all_matches = [o for o in opps if o.interest_for]
    # foundations ranked by the analyst (fit as tie-break) — the email always shows the top of this list
    found_ranked = sorted(foundations, key=lambda o: (-int(o.ai.get("ai_score", 0)), -o.fit_score, o.deadline or dt_date.max, o.title))
    found_top = found_ranked[:foundation_rows] if compact else found_ranked
    ai_picks = sorted((o for o in opps if o.ai_pick and not o.interest_for),
                      key=lambda o: (-int(o.ai.get("ai_score", 0)), o.deadline or dt_date.max, o.id))
    ai_picks_total = len(ai_picks)
    if compact and max_rows:
        ai_picks = ai_picks[:max_rows]
    verdict_counts = {
        "Strong fit": sum(1 for o in all_matches if o.fit_verdict == "Strong fit"),
        "Good fit": sum(1 for o in all_matches if o.fit_verdict == "Good fit"),
        "Worth a look": sum(1 for o in all_matches if o.fit_verdict == "Worth a look"),
    }
    focus_strip = [
        {"label": tr.theme_label(t), "color": t["color"], "priority": t["priority"],
         "count": sum(1 for o in all_matches if o.fit_theme == t["key"])}
        for t in themes
    ]
    if max_per_cluster:
        grouped = {k: v[:max_per_cluster] for k, v in grouped.items()}

    cluster_summary = [
        {
            "label": label,
            "key": items[0].cluster,
            "count": len(items),
            "open": sum(1 for o in items if o.status == "Open"),
            "new": sum(1 for o in items if o.id in new_ids),
            "next_deadline": next((o.deadline for o in items if o.deadline and o.deadline >= today), None),
        }
        for label, items in grouped.items()
    ]

    return tmpl.render(
        lang=lang,
        compact=compact,
        cluster_summary=cluster_summary,
        matches=matches, matches_total=matches_total, threshold=threshold,
        match_groups=match_groups, verdict_counts=verdict_counts, focus_strip=focus_strip,
        match_count=len(all_matches),
        ai_picks=ai_picks, ai_picks_total=ai_picks_total, ai_pick_min=ai_pick_min,
        ai_pick_count=sum(1 for o in opps if o.ai_pick),
        found_top=found_top, found_ranked=found_ranked,
        full_rate_count=sum(1 for o in opps if o.is_full_rate),
        new_foundations=new_foundations, new_found_total=new_found_total,
        found_grouped=found_grouped, foundations_total=len(foundations),
        date=date,
        today=today,
        total=len(portal),
        open_count=sum(1 for o in portal if o.status == "Open"),
        forthcoming_count=sum(1 for o in portal if o.status == "Forthcoming"),
        new_count=len(new_ids),
        closing_soon=closing_soon,
        closing_soon_total=closing_soon_total,
        closing_soon_days=closing_soon_days,
        new_items=new_items,
        new_total=new_total,
        grouped=grouped,
        new_ids=new_ids,
        soon=soon,
        archive_url=archive_url,
    )


def group_by_cluster(opps: List[Opportunity]) -> Dict[str, List[Opportunity]]:
    """cluster label → [opps sorted by deadline]. Keys ordered by earliest deadline."""
    groups: Dict[str, List[Opportunity]] = {}
    for o in opps:
        groups.setdefault(o.cluster_label, []).append(o)
    for k in groups:
        groups[k].sort(key=lambda o: (o.deadline or dt_date.max, o.id))
    return dict(sorted(groups.items(), key=lambda kv: (kv[1][0].deadline or dt_date.max, kv[0])))
