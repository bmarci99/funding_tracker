<h1 align="center">🇪🇺 Horizon Funding Tracker</h1>

<p align="center">
  <strong>Weekly digest of open &amp; forthcoming Horizon Europe funding opportunities</strong><br/>
  <sub>Fetches · Diffs · Renders · Delivers — every Monday morning</sub>
</p>

---

## What is this?

Every Monday this pipeline pulls all **open and forthcoming Horizon Europe topics** from the
[EU Funding & Tenders Portal](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals),
compares them against last week, and emails a styled digest:

1. ⏰ **Closing within 30 days** — sorted by deadline, across all clusters
2. 🆕 **New since last digest** — topics that appeared on the portal this week
3. **Everything, grouped by cluster** (ERC · MSCA · Cluster 1–6 · EIC · Missions · Widening · JUs …), sorted by deadline

Each row shows: title (linked to the portal), topic ID, action type, total budget, max grant size, deadline + days left, status.

```
┌─────────────┐    ┌────────────────────┐    ┌────────────┐    ┌───────────────────┐
│ config.yaml │ ─▶ │ INGEST             │ ─▶ │ DIFF       │ ─▶ │ RENDER + DELIVER  │
│             │    │ F&T portal search  │    │ vs history │    │ HTML · MD · JSON  │
│             │    │ API (paginated)    │    │ new/changed│    │ email · GH Pages  │
└─────────────┘    └────────────────────┘    └────────────┘    └───────────────────┘
```

## Quick start

```bash
uv sync
uv run python -m funding_tracker            # fetch + render to outputs/ and docs/
open outputs/digest.html                    # preview the email

export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"   # Gmail App Password, not your login password
export GMAIL_TO="you@gmail.com"                   # optional, defaults to sender
uv run python -m funding_tracker --send-email
```

The first run seeds `outputs/history.json` and flags nothing as new. From the second run on, new topics get a 🆕 badge.

## Narrowing it down

Edit `config.yaml`:

```yaml
filters:
  deadline_within_days: 180        # only topics closing in the next 6 months
  include_keywords: ["CL4", "EIC", "MSCA"]   # matched against ID, title, action type, tags
  exclude_keywords: ["EURATOM"]
```

Add other EU programmes by listing their portal IDs under `portal.framework_programmes`
(e.g. Digital Europe `43152860`, EU4Health `43251567`).

## Outputs

| File | What |
|:-----|:-----|
| `outputs/digest.html` | 📨 Email-ready digest |
| `outputs/digest.md` | 📝 Markdown version (also the plain-text email fallback) |
| `outputs/digest.json` | 🔗 Full data incl. new/removed lists |
| `outputs/history.json` | 🗂️ Rolling history for diffing |
| `docs/` | 🌐 GitHub Pages archive + RSS |

## CI

`.github/workflows/weekly.yml` runs Monday 08:00 CET. Required repo secrets:
`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `DIGEST_TO_EMAIL`.

## Related

- [HORIZONS](https://github.com/bmarci99/HORIZONS) — the CORDIS database of *funded* projects. This repo covers the other side: calls that are still open.
- [annoying_email_sender](https://github.com/bmarci99/annoying_email_sender) — the jobs tracker this layout is borrowed from.
