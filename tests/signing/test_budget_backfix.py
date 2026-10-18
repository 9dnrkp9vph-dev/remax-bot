# tests/signing/test_budget_backfix.py — אייל 18/10: "אם הלקוח חתם על 1790 למה הוא מופיע עם 2350?"
# קונים שנוצרו מהחתמה לפני התיקון של 14/10 — תקציב/תיאור מנכס אחר באותה כתובת. תיקון חד-פעמי עם תצוגה מקדימה.
import sys, os, ast, re
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
ns = {"re": re}
for node in ast.parse(src).body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_bbfix_plan", "_sig_price"):
        exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
plan = ns["_bbfix_plan"]
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
canon = lambda s: re.sub(r"\s", "", str(s or ""))
EP = {"08/10/2026 11:15": 1000, "09/10/2026 10:00": 2000, "01/10/2026 10:00": 500}
epoch = lambda s: EP.get(s, 0)
DESC = "דו משפחתי · 4 חד' · 312 מ\"ר · חרב לאת קרית חיים · עד 2,350,000"
sigs = [dict(deal_type="CLIENT_SALE", client_name="אלי אזולאי", agent="רויטל גל", address="אלכסנדר זייד 131", received_at="08/10/2026 11:15", tok="t1"),
        dict(deal_type="CLIENT_SALE", client_name="דנה", agent="רויטל גל", address="הגפן 1", received_at="08/10/2026 11:15", tok="t2"),
        dict(deal_type="CLIENT_SALE", client_name="רון", agent="משה", address="הגפן 2", received_at="08/10/2026 11:15", tok="t3"),
        dict(deal_type="OWNER_SALE", client_name="אלי אזולאי", agent="רויטל גל", address="x", received_at="09/10/2026 10:00", tok="t4")]
LIST = {"אלכסנדר זייד 131": 2350000, "הגפן 1": 1500000, "הגפן 2": 2000000}
TYPED = {"t1": [1790000], "t2": [1510000], "t3": [1200000]}
listing_prices = lambda g: [LIST[g["address"]]] if g["address"] in LIST else []
typed_prices = lambda g: TYPED.get(g.get("tok"), [])
def desc_for(g, typed):
    if g["address"] == "אלכסנדר זייד 131":
        return DESC, "חרב לאת קרית חיים · עד 1,790,000"
    return None
buyers = [dict(row=11, name="אלי אזולאי", agent="רויטל גל", budget="2,350,000", search=DESC),
          dict(row=12, name="דנה", agent="רויטל גל", budget="1,500,000", search="x"),          # הפרש קטן מ-15% — לא נוגעים
          dict(row=13, name="רון", agent="משה", budget="1,000,000", search="y"),               # הסוכן ערך ידנית — לא נוגעים
          dict(row=14, name="אלי אזולאי", agent="מישהו אחר", budget="2,350,000", search=DESC)]  # סוכן אחר — אין חתימה שלו
out = plan(buyers, sigs, canon, epoch, listing_prices, typed_prices, desc_for)
ck([x["row"] for x in out] == [11], out)
x = out[0]
ck(x["budget_old"] == "2,350,000" and x["budget_new"] == "1,790,000", x)
ck(x["search_new"] == "חרב לאת קרית חיים · עד 1,790,000" and x["search_old"] == DESC, x)
ck(x["name"] == "אלי אזולאי" and x["agent"] == "רויטל גל" and x["address"] == "אלכסנדר זייד 131", x)
# תיאור שהסוכן כתב בעצמו (לא התיאור האוטומטי) — התקציב מתוקן, התיאור נשאר
b2 = [dict(buyers[0], search="מחפש בית פרטי בקרית חיים")]
y = plan(b2, sigs, canon, epoch, listing_prices, typed_prices, desc_for)[0]
ck(y["budget_new"] == "1,790,000" and y["search_new"] == "מחפש בית פרטי בקרית חיים", y)
# בלי מחיר בטופס (מסמך לא נמצא) — לא נוגעים
ck(plan(buyers, sigs, canon, epoch, listing_prices, lambda g: [], desc_for) == [], "no typed price → skip")
# כמה נכסים באותו יום — ממוצע (כמו כלל 'החתימה האחרונה')
s3 = sigs + [dict(sigs[0], address="הגפן 9", tok="t9")]
LIST["הגפן 9"] = 2350000; TYPED["t9"] = [1810000]
z = plan(buyers[:1], s3, canon, epoch, listing_prices, typed_prices, desc_for)[0]
ck(z["budget_new"] == "1,800,000", z)
print("OK", n, "checks")
