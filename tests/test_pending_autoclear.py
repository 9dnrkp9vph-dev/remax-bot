# tests/test_pending_autoclear.py — 'בטיפול אצל המזכירה' מתבטל לבד כשהמחיר ירד (אייל 01/11)
import ast, os, re, time

SRC = open(os.path.join(os.path.dirname(__file__), "..", "app.py"), encoding="utf-8").read()
tree = ast.parse(SRC)
ns = {"re": re, "time": time, "PENDING_REQ_KEEP_DAYS": 60}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_price_digits", "pending_autoclear_plan"):
        exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
plan = ns["pending_autoclear_plan"]
NOW = 1_800_000_000
DAY = 86400

# 1) בקשה שנרשמה במחיר 1,385,000 והמחיר ירד ל-1,320,000 → מתבטל
clear, reqs = plan({"A1"}, {"A1": {"ts": NOW - DAY, "price": "1385000"}}, {"A1": "1320000"}, {}, NOW)
assert clear == ["A1"], clear
assert "A1" not in reqs

# 2) המחיר עוד לא ירד → נשאר
clear, reqs = plan({"A1"}, {"A1": {"ts": NOW - DAY, "price": "1385000"}}, {"A1": "1385000"}, {}, NOW)
assert clear == [] and reqs["A1"]["price"] == "1385000"

# 3) המחיר עלה → נשאר
clear, _ = plan({"A1"}, {"A1": {"ts": NOW, "price": "1385000"}}, {"A1": "1400000"}, {}, NOW)
assert clear == []

# 4) בקשה ישנה בלי רישום (מלפני הפריסה), ויש ירידת מחיר שנרשמה ב-7 הימים → מתבטל
clear, _ = plan({"A2"}, {}, {"A2": "1320000"}, {"L:A2": {"ts": NOW - 2 * DAY, "old": "1385000"}}, NOW)
assert clear == ["A2"]

# 5) בקשה ישנה בלי רישום ובלי ירידה → נרשם המחיר הנוכחי כנקודת התחלה, לא מתבטל
clear, reqs = plan({"A3"}, {}, {"A3": "900000"}, {}, NOW)
assert clear == [] and reqs["A3"]["price"] == "900000"
# ...ובסבב הבא, אחרי ירידה — מתבטל
clear, reqs = plan({"A3"}, reqs, {"A3": "880000"}, {}, NOW + 600)
assert clear == ["A3"]

# 6) ירידה ישנה (מעל 7 ימים) לא מבטלת בקשה בלי רישום
clear, _ = plan({"A4"}, {}, {"A4": "800000"}, {"L:A4": {"ts": NOW - 9 * DAY, "old": "850000"}}, NOW)
assert clear == []

# 7) נכס שלא נמצא בנכסי המשרד (למשל בקשת הסרה) — לא נוגעים
clear, reqs = plan({"A5"}, {}, {}, {"L:A5": {"ts": NOW, "old": "1"}}, NOW)
assert clear == [] and "A5" not in reqs

# 8) רישום של בקשה שכבר לא ממתינה נשמר עד 60 יום ואז נגזם
_, reqs = plan(set(), {"A6": {"ts": NOW - 10 * DAY, "price": "1"}, "A7": {"ts": NOW - 61 * DAY, "price": "1"}}, {}, {}, NOW)
assert "A6" in reqs and "A7" not in reqs

# 9) מחיר ריק בשורה — לא מבטל
clear, _ = plan({"A8"}, {"A8": {"ts": NOW, "price": "1000000"}}, {"A8": ""}, {}, NOW)
assert clear == []

print("ok 9")
