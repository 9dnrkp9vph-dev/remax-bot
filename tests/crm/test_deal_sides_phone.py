# tests/crm/test_deal_sides_phone.py — עסקאות ב-CRM (אייל 21/10): הפרדה קונה/מוכר/שוכר/משכיר/הפנייה + טלפון הלקוח אם יש
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_deal_records", "crm_deal_fill_phone", "_CRM_BRANCH_HE", "crm_ts", "inv_parse_dt", "_crm_int", "CRM_VIEWS", "CRM_MODULES",
                "_crm_day", "crm_query", "_crm_norm", "inv_phone9", "inv_name_key", "bs_p9")
rec, q, fill = ns["crm_deal_records"], ns["crm_query"], ns["crm_deal_fill_phone"]
now = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=ZoneInfo("Asia/Jerusalem")).timestamp()
D = [{"id": 1, "year": 2024, "deal_date": "2024-01-01", "street": "א 1", "side": "קונה", "agent": "רפי", "client_name": "דנה כהן"},
     {"id": 2, "year": 2024, "deal_date": "2024-01-02", "street": "א 2", "side": "מוכר", "agent": "רפי + אוצר", "client_name": "יוסי לוי"},
     {"id": 3, "year": 2024, "deal_date": "2024-01-03", "street": "א 3", "side": "שוכר", "agent": "דנה", "client_name": "משה"},
     {"id": 4, "year": 2024, "deal_date": "2024-01-04", "street": "א 4", "side": "משכיר", "agent": "דנה", "client_name": "רוני אבי"},
     {"id": 5, "year": 2024, "deal_date": "2024-01-05", "street": "א 5", "side": "הפניה", "agent": "דנה", "client_name": "רוני אבי"},
     {"id": 6, "year": 2024, "deal_date": "2024-01-06", "street": "א 6", "side": "קונה", "agent": "דנה", "lead_source": "הפנייה מעו\"ד", "client_name": "ש",
      "client_phone": "0501112222"},
     {"id": 7, "year": 2024, "deal_date": "2024-01-07", "street": "א 7", "side": "מוכר+קונה", "agent": "דנה", "client_name": "זוג"}]
R = rec(D, now)
V = lambda v: q(R, "", {"view": v}, "date", "desc", 1, 50, now, module="deals")["total"]
got = {v: V(v) for v in ("buyer", "seller", "tenant", "landlord", "referral")}
ck(got == {"buyer": 3, "seller": 2, "tenant": 1, "landlord": 1, "referral": 2}, got)
ck(next(r for r in R if r["key"] == "d:6")["source"] == "הפנייה מעו\"ד", "lead source column")
buyers = [{"name": "דנה כהן", "agent": "רפי", "phone": "054-1234567"}, {"name": "משה", "agent": "דנה", "phone": "0509999999"}]
sigs = [{"client_name": "לוי יוסי", "agent": "אוצר", "phone": "+972 52-1112233"}]
inv = [{"client_name": "רוני אבי", "phone": "0533334444"}, {"client_name": "משה", "phone": "0508888888"}]
F = {r["key"]: r for r in fill(R, buyers, sigs, inv, lambda n: n)}
ck(F["d:1"]["phone"] == "054-1234567" and F["d:1"]["phone_from"] == "קונים", F["d:1"])
ck(F["d:2"]["phone"] == "+972 52-1112233" and F["d:2"]["phone_from"] == "חתימות", ("joint agents, name in other order", F["d:2"]))
ck(F["d:3"]["phone"] == "0509999999", ("single-word name: only with the same agent", F["d:3"]))
ck(F["d:4"]["phone"] == "0533334444" and F["d:4"]["phone_from"] == "חשבוניות", ("full name, one phone → by name", F["d:4"]))
ck(F["d:6"]["phone"] == "0501112222" and F["d:6"]["phone_from"] == "קובץ", "file phone wins")
ck(F["d:7"]["phone"] == "" and F["d:7"]["phone_from"] == "", "no source → stays empty")
ck(R[0].get("phone_from") is None, "input not modified")
print("deal_sides_phone OK")
