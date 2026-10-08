"""Offline tests for ingest/: generic link titles are replaced by the detail page's own title."""
from datetime import datetime, timezone

import httpx

from funding_tracker.ingest.enrich import PageCache, enrich, is_generic_title, parse_page
from funding_tracker.ingest.foundations import FoundationsIngester
from funding_tracker.models import Opportunity

DETAIL = """<html><head><title>Next Frontier Robotics | SPRIND</title>
<meta property="og:title" content="Next Frontier Robotics | SPRIND"></head>
<body><header><h1>Next Frontier Robotics</h1></header><main><p>Apply by 15 December 2026. Funding up to EUR 2 million.</p></main></body></html>"""


def _client(pages: dict, hits: list) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        hits.append(str(req.url))
        body = pages.get(str(req.url))
        return httpx.Response(200, text=body) if body is not None else httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _opp(title: str, url: str) -> Opportunity:
    return Opportunity(id="found:x", title=title, url=url, source="foundation", programme="SPRIND")


def test_is_generic_title():
    for t in ("View challenge", "Read more", "Mehr erfahren", "Learn more", "Details", "tovább", "Læs mere ›",
              "läs mer", "Weiterlesen", "", "Apply"):
        assert is_generic_title(t), t
    for t in ("Next Frontier Robotics", "Villum Experiment 2027", "Recoding Medicine – Stage 2"):
        assert not is_generic_title(t), t


def test_parse_page_title_sources():
    text, title = parse_page(DETAIL)
    assert title == "Next Frontier Robotics"            # <h1> inside <header> still counts
    assert "Next Frontier" not in text and "15 December 2026" in text
    og_only = '<html><head><meta property="og:title" content="Orbital Bioworks – SPRIND"></head><body><p>x</p></body></html>'
    assert parse_page(og_only)[1] == "Orbital Bioworks"
    generic_h1 = "<html><head><title>Call for humanoid robots | Stiftung</title></head><body><h1>Read more</h1></body></html>"
    assert parse_page(generic_h1)[1] == "Call for humanoid robots"
    assert parse_page("<html><body><p>no title</p></body></html>")[1] == ""
    assert parse_page("<html><body><main><h1>Your Challenge: Next Frontier Robotics</h1></main></body></html>")[1] \
        == "Next Frontier Robotics"


def test_enrich_replaces_generic_title_and_caches_it(tmp_path):
    url = "https://www.sprind.org/en/actions/challenges/next-frontier-robotics"
    hits: list = []
    cache = PageCache(str(tmp_path / "pc.json"))
    with _client({url: DETAIL}, hits) as c:
        out = enrich([_opp("View challenge", url)], c, cache, delay_s=0)
    assert [o.title for o in out] == ["Next Frontier Robotics"]
    assert out[0].deadline is not None and cache.data[url]["title"] == "Next Frontier Robotics"
    # a specific index title is never overwritten
    with _client({url: DETAIL}, hits) as c:
        out = enrich([_opp("Robotics challenge 2026 (index title)", url)], c, cache, delay_s=0)
    assert out[0].title == "Robotics challenge 2026 (index title)" and len(hits) == 1   # served from cache


def test_enrich_legacy_cache_entries(tmp_path):
    url_generic, url_named = "https://x.org/calls/a", "https://x.org/calls/b"
    now = datetime.now(timezone.utc).isoformat()
    cache = PageCache(str(tmp_path / "pc.json"))
    legacy = {"text": "Apply by 15 December 2026", "ok": True, "fetched": now}       # no "title" key
    cache.data = {url_generic: dict(legacy), url_named: dict(legacy)}
    hits: list = []
    with _client({url_generic: DETAIL, url_named: DETAIL}, hits) as c:
        out = enrich([_opp("View challenge", url_generic), _opp("Humanoid robotics call", url_named)], c, cache, delay_s=0)
    assert hits == [url_generic]                         # only the generic one is re-fetched
    assert [o.title for o in out] == ["Next Frontier Robotics", "Humanoid robotics call"]
    assert "title" not in cache.data[url_named]          # old behaviour kept for named items


