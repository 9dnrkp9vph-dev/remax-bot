# tests/day_wa/test_day_wa.py — [DAY-WA 01/11 אייל] 'דוח בוואטסאפ למספר שלי שימדוד: כמה פגישות תואמו מהבוקר ועל ידי מי,
# החתמות קונים, תהליכים חדשים (סה"כ פתוחים), כמות נכסים בבלעדיות עדכני, כמה גיוסים מהבוקר ומי גייס, וכמות עסקאות מהבוקר'
# + 'כל יום בשעה 21'. day_wa.py = פונקציות טהורות; ההדבקה ב-app.py נבדקת סטטית.
import os, sys, datetime as dt
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
import day_wa as W

n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1

IL = W._IL
DAY = dt.date(2026, 11, 1)                     # ראשון
at = lambda h, m=0, d=DAY: dt.datetime(d.year, d.month, d.day, h, m, tzinfo=IL).timestamp()
YEST = DAY - dt.timedelta(days=1)

nb = {
    "a": {"status": "meeting", "agent": "רפי", "by": "אוצר", "meeting_at": at(9)},
    "b": {"status": "meeting", "agent": "מתן", "by": "אוצר", "meeting_at": at(13)},
    "c": {"status": "meeting", "agent": "מתן", "by": "", "meeting_at": at(15)},          # בלי 'by' → הסוכן
    "manual:1": {"status": "meeting", "agent": "רפי", "by": "רפי", "meeting_at": at(16)},  # ידני — נספר
    "d": {"status": "meeting", "agent": "רפי", "by": "אוצר", "meeting_at": at(22, d=YEST)},  # אתמול
    "e": {"status": "followup", "agent": "רפי", "by": "אוצר", "meeting_at": None},          # פולו-אפ
    "f": {"status": "meeting", "agent": "רפי", "by": "אוצר"},                               # ישנה בלי חותמת
    "x": "garbage",
}
sigs = [
    {"agent": "רפי", "address": "הנוטר 18", "type": "קונים", "signed": True, "ts": "01/11/2026 10:00"},
    {"agent": "רפי", "address": "שבזי 4", "type": "קונים", "signed": False, "ts": "2026-11-01T11:00:00+02:00"},
    {"agent": "דקלה", "address": "x 1", "type": "קונים", "signed": False, "ts": "01/11/2026 12:00"},
    {"agent": "רפי", "address": "y 2", "type": "קונים", "signed": True, "ts": "31/10/2026 20:00"},   # אתמול
    # גיוסים: בלעדיות חתומה מהיום, נכס ייחודי
    {"agent": "אלי שמול", "address": "הרצל 5 קרית ים", "type": "בלעדיות", "signed": True, "ts": "01/11/2026 09:00"},
    {"agent": "אלי שמול", "address": "הרצל 5, קריית ים", "type": "בלעדיות", "signed": True, "ts": "01/11/2026 09:05"},  # אותו נכס
    {"agent": "אלי שמול", "address": "בגין 2", "type": "בלעדיות", "signed": True, "ts": "01/11/2026 14:00"},
    {"agent": "רפי", "address": "דובדבן 6", "type": "בלעדיות", "signed": True, "ts": "01/11/2026 16:00"},
    {"agent": "רפי", "address": "דובדבן 9", "type": "בלעדיות", "signed": False, "ts": "01/11/2026 16:00"},    # לא נחתם
    {"agent": "רפי", "address": "בדיקה בדיקה 1", "type": "בלעדיות", "signed": True, "ts": "01/11/2026 16:00"},
    {"agent": "רפי", "address": "z 3", "type": "מוכר", "signed": True, "ts": "01/11/2026 16:00"},
]
deals = [
    {"agents": ["רפי"], "created": "01/11/2026", "deal": False},
    {"agents": ["מתן"], "ts": at(10), "deal": False},
    {"agents": ["רפי"], "created": "20/10/2026", "deal": False},
    {"agents": ["אוהד"], "created": "01/09/2026", "deal": True, "close_date": "01/11/2026"},
    {"agents": ["רפי", "מתן"], "created": "01/09/2026", "deal": True, "close_date": "01/11/2026"},
    {"agents": ["רפי"], "created": "01/09/2026", "deal": True, "close_date": "30/10/2026"},
]
canon = lambda s: str(s or "").strip()
C = W.day_wa_counts(DAY, nb, sigs, deals, excl_now=273, canon=canon)

