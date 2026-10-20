# tests/crm/test_buyer_api.py — /v2/crm/buyers: רשימה, עריכה (שדות + סטטוס), הוספה, מחיקה — דרך מסלולי הכתיבה הקיימים
import os, sys, warnings, json, tempfile; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"   # 21/10: הבדיקות כאן = בעל המשרד בטוקן האפליקציה (מסלול החזרה); הכניסה עם Google נבדקת בנפרד
os.environ["MAP_CACHE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
class SB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
A._sbdb = SB()
ROWS = [{"row": 5, "date": "19/10/2026", "name": "גדזיי", "phone": "0532254463", "agent": "אירנה", "budget": "1285000", "summary": "מהחתמת מתעניין", "search": "דירה"},
        {"row": 6, "date": "18/10/2026", "name": "ליד", "phone": "", "agent": "אייל שמול", "budget": "", "summary": "ליד מהאתר", "search": ""}]
W = []
def bw(action, p):
    W.append((action, dict(p)))
    if action == "updatebuyer":
        r = next(x for x in ROWS if x["row"] == int(p["row"])); r.update({k: v for k, v in p.items() if k != "row"})
    if action == "deletebuyer":
        ROWS[:] = [x for x in ROWS if x["row"] != int(p["row"])]
    if action == "addbuyer":
        ROWS.append(dict(p, row=99))
    return {"ok": True}
A._buyers_write = bw
A._fetch_manual_buyers = lambda: [dict(r) for r in ROWS]
LOG = []; A._log_activity = lambda *a: LOG.append(a)
import effie_v2 as E
class BPSB:
    def bpage_all(s): return [{"id": "p1", "row": 5, "token": "TOKfive1", "expires_at": "2099-01-01T00:00:00+00:00"}]
    def bpage_items(s, ids): return [{"page_id": "p1", "mark": "like"}, {"page_id": "p1", "mark": ""}]
E._BP_SB = BPSB()
c = A.app.test_client()
m = c.get("/v2/api/crm/buyers/meta").get_json()
ck(m["ok"] and m["title"] == "קונים" and m["counts"]["all"] == 2 and m["counts"]["site"] == 1, m.get("counts"))
L = c.get("/v2/api/crm/buyers/list?view=bpage").get_json()
ck(L["total"] == 1 and L["rows"][0]["bpage"] == "/b/TOKfive1" and L["rows"][0]["bpage_sum"] == "2 נכסים · 1 מתאים", L)
r = c.post("/v2/api/crm/buyers/record", json={"key": "b:5", "fields": {"budget": "1,300,000", "status": "חם", "bogus": "x"}}).get_json()
ck(r["ok"] and ("updatebuyer", {"row": 5, "budget": "1,300,000"}) in W, (r, W))
ck(c.get("/v2/api/crm/buyers/list?view=hot").get_json()["total"] == 1, "status saved to the buyers status store (same as the buyers screen)")
r = c.post("/v2/api/crm/buyers/record", json={"key": "b:6", "fields": {"status": "סגר"}}).get_json()
ck(r["ok"] and c.get("/v2/api/crm/buyers/list?view=closed").get_json()["total"] == 1, "status by row when no phone")
ck(c.post("/v2/api/crm/buyers/record", json={"key": "b:5", "fields": {"status": "משהו"}}).get_json().get("reason") == "bad_status", "bad status")
r = c.post("/v2/api/crm/buyers/record", json={"fields": {"name": "קונה חדש", "phone": "0509999999", "agent": "רפי", "search": "3 חדרים"}}).get_json()
ck(r["ok"] and W[-1][0] == "addbuyer" and W[-1][1]["name"] == "קונה חדש" and W[-1][1]["agent"] == "רפי" and W[-1][1]["date"], W[-1])
ck(c.post("/v2/api/crm/buyers/record", json={"fields": {"phone": "05"}}).get_json().get("reason") == "no_name", "name required")
r = c.post("/v2/api/crm/buyers/record", json={"key": "b:6", "delete": True}).get_json()
ck(r["ok"] and ("deletebuyer", {"row": 6}) in W and not any(x["row"] == 6 for x in ROWS), "delete")
ck(any("קונים" in str(x[3]) for x in LOG), "activity logged")
ck("גדזיי" in c.get("/v2/api/crm/buyers/export").get_data(as_text=True), "export")
h = c.get("/v2/crm/buyers").get_data(as_text=True)
ck("MOD === 'buyers' && k === 'status'" in h and "וואטסאפ לקונה" in h and "לא ניתן לשחזר" in h, "buyers drawer: status select, WhatsApp, permanent delete")
ck('data-rm="' in h and 'data-ed="' in h and "c[3] || 'למודעה'" in h, "row edit/delete buttons + link label")
import re, subprocess
js = re.search(r"function fmtPh\(v\)\{.*?return String\(v \|\| ''\); \}", h, re.S).group(0)
out = subprocess.run(["node", "-e", js + ";console.log([fmtPh('+972532254463'),fmtPh('972532254463'),fmtPh('0532254463'),fmtPh('048008283')].join('|'))"], capture_output=True, text=True).stdout.strip()
ck(out == "053-2254463|053-2254463|053-2254463|04-8008283", out)
print("buyer_api OK", n)
