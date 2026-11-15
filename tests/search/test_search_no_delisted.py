# -*- coding: utf-8 -*-
"""15/11 (אייל, צילום חיפוש בטאב נכס נולד: 'למה זה מראה נכסים שירדו מפרסום?') — חיפוש לא מחזיר
מודעות שירדו מפרסום: משרד ('ירד מפרסום'), נכס נולד (_nb.delisted_at), שת"פ (delisted_at).
python3 tests/search/test_search_no_delisted.py"""
import ast, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fns = {n.name: n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)}
ns = {}
exec(ast.get_source_segment(src, fns["_search_live_rows"]), ns)
f = ns["_search_live_rows"]
fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)
rows = [{"כתובת": "א"}, {"כתובת": "ב", "ירד מפרסום": "05/10/2026"},
        {"כתובת": "ג", "_nb": {"delisted_at": "05/10/2026"}}, {"כתובת": "ד", "_nb": {"delisted_at": ""}}]
check([r["כתובת"] for r in f(rows)] == ["א", "ד"], "משרד ונכס נולד שירדו — לא בתוצאות")
check(f(None) == [], "בלי שורות — ריק")
sl = ast.get_source_segment(src, fns["search_listings_in_sheet"])
check("_search_live_rows(rows)" in sl, "החיפוש מסנן לפני הניקוד")
se = ast.get_source_segment(src, fns["api_search_exclusives"])
check('if not str(r.get("delisted_at", "") or "").strip()]' in se, "שת\"פ — חיפוש בלי מודעות שירדו")
print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED" % len(fails))
raise SystemExit(1 if fails else 0)
