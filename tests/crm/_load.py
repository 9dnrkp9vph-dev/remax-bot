# tests/crm/_load.py — חילוץ פונקציות ברמת המודול מ-effie_v2.py (ast), בלי לייבא את כל האפליקציה.
import os, ast, re
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_SRC = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()

def load(*names, extra=None):
    ns = {"_re": re, "re": re}
    if extra:
        ns.update(extra)
    want = set(names)
    for node in ast.parse(_SRC).body:
        if (isinstance(node, ast.FunctionDef) and node.name in want) or (
                isinstance(node, ast.Assign) and [getattr(t, "id", "") for t in node.targets][0] in (want | {"_INV_TYPES", "_CRM_Y2_BRANCH", "_CRM_AGENT_BRANCH", "_CRM_BS_STATUS", "CRM_OWNER_ONLY"})):
            exec(compile(ast.Module([node], []), "effie_v2.py", "exec"), ns)
    missing = want - set(ns)
    if missing:
        raise NameError("not defined: " + ", ".join(sorted(missing)))
    return ns

n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1
