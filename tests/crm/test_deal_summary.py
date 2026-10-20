# tests/crm/test_deal_summary.py — עסקאות ב-CRM: סיכום שנתי / רבעוני / חודשי / מתחילת החודש, מול אותה תקופה אשתקד (אייל 21/10)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_deal_summary", "_CRM_MONTHS_HE")
f = ns["crm_deal_summary"]
IL = ZoneInfo("Asia/Jerusalem")
T = lambda y, m, d: datetime.datetime(y, m, d, 12, 0, tzinfo=IL).timestamp()
now = datetime.datetime(2026, 11, 15, 10, 0, tzinfo=IL).timestamp()
R = [{"date": T(2026, 11, 3), "amount": 2000000, "commission": 40000},      # מתחילת החודש, הרבעון, השנה
     {"date": T(2026, 10, 20), "amount": 1000000, "commission": 20000},     # החודש הקודם, הרבעון, השנה
     {"date": T(2026, 2, 1), "amount": 500000, "commission": 10000},        # השנה
     {"date": T(2025, 11, 10), "amount": 900000, "commission": 18000},      # אשתקד: מתחילת החודש, רבעון, שנה
     {"date": T(2025, 11, 20), "amount": 700000, "commission": 14000},      # אשתקד — אחרי ה-15 → לא נספר בהשוואה
     {"date": T(2025, 10, 5), "amount": 300000, "commission": "" },         # אשתקד: החודש הקודם
     {"date": 0, "amount": 999, "commission": 999}]                         # בלי תאריך — לא נספר
S = {x["key"]: x for x in f(R, now)}
ck([x["key"] for x in f(R, now)] == ["year", "quarter", "month", "mtd"], "order")
ck(S["year"]["n"] == 3 and S["year"]["amount"] == 3500000 and S["year"]["commission"] == 70000, S["year"])
ck(S["year"]["prev"] == {"n": 2, "amount": 1200000, "commission": 18000} and S["year"]["label"] == "שנתי · 2026", S["year"])
ck(S["quarter"]["n"] == 2 and S["quarter"]["label"] == "רבעוני · Q4" and S["quarter"]["prev"]["n"] == 2, S["quarter"])
ck(S["month"]["n"] == 1 and S["month"]["amount"] == 1000000 and S["month"]["label"] == "חודשי · אוקטובר" and S["month"]["prev"]["amount"] == 300000, S["month"])
ck(S["mtd"]["n"] == 1 and S["mtd"]["commission"] == 40000 and S["mtd"]["prev"]["n"] == 1 and S["mtd"]["label"] == "מתחילת החודש · נובמבר", S["mtd"])
ck(S["mtd"]["sub"] == "01/11–15/11" and S["month"]["sub"] == "01/10–31/10", (S["mtd"]["sub"], S["month"]["sub"]))
print("deal_summary OK")
