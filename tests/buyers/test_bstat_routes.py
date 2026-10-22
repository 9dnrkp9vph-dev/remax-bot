# tests/buyers/test_bstat_routes.py — הראוטים האמיתיים: המרת הקובץ הישן, GET לפי קונה, POST לקונה אחד
import sys, os, re, json, tempfile, datetime as dt
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
D = tempfile.mkdtemp(); os.environ["MAP_CACHE_DIR"] = D
from flask import Flask, request
class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None
import effie_v2
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
P = os.path.join(D, "v2_buyer_status.json")
json.dump({"544448065": "closed", "501111111": "hot"}, open(P, "w"))
B = [{"bid": "u300", "row": 300, "phone": "0544448065", "agent": "מתן ביטון", "date": "01/07/2026", "name": "ישן"},
     {"bid": "u896", "row": 896, "phone": "0544448065", "agent": "עוז דנילוב", "date": "20/10/2026", "name": "חדש"},
     {"bid": "u400", "row": 400, "phone": "0501111111", "agent": "רפי", "date": "02/10/2026", "name": "חם"}]
class SB:
    def enabled(self): return True
    def fetch_activity_actions(self, t0, pre):
        return [{"ts": dt.datetime(2026, 10, 5, 12).timestamp(), "action": "עדכון סטטוס קונה", "detail": "501111111 → hot"}]
logs, clears = [], []
SES = {"A": {"phone": "544444444", "name": "עוז דנילוב", "role": "agent"}}
G = AutoG(_web_auth=lambda: SES.get(request.headers.get("X-Auth-Token", "")), _sbdb=SB(),
          _fetch_manual_buyers=lambda: B, _canon_key=lambda s: re.sub(r"\s", "", str(s or "")),
          _canon_agent_name=lambda s: s, _cache_clear=lambda k: clears.append(k),
          _excl_epoch=lambda s: dt.datetime.strptime(s, "%d/%m/%Y").timestamp() if s else 0,
          _log_activity=lambda *a: logs.append(a), _load_config=lambda: {})
app = Flask("t"); effie_v2.register(app, G); c = app.test_client()
H = {"X-Auth-Token": "A"}
j = c.get("/v2/api/buyers/statuses", headers=H).get_json()
ck(j["statuses"] == {"r300": "closed", "r400": "hot"}, j)              # הקונה של עוז (896) פעיל
m = json.load(open(P))
ck(m.get("_v") == 2 and "544448065" not in m and m.get("id:u300") == "closed", m)
# קונה חדש שנוסף כרגע (עוד לא במטמון) — POST מרענן את המטמון ומוצא אותו
B.append({"bid": "u912", "row": 912, "phone": "0544448065", "agent": "אלי שמול", "date": "22/10/2026", "name": "עוד"})
j = c.post("/v2/api/buyers/status", json={"row": 912, "phone": "054-444-8065", "status": "hot"}, headers=H).get_json()
ck(j["ok"], j)
j = c.get("/v2/api/buyers/statuses", headers=H).get_json()
ck(j["statuses"] == {"r300": "closed", "r400": "hot", "r912": "hot"}, j)
# שורה שזזה (הטלפון לא תואם) — לא נוגעים בקונה אחר
j = c.post("/v2/api/buyers/status", json={"bid": "u896", "row": 896, "phone": "0509999999", "status": "closed"}, headers=H).get_json()
ck(not j["ok"] and "buyers" in clears, j)
ck(c.get("/v2/api/buyers/statuses", headers=H).get_json()["statuses"].get("r896") is None, "896 untouched")
# החזרה לפעיל מוחקת את המפתח של הקונה הזה בלבד
ck(c.post("/v2/api/buyers/status", json={"row": 912, "phone": "0544448065", "status": "active"}, headers=H).get_json()["ok"], "active")
ck(c.get("/v2/api/buyers/statuses", headers=H).get_json()["statuses"] == {"r300": "closed", "r400": "hot"}, "back")
print("OK", n, "checks")
