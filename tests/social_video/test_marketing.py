# [10/11 אייל] מסך שיווק ב-CRM — ספירת פרסומים (פוסטים/רילס/סטורי/SOLD/תיקים) לפי תקופה וסוכן
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import marketing_stats as M

n = 0
def ck(c, m=""):
    global n; assert c, m; n += 1

IL = dt.timezone(dt.timedelta(hours=2))
def ts(y, mo, d, h=12, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IL).timestamp()
def iso(y, mo, d, h=12):
    return dt.datetime(y, mo, d, h, tzinfo=IL).astimezone(dt.timezone.utc).isoformat()

# תקופות — שלישי 10/11/2026 15:00: היום מ-00:00, השבוע מראשון 08/11 00:00, החודש מ-01/11 00:00
NOW = ts(2026, 11, 10, 15)
ck(M.period_range("day", NOW) == (ts(2026, 11, 10, 0), NOW), M.period_range("day", NOW))
ck(M.period_range("week", NOW) == (ts(2026, 11, 8, 0), NOW), M.period_range("week", NOW))
ck(M.period_range("month", NOW) == (ts(2026, 11, 1, 0), NOW), M.period_range("month", NOW))
ck(M.period_range("junk", NOW) == M.period_range("week", NOW), "unknown → week")
SUN = ts(2026, 11, 8, 9)   # ביום ראשון השבוע מתחיל באותו בוקר
ck(M.period_range("week", SUN)[0] == ts(2026, 11, 8, 0), "sunday")

AG = {"k1": "דנה כהן", "k2": "יוסי לוי"}
canon = lambda s: str(s or "").replace(" ", "")

posts = [
    {"property_key": "k1", "created_at": iso(2026, 11, 9), "fb_status": "ok", "ig_status": "ok"},        # פוסט אחד, שתי רשתות
    {"property_key": "k2", "created_at": iso(2026, 11, 10), "fb_status": "ok", "ig_status": "failed"},
    {"property_key": "k1", "created_at": iso(2026, 11, 10), "fb_status": "preview", "ig_status": "preview"},  # טיוטה — לא נספר
    {"property_key": "k1", "created_at": iso(2026, 11, 10), "fb_status": "unknown", "ig_status": "skipped"},  # לא ודאי — לא נספר
    {"property_key": "k1", "created_at": iso(2026, 11, 2), "fb_status": "ok", "ig_status": "skipped"},    # מחוץ לשבוע
    {"property_key": "gone", "created_at": iso(2026, 11, 9), "fb_status": "skipped", "ig_status": "ok"}, # נכס שירד — ללא סוכן
]
videos = [
    {"property_key": "k1", "created_at": iso(2026, 11, 7), "decided_at": iso(2026, 11, 8, 10),
     "status": "published", "ig_story_status": "ok", "ig_reel_status": "ok", "fb_reel_status": "ok", "fb_story_status": "off"},
    {"property_key": "k2", "created_at": iso(2026, 11, 9), "decided_at": iso(2026, 11, 9), "status": "pending"},  # ממתין — לא נספר
    {"property_key": "k2", "created_at": iso(2026, 11, 6), "decided_at": iso(2026, 11, 6, 15), "publish_at": iso(2026, 11, 8, 8),
     "status": "partial", "ig_story_status": "failed", "ig_reel_status": "ok", "fb_reel_status": "failed"},  # אושר בשבת, עלה בראשון
]
solds = [
    {"status": "published", "ts": ts(2026, 11, 9), "agents": ["דנה כהן", "רפי"], "ig_story_status": "ok", "fb_story_status": "ok"},
    {"status": "ready", "ts": ts(2026, 11, 9), "agents": ["דנה כהן"]},                                     # לא פורסם
    {"status": "partial", "ts": ts(2026, 11, 10), "agents": ["יוסי  לוי"], "ig_story_status": "ok", "fb_story_status": "failed"},
]
kits = [
    {"status": "sent", "sent_at": iso(2026, 11, 9), "agent_name": "יוסי לוי"},
    {"status": "approved", "sent_at": None, "agent_name": "יוסי לוי"},                                     # עוד לא נשלח
    {"status": "sent", "sent_at": iso(2026, 10, 30), "agent_name": "דנה כהן"},                           # חודש קודם
]

s, e = M.period_range("week", NOW)
R = M.count(posts, videos, solds, kits, s, e, AG.get, canon)
T = R["totals"]
ck(T["posts"] == {"n": 3, "fb": 2, "ig": 2}, T["posts"])
ck(T["reels"] == {"n": 2, "fb": 1, "ig": 2}, T["reels"])
ck(T["stories"] == {"n": 1, "fb": 0, "ig": 1}, T["stories"])
ck(T["sold"] == {"n": 2} and T["kits"] == {"n": 1}, (T["sold"], T["kits"]))
ck(T["total"] == 3 + 2 + 1 + 2 + 1, T["total"])

A = {a["name"]: a for a in R["agents"]}
ck(A["דנה כהן"] == {"name": "דנה כהן", "posts": 1, "reels": 1, "stories": 1, "sold": 1, "kits": 0, "total": 4}, A["דנה כהן"])
ck(A["יוסי לוי"]["posts"] == 1 and A["יוסי לוי"]["reels"] == 1 and A["יוסי לוי"]["sold"] == 1 and A["יוסי לוי"]["kits"] == 1,
   A["יוסי לוי"])   # 'יוסי  לוי' מה-SOLD התמזג לפי canon
ck(A["רפי"]["sold"] == 1 and A["רפי"]["total"] == 1, A["רפי"])
ck(A[M.NO_AGENT]["posts"] == 1, A.get(M.NO_AGENT))
ck([a["name"] for a in R["agents"]][:2] == ["דנה כהן", "יוסי לוי"], [a["name"] for a in R["agents"]])   # הכי פעיל ראשון; תיקו — לפי שם
ck(R["agents"][-1]["name"] == M.NO_AGENT, "no-agent row last")

# היום בלבד
s, e = M.period_range("day", NOW)
R = M.count(posts, videos, solds, kits, s, e, AG.get, canon)
ck(R["totals"]["posts"]["n"] == 1 and R["totals"]["reels"]["n"] == 0 and R["totals"]["sold"]["n"] == 1 and R["totals"]["total"] == 2,
   R["totals"])
ck(all(a["total"] > 0 for a in R["agents"]) and "דנה כהן" not in [a["name"] for a in R["agents"]], R["agents"])

# החודש — כולל 02/11, בלי 30/10
s, e = M.period_range("month", NOW)
R = M.count(posts, videos, solds, kits, s, e, AG.get, canon)
ck(R["totals"]["posts"]["n"] == 4 and R["totals"]["kits"]["n"] == 1, R["totals"])

# קלט חסר/שבור לא מפיל
R = M.count(None, [{"status": "published"}], [{"status": "published", "agents": None}], [{}], 0, NOW, lambda k: None)
ck(R["totals"]["total"] == 0 and R["agents"] == [], R)

print("marketing OK", n)
