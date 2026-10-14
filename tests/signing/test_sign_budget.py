# tests/signing/test_sign_budget.py — אייל 14/10: "למה התקציב 2,480,000 אם נדב שלח לחתימה 1,830,000?"
# אהוד מנור 13 = מגדל; זיהוי הכתובת מצא דירה אחרת בבניין (5 חד', 150 מ"ר, 2.48M). המחיר שהסוכן הקליד בטופס גובר.
import ast, os, re
SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "app.py"), encoding="utf-8").read()
T = ast.parse(SRC)
ns = {"re": re}
for node in T.body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_parse_sign_header", "_sig_price", "_sign_header_prices", "_buyer_desc_for"):
        exec(compile(ast.Module([node], []), "app", "exec"), ns)
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
H1 = "תאריך: 13/10/2026 · הסוכן: נדב רייזר\nלקוח: לידן ורז מרקדו · טל: 0523189218\nנכס: אהוד מנור 13 · מחיר מבוקש: 1,830,000 ₪"
ck(ns["_sign_header_prices"](H1) == [1830000], ns["_sign_header_prices"](H1))
H2 = "תאריך: 13/10/2026\nלקוח: דנה\nנכסים:\n1. הרצל 1 — 1,500,000 ₪\n2. הרצל 2 — 1,700,000 ₪\n3. הגפן 4 — "
ck(ns["_sign_header_prices"](H2) == [1500000, 1700000], ns["_sign_header_prices"](H2))
ck(ns["_sign_header_prices"]("") == [], "empty")
INFO = [{"desc": 'דירה · 5 חדרים · 150 מ"ר · נאות אפק, אפקה · קרית ביאליק · עד 2,480,000', "price": 2480000}]
d = ns["_buyer_desc_for"](INFO, [1830000])
ck(d == "דירה · נאות אפק, אפקה · קרית ביאליק · עד 1,830,000", d)   # דירה אחרת בבניין — רק המיקום
ck(ns["_buyer_desc_for"](INFO, [2400000]) == INFO[0]["desc"], "close price (<15%) — same unit, full desc")
ck(ns["_buyer_desc_for"](INFO, []) == INFO[0]["desc"], "no typed price — as before")
ck(ns["_buyer_desc_for"]([], [1830000]) == "", "no listing match")
# הקריאות להוספת קונה מההחתמה מעבירות את המחיר מהטופס, ושורת החתימה נושאת אותו (לתקציב הבא)
for fn in ("api_sign_submit", "api_sign_send_remote"):
    f = next(x for x in T.body if isinstance(x, ast.FunctionDef) and x.name == fn)
    body = ast.get_source_segment(SRC, f)
    ck("_sign_header_prices(header)" in body and "price=" in body.split("_add_buyer_from_signing(")[1][:400], (fn, "passes typed price"))
    ck('"budget"' in body, (fn, "budget on signature row"))
print("OK", n, "checks")
