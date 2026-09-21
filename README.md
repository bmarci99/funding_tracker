<h1 align="center">🇪🇺 Funding Tracker</h1>

<p align="center">
  <strong>Weekly digest of open EU calls + foundation funding, scored against your profile</strong><br/>
  <sub>Fetches · Scores · Diffs · Renders · Delivers — every Monday morning</sub>
</p>

---

## What is this?

Every Monday this pipeline pulls **open and forthcoming calls** from the
[EU Funding & Tenders Portal](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals)
(Horizon Europe, Euratom, Digital Europe, LIFE, CEF, Erasmus+, I3, CERV, SMP, Innovation Fund, EMFAF, EU agencies —
topics, calls **and cascade-funding sub-grants**), plus **~35 foundations, Interreg programmes and national funders**
(Villum, Novo Nordisk, VolkswagenStiftung, Bosch, SPRIND, BMFTR, EIT Health, Interreg CE / Danube / AT–HU, NKFIH,
Széchenyi Plusz, NRW.Bank, EFRE.NRW, KI.NRW, Gauss Centre …). For those, every call found on an index page is
**followed to its own page** (`ingest/enrich.py`): the main text is kept for scoring, the deadline and the amount
are extracted (EN / DE / DK / SE / HU date and money formats), pages without any funding vocabulary are dropped,
and results are cached for 30 days in `outputs/page_cache.json`. Everything is scored against **your roadmap**,
diffed against last week, and emailed:

1. ⭐ **Matches your roadmap** — grouped by priority theme, each with a 0–100 fit score, verdict and the words that matched
2. ⏰ **Closing within 30 days**
3. 🆕 **New since last digest** on the EU portal
4. 🏛 **New at foundations & national funders**
5. **Per-cluster / per-programme summary** linking into the full archive page

### The roadmap (config.yaml → `profile.themes`)

| Priority | Theme | Axis |
|:--|:--|:--|
| P1 | Humanoid head & expressive HRI (ETHEA Face) | **capability** — what you build |
| P1 | Healthcare social companion (oncology) | domain |
| P2 | Teacher & learning companion | domain |
| P3 | Companion for war veterans & trauma | domain |
| P3 | Space crew companion | domain |

### The fit score (`scoring.py`)

| Part | Points | How |
|:--|:--|:--|
| theme | 0–60 | tiered vocabulary (anchor 4 · core 2 · context 0.75), title hits ×2, tags ×1.5; saturating; best theme + 25 % of runner-up; × priority weight |
| packs | 0–15 | the PBN / am-LAB / at.home / PBN Germany keyword packs as a secondary signal |
| instrument | 0–15 | RIA / IA / Pathfinder = full marks · CSA half · ERC & individual fellowships ≈ 0 |
| conditions | 0–10 | 100 % funding rate (+6) and grant ≥ €250k (+4) |
| penalty | ≤ 0 | defence / military / gambling (−12 each), unless the veterans theme matched |

Two rules keep it honest: a theme only fires on an **anchor** term, a core term in the title, or three core hits —
context words ("ai", "health") never make a match; and a **domain** theme that fires without any **capability**
signal from anchor/core terms (a pure clinical-trials call, a space-hardware call) is halved and capped at
*Worth a look* — it is a place to bring a robot, not a robot call. Terms of 7+ letters also match German compounds
("Robotik" → "Robotiklösungen"); the vocabulary is EN + DE + HU + DK.

Verdicts: ≥ 70 **Strong fit** · ≥ 50 **Good fit** · ≥ 35 **Worth a look**.

### Funding rate — 100 % for *your* entities

`funding_rate.py` uses the explicit rate in the call conditions when stated, otherwise the standard rate per action
type. With `profile.entities.nonprofit: true` (HU non-profit today, DE gGmbH planned) an Innovation Action's
"70 % (100 % for non-profit)" is reported as **100 % (as non-profit)**. Foundations are treated as 100 %.
`filters.only_full_rate: true` (default) drops anything with a known rate below 100 %; unknown rates are kept and shown.

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
- `profile.themes` — your roadmap vocabulary (`anchor` / `core` / `context`, `re:` prefix for regex), `capability: true`
  marks the what-you-build axis; `profile.entities` sets the effective funding rate
- `packs.companies` — the PBN keyword packs (secondary signal); `packs.demote` lists words too common in EU texts
- `digest.match_min_score` — fit needed for the ⭐ section; `digest.max_matches_per_theme` caps the email
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

`.github/workflows/weekly.yml` runs **Monday 07:30 Europe/Berlin** (two UTC crons + a local-time guard for DST).
Required repo secrets: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `DIGEST_TO_EMAIL` (comma-separated list of recipients).

## Related

- [HORIZONS](https://github.com/bmarci99/HORIZONS) — the CORDIS database of *funded* projects; its humanoid / space category filters are the `relevance.interests` here.
- PBN Tender Radar — the foundation feeds and company keyword packs come from its config.
- [annoying_email_sender](https://github.com/bmarci99/annoying_email_sender) — the jobs tracker this layout is borrowed from.
