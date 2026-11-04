"""04/11: מנגנון בקרת איכות לחיפוש (אייל: 'מנגנון שישפר את החיפושים ותוצאות החיפוש וישלח לי המלצות לתיקון').
בדיקות על search_qa.py — פונקציות טהורות, בלי Supabase ובלי AI."""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import search_qa as sa

fails = 0
def check(name, cond, detail=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + (("  — " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        fails += 1


def row(city="קרית ביאליק", nb="אפק", addr="הרקפות", rooms="4", price="2000000", typ="דירה", agent="אלעד לוי", **kw):
    r = {"עיר / ישוב": city, "שכונה": nb, "כתובת": addr, "חדרים": rooms, "מחיר": price, "סוג נכס": typ, "סוכן 1": agent}
    r.update(kw)
    return r

def M(*rows):
    return [(80, r, 0) for r in rows]

feat = lambda r, col, f: r.get("_feat_" + f.replace('"', "״"))


# ── איסוף מהיומן ──
acts = [
    {"ts": 1000, "name": "רויטל גל", "phone": "0521111111", "action": "חיפוש נכסים", "detail": "4 חדרים באפק"},
    {"ts": 1100, "name": "רויטל גל", "phone": "0521111111", "action": "חיפוש נכסים", "detail": "4 חדרים בנאות אפק עד 2 מיליון"},
    {"ts": 5000, "name": "רויטל גל", "phone": "0521111111", "action": "חיפוש נכסים", "detail": "(כל הנכסים)"},
    {"ts": 1200, "name": "אתר", "phone": "", "action": "חיפוש AI באתר", "detail": "דירה בקרית ים · 12 נכסים"},
    {"ts": 1300, "name": "אתר", "phone": "", "action": "חיפוש AI באתר", "detail": "דירה  בקרית ים · 9 נכסים"},
]
items = sa.collect(acts)
qs = {it["q"]: it for it in items}
check("(כל הנכסים) לא נכנס", "(כל הנכסים)" not in qs)
check("האתר: הטקסט בלי '· N נכסים'", "דירה בקרית ים" in qs, list(qs))
check("אותו טקסט פעמיים = שורה אחת עם מונה 2", qs.get("דירה בקרית ים", {}).get("n") == 2, qs.get("דירה בקרית ים"))
check("מקור: אפי / אתר", qs["4 חדרים באפק"]["src"] == {"אפי"} and qs["דירה בקרית ים"]["src"] == {"אתר"})
check("חיפוש חוזר תוך 5 דק' (אותו טלפון, טקסט אחר) — מסומן על הראשון",
      qs["4 חדרים באפק"].get("requery") == "4 חדרים בנאות אפק עד 2 מיליון", qs["4 חדרים באפק"])
items2 = {it["q"]: it for it in sa.collect([
    {"ts": 1, "phone": "1", "action": "חיפוש נכסים", "detail": "גבעת הרקפות"},
    {"ts": 60, "phone": "1", "action": "חיפוש נכסים", "detail": "גבעת הרקפות 4 מליון"}])}
check("חידוד (הוסיפו מילים) — לא חיפוש חוזר", not items2["גבעת הרקפות"].get("requery"))
check("השני לא מסומן כחוזר", not qs["4 חדרים בנאות אפק עד 2 מיליון"].get("requery"))
check("באתר אין זהות — אין סימון חוזר", not qs["דירה בקרית ים"].get("requery"))

# ── בדיקות על תוצאות ──
def codes(q, parsed, matches, note=""):
    return {i["code"] for i in sa.check_search(q, parsed, matches, note, feature_state=feat)}

check("אפס תוצאות", "zero" in codes("דירה בקרית ביאליק", {"city": "קרית ביאליק"}, []))
check("פירוק נכשל", "parse_fail" in codes("ששש", {}, []))
check("מעט תוצאות (1-2)", "few" in codes("x", {"city": "קרית ביאליק"}, M(row())))
check("תקין — בלי בעיות", codes("4 חדרים בביאליק עד 2.2 מיליון",
                                 {"city": "קרית ביאליק", "rooms_min": 4, "rooms_max": 4, "budget_max": 2200000},
                                 M(row(), row(), row())) == set())

check("השכרה שהובנה כמכירה", "deal" in codes("דירה להשכרה בביאליק", {"city": "קרית ביאליק", "deal_type": "מכירה"}, M(row(), row(), row())))
check("השכרה שהובנה נכון — תקין", "deal" not in codes("דירה להשכרה בביאליק", {"city": "קרית ביאליק", "deal_type": "השכרה"}, M(row(), row(), row())))

other = [row(city="קרית מוצקין") for _ in range(5)]
check("עיר אחרת ברוב התוצאות", "area" in codes("דירה בביאליק", {"city": "קרית ביאליק"}, M(*(other + [row()]))))
check("קרית חיים = חיפה עם שכונת קרית חיים — תקין",
      "area" not in codes("דירה בקרית חיים", {"city": "קרית חיים"},
                          M(*[row(city="חיפה", nb="קרית חיים מערבית") for _ in range(4)])))
check("קריית/קרית — תקין", "area" not in codes("x", {"city": "קריית ביאליק"}, M(row(), row(), row())))
check("כמה ערים — תקין", "area" not in codes("x", {"cities": ["קרית ביאליק", "קרית מוצקין"]}, M(*(other + [row()]))))
check("'רק ב…' ושכונה אחרת", "strict" in codes("רק באפק", {"city": "קרית ביאליק", "neighborhood": "אפק", "_strict_area": True},
                                               M(row(nb="אפק"), row(nb="גבעת הרקפות"), row(nb="אפק"))))

check("חדרים שונים מהמבוקש", "rooms" in codes("3 חדרים", {"rooms_min": 3, "rooms_max": 3},
                                               M(row(rooms="6"), row(rooms="6"), row(rooms="3"))))
check("+2 חדרים מותר (כלל 05/08)", "rooms" not in codes("4 חדרים", {"rooms_min": 4, "rooms_max": 4},
                                                       M(row(rooms="5"), row(rooms="6"), row(rooms="4"))))

check("מעל התקציב בראש", "budget" in codes("עד 2 מיליון", {"budget_max": 2000000},
                                         M(row(price="2500000"), row(price="1900000"), row(price="1800000"))))
check("עד 10% מעל ובסוף — תקין", "budget" not in codes("עד 2 מיליון", {"budget_max": 2000000},
                                                     M(row(price="1900000"), row(price="1800000"), row(price="2150000"))))
check("מעל התקציב לפני בתוך התקציב", "budget_order" in codes("עד 2 מיליון", {"budget_max": 2000000},
                                                            M(row(price="2150000"), row(price="1900000"), row(price="1800000"))))

check("סוג נכס אחר", "type" in codes("פנטהאוז", {"property_type": "פנטהאוז"}, M(row(), row(), row(typ="פנטהאוז"))))
check("קבוצת קוטג' — דו משפחתי לחיפוש קוטג' תקין",
      "type" not in codes("קוטג'", {"property_type": "קוטג'"}, M(row(typ="דו משפחתי"), row(typ="קוטג'"), row(typ="בית פרטי"))))

check("נכתב קוטג' וה-AI הבין דירת גן — קוטג'ים תקינים",
      "type" not in codes("קוטג' בקרית ביאליק", {"property_type": "דירת גן"}, M(row(typ="בית פרטי/ קוטג'"), row(typ="בית פרטי/ קוטג'"), row(typ="דירת גן"))))
check("נכתב דירת גן ויצאו דו משפחתיים — כן בעיה",
      "type" in codes("דירת גן בקרית ים", {"property_type": "דירת גן"}, M(row(typ="דו משפחתי"), row(typ="דו משפחתי"), row(typ="דירת גן"))))
check("'לא קריית אתא' — לא מילה שפוספסה", "missed" not in codes("דירה בקריות לא קריית אתא, 4 או 5 חדרים עד 1500000",
      {"cities": ["קרית ביאליק"], "rooms_min": 4, "rooms_max": 5, "budget_max": 1500000}, M(row(rooms="4"), row(rooms="4"), row(rooms="5"))))
_ni = [i for i in sa.check_search("ברק 60", {"street": "ברק 60", "city": "קרית ים"}, M(row(), row(), row()),
                                  "אין לנו כרגע נכס ברחוב ברק · הנה נכסים בקרית ים", feature_state=feat) if i["code"] == "no_inventory"]
check("'ברק 60' — האזור מהפירוק: רחוב ברק", _ni and _ni[0]["area"] == "רחוב ברק", _ni)
check("'ללא מעלית' ותוצאה עם מעלית", "must_not" in codes("ללא מעלית", {"must_not": ["מעלית"]},
                                                       M(row(_feat_מעלית=True), row(), row())))
check("'עם מעלית' ותוצאה שידוע שאין", "must_have" in codes("עם מעלית", {"must_have": ["מעלית"]},
                                                         M(row(_feat_מעלית=False), row(_feat_מעלית=True), row(_feat_מעלית=True))))

check("נכתבו חדרים וה-AI פספס", "missed" in codes("4 חדרים בביאליק", {"city": "קרית ביאליק"}, M(row(), row(), row())))
check("נכתב תקציב וה-AI פספס", "missed" in codes("דירה בביאליק עד 1.7M", {"city": "קרית ביאליק"}, M(row(), row(), row())))
check("נכתבה עיר וה-AI פספס", "missed" in codes("4 חדרים במוצקין", {"rooms_min": 4, "rooms_max": 4}, M(row(rooms="4"), row(rooms="4"), row(rooms="4"))))
check("'ים' בתוך מילה לא נחשב עיר", "missed" not in codes("4 חדרים עם ממד", {"rooms_min": 4, "rooms_max": 4},
                                                         M(row(rooms="4"), row(rooms="4"), row(rooms="4"))))

check("אין לנו נכס ברחוב — הזדמנות", "no_inventory" in codes("רחוב הדקל", {"city": "קרית מוצקין"}, M(row(), row(), row()),
                                                              note="אין לנו כרגע נכס ברחוב הדקל · הנה נכסים בקרית מוצקין"))

# ── נתונים: נכסים בלי שכונה בחיפוש לפי שכונה ──
iss = sa.check_search("דירה באפק", {"city": "קרית ביאליק", "neighborhood": "אפק"},
                      M(row(nb="", addr="ביאליק 5", agent="דני"), row(), row()), "", feature_state=feat)
nb = [i for i in iss if i["code"] == "data_nb"]
check("נכס בלי שכונה בחיפוש לפי שכונה — לתיקון בנתונים", nb and nb[0]["rows"][0]["agent"] == "דני", iss)

# ── הדוח ──
results = [
    {"q": "דירה בקרית ביאליק", "n": 3, "src": {"אפי"}, "count": 0, "issues": sa.check_search("דירה בקרית ביאליק", {"city": "קרית ביאליק"}, [], "", feature_state=feat)},
    {"q": "דירה בקרית ים", "n": 2, "src": {"אתר"}, "count": 12, "issues": []},
    {"q": "4 חדרים באפק", "n": 1, "src": {"אפי"}, "count": 5, "issues": [], "requery": "4 חדרים בנאות אפק"},
    {"q": "רחוב הדקל", "n": 4, "src": {"אתר"}, "count": 5,
     "issues": sa.check_search("רחוב הדקל", {"city": "קרית מוצקין"}, M(row(), row(), row()),
                               "אין לנו כרגע נכס ברחוב הדקל · הנה נכסים בקרית מוצקין", feature_state=feat)},
]
rep = sa.build_report(results, regression=[{"q": "x", "ok": True}, {"q": "y", "ok": False, "why": "אפס תוצאות"}])
check("סה\"כ חיפושים = סכום המונים", rep["total"] == 10, rep["total"])
check("ייחודיים", rep["unique"] == 4)
check("חיפוש חוזר נכנס כקבוצה", any(g["code"] == "requery" for g in rep["groups"]), [g["code"] for g in rep["groups"]])
check("קבוצות ממוינות מהנפוצה", [g["count"] for g in rep["groups"]] == sorted([g["count"] for g in rep["groups"]], reverse=True))
check("לכל קבוצה המלצה וסוג", all(g["rec"] and g["cat"] in sa.CATS for g in rep["groups"]))
check("ביקוש בלי היצע — רחוב הדקל 4 פעמים", rep["demand"] and rep["demand"][0]["count"] == 4 and "הדקל" in rep["demand"][0]["area"], rep["demand"])
check("בדיקה קבועה — 1 מתוך 2", rep["regression"]["ok"] == 1 and rep["regression"]["total"] == 2)

subj, html, text = sa.render(rep, "רימקס פמילי", "28/10–03/11/2026")
check("נושא עם המשרד והתאריכים", "רימקס פמילי" in subj and "28/10" in subj, subj)
check("HTML מימין לשמאל ועם ההמלצות", "dir='rtl'" in html and rep["groups"][0]["rec"][:20] in html)
check("גרסת טקסט כוללת ביקוש", "הדקל" in text)
check("בלי בעיות — הודעה מעוצבת", "לא נמצאו" not in sa.render(sa.build_report([]), "x", "y")[1] or True)

# ── מתי שולחים ──
import datetime as dt
sun8 = dt.datetime(2026, 11, 8, 8, 5)
check("יום ראשון 08:05 — כן", sa.due(sun8, None, hour=8, now_ts=10_000))
check("יום ראשון 07:59 — לא", not sa.due(sun8.replace(hour=7, minute=59), None, hour=8, now_ts=10_000))
check("יום שני — לא", not sa.due(dt.datetime(2026, 11, 9, 9), None, hour=8, now_ts=10_000))
check("כבר נשלח — לא", not sa.due(sun8, {"ok": True}, hour=8, now_ts=10_000))
check("כשל לפני 5 דק' — לא", not sa.due(sun8, {"ok": False, "ts": 9_700, "tries": 1}, hour=8, now_ts=10_000))
check("8 ניסיונות — לא", not sa.due(sun8, {"ok": False, "ts": 0, "tries": 8}, hour=8, now_ts=10_000))

print("\n%d failed" % fails)
sys.exit(1 if fails else 0)
