"""05/11 (אייל: 'החיפוש בשכונת נווה גנים — למה התוצאות של נווה גנים לא בראש?' → 'כן תבנה את שניהם'):
(א) חיפוש שכונה = סדר קשיח: השכונה המבוקשת → בלי שכונה ידועה → שכונה אחרת; 'התאמות חדשות' בלי שכונה אחרת;
(ב) נכס בלי שכונה ביד2 — השכונה מהרחוב (מפת הרחובות של OSM + נכסי המשרד), בלי לכתוב לטבלה."""
import ast, os, re, sys, logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SRC = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)
TOP = {}
for n in TREE.body:
    if isinstance(n, ast.FunctionDef):
        TOP[n.name] = n
    elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
        TOP[n.targets[0].id] = n
SKIP = {"fetch_sheet_rows", "fetch_sheet_rows_deal", "_prop_epoch", "_canon_key"}

def load(*names):
    need, order, stack = set(), [], list(names)
    while stack:
        nm = stack.pop()
        if nm in need or nm not in TOP or nm in SKIP:
            continue
        need.add(nm)
        for sub in ast.walk(TOP[nm]):
            if isinstance(sub, ast.Name) and sub.id in TOP:
                stack.append(sub.id)
    for n in TREE.body:
        key = n.name if isinstance(n, ast.FunctionDef) else (
            n.targets[0].id if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) else None)
        if key in need:
            order.append(n)
    g = {"re": re, "os": os, "logging": logging, "time": __import__("time"), "log": logging.getLogger("t"), "__file__": os.path.join(ROOT, "app.py")}
    exec(compile(ast.Module(body=order, type_ignores=[]), "app_extract", "exec"), g)
    return g

fails = 0
def check(name, cond, detail=""):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "  →  " + repr(detail)))
    if not cond:
        fails += 1

def row(street, nb="", city="קרית מוצקין", rooms="3", price="1,550,000", lid="", tags=""):
    return {"סוג עסקה": "מכירה", "עיר / ישוב": city, "שכונה": nb, "כתובת": street, "מספר בית": "",
            "חדרים": rooms, "מחיר": price, "סוג נכס": "דירה", "קומה": "", "סוכן 1": "", "מספר מודעה": lid or street,
            "תגיות": tags}

OFFICE = [row("הרב קוק", "מוצקין הותיקה"), row("הרב קוק", "מוצקין הותיקה"),     # עדויות: הרב קוק = מוצקין הותיקה
          row("זבולון המר", "לב מוצקין"), row("זבולון המר", "לב מוצקין")]       # עדויות גוברות על OSM (נווה גנים)
g = load("score_match", "search_listings_in_sheet", "_row_nb_guess", "_search_nb_tier")
g.update({"_prop_epoch": lambda r: 0, "_canon_key": lambda n: n, "fetch_sheet_rows": lambda: OFFICE})
guess, score, search = g["_row_nb_guess"], g["score_match"], g["search_listings_in_sheet"]

print("ב: שכונה מהרחוב")
check("החשמונאים 39, מוצקין → לב מוצקין (OSM)", "לב מוצקין" in guess(row("החשמונאים 39")), guess(row("החשמונאים 39")))
check("תדהר → נווה גנים", guess(row("תדהר")) == "נווה גנים", guess(row("תדהר")))
check("הנוטר, חיפה → קרית חיים מזרחית", guess(row("הנוטר", city="חיפה")) == "קרית חיים מזרחית", guess(row("הנוטר", city="חיפה")))
check("קריית/קרית ו'רחוב' לא מפריעים", guess(row("רחוב תדהר 7", city="קריית מוצקין")) == "נווה גנים")
check("רחוב לא מוכר → ריק", guess(row("רחוב שלא קיים")) == "")
check("נכס עם שכונה רשומה — לא נוגעים", guess(row("תדהר", nb="משהו")) == "")
check("עדויות הנכסים גוברות על OSM", guess(row("זבולון המר")) == "לב מוצקין", guess(row("זבולון המר")))
check("עדות מנכסי המשרד בלבד", guess(row("הרב קוק 3")) == "מוצקין הותיקה", guess(row("הרב קוק 3")))

print("ב: הניקוד משתמש בשכונה שהושלמה")
q = {"city": "קרית מוצקין", "neighborhood": "נווה גנים", "rooms_min": 3, "rooms_max": 3, "budget_max": 1600000}
check("תדהר בלי שכונה = נווה גנים (+30, כמו רשום)", score(row("תדהר"), q) == score(row("תדהר", nb="נווה גנים"), q))
check("החשמונאים — שכונה אחרת, מחוץ ל-±10% מהתקציב → לא נכנס", score(row("החשמונאים", price="1,300,000"), q) == 0)

print("א: סדר קשיח בחיפוש שכונה")
R = [row("ורד", "לב מוצקין", rooms="3", price="1,620,000", lid="other_nb", tags="מעלית · מרפסת · ממד"),
     row("רחוב שלא קיים", rooms="3", price="1,590,000", lid="no_nb", tags="מעלית · מרפסת · ממד"),
     row("מנחם בגין", "נווה גנים", rooms="5", price="1,590,000", lid="in_nb")]
qa = dict(q, must_have=["מעלית", "מרפסת", 'ממ"ד'])
o = [r["מספר מודעה"] for _, r, _ in search(qa, rows=R)]
check("נווה גנים → בלי שכונה → שכונה אחרת", o == ["in_nb", "no_nb", "other_nb"], o)
t = g["_search_nb_tier"]({"city": "קרית מוצקין"})
check("בלי שכונה בחיפוש — אין שכבה", t is None)

print("א: 'התאמות חדשות' בדף הקונה")
import effie_v2 as ev
ev._BP_NB_TIER = g["_search_nb_tier"]
src = {"office": {"other": dict(row("ורד", "לב מוצקין", price="1,620,000"), _ep=10),
                  "no": dict(row("רחוב שלא קיים", price="1,590,000"), _ep=10),
                  "in": dict(row("מנחם בגין", "נווה גנים", rooms="3", price="1,590,000"), _ep=10)}}
got = ev.bpage_new_matches(q, src, set(), 0, 1600000, lambda r, qq: 90)
check("שכונה אחרת לא מוצמדת; השכונה המבוקשת ראשונה", [x["key"] for x in got] == ["in", "no"], got)
ev._BP_NB_TIER = None
got2 = ev.bpage_new_matches(q, src, set(), 0, 1600000, lambda r, qq: 90)
check("בלי החיבור — כמו קודם (3)", len(got2) == 3, got2)

print("\n%d failed" % fails)
sys.exit(1 if fails else 0)
