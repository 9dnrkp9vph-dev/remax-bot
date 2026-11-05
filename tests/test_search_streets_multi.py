"""05/11 (אייל, עריכת הקונה אבי: '3 חדרים מעלית מרפסת ממד / נווה גנים מוצקין / וברחוב החשמונאים / וברחוב לוי אשכול'
— 'אם אני מוסיף שכונה או רחוב בסוף זה יחפש ויטפס לראש הרשימה'): כל 'ברחוב X' בטקסט נספר, נכס ברחוב שביקשו — ראשון,
גם כשהוא בשכונה אחרת מזו שנכתבה (החשמונאים ולוי אשכול = לב מוצקין)."""
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

g = load("score_match", "search_listings_in_sheet", "_query_streets", "_search_nb_tier")
g.update({"_prop_epoch": lambda r: 0, "_canon_key": lambda n: n, "fetch_sheet_rows": lambda: []})
qs, search = g["_query_streets"], g["search_listings_in_sheet"]

TEXT = "מחפש דירה 3 חדרים מעלית מרפסת ממד\nנווה גנים מוצקין\nוברחוב החשמונאים\nוברחוב לוי אשכול עד 1,600,000"
print("זיהוי רחובות מהטקסט")
check("שני הרחובות מזוהים", qs({"_qtext": TEXT}) == ["החשמונאים", "לוי אשכול"], qs({"_qtext": TEXT}))
check("רחוב מה-AI + מהטקסט, בלי כפילות", qs({"street": "החשמונאים", "_qtext": TEXT}) == ["החשמונאים", "לוי אשכול"])
check("'ברחוב הרצל 12, קרית ביאליק' → הרצל 12", qs({"_qtext": "דירה ברחוב הרצל 12, קרית ביאליק"}) == ["הרצל 12"])
check("בשורה אחת: 'ברחוב א וברחוב ב'", qs({"_qtext": "דירה ברחוב תדהר וברחוב הערבה"}) == ["תדהר", "הערבה"])
check("שדרות", qs({"_qtext": "דירה בשדרות ויצמן"}) == ["ויצמן"], qs({"_qtext": "דירה בשדרות ויצמן"}))
check("בלי 'רחוב' — כלום", qs({"_qtext": "3 חדרים בנווה גנים"}) == [])

def row(street, nb, lid, rooms="3", price="1,550,000", tags="מעלית · מרפסת · ממד"):
    return {"סוג עסקה": "מכירה", "עיר / ישוב": "קרית מוצקין", "שכונה": nb, "כתובת": street, "מספר בית": "",
            "חדרים": rooms, "מחיר": price, "סוג נכס": "דירה", "קומה": "", "סוכן 1": "", "מספר מודעה": lid, "תגיות": tags}
R = [row("תדהר", "נווה גנים", "ng1"), row("זבולון המר", "נווה גנים", "ng2"),
     row("החשמונאים", "לב מוצקין, בנה ביתך", "hash", price="1,300,000"),       # שכונה אחרת, רחוק מהתקציב
     row("לוי אשכול", "לב מוצקין, בנה ביתך", "levi", rooms="4"),
     row("ורד", "לב מוצקין, בנה ביתך", "other", price="1,300,000")]
q = {"city": "קרית מוצקין", "neighborhood": "נווה גנים", "rooms_min": 3, "rooms_max": 3, "budget_max": 1600000,
     "must_have": ["מעלית", "מרפסת", 'ממ"ד'], "_qtext": TEXT}
o = [r["מספר מודעה"] for _, r, _ in search(q, rows=R)]
print("החיפוש")
check("הרחובות שביקשו ראשונים", set(o[:2]) == {"hash", "levi"}, o)
check("אחריהם נווה גנים", set(o[2:4]) == {"ng1", "ng2"}, o)
check("שכונה אחרת שלא ביקשו — לא נכנסת", "other" not in o, o)
t = g["_search_nb_tier"](q)
check("'התאמות חדשות': נכס ברחוב שביקשו לא נחשב שכונה אחרת", t(R[2]) == 0, t(R[2]))

src = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
m = re.search(r"function matchQuery\(b\)\{.*?\n\}", src, re.S)
check("'מה מחפש' לא נחתך ב-160 תווים", m and ".slice(0, 160)" not in m.group(0), m and m.group(0)[-160:])

print("\n%d failed" % fails)
sys.exit(1 if fails else 0)
