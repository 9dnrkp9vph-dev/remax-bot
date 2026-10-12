# tests/deals_history/test_agents_link.py — אייל 12/10: "לסוכן חי אלבז לא מופיעות שום עסקאות" + טבלת כל הסוכנים
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from flask import Flask, jsonify, request
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
key = lambda s: re.sub(r"[\s'\"׳״.\-]", "", str(s or "")).replace("וו", "ו").replace("יי", "י")
APP = ["חי חיים אלבז", "סיון בן שטרית", "משה כהן", "משה לוי", "דנה כהן"]
L = D.link_names(["חי אלבז", "סיוון בן שטרית", "משה כהן", "רוני", "משה ישראלי כהן", "יוסי לוי"], APP, key)
ck(L["חי אלבז"] == "חי חיים אלבז", L)                 # פרטי+משפחה זהים
ck(L["סיוון בן שטרית"] == "סיון בן שטרית", L)          # כתיב (וו) — אותו מפתח
ck(L["משה כהן"] == "משה כהן", L)
ck("רוני" not in L and "יוסי לוי" not in L, L)          # מילה אחת / אין משתמש — לא מחברים
ck(L.get("משה ישראלי כהן") == "משה כהן", L)
ck("משה לוי" not in D.link_names(["משה לוי"], ["משה לוי", "משה אברהם לוי"], key) or
   D.link_names(["משה לוי"], ["משה לוי", "משה אברהם לוי"], key)["משה לוי"] == "משה לוי", "exact wins over loose")
ck("משה לוי" not in D.link_names(["משה דוד לוי"], ["משה לוי", "משה אברהם לוי"], key), "ambiguous loose → none")
# עסקה משותפת: כל חבר מקושר בנפרד
rows = [dict(id="1", agent="חי אלבז + משה כהן"), dict(id="2", agent="רוני")]
lr = D.apply_links(rows, L)
ck(lr[0]["agent"] == "חי חיים אלבז + משה כהן" and lr[0]["agent_file"] == "חי אלבז + משה כהן" and lr[1]["agent"] == "רוני", lr)
ck(rows[0]["agent"] == "חי אלבז + משה כהן", "original rows untouched")

# ראוטים: חי רואה את העסקאות שלו; טבלת הסוכנים למנהלים
def row(i, agent, date, br="bialik"):
    return dict(id=i, branch=br, year=int(date[:4]), deal_date=date, street="הגפן %s" % i, city="ביאליק", side="מוכר",
                agent=agent, deal_amount=1000, commission_net=1000, paid_amount=None, reported_date=None,
                client_name="", client_phone="", collection_status="", invoice_no="", receipt_no="")
R = [row("1", "חי אלבז", "2026-03-01"), row("2", "חי אלבז + משה כהן", "2025-03-01"), row("3", "רוני", "2019-01-01", "motzkin"),
     row("4", "משה כהן", "2026-05-01")]
S = {"C": {"role": "agent", "drole": "agent", "name": "חי חיים אלבז", "phone": "1"},
     "M": {"role": "admin", "drole": "manager", "name": "מנהל", "phone": "2"}}
class SB:
    def enabled(self): return True
    def deal_history_all(self): return R
G = {"_web_auth": lambda: S.get(request.headers.get("X-Auth-Token", "")), "_canon_key": key,
     "_scope_keys_phones": lambda role, name, ph, a=None, an=None: ({key(name)}, set(), False),
     "_etag_wrap": lambda d: jsonify(d), "_canon_agent_name": lambda x: x, "_log_activity": lambda *a, **k: None,
     "_sbdb": SB(), "web_contacts_phone_name": lambda: {"1": "חי חיים אלבז", "3": "משה כהן", "4": "אלעד לוי"}}
