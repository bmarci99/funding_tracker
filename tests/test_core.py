import json
from datetime import date

from funding_tracker.funding_rate import infer_funding_rate
from funding_tracker.ingest.ft_portal import _parse_budget
from funding_tracker.scoring import FitScorer
from funding_tracker.models import Opportunity
from funding_tracker.render.digest_html import fmt_eur, render_html

BUDGET = json.dumps({
    "budgetYearsColumns": ["2026"],
    "budgetTopicActionMap": {"1": [
        {"action": "HORIZON-X-01 - RIA", "budgetYearMap": {"2026": "10000000"}, "minContribution": 1000000,
         "maxContribution": 2000000, "expectedGrants": 3, "deadlineModel": "single-stage", "deadlineDates": ["2026-10-01"]},
        {"action": "HORIZON-X-02 - RIA", "budgetYearMap": {"2026": "10000000"}, "minContribution": 5000000,
         "maxContribution": 5000000, "expectedGrants": 1, "deadlineModel": "single-stage", "deadlineDates": ["2026-10-01"]},
    ]},
})


def test_budget_is_per_topic_not_per_call():
    b = _parse_budget(BUDGET, "HORIZON-X-01")
    assert b["call_budget"] == 10_000_000
    assert b["contribution_max"] == 2_000_000
    assert b["expected_grants"] == 3
    assert _parse_budget(BUDGET, "HORIZON-NOPE") == {}


def test_cluster_from_identifier():
    assert Opportunity(id="HORIZON-CL4-2026-01", title="t", url="u").cluster == "CL4"
    assert Opportunity(id="HORIZON-JU-CBE-2026-IA", title="t", url="u").cluster == "JU"
    assert Opportunity(id="ERC-2027-STG", title="t", url="u").cluster == "ERC"


def test_fmt_eur():
    assert fmt_eur(1_500_000) == "€1.5M"
    assert fmt_eur(200_000) == "€200k"
    assert fmt_eur(None) == "—"


def test_compact_render_caps_rows_and_marks_new():
    opps = [Opportunity(id=f"HORIZON-CL4-2026-{i:02d}", title=f"Topic {i}", url="http://x", status="Open",
                        deadline=date.today()) for i in range(5)]
    html = render_html(opps, new_ids={"HORIZON-CL4-2026-01"}, date="2026-09-21", compact=True, max_rows=2)
    assert "and 3 more" in html
    assert "NEW" in html
    assert "Cluster 4" in html


def test_funding_rate_rules_and_explicit_override():
    assert infer_funding_rate("HORIZON", "Research and Innovation Actions")[0] == "100%"
    assert infer_funding_rate("HORIZON", "Innovation Actions")[0].startswith("70%")
    assert infer_funding_rate("HORIZON", "Programme Cofund Actions", "The funding rate is up to 30% of costs")[0] == "up to 30%"
    assert infer_funding_rate("LIFE", "LIFE Project Grants")[0].startswith("60%")
    assert infer_funding_rate("XYZ", "whatever") == ("", "")


def _profile():
    return {
        "entities": {"nonprofit": True},
        "negative": ["military"],
        "negative_exempt_themes": ["veterans"],
        "themes": {
            "head": {"label": "Humanoid head", "priority": 1, "capability": True,
                     "anchor": ["humanoid", "social robot"], "core": ["gaze", "empathy", "speech interaction"], "context": ["robot"]},
            "health": {"label": "Oncology companion", "priority": 1,
                       "anchor": ["oncology", "cancer patients"], "core": ["hospital", "caregivers"], "context": ["health"]},
            "veterans": {"label": "Veterans", "priority": 3, "anchor": ["veterans"], "core": [], "context": []},
        },
    }


def _opp(**kw):
    base = dict(id="HORIZON-CL4-2026-01", title="t", url="u", action_type="Research and Innovation Actions",
                funding_rate="100%", contribution_max=1_000_000)
    base.update(kw)
    return Opportunity(**base)


def test_capability_call_scores_strong():
    sc = FitScorer(_profile())
    o = _opp(title="Expressive humanoid social robot heads", text="gaze, empathy and speech interaction for a robot")
    sc.score(o)
    assert o.fit_theme == "head" and o.fit_verdict == "Strong fit" and o.fit_score >= 70
    assert o.interest_hits[0].startswith("title:")


