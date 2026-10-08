# Scout protocol (shared by every `scout-*` agent)

You find **funding sources** — pages that list *currently open or recurring calls* — that the tracker does
not yet scan. You do not edit the repo. You return verified candidates; `feed-engineer` adds them.

## Who we are looking for money for
Read `config.yaml → profile.company_brief` and `profile.themes` first. In one line: PBN builds an expressive
humanoid robot head / social companion (ETHEA) and applies it to oncology care, education, war veterans &
trauma, and astronaut crews. Entities: PBN Germany GmbH, PBN Association (HU non-profit), am-LAB, at.home,
a planned DE gGmbH. Money we can take: grants, prizes, challenge funding, cascade sub-grants, compute/testbed
access with a cash component. **Not**: loans, equity-only, individual PhD scholarships, procurement tenders
under €50k, calls only open to one university.

## Step 1 — know what we already scan
```bash
uv run python -m funding_tracker.probe --list
grep -n "framework_programmes" -A 16 config.yaml      # EU portal programmes already covered
```
Skip anything already listed (same host = same source unless it is a clearly separate call index).
Skip anything already on the EU Funding & Tenders portal — the portal ingester covers it.

## Step 2 — search wide, then go to the source
Use WebSearch for your beat in **English and the local language** (DE: "Ausschreibung", "Förderaufruf",
"Bekanntmachung"; HU: "pályázati felhívás"; DK: "opslag", "ansøgningsfrist"; SE: "utlysning"; FR: "appel à
projets"). Prefer the funder's own *call index page* over news articles and aggregators. For each candidate
open the page (WebFetch) and confirm:
- it lists **several calls** or a recurring call with its own page per round (not a one-off news post);
- calls have their own URLs (the tracker follows each one for text, deadline and amount);
- at least one call is open now or opens within ~6 months.

## Step 3 — find the cleanest ingestion route (best first)
1. RSS / Atom feed of calls (look for `<link rel="alternate" type="application/rss+xml">`, `/feed`, `/rss`) → `--type rss`
2. WordPress: `curl -s <site>/wp-json/wp/v2/types | head` → a post type like `call`, `grant`, `ausschreibung` → `--type wp-json --post-type <type>`
3. HTML index where each call link shares a URL shape → `--link-pattern "<regex on the href>"`
4. HTML cards → `--item-selector` / `--title-selector`
Add `--title-pattern` when the index mixes calls with news.

## Step 4 — prove it with the probe (mandatory)
```bash
uv run python -m funding_tracker.probe --url <index> --name "<Funder — what>" --country <ISO> [route flags] --details 5 --yaml
```
A candidate passes only if: items ≥ 1, `kept after detail pages` ≥ 1, titles are real call names (not
"Read more" / "View challenge" — if they are, say so: feed-engineer can fix titles), and at least one row
has a deadline or the site genuinely has rolling calls. If the probe fails but the source is valuable, report
it under **needs code** with the reason (JS-rendered, 403, PDF-only …).

## Step 5 — report (your final message, nothing else)
```
## <beat> — N verified candidates

### 1. <Funder — what> (<country>) — relevance: high|medium
why: <one line tying it to a roadmap theme; typical grant size; who can apply>
evidence: <probe summary: items / kept / sample titles with deadlines>
```yaml
- name: "…"
  country: "…"
  url: "…"
  …route keys…
  detail_pages: 12
```

## Needs code
- <Funder> <url> — <why the probe fails> — <suggested fix>

## Rejected (one line each, so nobody re-checks them)
- <Funder> — <reason>
```
Rank by expected value for PBN (fit × size × odds). Quality over count: 3 excellent sources beat 10 weak ones.
Be polite to sites: one probe per candidate, `--details 5` max.
