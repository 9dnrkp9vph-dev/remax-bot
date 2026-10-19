# tests/crm/test_dash_route.py — הראוט האמיתי /v2/api/crm/dashboard: הרשאה, חיווט ל-_swr, מבנה התשובה
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
SWR = []
def fake_swr(key, ttl, build, max_stale=1800):
    SWR.append((key, ttl)); return build()
A._swr = fake_swr
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
A.build_office_report = lambda day=None: {"data": {"calls": {"day": 1}, "scans": {}, "insights": []}}
A.web_fetch_raw = lambda *a, **k: []
A.get_signings = lambda *a, **k: []
A._fetch_manual_buyers = lambda: []
A.fetch_newborn = lambda: []
A._activity_fetch = lambda t0, today=True: []
A._usage_rows = lambda *a, **k: []
A._shabbat_quiet_now = lambda: False
class FakeSB:
    def enabled(s): return True
    def fetch_invoices_rows(s, q="", limit=400): return [{"created_at": "2026-10-19T08:42:00+00:00"}]
A._sbdb = FakeSB()
c = A.app.test_client()
j = c.get("/v2/api/crm/dashboard").get_json()
ck(j["ok"] and SWR and SWR[0][0] == "crmdash" and SWR[0][1] == 900, (SWR, j.get("ok")))
ck(set(["health", "periods", "series", "ai", "usage_today"]) <= set(j), list(j))
ck({h["key"]: h for h in j["health"]}["invoices"]["last"] is not None, "invoice last wired")
ck(j["periods"]["calls"] == {"day": 1}, "report wired")
A._is_dev = lambda p: False
ck(c.get("/v2/api/crm/dashboard").status_code == 403, "dev only")
print("dash_route OK", n)
# רענן: לא בונה בתוך הבקשה ולא במקביל — בנייה אחת ברקע שנכנסת למטמון; אבחון הדוח היומי לא נדרס
import time as _t
A._is_dev = lambda p: True
PUT = []; A._cache_put = lambda k, v: PUT.append(k)
A._REPORT_LAST.clear(); A._REPORT_LAST.update({"stage": "sent", "day": "2026-10-18"})
def slow_report(day=None):
    A._REPORT_LAST["stage"] = "calls"; _t.sleep(0.3); return {"data": {}}
A.build_office_report = slow_report
SWR.clear()
A._swr = lambda key, ttl, build, max_stale=1800: (SWR.append((key, ttl)), {"ok": True, "cached": 1})[1]   # מטמון חם
j1 = c.get("/v2/api/crm/dashboard?fresh=1").get_json()
j2 = c.get("/v2/api/crm/dashboard?fresh=1").get_json()
ck(j1.get("refreshing") and j2.get("refreshing"), (j1.get("refreshing"), j2.get("refreshing")))
_t.sleep(1.0)
ck(PUT.count("crmdash") == 1, ("one background build", PUT))
ck(A._REPORT_LAST.get("stage") == "sent", ("daily report diagnostics kept", A._REPORT_LAST))
print("dash_route refresh OK", n)
