# tests/crm/test_inv_records.py — מודול 'מקבלי מסמכים' ב-CRM: שורת חשבונית → רשומה (סוכן לפי טלפון/שם, נשלח בוואטסאפ), תצוגות
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_inv_records", "crm_inv_agent_index", "_crm_int", "CRM_VIEWS", "CRM_MODULES", "_crm_day", "crm_query", "_crm_norm",
                "inv_phone9", "inv_name_key", "bs_p9", "crm_csv")
rec, q, idx = ns["crm_inv_records"], ns["crm_query"], ns["crm_inv_agent_index"]
NOW = 1_800_000_000.0
ep = lambda s: {"2027-01-15T10:00:00+02:00": NOW - 3600, "2026-12-01T09:00:00+02:00": NOW - 86400 * 45}.get(s, 0)
I = idx([{"name": "דנה כהן", "phone": "054-1234567", "agent": "רפי"}],
        [{"client_name": "יוסי לוי", "phone": "", "agent": "אירנה"}, {"client_name": "דנה כהן", "phone": "0541234567", "agent": "רפי"}])
ck(I["phone"]["541234567"] == ["רפי"] and I["name"][ns["inv_name_key"]("יוסי לוי")] == ["אירנה"], I)
R = [{"client_name": "דנה כהן", "phone": "0541234567", "phone9": "541234567", "doc_type": "חשבונית מס קבלה", "doc_num": "1052",
      "charge_line": "דמי תיווך", "created_at": "2027-01-15T10:00:00+02:00", "source": "fireberry", "link": "https://x/doc1", "amount": "11,700"},
     {"client_name": "לוי יוסי", "phone": "", "phone9": "", "doc_type": "קבלה", "doc_num": "", "charge_line": "",
      "created_at": "2026-12-01T09:00:00+02:00", "source": "csv", "link": "", "amount": "5000"},
     {"client_name": "לא מוכר", "phone": "0509999999", "phone9": "509999999", "doc_type": "חשבונית מס", "doc_num": "7",
      "created_at": "2026-12-01T09:00:00+02:00", "source": "direct", "link": "https://x/d7", "amount": ""}]
sent = {"541234567|1052": {"ts": NOW - 3500, "ok": True}}
out = rec(R, I, sent, ep)
by = {r["client"]: r for r in out}
d = by["דנה כהן"]
ck(d["agent"] == "רפי" and d["amount"] == 11700 and d["type"] == "חשבונית מס קבלה" and d["wa"] == "נשלח" and d["date"] == NOW - 3600
   and d["link"] == "https://x/doc1" and d["key"].startswith("iv:"), d)
ck(by["לוי יוסי"]["agent"] == "אירנה" and by["לוי יוסי"]["wa"] == "", ("name match in any word order", by["לוי יוסי"]))
ck(by["לא מוכר"]["agent"] == "" and by["לא מוכר"]["wa"] == "לא נשלח", ("phone + link but no record = not sent", by["לא מוכר"]))
ck([r["source"] for r in out] == ["fireberry", "csv", "direct"], ("document source shown as sent", [r["source"] for r in out]))
ck(len({r["key"] for r in out}) == 3, "unique keys")
V = lambda v: q(out, "", {"view": v}, "date", "desc", 1, 50, NOW, module="invoices")["total"]
got = {v: V(v) for v in ("all", "today", "tax", "receipt", "no_phone", "wa_sent", "wa_not", "no_agent")}
ck(got == {"all": 3, "today": 1, "tax": 2, "receipt": 1, "no_phone": 1, "wa_sent": 1, "wa_not": 1, "no_agent": 1}, got)
ck(q(out, "0541234567", {"view": "all"}, "date", "desc", 1, 50, NOW, module="invoices")["total"] == 1, "search by phone")
ck(ns["CRM_MODULES"]["invoices"]["editable"] == [], "read only")
csv = ns["crm_csv"](out, ns["CRM_MODULES"]["invoices"]["columns"]).decode("utf-8-sig")
ck("1052" in csv and "דמי תיווך" in csv, "export")
print("inv_records OK")
