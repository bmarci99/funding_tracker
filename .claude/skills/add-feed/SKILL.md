---
name: add-feed
description: Add one funding source (foundation, agency, programme, prize) to the tracker — choose the ingestion route, probe it, write the config.yaml block. Use when the user names a funder or pastes a URL to track.
---

# Add one feed

## Decision tree (stop at the first that works)
1. **RSS / Atom** — page source has `type="application/rss+xml"`, or `<site>/feed`, `/rss.xml` exists
   → `type: rss` (+ `title_pattern` if the feed mixes news and calls)
2. **WordPress** — `curl -s <site>/wp-json/wp/v2/types` lists a call-like post type
   → `type: wp-json`, `post_type: <slug>`
3. **Call links share a URL shape** — e.g. `/calls/<slug>`, `/ausschreibungen/<slug>`
   → `link_pattern: "/calls/[a-z0-9-]+/?$"` (anchored; test it against 3 real hrefs)
4. **Cards** → `item_selector` + `title_selector` (+ `link_attr` if the href lives elsewhere)
5. **JS-rendered with no API / PDF-only / login** → don't add; note it in
   `.claude/skills/expand-sources/references/rejected.md` with the reason.

## Probe (always)
```bash
uv run python -m funding_tracker.probe --url "<index>" --name "<Funder — what>" --country DE \
    [--type rss|wp-json --post-type X] [--link-pattern RX] [--title-pattern RX] --details 8 --yaml
```
A value that starts with `-` must use the `=` form: `--link-pattern="-apply"`.

Pass = items ≥ 1 · kept ≥ 1 · real call titles · deadlines where the site states them. Fit scores are a bonus
signal, not a gate — a good funder with no current robot call is still worth scanning.

## Write it
Paste the printed block into `config.yaml → foundations.feeds` under the right `# --- section ---`.
Then confirm from config:
```bash
uv run python -m funding_tracker.probe --feed "<Funder>" --details 5
uv run pytest -q
```

## Keys reference
`name` · `country` · `url` · `type` (html default | rss | wp-json) · `post_type` · `per_page` ·
`link_pattern` · `item_selector` · `title_selector` · `link_attr` · `title_pattern` · `detail_pages` ·
`funding_rate` (default "100% (typ.)") · `enabled` · `timeout_s` / `retries` (slow sites) ·
`max_age_days` (wp-json: only posts newer than N days) · `require_deadline` (drop undated items — for indexes
that keep awarded rounds online without marking them closed)
