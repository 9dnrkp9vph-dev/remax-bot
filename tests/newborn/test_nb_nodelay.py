# tests/newborn/test_nb_nodelay.py — הסרת מנגנון ההשהיה של נכס נולד (החלטת אייל 30/09: "לכולם מיד")
import ast, os
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
APP = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
V2 = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
tree = ast.parse(APP)
names = {x.name for x in ast.walk(tree) if isinstance(x, ast.FunctionDef)}
assigns = {t.id for x in ast.walk(tree) if isinstance(x, ast.Assign) for t in x.targets if isinstance(t, ast.Name)}
n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1
for gone in ("_fetch_newborn_delays", "_delayed_admin_days", "api_dev_nb_default"):
    ck(gone not in names, "function still exists: " + gone)
for gone in ("NEWBORN_HIDDEN", "NEWBORN_DELAYS_DISABLED", "NEWBORN_DEFAULT_DELAY", "_DELAYED_ADMINS",
             "_DELAYED_ADMIN_PHONES", "_LAST_GOOD_NB_DELAYS", "NEWBORN_DELAYS_TAB"):
    ck(gone not in assigns, "constant still exists: " + gone)
for word in ("_fetch_newborn_delays", "_delayed_admin_days", "NEWBORN_HIDDEN", "newbornDelay",
             "/api/dev/newborn_default", "nbDelay", "nbHidden", "nbDefault", "newborn_delays"):
    ck(word not in APP, "app.py still mentions " + word)
for word in ("_fetch_newborn_delays", "newbornDelay", "nbDelay", "nbHidden", "NB_DEFAULT", "nbDefault",
             "newborn_default", "pickNb", "nbSeg"):
    ck(word not in V2, "effie_v2.py still mentions " + word)
ast.parse(V2)
print("ok", n)
