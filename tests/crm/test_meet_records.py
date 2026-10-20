# tests/crm/test_meet_records.py — מודול 'פגישות' ב-CRM (אייל 20/10): מי תיאם, למי, מתי, ודרך איפה (ידני / נכס נולד)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_meeting_records", "_CRM_MEET_TAG", "crm_ts", "inv_parse_dt", "CRM_VIEWS", "CRM_MODULES", "_crm_day", "_crm_on_or_after", "crm_query", "_crm_norm", "inv_phone9", "crm_csv")
rec, q = ns["crm_meeting_records"], ns["crm_query"]
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 20, 9, 0, tzinfo=IL).timestamp()
st = {"רפי::abc123": {"status": "meeting", "date": "2026-10-20T14:30", "agent": "רפי", "by": "אוצר", "pkey": "abc123", "addr": "הנשיא 4, קרית ביאליק",
                      "owner": "משה", "ophone": "0541234567", "note": "להביא הסכם", "ts": int(now - 86400)},
      "רפי::manual:1760000000000": {"status": "meeting", "date": "2026-10-21T10:00", "agent": "רפי", "by": "רפי", "pkey": "manual:1760000000000",
                                    "addr": "הרצל 2", "ts": int(now - 3600)},
      "דנה::xyz": {"status": "followup", "date": "2026-10-19", "agent": "דנה", "by": "דנה", "pkey": "xyz", "tag": "after", "done": True},
      "דנה::q": {"status": "not_interested", "agent": "דנה"}}                                   # לא פגישה ולא פולו-אפ
R = rec(st)
by = {r["key"]: r for r in R}
ck(len(R) == 3 and "m:דנה::q" not in by, [r["key"] for r in R])
m = by["m:רפי::abc123"]
ck(m["date"] == ns["crm_ts"]("2026-10-20T14:30") and m["kind"] == "פגישה" and m["agent"] == "רפי" and m["by"] == "אוצר"
   and m["source"] == "נכס נולד" and m["state"] == "פתוח" and m["owner"] == "משה" and m["phone"] == "0541234567" and m["created"] == now - 86400, m)
ck(by["m:רפי::manual:1760000000000"]["source"] == "ידני" and by["m:רפי::manual:1760000000000"]["by"] == "רפי", "manual meeting")
f = by["m:דנה::xyz"]
ck(f["kind"] == "פולו-אפ" and f["tag"] == "אחרי פגישה" and f["state"] == "בוצע" and f["date"] == ns["crm_ts"]("2026-10-19"), f)
V = lambda v: q(R, "", {"view": v}, "date", "desc", 1, 50, now, module="meetings")["total"]
got = {v: V(v) for v in ("all", "today", "upcoming", "meetings", "followups", "newborn", "manual", "coordinated", "done")}
ck(got == {"all": 3, "today": 1, "upcoming": 2, "meetings": 2, "followups": 1, "newborn": 2, "manual": 1, "coordinated": 1, "done": 1}, got)
ck(q(R, "אוצר", {"view": "all"}, "date", "desc", 1, 50, now, module="meetings")["total"] == 1, "search by coordinator")
ck(ns["CRM_MODULES"]["meetings"]["editable"] == [], "read only — editing stays in the calendar screen")
csv = ns["crm_csv"](R, ns["CRM_MODULES"]["meetings"]["columns"]).decode("utf-8-sig")
ck("אוצר" in csv and "נכס נולד" in csv, "export")
print("meet_records OK")
