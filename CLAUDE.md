# Funding Tracker (Horizons)

Weekly digest of open EU calls + foundation / national funding, scored against the PBN roadmap
(humanoid head & HRI · oncology companion · education · veterans · space crew). README.md has the
full scoring and AI-analyst story; this file is the working map.

## Pipeline (`src/funding_tracker/main.py`)
ingest → filter → fit score → AI analyst → diff vs history → render (email + archive) → `docs/` → email

| Piece | File |
|:--|:--|
| EU Funding & Tenders portal | `ingest/ft_portal.py` (programme ids in `PROGRAMME_IDS`) |
| Foundations / national funders | `ingest/foundations.py` — feed types: html (selectors or `link_pattern`), `wp-json`, `rss`; optional `title_pattern`, `require_deadline`, `max_age_days`, `timeout_s` (keys: `.claude/skills/add-feed`) |
| Detail pages (text, title, deadline, amount, closed?) | `ingest/enrich.py`, cached 30 d in `outputs/page_cache.json`; cuts "related content" teasers; ≥ €20M = programme budget |
| Fit score 0–100 | `scoring.py`, vocabulary in `config.yaml → profile.themes` |
| AI analyst | `analyst.py`, cached in `outputs/ai_cache.json`, hard € budget per run |
| Email + archive HTML | `render/digest_html.py` + `render/templates/email.html` (one template, `compact` flag) |
| Archive index / RSS | `render/site_builder.py` → `docs/` (GitHub Pages) |
| UI strings (en / hu) | `i18n.py` — every new string needs **both** languages |

## Commands
```bash
uv run pytest -q                                              # fast, offline
uv run python -m funding_tracker                              # full local run (~5–7 min), never emails without --send-email
uv run python -m funding_tracker.probe --all                  # feed health
uv run python -m funding_tracker.probe --feed <name> --details 5
uv run python -m funding_tracker.probe --url <url> [--type rss|wp-json] [--link-pattern RX] --details 5 --yaml
```
`.env` (OPENAI_API_KEY) is loaded automatically; without a key the analyst re-uses `ai_cache.json` but makes no calls.

## Rules of the house
- **Email ≤ 100 KB** (Gmail clips at ~102 KB). `main.fit_email` re-renders with fewer rows until it fits (`digest.email_max_kb`); keep new email content cheap.
- **No JS in the email.** The archive page (`compact=False`) may use small, dependency-free JS; it must work without it.
- A new feed is only added after `probe --details` shows real calls (kept ≥ 1, sensible titles, deadlines where the site has them).
- One dead site must never kill a run — ingesters catch per feed.
- CI (`.github/workflows/weekly.yml`) commits `outputs/history.json`, both caches and `docs/`. Local runs change those files too — don't commit them by accident.
- Match the existing code style: compact, comment the *why*, no new dependencies without a reason.

## Claude setup
`.claude/agents/` — specialist subagents (scouts per funding beat, feed engineer / doctor, scoring auditor,
digest designer, digest QA). `.claude/skills/` — `taste`, `expand-sources`, `add-feed`, `feed-health`, `run-digest`.