# 1. פגישות שתואמו היום — לפי מי שתיאם (בלי 'by' → הסוכן); ידניות נספרות; אתמול/פולו-אפ/בלי חותמת — לא
ck(C["meetings"] == 4, C["meetings"])
ck(C["meetings_by"] == [("אוצר", 2), ("מתן", 1), ("רפי", 1)], C["meetings_by"])
# 2. החתמות קונים מהיום (נשלחו) + כמה כבר נחתמו
ck(C["buyers_sign"] == 3 and C["buyers_signed"] == 1, (C["buyers_sign"], C["buyers_signed"]))
# 3. תהליכים חדשים מהיום + סה"כ פתוחים
ck(C["deals_new"] == 2 and C["open_now"] == 3, (C["deals_new"], C["open_now"]))
ck(C["deals_new_by"] == [("מתן", 1), ("רפי", 1)], C["deals_new_by"])
# 4. בלעדיות כרגע — מה שהועבר
ck(C["excl_now"] == 273, C["excl_now"])
# 5. גיוסים — בלעדיות חתומה מהיום, נכס ייחודי לסוכן; לא חתום / בדיקה / מוכר — לא
ck(C["gius"] == 3 and C["gius_by"] == [("אלי שמול", 2), ("רפי", 1)], (C["gius"], C["gius_by"]))
# 6. עסקאות שנסגרו היום — עסקה משותפת = עסקה אחת, נזקפת לסוכן הראשון
ck(C["closed"] == 2 and C["closed_by"] == [("אוהד", 1), ("רפי", 1)], (C["closed"], C["closed_by"]))
# 7. מקור שנפל (None) → '—' בלי להפיל
D = W.day_wa_counts(DAY, None, None, None, excl_now=None, canon=canon)
ck(D["meetings"] is None and D["gius"] is None and D["closed"] is None and D["excl_now"] is None, D)

# 8. הטקסט — כל הסעיפים, שמות עם מספרים, נקרא גם כשהתבנית מאחדת שורות
t = W.day_wa_text(C, "01/11/2026", "רימקס פמילי")
for s in ("01/11/2026", "רימקס פמילי", "פגישות שתואמו: 4", "אוצר 2", "מתן 1", "החתמות קונים: 3", "נחתמו 1",
          "תהליכים חדשים: 2", "סה\"כ פתוחים: 3", "נכסים בבלעדיות: 273", "גיוסים: 3", "אלי שמול 2", "עסקאות שנסגרו: 2", "אוהד 1"):
    ck(s in t, "text: " + s)
ck(all(len(line) < 400 for line in t.split("\n")), "שורות קצרות")
td = W.day_wa_text(D, "01/11/2026", "")
ck("פגישות שתואמו: —" in td and "גיוסים: —" in td, td)
tz = W.day_wa_text(W.day_wa_counts(DAY, {}, [], [], excl_now=0, canon=canon), "01/11/2026", "o")
ck("פגישות שתואמו: 0" in tz and "(" not in tz.split("\n")[2], tz)

# 9. מתי שולחים: 21:00 ואילך, לא בשבת/חג, פעם ביום, ניסיון חוזר אחרי 15 דק' עד 8
T = at(21)
d_ = lambda s: dt.datetime.strptime(s, "%Y-%m-%d %H:%M")
ck(W.day_wa_due(d_("2026-11-01 21:00"), {}, quiet=False, hour=21, now_ts=T), "ראשון 21:00")
ck(not W.day_wa_due(d_("2026-11-01 20:59"), {}, quiet=False, hour=21, now_ts=T), "לפני 21")
ck(not W.day_wa_due(d_("2026-10-31 21:00"), {}, quiet=False, hour=21, now_ts=T), "שבת")
ck(not W.day_wa_due(d_("2026-11-01 21:00"), {}, quiet=True, hour=21, now_ts=T), "חג")
ck(not W.day_wa_due(d_("2026-11-01 22:00"), {"ok": True, "ts": T}, quiet=False, hour=21, now_ts=T), "כבר נשלח")
ck(not W.day_wa_due(d_("2026-11-01 21:05"), {"ok": False, "ts": T - 60, "tries": 1}, quiet=False, hour=21, now_ts=T), "15 דק'")
ck(W.day_wa_due(d_("2026-11-01 21:20"), {"ok": False, "ts": T - 1200, "tries": 1}, quiet=False, hour=21, now_ts=T), "ניסיון חוזר")
ck(not W.day_wa_due(d_("2026-11-01 23:00"), {"ok": False, "ts": T - 9999, "tries": 8}, quiet=False, hour=21, now_ts=T), "עד 8")

# 10. ההדבקה ב-app.py
SRC = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
loop = SRC.split("def _report_daily_loop_body")[1][:4000]
ck("_day_wa_tick(now)" in loop, "tick בלולאה")
tick = SRC.split("def _day_wa_tick")[1][:3500]
for s in ("_shabbat_quiet_now()", "DAY_WA", "v2_day_wa", "OWNER_PUSH_ID", "send_text(", "nbStatus", "_deals_load",
          "get_signings", "fetch_sheet_rows", "_config_mutate", "_display_name_for", "by_phone"):
    ck(s in tick, "tick: " + s)
print("OK", n, "checks")
