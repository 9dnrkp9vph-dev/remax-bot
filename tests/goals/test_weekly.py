# tests/goals/test_weekly.py — [GOALS-WEEKLY 29/10] סיכום יעדים שבועי לכל סוכן בוואטסאפ הרשמי.
# python3 tests/goals/test_weekly.py
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from zoneinfo import ZoneInfo
import goals as g

IL = ZoneInfo("Asia/Jerusalem")
canon = lambda n: " ".join(str(n or "").split())
N = [0]
def ck(c, m=""):
    assert c, m
    N[0] += 1

def at(day, h=11):
    return dt.datetime(day.year, day.month, day.day, h, 0, tzinfo=IL)

SUN = dt.date(2026, 10, 25)            # השבוע שהסתיים: 25/10–31/10
NEXT_SUN = dt.date(2026, 11, 1)

# ── התקופה ───────────────────────────────────────────────────────────────────
ck(g.weekly_period(NEXT_SUN) == (SUN, dt.date(2026, 10, 31)), g.weekly_period(NEXT_SUN))
ck(g.weekly_period(dt.date(2026, 11, 2)) == (SUN, dt.date(2026, 10, 31)), "Monday after holiday → same week")
ck(g.weekly_scale() == 5.5, g.weekly_scale())

# ── מתי שולחים ───────────────────────────────────────────────────────────────
ck(g.weekly_due(at(NEXT_SUN, 10), False, {}) == SUN.isoformat(), "Sunday 10:00")
ck(g.weekly_due(at(NEXT_SUN, 9), False, {}) is None, "before 10:00")
ck(g.weekly_due(at(NEXT_SUN, 10), True, {}) is None, "holiday / quiet")
ck(g.weekly_due(at(dt.date(2026, 11, 2), 11), False, {}) == SUN.isoformat(), "next workday after holiday Sunday")
ck(g.weekly_due(at(dt.date(2026, 11, 5), 11), False, {}) == SUN.isoformat(), "Thursday still")
ck(g.weekly_due(at(dt.date(2026, 11, 6), 11), False, {}) is None, "not Friday")
ck(g.weekly_due(at(dt.date(2026, 11, 7), 11), False, {}) is None, "not Saturday")
ck(g.weekly_due(at(NEXT_SUN, 11), False, {SUN.isoformat(): {"done": True}}) is None, "already done")

# ── המלצה ────────────────────────────────────────────────────────────────────
ck(g.weekly_recommend(15, 11, 2) == ("up", 3), g.weekly_recommend(15, 11, 2))       # 136%
ck(g.weekly_recommend(14, 11, 2) == ("keep", 2), "127% → keep")
ck(g.weekly_recommend(5, 11, 2) == ("down", 1), "45% → down")
ck(g.weekly_recommend(6, 11, 2) == ("keep", 2), "55% → keep")
ck(g.weekly_recommend(0, 5.5, 1) == ("keep", 1), "never below 1")
ck(g.weekly_recommend(0, 0, 0) == ("keep", 0), "target 0")
ck(g.weekly_recommend(None, 11, 2) == ("keep", 2), "unknown count")
ck(g.weekly_recommend(40, 27.5, 5)[0] == "up" and g.weekly_recommend(40, 27.5, 5)[1] >= 6, "up at least +1")

# ── בנייה ────────────────────────────────────────────────────────────────────
nb = {"a1": {"agent": "דנה כהן", "status": "meeting", "meeting_at": at(SUN).timestamp(), "pkey": "p1"},
      "a2": {"agent": "דנה כהן", "status": "meeting", "meeting_at": at(dt.date(2026, 10, 30)).timestamp(), "pkey": "p2"},
      "a3": {"agent": "דנה כהן", "status": "meeting", "meeting_at": at(NEXT_SUN).timestamp(), "pkey": "p3"},  # לא בשבוע
      "a4": {"agent": "דנה  כהן", "status": "meeting", "meeting_at": at(dt.date(2026, 10, 24)).timestamp(), "pkey": "p4"}}
