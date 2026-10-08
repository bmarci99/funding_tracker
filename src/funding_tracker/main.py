from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .analyst import Analyst
from .consortium import classify_all
from .delivery.email_sender import send_digest_email
from .i18n import Translator
from .ingest.foundations import FoundationsIngester
from .ingest.ft_portal import FTPortalIngester
from .scoring import FitScorer
from .models import Opportunity
from .render.digest_html import render_html
from .render.digest_md import render_markdown
from .render.site_builder import build_site
from .util.history import diff_items, first_seen_within, load_history, prune_history, record_items, save_history
from .util.logging import section, setup_logger

logger, console = setup_logger()


def load_dotenv(path: str = ".env") -> None:
    """KEY=value lines from .env into os.environ (already-set variables win). Keeps local runs = CI runs."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        key, sep, val = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip().removeprefix("export ").strip(), val.strip().strip("'\""))


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def apply_filters(opps: List[Opportunity], f: Dict[str, Any]) -> List[Opportunity]:
    """Keyword include/exclude + deadline horizon, all from config.filters."""
    inc = [k.lower() for k in f.get("include_keywords", []) or []]
    exc = [k.lower() for k in f.get("exclude_keywords", []) or []]
    horizon = int(f.get("deadline_within_days", 0) or 0)
    only_full = bool(f.get("only_full_rate", False))
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
        if o.deadline and o.deadline < date.today():   # stale portal entries (status never updated)
            continue
        if only_full and o.funding_rate and not o.is_full_rate:   # unknown rate → keep, it is flagged in the digest
            continue
        out.append(o)
    return out


def fit_email(opps: List[Opportunity], render_kw: Dict[str, Any], *, rows: int, per_theme: int, limit_kb: int) -> str:
    """Render the email, shrinking row caps until it fits — Gmail clips anything over ~102 KB.
    The secondary sections (AI picks, closing soon, new) shrink first; the roadmap matches only as a last resort."""
    while True:
        html = render_html(opps, compact=True, max_rows=rows, max_per_theme=per_theme, **render_kw)
        size_kb = len(html.encode()) / 1024
        if size_kb <= limit_kb or (rows <= 3 and per_theme <= 3):
            if size_kb > limit_kb:
                logger.warning(f"[yellow]email is {size_kb:.0f} KB even at minimum rows — Gmail will clip it[/yellow]")
            return html
        if rows > 3:
            rows = max(3, rows * 2 // 3)
        else:
            per_theme = max(3, per_theme * 2 // 3)
        logger.info(f"email {size_kb:.0f} KB > {limit_kb} KB → re-rendering with {rows} rows per section, {per_theme} per theme")


def run_pipeline(cfg: Dict[str, Any], *, send_email: bool = False) -> Dict[str, Any]:
    """ingest → filter → diff → render → archive → email"""
    t0 = time.monotonic()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # --- 1. Ingest ---
    section(console, "INGEST")
    http_cfg = cfg.get("http", {})
    opps: List[Opportunity] = []
    if cfg.get("portal", {}).get("enabled", True):
        opps += FTPortalIngester(cfg["portal"], http_cfg, cfg.get("profile", {}).get("entities")).safe_fetch()
    if cfg.get("foundations", {}).get("enabled", False):
        logger.info("foundations & national funders:")
        opps += FoundationsIngester(cfg["foundations"], http_cfg).safe_fetch()
    before = len(opps)
    opps = apply_filters(opps, cfg.get("filters", {}))
    logger.info(f"{before} fetched → [bold]{len(opps)}[/bold] after filters")

    # --- 1b. Relevance scoring ---
    scorer = FitScorer(cfg.get("profile", {}), cfg.get("packs", {}))
    scorer.score_all(opps)
    dg = cfg.get("digest", {})
    min_score = int(dg.get("match_min_score", 35))
    for o in opps:                                   # config threshold decides what counts as a match
        if o.fit_score < min_score:
            o.interest_for, o.fit_verdict = [], ""
    n_match = sum(1 for o in opps if o.interest_for)
    n_full = sum(1 for o in opps if o.is_full_rate)
    logger.info(f"[bold]{n_match}[/bold] match your profile · [bold]{n_full}[/bold] are 100%-funded")

    # --- 1c. AI analyst ---
    ai_cfg = cfg.get("ai", {})
    Opportunity.AI_PICK_MIN = int(ai_cfg.get("pick_min_score", 55))
    analyst = Analyst(ai_cfg, cfg.get("profile", {}).get("company_brief", ""), dg.get("language", "en"))
    if ai_cfg.get("enabled", True):                  # without a key the cached judgements are still applied
        section(console, "AI ANALYST")
        cands = [o for o in opps if (o.source != "portal" and ai_cfg.get("analyse_all_foundations", True))
                 or o.fit_score >= int(ai_cfg.get("min_fit_for_portal", 35))]
        cands.sort(key=lambda o: (-o.fit_score, o.id))
        analyst.analyse(cands[: int(ai_cfg.get("max_items", 300))])
        n_picks = sum(1 for o in opps if o.ai_pick)
        logger.info(f"[bold]{n_picks}[/bold] AI picks (applicable · score ≥ {ai_cfg.get('pick_min_score', 60)})")

    # --- 1d. Who can apply: alone, or only in a consortium? (text › programme rules › analyst) ---
    classify_all(opps)
    n_solo = sum(1 for o in opps if o.solo_ok and (o.interest_for or o.ai_pick))
    logger.info(f"[bold]{n_solo}[/bold] matches / AI picks can be applied for without a consortium")

    # --- 2. Diff against history ---
    section(console, "DIFF")
    hist_cfg = cfg.get("history", {})
    hist_path = hist_cfg.get("path", "outputs/history.json")
    history = prune_history(load_history(hist_path), hist_cfg.get("rolling_days", 400))
    first_run = not history.get("items")

    current = [o.model_dump(mode="json") for o in opps]
    since_last, changed_items, removed_items = diff_items(current, history)
    history = record_items(history, current)
    save_history(hist_path, history)
    # NEW = first seen within the window, so an extra run mid-week doesn't wipe the flags of Monday's arrivals
    window = int(dg.get("new_window_days", 7))
    first_seen = {e["id"]: str(e.get("first_seen", "")) for e in history["items"]}
    for o, i in zip(opps, current):                  # carry the real first sighting into the outputs
        if (fs := first_seen.get(o.id)):
            o.first_seen = datetime.fromisoformat(fs.replace("Z", "+00:00"))
            i["first_seen"] = fs
    fresh = first_seen_within(history, [o.id for o in opps], window)
    new_items = [] if first_run else [i for i in current if i["id"] in fresh]
    if first_run:
        # No baseline yet — don't flag the whole portal as "new"
        logger.info("first run: seeding history, nothing flagged as new")
    logger.info(
        f"[green]+{len(new_items)} new in {window} d[/green] ({len(since_last)} since last run) · "
        f"[yellow]~{len(changed_items)} changed[/yellow] · [red]-{len(removed_items)} removed[/red] · {len(opps)} total"
    )

    # --- 3. Render ---
    section(console, "RENDER")
    out_dir = Path(cfg.get("output", {}).get("dir", "outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)
    new_ids = {i["id"] for i in new_items}
    archive_url = cfg.get("output", {}).get("archive_url", "")

    (out_dir / "digest.json").write_text(
        json.dumps(
            {"date": today, "total": len(opps), "new": len(new_items), "changed": len(changed_items),
             "removed": len(removed_items), "items": current, "new_items": new_items, "removed_items": removed_items},
            ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md_text = render_markdown(opps, new_ids=new_ids, date=today, closing_soon_days=dg.get("closing_soon_days", 30),
                              threshold=min_score, themes=scorer.theme_meta(), lang=dg.get("language", "en"))
    (out_dir / "digest.md").write_text(md_text, encoding="utf-8")
    render_kw = dict(
        new_ids=new_ids, date=today,
        closing_soon_days=dg.get("closing_soon_days", 30),
        max_per_cluster=dg.get("max_per_cluster", 0),
        archive_url=archive_url,
        threshold=min_score,
        themes=scorer.theme_meta(),
        lang=dg.get("language", "en"),
        ai_pick_min=int(ai_cfg.get("pick_min_score", 55)),
        foundation_rows=int(dg.get("foundation_ranking_rows", 12)),
        solo_bonus=float(dg.get("solo_bonus", 12)),
        solo_rows=int(dg.get("solo_rows", 8)),
    )
    html_text = fit_email(opps, render_kw, rows=int(dg.get("max_rows_per_section", 15)),
                          per_theme=int(dg.get("max_matches_per_theme", 10)),
                          limit_kb=int(dg.get("email_max_kb", 100)))                             # email: compact
    html_full = render_html(opps, compact=False, **render_kw)      # archive: everything
    (out_dir / "digest.html").write_text(html_text, encoding="utf-8")
    (out_dir / "digest_full.html").write_text(html_full, encoding="utf-8")
    logger.info(f"email HTML {len(html_text.encode()) / 1024:.0f} KB · full HTML {len(html_full.encode()) / 1024:.0f} KB")
    logger.info(f"Outputs → {out_dir}/")

    # --- 4. Archive (GitHub Pages) ---
    if cfg.get("output", {}).get("archive", True):
        section(console, "ARCHIVE")
        build_site(html_full, today, cfg.get("output", {}).get("archive_dir", "docs"), lang=dg.get("language", "en"),
                   base_url=archive_url,
                   stats={"total": len(opps), "matches": n_match, "new": len(new_items),
                          "ai_picks": sum(1 for o in opps if o.ai_pick),
                          "solo": sum(1 for o in opps if o.solo_ok and (o.interest_for or o.ai_pick)),
                          "strong": sum(1 for o in opps if o.interest_for and o.fit_verdict == "Strong fit")})

    # --- 5. Email ---
    has_changes = bool(since_last or changed_items)
    if send_email and (has_changes or cfg.get("email", {}).get("send_on_empty", False)):
        section(console, "EMAIL")
        tr = Translator(dg.get("language", "en"))
        prefix = cfg.get("email", {}).get("subject_prefix") or tr("title")
        bits = [tr("subject_matches", n=n_match)] + ([tr("subject_new", n=len(new_items))] if new_items else [])
        subj = tr("subject", prefix=prefix, date=today, bits=" · ".join(bits))
        send_digest_email(html_text, subject=subj, text_fallback=md_text)
    elif send_email:
        logger.info("No changes — skipping email")

    # --- 6. Stats ---
    elapsed = time.monotonic() - t0
    stats = {
        "date": today, "elapsed_s": round(elapsed, 1), "total": len(opps),
        "new": len(new_items), "changed": len(changed_items), "removed": len(removed_items),
        "matches": n_match, "full_rate": n_full, "ai_picks": sum(1 for o in opps if o.ai_pick),
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
    load_dotenv()
    run_pipeline(load_config(args.config), send_email=args.send_email)


if __name__ == "__main__":
    cli()
