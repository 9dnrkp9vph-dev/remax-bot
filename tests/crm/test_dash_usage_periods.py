# tests/crm/test_dash_usage_periods.py — אייל: "למה זה לא משנה 'הכי פעילים' בחודש?" — זמן פעיל לכל תקופה, משליפה אחת
import os, sys, warnings, datetime as dt; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from zoneinfo import ZoneInfo
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A, effie_v2 as E
IL = ZoneInfo("Asia/Jerusalem")
now = dt.datetime(2026, 10, 20, 12, 0, tzinfo=IL)          # שלישי
def burst(d, name, phone, k=10):
    return [{"ts": (d + dt.timedelta(seconds=45 * i)).isoformat(), "name": name, "phone": phone} for i in range(k)]
P = burst(now.replace(hour=9), "דנה", "501111111") + burst(dt.datetime(2026, 10, 18, 9, tzinfo=IL), "רועי", "502222222") \
    + burst(dt.datetime(2026, 10, 2, 9, tzinfo=IL), "מיכל", "503333333") + burst(dt.datetime(2026, 9, 1, 9, tzinfo=IL), "יוסי", "504444444")
calls = []
class SB:
    def enabled(s): return True
    def fetch_pings_today(s, iso): calls.append(iso); return [p for p in P if p["ts"] >= iso]
A._sbdb = SB()
A._usage_places = lambda t: None
_ORIG_DN = A._display_name_for
A._display_name_for = lambda n, p: n
U = A._usage_periods(now)
ck(len(calls) == 1, ("one fetch for all four periods", calls))
names = lambda k: [r["name"] for r in U[k]]
ck(names("day") == ["דנה"] and sorted(names("week")) == ["דנה", "רועי"] and sorted(names("month")) == ["דנה", "מיכל", "רועי"], U)
ck(sorted(names("year")) == ["דנה", "יוסי", "מיכל", "רועי"] and U["year_from"] == "2026-08-21", ("year capped to 60 days of retention", U.get("year_from")))
src = {"usage_periods": lambda: U}
D = E.crm_dashboard_data(dict(src, report=lambda: {}, calls=lambda: [], signings=lambda: [], buyers=lambda: [], newborn=lambda: [],
                              last_invoice=lambda: None, activity=lambda t0: [], usage=lambda t0: [], site_ai=lambda: {}, ai_cap=lambda: 500),
                         now.timestamp(), False, "2026-10-20")
ck(D.get("usage_by", {}).get("month") and D["usage_by"]["year_from"] == "2026-08-21", ("dashboard carries usage per period", D.get("usage_by")))
h = open(os.path.join(os.path.dirname(E.__file__), "effie_v2.py"), encoding="utf-8").read()
ck("D.usage_by" in h and "הכי פעילים באפי · " in h, "the card follows the selected period")
A2 = A
A2.web_phone_name_map = lambda: {"505709865": "eyal-shmul"}
A2.web_contacts_phone_name = lambda: (_ for _ in ()).throw(RuntimeError("down"))
A2._config_agent_phones = lambda: {}
A2._name_for_phone = lambda l9: ""
A2._contacts_rows = lambda: [["אייל שמול", "0505709865", "", "", ""]]
A2._display_name_for = _ORIG_DN
ck(A2._display_name_for("eyal-shmul", "0505709865") == "אייל שמול", "real name from the team table when other sources fail")
print("dash_usage_periods OK", n)
