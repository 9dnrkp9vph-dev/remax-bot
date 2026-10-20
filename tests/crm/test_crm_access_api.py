# tests/crm/test_crm_access_api.py — הרשאות CRM מקצה לקצה (אייל 21/10): טוקן CRM מ-Google, מודולים, היקף, ייצוא, עריכה, מפתח Claude
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ.pop("CRM_ALLOW_APP_TOKEN", None)
os.environ["CRM_OWNER_EMAILS"] = "eyalshmul@gmail.com"
os.environ["CRM_AGENT_KEY"] = "test-agent-key-123"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
CFG = {"v2_crm_access": {"hodaya@gmail.com": {"name": "הודיה צרויה", "phone": "0541111111", "modules": ["meetings", "buyers"],
                                              "scope": "team", "export": False, "edit": False}}}
A._load_config = lambda: CFG
A._session_from_phone = lambda p: ({"role": "coordinator", "name": "הודיה צרויה", "agents": ["0542222222"], "agent_names": ["רפי"]}
                                   if p == "541111111" else {"role": "admin", "name": "מנהל"})
A._is_dev = lambda p: p == "505709865"
A._canon_agent_name = lambda n: n
LOG = []; A._log_activity = lambda *a: LOG.append(a)
class SB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
A._sbdb = SB()
A._nb_statuses = lambda: {"רפי::a": {"status": "meeting", "date": "2026-10-21T10:00", "agent": "רפי", "by": "הודיה צרויה", "pkey": "a"},
                          "דנה::b": {"status": "meeting", "date": "2026-10-21T11:00", "agent": "דנה", "by": "דנה", "pkey": "b"}}
c = A.app.test_client()
OWN = {"X-Auth-Token": A._mint_crm_token("0505709865", "eyalshmul@gmail.com")}
HOD = {"X-Auth-Token": A._mint_crm_token("0541111111", "hodaya@gmail.com")}
APP = {"X-Auth-Token": A._mint_token("0505709865")}
# בלי טוקן CRM — גם לבעל המשרד עם טוקן האפליקציה
r = c.get("/v2/api/crm/meetings/meta", headers=APP)
ck(r.status_code == 401 and r.get_json()["reason"] == "login", ("app token → log in with Google", r.status_code))
# בעל המשרד
m = c.get("/v2/api/crm/meetings/meta", headers=OWN).get_json()
ck(m["ok"] and m["counts"]["all"] == 2 and m["me"]["owner"] and m["me"]["access"] and m["me"]["dashboard"], m.get("me"))
ck(len(m["modules"]) == len(A.effie_v2.CRM_MODULES) if hasattr(A, "effie_v2") else len(m["modules"]) >= 10, len(m["modules"]))
# הודיה — מתאמת, היקף צוות, פגישות + קונים, בלי ייצוא ובלי עריכה
m = c.get("/v2/api/crm/meetings/meta", headers=HOD).get_json()
ck(m["ok"] and m["counts"]["all"] == 1 and m["agents"] == ["רפי"], ("only her team's meetings", m.get("counts"), m.get("agents")))
ck([x[0] for x in m["modules"]] == ["buyers", "meetings"] and not m["me"]["owner"] and not m["me"]["export"] and not m["me"]["dashboard"], m["modules"])
l = c.get("/v2/api/crm/meetings/list", headers=HOD).get_json()
ck(l["total"] == 1 and l["rows"][0]["agent"] == "רפי", l)
ck(c.get("/v2/api/crm/meetings/record?key=m:דנה::b", headers=HOD).status_code == 404, "another agent's record is not found")
ck(c.get("/v2/api/crm/calls/meta", headers=HOD).status_code == 403, "module not allowed")
ck(c.get("/v2/api/crm/meetings/export", headers=HOD).status_code == 403, "no export permission")
ck(c.post("/v2/api/crm/buyers/record", headers=HOD, json={"fields": {"name": "x"}}).status_code == 403, "no edit permission")
ck(c.get("/v2/api/crm/dashboard", headers=HOD).status_code == 403, "dashboard not allowed")
ck(c.get("/v2/api/crm/team/status", headers=HOD).status_code == 403, "team tools owner only")
# מפתח Claude — קריאה בלבד
K = {"X-CRM-Key": "test-agent-key-123"}
ck(c.get("/v2/api/crm/meetings/meta", headers=K).get_json()["counts"]["all"] == 2, "agent key reads like the owner")
ck(c.post("/v2/api/crm/buyers/record", headers=K, json={"fields": {"name": "x"}}).status_code in (401, 403), "agent key cannot write")
ck(c.get("/v2/api/crm/meetings/meta", headers={"X-CRM-Key": "wrong"}).status_code == 401, "wrong key")
ck(any("Claude — קריאת CRM" in str(x) for x in LOG), "agent reads are logged")
print("crm_access_api OK", n)
# ── מסך ההרשאות ──
A._contacts_rows = lambda: [["הודיה צרויה", "0541111111"], ["רפי", "0542222222"]]
A._gauth_all = lambda: {}
SAVED = {}
def mut(fn):
    fn(CFG); SAVED.update(CFG); return True, None
