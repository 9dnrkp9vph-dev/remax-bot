# tests/crm/test_import_fireberry.py — CRM שלב 1: תכנון ייבוא היסטוריה מ-CSV של פיירברי (בלי DB)
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(__file__))
from _load import ck
import _load
import import_fireberry as T
plan = T.fb_plan

# חשבוניות — אותו בנאי שורה כמו הקליטה החיה (inv_ingest_row) → אותו row_hash
inv = {"שם": "מילה ברזין", "טלפון": "0508148184", "סוג מסמך": "חשבונית מס", "מספר מסמך": "",
       "סכום במסמך": "3422.00", "נוצר בתאריך": "15/10/2026 13:06", "קישור למסמך": "bit.ly/4BfefHd"}
H = T.inv_ingest_row(inv)["row_hash"]
ck(plan("invoices", [inv], {"hashes": {H}, "docnums": set(), "triples": set()})[0]["action"] == "exists", "hash")
inv2 = dict(inv, **{"מספר מסמך": "25134", "נוצר בתאריך": "15/10/2026 13:07"})
ck(plan("invoices", [inv2], {"hashes": set(), "docnums": {"25134"}, "triples": set()})[0]["action"] == "exists", "doc_num")
ck(plan("invoices", [inv], {"hashes": set(), "docnums": set(), "triples": {T._inv_triple(dict(phone9="508148184", amount="3422", doc_type="חשבונית מס", created_at="2026-10-15T10:06:00+00:00"))}})[0]["action"] == "exists", "phone+amount+type+day (UTC from DB)")
# 00:30 בישראל = 21:30Z יום קודם — אותו יום ישראלי
night = dict(inv, **{"נוצר בתאריך": "16/10/2026 00:30"})
ck(plan("invoices", [night], {"hashes": set(), "docnums": set(), "triples": {T._inv_triple(dict(phone9="508148184", amount="3422", doc_type="חשבונית מס", created_at="2026-10-15T21:30:00+00:00"))}})[0]["action"] == "exists", "Israel day, not UTC day")
# קבלה לאותו לקוח/סכום/יום — לא נבלעת בחשבונית
rcpt = dict(inv, **{"סוג מסמך": "קבלה"})
ck(plan("invoices", [rcpt], {"hashes": set(), "docnums": set(), "triples": {T._inv_triple(dict(phone9="508148184", amount="3422", doc_type="חשבונית מס", created_at="2026-10-15T10:06:00+00:00"))}})[0]["action"] == "new", "receipt ≠ invoice")
ck(plan("invoices", [inv], {"hashes": {H}, "docnums": set(), "triples": set()})[0]["reason"] == "hash", "report says why")
it = plan("invoices", [inv], {"hashes": set(), "docnums": set(), "triples": set()})[0]
ck(it["action"] == "new" and it["record"]["row_hash"] == H, it)
ck(plan("invoices", [{"שם": ""}], {"hashes": set(), "docnums": set(), "triples": set()})[0]["action"] == "reject", "no name")

# שיחות — לפי מזהה הרשומה בפיירברי (event_id), אחרת טלפונים+דקה
call = {"מזהה": "e1", "שם הסוכן": "עידן חלווה", "טלפון לקוח": "549572532", "טלפון סוכן": "0505068814",
        "סטטוס": "ANSWER", "נוצר בתאריך": "18/10/2026 18:43", "סיכום תמלול": "AI* מתמלל ומסכם"}
ck(plan("calls", [call], {"event_ids": {"e1"}, "triples": set()})[0]["action"] == "exists", "call by event_id")
it = plan("calls", [call], {"event_ids": set(), "triples": set()})[0]
ck(it["action"] == "new" and it["source_key"] == "fbimp:e1" and it["record"]["event_id"] == "e1"
   and it["record"]["raw"]["caller_phone"] == "549572532" and it["record"]["received_at"] == "2026-10-18", it)
nid = dict(call); nid.pop("מזהה")
trip = T.call_triple("549572532", "0505068814", "18/10/2026 18:43")
ck(plan("calls", [nid], {"event_ids": set(), "triples": {trip}})[0]["action"] == "exists", "call by phones+minute")
ck(plan("calls", [nid], {"event_ids": set(), "triples": set()})[0]["source_key"].startswith("fbimph:"), "hash key without id")
ck(plan("calls", [{}], {"event_ids": set(), "triples": set()})[0]["action"] == "reject", "empty")

# חתימות — המפתח של הקליטה החיה (fb:<id>:<TYPE>)
sig = {"מזהה": "e2", "סוג הסכם": "BUYER_VIEW", "סוכן": "דידי לוי", "שם לקוח": "יעל מור",
       "נוצר בתאריך": "24/09/2026 20:20", "קישור1": "https://sign.hatimatova.co.il/signpad/x/?p=5"}
it = plan("signatures", [sig], {"keys": set(), "event_ids": set()})[0]
ck(it["action"] == "new" and it["source_key"] == "fb:e2:BUYER_VIEW" and it["record"]["received_at"] == "2026-09-24", it)
ck("hatimatova" in it["record"]["raw"]["commission_pct"], "link kept (sig_nonapp)")
ck(plan("signatures", [sig], {"keys": {"fb:e2:BUYER_VIEW"}, "event_ids": set()})[0]["action"] == "exists", "by key")
ck(plan("signatures", [sig], {"keys": set(), "event_ids": {"e2"}})[0]["action"] == "exists", "by event_id (legacy key)")
# אותה רשומה פעמיים בקובץ → פעם אחת חדשה
ck([x["action"] for x in plan("signatures", [sig, sig], {"keys": set(), "event_ids": set()})] == ["new", "exists"], "dup in file")
print("import_fireberry OK", _load.n)
