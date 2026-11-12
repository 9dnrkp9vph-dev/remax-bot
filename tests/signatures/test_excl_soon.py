# -*- coding: utf-8 -*-
"""[13/11 אייל] טאב 'בלעדיות': נכסים שהבלעדיות שלהם נגמרת בחודש הקרוב — למעלה, עם 'בלעדיות עד' מודגש.
python3 tests/signatures/test_excl_soon.py"""
import ast, os, re, json, subprocess, time, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
tree = ast.parse(src)
want = ("_excl_parse_date", "_sig_doc_token", "_sig_is_signed", "_excl_end_map")
code = "\n\n".join(ast.get_source_segment(src, n) for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name in want)
fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

class L:
    def warning(self, *a): pass
ns = dict(re=re, log=L(), _EXCL_END_CACHE={},
          _web_valid_pct=lambda v: (str(v).replace(".", "", 1).isdigit() and 0 < float(v) <= 10) if v not in (None, "") else None,
          _excl_epoch=lambda v: time.time() - 30 * 86400 if v != "old" else time.time() - 500 * 86400)
exec(code, ns)
P = ns["_excl_parse_date"]
check(P("12/02/2027") == dt.date(2027, 2, 12), "DD/MM/YYYY")
check(P("1.3.27") == dt.date(2027, 3, 1), "D.M.YY")
check(P("2027-02-12T00:00") == dt.date(2027, 2, 12), "ISO")
check(P("____") is None and P("31/02/2027") is None, "ריק/לא תקין = None")

CALLS = []
def fetch(toks):
    CALLS.append(list(toks))
    return {"AbcdefGhijklmn12": "15/12/2026", "Zzzzzzzzzzzzzzz9": ""}
rows = [
    {"deal_type": "OWNER_EXCLUSIVE", "commission_pct": "https://x/s/AbcdefGhijklmn12", "received_at": "x"},  # מגוף ההסכם
    {"deal_type": "OWNER_EXCLUSIVE", "commission_pct": "https://x/s/Q", "excl_to": "01/12/2026", "received_at": "x"},  # מהשורה
    {"deal_type": "OWNER_SALE", "commission_pct": "https://x/s/AbcdefGhijklmn12", "received_at": "x"},  # לא בלעדיות
    {"deal_type": "OWNER_EXCLUSIVE", "commission_pct": "", "event_id": "Zzzzzzzzzzzzzzz9", "received_at": "x"},  # לא נחתם
    {"deal_type": "OWNER_EXCLUSIVE", "commission_pct": "https://x/s/Zzzzzzzzzzzzzzz9", "received_at": "x"},  # בלי תאריך בגוף
    {"deal_type": "OWNER_EXCLUSIVE", "commission_pct": "https://x/s/OldOldOldOldOld1", "received_at": "old"},  # ישן מ-400 יום
]
m = ns["_excl_end_map"](rows, fetch=fetch)
check(m.get(id(rows[0])) == dt.date(2026, 12, 15), "תאריך מגוף ההסכם")
check(m.get(id(rows[1])) == dt.date(2026, 12, 1), "excl_to מהשורה גובר, בלי שאילתה")
check(id(rows[2]) not in m and id(rows[3]) not in m and id(rows[4]) not in m, "מוכר / ממתין / בלי תאריך — לא נכנסים")
check(CALLS == [["AbcdefGhijklmn12", "Zzzzzzzzzzzzzzz9"]], "שאילתה אחת, בלי ישנים מ-400 יום")
ns["_excl_end_map"](rows, fetch=fetch)
check(len(CALLS) == 1, "טוקן שנבדק לא נשאל שוב (גם בלי תאריך)")
def boom(t): raise RuntimeError("x")
ns["_EXCL_END_CACHE"].clear()
check(ns["_excl_end_map"](rows, fetch=boom).get(id(rows[1])) == dt.date(2026, 12, 1), "כשל במקור — לא נופלים")

# --- api_signatures: בלעדיות שנגמרת בקרוב נכנסת גם מעבר ל-500 ---
check('_soon_extra = [g for g in sigs[500:]' in src and '"exclTo":' in src, "השרת מוסיף בלעדיות קרובה מעבר ל-500")

# --- client ---
e2 = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
js = e2[e2.index("function exclDays(g){"):e2.index("function render(){", e2.index("function exclDays(g){"))]
today = dt.date.today()
f = lambda d: (today + dt.timedelta(days=d)).strftime("%d/%m/%Y")
prog = js + r"""
function esc(s){ return String(s); }
var A=[{a:'far',exclTo:'%s'},{a:'soon20',exclTo:'%s'},{a:'none',exclTo:''},{a:'soon3',exclTo:'%s'},{a:'past',exclTo:'%s'}];
var soonL=A.filter(exclSoon).sort(function(a,b){return exclDays(a)-exclDays(b);});
var src=soonL.concat(A.filter(function(g){return !exclSoon(g);}));
console.log(JSON.stringify({order:src.map(function(g){return g.a;}), l3:exclLine(A[3]), lfar:exclLine(A[0]), lnone:exclLine(A[2]), lpast:exclLine(A[4])}));
""" % (f(90), f(20), f(3), f(-2))
out = json.loads(subprocess.run(["node", "-e", prog], capture_output=True, text=True).stdout)
check(out["order"] == ["soon3", "soon20", "far", "none", "past"], "הקרובים ראשונים (הקרוב ביותר למעלה), השאר בסדר המקורי")
check("font-weight:800" in out["l3"] and "בלעדיות עד " + f(3) in out["l3"] and "עוד 3 ימים" in out["l3"], "שורה מודגשת עם התאריך והימים")
check("בלעדיות עד" in out["lfar"] and "עוד" not in out["lfar"], "רחוקה — רק התאריך")
check(out["lnone"] == "", "בלי תאריך — בלי שורה")
check("הסתיימה" in out["lpast"], "שעברה — 'הסתיימה'")
check(e2.count("'הבלעדיות נגמרת בחודש הקרוב · ' + nSoon") == 1, "כותרת הקבוצה בראש הטאב")
print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED" % len(fails))
raise SystemExit(1 if fails else 0)
