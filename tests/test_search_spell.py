"""18/11: חיפוש רחוב — כתיב מלא/חסר ('בלינסון' ↔ 'בילינסון') והאות הראשונה שה-AI חותך ('ברק 54' → 'רק').
אייל: 'כן תתחיל מ-1 ו-2' (מתוך ניתוח החיפושים)."""
import ast, os, re, sys, logging, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)
TOP = {}
for n in TREE.body:
    if isinstance(n, ast.FunctionDef):
        TOP[n.name] = n
    elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
        TOP[n.targets[0].id] = n

SKIP = {"fetch_sheet_rows", "fetch_sheet_rows_deal", "_prop_epoch", "_canon_key", "_nb_guess_index"}

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
    g = {"re": re, "os": os, "time": time, "logging": logging, "log": logging.getLogger("t"),
         "__file__": os.path.join(ROOT, "app.py")}
    exec(compile(ast.Module(body=order, type_ignores=[]), "app_extract", "exec"), g)
    return g

fails = 0
def check(name, cond, detail=""):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "  →  " + repr(detail)))
    if not cond:
        fails += 1

ROWS = [
    {"כתובת": "משה בילינסון 8", "עיר / ישוב": "חיפה", "שכונה": "קרית חיים מזרחית", "מחיר": "1500000", "חדרים": "4", "סטטוס": "פעילה"},
    {"כתובת": "נעמי שמר 32", "עיר / ישוב": "קרית ביאליק", "שכונה": "נאות אפק", "מחיר": "2000000", "חדרים": "5", "סטטוס": "פעילה"},
    {"כתובת": "אנרי מאטיס 4", "עיר / ישוב": "קרית מוצקין", "שכונה": "משכנות האומנים", "מחיר": "2300000", "חדרים": "5", "סטטוס": "פעילה"},
    {"כתובת": "הרצל 5", "עיר / ישוב": "קרית מוצקין", "שכונה": "", "מחיר": "1200000", "חדרים": "3", "סטטוס": "פעילה"},
    {"כתובת": "דוד שמעוני 3", "עיר / ישוב": "קרית ביאליק", "שכונה": "", "מחיר": "1300000", "חדרים": "3", "סטטוס": "פעילה"},
]
g = load("_street_match", "_search_post_rules", "search_area_note", "_query_streets", "search_listings_in_sheet", "_known_street")
g["fetch_sheet_rows"] = lambda: ROWS
g["fetch_sheet_rows_deal"] = lambda d: []
g["_prop_epoch"] = lambda r: 0
g["_canon_key"] = lambda s: str(s or "").strip()
g["_nb_guess_index"] = lambda: {"קרית ביאליק": {"ברק": "גבעת הרקפות", "יקינטון": "צור שלום"}}
match, post, note, search = g["_street_match"], g["_search_post_rules"], g["search_area_note"], g["search_listings_in_sheet"]

print("כתיב מלא / חסר")
check("בלינסון ↔ משה בילינסון", match("בלינסון 8", "משה בילינסון 8"))
check("ביילינסון ↔ בילינסון", match("ביילינסון 32", "משה בילינסון"))
check("אנרי מטיס ↔ אנרי מאטיס", match("אנרי מטיס", "אנרי מאטיס 4"))
check("נעומי שמר ↔ נעמי שמר", match("נעומי שמר 32", "נעמי שמר 32"))
check("מדויק עדיין עובד (בגין ↔ מנחם בגין)", match("בגין 12", "מנחם בגין"))
check("שמיר לא מתאים לנעמי שמר (שם קצר)", not match("שמיר", "נעמי שמר"))
check("יצחק שמיר לא מתאים לנעמי שמר", not match("יצחק שמיר", "נעמי שמר 32"))
check("שמעון אינו שמעוני", not match("שמעון", "דוד שמעוני 3"))
check("מטיס לבד (3 אותיות בשלד) — לא סלחני", not match("מטיס", "אנרי מאטיס 4"))
check("רחוב אחר לגמרי", not match("ויצמן", "הרצל 5"))

print("האות הראשונה שנחתכה")
p = post({"street": "לינסון 8", "property_type": "דירה"}, "בלינסון 8")
check("'בלינסון 8' → הרחוב כפי שנכתב", p.get("street") == "בלינסון 8", p)
p = post({"street": "רק 54", "property_type": "דירה"}, "ברק 54")
check("'ברק 54' → ברק", p.get("street") == "ברק 54", p)
p = post({"street": "קינטון", "property_type": "דירה"}, "ביקינטון")
check("'ביקינטון' → יקינטון", p.get("street") == "יקינטון", p)
p = post({"street": "הרצל 5", "property_type": "דירה"}, "דירה בהרצל 5")
check("'בהרצל 5' — הרצל נשאר (רחוב מוכר)", p.get("street") == "הרצל 5" and not p.get("_street_alt"), p)
p = post({"street": "ברק 54", "property_type": "דירה"}, "ברק 54")
check("ה-AI צדק — בלי שינוי", p.get("street") == "ברק 54" and not p.get("_street_alt"), p)
p = post({"street": "פתלי 5", "property_type": "דירה"}, "נפתלי 5")
check("אף צורה לא מוכרת — נשמרת גם הצורה שנכתבה", p.get("street") == "פתלי 5" and p.get("_street_alt") == "נפתלי 5", p)
check("…וההודעה מציגה את מה שנכתב", "נפתלי" in note(p, [(50, ROWS[3], 0)]) and "פתלי 5" not in note(p, [(50, ROWS[3], 0)]), note(p, [(50, ROWS[3], 0)]))
check("…והיא נכנסת לרחובות שנבדקים", "נפתלי 5" in g["_query_streets"](dict(p)), g["_query_streets"](dict(p)))

p = post({"street": "סוקולוב 3", "property_type": "דירה"}, "דירה בסוקולוב 3")
check("באמצע משפט — מילת יחס, בלי צורה חלופית", p.get("street") == "סוקולוב 3" and not p.get("_street_alt"), p)

print("חיפוש מקצה לקצה")
q = post({"street": "לינסון 8", "property_type": "דירה", "deal_type": "מכירה"}, "בלינסון 8")
q["_qtext"] = "בלינסון 8"
res = search(q, rows=ROWS)
check("'בלינסון 8' מוצא את משה בילינסון 8 ראשון", res and res[0][1]["כתובת"] == "משה בילינסון 8", [r[1]["כתובת"] for r in res])
check("…ואין הודעת 'אין לנו נכס ברחוב'", note(q, res) == "", note(q, res))
q = {"street": "אנרי מטיס", "property_type": "דירה", "deal_type": "מכירה", "_qtext": "אנרי מטיס"}
res = search(q, rows=ROWS)
check("'אנרי מטיס' מוצא את אנרי מאטיס ראשון", res and res[0][1]["כתובת"] == "אנרי מאטיס 4", [r[1]["כתובת"] for r in res])

print("\nALL PASS" if not fails else "\n%d FAILED" % fails)
sys.exit(1 if fails else 0)
