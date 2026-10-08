"""New-item highlighting, archive navigation, archive index, RSS feeds, .env loading."""
import json
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from funding_tracker.ingest.foundations import FoundationsIngester
from funding_tracker.main import load_dotenv
from funding_tracker.models import Opportunity
from funding_tracker.render.digest_html import render_html, squeeze
from funding_tracker.render.site_builder import build_site
from funding_tracker.util.history import first_seen_within


def _opps():
    today = date.today()
    return [
        Opportunity(id="HORIZON-CL4-2026-01", title="Social robots for care", url="http://a", status="Open",
                    deadline=today + timedelta(days=10), fit_score=72, fit_verdict="Strong fit", fit_theme="hri",
                    interest_for=["HRI"], funding_rate="100%"),
        Opportunity(id="HORIZON-CL4-2026-02", title="Old topic", url="http://b", status="Open",
                    deadline=today + timedelta(days=90)),
        Opportunity(id="found:abc", title="Foundation call for companions", url="http://c", source="foundation",
                    programme="Villum", country="DK", funding_rate="100% (typ.)"),
    ]


def test_new_items_are_highlighted_in_email_and_archive():
    new = {"HORIZON-CL4-2026-01", "found:abc"}
    email = render_html(_opps(), new_ids=new, date="2026-10-08", compact=True)
    full = render_html(_opps(), new_ids=new, date="2026-10-08", compact=False)
    for html in (email, full):
        assert "is-new" in html
        assert html.count("is-new") >= 2
    # the email carries no JS and no filter attributes; the archive carries both
    assert "<script" not in email and "data-f=" not in email
    assert "<script" in full and 'data-f="new match full soon"' in full
    assert 'id="q"' in full and "<!--ARCHIVE_NAV-->" in full


def test_new_items_sorted_best_fit_first():
    opps = _opps()
    opps[1].fit_score = 5
    html = render_html(opps, new_ids={o.id for o in opps}, date="2026-10-08", compact=True)
    new_sec = html[html.index('id="new"'):]
    assert new_sec.index("Social robots for care") < new_sec.index("Old topic")


def test_archive_lists_foundations_once():
    full = render_html(_opps(), date="2026-10-08", compact=False)
    assert full.count(">Foundation call for companions</a>") == 1


def test_squeeze_removes_indentation_but_keeps_word_breaks():
    assert squeeze("<p>\n      a\n   b</p>\n\n  <i>x</i>") == "<p>\na\nb</p>\n<i>x</i>"


def test_first_seen_within_window():
    now = datetime.now(timezone.utc)
    hist = {"items": [{"id": "a", "first_seen": (now - timedelta(days=2)).isoformat()},
                      {"id": "b", "first_seen": (now - timedelta(days=20)).isoformat()}]}
    assert first_seen_within(hist, ["a", "b", "c"], 7) == {"a"}


