"""UI strings for the digest. Call titles / descriptions stay in their source language."""
from __future__ import annotations

STRINGS = {
    "en": {
        "title": "Funding Digest",
        "subtitle": "Weekly digest — {date} · EU programmes incl. cascade funding + Interreg, foundations & national funders ({n} items)",
        "stat_matches": "⭐ {n} matches · {strong} strong · {good} good",
        "stat_full": "💯 {n} at 100% for your entities",
        "stat_total": "{n} EU topics", "stat_open": "{n} open", "stat_forth": "{n} forthcoming",
        "stat_new": "+{n} new this week", "stat_soon": "{n} closing ≤ {d}d",
        "sec_matches": "⭐ Matches your roadmap",
        "sec_matches_count": "{n} opportunities · fit ≥ {t} · {strong} strong · {good} good · {look} worth a look",
        "matches_in_theme": "{n} match", "matches_in_theme_pl": "{n} matches",
        "sec_soon": "⏰ Closing within {d} days", "sec_new": "🆕 New since last digest",
        "sec_found": "🏛 New at foundations & national funders", "sec_all": "All open & forthcoming topics by cluster",
        "topics": "{n} topics", "items": "{n} items",
        "more": "… and {n} more", "more_theme": "… and {n} more in this theme", "full_list": "see the full list",
        "full_list_of": "Full list of all {n} topics:",
        "col_topic": "Topic", "col_action": "Action", "col_grant": "Grant", "col_deadline": "Deadline", "col_status": "Status",
        "col_call": "Call / page", "col_funder": "Funder", "col_cluster": "Cluster", "col_open": "Open", "col_new": "New",
        "col_next": "Next deadline",
        "why": "why", "in_days": "in {d}d", "days_ago": "{d}d ago", "see_page": "see page",
        "deadline_see_page": "deadline: see page", "grant_see_page": "grant: see page", "rate_check": "rate: check",
        "call_budget": "call {b}", "per_grant": "/ grant",
        "Strong fit": "Strong fit", "Good fit": "Good fit", "Worth a look": "Worth a look",
        "NEW": "🆕 NEW", "SOON": "⏰ SOON", "OPEN": "OPEN", "FORTHCOMING": "FORTHCOMING",
        "Open": "Open", "Forthcoming": "Forthcoming",
        "bd": "theme {theme}/60 · instrument {instr}/15 · conditions {cond}/10",
        "bd_packs": " · packs {p}", "bd_penalty": " · penalty {p}",
        "no_signal": "(no robot / HRI signal)",
        "foundation_call": "foundation call", "cascade": "cascade funding",
        "footer": "Generated {date} by Funding Tracker · sources: EU Funding & Tenders Portal + {n} foundation / national funder pages · funding rates are your effective rate (non-profit entity where allowed) and indicative — check the call conditions",
        "archive": "archive",
        "subject": "{prefix} — {date} ({bits})", "subject_matches": "{n} matches", "subject_new": "+{n} new",
        "rate_nonprofit": "100% (as non-profit)", "rate_typ": "100% (typ.)", "rate_np_ia": "70% (100% for non-profit)",
        "ai_block": "🤖 AI analysis", "ai_score": "AI {n}", "ai_applicable": "applicable", "ai_not_applicable": "not for us",
        "ai_angle": "Angle", "ai_entity": "Entity", "ai_partners": "Partners", "ai_risks": "Risks", "ai_next": "Next step",
        "ai_conf": "confidence {n}%",
        "sec_ai": "🤖 AI picks among foundations & national funders",
        "sec_ai_count": "{n} calls the analyst rates as applicable (AI ≥ {t}) that the keyword score missed",
        "stat_ai": "🤖 {n} AI picks",
        "md_title": "Funding Digest — {date}",
        "md_stats": "**{portal}** EU topics · **{m}** match your profile · **{full}** 100%-funded · **{new}** new",
        "md_matches": "## ⭐ Matches your roadmap ({n})", "md_soon": "## ⏰ Closing within {d} days",
        "md_found": "## 🏛 New at foundations & national funders",
        "md_footer": "_Generated {date} by Funding Tracker · sources: EU Funding & Tenders Portal + foundation feeds_",
    },
    "hu": {
        "title": "Pályázati Hírlevél",
        "subtitle": "Heti összefoglaló — {date} · EU-programok (kaszkád-finanszírozással) + Interreg, alapítványok és nemzeti támogatók ({n} tétel)",
        "stat_matches": "⭐ {n} találat · {strong} erős · {good} jó",
        "stat_full": "💯 {n} db 100%-os finanszírozás a szervezeteiteknek",
        "stat_total": "{n} EU-témakör", "stat_open": "{n} nyitott", "stat_forth": "{n} várható",
        "stat_new": "+{n} új ezen a héten", "stat_soon": "{n} zárul ≤ {d} napon belül",
        "sec_matches": "⭐ Illeszkedik a stratégiátokhoz",
        "sec_matches_count": "{n} lehetőség · illeszkedés ≥ {t} · {strong} erős · {good} jó · {look} érdemes megnézni",
        "matches_in_theme": "{n} találat", "matches_in_theme_pl": "{n} találat",
        "sec_soon": "⏰ {d} napon belül záruló felhívások", "sec_new": "🆕 Új a legutóbbi hírlevél óta",
        "sec_found": "🏛 Új alapítványi és nemzeti felhívások", "sec_all": "Minden nyitott és várható témakör klaszterenként",
        "topics": "{n} témakör", "items": "{n} tétel",
        "more": "… és további {n}", "more_theme": "… és további {n} ebben a témában", "full_list": "teljes lista",
        "full_list_of": "Mind a(z) {n} témakör teljes listája:",
        "col_topic": "Témakör", "col_action": "Támogatási forma", "col_grant": "Támogatás", "col_deadline": "Határidő", "col_status": "Státusz",
        "col_call": "Felhívás / oldal", "col_funder": "Támogató", "col_cluster": "Klaszter", "col_open": "Nyitott", "col_new": "Új",
        "col_next": "Következő határidő",
        "why": "miért", "in_days": "{d} nap múlva", "days_ago": "{d} napja", "see_page": "lásd az oldalt",
        "deadline_see_page": "határidő: lásd az oldalt", "grant_see_page": "összeg: lásd az oldalt", "rate_check": "arány: ellenőrizd",
        "call_budget": "felhívás {b}", "per_grant": "/ projekt",
        "Strong fit": "Erős illeszkedés", "Good fit": "Jó illeszkedés", "Worth a look": "Érdemes megnézni",
        "NEW": "🆕 ÚJ", "SOON": "⏰ HAMAROSAN", "OPEN": "NYITOTT", "FORTHCOMING": "VÁRHATÓ",
        "Open": "Nyitott", "Forthcoming": "Várható",
        "bd": "téma {theme}/60 · eszköz {instr}/15 · feltételek {cond}/10",
        "bd_packs": " · kulcsszavak {p}", "bd_penalty": " · levonás {p}",
        "no_signal": "(nincs robot / HRI jel)",
        "foundation_call": "alapítványi felhívás", "cascade": "kaszkád-finanszírozás",
        "footer": "Készült {date} · Funding Tracker · források: EU Funding & Tenders Portal + {n} alapítványi / nemzeti támogatói oldal · a finanszírozási arány a ti tényleges arányotok (nonprofit szervezettel, ahol lehet) és tájékoztató jellegű — ellenőrizd a felhívás feltételeit",
        "archive": "archívum",
        "subject": "{prefix} — {date} ({bits})", "subject_matches": "{n} találat", "subject_new": "+{n} új",
        "rate_nonprofit": "100% (nonprofitként)", "rate_typ": "100% (jellemzően)", "rate_np_ia": "70% (nonprofitnak 100%)",
        "ai_block": "🤖 AI-elemzés", "ai_score": "AI {n}", "ai_applicable": "pályázható", "ai_not_applicable": "nem nekünk való",
        "ai_angle": "Kapcsolódás", "ai_entity": "Szervezet", "ai_partners": "Partnerek", "ai_risks": "Kockázatok", "ai_next": "Következő lépés",
        "ai_conf": "bizonyosság {n}%",
        "sec_ai": "🤖 AI-ajánlások az alapítványi és nemzeti felhívások közül",
        "sec_ai_count": "{n} felhívás, amelyet az elemző pályázhatónak tart (AI ≥ {t}), de a kulcsszavas pontszám kihagyott",
        "stat_ai": "🤖 {n} AI-ajánlás",
        "md_title": "Pályázati Hírlevél — {date}",
        "md_stats": "**{portal}** EU-témakör · **{m}** illeszkedik a profilhoz · **{full}** 100%-os finanszírozású · **{new}** új",
        "md_matches": "## ⭐ Illeszkedik a stratégiátokhoz ({n})", "md_soon": "## ⏰ {d} napon belül záruló felhívások",
        "md_found": "## 🏛 Új alapítványi és nemzeti felhívások",
        "md_footer": "_Készült {date} · Funding Tracker · források: EU Funding & Tenders Portal + alapítványi oldalak_",
    },
}

_RATE_KEYS = {"100% (as non-profit)": "rate_nonprofit", "100% (typ.)": "rate_typ", "70% (100% for non-profit)": "rate_np_ia"}


class Translator:
    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in STRINGS else "en"
        self.s = {**STRINGS["en"], **STRINGS[self.lang]}

    def __call__(self, key: str, **kw) -> str:
        return self.s.get(key, key).format(**kw) if kw else self.s.get(key, key)

    def rate(self, rate: str) -> str:
        return self(_RATE_KEYS[rate]) if rate in _RATE_KEYS else rate

    def theme_label(self, theme: dict) -> str:
        return theme.get(f"label_{self.lang}") or theme.get("label", theme.get("key", ""))
