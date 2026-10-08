---
name: expand-sources
description: Find and add new funding sources to the tracker using the specialist scout agents in parallel, then integrate the verified ones with feed-engineer. Use when asked to scan more websites / funders / opportunities, to "find more calls", or on a monthly expansion pass.
---

# Expand sources

A fan-out → verify → integrate pass. Scouts only research and probe; one engineer edits the repo, so there are
no edit conflicts.

## 1. Baseline (1 min)
```bash
uv run python -m funding_tracker.probe --list | wc -l
uv run python -m funding_tracker.probe --all > /tmp/feed_health_before.txt; tail -1 /tmp/feed_health_before.txt
```

## 2. Fan out — launch the scouts in ONE message, in parallel, in the background
| Agent | Beat |
|:--|:--|
| `scout-eu-cascade` | cascade / FSTP open calls, EIT KICs, other Interreg programmes |
| `scout-space` | ESA, national space agencies, space-health (P3 space) |
| `scout-health-care` | oncology & care funders (P1) |
| `scout-education-social` | education, veterans & trauma, social innovation (P2/P3) |
| `scout-national` | DE / HU / DK / AT public funders |
| `scout-prizes-challenges` | prizes, ARPA-style agencies, corporate grants |
| `scout-deeptech-philanthropy` | AI / robotics / HRI foundations |

Prompt each with: *"Run your beat per the scout protocol. Return at most 6 verified candidates."* Pick a subset
when the user names a focus. If the custom agent types aren't loaded in this session, use `general-purpose`
and paste the agent file's body as the prompt.

## 3. Merge
Collect the reports. Dedupe by host. Rank by relevance (high first) then by evidence (kept rows with deadlines).
Show the user a one-screen table before integrating if they asked to review; otherwise continue.

## 4. Integrate — one `feed-engineer`
Give it the merged YAML blocks plus the "Needs code" list. It probes each from config, adds the passing ones,
implements shared fixes (title-from-detail-page, new feed types) with tests.

## 5. Verify
```bash
uv run pytest -q
uv run python -m funding_tracker.probe --all | tail -1      # healthy count should go up, never down
```
Then, if the user wants the digest, follow `run-digest` and hand the result to `digest-qa`.

## Report
Sources before → after · healthy feeds before → after · table of added feeds · needs-code backlog · rejected list
(so the next pass doesn't re-check them — append it to `.claude/skills/expand-sources/references/rejected.md`).