def test_link_pattern_feed_keeps_generic_links_and_prefers_real_text():
    index_url = "https://www.sprind.org/en/actions/challenges"
    index = """<html><body><main>
      <div><a href="/en/actions/challenges/next-frontier-robotics"><img src="x.png"></a>
           <a href="/en/actions/challenges/next-frontier-robotics">Next Frontier Robotics</a></div>
      <div><a href="/en/actions/challenges/orbital-bioworks">View challenge</a></div>
      <div><a href="/en/about">Read more about us</a></div></main></body></html>"""
    ing = FoundationsIngester({}, {})
    feed = {"name": "SPRIND", "url": index_url, "link_pattern": "/actions/challenges/[a-z0-9-]+$"}
    with _client({index_url: index}, []) as c:
        items = ing._fetch_feed(c, feed)
    assert {o.url.rsplit("/", 1)[-1]: o.title for o in items} == {
        "next-frontier-robotics": "Next Frontier Robotics", "orbital-bioworks": "View challenge"}
    # bare link heuristic (no link_pattern / item_selector): generic link text is navigation noise
    with _client({index_url: index.replace("View challenge", "Read more")}, []) as c:
        items = ing._fetch_feed(c, {"name": "X", "url": index_url})
    assert [o.title for o in items] == ["Next Frontier Robotics"]
    # a configured item_selector vouches for its cards, so "Read more" survives for enrich() to fix
    with _client({index_url: index.replace("View challenge", "Read more")}, []) as c:
        items = ing._fetch_feed(c, {"name": "X", "url": index_url, "item_selector": "main > div", "title_selector": "h3"})
    assert "Read more" in [o.title for o in items]


def test_card_with_past_deadline_is_skipped():
    from datetime import date
    from funding_tracker.ingest.enrich import deadline_passed
    t = date(2026, 10, 8)
    assert deadline_passed("Application deadline 03 Apr 2024 Seed Money Facility call for proposals", t)
    assert not deadline_passed("Application deadline 15 Jan 2027 Fourth call", t)
    assert not deadline_passed("Deadline 03 Apr 2024 (first round); second round closes 1 March 2027", t)
    assert not deadline_passed("Founded on 3 April 2004, we fund research", t)     # a date, but no deadline keyword
    assert is_generic_title("Learn more about this call") and is_generic_title("Zum Förderangebot Inklusion")
    assert not is_generic_title("Zur Geschichte der Menschenrechte")


def test_related_content_blocks_are_cut_also_from_cache(tmp_path):
    from funding_tracker.ingest.enrich import cut_related
    body = "Next Frontier Robotics. Apply by 15 December 2026 for funding of autonomous lab robots. " * 3
    teaser = "More about this topic Podcast: humanoid robots in elder care. More Challenges and Funken Anti-Drone"
    html = f"<html><body><main><h1>Your Challenge: Next Frontier Robotics</h1><p>{body}</p><h2>{teaser}</h2></main></body></html>"
    text, _ = parse_page(html)
    assert "humanoid" not in text and "Anti-Drone" not in text and text.endswith("autonomous lab robots.")
    assert cut_related("Related news only, nothing before it") == "Related news only, nothing before it"   # too early: keep
    de = "Aufruf zur Förderung von Pflegerobotik, Antragsfrist 1. März 2027, Förderung bis 500.000 Euro. " * 2
    assert cut_related(de + "Das könnte Sie auch interessieren: Drohnenabwehr") == de.rstrip()
    # entries cached before the cut existed are cleaned when read
    url = "https://www.sprind.org/en/actions/challenges/next-frontier-robotics"
    cache = PageCache(str(tmp_path / "pc.json"))
    cache.data = {url: {"text": body + teaser, "title": "Your Challenge: Next Frontier Robotics", "ok": True,
                        "fetched": datetime.now(timezone.utc).isoformat()}}
    with _client({}, []) as c:
        out = enrich([_opp("View challenge", url)], c, cache, delay_s=0)
    assert out[0].title == "Next Frontier Robotics" and "humanoid" not in out[0].text


# --- scout-integration fixes (2026-10-08) -------------------------------------------------------------------

def test_rss_with_junk_before_xml_declaration():
    # clustercollaboration.eu (Drupal theme debug) prints HTML comments ahead of <?xml
    url = "https://clustercollaboration.eu/taxonomy/term/3711/feed"
    body = ("\n<!-- THEME DEBUG -->\n<!-- CALL: theme_hook -->\n<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<rss version=\"2.0\"><channel><title>x</title>"
            "<item><title>Open call: robotics for care</title><link>https://clustercollaboration.eu/open-calls/robo-care</link>"
            "<description>&lt;p&gt;Deadline 1 March 2027&lt;/p&gt;</description></item></channel></rss>")
    ing = FoundationsIngester({}, {})
    with _client({url: body}, []) as c:
        items = ing._fetch_feed(c, {"name": "ECCP", "url": url, "type": "rss"})
    assert [(o.title, o.url) for o in items] == [
        ("Open call: robotics for care", "https://clustercollaboration.eu/open-calls/robo-care")]
    assert "Deadline 1 March 2027" in items[0].text