src = {"nb": nb, "buyers": [], "bpages": [], "activity": [], "reviews": [], "missed": [],
       "roster": ["דנה כהן", "רון לוי", "יוסי חדש"], "seen": ["דנה כהן", "רון לוי"],
       # [GOALS3] יעד משרד לחודש; לרון יעד אישי 47 פגישות → דנה מקבלת את היתרה (94 − 47). אוקטובר: 23.5 ימי עבודה
       "cfg": {"v2_goals": {"office": {"meetings": 94, "buyers": 141}, "agents_month": {"רון לוי": {"meetings": 47}}}}}
rows = g.build_weekly(src, SUN, canon)
ck([r["name"] for r in rows] == ["דנה כהן", "רון לוי"], "only seen agents: " + str([r["name"] for r in rows]))
d = rows[0]
ck(d["counts"]["meetings"] == 2, d["counts"])
ck(d["targets"]["meetings"] == 11 and d["targets"]["buyers"] == 17, d["targets"])     # 2×5.5; 3×5.5=16.5 → 17
ck(d["daily"]["meetings"] == 2 and d["monthly"]["meetings"] == 47 and d["monthly"]["buyers"] == 71, d)
ck(d["met"] == 0 and d["goals_n"] == 6, (d["met"], d["goals_n"]))
ck(d["rec"]["meetings"] == ("down", 35), d["rec"])                                        # 47 × 0.75
ck(rows[1]["targets"]["meetings"] == 11 and rows[1]["monthly"]["meetings"] == 47, rows[1])
ck(d["from"] == SUN.isoformat() and d["to"] == "2026-10-31", (d["from"], d["to"]))

# מקור שנכשל → None, בלי ליפול
rows2 = g.build_weekly(dict(src, buyers=RuntimeError("x")), SUN, canon)
ck(rows2[0]["counts"]["buyers"] is None and rows2[0]["rec"]["buyers"] == ("keep", 71), rows2[0])

# ── ההודעה ───────────────────────────────────────────────────────────────────
msg = g.weekly_message(d, "רימקס פמילי", "https://x/v2/goals")
ck(msg.startswith("שלום דנה,"), msg)
ck("רימקס פמילי" in msg and "25/10–31/10" in msg, msg)
ck("פגישות מנכס נולד: 2 מתוך 11" in msg, msg)
ck("קונים חדשים: 0 מתוך 17" in msg, msg)
ck("הגעת ל-0 מתוך 6 יעדים" in msg, msg)
ck("להוריד ל-35 בחודש" in msg, msg)
ck(msg.rstrip().endswith("https://x/v2/goals"), msg)
ck(not any(0x1F300 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF for ch in msg), "no emojis")
ck("RE/MAX" not in msg and "רימקס פמילי" in msg, "office name only from config")
msg_unknown = g.weekly_message(rows2[0], "", "https://x/v2/goals")
# [GOALS2] גיוס נכסים — יעד שבועי לא מוכפל, ראשון בהודעה; קונים מהחתמה; פניות לנכס נולד
sigs = [{"agent": "דנה כהן", "address": "הרצל 5", "type": "בלעדיות", "signed": True, "ts": "27/10/2026 10:00"}]
buy = [{"agent": "דנה כהן", "date": "26/10/2026 10:00", "summary": "מהחתמת מתעניין · הרצל 5"}]
r3 = g.build_weekly(dict(src, sigs=sigs, buyers=buy), SUN, canon)[0]
ck(r3["targets"]["listings"] == 10 and r3["counts"]["listings"] == 1, (r3["targets"], r3["counts"]))   # 40 בחודש → 9.03 בשבוע
m3 = g.weekly_message(r3, "רימקס פמילי", "https://x/v2/goals")
ck(m3.index("גיוס נכסים: 1 מתוך 10") < m3.index("פגישות מנכס נולד"), m3)
ck("(מתוכם 1 מהחתמה)" in m3 and "פניות לנכס נולד:" in m3 and "בחודש" in m3, m3)
ck("קונים חדשים: אין נתון" in msg_unknown, msg_unknown)
ck("ב" + "," not in msg_unknown.split("\n")[0], msg_unknown.split("\n")[0])

