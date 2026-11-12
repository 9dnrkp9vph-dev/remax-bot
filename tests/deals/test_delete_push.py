# -*- coding: utf-8 -*-
"""פוש על מחיקת תהליך/עסקה למנהלים (אייל 12/11). python3 tests/deals/test_delete_push.py"""
import ast, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "_deals_notify_deleted")
P, L = [], []
class T:
    def __init__(self, target=None, args=(), daemon=None): self.t, self.a = target, args
    def start(self): self.t(*self.a)
ns = dict(threading=type("m", (), {"Thread": T}), send_push=lambda *a: P.append(a),
          _manager_push_ids=lambda: ["505709865", "544448065"], _log_activity=lambda *a: L.append(a))
exec(ast.get_source_segment(src, fn), ns)
f = ns["_deals_notify_deleted"]
S = {"name": "נוי רבן", "role": "coordinator", "phone": "0504875995"}
f({"notes": "עפרה חזה 16", "agents": ["קובי חמו"]}, S)
f({"notes": "הנוטר 28", "agents": ["נדב רייזר", "רפי"], "deal": True}, S)
ok = (P[0][0].startswith("תהליך נמחק") and P[0][2] == ["505709865", "544448065"]
      and "עפרה חזה 16" in P[0][1] and "קובי חמו" in P[0][1] and "נוי רבן" in P[0][1]
      and P[1][0].startswith("עסקה נמחקה") and "נדב רייזר + רפי" in P[1][1] and len(L) == 2)
print(P); print("OK" if ok else "FAIL"); raise SystemExit(0 if ok else 1)
