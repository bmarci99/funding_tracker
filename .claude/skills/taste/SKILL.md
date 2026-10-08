---
name: taste
description: House design rules for the Funding Digest (email + archive page + archive index). Load before changing render/templates/email.html, render/digest_html.py, render/site_builder.py or i18n strings — or when asked to make the digest look better, read faster, or be easier to move around in. Wins over generic design skills where they disagree.
---

# Taste — the Funding Digest

The digest is a **working tool**, not a landing page. The reader is a founder or grant manager who has two
minutes on Monday morning and wants three answers, in this order:

1. **What should we apply for — preferably without a consortium?** (the gold "apply on your own"
   shortlist first, then ⭐ matches, AI picks, foundation ranking)
2. **What is new?** (since the last digest — visibly different from everything else)
3. **What closes soon?** (deadlines ≤ 30 days)

Then, on the archive page, they want to **find anything in ten seconds**. Every design decision is judged by
how much it shortens one of those paths. Distinctiveness comes from the content — scores, deadlines, money,
the AI's concrete angle — not from decoration. (For the general anti-template stance see `frontend-design`;
`design-taste-frontend` is for marketing pages and mostly does *not* apply here.)

## Visual system (tokens live at the top of `email.html`)
- Rooted in the subject: **EU navy `#003399`** carries structure (masthead rule, section rules, title);
  **EU gold `#fecb00`** is the single bold accent and means exactly one thing — *you can apply on your own*
  (solo shortlist rule, "Apply alone" badge, the solo KPI, the latest row on the index). Spend boldness only there.
- Ink `#161a23`, slate `#5b6472` for metadata, hairline `#e3e6ec`, canvas `#f2f3f6`. No solid coloured section
  bands, no rainbow stat pills, no gradients, no shadows beyond hairlines.
- Masthead = title + one-line scope + a four-number KPI strip (matches · apply alone · new · closing soon) +
  theme legend dots + one quiet facts line. Nothing else above the first section.

## Hierarchy
- One visual idea per level: section heading (ink text on a 2 px semantic rule) → theme heading (theme-coloured
  text + dot over a hairline) → card / row. Never a fourth level of chrome.
- The score is the loudest thing on a match card; the title is the second. Metadata is quiet grey and wraps.
- Numbers line up: `font-variant-numeric: tabular-nums` on money, dates, scores.
- Deadlines are relative first ("in 12 d"), absolute second. Red only for ≤ 30 days — red means *act*.
- Colour is semantic and sparse: gold = apply alone · green = strong fit / 100 % funded · blue = good fit ·
  orange = NEW · red = closing soon · violet = AI · navy = structure. Don't introduce a colour without a meaning,
  and don't reuse one for a different meaning.
- Badges are tinted pills in sentence case without emoji; emoji appear only in section headings (one each).

## No consortium first
- `consortium.py` classifies every call: `solo` / `optional` / `required` (text › programme rules › analyst).
- Solo calls get `digest.solo_bonus` added to their rank everywhere (half for optional) and lead the digest
  in the gold shortlist with the first sentence of the analyst's *angle* (how the call connects to ETHEA — its
  "next step" is mostly boilerplate); shortlist order blends both signals (0.6 × higher + 0.4 × lower of
  fit / AI). Cards show the consortium badge; partners are not
  suggested on solo calls. The archive has an "Apply alone" chip (`?f=solo`).

## New items must be unmistakable
- New = first seen within `digest.new_window_days` (default 7), not "absent from the last run" — re-running
  the pipeline must not erase it.
- Every new row/card carries `is-new`: orange left rule + faint warm wash + the "New" badge. The wash must be
  subtle enough that a page with 30 new rows still reads calmly.
- New items sort **by fit first**, deadline second — the best new thing is the first new thing.
- The header shows how many are new; on the archive page "New only" is one click (and the `n` key).

## Moving around (archive page)
- Sticky top bar: section links with counts, a search box (`/` focuses it), filter chips
  (Apply alone · New · Matches · AI · 100 % · Closing soon). Filters combine with AND; the count of visible
  calls updates live. State goes in the query string (`?q=…&f=solo,new`) so a filtered view can be shared and
  email links can pre-filter; the hash stays free for section anchors (`…?f=new#new`).
- Clusters are `<details open>` so they collapse natively without JS. Every section has an `id` and
  `scroll-margin-top` so sticky bars don't cover headings.
- Keyboard: `/` search · `n` next new item · `Esc` clear. A back-to-top link, not a floating button.
- The page must be fully usable with JS off (everything visible, links work).
- Archive index: one row per digest with date, matches, new, and a link — the list is the navigation.
  Each digest page links back to the index and to the previous digest.

## Email constraints (non-negotiable)
- ≤ 100 KB HTML (Gmail clips at ~102 KB; clipped mail hides the bottom half). Collapse whitespace; cap rows;
  link to the archive for the rest.
- No JS, no external fonts, no background images, no `position: sticky`. CSS in `<style>` is fine for Gmail /
  Apple Mail; keep layout table-based where it already is.
- System font stack. Light background; don't depend on dark mode.

## Copy
- Sentence case, plain verbs, no hype. Hungarian and English both exist for every string (`i18n.py`).
- Titles stay in their source language; never translate or truncate a call title below ~90 characters.
- Every "… and N more" links to exactly where the rest is.

## Layout details that bit us
- Phones: grant / deadline / verdict columns hide (`hide-sm`) and a `sm-meta` line under the title carries them;
  cards show a small score next to the title (`sm-score`). Never put `nowrap` content in a < 60 px column.
- Deadlines everywhere: relative first ("in 14 d", red within `closing_soon_days`), date second — one `deadline()` macro.
- Theme headings are ink; only the dot carries the theme colour (config colours collide with semantic ones).
- Text is cut with the `clip` / `first_sentence` filters (word boundary, "…" only when cut), never `[:n]`.
- Coloured rules are `border-left`, not inset `box-shadow` (Outlook drops it). On solo rows New's orange wins.
- Section order: apply alone → matches → AI picks → foundations → new → closing soon → clusters.
- Headings are real `h2` (sections) / `h3` (themes). Archive: skip link, labelled chip group, and
  `scroll-padding-top` that follows the measured nav height.
- Muted text is never lighter than `#6b7280` (4.8:1 on white).

## Accessibility floor
Visible `:focus-visible` rings · inputs have labels (`aria-label` is fine for the search) · contrast ≥ 4.5:1 for
text (the amber wash is background only) · `prefers-reduced-motion` respected (we barely animate anyway) ·
`role="status"` / `aria-live="polite"` on the live result count.

## Before you call it done
1. Re-render from `outputs/digest.json` (see `run-digest` → *Re-render only*) and open both files.
2. `wc -c outputs/digest.html` ≤ 100 KB.
3. Run the `web-design-guidelines` checklist on what you touched.
4. Look at it at 375 px wide. Then remove one accessory.
