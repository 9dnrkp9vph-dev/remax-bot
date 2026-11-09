# tests/kit/test_snapshot.py — צילום הנתונים של תיק הפרזנטציה (בלי רשת)
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import kit_core as K

TODAY = dt.date.today()
FUTURE = (TODAY + dt.timedelta(days=30)).isoformat()


class FakeSB:
    def __init__(self, deals=None, settings=None):
        self.deals = deals or []
        self.settings = settings or []

    def enabled(self):
        return True

    def deal_history_all(self):
        return list(self.deals)


def make_G(buyers=None, deals=None, cfg=None, stat=None, contacts=None, roles=None, coords=None, phones=None, full=None):
    contacts = contacts if contacts is not None else [["דנה כהן", "0501111111"], ["רון לוי", "0502222222"],
                                                      ["מתאמת א", "0503333333"], ["מנהל ב", "0504444444"]]
    roles = roles if roles is not None else {"501111111": "agent", "502222222": "agent",
                                             "503333333": "agent", "504444444": "manager"}
    phones = phones if phones is not None else {"דנה כהן": ["0501111111"], "רון לוי": ["0502222222"],
                                                 "מתאמת א": ["0503333333"], "מנהל ב": ["0504444444"]}
    l9 = lambda p: "".join(ch for ch in str(p or "") if ch.isdigit())[-9:]
    nk = lambda s: "".join(str(s or "").split())
    G = {
        "_swr": lambda k, t, f: f(),
        "_sbdb": FakeSB(deals),
        "_load_config": lambda: cfg or {"v2_office": {"name": "רימקס פמילי"}},
        "_fetch_manual_buyers": lambda: list(buyers or []),
        "_bstat_current": lambda: stat or {},
        "_bcanon": lambda n: nk(n),
        "_contacts_rows": lambda: contacts,
        "_suspended_set": lambda: set(),
        "_removed_agent_keys": lambda: set(),
        "_last9": l9,
        "_name_key": nk,
        "_resolve_roles": lambda p: ("agent", roles.get(l9(p), "agent")),
        "_phones_for_name": lambda n: phones.get(n, []),
        "_coordinators_all": lambda: coords if coords is not None else {"503333333": {"name": "מתאמת א", "agents": set(), "names": set()}},
        "fetch_agents_full": lambda: full or {},
    }
    return G


def deal(date, side="מוכר", missing=None):
    return {"deal_date": date, "side": side, "missing_since": missing}


def test_office_numbers():
    deals = [deal("2020-05-01"), deal("2024-01-02", "קונה"), deal(TODAY.isoformat(), "מוכר+קונה"),
             deal("2023-01-01", "שוכר"), deal("2015-12-31"), deal(FUTURE), deal("2022-02-02", missing="2026-01-01")]
    o = K.office_numbers(make_G(deals=deals))
    assert o["deals"] == 3
    assert o["years"] == TODAY.year - 2005
    assert o["agents"] == 2          # דנה ורון — בלי המתאמת והמנהל
    assert o["office"] == "רימקס פמילי"


def _buyer(i, text, budget="2,000,000", agent="דנה כהן"):
    return {"row": i, "bid": "b%d" % i, "name": "קונה %d" % i, "phone": "05000000%02d" % i,
            "agent": agent, "search": text, "summary": "", "budget": budget}


LISTING = {"עיר / ישוב": "קרית ביאליק", "שכונה": "", "חדרים": "5", "מחיר": "1,850,000", "סוג נכס": "דירה"}


def test_buyers_match():
    buyers = [_buyer(i, "דירה 5 חדרים בקרית ביאליק") for i in range(4)]
    b = K.buyers_block(make_G(buyers=buyers), LISTING)
    assert b["mode"] == "match" and b["n"] == 4
    labels = dict((l, n) for l, n in b["lines"])
    assert labels["תקציב של 1,800,000 ומעלה"] == 4
    assert labels["מחפשים 5 חדרים ומעלה"] == 4
    assert labels["מחפשים בקרית ביאליק"] == 4
    assert all(n > 0 for _, n in b["lines"])


def test_buyers_city_mode():
    buyers = [_buyer(0, "דירה 5 חדרים בקרית ביאליק"), _buyer(1, "דירה 5 חדרים בקריית ביאליק"),
              _buyer(2, "קוטג' בקרית ביאליק", budget="500,000"),     # בעיר, לא מתאים (תקציב)
              _buyer(3, "דירה בקרית ביאליק"),                       # בהקפאה
              _buyer(4, "דירה 3 חדרים בחיפה")]
    stat = {"id:b3": "frozen"}
    b = K.buyers_block(make_G(buyers=buyers, stat=stat), LISTING)
    assert b["mode"] == "city"
    assert b["n"] == 3 and b["lines"] == [] and b["city"] == "קרית ביאליק"


def test_agent_block_empty():
    G = make_G()
    a = K.agent_block(G, "דנה כהן", "501111111")
    assert a["bio"] == "" and a["review"] is None and a["photo"] is None and a["license"] == ""
    assert a["first"] == "דנה" and a["name"] == "דנה כהן"
    assert a["site_url"].endswith("/צוות/דנה-כהן")


