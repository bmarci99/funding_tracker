import json
from datetime import date

from funding_tracker.funding_rate import infer_funding_rate
from funding_tracker.ingest.ft_portal import _parse_budget
from funding_tracker.interests import InterestScorer
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


def test_interest_scoring_demotes_generic_terms():
    cfg = {
        "threshold": 4.5,
        "demote": ["ecosystem", "consortium"],
        "companies": {"x": {"name": "X", "keywords": {
            "strong": ["humanoid", "ecosystem", "consortium"], "medium": ["machine learning"], "negative": ["military"]}}},
        "interests": [{"label": "Space", "pattern": "SPACE"}],
    }
    sc = InterestScorer(cfg)
    generic = Opportunity(id="HORIZON-CL6-2026-01", title="t", url="u", text="a resilient ecosystem for the consortium")
    real = Opportunity(id="HORIZON-CL4-2026-01", title="Humanoid robots", url="u", text="machine learning for humanoid platforms")
    military = Opportunity(id="EDF-2026-01", title="Humanoid robots", url="u", text="military machine learning")
    space = Opportunity(id="HORIZON-CL4-2027-SPACE-03-12", title="t", url="u")
    for o in (generic, real, military, space):
        sc.score(o)
    assert generic.interest_for == [] and generic.interest_score == 1.0
    assert real.interest_for == ["X"] and real.interest_score == 4.5
    assert military.interest_for == []
    assert "Space" in space.interest_for and space.interest_hits[0] == "★ Space"
