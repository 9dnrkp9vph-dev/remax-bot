# tests/signing/test_budget_backfix_route.py — הראוט האמיתי (app.py) עם נתונים מזויפים: תצוגה מקדימה, תיקון לפי בחירה, מפתח בלבד
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
writes, logs = [], []
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
A._fetch_manual_buyers = lambda: [{"row": 11, "name": "אלי אזולאי", "agent": "רויטל גל", "budget": "2,350,000",
                                   "search": "דו משפחתי · 4 חד' · 312 מ\"ר · קרית חיים · עד 2,350,000"}]
A.get_signings = lambda *a, **k: [{"deal_type": "CLIENT_SALE", "client_name": "אלי אזולאי", "agent": "רויטל גל",
                                   "address": "אלכסנדר זייד 131", "city": "חיפה", "received_at": "2026-10-08T11:15:00+03:00",
                                   "commission_pct": "https://remax-bot.onrender.com/s/YT-oQqMuuFut7tv5", "event_id": "027497551"}]
A._office_prop_index = lambda: {}
A.fetch_external_exclusives = lambda: []
A._sign_prop_lookup = lambda a, city="", idx=None, excl=None: {"price": 2350000, "desc": "דו משפחתי · 4 חד' · 312 מ\"ר · קרית חיים · עד 2,350,000"} if "זייד" in a else None
A._signdoc_get = lambda t: {"ok": True, "found": True, "doc": {"header": "תאריך: 08/10/2026\nלקוח: אלי אזולאי\nנכס: אלכסנדר זייד 131 · מחיר מבוקש: 1,790,000 ₪"}} if t == "YT-oQqMuuFut7tv5" else {}
A._buyers_write = lambda act, p: (writes.append((act, p)), {"ok": True})[1]
A._cache_clear = lambda *a: None
A._log_activity = lambda *a: logs.append(a)
c = A.app.test_client()
j = c.get("/api/dev/buyer_budget_fix").get_json(); print("GET", j)
assert j["ok"] and len(j["items"]) == 1 and j["items"][0]["budget_new"] == "1,790,000", j
assert j["items"][0]["search_new"] == "דו משפחתי · קרית חיים · עד 1,790,000", j["items"][0]["search_new"]
j2 = c.post("/api/dev/buyer_budget_fix", json={"rows": [11]}).get_json(); print("POST", j2, writes)
assert writes == [("updatebuyer", {"row": "11", "budget": "1,790,000", "budget_day": "2026-10-08", "search": "דו משפחתי · קרית חיים · עד 1,790,000"})], writes
assert logs and "תיקון תקציב" in logs[0][3]
writes.clear(); assert c.post("/api/dev/buyer_budget_fix", json={"rows": [99]}).get_json()["done"] == [] and not writes
A._is_dev = lambda p: False
assert c.get("/api/dev/buyer_budget_fix").status_code == 403
print("ROUTE OK")
