"""28/10: חיפוש נכסים — שלב 2 (אייל: 'תמשיך ל-2'). 2א בתוך התקציב לפני מעליו · 2ב הודעה כנה כשאין נכס ברחוב/שכונה ·
2ג שם סוכן · 2ד 'רק ב…'."""
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


SKIP = {"fetch_sheet_rows", "fetch_sheet_rows_deal", "_prop_epoch", "_canon_key"}   # מוחלפים בגרסאות דמה בבדיקה

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
    g = {"re": re, "log": logging.getLogger("t")}
    exec(compile(ast.Module(body=order, type_ignores=[]), "app_extract", "exec"), g)
    return g


fails = 0
def check(name, cond, detail=""):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "  →  " + repr(detail)))
    if not cond:
        fails += 1



import datetime, time
g = load("score_match", "search_listings_in_sheet", "_search_post_rules", "search_area_note", "_agent_in_query", "_strip_words")
g.update({"_prop_epoch": lambda r: 0, "_canon_key": lambda n: re.sub(r"\s+", " ", str(n or "")).strip()})
score, search, post, note = g["score_match"], g["search_listings_in_sheet"], g["_search_post_rules"], g["search_area_note"]

def row(city="קרית ביאליק", nb="", street="", house="", rooms="4", price="1,500,000", ptype="דירה", agent="", lid=""):
    return {"סוג עסקה": "מכירה", "עיר / ישוב": city, "שכונה": nb, "כתובת": street, "מספר בית": house,
            "חדרים": rooms, "מחיר": price, "סוג נכס": ptype, "סוכן 1": agent, "מספר מודעה": lid or (street + house + price)}
def ids(res):
    return [r["מספר מודעה"] for _, r, _ in res]

print("SA 2א: 'up to 1.7M' — within budget before above it")
R = [row(street="א", price="1,750,000", lid="over3"), row(street="ב", price="1,900,000", lid="over12"),
     row(street="ג", price="1,540,000", lid="in90"), row(street="ד", price="1,690,000", lid="in99")]
res = search({"city": "קרית ביאליק", "budget_max": 1700000}, rows=R)
o = ids(res)
check("in-budget listings first", o[:2] == ["in99", "in90"], o)
check("above budget still shown (within +10%), after", "over3" in o and o.index("over3") > 1, o)
check("over +10% not at flex 0", "over12" not in o, o)

print("SA 2ב: honest note when street / neighborhood has nothing of ours")
M = [(80, row(street="הרצל", lid="h1"), 0)]
n = note({"city": "קרית ביאליק", "street": "הגפן 4"}, M)
check("street miss note", n == "אין לנו כרגע נכס ברחוב הגפן · הנה נכסים בקרית ביאליק", n)
check("street hit → no note", note({"city": "קרית ביאליק", "street": "הרצל"}, M) == "")
check("neighborhood miss note", note({"city": "קרית ביאליק", "neighborhood": "אפק"}, [(80, row(nb="צור שלום"), 0)]) ==
      "אין לנו כרגע נכס באפק · הנה נכסים בקרית ביאליק")
check("neighborhood hit → no note", note({"neighborhood": "אפק"}, [(80, row(nb="נאות אפק"), 0)]) == "")
check("nothing asked → no note", note({"city": "קרית ביאליק"}, M) == "")

print("SA 2ג: agent name in the search")
A = [row(street="הגפן", agent="אלעד לוי", lid="e1"), row(street="הרצל", agent="אלעד לוי", lid="e2"),
     row(street="לוי אשכול", agent="קובי חמו", lid="k1"), row(street="יהודה הלוי", agent="רפי כהן", lid="r1")]
check("full name found", g["_agent_in_query"]("מחפש דירה נכסים של אלעד לוי", A) == "אלעד לוי")
check("first name after 'של' found", g["_agent_in_query"]("מחפש דירה הנכסים של אלעד", A) == "אלעד לוי")
check("'יהודה הלוי' street is not an agent", g["_agent_in_query"]("מחפש דירה ביהודה הלוי", A) == "")
res = search({"_qtext": "מחפש דירה נכסים של אלעד לוי", "street": "לוי"}, rows=A)
check("only the agent's listings", sorted(ids(res)) == ["e1", "e2"], ids(res))
res = search({"_qtext": "מחפש דירה של אלעד לוי ברחוב הגפן", "city": "קרית ביאליק", "street": "הגפן"}, rows=A)
check("agent + criteria → filtered then scored", ids(res)[:1] == ["e1"] and "k1" not in ids(res), ids(res))

print("SA 2ד: 'רק במשכנות' — no other neighborhood even at budget")
q = post({"city": "קרית מוצקין", "neighborhood": "משכנות האומנים", "budget_max": 2000000}, "מחפש דירה רק במשכנות האומנים עד 2 מיליון")
check("strict flag set", q.get("_strict_area") is True, q)
other = row(city="קרית מוצקין", nb="נווה גנים", price="1,980,000")
check("other neighborhood at budget → out", score(other, q) == 0)
q2 = post({"city": "קרית מוצקין", "neighborhood": "משכנות האומנים", "budget_max": 2000000}, "מחפש דירה במשכנות האומנים עד 2 מיליון")
check("without 'רק' — still the ±10% exemption", not q2.get("_strict_area") and score(other, q2) > 0)

print("\nFAIL %d" % fails if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
