# tests/avatars/test_sign_avatar.py — אייל 18/10: 'לאן נעלמה התמונה של רפי' — דף ההסכם בדק תמונה רק בדיסק
import sys, os, ast
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
ns = {}
for node in ast.parse(src).body:
    if isinstance(node, ast.FunctionDef) and node.name == "_pick_avatar_phone":
        exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
pick = ns["_pick_avatar_phone"]
C = ["527245668", "529097700", "522265921"]
ck(pick(C, lambda p: p == "529097700", {"522265921"}) == "529097700", "local file wins")
ck(pick(C, lambda p: False, {"522265921"}) == "522265921", "photo only in Supabase under 3rd phone")
ck(pick(C, lambda p: False, set()) == "", "no photo anywhere → letter, no broken img")
ck(pick(C, lambda p: False, None) == "527245668", "Supabase unknown → old behaviour (first)")
ck(pick([], lambda p: True, None) == "", "no candidates")
# supabase_db.avatar_phones: שאילתה אחת לכל המספרים
import supabase_db as S
calls = []
class R:
    def raise_for_status(self): pass
    def json(self): return [{"phone": "522265921"}]
S.enabled = lambda: True
S.requests.get = lambda url, **k: (calls.append((url, k.get("params"))), R())[1]
got = S.avatar_phones(["0527245668", "522265921", ""])
ck(got == {"522265921"}, got)
ck(calls and calls[0][1]["phone"] == "in.(527245668,522265921)" and calls[0][1]["select"] == "phone", calls)
def boom(*a, **k): raise RuntimeError("x")
S.requests.get = boom
ck(S.avatar_phones(["522265921"]) is None, "failure → None (unknown)")
ck(S.avatar_phones([]) == set(), "empty")
print("OK", n, "checks")
