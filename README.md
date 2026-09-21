<h1 align="center">🇪🇺 Funding Tracker</h1>

<p align="center">
  <strong>Weekly digest of open EU calls + foundation funding, scored against your profile</strong><br/>
  <sub>Fetches · Scores · Diffs · Renders · Delivers — every Monday morning</sub>
</p>

---

## What is this?

Every Monday this pipeline pulls **open and forthcoming topics** from the
[EU Funding & Tenders Portal](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals)
(Horizon Europe, Euratom, Digital Europe, LIFE, CEF, Erasmus+, I3, CERV, SMP, Innovation Fund, EMFAF, EU agencies)
plus **~30 private foundations and national funders** (Villum, Novo Nordisk, VolkswagenStiftung, Bosch, NKFIH,
Lundbeck, Wallenberg, NRW.Bank, EFRE.NRW, KI.NRW, Gauss Centre …), scores everything against the company keyword
packs, diffs against last week, and emails a digest:

1. ⭐ **Matches your profile** — keyword-pack relevance (PBN · am-LAB · at.home · PBN Germany + humanoid / space interests)
2. ⏰ **Closing within 30 days**
3. 🆕 **New since last digest** on the EU portal
4. 🏛 **New at foundations & national funders**
5. **Per-cluster / per-programme summary** linking into the full archive page

Each row shows: title (→ source), topic ID, action type, grant size + call budget, deadline + days left,
**funding rate** (💯 badge for 100%-funded topics), status, and why it matched.

```
┌─────────────┐    ┌────────────────────┐    ┌──────────┐    ┌────────────┐    ┌───────────────────┐
│ config.yaml │ ─▶ │ INGEST             │ ─▶ │ SCORE    │ ─▶ │ DIFF       │ ─▶ │ RENDER + DELIVER  │
│ programmes  │    │ F&T portal API     │    │ keyword  │    │ vs history │    │ HTML · MD · JSON  │
│ feeds       │    │ + foundation pages │    │ packs    │    │ new/changed│    │ email · GH Pages  │
│ keywords    │    └────────────────────┘    └──────────┘    └────────────┘    └───────────────────┘
└─────────────┘
```

### Funding rate

The portal only states the rate when it deviates from the default, so `funding_rate.py` uses the explicit
statement in the call conditions when present and otherwise the standard rate per action type
(RIA / CSA / ERC / MSCA / Pathfinder = 100 %, IA = 70 % (100 % non-profit), Cofund ≈ 30 %, …).
Set `filters.only_full_rate: true` to keep only 100 %-funded topics. Rates are indicative — check the call.

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

## Tuning

Everything lives in `config.yaml`:

- `portal.framework_programmes` — which EU programmes to pull (IDs mapped in `ingest/ft_portal.py`)
- `foundations.feeds` — index pages to scrape; CSS selectors are optional, there is a generic fallback
- `relevance.companies` — keyword packs (strong 3 / medium 1.5 / soft 0.5 / negative −5, capped at 3 hits per tier);
  `relevance.demote` lists words too common in EU call texts to count as more than soft;
  `relevance.threshold` gates the ⭐ section
- `filters` — deadline horizon, hard include/exclude, `only_full_rate`

## Outputs

| File | What |
|:-----|:-----|
| `outputs/digest.html` | 📨 Email-ready digest (compact) |
| `outputs/digest_full.html` | 📄 Full listing (what goes to the archive) |
| `outputs/digest.md` | 📝 Markdown version (also the plain-text email fallback) |
| `outputs/digest.json` | 🔗 Full data incl. new/removed lists |
| `outputs/history.json` | 🗂️ Rolling history for diffing |
| `docs/` | 🌐 GitHub Pages archive + RSS |

## CI

`.github/workflows/weekly.yml` runs Monday 08:00 CET. Required repo secrets:
`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `DIGEST_TO_EMAIL`.

## Related

- [HORIZONS](https://github.com/bmarci99/HORIZONS) — the CORDIS database of *funded* projects; its humanoid / space category filters are the `relevance.interests` here.
- PBN Tender Radar — the foundation feeds and company keyword packs come from its config.
- [annoying_email_sender](https://github.com/bmarci99/annoying_email_sender) — the jobs tracker this layout is borrowed from.
