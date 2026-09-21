"""LLM analyst: how could *we* actually use this call?

For each candidate (roadmap matches + every foundation / national call) an OpenAI model reads
the call text against the company brief in config and returns a structured judgement. Results
are cached in outputs/ai_cache.json keyed by (id, content hash, model, prompt version), so a
weekly run only pays for calls that are new or changed. Without OPENAI_API_KEY the step is
skipped and the digest is rendered without AI blocks.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .models import Opportunity
from .util.logging import setup_logger

logger, _ = setup_logger()

PROMPT_VERSION = "4"
# USD per 1M tokens (input, output) — update if you switch models
PRICES = {"gpt-4o-mini": (0.15, 0.60), "gpt-4.1-mini": (0.40, 1.60), "gpt-4.1-nano": (0.10, 0.40), "gpt-4o": (2.50, 10.0), "gpt-4.1": (2.00, 8.00)}
USD_PER_EUR = 1.08
LANG_NAMES = {"hu": "Hungarian", "en": "English", "de": "German"}

SYSTEM = """You are a senior EU/foundation grant strategist working for a small applied-research group
building a social humanoid robot head and a social-companion AI platform. You judge funding calls
strictly and concretely: could THIS organisation realistically win THIS call, and with what project?

Calibration of ai_score (be tough — most calls are NOT for us):
  85-100  the call explicitly asks for what we build (HRI, social/humanoid robots, companion AI, expressive
          interfaces) and we could lead or be the core technology partner
  65-84   the call has an explicit technology/innovation strand where a humanoid companion is a credible,
          differentiating pilot (health, eldercare, education, veterans, space) — we would be one partner
  40-64   a stretch: thematic overlap but the call funds something else (policy studies, clinical trials,
          basic science, infrastructure); we could at most join as a small use-case partner
  0-39    not for us
applicable = true only for ai_score >= 55.
Policy-research, socio-economic, clinical-trial and pure hardware/infrastructure calls are NOT applicable
for a technology developer unless the text explicitly invites technology pilots.

Choosing the entity — apply the rules, do not default to one company:
  - foundation or national funder in Germany (DE) → PBN Germany GmbH, or the planned gGmbH if the funder requires non-profit
  - Hungarian funder (NKFIH, Széchenyi Plusz) → Pannon Business Network Association or am-LAB
  - EU Innovation Action (70% for-profit / 100% non-profit) → the Association (HU non-profit) to get 100%
  - EU RIA / CSA / Pathfinder (100% for everyone) → whichever entity holds the relevant track record
  - EIC Accelerator / equity → PBN Germany GmbH (must be a for-profit SME)
  - Nordic foundations → check whether a Danish/Swedish host institution is mandatory; say so in risks

