# tests/crm/test_call_norm.py — CRM שלב 1: נרמול שיחה שמגיעה ישירות מ-Make (במקום דרך פיירברי)
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("call_ingest_norm", "inv_parse_dt", "crm_ts")
norm = ns["call_ingest_norm"]

ck(norm({"call_uuid": "u1", "callstatus": "ANSWER", "agent": "אלי שמול", "agent_phone": "0505235330",
         "caller_phone": "546631493", "created": "18/10/2026 17:08", "summary": "סיכום", "transcript": "שלום…"})[0] == "mk:u1", "key")
r = norm({"call_uuid": "u1", "callstatus": "ANSWER", "created": "18/10/2026 17:08", "summary": "s", "transcript": "t"})
ck(r[1] == "2026-10-18" and r[2]["status"] == "ANSWER" and r[2]["transcript_summary"] == "s" and r[3] == "t", r)
ck(r[2]["event_id"] == "mk:u1" and r[2]["received_at"] == "2026-10-18T14:08:00Z", "ISO-Z like the sheet sync (sorting in /api/history)")
# Make ב-UTC: 23:30Z = 02:30 למחרת בישראל → תאריך העמודה לפי ישראל
r = norm({"call_uuid": "z1", "created": "2026-10-18T23:30:00Z"})
ck(r[1] == "2026-10-19" and r[2]["received_at"] == "2026-10-18T23:30:00Z", r[:3])
ck(norm({"callstatus": "ANSWER"}) is None, "no uuid")
ck(norm({"call_uuid": "u2", "callstatus": "NOANSWER", "transcript": "No Answer"})[3] == "", "no answer → empty transcript")
big = "א" * 60000
ck(len(norm({"call_uuid": "u3", "transcript": big})[3]) == 60000, "no truncation")
ck(norm({"call_uuid": "u4", "callstatus": "call2call"})[2]["status"] == "call2call", "status kept raw")
# עברית + uuid חלופי + קישור הקלטה
r = norm({"uuid": "u5", "סטטוס": "BUSY", "טלפון לקוח": "0549572532", "recording_url": "https://x/rec.mp3"})
ck(r[0] == "mk:u5" and r[2]["status"] == "BUSY" and r[2]["caller_phone"] == "0549572532" and r[4] == "https://x/rec.mp3", r)
# תאריך לא פריס → היום (YYYY-MM-DD)
import re
ck(re.match(r"^\d{4}-\d{2}-\d{2}$", norm({"call_uuid": "u6", "created": "zz"})[1]), "date fallback")
print("call_norm OK", _load.n)
