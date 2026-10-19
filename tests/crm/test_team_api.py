# tests/crm/test_team_api.py — מודול 'צוות' ב-CRM: רשימה, עריכה, הוספה, השבתה/שחזור, ייבוא, השוואה, תמונה
import os, sys, warnings, base64, io; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
LOG = []; A._log_activity = lambda *a: LOG.append(a)
CLR = []; A._contacts_cache_clear = lambda: CLR.append(1)
A._contacts_rows_sheet = lambda: [["שם מלא", "טלפון"], ["דנה לוי", "0501111111", "", "3123", "d@x.co"], ["רועי", "0502222222"]]
class FakeSB:
    def __init__(s): s.rows = []; s.av = {}
    def enabled(s): return True
    def team_fetch(s, active_only=False): return [dict(r) for r in s.rows if r["active"] or not active_only]
    def team_upsert(s, rows, by):
        rows = [dict(r, _by=by) for r in rows]
        for r in rows:
            ex = next((x for x in s.rows if x["name"] == r["name"]), None)
            if ex: ex.update(r)
            else: s.rows.append(dict({"id": "id%d" % len(s.rows), "active": True, "sort": 0, "phone": "", "vphone": "", "license": "", "email": ""}, **r))
        return len(rows)
    def team_update(s, rid, f, by):
        next(x for x in s.rows if x["id"] == rid).update(dict({k: v for k, v in f.items() if k in ("name", "phone", "vphone", "license", "email", "active")}, _by=by, updated_by=by)); return True
    def crm_overrides_fetch(s, m): return {}
    def avatar_save(s, p, b64): s.av[p] = b64
