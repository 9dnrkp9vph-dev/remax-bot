# tests/crm/test_deal_records.py — מודול 'עסקאות' ב-CRM (אייל 21/10): היסטוריית העסקאות של אפי במבנה ה-CRM
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_deal_records", "_CRM_BRANCH_HE", "crm_ts", "inv_parse_dt", "_crm_int", "CRM_VIEWS", "CRM_MODULES", "_crm_day",
                "crm_query", "_crm_norm", "inv_phone9", "crm_csv")
rec, q = ns["crm_deal_records"], ns["crm_query"]
now = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=ZoneInfo("Asia/Jerusalem")).timestamp()
D = [{"id": 1, "branch": "motzkin", "year": 2026, "deal_date": "2026-10-20", "city": "אתא", "street": "בית וגן 10", "side": "קונה",
      "agent": "לירון איש לב", "client_name": "דנה", "client_phone": "0541234567", "deal_amount": 19650, "commission_net": 19650,
      "paid_amount": None, "reported_date": None, "status": {}, "invoice_no": "", "notes": ""},
     {"id": 2, "branch": "bialik", "year": 2025, "deal_date": "2025-03-01", "city": "ביאליק", "street": "הפטל 12", "side": "שוכר",
      "agent": "יניב פרי", "client_name": "משה", "deal_amount": 4000, "commission_net": 4000, "paid_amount": 4000},
     {"id": 3, "branch": "bialik", "year": 2026, "deal_date": "2109-08-07", "city": "ביאליק", "street": "הפטל 12", "side": "קונה",
      "agent": "יניב פרי", "deal_amount": 41000, "paid_amount": 41000, "reported_date": "2026-09-01"},
     {"id": 4, "branch": "kiryat_yam", "year": 2026, "deal_date": "2026-05-01", "street": "ים 1", "side": "מוכר", "agent": "קובי חמו",
      "missing_since": "2026-10-01"},
     {"id": 5, "branch": "bialik", "year": 2026, "deal_date": "", "street": "", "client_name": ""}]                 # שורת סכום — לא עסקה
R = rec(D, now)
by = {r["key"]: r for r in R}
ck(set(by) == {"d:1", "d:2", "d:3", "d:4"}, sorted(by))
a = by["d:1"]
ck(a["branch"] == "מוצקין" and a["kind"] == "מכירה" and a["address"] == "בית וגן 10, אתא" and a["amount"] == 19650
   and a["paid"] == "טרם שולם" and a["reported"] == "לא דווח" and a["date"] == ns["crm_ts"]("2026-10-20"), a)
ck(by["d:2"]["kind"] == "השכרה" and by["d:2"]["paid"] == "" and by["d:2"]["reported"] == "", ("history before 2026: no collection columns", by["d:2"]))
ck(by["d:3"]["date"] == 0 and "תאריך שגוי" in by["d:3"]["check"] and by["d:3"]["paid"] == "שולם" and by["d:3"]["reported"] == "דווח", by["d:3"])
ck(by["d:4"]["missing"] and "נעלמה מהקובץ" in by["d:4"]["check"], by["d:4"])
V = lambda v: q(R, "", {"view": v}, "date", "desc", 1, 50, now, module="deals")["total"]
got = {v: V(v) for v in ("all", "year", "sale", "rent", "unpaid", "unreported", "check", "bialik", "motzkin", "kiryat_yam")}
ck(got == {"all": 3, "year": 2, "sale": 2, "rent": 1, "unpaid": 1, "unreported": 1, "check": 2, "bialik": 2, "motzkin": 1, "kiryat_yam": 0}, got)
ck(q(R, "", {"view": "all"}, "date", "desc", 1, 50, now, module="deals")["rows"][0]["key"] == "d:1", "a typo date does not jump to the top")
ck(q(R, "0541234567", {"view": "all"}, "date", "desc", 1, 50, now, module="deals")["total"] == 1, "search by client phone")
ck(ns["CRM_MODULES"]["deals"]["editable"] == [], "read only")
ck("בית וגן 10" in ns["crm_csv"](R, ns["CRM_MODULES"]["deals"]["columns"]).decode("utf-8-sig"), "export")
print("deal_records OK")
