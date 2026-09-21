from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..util.logging import setup_logger

logger, _ = setup_logger()

_INDEX = """\
<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Horizon Funding Digest — Archive</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; }}
  h1 {{ color: #003399; }} ul {{ list-style: none; padding: 0; }} li {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
  a {{ color: #0066cc; text-decoration: none; font-weight: 500; }} a:hover {{ text-decoration: underline; }}
</style></head><body>
<h1>🇪🇺 Horizon Funding Digest — Archive</h1>
<p>Weekly digests of open &amp; forthcoming Horizon Europe topics.</p>
<ul>
{entries}
</ul>
<hr/><p style="font-size:12px;color:#888;">Updated {updated} · <a href="feed.xml">RSS</a></p>
</body></html>
"""

_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Horizon Funding Digest</title>
<description>Weekly digests of open Horizon Europe topics</description>
<link>https://github.com</link>
<lastBuildDate>{build_date}</lastBuildDate>
{items}
</channel></rss>
"""


def build_site(html: str, date: str, archive_dir: str) -> None:
    root = Path(archive_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / ".nojekyll").touch()          # plain static files — no Jekyll build on GitHub Pages
    (root / f"{date}.html").write_text(html, encoding="utf-8")
    pages = sorted(root.glob("????-??-??.html"), reverse=True)

    entries = "\n".join(f'  <li><a href="{p.name}">{p.stem}</a></li>' for p in pages[:90])
    (root / "index.html").write_text(
        _INDEX.format(entries=entries, updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        encoding="utf-8",
    )
    items = "\n".join(
        f"<item><title>Horizon Funding Digest — {p.stem}</title><link>{p.name}</link><pubDate>{p.stem}</pubDate></item>"
        for p in pages[:20]
    )
    (root / "feed.xml").write_text(
        _RSS.format(build_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"), items=items),
        encoding="utf-8",
    )
    logger.info(f"Archive → {root}/ ({len(pages)} pages)")
