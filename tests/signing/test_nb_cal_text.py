# tests/signing/test_nb_cal_text.py — אייל 20/10: "אני רוצה שהפגישות ליומן מאפי יגיעו כמו מנדלן וואן"
# כותרת 'פגישה עם בעל נכס - <שם>', כתובת מלאה בשדה המיקום, פרטי הנכס + טלפון + הערות בעל הנכס בתיאור.
import sys, os, ast, re
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
ns = {"re": re}
for node in ast.parse(src).body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_nb_cal_text", "_newborn_price"):
        exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
f = ns["_nb_cal_text"]
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
row = {"עיר": "קרית ביאליק", "שכונה": "נאות אפק", "סוג עסקה": "מכירה", "מחיר": "1780000",
       "תיאור נכס": "דירה · 4 חד' · 110 מ\"ר · קומה 4. הבנין חדש בן 6 שנים בלבד!\nמרפסת שמש"}
rec = {"status": "meeting", "addr": "עוזי חיטמן 1", "owner": "גני", "price": "1780000", "ophone": "0533412796", "note": ""}
s, d, loc = f(rec, row)
ck(s == "פגישה עם בעל נכס - גני", s)
ck(loc == "עוזי חיטמן 1, נאות אפק, קרית ביאליק", loc)
lines = d.split("\n")
ck(lines[0] == "למכירה: דירה, 4 חד', 110 מ\"ר, קומה 4, עוזי חיטמן 1, קרית ביאליק 1,780,000 ₪", lines[0])
ck(lines[1] == "טלפון: 0533412796", lines[1])
ck("הערות בעל הנכס:\nהבנין חדש בן 6 שנים בלבד!\nמרפסת שמש" in d, d)
ck("Family Bot" not in d, "no internal brand line")
# פולו-אפ + הערת הסוכן + בלי שם בעלים
s2, d2, _ = f(dict(rec, status="followup", owner="", note="להתקשר אחרי החגים"), row)
ck(s2 == "פולו-אפ לבעל נכס", s2)
ck("הערה: להתקשר אחרי החגים" in d2, d2)
# שורה ישנה: תיאור חופשי בלי פירוט, עיר כבר בכתובת, השכרה
s3, d3, loc3 = f(dict(rec, addr="הרצל 5 קרית ים", price="5000"),
                 {"עיר": "קרית ים", "סוג עסקה": "השכרה", "תיאור נכס": "דירה מקסימה ליד הים"})
ck(loc3 == "הרצל 5 קרית ים", loc3)
ck(d3.split("\n")[0] == "להשכרה: הרצל 5 קרית ים 5,000 ₪", d3)
ck("הערות בעל הנכס:\nדירה מקסימה ליד הים" in d3, d3)
# בלי שורת הנכס בכלל (לא נמצאה) — מה שיש ברשומה
s4, d4, loc4 = f(rec, None)
ck(s4 == "פגישה עם בעל נכס - גני" and loc4 == "עוזי חיטמן 1" and d4.startswith("למכירה: עוזי חיטמן 1 1,780,000 ₪"), (s4, loc4, d4))
print("OK", n, "checks")