def test_domain_only_call_is_capped_below_good_fit():
    sc = FitScorer(_profile())
    o = _opp(title="Clinical trials for cancer patients", text="oncology hospital caregivers health")
    sc.score(o)
    assert o.fit_theme == "health" and o.fit_verdict == "Worth a look" and o.fit_score <= 49
    assert "(no robot / HRI signal)" in o.interest_hits


def test_domain_plus_capability_is_strong():
    sc = FitScorer(_profile())
    o = _opp(title="Social robot companions for cancer patients", text="oncology hospital; gaze and empathy")
    sc.score(o)
    assert o.fit_verdict == "Strong fit"


def test_context_words_alone_never_match_and_negatives_penalise():
    sc = FitScorer(_profile())
    ctx = _opp(title="Health robot", text="health robot health")
    sc.score(ctx)
    assert ctx.interest_for == [] and ctx.fit_score == 0
    mil = _opp(title="Humanoid military robots", text="humanoid")
    sc.score(mil)
    assert mil.fit_breakdown["penalty"] < 0
    vet = _opp(title="Companion robots for military veterans", text="veterans humanoid")
    sc.score(vet)
    assert vet.fit_breakdown["penalty"] == 0 or vet.fit_theme != "veterans"


def test_instrument_and_entity_rate():
    sc = FitScorer(_profile())
    erc = _opp(title="Humanoid social robot", action_type="ERC Starting Grants", funding_rate="100%")
    ria = _opp(title="Humanoid social robot", action_type="Innovation Actions", funding_rate="100% (as non-profit)")
    sc.score(erc); sc.score(ria)
    assert ria.fit_breakdown["instrument"] > erc.fit_breakdown["instrument"]
    assert infer_funding_rate("HORIZON", "Innovation Actions", "", {"nonprofit": True})[0] == "100% (as non-profit)"
    assert infer_funding_rate("HORIZON", "EIC Grants")[0] == "100%"


def test_enrich_extractors():
    from datetime import date
    from funding_tracker.ingest.enrich import extract_amount_eur, extract_deadline, main_text
    t = date(2026, 9, 21)
    assert extract_deadline("Ansøgningsfrist: 15. oktober 2026. Info meeting 1 September 2026.", t) == date(2026, 10, 15)
    assert extract_deadline("Bewerbungsschluss ist der 22.10.2026, 18:00 Uhr", t) == date(2026, 10, 22)
    assert extract_deadline("Benyújtási határidő: 2026. november 30.", t) == date(2026, 11, 30)
    assert extract_deadline("Founded in 2006, deadline passed 01.01.2025", t) is None
    assert extract_amount_eur("Grants of up to DKK 5 million per project") == 670000.0
    assert extract_amount_eur("bis zu 2,5 Mio. Euro") == 2500000.0
    html = "<html><body><nav>Home Contact</nav><main><h1>Call</h1><p>Apply now © sdecoret – stock.adobe.com Deadline 1 May 2027</p></main></body></html>"
    assert main_text(html) == "Call Apply now Deadline 1 May 2027"


def test_analyst_normalise_and_budget(monkeypatch, tmp_path):
    from funding_tracker.analyst import Analyst
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    a = Analyst({"model": "gpt-4o-mini", "max_eur_per_run": 0.0001, "cache": str(tmp_path / "c.json")}, "brief", "hu")
    n = Analyst._normalise({"applicable": "yes", "ai_score": "72.4", "confidence": 500, "partners": "ETH", "risks": None})
    assert n["applicable"] is True and n["ai_score"] == 72 and n["confidence"] == 100
    assert n["partners"] == ["ETH"] and n["risks"] == []
    a._account({"prompt_tokens": 1_000_000, "completion_tokens": 0})     # €0.14 → over the tiny budget
    assert a._over_budget() and a.spent_eur > 0.1
    o = _opp(title="Humanoid", content_hash="abc")
    assert "gpt-4o-mini" in a._key(o) and "Hungarian" == a.lang