next_step must be a concrete action tied to THIS call (a named document to read, a specific partner
type to contact, a webinar/deadline date, an eligibility question to clarify) — never a generic
"start contacting partners". Never invent facts about the call; if the text is thin, say so and lower
confidence. Answer ONLY with a JSON object matching the schema."""

SCHEMA = """{
  "applicable": true|false,           // could we credibly apply (alone or in a consortium)?
  "ai_score": 0-100,                  // overall attractiveness for us: fit x winnability x money
  "confidence": 0-100,                // how sure you are, given how much of the call text you saw
  "angle": "2-3 sentences: the concrete project idea that connects OUR roadmap (humanoid head / ETHEA companion / oncology / education / veterans / space) to THIS call",
  "entity": "which of our entities should apply and why (PBN Germany GmbH · PBN Association HU non-profit · am-LAB · at.home · planned DE gGmbH)",
  "partners": ["2-4 concrete partner types or named organisations we would need"],
  "risks": ["1-3 eligibility or competitiveness risks"],
  "next_step": "one sentence: what to do this week",
  "summary": "one plain sentence describing what the call funds"
}"""


class Analyst:
    def __init__(self, cfg: Dict[str, Any], company_brief: str, lang: str = "en"):
        self.cfg = cfg
        self.model = cfg.get("model", "gpt-4o-mini")
        self.api_key = os.environ.get(cfg.get("api_key_env", "OPENAI_API_KEY"), "")
        self.base_url = cfg.get("base_url") or "https://api.openai.com/v1"
        self.brief = company_brief.strip()
        self.lang = LANG_NAMES.get(lang, "English")
        self.max_chars = int(cfg.get("max_call_chars", 3500))
        self.cache_path = Path(cfg.get("cache", "outputs/ai_cache.json"))
        self.budget_eur = float(cfg.get("max_eur_per_run", 5.0))
        self.spent_eur = 0.0
        self.tokens_in = self.tokens_out = 0
        try:
            self.cache: Dict[str, Dict[str, Any]] = json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path.exists() else {}
        except json.JSONDecodeError:
            self.cache = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and self.cfg.get("enabled", True)

    # ------------------------------------------------------------------
    def _key(self, o: Opportunity) -> str:
        return f"{o.id}|{o.content_hash}|{self.model}|v{PROMPT_VERSION}|{self.lang}"

    def _user_prompt(self, o: Opportunity) -> str:
        meta = [
            f"Source: {'EU Funding & Tenders Portal' if o.source == 'portal' else 'foundation / national funder'}",
            f"Programme / funder: {o.programme}", f"Identifier: {o.id}", f"Title: {o.title}",
            f"Call: {o.call_title}" if o.call_title else "", f"Type of action: {o.action_type}" if o.action_type else "",
            f"Status: {o.status}", f"Deadline: {o.deadline or 'unknown'}",
            f"Grant size: up to €{o.contribution_max:,.0f}" if o.contribution_max else "Grant size: unknown",
            f"Funding rate: {o.funding_rate or 'unknown'}", f"Tags: {', '.join(o.tags[:8])}" if o.tags else "",
            f"Our keyword-fit score: {o.fit_score}/100 (theme: {o.fit_theme_label or 'none'})",
        ]
        text = (o.text or o.summary or "")[: self.max_chars]
        return (
            f"## Our organisation\n{self.brief}\n\n## The call\n" + "\n".join(m for m in meta if m)
            + f"\n\n## Call text (may be truncated)\n{text}\n\n"
            f"## Task\nJudge the call for us. Write the free-text fields (angle, entity, partners, risks, next_step, summary) in {self.lang}. "
            f"Return JSON with exactly this schema:\n{SCHEMA}"
        )

    def _call(self, client: httpx.Client, o: Opportunity) -> Optional[Dict[str, Any]]:
        body = {
            "model": self.model, "temperature": 0.2, "max_tokens": 700,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": self._user_prompt(o)}],
        }
        for attempt in range(3):
            try:
                r = client.post(f"{self.base_url}/chat/completions", json=body,
                                headers={"Authorization": f"Bearer {self.api_key}"})
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1)); continue
                r.raise_for_status()
                payload = r.json()
                self._account(payload.get("usage", {}))
                data = json.loads(payload["choices"][0]["message"]["content"])
                return self._normalise(data)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                logger.warning(f"  analyst {o.id}: {type(exc).__name__} {str(exc)[:80]}")
                time.sleep(2)
        return None

    def _account(self, usage: Dict[str, Any]) -> None:
        pin, pout = PRICES.get(self.model, (2.50, 10.0))      # unknown model → assume expensive
        ti, to = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        self.tokens_in += ti
        self.tokens_out += to
        self.spent_eur += (ti * pin + to * pout) / 1e6 / USD_PER_EUR

    def _over_budget(self) -> bool:
        return self.spent_eur >= self.budget_eur

    @staticmethod
    def _normalise(d: Dict[str, Any]) -> Dict[str, Any]:
        def num(v, lo=0, hi=100):
            try:
                return max(lo, min(hi, int(float(v))))
            except (TypeError, ValueError):
                return 0
        def lst(v):
            return [str(x) for x in v][:4] if isinstance(v, list) else ([str(v)] if v else [])
        return {
            "applicable": bool(d.get("applicable")), "ai_score": num(d.get("ai_score")), "confidence": num(d.get("confidence")),
            "angle": str(d.get("angle", ""))[:600], "entity": str(d.get("entity", ""))[:200],
            "partners": lst(d.get("partners")), "risks": lst(d.get("risks")),
            "next_step": str(d.get("next_step", ""))[:300], "summary": str(d.get("summary", ""))[:300],
        }

    # ------------------------------------------------------------------
    def analyse(self, opps: List[Opportunity]) -> int:
        """Fill o.ai for each opportunity (from cache or the model). Returns number of API calls made."""
        if not self.enabled:
            logger.info("analyst: no API key — skipped")
            return 0
        todo = [o for o in opps if self._key(o) not in self.cache]
        for o in opps:
            if (hit := self.cache.get(self._key(o))):
                o.ai = {k: v for k, v in hit.items() if k != "at"}
        logger.info(f"analyst: {len(opps)} candidates · {len(opps) - len(todo)} cached · {len(todo)} to analyse with {self.model}")
        if not todo:
            return 0
        made = 0
        workers = int(self.cfg.get("max_concurrent", 4))
        with httpx.Client(timeout=float(self.cfg.get("timeout_s", 60))) as client:
            # process in small batches so the budget check happens between batches, not after everything
            for start in range(0, len(todo), workers):
                if self._over_budget():
                    logger.warning(f"[yellow]analyst: budget of €{self.budget_eur:.2f} reached after {made} calls — stopping[/yellow]")
                    break
                batch = todo[start:start + workers]
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for o, res in zip(batch, pool.map(lambda x: self._call(client, x), batch)):
                        made += 1
                        if res:
                            o.ai = res
                            self.cache[self._key(o)] = {**res, "at": datetime.now(timezone.utc).isoformat()}
        logger.info(f"analyst: {made} calls · {self.tokens_in:,} in / {self.tokens_out:,} out tokens · "
                    f"[bold]€{self.spent_eur:.3f}[/bold] of €{self.budget_eur:.2f} budget")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        # keep the cache bounded: drop entries older than ~120 days
        cutoff = datetime.now(timezone.utc).timestamp() - 120 * 86400
        self.cache = {k: v for k, v in self.cache.items()
                      if datetime.fromisoformat(v.get("at", "2000-01-01T00:00:00+00:00")).timestamp() > cutoff}
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        return made
