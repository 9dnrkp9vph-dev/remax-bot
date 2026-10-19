# tests/crm/test_sig_merge.py — 'למה אין תקציב ב-CRM?' (בוריס גולדברג): בדדופ של get_signings השורה החתומה (מהגיליון,
# עם קישור) גוברת אבל בלי תקציב/נייד — עכשיו שדות חסרים מושלמים מהעותק השני. ושורת אפי שומרת את נייד הלקוח.
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
app_row = {"event_id": "DpBmo_M09njPnuoF", "doc_token": "DpBmo_M09njPnuoF", "deal_type": "CLIENT_SALE", "agent": "רויטל גל",
           "client_name": "בוריס גולדברג", "address": "הנרייטה סולד 52 חיפה כרמל", "city": "חיפה", "commission_pct": "",
           "received_at": "2026-10-19T17:17:00", "budget": "3280000", "phone": "0544980817"}
sheet_row = {"event_id": "307600478", "deal_type": "CLIENT_SALE", "agent": "רויטל גל", "client_name": "בוריס גולדברג",
             "address": "הנרייטה סולד 52 חיפה כרמל", "city": "חיפה", "commission_pct": "https://x/s/DpBmo_M09njPnuoF",
             "received_at": "2026-10-19T17:17:05"}
A.web_fetch_raw = lambda tab, frm=None, to=None: [dict(app_row), dict(sheet_row)]
A._recent_signs_merge = lambda x: x
A._recent_sign_dels_filter = lambda x: x
out = A.get_signings()
ck(len(out) == 1, out)
g = out[0]
ck(g["commission_pct"].endswith("DpBmo_M09njPnuoF") and g["budget"] == "3280000" and g["phone"] == "0544980817" and g["doc_token"] == "DpBmo_M09njPnuoF",
   ("signed row wins, missing fields filled from the other copy", g))
A.web_fetch_raw = lambda tab, frm=None, to=None: [dict(sheet_row), dict(app_row)]
g2 = A.get_signings()[0]
ck(g2["budget"] == "3280000" and g2["commission_pct"].startswith("https"), ("order independent", g2))
src = open(os.path.join(os.path.dirname(A.__file__), "app.py"), encoding="utf-8").read()
ck(src.count('"client_name": client, "phone": phone,') == 2, "both Effie signing routes store the client phone on the row")
print("sig_merge OK", n)
