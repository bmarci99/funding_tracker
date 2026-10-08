from __future__ import annotations

import html as html_lib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..i18n import Translator
from ..util.logging import setup_logger

logger, _ = setup_logger()

_INDEX = """\
<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<link rel="alternate" type="application/rss+xml" title="{title}" href="feed.xml"/>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
         margin: 0; background: #f2f3f6; color: #161a23; line-height: 1.5; }}
  main {{ max-width: 780px; margin: 0 auto; padding: 28px 28px 48px; background: #fff; min-height: 100vh; }}
  .mast {{ border-top: 6px solid #003399; padding-top: 18px; }}
  h1 {{ color: #003399; font-size: 26px; line-height: 1.15; letter-spacing: -0.015em; margin: 0; }}
  .lead {{ color: #5b6472; margin: 6px 0 26px; font-size: 14px; max-width: 64ch; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }}
  th {{ text-align: right; font-size: 11px; font-weight: 600; color: #5b6472; padding: 6px 10px; border-bottom: 1px solid #cfd4dc; }}
  td {{ text-align: right; padding: 11px 10px; border-bottom: 1px solid #eef0f3; }}
  th:first-child, td:first-child {{ text-align: left; }}
  td.zero {{ color: #6b7280; }}
  tr:hover td {{ background: #fafbfc; }}
  tr.latest td {{ font-weight: 600; }}
  tr.latest td:first-child {{ box-shadow: inset 3px 0 0 #fecb00; }}
  td:first-child {{ padding-left: 12px; }} th:first-child {{ padding-left: 12px; }}
  a {{ color: #0b46c4; text-decoration: none; font-weight: 600; }}
  a:hover {{ text-decoration: underline; }}
  a:focus-visible {{ outline: 2px solid #003399; outline-offset: 2px; }}
  .pill {{ display: inline-block; margin-left: 8px; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; background: #fecb00; color: #002a80; vertical-align: 1px; }}
  .new {{ color: #c2410c; }}
  .solo {{ color: #002a80; }}
  footer {{ margin-top: 22px; font-size: 12px; color: #6b7280; }}
  @media (max-width: 560px) {{ main {{ padding: 18px 16px 40px; }} .hide-sm {{ display: none; }} }}
</style></head><body>
<main>
<div class="mast"><h1>{title}</h1>
<p class="lead">{lead}</p></div>
<table>
<thead><tr><th>{h_date}</th><th>{h_matches}</th><th>{h_solo}</th><th class="hide-sm">{h_strong}</th><th>{h_new}</th><th class="hide-sm">{h_ai}</th><th class="hide-sm">{h_total}</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<footer>{updated} · <a href="feed.xml">RSS</a></footer>
</main>
</body></html>
"""

_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Horizon Funding Digest</title>
<description>Weekly digests of open Horizon Europe topics</description>
<link>{base}/</link>
<lastBuildDate>{build_date}</lastBuildDate>
{items}
</channel></rss>
"""


def _nav_links(tr: Translator, prev: Optional[str]) -> str:
    links = [f'<a href="index.html">{tr("archive_index")}</a>']
    if prev:
        links.append(f'<a href="{prev}.html">{tr("prev_digest")}</a>')
    return " ".join(links)


def build_site(html: str, date: str, archive_dir: str, *, lang: str = "en", stats: Optional[Dict[str, Any]] = None,
               base_url: str = "") -> None:
    root = Path(archive_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / ".nojekyll").touch()          # plain static files — no Jekyll build on GitHub Pages
    tr = Translator(lang)

    # digests.json: date → headline numbers, so the index can show more than a list of dates
    manifest_path = root / "digests.json"
    try:
        manifest: Dict[str, Dict[str, Any]] = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    except json.JSONDecodeError:
        manifest = {}
    if stats:
        manifest[date] = stats
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items(), reverse=True)), indent=1), encoding="utf-8")

    older = sorted((p.stem for p in root.glob("????-??-??.html") if p.stem < date), reverse=True)
    (root / f"{date}.html").write_text(html.replace("<!--ARCHIVE_NAV-->", _nav_links(tr, older[0] if older else None)),
                                       encoding="utf-8")
    pages = sorted(root.glob("????-??-??.html"), reverse=True)

    def cell(v: Any, cls: str = "") -> str:
        classes = " ".join(c for c in (cls, "" if v else "zero") if c)
        attr = f' class="{classes}"' if classes else ""
        return f"<td{attr}>{'—' if v is None else v}</td>"

    rows = []
    for i, p in enumerate(pages[:120]):
        s = manifest.get(p.stem, {})
        latest = f'<span class="pill">{tr("idx_latest")}</span>' if i == 0 else ""
        new = cell(f"+{s['new']}", "new") if s.get("new") else cell(s.get("new"))
        rows.append(
            f'<tr{" class=latest" if i == 0 else ""}><td><a href="{p.name}">{p.stem}</a>{latest}</td>'
            + cell(s.get("matches")) + cell(s.get("solo"), "solo") + cell(s.get("strong"), "hide-sm") + new
            + cell(s.get("ai_picks"), "hide-sm") + cell(s.get("total"), "hide-sm") + "</tr>")
    (root / "index.html").write_text(
        _INDEX.format(
            lang=lang, title=html_lib.escape(tr("idx_title")), lead=html_lib.escape(tr("idx_lead")), rows="\n".join(rows),
            h_date=tr("idx_date"), h_matches=tr("idx_matches"), h_solo=tr("idx_solo"), h_strong=tr("idx_strong"), h_new=tr("idx_new"),
            h_ai=tr("idx_ai"), h_total=tr("idx_total"),
            updated=tr("idx_updated", t=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))),
        encoding="utf-8",
    )
    base = base_url.rstrip("/")
    def rfc822(stem: str) -> str:
        return datetime.strptime(stem, "%Y-%m-%d").replace(hour=7, tzinfo=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "\n".join(
        f"<item><title>Horizon Funding Digest — {p.stem}</title><link>{base}/{p.name}</link>"
        f"<guid>{base}/{p.name}</guid><pubDate>{rfc822(p.stem)}</pubDate></item>"
        for p in pages[:20]
    )
    (root / "feed.xml").write_text(
        _RSS.format(base=base, build_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"), items=items),
        encoding="utf-8",
    )
    logger.info(f"Archive → {root}/ ({len(pages)} pages)")