app = Flask("l"); D._HIST_CACHE["ts"] = 0; D._LINK_CACHE["ts"] = 0; D.register(app, G, lambda h: h); c = app.test_client()
m = c.get("/v2/api/deals/history/mine", headers={"X-Auth-Token": "C"}).get_json()
ck([x["id"] for x in m["results"]] == ["1", "2"], m)
t = c.get("/v2/api/deals/history/agents", headers={"X-Auth-Token": "M"}).get_json()
byn = {a["name"]: a for a in t["agents"]}
ck(byn["חי חיים אלבז"]["n"] == 2 and byn["חי חיים אלבז"]["n_cur"] == 1 and byn["חי חיים אלבז"]["file_names"] == ["חי אלבז"], byn["חי חיים אלבז"])
ck(byn["משה כהן"]["n"] == 2 and byn["אלעד לוי"]["n"] == 0 and byn["חי חיים אלבז"]["last"] == "01/03/2026", byn)
ck([a["name"] for a in t["agents"]][0] in ("חי חיים אלבז", "משה כהן") and t["agents"][-1]["name"] == "אלעד לוי", "sorted by n desc, zeros last")
ck(t["unlinked"] == [{"name": "רוני", "n": 1, "last": "01/01/2019", "branches": ["motzkin"]}], t["unlinked"])
ck(c.get("/v2/api/deals/history/agents", headers={"X-Auth-Token": "C"}).status_code == 403, "agents table: editors only")
print("OK", n, "checks")
# אייל 12/10: וואטסאפ ללקוח מ'העסקאות שלי' — הטלפון בכרטיס של הסוכן (רק שלו), שם המשרד בתשובה
R.append(dict(row("5", "חי אלבז", "2024-02-01"), client_name="דנה לוי", client_phone="052-1234567", side="קונה"))
D._HIST_CACHE["ts"] = 0; D._LINK_CACHE["ts"] = 0
G["_load_config"] = lambda: {"v2_office": {"name": "רימקס פמילי"}}
m2 = c.get("/v2/api/deals/history/mine", headers={"X-Auth-Token": "C"}).get_json()
x5 = [x for x in m2["results"] if x["id"] == "5"][0]
ck(x5["phone"] == "0521234567" and m2["office"] == "רימקס פמילי" and [x for x in m2["results"] if x["id"] == "1"][0]["phone"] == "", (x5, m2.get("office")))
print("OK", n, "checks")
# אייל 13/10: שמות קצרים בקובץ 2026 → שם מלא, גם לשורות שכבר נשמרו (בלי ייבוא חוזר)
AM = {"bialik|ליקה": "ליקה אוברוב", "bialik|בן ובן": "בנימין אביטן + בן קדוש", "bialik|מתן": "מתן הרשקו",
      "bialik|קובי": "קובי חמו", "bialik|אבירן": ""}
rr = [dict(id="a", branch="bialik", agent="ליקה"), dict(id="b", branch="bialik", agent="בן ובן"),
      dict(id="c", branch="bialik", agent="מתן + קובי"), dict(id="d", branch="motzkin", agent="ליקה"),
      dict(id="e", branch="bialik", agent="אבירן"), dict(id="f", branch="bialik", agent="נדב רייזר")]
out = {r["id"]: r["agent"] for r in D.apply_agent_map(rr, AM)}
ck(out == {"a": "ליקה אוברוב", "b": "בנימין אביטן + בן קדוש", "c": "מתן הרשקו + קובי חמו", "d": "ליקה", "e": "אבירן", "f": "נדב רייזר"}, out)
ck(rr[0]["agent"] == "ליקה", "input untouched")
import json as _j
REAL = _j.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "tools", "deals_agent_map.json"), encoding="utf-8"))
ck(REAL.get("bialik|ליקה") == "ליקה אוברוב" and REAL.get("bialik|רוי") == "רוי אזולאי" and REAL.get("bialik|בן ובן") == "בנימין אביטן + בן קדוש"
   and REAL.get("bialik|מתן+קובי") == "מתן הרשקו + קובי חמו" and REAL.get("bialik|ירין") == "ירין לוי"
   and REAL.get("bialik|קבלי וליאור") == "מאור קבלי + ליאור גרונפינקל" and REAL.get("bialik|קובי") == "קובי חמו", "approved map entries")
print("OK", n, "checks")
