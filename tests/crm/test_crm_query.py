# tests/crm/test_crm_query.py — מודול השיחות + מנוע השאילתות של מסכי ה-CRM (טהור)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_calls_records", "crm_query", "crm_csv", "CRM_MODULES", "_CRM_STATUS", "_crm_norm", "CRM_VIEWS", "_crm_day", "crm_ts", "inv_parse_dt", "inv_phone9")
recs_f, query, csv = ns["crm_calls_records"], ns["crm_query"], ns["crm_csv"]
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 19, 15, 0, tzinfo=IL).timestamp()
rows = [
 {"event_id": "e1", "status": "ANSWER", "agent": "דנה לוי", "agent_phone": "0505068814", "caller_phone": "549572532",
  "duration_sec": "252", "transcript_summary": "מחפש 4 חדרים בנאות אפק", "call_review": "✓ טוב\nציון: 4/5", "received_at": "2026-10-19T15:43:00.000Z"},
 {"event_id": "e2", "status": "NOANSWER", "agent": "רועי כהן", "caller_phone": "0523807638", "transcript_summary": "", "received_at": "2026-10-19T10:00:00.000Z"},
 {"event_id": "e3", "status": "call2call", "agent": "דנה לוי", "caller_phone": "972501112233", "transcript_summary": "חזרה ללקוח", "call_review": "ציון: 2/5", "received_at": "2026-10-18T09:00:00.000Z"},
 {"event_id": "e4", "status": "ANSWER", "agent": "מיכל", "caller_phone": "0501234567", "transcript_summary": "קומה ג'", "received_at": "2026-10-17T09:00:00.000Z"},
]
R = recs_f(rows, {"e2": {"agent": "יוסי מזרחי", "note": "לחזור מחר"}}, {"e4"})
by = {r["key"]: r for r in R}
ck(by["e1"]["status_label"] == "נענתה" and by["e2"]["status_label"] == "לא נענתה" and by["e3"]["status_label"] == "יוצאת", by)
ck(by["e1"]["score"] == 4 and by["e3"]["score"] == 2 and by["e2"]["score"] is None, "score from review")
ck(by["e2"]["agent"] == "יוסי מזרחי" and by["e2"]["note"] == "לחזור מחר" and by["e2"]["edited"], "override on top of source")
ck(by["e4"]["hidden"] and not by["e1"]["hidden"], "hidden")
ck(by["e1"]["duration"] == "4:12", by["e1"]["duration"])
q = lambda **k: query(R, k.get("q", ""), k.get("filters", {}), k.get("sort", "date"), k.get("dir", "desc"), 1, 50, now)
ck([r["key"] for r in q()["rows"]] == ["e1", "e2", "e3"], "hidden excluded, newest first")
ck(q()["total"] == 3, "total")
ck([r["key"] for r in q(filters={"view": "hidden"})["rows"]] == ["e4"], "hidden view")
ck([r["key"] for r in q(filters={"view": "today"})["rows"]] == ["e1", "e2"], "today")
ck([r["key"] for r in q(filters={"view": "missed"})["rows"]] == ["e2"], "missed")
ck([r["key"] for r in q(filters={"view": "outgoing"})["rows"]] == ["e3"], "outgoing")
ck([r["key"] for r in q(filters={"view": "low_score"})["rows"]] == ["e3"], "low score")
ck([r["key"] for r in q(q="דנה אפק")["rows"]] == ["e1"], "all words")
ck([r["key"] for r in q(q="050-111-2233")["rows"]] == ["e3"], "phone formats (972 vs dashes)")
ck([r["key"] for r in q(q="קומה ג", filters={"view": "hidden"})["rows"]] == ["e4"], "geresh normalized")
ck([r["key"] for r in q(filters={"agent": "דנה לוי"}, sort="date", dir="asc")["rows"]] == ["e3", "e1"], "field filter + asc")
ck([r["key"] for r in q(sort="agent", dir="asc")["rows"]][0] == "e1", "sort by agent")
p2 = query(R, "", {}, "date", "desc", 2, 2, now)
ck([r["key"] for r in p2["rows"]] == ["e3"] and p2["total"] == 3, "paging")
cols = ns["CRM_MODULES"]["calls"]["columns"]
data = csv(R[:1], cols)
ck(data.startswith(b"\xef\xbb\xbf") and "דנה לוי".encode() in data and b"549572532" in data, "csv with BOM")
# CSV: הגנה מנוסחאות (= + - @) וטלפון נשאר עם 0
evil = [{"agent": "=HYPERLINK(1)", "caller_phone": "0549572532", "summary": "- סיכום", "date": 0}]
d2 = csv(evil, [("agent", "a", "text"), ("caller_phone", "p", "phone"), ("summary", "s", "long")]).decode("utf-8-sig")
ck("'=HYPERLINK(1)" in d2 and "'- סיכום" in d2, d2)
import csv as _csv, io as _io
_cells = list(_csv.reader(_io.StringIO(d2)))[1]
ck(_cells[1] == '="0549572532"', ("phone as text (parsed CSV cell)", _cells))
# 7 ספרות לא תואמות שורה בלי טלפון סוכן
ck(q(q="1234567")["total"] == 0, "short phone token doesn't match empty")
# שורה בלי event_id (רוב השיחות מהגיליון) — מזהה מפונקציית המזהה של האפליקציה (_call_uid), לא נזרקת
R2 = recs_f([{"status": "ANSWER", "agent": "x", "caller_phone": "1", "received_at": "2026-10-19T10:00:00Z"}], {}, set(),
            uid=lambda c: "h-" + c["caller_phone"])
ck(len(R2) == 1 and R2[0]["key"] == "h-1", R2)
print("crm_query OK", _load.n)
