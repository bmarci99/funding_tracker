---
name: feed-health
description: Check which configured funding feeds are alive, dead, or leaking junk, and repair them (directly or via the feed-doctor agent). Use when asked "are all sources working?", after a run with a funder at 0, or weekly.
---

# Feed health

```bash
uv run python -m funding_tracker.probe --all              # index pages only, ~2 min, exit 1 if any feed is dead
uv run python -m funding_tracker.probe --feed "<name>" --details 5     # one feed, deep
uv run python -m funding_tracker.probe --all --json > /tmp/health.json  # for scripts / agents
```

Read the result in three buckets:
- **Dead** (✗, error or 0 items) — page moved, bot wall, JS-rendered, broken TLS.
- **Hollow** — items > 0 but missing from `outputs/run_stats.json → per_cluster` after a run: every detail page
  was dropped for lacking funding vocabulary → the link pattern is catching navigation.
- **Noisy** — titles like "View challenge" / "Read more", or news posts → tighten `link_pattern` /
  `title_pattern`, or fix titles centrally in `ingest/enrich.py`.

For more than two sick feeds, delegate to the `feed-doctor` agent with the `--all` output pasted in.
Never delete a feed: `enabled: false` + `# YYYY-MM-DD: reason`.
