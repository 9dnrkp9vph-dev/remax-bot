"""22/10: בדיקת 46 חיפושים אמיתיים (אתר + אפי) — שלב 1 של התיקונים (אייל: 'צא לדרך').
1א השכרה מחזירה מכירה · 1ב 'דו משפחתי' לא מחזיר דו-משפחתי · 1ג 'חיים' ברשימת ערים פותח את כל חיפה ·
1ד רחוב: 'בגין 12' לא תופס 'מנחם בגין', 'דן קרית ביאליק' הובן כדירת גן."""
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


SKIP = {"fetch_sheet_rows", "fetch_sheet_rows_deal"}   # מוחלפים בגרסאות דמה בבדיקה

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


g = load("score_match", "search_listings_in_sheet", "_search_post_rules", "_street_hint")
score, search, post = g["score_match"], g["search_listings_in_sheet"], g["_search_post_rules"]

def row(city="קרית ביאליק", nb="", street="", house="", rooms="4", price="1,500,000", ptype="דירה", deal="מכירה", lid=""):
    return {"סוג עסקה": deal, "עיר / ישוב": city, "שכונה": nb, "כתובת": street, "מספר בית": house,
            "חדרים": rooms, "מחיר": price, "סוג נכס": ptype, "מספר מודעה": lid or (street + house + price)}

def ids(res):
    return [r["מספר מודעה"] for _, r, _ in res]

print("SA 1א: rent query searches the office rent listings, not the sale ones")
SALE = [row(city="קרית ים", street="שבזי", rooms="4", price="1,390,000", lid="sale1"),
        row(city="קרית ים", street="לילך", rooms="4", price="1,590,000", lid="sale2"),
        row(city="קרית ים", street="שפרינצק", rooms="5", price="1,150,000", lid="sale3")]
RENT = [row(city="קרית ים", street="הרצל", rooms="4", price="5,200", deal="השכרה", lid="rent1"),
        row(city="קרית ים", street="סוקולוב", rooms="5", price="6,000", deal="השכרה", lid="rent2"),
        row(city="קרית ים", street="ויצמן", rooms="4.5", price="5,500", deal="השכרה", lid="rent3")]
asked = []
g["fetch_sheet_rows"] = lambda: SALE
g["fetch_sheet_rows_deal"] = lambda d: (asked.append(d), RENT if d == "השכרה" else [])[1]
qr = {"city": "קרית ים", "rooms_min": 4, "rooms_max": 5, "deal_type": "השכרה"}
res = search(qr)
check("rent rows asked", asked == ["השכרה"], asked)
check("only rent listings", ids(res) and all(i.startswith("rent") for i in ids(res)), ids(res))
asked.clear()
res = search({"city": "קרית ים", "rooms_min": 4, "rooms_max": 5, "deal_type": "מכירה"})
check("sale query → sale rows, rent not fetched", asked == [] and all(i.startswith("sale") for i in ids(res)), (asked, ids(res)))
res = search(qr, rows=SALE + RENT)
check("explicit rows are used as given (rent ones match)", all(i.startswith("rent") for i in ids(res)), ids(res))
check("sale row never matches a rent query", score(SALE[0], {"deal_type": "השכרה"}) == 0)

print("SA 1ב: 'דו משפחתי' / 'בית פרטי' — both private-house types")
DUO = row(street="דובדבן", rooms="6", price="3,870,000", ptype="דו משפחתי")
HOUSE = row(street="אפרים", rooms="7", price="3,150,000", ptype="בית פרטי/ קוטג'")
FLAT = row(street="השקדים", rooms="4", ptype="דירה")
qd = {"property_type": "דו משפחתי"}
check("דו משפחתי → דו-משפחתי included", score(DUO, qd) > 0, score(DUO, qd))
check("דו משפחתי → private house included too", score(HOUSE, qd) > 0, score(HOUSE, qd))
check("דו משפחתי ranks above private house", score(DUO, qd) > score(HOUSE, qd), (score(DUO, qd), score(HOUSE, qd)))
check("flat excluded", score(FLAT, qd) == 0)
qc = {"property_type": "קוטג'"}
check("קוטג' → private house", score(HOUSE, qc) > 0)
check("קוטג' → דו-משפחתי too", score(DUO, qc) > 0)
check("פנטהאוז search unchanged (house excluded)", score(HOUSE, {"property_type": "פנטהאוז"}) == 0)
p = post({"property_type": "קוטג'"}, "מחפש דירה דו משפחתי")
check("text 'דו משפחתי' → property_type דו משפחתי", p.get("property_type") == "דו משפחתי", p)
p = post({"property_type": "קוטג'"}, "מחפש דירה בית פרטי")
check("text 'בית פרטי' → קוטג'", p.get("property_type") == "קוטג'", p)

print("SA 1ד-1: a garden the customer never asked for is dropped ('דן קרית ביאליק')")
p = post({"city": "קרית ביאליק", "property_type": "דירת גן", "must_have": ["גינה"]}, "מחפש דירה דן קרית ביאליק")
check("property_type → דירה", p.get("property_type") == "דירה", p)
check("גינה removed", "גינה" not in (p.get("must_have") or []), p)
p = post({"property_type": "דירת גן", "must_have": ["גינה", "מעלית"]}, "מחפש דירת גן עם מעלית")
check("asked garden kept", p.get("property_type") == "דירת גן" and p.get("must_have") == ["גינה", "מעלית"], p)
p = post({"property_type": "דירת גן", "must_have": ["גינה"]}, "מחפש קוטג' בקרית ביאליק")
check("קוטג' keeps the garden group", p.get("property_type") == "דירת גן", p)
p = post({"property_type": "דירת גן", "must_have": ["גינה"]}, "מחפש דירה עם חצר")
check("חצר keeps the garden group", p.get("property_type") == "דירת גן", p)

