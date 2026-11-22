"""[AGENT-ORDER 22/11] שם סוכן מיד2 בסדר הפוך → השם כפי שהוא באפי."""
import ast, os, re as _re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
tree = ast.parse(src)
ns = {"_re": _re}
for n in tree.body:
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "Y2_AGENT_FIX" for t in n.targets):
        exec(compile(ast.Module([n], []), "x", "exec"), ns)
    if isinstance(n, ast.FunctionDef) and n.name in ("_y2_nk", "y2_agent_canon"):
        exec(compile(ast.Module([n], []), "x", "exec"), ns)
f = ns["y2_agent_canon"]
K = ["דודו עובדיה", "צדוק עובדיה", "לירז עפרוני", "לירון איש לב", "ליאת גימפל", "ליאור גימפל", "דיקלה ביבי",
     "רחלי וקסלר", "לירז אוליאל ישי", "דידי לוי", "אלעד לוי", "ירין לוי", "קובי חמו", "בינימין אביטן",
     "אלי שמול", "יהודית שמול", "יאיר סקיטל", "רון בורנשטיין"]
ok = 0
def eq(a, b):
    global ok
    assert a == b, (a, b); ok += 1
eq(f("עובדיה דוד", K), "דודו עובדיה")
eq(f("דוד עובדיה", K), "דודו עובדיה")
eq(f("עובדיה צדוק עופר", K), "צדוק עובדיה")
eq(f("עפרוני לירז", K), "לירז עפרוני")
eq(f("איש לב לירון", K), "לירון איש לב")
eq(f("גימפל ליאת ויקי", K), "ליאת גימפל")
eq(f("ביבי דיקלה", K), "דיקלה ביבי")
eq(f("וקסלר רחל", K), "רחלי וקסלר")
eq(f("אוליאל ישי לירז", K), "לירז אוליאל ישי")
eq(f("לוי דידי דקלה", K), "דידי לוי")
eq(f("סקיטל יאיר", K), "יאיר סקיטל")
eq(f("בורנשטיין  רון", K), "רון בורנשטיין")
eq(f("קובי חמו", K), "קובי חמו")
eq(f("בינימין אביטן", K), "בינימין אביטן")       # רשום כך באפי — לא משתנה
eq(f("אלי שמול", K), "אלי שמול")
eq(f("בן שלל", K), "בן שלל")                      # לא מוכר — לא משתנה
eq(f("שלל בן יעקב", K), "שלל בן יעקב")
eq(f("לוי", K), "לוי")                            # מילה אחת — לא מנחשים
eq(f("סוכן 8719", K), "סוכן 8719")
eq(f("", K), "")
eq(f("עובדיה דוד", []), "דודו עובדיה")            # גם בלי ספרייה — לפי טבלת התיקונים
eq(f("לוי אלעד ירין", K), "לוי אלעד ירין")        # שתי התאמות — לא נוגעים
# merge_office_props: שורות קיימות מתוקנות
sys.path.insert(0, ROOT)
import supabase_db as sb
cur = [{"sheet_row": 1, "raw": {"סוכן 1": "עובדיה דוד", "מספר מודעה": "aaa", "_y2_office_id": "5625538"}},
       {"sheet_row": 2, "raw": {"סוכן 1": "סוכן 12", "מספר מודעה": "bbb", "_y2_office_id": "5628636"}}]
saved = {}
sb.enabled = lambda: True
sb._get_all = lambda *a, **k: cur
sb.replace_properties = lambda rows: (saved.setdefault("rows", rows), (True, len(rows)))[1]
new = [{"סוכן 1": "קובי חמו", "מספר מודעה": "ccc", "_y2_office_id": "8532791"}]
sb.merge_office_props("8532791", new, set(), "22/11/2026", "22/11/2026 15:00", agent_fix=lambda n: f(n, K))
by = {r["מספר מודעה"]: r["סוכן 1"] for r in saved["rows"]}
eq(by, {"aaa": "דודו עובדיה", "bbb": "סוכן 12", "ccc": "קובי חמו"})
print("OK", ok)