def test_quadruple_slash_hrefs_are_normalised():
    index_url = "https://www.gesundheitsindustrie-bw.de/datenbank/foerderungen"
    index = """<html><body><main>
      <div><a href="https:////www.gesundheitsindustrie-bw.de/datenbank/foerderungen/pflege-robotik-2026">Förderaufruf Pflegerobotik 2026</a></div>
      </main></body></html>"""
    ing = FoundationsIngester({}, {})
    with _client({index_url: index}, []) as c:
        items = ing._fetch_feed(c, {"name": "GIBW", "url": index_url, "link_pattern": "/foerderungen/[a-z0-9-]+$"})
    assert [o.url for o in items] == ["https://www.gesundheitsindustrie-bw.de/datenbank/foerderungen/pflege-robotik-2026"]


def test_title_prefixes_are_stripped():
    from funding_tracker.ingest.enrich import clean_title
    assert clean_title("Frist: 22. November 2026 Ideenaufruf ISS-Experimente") == "Ideenaufruf ISS-Experimente"
    assert clean_title("30.11.2026 BMFTR Richtlinie zur Förderung von Pflegeinnovationen") \
        == "BMFTR Richtlinie zur Förderung von Pflegeinnovationen"
    assert clean_title("Your Challenge: Next Frontier Robotics") == "Next Frontier Robotics"
    assert clean_title("2026-12-01 – Call for robotics pilots") == "Call for robotics pilots"
    assert clean_title("Robotics 2030 programme") == "Robotics 2030 programme"          # nothing to strip
    assert clean_title("Frist: 22. November 2026") == "22. November 2026"               # never empty
    assert clean_title("Your Challenge:") == "Your Challenge:"
    # applied at index level for every feed type
    ing = FoundationsIngester({}, {})
    assert ing._make({"name": "DLR"}, "Frist: 22. November 2026 Ideenaufruf ISS", "https://x.de/a", "").title \
        == "Ideenaufruf ISS"
    for t in ("Kurzbeschreibung Programm", "Zum Förderangebot Inklusion", "Learn more about this call"):
        assert is_generic_title(t), t


def test_closed_detail_pages_are_dropped(tmp_path):
    from datetime import date
    from funding_tracker.ingest.enrich import page_closed
    t = date(2026, 10, 8)
    assert page_closed("Förderbekanntmachung vom 3.4.2023. Die Einreichungsfrist ist abgelaufen.", t)
    assert page_closed("Bekanntmachung Interaktive Technologien 2024 — Frist abgelaufen", t)
    assert page_closed("The application period closed on 1 May 2025.", t)
    assert page_closed("A pályázati felhívás lezárult.", t)
    # a future date on the page means another round / stage is still open
    assert not page_closed("Erste Runde: Frist abgelaufen. Zweite Stufe: Einreichungsfrist 1. Juni 2027.", t)
    assert not page_closed("Apply by 15 December 2026 for funding.", t)
    url = "https://innovationsfonds.g-ba.de/foerderbekanntmachungen/foerderbekanntmachung-2023"
    page = "<html><body><main><h1>Förderbekanntmachung 2023</h1><p>Förderung neuer Versorgungsformen. " \
           "Die Einreichungsfrist ist abgelaufen.</p></main></body></html>"
    with _client({url: page}, []) as c:
        assert enrich([_opp("Förderbekanntmachung Neue Versorgungsformen 2023", url)], c,
                      PageCache(str(tmp_path / "pc.json")), delay_s=0) == []


def test_programme_totals_go_to_call_budget(tmp_path):
    from funding_tracker.ingest.enrich import extract_amount_eur
    assert extract_amount_eur("budget €314m, up to €250,000 per project") == 314e6
    assert extract_amount_eur("budget €314m, up to €250,000 per project", max_eur=20e6 - 1) == 250_000
    pages = {
        "https://x.eu/a": "<html><body><main><p>Open call, deadline 4 November 2026. Total EUR 314 million; "
                          "grants up to EUR 250,000 per project.</p></main></body></html>",
        "https://x.eu/b": "<html><body><main><p>ARIA programme, apply by 31 October 2026. £59m programme.</p></main></body></html>",
        "https://x.eu/c": "<html><body><main><p>Apply by 1 December 2026, funding up to €100.000.</p></main></body></html>",
    }
    with _client(pages, []) as c:
        out = enrich([_opp("FORTIS open call", "https://x.eu/a"), _opp("ARIA opportunity space", "https://x.eu/b"),
                      _opp("MINT-Innovationen", "https://x.eu/c")], c, PageCache(str(tmp_path / "pc.json")), delay_s=0)
    got = {o.url[-1]: (o.contribution_max, o.call_budget) for o in out}
    assert got["a"] == (250_000, 314e6)
    assert got["b"][0] is None and round(got["b"][1]) == round(59e6 * 1.17)
    assert got["c"] == (100_000, None)


