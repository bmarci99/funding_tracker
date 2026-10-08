---
name: run-digest
description: Run the funding digest locally (full pipeline or re-render only), open the results, and check them — without emailing anyone or committing CI state by accident. Use when asked to run, preview, test or regenerate the digest.
---

# Run the digest locally

## Full run (~5–7 min; network; uses the AI budget only for new/changed calls)
```bash
uv run pytest -q                       # first — it's offline and fast
uv run python -m funding_tracker       # NO --send-email unless the user explicitly asks to send
open outputs/digest.html               # the email
open outputs/digest_full.html          # the archive page (nav, search, filters)
```
`.env` is loaded automatically (OPENAI_API_KEY). Without a key the analyst re-applies cached judgements and
makes no API calls.

What a run changes: `outputs/history.json`, `outputs/page_cache.json`, `outputs/ai_cache.json`, `docs/*`
(CI commits these every Monday). NEW is computed from `first_seen` within `digest.new_window_days`, so extra
local runs don't wipe the NEW flags — but committing a local history.json still moves the baseline. Leave them
uncommitted unless the user asks.

## Re-render only (seconds; no network) — for template / design work
```bash
uv run python - <<'EOF'
import json, yaml
from pathlib import Path
from funding_tracker.models import Opportunity
from funding_tracker.render.digest_html import render_html
from funding_tracker.scoring import FitScorer
cfg = yaml.safe_load(open("config.yaml")); dg = cfg["digest"]
d = json.load(open("outputs/digest.json"))
opps = [Opportunity(**i) for i in d["items"]]
new_ids = {i["id"] for i in d.get("new_items", [])}
themes = FitScorer(cfg["profile"], cfg.get("packs", {})).theme_meta()
kw = dict(new_ids=new_ids, date=d["date"], themes=themes, lang=dg["language"], threshold=dg["match_min_score"],
          archive_url=cfg["output"]["archive_url"], foundation_rows=dg.get("foundation_ranking_rows", 12))
Path("outputs/digest.html").write_text(render_html(opps, compact=True, max_rows=dg["max_rows_per_section"],
                                                   max_per_theme=dg["max_matches_per_theme"], **kw))
Path("outputs/digest_full.html").write_text(render_html(opps, compact=False, **kw))
print("email", Path("outputs/digest.html").stat().st_size // 1024, "KB")
EOF
```

## After any run
Hand off to the `digest-qa` agent, or at least:
```bash
wc -c outputs/digest.html                    # ≤ 100 KB or Gmail clips it
cat outputs/run_stats.json | head -12
uv run python -m funding_tracker.probe --all | tail -1
```

## Sending
Only with explicit permission: `uv run python -m funding_tracker --send-email` (needs GMAIL_ADDRESS,
GMAIL_APP_PASSWORD, GMAIL_TO). Emails go to real recipients.
