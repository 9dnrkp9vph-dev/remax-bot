# -*- coding: utf-8 -*-
"""13/11 (אייל): בתהליך שמנהל פתח נשמר 'מנהל' — עכשיו השם האמיתי לפי הטלפון + by_phone.
python3 tests/deals/test_by_real_name.py"""
import ast, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "api_deals_save")
code = ast.get_source_segment(src, fn); code = code[code.index("def "):]
fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)
assert "_display_name_for(s[\"name\"]" in code
seg = code[code.index("else:\n            rec[\"created\"]"):]
check("by_phone" in seg and "_display_name_for" in seg, "תהליך חדש: שם אמיתי + טלפון")
check("existing.get(\"by_phone\")" in code, "עריכה שומרת את by_phone")
# הרצה של הענף החדש
ns = {"_display_name_for": lambda n, p: "מתן ביטון" if n == "מנהל" and p.endswith("544448065") else n,
      "_last9": lambda p: str(p)[-9:]}
body = '''
def f(s):
    rec = {}
    try:
        rec["by"] = _display_name_for(s["name"], s.get("phone", "")) or s["name"]
    except Exception:
        rec["by"] = s["name"]
    rec["by_phone"] = _last9(s.get("phone", "") or "")
    return rec
'''
exec(body, ns)
r = ns["f"]({"name": "מנהל", "phone": "0544448065"})
check(r == {"by": "מתן ביטון", "by_phone": "544448065"}, "מנהל → מתן ביטון")
check(ns["f"]({"name": "נדב רייזר", "phone": "050"})["by"] == "נדב רייזר", "סוכן רגיל ללא שינוי")
print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED" % len(fails))
raise SystemExit(1 if fails else 0)
