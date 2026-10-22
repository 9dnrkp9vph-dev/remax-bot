# tests/gauth/test_email_for_phone.py — אייל 22/10: ירין לוי רוצה להחליף את חשבון ה-Google של היומן
# מ-yarinlevi0607 ל-yarinnnn0607 ו"לא מצליח": כמה מיילים מקושרים לאותו טלפון, והראשון בקובץ תמיד ניצח.
import os, ast
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
G = {}
ns = {"_last9": lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:], "_gauth_all": lambda: G}
for node in ast.parse(src).body:
    if isinstance(node, ast.FunctionDef) and node.name == "_gauth_email_for_phone":
        exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
f = ns["_gauth_email_for_phone"]
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
G.update({"old@x.com": {"phone": "504567763", "refresh_token": "a", "ts": 100},
          "eyal@x.com": {"phone": "505709865", "refresh_token": "e", "ts": 50},
          "new@x.com": {"phone": "504567763", "refresh_token": "b", "ts": 200}})
ck(f("0504567763") == "new@x.com", f("0504567763"))          # המקושר האחרון גובר
ck(f("0505709865") == "eyal@x.com", "other phone")
ck(f("0521111111") == "", "unknown")
# מייל חדש בלי טוקן יומן (קישור כניסה בלבד) לא מחליף חשבון שיש לו יומן
G["login-only@x.com"] = {"phone": "504567763", "ts": 300}
ck(f("0504567763") == "new@x.com", "prefer one with calendar token")
# רשומות ישנות בלי ts — עדיין נמצאות
G.clear(); G["legacy@x.com"] = {"phone": "504567763"}
ck(f("0504567763") == "legacy@x.com", "legacy")
print("OK", n, "checks")
