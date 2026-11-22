# tests/goals/test_wa_templates.py — [GOALS-TPL 29/10] אייל: "נשלח לא יפה ולא ברור" — הסיכומים יוצאים בתבניות ייעודיות
# (שורה לכל יעד) במקום family_update שמשטחת הכל לשורה אחת עם ' | '. python3 tests/goals/test_wa_templates.py
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import goals as g

N = [0]
def ck(c, m=""):
    assert c, m
    N[0] += 1

K = g.GOAL_KEYS
row = {"name": "אור צוקרמן", "from": "2026-10-18", "to": "2026-10-24", "met": 2, "goals_n": 6,
       "counts": {"listings": 0, "meetings": 0, "nb_wa": 1, "buyers": 14, "buyers_sign": 3, "past_clients": 0, "reviews": None},
       "targets": {"listings": 2, "meetings": 11, "nb_wa": 55, "buyers": 16.5, "past_clients": 27.5, "reviews": 11},
       "daily": {"listings": 2, "meetings": 2, "nb_wa": 10, "buyers": 3, "past_clients": 5, "reviews": 2},
       "rec": {"listings": ("keep", 2), "meetings": ("down", 1), "nb_wa": ("down", 7), "buyers": ("keep", 3),
               "past_clients": ("down", 3), "reviews": ("keep", 2)}}

# ── תאריכים בלי '/' (בעברית '18/10–24/10' מתהפך) ───────────────────────────
ck(g.span_he("2026-10-18", "2026-10-24") == "18–24 באוקטובר", g.span_he("2026-10-18", "2026-10-24"))
ck(g.span_he("2026-10-25", "2026-10-31") == "25–31 באוקטובר")
ck(g.span_he("2026-11-29", "2026-12-05") == "29 בנובמבר – 5 בדצמבר", g.span_he("2026-11-29", "2026-12-05"))

# [22/11] הבדיקה עודכנה ל-GOALS4 (29/10): weekly_tpl_params/monthly_tpl_params/owner_tpl_params הוחלפו ב-
# weekly_params/monthly_params (10 פרמטרים: שם, תקופה, 6 יעדים, שורת עידוד, קישור), בלי המלצות לסוכן.
# השליחה עצמה (goals_send) נבדקת ב-tests/goals/test_weekly.py; סיכום בעל המשרד ב-tests/goals/test_monthly.py.
LINK = "https://x/v2/goals"

# ── פרמטרים לתבנית השבועית ───────────────────────────────────────────────────
p = g.weekly_params(row, LINK)
ck(len(p) == 10, p)
ck(p[0] == "אור" and p[1] == "שבוע 18–24 באוקטובר", p[:2])
ck(p[2] == "0 מתוך 2", p[2])
ck(p[5] == "14 מתוך 16.5 (3 מהחתמה)", p[5])
ck(p[7] == "אין נתון", p[7])
ck("2 מתוך 6" in p[8], p[8])
ck(p[9] == LINK, p[9])
ck(all("\n" not in x and "\t" not in x and x.strip() for x in p), "Meta: no newlines / empty")
row_ok = dict(row, counts=dict(row["counts"], buyers=20))
ck(g.weekly_params(row_ok, LINK)[5] == "20 מתוך 16.5 (3 מהחתמה) — הושג", g.weekly_params(row_ok, LINK)[5])

# ── ההודעה בטקסט חופשי (בחלון 24 ש' / בלי תבנית) — ברורה, בלי '/' בתאריכים ──
msg = g.weekly_message(row, "RE/MAX Family", LINK)
ck("בRE/MAX" not in msg and "18–24 באוקטובר" in msg, msg.split("\n")[0])
ck("\n\nגיוס נכסים: 0 מתוך 2\n" in msg, msg)

# ── חודשי ────────────────────────────────────────────────────────────────────
mrow = dict(row, prev={"listings": 1, "meetings": 3, "nb_wa": 0, "buyers": 10, "past_clients": 0, "reviews": 1},
            prev_met=1, from_="2026-10-01")
mp = g.monthly_params(mrow, "אוקטובר 2026", LINK)
ck(len(mp) == 10 and mp[1] == "חודש אוקטובר 2026", mp)
ck(mp[3] == "0 מתוך 11 (בחודש הקודם 3)", mp[3])
ck("בחודש הקודם: 1 מתוך 6" in mp[8], mp[8])
print("wa templates ok", N[0])