# ── סיכום למנהל ──────────────────────────────────────────────────────────────
sm = g.weekly_manager_summary(rows, "רימקס פמילי")
ck("דנה כהן" in sm and "פגישות מנכס נולד: להוריד ל-35 בחודש (היום 47;" in sm, sm)
ck("25/10–31/10" in sm, sm)
calm = g.weekly_manager_summary([dict(r, rec={k: ("keep", v) for k, v in r["monthly"].items()}) for r in rows], "")
ck("אין המלצות לשינוי" in calm, calm)

# ── רישום שליחה ──────────────────────────────────────────────────────────────
rec = {}
g.weekly_mark(rec, "דנה כהן", "sent", 100.0)
g.weekly_mark(rec, "רון לוי", "fail", 100.0)
ck(rec["agents"]["דנה כהן"]["r"] == "sent" and rec["agents"]["רון לוי"]["tries"] == 1, rec)
g.weekly_mark(rec, "רון לוי", "fail", 200.0)
ck(rec["agents"]["רון לוי"]["tries"] == 2, rec)
ck(g.weekly_pending(["דנה כהן", "רון לוי", "יוסי"], rec, 200.0 + 60, canon) == ["יוסי"], "retry waits 15 min")
ck(g.weekly_pending(["דנה כהן", "רון לוי", "יוסי"], rec, 200.0 + 901, canon) == ["רון לוי", "יוסי"], "retry after 15 min")
for i in range(10):
    g.weekly_mark(rec, "רון לוי", "fail", 300.0 + i)
ck(g.weekly_pending(["רון לוי"], rec, 10 ** 6, canon) == [], "gives up after 8 tries")
ck(g.weekly_pending(["דנה  כהן"], rec, 10 ** 6, canon) == [], "canon names")

# ── [29/10] ריבוע בריאות בלוח הבקרה ─────────────────────────────────────────
def ts(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IL).timestamp()
W = "2026-10-25"
ok_rec = {W: {"done": True, "agents": {"א": {"r": "sent", "ts": ts(2026, 11, 1, 10, 2)}}, "mgr": {"r": "sent", "ts": ts(2026, 11, 1, 10, 3)}}}
h = g.weekly_health(ok_rec, ts(2026, 11, 1, 12), False)
ck(h["status"] == "ok" and h["last"] == ts(2026, 11, 1, 10, 3) and h["label"] == "סיכום יעדים שבועי", h)
part = {W: {"done": True, "agents": {"א": {"r": "sent", "ts": 1}, "ב": {"r": "fail", "ts": 2, "tries": 8}}, "mgr": {"r": "sent", "ts": 3}}}
ck(g.weekly_health(part, ts(2026, 11, 1, 12), False)["status"] == "warn", "some failed")
ck(g.weekly_health({}, ts(2026, 11, 1, 10, 30), False)["status"] == "ok", "Sunday before grace — not late yet")
ck(g.weekly_health({}, ts(2026, 11, 1, 12), False)["status"] == "warn", "Sunday after 11:00, not sent")
ck(g.weekly_health({}, ts(2026, 11, 2, 13), False)["status"] == "bad", "Monday afternoon, not sent")
ck(g.weekly_health({}, ts(2026, 11, 1, 12), True)["status"] == "quiet", "holiday")
prev = {"2026-10-18": {"done": True, "mgr": {"r": "sent", "ts": ts(2026, 10, 25, 10, 3)}}}
hw = g.weekly_health(prev, ts(2026, 10, 28, 12), False)
ck(hw["status"] == "ok" and hw["last"] == ts(2026, 10, 25, 10, 3), hw)          # רביעי: השבוע הקודם נשלח
ck(g.weekly_health({}, ts(2026, 10, 28, 12), False)["status"] == "bad", "midweek, last week never sent")
ck(g.weekly_health(ok_rec, ts(2026, 11, 1, 12), False, enabled=False)["status"] == "none", "env off")
print("weekly ok", N[0])
