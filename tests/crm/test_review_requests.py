# tests/crm/test_review_requests.py — [21/10 אייל] וואטסאפ מ-360 לכל לקוח שבוע אחרי שהעסקה נכנסה עם טלפון: בקשת ביקורת בגוגל
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("review_queue", "review_message", "review_phone", "crm_deal_review", "crm_ts", "_crm_int", "inv_parse_dt", "review_window", "review_sent_today", "CRM_MODULES", "CRM_VIEWS", "crm_query", "_crm_norm", "inv_phone9", "_crm_day")
Q, M, P, MARK = ns["review_queue"], ns["review_message"], ns["review_phone"], ns["crm_deal_review"]
NOW = 1_800_000_000.0
DAY = 86400
def iso(ep):
    import datetime
    return datetime.datetime.utcfromtimestamp(ep).strftime("%Y-%m-%dT%H:%M:%S+00:00")
def row(i, phone="0541234567", side="קונה", created=NOW - 8 * DAY, date="2026-10-01", year=2026, **kw):
    r = {"id": "id%d" % i, "src_key": "k%d" % i, "client_name": "דנה כהן", "client_phone": phone, "side": side,
         "agent": "רפי", "street": "הנוטר 18", "city": "קרית ביאליק", "deal_date": date, "year": year,
         "created_at": iso(created)}
    r.update(kw)
    return r

# טלפון: נייד ישראלי בלבד, 9 ספרות אחרונות
ck(P("0541234567") == "541234567" and P("546334989") == "546334989" and P("+972-54-123-4567") == "541234567", "mobile")
ck(P("04-8008283") == "" and P("") == "" and P("12") == "", "landline/empty → no")

rows = [row(1, date="2026-10-05"),                                  # בתור
        row(2, created=NOW - 3 * DAY),                               # עוד לא עבר שבוע
        row(3, phone=""),                                            # בלי טלפון
        row(4, side="הפנייה"),                                       # הפנייה — לא
        row(5, year=2025, date="2025-12-01"),                        # לפני 2026 — לא
        row(6, missing_since="2026-10-10T00:00:00+00:00"),            # נעלמה מהקובץ
        row(7, phone="054-123-4567", date="2026-09-01"),             # אותו טלפון כמו 1 — פעם אחת
        row(8, phone="0527777777", date="2026-10-07", side="מוכר"),  # בתור, חדשה יותר
        row(9, phone="0528888888", date="2109-08-07"),               # תאריך עתידי — לא
        row(10, phone="0529999999", date="2026-08-01")]              # כבר נשלח
sent = {"d:id10": {"ts": NOW - DAY, "p9": "529999999", "r": "sent"}}
q = Q(rows, sent, NOW, 10)
ck([r["id"] for r in q] == ["id8", "id1"], [r["id"] for r in q])
ck([r["id"] for r in Q(rows, sent, NOW, 1)] == ["id8"], "max_n")
s3 = dict(sent, x={"p9": "541234567", "r": "sent"})
ck([r["id"] for r in Q(rows, s3, NOW, 10)] == ["id8"],
   "phone already got a request (other deal) → not again")

# נוסח: שם פרטי, הסוכן (הראשון בעסקה משותפת), הצד, המשרד, הקישור
m = M(row(1, side="מוכר", agent="מאור קבלי + ליאור גרונפינקל"), "רימקס פמילי", "https://g.page/r/x/review")
ck(m.startswith("שלום דנה, כאן מאור קבלי מרימקס פמילי.") and "במכירת הנכס" in m and "https://g.page/r/x/review" in m and m.rstrip().endswith("מאור קבלי"), m)
ck("בעסקת הנדל" in M(row(1, side=""), "", "https://g.page/r/x/review"), "unknown side")

# סימון ב-CRM
recs = [{"key": "d:id1"}, {"key": "d:id10"}, {"key": "d:id3"}, {"key": "d:id11"}]
sent2 = dict(sent, **{"d:id11": {"ts": NOW - 2 * DAY, "p9": "1", "r": "fail"}})
due = {"d:id1"}
MARK(recs, sent2, due, NOW)
import datetime
from zoneinfo import ZoneInfo
d10 = datetime.datetime.fromtimestamp(NOW - DAY, ZoneInfo("Asia/Jerusalem")).strftime("%d/%m")
ck(recs[0]["review"] == "ממתין" and recs[1]["review"] == "נשלח " + d10 and recs[2]["review"] == "" and recs[3]["review"] == "נכשל",
   [r["review"] for r in recs])
# חלון שליחה: א'-ה' 10:00-19:00, ו' 10:00-13:00, לא בשבת; ומונה היום (שעון ישראל)
import datetime as _dt
from zoneinfo import ZoneInfo as _Z
il = _Z("Asia/Jerusalem")
W = ns["review_window"]
ck(W(_dt.datetime(2026, 10, 21, 11, 0, tzinfo=il)) and not W(_dt.datetime(2026, 10, 21, 9, 59, tzinfo=il))
   and not W(_dt.datetime(2026, 10, 21, 19, 0, tzinfo=il)), "wed")
ck(W(_dt.datetime(2026, 10, 23, 12, 0, tzinfo=il)) and not W(_dt.datetime(2026, 10, 23, 13, 0, tzinfo=il)), "fri")
ck(not W(_dt.datetime(2026, 10, 24, 12, 0, tzinfo=il)), "sat")
t0 = _dt.datetime(2026, 10, 21, 11, 0, tzinfo=il).timestamp()
ST = {"a": {"ts": t0 - 3600, "r": "sent"}, "b": {"ts": t0 - 3600, "r": "fail"}, "c": {"ts": t0 - 86400, "r": "sent"}}
ck(ns["review_sent_today"](ST, t0) == 2, "today counts sent+failed attempts")
# עמודה ותצוגות במודול העסקאות
mod = ns["CRM_MODULES"]["deals"]
ck("review" in [c[0] for c in mod["columns"]] and "review" in mod["default_cols"], "column")
vw = dict(mod["views"])
ck(vw.get("review_sent") == "נשלחה בקשת ביקורת" and vw.get("review_due") == "ממתינות לבקשת ביקורת", vw)
QV = lambda v: ns["crm_query"](recs, "", {"view": v}, "date", "desc", 1, 50, NOW, module="deals")["total"]
ck(QV("review_sent") == 1 and QV("review_due") == 1, (QV("review_sent"), QV("review_due")))
print("review_requests OK", _load.n)
