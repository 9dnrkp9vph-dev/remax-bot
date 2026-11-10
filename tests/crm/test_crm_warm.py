# tests/crm/test_crm_warm.py — [10/11 אייל: 'לוקח המון זמן להעלות, גם לדשבורד'] מודולי ה-CRM והדשבורד חמים תמיד:
# ה-warmer בונה אותם ברקע (גם מיד אחרי פריסה), עותק ישן עד 6 שעות מוגש מיד, ושיחות נשמרות במטמון.
import os, sys, time, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["DISABLE_WARMER"] = "1"
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל", "role": "admin"}
A._is_dev = lambda p: True
class SB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
    def crm_override_upsert(s, *a): pass
A._sbdb = SB()
A._fetch_hidden_calls = lambda: set()
built = []
A.web_fetch_raw = lambda tab, *a, **k: (built.append(tab), [])[1]
c = A.app.test_client()

# 1. ה-warmer של ה-CRM קיים ובונה את השיחות למטמון
ck(callable(getattr(A, "_crm_warm", None)), "_crm_warm exported to app")
A._cache_clear("crmcalls")
A._crm_warm()
ck(A._cache_get("crmcalls", 3600) is not None, "calls warmed into crmcalls")

# 2. רשימת השיחות מוגשת מהמטמון — בלי לבנות שוב
built.clear()
ck(c.get("/v2/api/crm/calls/list").get_json()["ok"], "calls list ok")
ck(built == [], ("calls list served from cache", built))

# 3. עריכת שיחה מנקה את המטמון (השינוי נראה מיד)
r = c.post("/v2/api/crm/calls/record", json={"key": "k1", "fields": {"note": "x"}})
ck(r.get_json().get("ok"), r.get_json())
ck(A._cache_get("crmcalls", 3600) is None, "edit clears crmcalls")

# 4. עותק ישן (3 שעות) מוגש מיד — לא בונים בתוך הבקשה
A._TTL_CACHE["crmbuyers"] = (time.time() - 3 * 3600, [{"key": "b1", "name": "ישן", "agent": "", "date": 0}])
A._fetch_manual_buyers = lambda: (_ for _ in ()).throw(RuntimeError("slow build must not run in the request"))
j = c.get("/v2/api/crm/buyers/list").get_json()
ck(j.get("ok") and j["total"] == 1 and j["rows"][0]["name"] == "ישן", ("stale buyers served", j))

# 5. ה-warmer הכללי מפעיל את ה-CRM — מיד בהתחלה, ואז לכל היותר פעם ב-5 דקות
hits = []
A._crm_warm = lambda: hits.append(1)
A._warm_key = lambda *a, **k: None
for nm in ("_fetch_hidden_calls", "fetch_external_exclusives", "_load_config", "fetch_agents_phones"):
    setattr(A, nm, lambda *a, **k: None)
A._CRM_WARM_LAST[0] = 0
A._warm_once(); A._warm_once()
ck(len(hits) == 1, ("crm warm throttled", hits))
A._CRM_WARM_LAST[0] = time.time() - 301
A._warm_once()
ck(len(hits) == 2, ("crm warm after 5 min", hits))
print("crm_warm OK", n)
