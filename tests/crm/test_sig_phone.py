# tests/crm/test_sig_phone.py — מתעניינים ב-CRM: 'למה חסרים מספרי טלפון?' (אייל 20/10) — השלמה מכותרת ההסכם, משורת-אחות ומהקונים
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_sig_fill_phone", "_crm_sig_token", "inv_name_key", "bs_p9", "crm_ts", "inv_parse_dt")
f = ns["crm_sig_fill_phone"]
S = [{"event_id": "AbCdEfGhIjKlMnOp", "client_name": "לילך הדר", "agent": "רויטל גל", "received_at": "19/10/2026 21:04", "phone": ""},     # טוקן אפי → מהכותרת
     {"event_id": "fb:9:OWNER_SALE", "client_name": "אלדד צורדקר", "agent": "חי חיים אלבז", "received_at": "20/10/2026 09:24", "phone": ""},
     {"event_id": "fb:9:OWNER_EXCLUSIVE", "client_name": "אלדד צורדקר", "agent": "חי חיים אלבז", "received_at": "20/10/2026 09:24", "phone": "054-8022494"},
     {"event_id": "fb:7", "client_name": "קלרה", "agent": "קובי חמו", "received_at": "19/10/2026 20:34", "phone": ""},                     # מהקונים
     {"event_id": "fb:8", "client_name": "דיוויד", "agent": "עוז דנילוב", "received_at": "19/10/2026 11:05", "phone": ""}]                    # אין בשום מקום
H = {"AbCdEfGhIjKlMnOp": "תאריך: 19/10/2026 · הסוכן: רויטל גל\nלקוח: לילך הדר · טל' 050-1112233 · ת״ז 123\nנכס: קק\"ל 24"}
calls = []
def fetch(toks):
    calls.append(sorted(toks)); return {t: H.get(t, "") for t in toks}
parse = lambda h: {"phone": "050-1112233"} if "טל'" in h else {"phone": ""}
B = [{"name": "קלרה", "agent": "קובי חמו", "phone": "0521234567"}, {"name": "דיוויד", "agent": "אחר", "phone": "0529999999"}]
out = f(S, fetch, parse, B, lambda n: n)
ck([g["phone"] for g in out] == ["050-1112233", "054-8022494", "054-8022494", "0521234567", ""], [g["phone"] for g in out])
ck(calls == [["AbCdEfGhIjKlMnOp"]], ("one header query, only for Effie tokens missing a phone", calls))
ck(S[0]["phone"] == "", "input not modified")
ck(f(S, lambda t: (_ for _ in ()).throw(RuntimeError("down")), parse, [], lambda n: n)[1]["phone"] == "054-8022494", "header failure → other sources still fill")
# אותה החתמה בשני פורמטים של זמן (ISO-UTC מהמראה, DD/MM מהגיליון) — עדיין אותו יום בישראל
M = [{"event_id": "x1", "client_name": "אלדד  צורדקר", "agent": "חי חיים אלבז", "received_at": "2026-10-20T06:24:00Z", "phone": ""},
     {"event_id": "x2", "client_name": "אלדד צורדקר", "agent": "חי חיים אלבז", "received_at": "20/10/2026 09:24", "phone": "054-8022494"}]
ck(f(M, lambda t: {}, parse, [], lambda n: n)[0]["phone"] == "054-8022494", "mixed time formats, extra space in the name")
print("sig_phone OK")