def test_build_site_index_manifest_and_prev_link(tmp_path):
    (tmp_path / "2026-10-01.html").write_text("old")
    build_site("<nav><!--ARCHIVE_NAV--></nav>", "2026-10-08", str(tmp_path), stats={"matches": 4, "new": 3, "total": 9})
    page = (tmp_path / "2026-10-08.html").read_text()
    assert 'href="2026-10-01.html"' in page and 'href="index.html"' in page
    index = (tmp_path / "index.html").read_text()
    assert "+3" in index and index.index("2026-10-08") < index.index("2026-10-01")
    assert json.loads((tmp_path / "digests.json").read_text())["2026-10-08"]["matches"] == 4


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Call: robots in classrooms</title><link>https://f.org/calls/1</link><description>&lt;p&gt;Apply by 1 Dec&lt;/p&gt;</description></item>
<item><title>Annual report 2025</title><link>https://f.org/news/2</link></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Open call: HRI</title>
<link href="/calls/hri"/><summary>Grants up to 200k</summary></entry></feed>"""


def _client(body: bytes) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=body)))


def test_rss_and_atom_feeds_with_title_pattern():
    ing = FoundationsIngester({}, {})
    items = ing._fetch_feed(_client(RSS), {"name": "F", "url": "https://f.org/feed", "type": "rss", "title_pattern": "call"})
    assert [o.title for o in items] == ["Call: robots in classrooms"]
    assert items[0].summary == "Apply by 1 Dec"
    atom = ing._fetch_feed(_client(ATOM), {"name": "F", "url": "https://f.org/feed.xml", "type": "rss"})
    assert atom[0].url == "https://f.org/calls/hri"


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nFT_TEST_A=one\nexport FT_TEST_B='two'\n")
    monkeypatch.setenv("FT_TEST_A", "already")
    monkeypatch.delenv("FT_TEST_B", raising=False)
    load_dotenv(str(env))
    assert os.environ["FT_TEST_A"] == "already" and os.environ["FT_TEST_B"] == "two"


def test_analyst_prompt_does_not_leak_the_keyword_score():
    """The model copied the keyword fit into ai_score (188 / 300 identical) — its judgement must be blind."""
    from funding_tracker.analyst import Analyst
    o = Opportunity(id="found:x", title="Call", url="http://x", fit_score=73, fit_theme_label="HRI")
    prompt = Analyst({}, "brief")._user_prompt(o)
    assert "73" not in prompt and "keyword" not in prompt.lower()


def test_fit_email_shrinks_rows_until_under_limit():
    from funding_tracker.main import fit_email
    opps = [Opportunity(id=f"HORIZON-CL4-2026-{i:03d}", title=f"Topic number {i} " * 6, url="http://x", status="Open",
                        deadline=date.today() + timedelta(days=5)) for i in range(120)]
    kw = dict(new_ids={o.id for o in opps}, date="2026-10-08")
    big = fit_email(opps, kw, rows=120, per_theme=10, limit_kb=10_000)
    small = fit_email(opps, kw, rows=120, per_theme=10, limit_kb=40)
    assert len(small.encode()) < len(big.encode()) and len(small.encode()) <= 40 * 1024


def test_analyst_caps_non_calls_and_non_tech_calls():
    from funding_tracker.analyst import Analyst
    page = Analyst._normalise({"is_open_call": False, "tech_explicit": True, "applicable": True, "ai_score": 75})
    policy = Analyst._normalise({"is_open_call": True, "tech_explicit": False, "applicable": True, "ai_score": 75})
    robot = Analyst._normalise({"is_open_call": True, "tech_explicit": True, "applicable": True, "ai_score": 81})
    assert (page["ai_score"], page["applicable"]) == (25, False)
    assert (policy["ai_score"], policy["applicable"]) == (54, False)
    assert (robot["ai_score"], robot["applicable"]) == (81, True)


def test_consortium_from_text_programme_and_ai():
    from funding_tracker.consortium import classify
    def opp(**kw):
        return Opportunity(**{"id": "found:1", "title": "Call", "url": "http://x", "source": "foundation", **kw})
    assert classify(opp(text="Funding for single applicants or consortia of up to five partners")) == "optional"
    assert classify(opp(text="Gefördert werden Einzelvorhaben von Unternehmen")) == "solo"
    assert classify(opp(text="Proposals must be submitted by a consortium of at least three entities")) == "required"
    assert classify(Opportunity(id="HORIZON-CL4-2026-01", title="t", url="u", action_type="Research and Innovation Actions")) == "required"
    assert classify(Opportunity(id="HORIZON-EIC-2026-PATHFINDERCHALLENGES-01-03", title="t", url="u", action_type="EIC Grants")) == "optional"
    assert classify(Opportunity(id="ERC-2027-STG", title="t", url="u")) == "solo"
    assert classify(opp(ai={"consortium": "solo"})) == "solo"            # analyst fills the gap for foundations
    assert classify(opp(text="Verbundprojekt", ai={"consortium": "solo"})) == "required"   # explicit text wins


def test_solo_calls_lead_the_email_and_outrank_equal_fits():
    a = Opportunity(id="HORIZON-CL4-2026-01", title="Consortium call", url="http://a", fit_score=60, fit_verdict="Good fit",
                    fit_theme="hri", interest_for=["HRI"], consortium="required")
    b = Opportunity(id="found:b", title="Solo call", url="http://b", source="foundation", programme="F", fit_score=55,
                    fit_verdict="Good fit", fit_theme="hri", interest_for=["HRI"], consortium="solo")
    html = render_html([a, b], date="2026-10-08", compact=True, themes=[{"key": "hri", "label": "HRI", "color": "#000", "priority": 1}])
    assert html.index('id="solo"') < html.index('id="matches"')
    solo_sec = html[html.index('id="solo"'):html.index('id="matches"')]
    assert "Solo call" in solo_sec and "Consortium call" not in solo_sec
    matches = html[html.index('id="matches"'):]
    assert matches.index("Solo call") < matches.index("Consortium call")      # 55 + 12 beats 60


def test_consortium_real_world_wording():
    from funding_tracker.consortium import classify
    fortis = Opportunity(id="found:f", title="FORTIS Open Call", url="u", source="foundation", text=(
        "Consortium requirements: proposals must be submitted by a multidisciplinary consortium of 3 entities minimum "
        "for Topic OC#2.1 or 2 entities minimum for Topic OC#2.2 (single-country consortia allowed)."))
    assert classify(fortis) == "required"
    booster = Opportunity(id="HORIZON-CL4-2027-04-DIGITAL-EMERGING-04", title="Apply AI booster", url="u",
                          action_type="Research and Innovation Actions",
                          text="the best developers, particularly SMEs, alone or within a team competing for the challenges")
    assert classify(booster) == "required"      # programme rule beats text about sub-grantees
    hri = Opportunity(id="HORIZON-CL4-2023-DIGITAL-EMERGING-01-02", title="Advanced human robot interaction (IA)", url="u")
    assert classify(hri) == "required"


def test_clip_cuts_at_word_boundary_only_when_needed():
    from funding_tracker.render.digest_html import clip, first_sentence
    assert clip("short text", 50) == "short text"
    assert clip("the robot head companion platform", 20) == "the robot head…"
    assert first_sentence("We integrate ETHEA. Then more.", 200) == "We integrate ETHEA."


def test_rss_has_absolute_links_and_rfc822_dates(tmp_path):
    build_site("<html></html>", "2026-10-08", str(tmp_path), base_url="https://x.github.io/ft/")
    rss = (tmp_path / "feed.xml").read_text()
    assert "<link>https://x.github.io/ft/2026-10-08.html</link>" in rss
    assert "<pubDate>Thu, 08 Oct 2026 07:00:00 +0000</pubDate>" in rss


def test_email_section_order_and_real_headings():
    opps = _opps()
    opps[0].consortium = "solo"
    html = render_html(opps, new_ids={o.id for o in opps}, date="2026-10-08", compact=True)
    assert html.index('id="solo"') < html.index('id="new"') < html.index('id="soon"')
    assert '<h2 class="section-header' in html and "<div class=\"section-header" not in html
