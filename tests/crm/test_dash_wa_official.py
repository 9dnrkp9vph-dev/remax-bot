# tests/crm/test_dash_wa_official.py — לוח הבקרה: כמה הודעות יצאו מ-360dialog (המספר הרשמי) — לפי תקופה ולפי תבנית (אייל 21/10)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_wa_official", "crm_period_bounds", "_CRM_WA_OFFICIAL")
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 21, 15, 0, tzinfo=IL).timestamp()
B = ns["crm_period_bounds"](now)
A = [{"ts": now - 600, "action": "וואטסאפ רשמי — נשלח", "detail": "דנה · family_update · שלום"},
     {"ts": now - 700, "action": "וואטסאפ רשמי — נשלח", "detail": "רפי · call_summary · שיחה"},
     {"ts": now - 800, "action": "וואטסאפ רשמי — נכשל", "detail": "0541234567 · family_update"},
     {"ts": now - 900, "action": "וואטסאפ רשמי — נשלח", "detail": "ליד · שלום, קיבלתי את הבקשה"},
     {"ts": now - 950, "action": "וואטסאפ רשמי — מושבת", "detail": "ליד · family_update"},
     {"ts": now - 5 * 86400, "action": "וואטסאפ רשמי — נשלח", "detail": "x · family_update"},
     {"ts": now - 40 * 86400, "action": "וואטסאפ רשמי — נשלח", "detail": "x · מסמך חשבונית.pdf"},
     {"ts": now - 100, "action": "וואטסאפ מהטלפון — קונים", "detail": ""}]
W = ns["crm_wa_official"](A, B)
ck(W["day"] == {"sent": 3, "failed": 1, "blocked": 1, "kinds": {"family_update": 1, "call_summary": 1, "הודעה חופשית": 1}}, W["day"])
ck(W["month"]["sent"] == 4 and W["month"]["kinds"]["family_update"] == 2, ("this month", W["month"]))
ck(W["year"]["sent"] == 5 and W["year"]["kinds"]["מסמך"] == 1, W["year"])
print("dash_wa_official OK")
