# tests/crm/test_ai_returning.py — [29/10 אייל] 'תוסיף ל-CRM ולסריקה היומית ב-11 גם את הלקוחות החוזרים (כאלה שהוצאנו להם
# חשבונית — קונה מוכר או שוכר משכיר — ושוב איתנו: אנחנו משווקים להם את הנכס). רק לוואטסאפ שלי כרגע, לא לסוכנים'.
# לקוח חוזר = נייד שיש לו עסקה / מסמך מלפחות 60 יום לפני, וחתם עכשיו על הסכם בעל נכס (מוכר / בלעדיות / משכיר).
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_ai_records", "bs_p9", "crm_sig_records", "CRM_MODULES", "CRM_VIEWS", "crm_query", "_crm_norm",
                "inv_phone9", "_crm_day", "_crm_on_or_after", "_crm_td", "_crm_int", "_crm_dmy")
AI, SIG, Q = ns["crm_ai_records"], ns["crm_sig_records"], ns["crm_query"]
NOW = 1_800_000_000.0
DAY = 86400
deals = [{"key": "d:1", "date": NOW - 400 * DAY, "client": "משה כהן", "phone": "054-1111111", "address": "הנוטר 18", "agent": "רפי", "side": "קונה"}]
invs = [{"key": "iv:1", "date": NOW - 300 * DAY, "client": "רונית לוי", "phone": "0522222222", "type": "חשבונית מס", "agent": "אלי שמול"},
        {"key": "iv:2", "date": NOW - 10 * DAY, "client": "טרי", "phone": "0533333333", "type": "חשבונית מס", "agent": "x"}]
sigs = [  # מוכר + בלעדיות באותה החתמה → התראה אחת
    {"key": "sg:1", "date": NOW - 2 * DAY, "deal_type": "OWNER_SALE", "type": "מוכר", "client": "משה כהן", "phone": "0541111111",
     "agent": "דקלה ביבי", "address": "שבזי 4 · קרית ביאליק", "status": "נחתם", "link": "/s/abc"},
    {"key": "sg:2", "date": NOW - 2 * DAY + 60, "deal_type": "OWNER_EXCLUSIVE", "type": "בלעדיות", "client": "משה כהן", "phone": "0541111111",
     "agent": "דקלה ביבי", "address": "שבזי 4 · קרית ביאליק", "status": "ממתין", "link": "/s/abd"},
    {"key": "sg:3", "date": NOW - DAY, "deal_type": "OWNER_RENT", "type": "שכירות", "client": "רונית", "phone": "052-2222222",
     "agent": "נדב רייזר", "address": "הרצל 5", "status": "ממתין", "link": ""},
    # קונה (לא בעל נכס) — לא לקוח חוזר לפי ההגדרה
    {"key": "sg:4", "date": NOW - DAY, "deal_type": "CLIENT_SALE", "type": "קונים", "client": "משה כהן", "phone": "0541111111", "agent": "a", "address": "x", "status": "נחתם", "link": ""},
    # שוכר (CLIENT_RENT) — לא בעל נכס
    {"key": "sg:5", "date": NOW - DAY, "deal_type": "CLIENT_RENT", "type": "שכירות", "client": "רונית", "phone": "0522222222", "agent": "a", "address": "y", "status": "נחתם", "link": ""},
    # החשבונית מלפני 10 ימים = העסקה הנוכחית, לא לקוח חוזר
    {"key": "sg:6", "date": NOW - DAY, "deal_type": "OWNER_SALE", "type": "מוכר", "client": "טרי", "phone": "0533333333", "agent": "a", "address": "z", "status": "נחתם", "link": ""},
    # רשומת בדיקה
    {"key": "sg:8", "date": NOW - DAY, "deal_type": "OWNER_SALE", "type": "מוכר", "client": "בדיקה", "phone": "0541111111", "agent": "a", "address": "q", "status": "נחתם", "link": ""},
    # בלי טלפון / טלפון לא מוכר
    {"key": "sg:7", "date": NOW - DAY, "deal_type": "OWNER_SALE", "type": "מוכר", "client": "זר", "phone": "0549999999", "agent": "a", "address": "w", "status": "נחתם", "link": ""},
]
R = AI(deals, invs, {}, [], [], NOW, lambda b: 0, lambda raw: 0, sigs=sigs)
rc = [r for r in R if r["type"] == "לקוח חוזר"]
ck(len(rc) == 2, [(r["name"], r["what"]) for r in rc])
m = [r for r in rc if r["phone"] == "0541111111"][0]
ck(m["what"].startswith("חתם שוב — מוכר + בלעדיות"), m["what"])
ck(m["name"] == "משה כהן" and m["agent"] == "דקלה ביבי" and "מוכר" in m["what"] and "בלעדיות" in m["what"] and "שבזי 4" in m["what"], m)
ck("הנוטר 18" in m["past"] and m["deals_link"] == "/v2/crm/deals?q=0541111111" and m["date"] == NOW - 2 * DAY, m)
ck(m["status"] == "נחתם חלקית", m["status"])
ck(m["link"] == "/v2/crm/signatures?q=0541111111", m["link"])
r2 = [r for r in rc if r["phone"] == "0522222222"][0]
ck(r2["status"] == "ממתין לחתימה", r2["status"])
ck("משכיר" in r2["what"] and "חשבונית מס" in r2["past"] and r2["inv_link"] == "/v2/crm/invoices?q=0522222222", r2)
ck(len({r["key"] for r in R}) == len(R), "מפתחות ייחודיים")
# נייד עם יותר מ-20 עסקאות/מסמכים = טלפון של המשרד — לא לקוח חוזר
many = [{"key": "iv:%d" % i, "date": NOW - 400 * DAY, "client": "x", "phone": "0577777777", "type": "קבלה"} for i in range(21)]
ck(not [r for r in AI([], many, {}, [], [], NOW, lambda b: 0, lambda raw: 0, sigs=[dict(sigs[0], phone="0577777777", client="y")]) if r["type"] == "לקוח חוזר"], "office phone")
# בלי sigs — כמו קודם (תאימות לאחור)
ck(not [r for r in AI(deals, invs, {}, [], [], NOW, lambda b: 0, lambda raw: 0) if r["type"] == "לקוח חוזר"], "ברירת מחדל")
# תצוגה ב-CRM
V = lambda v: Q(R, "", {"view": v}, "date", "desc", 1, 50, NOW, module="ai")["total"]
ck(V("returning") == 2, V("returning"))
ck(("returning", "לקוח חוזר") in ns["CRM_MODULES"]["ai"]["views"], ns["CRM_MODULES"]["ai"]["views"])
# crm_sig_records שומר את סוג ההסכם המקורי (שכירות של בעל נכס ≠ שוכר)
S = SIG([{"event_id": "e1", "client_name": "א", "phone": "050", "deal_type": "OWNER_RENT", "received_at": "x"}],
        {"ep": lambda s: 1.0, "label": lambda c: "שכירות"})
ck(S[0]["deal_type"] == "OWNER_RENT", S[0])
# _build_ai מעביר את החתימות
SRC = open(os.path.join(_load.ROOT, "effie_v2.py"), encoding="utf-8").read()
blk = SRC[SRC.index('if module == "ai":'):SRC.index('if module == "invoices":')]
ck('_crm_records("signatures")' in blk and "sigs=" in blk, "build passes sigs")
print("OK", _load.n, "checks")
