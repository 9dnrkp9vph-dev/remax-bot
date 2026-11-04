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
# [04/11 אייל: 'שגם אם מישהו נכנס לדקה יופיע'] — 12 משתמשים נוספים היום, כל אחד פעימה אחת (פחות מדקה)
P += [{"ts": now.replace(hour=10, minute=i).isoformat(), "name": "סוכן %d" % i, "phone": "5100000%02d" % i} for i in range(12)]
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
ck(len(U["day"]) == 13 and "סוכן 11" in names("day"), ("all users, not just top 10", len(U["day"])))
ck(all(r["min"] >= 1 for r in U["day"]), "a short visit still shows at least a minute")
ck(names("day")[0] == "דנה" and {"דנה", "רועי"} <= set(names("week")) and "מיכל" not in names("week") and {"דנה", "מיכל", "רועי"} <= set(names("month")), U)
ck({"דנה", "יוסי", "מיכל", "רועי"} <= set(names("year")) and U["year_from"] == "2026-08-21", ("year capped to 60 days of retention", U.get("year_from")))
# [22/10 אייל: 'סה"כ של כל המשתמשים'] — מכל המשתמשים בתקופה, לא רק 10 הראשונים
T = U.get("totals") or {}
ck(T.get("day", {}).get("users") == 13 and T.get("month", {}).get("users") == 15 and T.get("year", {}).get("users") == 16, T)
ck(T["month"]["min"] == sum(r["min"] for r in U["month"]), T)
# [04/11 אייל: 'גרף לפי שימוש כללי במערכת לפי שבועות והיסטוריה של חודשיים אחורה'] — שבועות מיום ראשון, מתחילת השמירה (60 יום)
W = U.get("weeks") or []
ck([w["from"] for w in W] == ["2026-08-23", "2026-08-30", "2026-09-06", "2026-09-13", "2026-09-20", "2026-09-27",
                              "2026-10-04", "2026-10-11", "2026-10-18"], ("9 weeks from the first Sunday inside retention", [w.get("from") for w in W]))
wk = {w["from"]: w for w in W}
ck(wk["2026-08-30"]["users"] == 1 and wk["2026-09-27"]["users"] == 1 and wk["2026-10-18"]["users"] == 14 and wk["2026-09-06"]["users"] == 0, wk)
ck(wk["2026-10-18"]["min"] == T["week"]["min"] and W[-1].get("partial") is True and not W[0].get("partial"), W[-1])
src = {"usage_periods": lambda: U}
D = E.crm_dashboard_data(dict(src, report=lambda: {}, calls=lambda: [], signings=lambda: [], buyers=lambda: [], newborn=lambda: [],
                              last_invoice=lambda: None, activity=lambda t0: [], usage=lambda t0: [], site_ai=lambda: {}, ai_cap=lambda: 500),
                         now.timestamp(), False, "2026-10-20")
ck(D.get("usage_by", {}).get("month") and D["usage_by"]["year_from"] == "2026-08-21", ("dashboard carries usage per period", D.get("usage_by")))
ck((D.get("usage_by") or {}).get("totals", {}).get("month", {}).get("users") == 15, ("dashboard carries the totals", D.get("usage_by")))
ck(len(D["usage_by"]["day"]) == 13, ("dashboard keeps every user", len(D["usage_by"]["day"])))
ck([w["from"] for w in D.get("usage_weeks") or []] == [w["from"] for w in W], ("dashboard carries the weekly series", D.get("usage_weeks")))
h = open(os.path.join(os.path.dirname(E.__file__), "effie_v2.py"), encoding="utf-8").read()
ck("D.usage_by" in h and "הכי פעילים באפי · " in h, "the card follows the selected period")
ck("UB.totals" in h and "סה״כ · " in h, "card shows the total row")
ck("D.usage_weeks" in h and "id=\"c5\"" in h and "שימוש באפי לפי שבוע" in h, "weekly usage chart")
ck("ulist" in h, "full list scrolls inside the card")
A2 = A
A2.web_phone_name_map = lambda: {"505709865": "eyal-shmul"}
A2.web_contacts_phone_name = lambda: (_ for _ in ()).throw(RuntimeError("down"))
A2._config_agent_phones = lambda: {}
A2._name_for_phone = lambda l9: ""
A2._contacts_rows = lambda: [["אייל שמול", "0505709865", "", "", ""]]
A2._display_name_for = _ORIG_DN
ck(A2._display_name_for("eyal-shmul", "0505709865") == "אייל שמול", "real name from the team table when other sources fail")
print("dash_usage_periods OK", n)
