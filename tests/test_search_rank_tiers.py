"""05/11 (אייל: 'כן תתקן את 1 ו-2', מבקרת החיפושים): (1) בתוך התקציב תמיד לפני מעליו — גם כשבונוס שכונה/חדרים
מעלה את היקר; (2) 'דירת גן' — דירות גן לפני קוטג'ים ודו משפחתיים (אלא אם הוקלד קוטג'/בית פרטי)."""
import ast, os, re, sys, logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    g = {"re": re, "os": os, "time": __import__("time"), "logging": logging, "log": logging.getLogger("t"), "__file__": os.path.join(ROOT, "app.py")}
    exec(compile(ast.Module(body=order, type_ignores=[]), "app_extract", "exec"), g)
    return g

fails = 0
def check(name, cond, detail=""):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "  →  " + repr(detail)))
    if not cond:
        fails += 1

g = load("score_match", "search_listings_in_sheet")
g.update({"_prop_epoch": lambda r: 0, "_canon_key": lambda n: re.sub(r"\s+", " ", str(n or "")).strip()})
search = g["search_listings_in_sheet"]

def row(city="קרית ביאליק", nb="", street="", rooms="5", price="1,900,000", ptype="דירה", floor="", lid=""):
    return {"סוג עסקה": "מכירה", "עיר / ישוב": city, "שכונה": nb, "כתובת": street, "מספר בית": "",
            "חדרים": rooms, "מחיר": price, "סוג נכס": ptype, "קומה": floor, "סוכן 1": "", "מספר מודעה": lid}
ids = lambda res: [r["מספר מודעה"] for _, r, _ in res]

print("1: בתוך התקציב לפני מעליו — גם כשהיקר מקבל בונוס")
R = [row(nb="נאות אפק", rooms="5", price="2,050,000", lid="over_nb"),     # שכונה + חדרים מדויקים, מעל התקציב
     row(nb="צור שלום", rooms="5", price="1,970,000", lid="in_other"),
     row(nb="נאות אפק", rooms="5", price="1,800,000", lid="in_nb"),
     row(nb="נאות אפק", rooms="5", price="", lid="noprice")]
q = {"city": "קרית ביאליק", "neighborhoods": ["אפק", "צור שלום"], "rooms_min": 5, "rooms_max": 5, "budget_max": 2000000}
o = ids(search(q, rows=R))
check("הנכס שמעל התקציב אחרון", o and o[-1] == "over_nb", o)
check("כל מה שבתוך התקציב לפניו", set(o[:-1]) >= {"in_other", "in_nb"}, o)
check("בלי מחיר — לא נדחק לסוף", o.index("noprice") < o.index("over_nb"), o)
o2 = ids(search({"city": "קרית ביאליק"}, rows=R))
check("בלי תקציב — הסדר לא מושפע מהכלל (כולם מוצגים)", len(o2) == 4, o2)

print("2: 'דירת גן' — דירות גן קודם")
G = [row(city="קרית ים", ptype="דו משפחתי", price="2,000,000", lid="d1"),
     row(city="קרית ים", ptype="דו משפחתי", price="2,100,000", lid="d2"),
     row(city="קרית ים", ptype="בית פרטי/ קוטג'", price="2,200,000", lid="c1"),
     row(city="קרית ים", ptype="דירת גן", price="1,500,000", lid="g1"),
     row(city="קרית ים", ptype="דירה", floor="0", price="1,400,000", lid="g0")]
qg = {"city": "קרית ים", "property_type": "דירת גן", "must_have": ["גינה"], "_qtext": "מחפש דירה דירת גן בקרית ים"}
og = ids(search(qg, rows=G))
check("דירות גן (וקומת קרקע) ראשונות", set(og[:2]) == {"g1", "g0"}, og)
check("קוטג'ים ודו משפחתיים עדיין מוצגים, אחריהן", set(og[2:]) == {"d1", "d2", "c1"}, og)
qc = dict(qg, _qtext="מחפש דירה קוטג' בקרית ים")
oc = ids(search(qc, rows=G))
check("הוקלד קוטג' — אין דחיקה של בתים", oc.index("c1") < oc.index("g0"), oc)

print("1+2 יחד: סוג הנכס לפני התקציב")
GB = [row(city="קרית ים", ptype="דו משפחתי", price="1,500,000", lid="d_in"),
      row(city="קרית ים", ptype="דירת גן", price="2,150,000", lid="g_over")]
ob = ids(search(dict(qg, budget_max=2000000), rows=GB))
check("דירת גן מעל התקציב לפני דו משפחתי בתוכו", ob == ["g_over", "d_in"], ob)

print("\n%d failed" % fails)
sys.exit(1 if fails else 0)
