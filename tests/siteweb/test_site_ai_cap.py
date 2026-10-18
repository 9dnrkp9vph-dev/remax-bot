"""תקרה יומית לחיפושי AI מהאתר + מונה יומי/שעתי (19/10, אייל: 'שלא יאכלו המון טוקנים').
רץ ישירות: python3 tests/siteweb/test_site_ai_cap.py (בלי pytest)."""
import os, sys, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask
import site_api

_ENV = {}


def setenv(k, v):
    _ENV.setdefault(k, os.environ.get(k))
    os.environ[k] = v


def restore_env():
    for k, v in _ENV.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _ENV.clear()


class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


CLOCK = {"t": dt.datetime(2026, 10, 19, 14, 5)}
site_api._now_il = lambda: CLOCK["t"]


def make(cfg, cached=(), picks=("a",)):
    calls, pushes, sent = [], [], []
    cache = set(cached)

    def parse(q):
        if q not in cache:                # קריאת AI אמיתית רק כשלא במטמון
            calls.append(q)
        cache.add(q)                      # כמו המטמון של 10 דק' באפי
        return {"summary_he": "דירה"}

    def cache_get(key, ttl):
        text = key[3:]
        for q in cache:
            if text in (q, "מחפש דירה " + q):
                return {"x": 1}
        return None

    def mutate(fn):
        fn(cfg)
        return True
    G = AutoG(log=None, _parse_props_query=parse, _cache_get=cache_get, _PARSE_Q_TTL=600,
              search_listings_in_sheet=lambda p: [(90, {"מספר מודעה": "a"}, 0)],
              _load_config=lambda: cfg, _config_mutate=mutate,
              send_push=lambda title, body, *to: pushes.append((title, body, to)),
              _d360_send_text=lambda to, t: (sent.append(t) or True),
              _fetch_manual_buyers=lambda: [], _buyers_write=lambda a, p: {"ok": True, "row": 5},
              fetch_agents_phones=lambda: {"אייל שמול": "0505709865"}, _last9=lambda p: str(p or "")[-9:])

    class St:
        def all(self):
            return []
    app = Flask(__name__)
    site_api.register_site(app, G, store=St())
    app.bpage_lead_pick = lambda q: (G["_parse_props_query"](q), list(picks))[1]
    app.bpage_lead_send = lambda b, k, q: {"url": "https://x/b/T", "n": len(k), "first": True}
    return app, calls, pushes, sent


def post(app, q):
    return app.test_client().post("/site/api/search", json={"key": "secret", "q": q}).get_json()


def test_cap_blocks_ai_but_cache_still_works():
    setenv("SITE_KEY", "secret"); setenv("SITE_AI_DAILY", "2")
    cfg = {}
    app, calls, pushes, _ = make(cfg)
    assert post(app, "3 חדרים בביאליק")["ok"] and post(app, "4 חדרים במוצקין")["ok"]
    r = post(app, "5 חדרים באפקה")
    assert r == {"ok": False, "reason": "daily_cap"}, r          # האתר נופל לפענוח המקומי
    assert len(calls) == 2                                       # ה-AI לא נקרא מעל התקרה
    assert post(app, "3 חדרים בביאליק")["ok"]                   # מהמטמון — לא עולה טוקנים, לא נחסם
    assert len(calls) == 2
    post(app, "6 חדרים")
    assert [p[0] for p in pushes] == ["חיפושי AI באתר — הגעתם לתקרה היומית"], pushes   # פוש אחד ביום
    assert pushes[0][2] == ()                                    # בלי יעד = בעל המשרד
    u = app.site_ai_usage()["2026-10-19"]
    assert (u["site_ai"], u["site_cache"], u["site_blocked"]) == (2, 1, 2), u
    assert u["hours"]["14"]["site_ai"] == 2
    restore_env()


def test_resets_at_israel_midnight():
    setenv("SITE_KEY", "secret"); setenv("SITE_AI_DAILY", "1")
    app, calls, _, _ = make({})
    CLOCK["t"] = dt.datetime(2026, 10, 19, 23, 50)
    assert post(app, "א ב")["ok"] and post(app, "ג ד") == {"ok": False, "reason": "daily_cap"}
    CLOCK["t"] = dt.datetime(2026, 10, 20, 0, 1)
    assert post(app, "ג ד")["ok"] and len(calls) == 2
    CLOCK["t"] = dt.datetime(2026, 10, 19, 14, 5)
    restore_env()


def test_counter_survives_restart():
    setenv("SITE_KEY", "secret"); setenv("SITE_AI_DAILY", "2")
    cfg = {}
    app, _, pushes, _ = make(cfg)
    post(app, "א ב"); post(app, "ג ד"); post(app, "ה ו")         # התקרה נחצתה → פוש + שמירה מיידית
    app.site_ai_flush()
    saved = cfg["v2_site_ai_usage"]["2026-10-19"]
    assert saved["site_ai"] == 2 and saved["site_blocked"] == 1 and saved["pushed"], saved
    app2, calls2, pushes2, _ = make(cfg)                          # שרת מאותחל
    assert post(app2, "ז ח") == {"ok": False, "reason": "daily_cap"} and not calls2
    assert not pushes2                                            # הפוש כבר יצא היום
    app2.site_ai_flush()
    assert cfg["v2_site_ai_usage"]["2026-10-19"]["site_blocked"] == 2
    restore_env()


def test_old_days_pruned():
    store = {("2026-10-%02d" % d): {"site_ai": 1} for d in range(1, 19)}
    out = site_api.ai_usage_merge(store, {"2026-10-19": {"site_ai": 3, "hours": {"09": {"site_ai": 3}}}})
    assert sorted(out)[0] == "2026-10-06" and len(out) == 14 and out["2026-10-19"]["hours"]["09"]["site_ai"] == 3
    out = site_api.ai_usage_merge(out, {"2026-10-19": {"site_ai": 2, "hours": {"09": {"site_ai": 1}}}})
    assert out["2026-10-19"]["site_ai"] == 5 and out["2026-10-19"]["hours"]["09"]["site_ai"] == 4


def test_lead_shares_cap():
    setenv("SITE_KEY", "secret"); setenv("SITE_AI_DAILY", "1"); setenv("SITE_LEAD_AGENT", "אייל שמול")
    os.environ.pop("SITE_LEADS", None)
    app, calls, pushes, sent = make({"v2_office": {"name": "רימקס פמילי"}})
    assert post(app, "א ב")["ok"]
    st = app.site_lead_inbound("972521234567", "דנה", "היי, אני מחפש/ת: 3 חדרים במוצקין", sync=True)
    assert st == "no_match" and len(calls) == 1, (st, calls)     # הליד לא קרא ל-AI מעל התקרה
    assert "ונחזור אליכם" in sent[-1]
    assert any(p[0] == "ליד מהאתר — תקרת AI יומית" for p in pushes), pushes
    u = app.site_ai_usage()["2026-10-19"]
    assert u["lead_blocked"] == 1 and u["site_ai"] == 1
    restore_env()


def test_cap_zero_means_ai_off():
    setenv("SITE_KEY", "secret"); setenv("SITE_AI_DAILY", "0")
    app, calls, _, _ = make({})
    assert post(app, "א ב") == {"ok": False, "reason": "daily_cap"} and not calls
    restore_env()


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            f(); n += 1; print("ok", k)
    print("%d passed" % n)
