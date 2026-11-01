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

# 1. [02/11] פגישות שתואמו היום — לפי הסוכן שהפגישה שלו; מי שתיאם לסוכן אחר בנפרד; ידניות נספרות; אתמול/פולו-אפ/בלי חותמת — לא
ck(C["meetings"] == 4, C["meetings"])
ck(C["meetings_by"] == [("מתן", 2), ("רפי", 2)], C["meetings_by"])
ck(C["meetings_coord"] == [("אוצר", 2)], C["meetings_coord"])
# 2. [01/11 אייל 'תספור רק את החתמות קונים (ברגע שנחתמו)'] — רק מה שנחתם היום; נשלח ולא נחתם / נחתם אתמול — לא
ck(C["buyers_sign"] == 1 and C["buyers_sign_by"] == [("רפי", 1)], (C["buyers_sign"], C.get("buyers_sign_by")))
# 3. תהליכים חדשים מהיום + סה"כ פתוחים
ck(C["deals_new"] == 2 and C["open_now"] == 3, (C["deals_new"], C["open_now"]))
ck(C["deals_new_by"] == [("מתן", 1), ("רפי", 1)], C["deals_new_by"])
# 4. בלעדיות כרגע — מה שהועבר
ck(C["excl_now"] == 273, C["excl_now"])
# 5. גיוסים — בלעדיות חתומה מהיום, נכס ייחודי לסוכן; לא חתום / בדיקה / מוכר — לא
ck(C["gius"] == 3 and C["gius_by"] == [("אלי שמול", 2), ("רפי", 1)], (C["gius"], C["gius_by"]))
# 6. [02/11 מתן] עסקאות שנסגרו היום — עסקה משותפת = עסקה אחת בסה"כ, נזקפת לכל אחד מהסוכנים שבה
ck(C["closed"] == 2 and C["closed_by"] == [("אוהד", 1), ("מתן", 1), ("רפי", 1)], (C["closed"], C["closed_by"]))
# 6א. תהליך משותף — לכל אחד מהשותפים; סוכן כפול בתהליך נספר פעם אחת; בלי סוכנים → מי שיצר
E = W.day_wa_counts(DAY, {}, [], [
    {"agents": ["רויטל", "בן קדוש"], "created": "01/11/2026", "deal": False},
    {"agents": ["רויטל", "בן קדוש"], "created": "01/11/2026", "deal": False},
    {"agents": ["מתן הרשקו", "רויטל", "רויטל"], "created": "01/11/2026", "deal": False},
    {"agents": [], "by": "אוצר", "created": "01/11/2026", "deal": False},
    {"agents": ["קובי חמו", "יהודית שמול"], "created": "01/09/2026", "deal": True, "close_date": "01/11/2026"},
], excl_now=0, canon=canon)
ck(E["deals_new"] == 4 and E["deals_new_by"] == [("רויטל", 3), ("בן קדוש", 2), ("אוצר", 1), ("מתן הרשקו", 1)], (E["deals_new"], E["deals_new_by"]))
ck(E["closed"] == 1 and E["closed_by"] == [("יהודית שמול", 1), ("קובי חמו", 1)], (E["closed"], E["closed_by"]))
# 7. מקור שנפל (None) → '—' בלי להפיל
D = W.day_wa_counts(DAY, None, None, None, excl_now=None, canon=canon)
ck(D["meetings"] is None and D["gius"] is None and D["closed"] is None and D["excl_now"] is None, D)

# 8. [01/11 אייל, 'אני רוצה אותו ככה'] הנוסח: כותרת, תאריך, מדדי היום, ואז הסיכומים (כולל עסקאות שנסגרו החודש)
ck(C["closed_month"] == 2, C["closed_month"])            # 30/10 — חודש קודם, לא נספר
t = W.day_wa_text(C, "01/11/2026", "רימקס פמילי")
want = """דוח סיכום יום
01/11/2026

פגישות שתואמו היום: 4 (מתן 2, רפי 2)
מתוכן תיאמו לסוכנים: אוצר 2
גיוסים היום: 3 (אלי שמול 2, רפי 1)
החתמות קונים היום: 1 (רפי 1)
תהליכים חדשים היום: 2 (מתן 1, רפי 1)
עסקאות שנחתמו היום: 2 (אוהד 1, מתן 1, רפי 1)

סה"כ תהליכים פתוחים: 3
סה"כ נכסים בבלעדיות: 273
סה"כ עסקאות שנסגרו החודש: 2"""
ck(t == want, t)
td = W.day_wa_text(D, "01/11/2026", "")
ck("פגישות שתואמו היום: —" in td and "גיוסים היום: —" in td and "סה\"כ עסקאות שנסגרו החודש: —" in td, td)
tz = W.day_wa_text(W.day_wa_counts(DAY, {}, [], [], excl_now=0, canon=canon), "01/11/2026", "o")
ck("פגישות שתואמו היום: 0\nגיוסים היום: 0\nהחתמות קונים היום: 0\nתהליכים חדשים היום: 0\nעסקאות שנחתמו היום: 0" in tz, tz)

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
tick = SRC.split("def _day_wa_tick")[1][:3500] + SRC.split("def _day_wa_build_and_send")[1][:3500]
for s in ("_shabbat_quiet_now()", "DAY_WA", "v2_day_wa", "OWNER_PUSH_ID", "send_text(", "nbStatus", "_deals_load",
          "get_signings", "fetch_sheet_rows", "_config_mutate", "_display_name_for", "by_phone"):
    ck(s in tick, "tick: " + s)

# 11. [01/11 אייל] 'שלח דוח ערב עכשיו' — כפתור בניהול; לא מסמן את היום (ה-21:00 עדיין יוצא)
ck('@app.route("/api/day-wa/send"' in SRC, "ראוט שליחה ידנית")
rt = SRC.split('@app.route("/api/day-wa/send"')[1][:1500]
ck("_report_auth_ok()" in rt and "_day_wa_build_and_send" in rt and "v2_day_wa" not in rt, "ראוט: הרשאה, בנייה, בלי סימון היום")
ck("_day_wa_build_and_send(" in tick, "ה-21:00 משתמש באותה בנייה")
EV = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
ck("daySend()" in EV and "/api/day-wa/send" in EV and "שלח דוח ערב עכשיו" in EV, "כפתור בניהול")
# 12. [02/11 אייל] שליחה ידנית: d=יום → סוף אותו יום; לפני 04:00 → אתמול; אחרת עכשיו
N0 = dt.datetime(2026, 11, 2, 0, 10, tzinfo=IL)
tg = W.day_wa_target(N0)
ck(tg.date() == DAY and (tg.hour, tg.minute) == (23, 59) and tg.tzinfo is IL, tg)
ck(W.day_wa_target(N0, "2026-10-30").date() == dt.date(2026, 10, 30), "d")
ck(W.day_wa_target(N0, "זבל") == N0, "d לא תקין")
N1 = dt.datetime(2026, 11, 2, 14, 0, tzinfo=IL)
ck(W.day_wa_target(N1) == N1, "בצהריים = עכשיו")
ck("day_wa_target(" in SRC.split('@app.route("/api/day-wa/send"')[1][:1500], "ראוט משתמש ביעד")
print("OK", n, "checks")
