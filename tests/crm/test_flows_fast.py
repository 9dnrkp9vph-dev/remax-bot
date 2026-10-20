# tests/crm/test_flows_fast.py — 'נכנס ויוצא' מהיר: היומן נקרא מסונן לפי סוגי הפעולות (לא כל 30 הימים), ומוגש מהמטמון
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"   # 21/10: הבדיקות כאן = בעל המשרד בטוקן האפליקציה (מסלול החזרה); הכניסה עם Google נבדקת בנפרד
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import supabase_db as S
seen = []
class R:
    status_code = 200
    def raise_for_status(s): pass
    def json(s): return [{"user_name": "SMS", "role": "system", "phone": "", "action": "SMS — נשלח", "target": "…4567", "ts": "2026-10-19T10:00:00+00:00"}]
S.requests.get = lambda url, headers=None, params=None, timeout=None: (seen.append(params), R())[1]
out = S.fetch_activity_actions(0, ["SMS —", "שיחה חדשה (ישירות)", "וואטסאפ רשמי —"])
ck(out and out[0]["action"] == "SMS — נשלח" and out[0]["detail"] == "…4567", out)
orp = seen[-1].get("or", "")
ck(orp.startswith("(") and 'action.like."SMS —*"' in orp and 'action.like."שיחה חדשה (ישירות)*"' in orp, ("server-side prefix filter", orp))
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל", "role": "admin"}
A._is_dev = lambda p: True
calls = []
class SB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
    def fetch_activity_actions(s, t0, prefixes):
        calls.append(list(prefixes)); return [{"ts": 1.7e9, "name": "SMS", "role": "system", "phone": "", "action": "SMS — נשלח", "detail": "x"}]
A._sbdb = SB()
A._activity_fetch = lambda *a, **k: (_ for _ in ()).throw(AssertionError("full 30-day log must not be read"))
c = A.app.test_client()
ck(c.get("/v2/api/crm/flows/list").get_json()["total"] == 1, "flows list")
ck(c.get("/v2/api/crm/flows/meta").get_json()["ok"], "flows meta")
ck(c.get("/v2/api/crm/automations/list").get_json()["ok"], "automations list")
ck(len(calls) == 1, ("one filtered read serves meta+list+automations", len(calls)))
ck("SMS —" in calls[0] and "חתימה מפיירברי" in calls[0], calls[0])
print("flows_fast OK", n)
