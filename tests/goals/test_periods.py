# tests/goals/test_periods.py — [GOALS4 29/10] אייל: "אני רוצה שהיעדים יהיו מתחילת שבוע ומתחילת חודש".
# build_office מחזיר לכל סוכן ולסכום גם week / month (מתחילת השבוע / החודש עד היום) מול היעד לשבוע / לחודש,
# ו-pace (כמה מהתקופה עבר). python3 tests/goals/test_periods.py
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import goals as g

N = [0]
def ck(c, m=""):
    assert c, m
    N[0] += 1

canon = lambda n: " ".join(str(n or "").split())
A, B = "דנה כהן", "רון לוי"
DAY = dt.date(2026, 10, 29)                      # חמישי. השבוע מ-25/10, החודש מ-1/10


def ts(d, h=11):
    return dt.datetime(d.year, d.month, d.day, h, 0, tzinfo=g._IL).timestamp()


def s(d, h=11):
    return f"{d.day:02d}/{d.month:02d}/{d.year} {h:02d}:00"


buyers = [{"agent": A, "date": s(DAY)},                                    # היום
          {"agent": A, "date": s(dt.date(2026, 10, 26)), "summary": "מהחתמת מתעניין"},   # השבוע
          {"agent": A, "date": s(dt.date(2026, 10, 5))},                    # החודש, לא השבוע
          {"agent": A, "date": s(dt.date(2026, 9, 30))},                    # חודש קודם
          {"agent": B, "date": s(dt.date(2026, 10, 27))}]
activity = [{"ts": ts(DAY), "name": A, "action": g.ACT_REMIND, "detail": "501"},
            {"ts": ts(dt.date(2026, 10, 25)), "name": A, "action": g.ACT_REMIND, "detail": "502"},
            {"ts": ts(dt.date(2026, 10, 2)), "name": A, "action": g.ACT_REMIND, "detail": "503"},
            {"ts": ts(dt.date(2026, 10, 27)), "name": A, "action": g.ACT_NB_WA + " · x", "detail": "k1"}]
sigs = [{"agent": A, "address": "הרצל 5", "type": "בלעדיות", "signed": True, "ts": s(dt.date(2026, 10, 27))},
        {"agent": A, "address": "ויצמן 3", "type": "בלעדיות", "signed": True, "ts": s(dt.date(2026, 10, 12))}]
src = {"nb": {}, "buyers": buyers, "bpages": [], "activity": activity, "reviews": [], "missed": [],
       "sigs": sigs, "roster": [A, B], "active": [A, B], "seen": [A], "staff": [], "cfg": {}}

o = g.build_office(dict(src), DAY, canon)
r = {x["name"]: x for x in o["rows"]}[A]

# היום — יומן הפעולות מתחילת החודש לא מנפח את 'היום' (רק התזכורת של היום)
ck(r["counts"]["past_clients"] == 1, r["counts"])
ck(r["counts"]["buyers"] == 1, r["counts"])

# השבוע (25/10–29/10)
w = r["week"]["counts"]
ck(w["buyers"] == 2 and w["buyers_sign"] == 1, w)
ck(w["past_clients"] == 2 and w["nb_wa"] == 1, w)
ck(w["listings"] == 1, w)
ck("followups" not in w and "missed" not in w, w)

# החודש (1/10–29/10)
m = r["month"]["counts"]
ck(m["buyers"] == 3 and m["past_clients"] == 3 and m["listings"] == 2, m)

# היעדים: החודש = החלק של הסוכן ביעד המשרד (שני סוכנים פעילים), השבוע = קצב × 5.5 (גיוס — לשבוע)
ck(r["month"]["targets"] == r["monthly"], (r["month"]["targets"], r["monthly"]))
ck(r["month"]["targets"]["meetings"] == 80 and r["month"]["targets"]["listings"] == 40, r["month"]["targets"])
ck(r["week"]["targets"]["meetings"] == 19, r["week"]["targets"])          # 80 / 23.5 × 5.5 = 18.7 → 19
ck(r["week"]["targets"]["listings"] == 10, r["week"]["targets"])          # 40 / 31 × 7 = 9.03 → 10

# הסכום: השבוע = כל השורות; יעד המשרד לחודש כפי שנקבע; לשבוע — מעוגל למעלה
T = o["total"]
ck(T["week"]["counts"]["buyers"] == 3 and T["month"]["counts"]["buyers"] == 4, (T["week"]["counts"], T["month"]["counts"]))
ck(T["month"]["targets"] == g.OFFICE_MONTH, T["month"]["targets"])
ck(T["week"]["targets"]["meetings"] == 38, T["week"]["targets"])          # 160 × 5.5 / 23.5 = 37.4 → 38

# הקצב: חמישי = 4.5 מתוך 5.5 ימי עבודה; אוקטובר עד 29 = 21 מתוך 23.5
P = T["pace"]
ck(abs(P["week"] - 4.0 / 5.5) < 0.002 or abs(P["week"] - 5.0 / 5.5) < 0.002, P)
ck(P["week_from"] == "2026-10-25" and P["month_from"] == "2026-10-01" and P["month_to"] == "2026-10-31", P)
ck(0.8 < P["month"] < 1.0, P)
ck(r["pace"] == P, r["pace"])

# צוות (office=False): יעד = סכום הקצבים של הפעילים
o2 = g.build_office(dict(src), DAY, canon, office=False)
ck(o2["total"]["month"]["targets"]["meetings"] == 160, o2["total"]["month"]["targets"])

# מקור שנכשל → None בשבוע ובחודש, בלי ליפול
o3 = g.build_office(dict(src, buyers=RuntimeError("x")), DAY, canon)
r3 = {x["name"]: x for x in o3["rows"]}[A]
ck(r3["week"]["counts"]["buyers"] is None and r3["month"]["counts"]["buyers"] is None, r3["week"])

# span_start: שבוע שמתחיל בחודש הקודם
ck(g.span_start(dt.date(2026, 11, 3)) == dt.date(2026, 11, 1), g.span_start(dt.date(2026, 11, 3)))
ck(g.span_start(dt.date(2026, 12, 2)) == dt.date(2026, 11, 29), g.span_start(dt.date(2026, 12, 2)))

print(f"OK {N[0]}")
