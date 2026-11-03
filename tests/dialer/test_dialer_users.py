"""[DIALER-USERS 03/11] בעל המשרד בוחר מי רואה את החייגן — לא רק מתאמות.
python3 tests/dialer/test_dialer_users.py"""
import os, sys, re, json, subprocess, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask
import dialer as D

fails = []


def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c:
        fails.append(m)


class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


PHONES = {"נוי רבן": {"0504875995"}, "אוצר בן חמו": {"0528899985"}, "דנה לוי": {"0501111111"}}


def make(sess, cfg=None, coords=None):
    D._CACHE.update(t=0, v=None)
    st = {"cfg": cfg if cfg is not None else {"nbStatus": {}}, "logs": []}

    def mutate(fn):
        fn(st["cfg"])
        return True, None
    G = AutoG(
        log=None, _web_auth=lambda: sess, _load_config=lambda: st["cfg"], _config_mutate=mutate,
        _log_activity=lambda *a: st["logs"].append(a),
        _display_name_for=lambda n, p: {"504875995": "נוי רבן", "528899985": "אוצר בן חמו"}.get(p, n),
        _canon_key=lambda n: " ".join(str(n or "").split()), _canon_agent_name=lambda n: n,
        _last9=lambda p: re.sub(r"\D", "", str(p or ""))[-9:],
        _coordinators_all=lambda: coords or {},
        _is_dev=lambda p: re.sub(r"\D", "", str(p or ""))[-9:] == "505709865",
        _phones_for_name=lambda n: PHONES.get(n, set()),
        fetch_newborn=lambda: [], fetch_sheet_rows=lambda: [], _fetch_manual_buyers=lambda: [],
        fetch_agents_phones=lambda: {"דנה לוי": "0501111111"},
        web_phone_name_map=lambda: {}, web_contacts_phone_name=lambda: {},
        _price_dropped_map=lambda: {}, _fetch_newborn_contacts=lambda: {}, _famexcl_addr_list=lambda: {})
    app = Flask(__name__)
    D.register(app, G)
    return app.test_client(), st


OWNER = {"name": "מנהל", "role": "admin", "drole": "developer", "dev": True, "phone": "505709865"}
NOY = {"name": "מנהל", "role": "admin", "drole": "manager", "phone": "504875995"}       # נכנסת כמנהלת, השם הגנרי
DANA = {"name": "דנה לוי", "role": "agent", "drole": "agent", "phone": "501111111"}

print("1. בלי בחירה — מנהלת שאינה מתאמת וסוכנת לא רואות")
c, st = make(NOY)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is False, "נוי (מנהלת) — אין גישה")
c, st = make(DANA)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is False, "דנה (סוכנת) — אין גישה")

print("2. בעל המשרד בוחר")
cfg = {"nbStatus": {}}
c, st = make(OWNER, cfg, coords={"528899985": {"name": "אוצר בן חמו", "agents": set(), "names": set()}})
g = c.get("/v2/api/dialer/users").get_json()
check(g["ok"] and g["names"] == [] and g["coords"] == ["אוצר בן חמו"], "רשימה ריקה + המתאמות שמזוהות אוטומטית")
r = c.post("/v2/api/dialer/users", json={"names": [" נוי רבן ", "דנה לוי", "נוי  רבן", "", 7]}).get_json()
check(r["ok"] and r["names"] == ["נוי רבן", "דנה לוי"], "נשמר בלי רווחים וכפילויות")
check(cfg.get("v2_dialer_users") == ["נוי רבן", "דנה לוי"], "בקונפיג: v2_dialer_users")
check(st["logs"] and "חייגן חכם" in st["logs"][-1][3], "נרשם ביומן הפעילות")

print("3. מי שנבחר — רואה; גם כשנכנס בשם הגנרי 'מנהל' (לפי הטלפון)")
c, st = make(NOY, cfg)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is True, "נוי — יש גישה")
q = c.get("/v2/api/dialer/queue").get_json()
check(q.get("allowed") is True and [a["name"] for a in q["agents"]] == ["דנה לוי"], "תור עובד, כל הסוכנים לבחירה")
c, st = make(dict(NOY, name="נוי רבן", phone="999999999"), cfg)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is True, "לפי השם — גם מטלפון אחר")
c, st = make(DANA, cfg)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is True, "דנה (סוכנת שנבחרה) — יש גישה")

print("4. הסרה")
c, st = make(OWNER, cfg)
c.post("/v2/api/dialer/users", json={"names": ["דנה לוי"]})
c, st = make(NOY, cfg)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is False, "נוי הוסרה — אין גישה")

print("5. רק בעל המשרד משנה")
c, st = make(NOY, cfg)
check(c.get("/v2/api/dialer/users").status_code == 403, "GET — 403 למי שאינו בעל המשרד")
check(c.post("/v2/api/dialer/users", json={"names": ["נוי רבן"]}).status_code == 403, "POST — 403")
check(cfg["v2_dialer_users"] == ["דנה לוי"], "לא השתנה")

print("6. מתאמת מזוהה — עדיין רואה גם בלי בחירה")
c, st = make(dict(NOY, phone="528899985"), {"nbStatus": {}},
             coords={"528899985": {"name": "אוצר בן חמו", "agents": set(), "names": set()}})
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is True, "אוצר כמתאמת — יש גישה")

print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