A._config_mutate = mut
ck(c.get("/v2/api/crm/access", headers=HOD).status_code == 403, "access screen: owner only")
g = c.get("/v2/api/crm/access", headers=OWN).get_json()
ck(g["ok"] and [p["name"] for p in g["people"]][0] == "הודיה צרויה" and ["dashboard", "לוח בקרה"] in g["modules"], g)
r = c.post("/v2/api/crm/access", headers=OWN, json={"email": "rafi@gmail.com", "name": "רפי", "phone": "0542222222",
                                                  "modules": ["calls", "deals"], "scope": "own", "export": True})
ck(r.get_json()["ok"] and CFG["v2_crm_access"]["rafi@gmail.com"]["modules"] == ["calls", "deals"], CFG["v2_crm_access"].get("rafi@gmail.com"))
ck(c.post("/v2/api/crm/access", headers=OWN, json={"email": "eyalshmul@gmail.com", "modules": ["calls"]}).status_code == 400, "owner email cannot be limited")
ck(c.post("/v2/api/crm/access", headers=K, json={"email": "x@y.co", "modules": ["calls"]}).status_code in (401, 403), "agent key cannot change permissions")
ck(c.post("/v2/api/crm/access", headers=OWN, json={"email": "rafi@gmail.com", "delete": True}).get_json()["ok"] and "rafi@gmail.com" not in CFG["v2_crm_access"], "remove")
ck(any("CRM — הרשאות" in str(x) for x in LOG), "permission changes logged")
ck(c.get("/v2/crm/access").status_code == 200 and "crmTok" in c.get("/v2/crm/access").get_data(as_text=True), "page")
# ── תיקוני הביקורת ──
CFG["v2_crm_access"]["helper@gmail.com"] = {"name": "עוזר", "phone": "0505709865", "modules": ["calls"], "scope": "own"}
HLP = {"X-Auth-Token": A._mint_crm_token("0505709865", "helper@gmail.com")}
m = c.get("/v2/api/crm/calls/meta", headers=HLP)
ck(m.status_code in (200, 500) and not (m.get_json() or {}).get("me", {}).get("owner"), ("a record phone of the owner does not make you owner", m.get_json()))
ck(c.get("/v2/api/crm/access", headers=HLP).status_code == 403, "and no permissions screen")
ck(c.post("/v2/api/crm/access", headers=OWN, json={"email": "x@gmail.com", "phone": "0505709865", "modules": ["calls"]}).get_json().get("reason") == "dev_phone",
   "cannot save a record with the owner's phone")
CFG["v2_crm_access"]["hodaya@gmail.com"].update(edit=True, modules=["meetings", "buyers"])
A._buyers_write = lambda action, p: (WR.append((action, dict(p))) or {"ok": True})
WR = []
A._fetch_manual_buyers = lambda: [{"row": 5, "name": "קונה של רפי", "agent": "רפי"}, {"row": 6, "name": "קונה של דנה", "agent": "דנה"}]
r = c.post("/v2/api/crm/buyers/record", headers=HOD, json={"fields": {"name": "חדש", "agent": "דנה"}})
ck(r.status_code == 403 and not WR, ("cannot create a buyer for an agent outside the team", r.get_json()))
r = c.post("/v2/api/crm/buyers/record", headers=HOD, json={"key": "b:5", "fields": {"agent": "דנה"}})
ck(r.status_code == 403 and not WR, ("cannot move a buyer to an agent outside the team", r.get_json()))
A._cache_clear("crmbuyers")
SHIFT = [{"row": 5, "name": "קונה של רפי", "agent": "רפי"}]
A._fetch_manual_buyers = lambda: SHIFT
c.get("/v2/api/crm/buyers/list", headers=HOD)                     # מטמון: b:5 = של רפי
SHIFT[:] = [{"row": 5, "name": "קונה של דנה", "agent": "דנה"}]     # אחרי מחיקה במקום אחר — שורה 5 של דנה
r = c.post("/v2/api/crm/buyers/record", headers=HOD, json={"key": "b:5", "delete": True})
ck(r.status_code == 403 and not WR, ("stale row key does not delete another agent's buyer", r.get_json()))
A._is_suspended = lambda p: p == "541111111"
ck(c.get("/v2/api/crm/meetings/meta", headers=HOD).status_code in (401, 403), "suspended user loses CRM access")
A._is_suspended = lambda p: False
ck(c.post("/v2/api/crm/views?module=meetings", headers=HOD, json={"name": "x", "view": "all"}).status_code == 403, "saved views: owner only")
ck(c.get("/v2/api/crm/views?module=meetings", headers=HOD).get_json().get("views") == [], "non-owner sees no shared views")
ck(c.get("/v2/api/usage_now", headers=OWN).status_code == 200, "dashboard 'online now' works with the CRM token")
print("crm_access_review OK", n)