def test_require_deadline_drops_undated_items_of_that_feed_only(tmp_path):
    index_url = "https://www.interaktive-technologien.de/foerderung/bekanntmachungen"
    pages = {
        index_url: """<html><body><main>
          <article><a href="/foerderung/bekanntmachungen/nlp.bot">Robotik in Gesundheitseinrichtungen (NLP.bot)</a></article>
          <article><a href="/foerderung/bekanntmachungen/pflegerobotik">Pflegerobotik und Mensch-Roboter-Interaktion</a></article>
          </main></body></html>""",
        index_url + "/nlp.bot": "<html><body><main><p>Wir fördern Projekte. Geförderte Projekte: CICERO 10/2025 - 09/2028.</p></main></body></html>",
        index_url + "/pflegerobotik": "<html><body><main><p>Förderung; Einreichungsfrist für Skizzen: 15. Januar 2027.</p></main></body></html>",
    }
    feed = {"name": "IT", "url": index_url, "link_pattern": "/foerderung/bekanntmachungen/[a-z0-9.-]+$"}
    cfg = {"feeds": [feed], "request_delay_s": 0, "page_cache": str(tmp_path / "pc.json")}
    ing = FoundationsIngester(cfg, {})
    ing.client = lambda: _client(pages, [])
    assert len(ing.fetch()) == 2
    feed["require_deadline"] = True
    assert [o.url.rsplit("/", 1)[-1] for o in ing.fetch()] == ["pflegerobotik"]


def test_wp_json_max_age_days_sends_after_filter():
    seen: list = []
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.params)
        return httpx.Response(200, json=[{"id": 1, "link": "https://esa.int/ao-2026-ohts/",
                                          "title": {"rendered": "Announcement of Opportunity (AO-2026-OHTS)"}}])
    ing = FoundationsIngester({}, {})
    feed = {"name": "ESA", "url": "https://esa.int", "type": "wp-json", "post_type": "opportunity"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert len(ing._fetch_feed(c, feed)) == 1
        ing._fetch_feed(c, {**feed, "max_age_days": 120})
    assert "after" not in seen[0] and seen[1]["after"][:2] == "20" and seen[1]["per_page"] == "100"
    from funding_tracker.ingest.enrich import FUNDING_SIGNAL
    assert FUNDING_SIGNAL.search("Announcement of Opportunity for the Orbital High-Throughput Screener")


def test_short_page_titles_and_running_call_buttons():
    # Carl-Zeiss-Stiftung: h1 "CZS Plus" is a real (short) title; "Zur laufenden Ausschreibung" is a button
    assert parse_page("<html><head><title>CZS Plus | Carl-Zeiss-Stiftung</title></head>"
                      "<body><main><h1>CZS Plus</h1></main></body></html>")[1] == "CZS Plus"
    assert parse_page("<html><body><main><h1>Menü</h1></main><h1>CZS Fokus 2027</h1></body></html>")[1] == "CZS Fokus 2027"
    assert is_generic_title("Zur laufenden Ausschreibung") and is_generic_title("Zum aktuellen Programm")
    assert not is_generic_title("Zur laufenden Forschung an Pflegerobotern im Krankenhaus")
    assert is_generic_title("CZS Plus")                     # still too short to trust as *index* link text


def test_decimal_millions_are_not_thousands_separators():
    from funding_tracker.ingest.enrich import extract_amount_eur
    assert extract_amount_eur("a total budget of €3.14 million") == 3_140_000
    assert extract_amount_eur("bis zu 2,5 Mio. EUR") == 2_500_000
    assert extract_amount_eur("up to €250.000 per project") == 250_000
    assert extract_amount_eur("indicative total budget of €3,142,746.92 , split") == 3_142_746.92
    assert extract_amount_eur("Budget: 1.250.000,50 EUR") == 1_250_000.50


def test_call_total_is_not_the_grant_size():
    from funding_tracker.ingest.enrich import extract_amount_eur
    text = ("The call has an indicative total budget of €3,142,746.92 , split as €2,065,373.46 for OC#2.1 and "
            "€1,077,373.46 for OC#2.2. Up to €250,000 per project.")
    assert extract_amount_eur(text) == 3_142_746.92
    assert extract_amount_eur(text, skip_totals=True) == 250_000