print("SA 1ג: 'חיים' in a city list = קרית חיים only, not all of Haifa")
p = post({"cities": ["קרית ביאליק", "קרית מוצקין", "חיפה"]}, "מחפש דירה 4 חדרים בקרית ביאליק או מוצקין או חיים עם מעלית")
check("חיפה → קרית חיים", p.get("cities") == ["קרית ביאליק", "קרית מוצקין", "קרית חיים"], p)
p = post({"cities": ["חיפה", "קרית ביאליק"]}, "מחפש דירה 3 חדרים עד 1.85M בחיפה או בקרית ביאליק")
check("Haifa written explicitly → unchanged", p.get("cities") == ["חיפה", "קרית ביאליק"], p)
p = post({"city": "קרית ביאליק", "street": "חיים"}, "מחפש דירה רחוב חיים בקרית ביאליק")
check("street 'חיים' in Bialik → untouched", p.get("city") == "קרית ביאליק" and not p.get("cities"), p)
p = post({"city": "חיפה"}, "מחפש דירה 4 חד בקריית חיים עד 1,350,000")
check("single city Haifa + 'קריית חיים' → neighborhood קרית חיים", p.get("neighborhood") == "קרית חיים", p)
qh = {"cities": ["קרית ביאליק", "קרית חיים"], "rooms_min": 4, "rooms_max": 4, "budget_min": 1800000, "budget_max": 2050000}
CARMEL = row(city="חיפה", nb="מרכז הכרמל", street="שדרות הנשיא", price="2,100,000")
HAIM = row(city="חיפה", nb="קרית חיים מזרחית", street="הנוטר", price="1,950,000")
HAIM_NONB = row(city="חיפה", nb="", street="הנוטר", price="1,950,000")
check("Haifa, Carmel → excluded", score(CARMEL, qh) == 0, score(CARMEL, qh))
check("Haifa, קרית חיים מזרחית → included", score(HAIM, qh) > 0)
check("Haifa, no neighborhood → still included", score(HAIM_NONB, qh) > 0)
q1 = {"city": "חיפה", "neighborhood": "קרית חיים", "budget_max": 2000000}
check("single city: Carmel inside the ±10% budget band → still excluded", score(row(city="חיפה", nb="מרכז הכרמל", price="2,050,000"), q1) == 0)
check("single city: קרית שמואל near budget → kept (Krayot)", score(row(city="חיפה", nb="קרית שמואל", price="2,050,000"), q1) > 0)

print("SA 1ד-2: street search — 'בגין 12' finds 'מנחם בגין' first")
BEGIN = row(city="קרית מוצקין", nb="נווה גנים", street="מנחם בגין", house="12", rooms="3", price="1,290,000")
OFRA = row(city="קרית מוצקין", nb="משכנות האומנים", street="עפרה חזה", house="12", rooms="5", price="2,120,000")
OTHER = row(city="קרית מוצקין", street="הרב קוק", house="3", rooms="4", price="1,500,000")
qs = {"city": "קרית מוצקין", "street": "בגין 12"}
check("מנחם בגין ranks first", score(BEGIN, qs) > max(score(OFRA, qs), score(OTHER, qs)), (score(BEGIN, qs), score(OFRA, qs), score(OTHER, qs)))
qs2 = {"city": "קרית ביאליק", "street": "רחוב השקדים", "rooms_min": 4, "rooms_max": 4, "budget_max": 1700000}
SHK = row(street="השקדים", house="9", rooms="4", price="1,190,000")
NEAR = row(street="עוזי חיטמן", rooms="4", price="1,690,000")
check("'רחוב השקדים' → השקדים above a closer-priced listing", score(SHK, qs2) > score(NEAR, qs2), (score(SHK, qs2), score(NEAR, qs2)))
check("house number bonus", score(row(city="קרית מוצקין", street="מנחם בגין", house="12"), qs) > score(row(city="קרית מוצקין", street="מנחם בגין", house="30"), qs))

print("SA 1ד-3: a street name the AI missed is found from our own listings")
hint = g["_street_hint"]
ROWS = [row(street="דן", house="3", rooms="5", price="2,950,000", ptype="דירת גן"),
        row(street="הגפן", rooms="5", price="2,700,000"),
        row(street="חיים", house="32", rooms="3", price="1,540,000"),
        row(city="קרית מוצקין", street="מנחם בגין", house="12")]
check("'דן קרית ביאליק' → דן", hint("מחפש דירה דן קרית ביאליק", ROWS, {"city": "קרית ביאליק"}) == "דן")
check("'קרית חיים' is a place, not the street חיים", hint("מחפש דירה 4 חדרים בקרית חיים", ROWS, {}) == "")
check("plain search → no street", hint("מחפש דירה 4 חדרים בקרית ביאליק עד 1.7 מיליון", ROWS, {"city": "קרית ביאליק"}) == "")
check("street in another city → ignored", hint("מחפש דירה מנחם בגין קרית ביאליק", ROWS, {"city": "קרית ביאליק"}) == "")
res = search({"city": "קרית ביאליק", "property_type": "דירה", "_qtext": "מחפש דירה דן קרית ביאליק"}, rows=ROWS)
check("search: דן ranks first", res and res[0][1]["כתובת"] == "דן", [r["כתובת"] for _, r, _ in res])

print(f"{fails} FAILURES" if fails else "ALL SEARCH-AUDIT TESTS PASSED")
sys.exit(1 if fails else 0)