def test_agent_block_full():
    cfg = {"v2_office": {"name": "רימקס פמילי"}, "v2_licenses": {"501111111": "3123456"}}
    G = make_G(cfg=cfg)
    G["_sbdb"].settings = None
    rows = [{"kind": "agent", "key": "דנה כהן", "data": {"bio": "אני דנה", "shown": False}},
            {"kind": "review", "key": "r1", "data": {"agents": ["רון לוי"], "text": "משרד מעולה", "by": "יוסי", "at": "2026-01-01"}},
            {"kind": "review", "key": "r2", "data": {"agents": ["דנה כהן"], "text": "דנה מעולה", "by": "רות", "at": "2025-01-01"}}]
    a = K.agent_block(G, "דנה כהן", "501111111", settings_rows=rows)
    assert a["license"] == "3123456" and a["bio"] == "אני דנה"
    assert a["review"] == {"text": "דנה מעולה", "by": "רות"}
    assert a["site_url"] == ""        # העמוד מוסתר באתר
    a2 = K.agent_block(G, "מנהל ב", "504444444", settings_rows=rows)
    assert a2["review"] == {"text": "משרד מעולה", "by": "יוסי"}   # המלצה על המשרד (החדשה)


def test_license_fallback():
    G = make_G(full={"דנה כהן": {"name": "דנה כהן", "phone": "0501111111", "license": "777"}})
    G["_norm_name"] = lambda s: str(s).strip()
    assert K.agent_block(G, "דנה כהן", "501111111", settings_rows=[])["license"] == "777"


SRC = {"owner": "משה כהן", "phone": "0544448065", "street": "הנוטר 18", "city": "קרית ביאליק", "rooms": "5",
       "price": "1850000", "meet_at": "2026-11-11T17:00", "agent_name": "דנה כהן", "agent_phone": "0501111111"}


def test_build_snapshot():
    G = make_G(buyers=[_buyer(i, "דירה 5 חדרים בקרית ביאליק") for i in range(4)])
    s = K.build_snapshot(G, SRC)
    assert s["street"] == "הנוטר"
    assert s["owner_first"] == "משה" and s["price"] == "1,850,000"
    assert s["agent"]["name"] == "דנה כהן" and s["office"]["office"] == "רימקס פמילי"
    assert s["buyers"]["mode"] == "match"
    assert s["claims"]["g_rating"] == "4.9"
    assert s["made_at"]
    assert s["cma"] is None            # cma.py עוד לא קיים
    assert s["listing"]["sqm"] == "" and s["listing"]["ptype"] == "דירה"
    s2 = K.build_snapshot(G, dict(SRC, sqm="120", ptype="קוטג'"))
    assert s2["listing"]["sqm"] == "120" and s2["listing"]["ptype"] == "קוטג'"
    assert "18" not in s["street"]


def test_cma_hook(monkeypatch):
    import types
    mod = types.ModuleType("cma")
    seen = {}
    def cma_block(G, listing):
        seen["l"] = listing
        return {"title": "ניתוח שוק"}
    mod.cma_block = cma_block
    monkeypatch.setitem(sys.modules, "cma", mod)
    s = K.build_snapshot(make_G(), SRC)
    assert s["cma"] == {"title": "ניתוח שוק"} and seen["l"]["עיר / ישוב"] == "קרית ביאליק"
    def boom(G, listing):
        raise ValueError("x")
    mod.cma_block = boom
    assert K.build_snapshot(make_G(), SRC)["cma"] is None


def test_claims_defaults():
    d = K.KIT_DEFAULTS
    assert d["coop"] == "מעל 70% מהעסקאות שלנו נסגרות בשיתוף פעולה בין סוכני <office>"
    assert d["rank"] == "מקום 2 בעסקאות ברשת רימקס ישראל · מתחילת 2026, נכון ל-01/11/2026"
    assert d["g_rating"] == "4.9" and d["g_count"] == "118" and d["g_url"] == ""
    s = K.kit_settings({"v2_kit": {"g_url": "https://g.page/x", "rank": ""}})
    assert s["g_url"] == "https://g.page/x" and s["coop"] == d["coop"]
    assert s["rank"] == d["rank"]       # ערך ריק לא דורס את ברירת המחדל
    assert K.kit_settings({}) == d


def test_cma_gets_full_street_listing_does_not(monkeypatch):
    import types, json
    mod = types.ModuleType("cma")
    seen = {}
    mod.cma_block = lambda G, listing: seen.update(listing) or {"title": "x"}
    monkeypatch.setitem(sys.modules, "cma", mod)
    s = K.build_snapshot(make_G(), dict(SRC, street="מנחם בגין 12", nb_key="nb:77"))
    assert "רחוב" not in s["listing"] and "12" not in json.dumps(s["listing"], ensure_ascii=False)
    assert seen["רחוב"] == "מנחם בגין 12" and seen["listing_key"] == "nb:77"
    assert s["street"] == "מנחם בגין"
    s2 = K.build_snapshot(make_G(), dict(SRC, pkey="p1"))
    assert seen["listing_key"] == "p1"
    K.build_snapshot(make_G(), SRC)
    assert seen["listing_key"] == ""