sb = FakeSB(); A._sbdb = sb
CACHE = {}
A._cache_get = lambda k, ttl=None: CACHE.get(k); A._cache_put = lambda k, v: CACHE.__setitem__(k, v); A._cache_clear = lambda *a: CACHE.clear()
c = A.app.test_client()
st = c.get("/v2/api/crm/team/status").get_json()
ck(st["ok"] and st["source"] == "sheets" and st["compare"]["only_sheet"] == ["דנה לוי", "רועי"] and st["table_count"] == 0, st)
im = c.post("/v2/api/crm/team/import").get_json()
ck(im["ok"] and im["imported"] == 2 and CLR, im)
st = c.get("/v2/api/crm/team/status").get_json()
ck(st["compare"]["same"] == 2 and not st["compare"]["diffs"] and not st["compare"]["only_sheet"], st["compare"])
m = c.get("/v2/api/crm/team/meta").get_json()
ck(m["ok"] and m["counts"]["all"] == 2 and m["editable"], m)
lst = c.get("/v2/api/crm/team/list?q=דנה").get_json()
ck(lst["total"] == 1 and lst["rows"][0]["email"] == "d@x.co" and lst["rows"][0]["photo"].startswith("/v2/api/avatar?p="), lst)
key = lst["rows"][0]["key"]
ck(c.post("/v2/api/crm/team/record", json={"key": key, "fields": {"vphone": "0529000000", "bogus": "x"}}).get_json()["ok"], "edit")
ck(sb.rows[0]["vphone"] == "0529000000" and "bogus" not in sb.rows[0], sb.rows[0])
ck(c.post("/v2/api/crm/team/record", json={"key": key, "delete": True}).get_json()["ok"] and sb.rows[0]["active"] is False, "deactivate")
ck(c.get("/v2/api/crm/team/list").get_json()["total"] == 1, "inactive hidden from 'all'")
ck(c.get("/v2/api/crm/team/list?view=inactive").get_json()["total"] == 1, "inactive view")
ck(c.post("/v2/api/crm/team/record", json={"key": key, "restore": True}).get_json()["ok"] and sb.rows[0]["active"] is True, "restore")
nj = c.post("/v2/api/crm/team/record", json={"fields": {"name": "סוכנת חדשה", "phone": "0503333333"}}).get_json()
ck(nj["ok"] and any(r["name"] == "סוכנת חדשה" for r in sb.rows), nj)
ck(c.post("/v2/api/crm/team/record", json={"fields": {"phone": "050"}}).get_json()["reason"] == "no_name", "name required")
# ביקורת: שם קיים, שינוי שם לשם תפוס, ייבוא אחרי המעבר
dup = c.post("/v2/api/crm/team/record", json={"fields": {"name": "דנה לוי", "phone": "0"}}).get_json()
ck(dup.get("reason") == "name_taken" and sb.rows[0]["phone"] == "0501111111", ("new with existing name rejected", dup))
ck(next(r for r in sb.rows if r["name"] == "סוכנת חדשה")["sort"] > max(r["sort"] for r in sb.rows if r["name"] != "סוכנת חדשה"), "new member sorts last")
ren = c.post("/v2/api/crm/team/record", json={"key": key, "fields": {"name": "רועי"}}).get_json()
ck(ren.get("reason") == "name_taken" and sb.rows[0]["name"] == "דנה לוי", ("rename to taken name", ren))
os.environ["CONTACTS_SOURCE"] = "supabase"
ck(c.post("/v2/api/crm/team/import").get_json().get("reason") == "already_live", "no re-import after the switch")
_saved = sb.rows; sb.rows = []
ck(c.post("/v2/api/crm/team/import").get_json().get("ok") is True and len(sb.rows) == 2, "empty table after the switch: import allowed")
sb.rows = _saved
os.environ.pop("CONTACTS_SOURCE", None)
# תיקוני נתונים: תצוגה מקדימה → החלה; כתיבות חדשות מנורמלות; 'עודכן ע"י' = שם אמיתי
A._web_auth = lambda: {"phone": "505709865", "name": "מנהל", "role": "admin"}
A._display_name_for = lambda n, p: "אייל שמול" if n == "מנהל" else n
A._load_config = lambda: {"v2_licenses": {"501111111": "3123"}}
sb.rows.append({"id": "idx", "name": "אבי", "phone": "546612292", "vphone": "", "license": "avi@x.co", "email": "", "active": True, "sort": 9, "updated_by": "מנהל"})
fx = c.get("/v2/api/crm/team/fix").get_json()
ax = next(x for x in fx["fixes"] if x["name"] == "אבי")
ck(fx["ok"] and ax["changes"]["email"][1] == "avi@x.co" and ax["changes"]["phone"][1] == "0546612292" and ax["changes"]["updated_by"][1] == "אייל שמול", fx)
ap = c.post("/v2/api/crm/team/fix").get_json()
avi = next(r for r in sb.rows if r["name"] == "אבי")
ck(ap["ok"] and ap["applied"] >= 1 and avi["email"] == "avi@x.co" and avi["license"] == "" and avi["phone"] == "0546612292", (ap, avi))
ck(any("תיקון נתונים" in str(x[3]) for x in LOG), "fix logged")
ck(not [x for x in c.get("/v2/api/crm/team/fix").get_json()["fixes"] if x["changes"]], "no changes left after apply (only unfixable warnings)")
c.post("/v2/api/crm/team/record", json={"fields": {"name": "חדשה2", "phone": "+972 52-555-1234", "license": "new@x.co"}})
nw = next(r for r in sb.rows if r["name"] == "חדשה2")
ck(nw["phone"] == "0525551234" and nw["email"] == "new@x.co" and nw["license"] == "", ("new writes normalized", nw))
ck(nw.get("_by") == "אייל שמול", ("real name as updater", nw))
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (600, 400), (30, 58, 95)).save(buf, "JPEG")
img = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
import supabase_db as _S
_S.enabled = lambda: True
_S.avatar_save = lambda p, b64: sb.av.__setitem__(p, b64)
av = c.post("/v2/api/crm/team/avatar", json={"phone": "0501111111", "img": img}).get_json()
ck(av["ok"] and "501111111" in sb.av, (av, list(sb.av)))
ck(any("צוות" in str(x[3]) for x in LOG), "activity logged")
A._is_dev = lambda p: False
ck(c.get("/v2/api/crm/team/status").status_code == 403 and c.post("/v2/api/crm/team/avatar", json={}).status_code == 403, "dev only")
print("team_api OK", n)
