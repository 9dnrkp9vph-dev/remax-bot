# tests/home/test_drops_today.py — [HOME-TILES 08/11] ספירת ירידות המחיר של היום (שעון ישראל)
import ast, os, time
SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "app.py"), encoding="utf-8").read()
ns = {"time": time}
for node in ast.parse(SRC).body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_il_midnight_epoch", "drops_today_count"):
        exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
from datetime import datetime
from zoneinfo import ZoneInfo
TZ = ZoneInfo("Asia/Jerusalem")
# 00:30 בישראל = 22:30 UTC יום קודם — חצות לפי ישראל, לא לפי השרת
t = datetime(2026, 11, 8, 0, 30, tzinfo=TZ).timestamp()
mid = ns["_il_midnight_epoch"](t)
assert mid == datetime(2026, 11, 8, 0, 0, tzinfo=TZ).timestamp(), mid
rows = [{"k": "a"}, {"k": "b"}, {"k": "c", "ירד מפרסום": "07/11"}, {"k": "d", "delisted_at": "x"}, {"k": ""}, {"k": "e"}]
ts = {"a": mid + 10, "b": mid - 1, "c": mid + 5, "d": mid + 5, "e": mid}
assert ns["drops_today_count"](rows, lambda r: r["k"], ts, mid) == 2   # a + e
assert ns["drops_today_count"]([], lambda r: r["k"], ts, mid) == 0
print("ok")
