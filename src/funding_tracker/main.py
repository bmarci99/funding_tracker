from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .delivery.email_sender import send_digest_email
from .ingest.ft_portal import FTPortalIngester
from .models import Opportunity
from .render.digest_html import render_html
from .render.digest_md import render_markdown
from .render.site_builder import build_site
from .util.history import diff_items, load_history, prune_history, record_items, save_history
from .util.logging import section, setup_logger

logger, console = setup_logger()


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def apply_filters(opps: List[Opportunity], f: Dict[str, Any]) -> List[Opportunity]:
    """Keyword include/exclude + deadline horizon, all from config.filters."""
    inc = [k.lower() for k in f.get("include_keywords", []) or []]
    exc = [k.lower() for k in f.get("exclude_keywords", []) or []]
    horizon = int(f.get("deadline_within_days", 0) or 0)
    cutoff = date.today() + timedelta(days=horizon) if horizon else None

    def blob(o: Opportunity) -> str:
        return " ".join([o.id, o.title, o.call_title, o.action_type, *o.tags]).lower()

    out: List[Opportunity] = []
    for o in opps:
        b = blob(o)
        if inc and not any(k in b for k in inc):
            continue
        if exc and any(k in b for k in exc):
            continue
        if cutoff and o.deadline and o.deadline > cutoff:
            continue
        out.append(o)
    return out


def run_pipeline(cfg: Dict[str, Any], *, send_email: bool = False) -> Dict[str, Any]:
    """ingest → filter → diff → render → archive → email"""
    t0 = time.monotonic()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # --- 1. Ingest ---
    section(console, "INGEST")
    opps = FTPortalIngester(cfg["portal"], cfg.get("http", {})).safe_fetch()
    before = len(opps)
    opps = apply_filters(opps, cfg.get("filters", {}))
    logger.info(f"{before} fetched → [bold]{len(opps)}[/bold] after filters")

    # --- 2. Diff against history ---
    section(console, "DIFF")
    hist_cfg = cfg.get("history", {})
    hist_path = hist_cfg.get("path", "outputs/history.json")
    history = prune_history(load_history(hist_path), hist_cfg.get("rolling_days", 400))
    first_run = not history.get("items")

    current = [o.model_dump(mode="json") for o in opps]
    new_items, changed_items, removed_items = diff_items(current, history)
    if first_run:
        # No baseline yet — don't flag the whole portal as "new"
        logger.info("first run: seeding history, nothing flagged as new")
        new_items = []
    logger.info(
        f"[green]+{len(new_items)} new[/green] · [yellow]~{len(changed_items)} changed[/yellow] · "
        f"[red]-{len(removed_items)} removed[/red] · {len(opps)} total"
    )
    save_history(hist_path, record_items(history, current))

    # --- 3. Render ---
    section(console, "RENDER")
    out_dir = Path(cfg.get("output", {}).get("dir", "outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)
    new_ids = {i["id"] for i in new_items}
    dg = cfg.get("digest", {})
    archive_url = cfg.get("output", {}).get("archive_url", "")

    (out_dir / "digest.json").write_text(
        json.dumps(
            {"date": today, "total": len(opps), "new": len(new_items), "changed": len(changed_items),
             "removed": len(removed_items), "items": current, "new_items": new_items, "removed_items": removed_items},
            ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_text = render_markdown(opps, new_ids=new_ids, date=today, closing_soon_days=dg.get("closing_soon_days", 30))
    (out_dir / "digest.md").write_text(md_text, encoding="utf-8")
    render_kw = dict(
        new_ids=new_ids, date=today,
        closing_soon_days=dg.get("closing_soon_days", 30),
        max_per_cluster=dg.get("max_per_cluster", 0),
        archive_url=archive_url,
    )
    html_text = render_html(opps, compact=True, max_rows=dg.get("max_rows_per_section", 40), **render_kw)       # email: compact
    html_full = render_html(opps, compact=False, **render_kw)      # archive: everything
    (out_dir / "digest.html").write_text(html_text, encoding="utf-8")
    (out_dir / "digest_full.html").write_text(html_full, encoding="utf-8")
    logger.info(f"email HTML {len(html_text.encode()) / 1024:.0f} KB · full HTML {len(html_full.encode()) / 1024:.0f} KB")
    logger.info(f"Outputs → {out_dir}/")

    # --- 4. Archive (GitHub Pages) ---
    if cfg.get("output", {}).get("archive", True):
        section(console, "ARCHIVE")
        build_site(html_full, today, cfg.get("output", {}).get("archive_dir", "docs"))

    # --- 5. Email ---
    has_changes = bool(new_items or changed_items)
    if send_email and (has_changes or cfg.get("email", {}).get("send_on_empty", False)):
        section(console, "EMAIL")
        prefix = cfg.get("email", {}).get("subject_prefix", "Horizon Funding Digest")
        subj = f"{prefix} — {today}" + (f" (+{len(new_items)} new)" if new_items else "")
        send_digest_email(html_text, subject=subj, text_fallback=md_text)
    elif send_email:
        logger.info("No changes — skipping email")

    # --- 6. Stats ---
    elapsed = time.monotonic() - t0
    stats = {
        "date": today, "elapsed_s": round(elapsed, 1), "total": len(opps),
        "new": len(new_items), "changed": len(changed_items), "removed": len(removed_items),
        "per_cluster": {},
    }
    for o in opps:
        stats["per_cluster"][o.cluster] = stats["per_cluster"].get(o.cluster, 0) + 1
    (out_dir / "run_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    section(console, "DONE")
    logger.info(f"Completed in {elapsed:.1f}s")
    return stats


def cli() -> None:
    p = argparse.ArgumentParser(description="Horizon Funding Tracker")
    p.add_argument("--send-email", action="store_true", help="Send digest email (needs GMAIL_* env vars)")
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args()
    run_pipeline(load_config(args.config), send_email=args.send_email)


if __name__ == "__main__":
    cli()
