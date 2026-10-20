"""20/10: חיפוש נכסים — 'עד קומה 2' ו'ללא מעלית' (אייל: "מחפש דירה עד קומה 2 ללא מעלית עם מרפסת").
בשורות יד2 עמודת הקומה ריקה (הקומה בתיאור), ו'ללא X' לא נתמך בכלל."""
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


def load(*names):
    need, order, stack = set(), [], list(names)
    while stack:
        nm = stack.pop()
        if nm in need or nm not in TOP:
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
    g = {"re": re, "log": logging.getLogger("t")}
    exec(compile(ast.Module(body=order, type_ignores=[]), "app_extract", "exec"), g)
    return g


fails = 0
def check(name, cond, detail=""):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "  →  " + repr(detail)))
    if not cond:
        fails += 1


g = load("score_match", "_row_floor", "_query_text_rules", "_apply_text_rules")
score, row_floor, rules = g["score_match"], g["_row_floor"], g["_query_text_rules"]

def row(desc, floor="", city="קרית ביאליק"):
    return {"סוג עסקה": "מכירה", "עיר / ישוב": city, "סוג נכס": "דירה", "קומה": floor, "_desc_ae": desc}

print("SF 1: floor from the description when the column is empty")
check("'קומה 9 מתוך 24' → 9", row_floor(row("דירת 5 חדרים קומה 9 מתוך 24")) == 9)
check("'קומה 2/4' → 2", row_floor(row("דירה בקומה 2/4 עם מעלית")) == 2)
check("'בקומה ראשונה' → 1", row_floor(row("דירת 4 חדרים בקומה ראשונה מעל הקרקע")) == 1)
check("'קומת קרקע' → 0", row_floor(row("דירה בקומת קרקע עם חצר")) == 0)
check("'בניין 6 קומות' → None", row_floor(row("בניין בוטיק של 6 קומות")) is None)
check("column wins", row_floor(row("קומה 9", floor="3")) == 3)

print("SF 2: floor_max filters by the description floor")
q = {"floor_max": 2}
check("קומה 9 → excluded", score(row("קומה 9 מתוך 24"), q) == 0)
check("קומה 1 → kept", score(row("בקומה ראשונה"), q) > 0)
check("unknown floor → kept", score(row("דירה מרווחת"), q) > 0)

print("SF 3: text rules — 'ללא מעלית', 'עד קומה 2'")
r = rules("מחפש דירה עד קומה 2 ללא מעלית עם מרפסת")
check("must_not מעלית", r.get("must_not") == ["מעלית"], r)
check("floor_max 2", r.get("floor_max") == 2, r)
r2 = rules("דירה עם מעלית וממ\"ד")
check("no negation", not r2.get("must_not"), r2)
r3 = rules("בלי ממד, עד קומה 3")
check("בלי ממד → ממ״ד", r3.get("must_not") == ["ממ״ד"] and r3.get("floor_max") == 3, r3)

print("SF 4: must_not excludes listings that have the feature")
q = {"must_not": ["מעלית"], "must_have": ["מרפסת"]}
s_el = score(row("3 חדרים עם מעלית ומרפסת"), q)
s_no = score(row("3 חדרים ללא מעלית, מרפסת שמש"), q)
s_unk = score(row("3 חדרים עם מרפסת"), q)
check("with elevator → 0", s_el == 0, s_el)
check("'ללא מעלית' ranks above unknown", s_no > s_unk > 0, (s_no, s_unk))
check("flex 2 still excludes elevator", score(row("עם מעלית ומרפסת"), q, flex_level=2) == 0)

print("SF 5: AI put the unwanted feature in must_have → moved out")
qq = g["_apply_text_rules"]({"must_have": ["מעלית", "מרפסת"]}, "מחפש דירה עד קומה 2 ללא מעלית עם מרפסת")
check("must_have = מרפסת only", qq.get("must_have") == ["מרפסת"], qq)
check("must_not = מעלית", qq.get("must_not") == ["מעלית"], qq)
check("floor_max filled", qq.get("floor_max") == 2, qq)
qq2 = g["_apply_text_rules"]({"floor_max": 3, "must_have": ["ממ\"ד"]}, "עד קומה 2 עם ממ\"ד")
check("AI floor_max kept", qq2.get("floor_max") == 3, qq2)
check("must_have untouched", qq2.get("must_have") == ['ממ"ד'], qq2)

print(f"{fails} FAILURES" if fails else "ALL SEARCH-FEATURE TESTS PASSED")
sys.exit(1 if fails else 0)
