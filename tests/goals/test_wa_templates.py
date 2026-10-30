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

# ── פרמטרים לתבנית השבועית ───────────────────────────────────────────────────
p = g.weekly_tpl_params(row)
ck(len(p) == 10, p)
ck(p[0] == "אור" and p[1] == "18–24 באוקטובר", p[:2])
ck(p[2] == "0 מתוך 2", p[2])
ck(p[5] == "14 מתוך 16.5 (3 מהחתמה)", p[5])
ck(p[7] == "אין נתון", p[7])
ck(p[8] == "2", p[8])
ck("להוריד" in p[9] and "פגישות מנכס נולד ל-1 ביום" in p[9], p[9])
ck(all("\n" not in x and "\t" not in x and x.strip() for x in p), "Meta: no newlines / empty")
row_ok = dict(row, counts=dict(row["counts"], buyers=20), rec={k: ("keep", v) for k, v in row["daily"].items()})
ck(g.weekly_tpl_params(row_ok)[5] == "20 מתוך 16.5 (3 מהחתמה) — הושג", g.weekly_tpl_params(row_ok)[5])
ck(g.weekly_tpl_params(row_ok)[9] == "להשאיר את היעדים כמו שהם", g.weekly_tpl_params(row_ok)[9])

# ── ההודעה בטקסט חופשי (בחלון 24 ש' / בלי תבנית) — ברורה, בלי '/' בתאריכים ──
msg = g.weekly_message(row, "RE/MAX Family", "https://x/v2/goals")
ck("בRE/MAX" not in msg and "18–24 באוקטובר" in msg, msg.split("\n")[0])
ck("\n\nגיוס נכסים: 0 מתוך 2\n" in msg, msg)

# ── חודשי ────────────────────────────────────────────────────────────────────
mrow = dict(row, prev={"listings": 1, "meetings": 3, "nb_wa": 0, "buyers": 10, "past_clients": 0, "reviews": 1},
            prev_met=1, from_="2026-10-01")
mp = g.monthly_tpl_params(mrow, "אוקטובר 2026")
ck(len(mp) == 11 and mp[1] == "אוקטובר 2026", mp)
ck(mp[3] == "0 מתוך 11 (בחודש הקודם 3)", mp[3])
ck(mp[9] == "1", mp[9])

# ── בעל המשרד ────────────────────────────────────────────────────────────────
M = {"label": "אוקטובר 2026", "rows": [row], "total": {"met": 3, "goals_n": 6}, "top": [row], "inactive": ["א", "ב"]}
op = g.owner_tpl_params("חודשי", M)
ck(len(op) == 7 and op[0] == "חודשי" and op[1] == "אוקטובר 2026" and op[2] == "1" and op[3] == "3 מתוך 6", op)
ck(op[4] == "אור צוקרמן (2/6)" and op[5] == "2" and op[6] == "3", op)

# ── השליחה: תבנית כשמוגדרת ב-env, אחרת טקסט ─────────────────────────────────
calls = []
G = {"send_text": lambda to, t: calls.append(("text", to, t)) or True,
     "send_template": lambda to, name, params, btn=None: calls.append(("tpl", to, name, params, btn)) or True}
os.environ.pop("WA_TPL_GOALS_WEEKLY", None)
ck(g.goals_send(G, "9725", "WA_TPL_GOALS_WEEKLY", "טקסט", ["a"]) and calls[-1][0] == "text", calls)
os.environ["WA_TPL_GOALS_WEEKLY"] = "goals_weekly"
ck(g.goals_send(G, "9725", "WA_TPL_GOALS_WEEKLY", "טקסט", ["a"], "weekly") and calls[-1] == ("tpl", "9725", "goals_weekly", ["a"], "weekly"), calls)
G2 = {"send_text": G["send_text"]}           # אין send_template (גרסה ישנה) → טקסט
ck(g.goals_send(G2, "9725", "WA_TPL_GOALS_WEEKLY", "טקסט", ["a"]) and calls[-1][0] == "text", calls)
os.environ.pop("WA_TPL_GOALS_WEEKLY")
print("wa templates ok", N[0])
