"""Probe funding sources without running the whole pipeline.

    python -m funding_tracker.probe --list                      # configured feeds
    python -m funding_tracker.probe --all                       # health check: items per enabled feed
    python -m funding_tracker.probe --feed sprind --details 5   # one configured feed, follow 5 detail pages
    python -m funding_tracker.probe --url https://… --link-pattern "/calls/[a-z0-9-]+$" --details 5 --yaml

Detail pages are read through the page cache but the cache is never written, so probing leaves
outputs/ untouched. `--json` prints machine-readable results (used by the .claude agents).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List

import yaml

from .ingest.enrich import PageCache, enrich
from .ingest.foundations import FoundationsIngester
from .main import load_config
from .models import Opportunity
from .scoring import FitScorer


def _adhoc_feed(a: argparse.Namespace) -> Dict[str, Any]:
    feed: Dict[str, Any] = {"name": a.name or a.url, "country": a.country, "url": a.url}
    for key, val in (("type", a.type), ("link_pattern", a.link_pattern), ("item_selector", a.item_selector),
                     ("title_selector", a.title_selector), ("post_type", a.post_type), ("title_pattern", a.title_pattern)):
        if val:
            feed[key] = val
    return feed


def probe_feed(ing: FoundationsIngester, client, feed: Dict[str, Any], details: int, scorer: FitScorer | None) -> Dict[str, Any]:
    t0 = time.monotonic()
    res: Dict[str, Any] = {"name": feed["name"], "url": feed["url"], "items": 0, "kept": None, "error": "", "rows": []}
    try:
        items: List[Opportunity] = ing._fetch_feed(client, feed)
    except Exception as exc:  # noqa: BLE001 — report, don't crash the health check
        res["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        res["seconds"] = round(time.monotonic() - t0, 1)
        return res
    res["items"] = len(items)
    if details:
        cache = PageCache(ing.cfg.get("page_cache", "outputs/page_cache.json"), int(ing.cfg.get("cache_days", 30)))
        items = enrich(items[:details], client, cache, per_feed=details, delay_s=float(ing.cfg.get("request_delay_s", 1.0)))
        if feed.get("require_deadline"):             # same rule as FoundationsIngester.fetch
            items = [o for o in items if o.deadline]
        res["kept"] = len(items)                     # detail pages with funding vocabulary (and a deadline, if required)
        if scorer:
            scorer.score_all(items)
    res["rows"] = [{"title": o.title, "url": o.url, "deadline": str(o.deadline or ""),
                    "amount_eur": o.contribution_max, "fit": o.fit_score if details else None,
                    "theme": o.fit_theme_label if details else ""} for o in items]
    res["seconds"] = round(time.monotonic() - t0, 1)
    return res


def _print(res: Dict[str, Any], show_rows: bool) -> None:
    status = f"ERROR {res['error']}" if res["error"] else f"{res['items']} items" + (
        f" · {res['kept']} kept after detail pages" if res["kept"] is not None else "")
    print(f"{'✗' if res['error'] or not res['items'] else '✓'} {res['name']} — {status} ({res.get('seconds', 0)}s)")
    if show_rows:
        for r in res["rows"][:40]:
            extra = " · ".join(x for x in (r["deadline"], f"€{r['amount_eur']:,.0f}" if r["amount_eur"] else "",
                                            f"fit {r['fit']} {r['theme']}" if r["fit"] is not None else "") if x)
            print(f"    · {r['title'][:90]}" + (f"  [{extra}]" if extra else "") + f"\n      {r['url']}")


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Probe foundation / national-funder feeds")
    p.add_argument("--config", default="config.yaml")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="list configured feeds")
    g.add_argument("--all", action="store_true", help="health check every enabled feed (index pages only)")
    g.add_argument("--feed", action="append", help="configured feed(s) by case-insensitive name substring")
    g.add_argument("--url", help="ad-hoc feed: index page / API base / RSS url")
    p.add_argument("--name"); p.add_argument("--country", default="")
    p.add_argument("--type", choices=["wp-json", "rss"]); p.add_argument("--post-type")
    p.add_argument("--link-pattern"); p.add_argument("--item-selector"); p.add_argument("--title-selector")
    p.add_argument("--title-pattern")
    p.add_argument("--details", type=int, default=0, help="follow N detail pages (deadline, amount, fit score)")
    p.add_argument("--json", action="store_true"); p.add_argument("--yaml", action="store_true",
                                                                   help="print a config.yaml feed block for --url")
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    fcfg = cfg.get("foundations", {})
    feeds = fcfg.get("feeds", [])
    if a.list:
        for f in feeds:
            print(f"{'  ' if f.get('enabled', True) else '✗ '}{f['name']}  [{f.get('type', 'html')}]  {f['url']}")
        return 0

    if a.all:
        targets = [f for f in feeds if f.get("enabled", True)]
    elif a.feed:
        targets = [f for f in feeds if any(s.lower() in f["name"].lower() for s in a.feed)]
        if not targets:
            print(f"no configured feed matches {a.feed}", file=sys.stderr)
            return 2
    else:
        targets = [_adhoc_feed(a)]

    ing = FoundationsIngester(fcfg, cfg.get("http", {}))
    scorer = FitScorer(cfg.get("profile", {}), cfg.get("packs", {})) if a.details else None
    results = []
    with ing.client() as client:
        for f in targets:
            res = probe_feed(ing, client, f, a.details, scorer)
            results.append(res)
            if not a.json:
                _print(res, show_rows=not a.all)
            time.sleep(float(fcfg.get("request_delay_s", 1.0)) if a.all else 0)

    if a.json:
        print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2, default=str))
    elif a.all:
        dead = [r for r in results if r["error"] or not r["items"]]
        print(f"\n{len(results) - len(dead)}/{len(results)} feeds healthy" + (f" · dead: {', '.join(r['name'] for r in dead)}" if dead else ""))
    if a.yaml and a.url:
        feed = _adhoc_feed(a)
        if a.details:
            feed["detail_pages"] = max(a.details, 12)
        print("\n# paste under foundations.feeds:\n" + yaml.safe_dump([feed], allow_unicode=True, sort_keys=False))
    return 1 if any(r["error"] or not r["items"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
