# tests/signing/test_last_form_budget_flow.py — הלולאה האמיתית (_sync_signing_buyers) על המקרה של בוריס גולדברג (אייל 20/10)
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("WARMUP_ON_BOOT", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
B = [{"row": 7, "name": "בוריס גולדברג", "agent": "רויטל גל", "phone": "0544980817", "budget": "2,350,000",
      "budget_day": "2026-10-20", "search": "x", "summary": "נשלחה חתימה"}]
writes = []
def bw(act, p):
    writes.append((act, dict(p)))
    for b in B:
        if str(b["row"]) == str(p.get("row")):
            b.update({k: v for k, v in p.items() if k != "row"})
    return {"ok": True}
SIGS = [{"deal_type": "CLIENT_SALE", "client_name": "בוריס גולדברג", "agent": "רויטל גל", "phone": "0544980817",
         "address": "הנרייטה סולד 52", "city": "חיפה", "received_at": "2026-10-19T15:30:00+03:00", "budget": "3280000"},
        {"deal_type": "CLIENT_SALE", "client_name": "בוריס גולדברג", "agent": "רויטל גל", "phone": "0544980817",
         "address": "אלכסנדר זייד 131", "city": "חיפה", "received_at": "2026-10-19T11:00:00+03:00", "budget": "2350000"}]
A.get_signings = lambda *a, **k: SIGS
A._fetch_manual_buyers = lambda: B
A._buyers_write = bw
A._office_prop_index = lambda: {}
A.fetch_external_exclusives = lambda: []
A._sign_prop_lookup = lambda *a, **k: None
A._phones_for_name = lambda n: {"544326760"}
A._cache_clear = lambda *a: None
A._sync_signing_buyers()
bud = [p for a, p in writes if "budget" in p]
assert B[0]["budget"] == "3,280,000" and B[0]["budget_day"] == "2026-10-19T15:30:00", (B[0], writes)
n1 = len(bud)
A._sync_signing_buyers()   # ריצה שנייה — יציב, בלי כתיבות תקציב נוספות
assert B[0]["budget"] == "3,280,000" and len([p for a, p in writes if "budget" in p]) == n1, writes
# עריכה ידנית של הסוכן נשמרת עד הטופס הבא
B[0]["budget"] = "3,000,000"
A._sync_signing_buyers()
assert B[0]["budget"] == "3,000,000", B[0]
# טופס חדש עם שני נכסים → ממוצע הטופס
SIGS.insert(0, {"deal_type": "CLIENT_SALE", "client_name": "בוריס גולדברג", "agent": "רויטל גל", "phone": "0544980817",
                "address": "א|ב", "city": "", "received_at": "2026-10-21T10:00:00+03:00", "budget": "2500000"})
A._sync_signing_buyers()
assert B[0]["budget"] == "2,500,000" and B[0]["budget_day"] == "2026-10-21T10:00:00", B[0]
print("FLOW OK")
