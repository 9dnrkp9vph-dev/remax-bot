import os, re, sys, ast
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import goals

assert goals.meeting_stamp({}, "meeting", 100.0) == 100.0
assert goals.meeting_stamp({"meeting_at": 50.0}, "followup", 100.0) == 50.0
assert goals.meeting_stamp({"meeting_at": 50.0}, "meeting", 200.0) == 50.0
assert goals.meeting_stamp({}, "followup", 100.0) is None
assert goals.meeting_stamp(None, "meeting", 7.0) == 7.0

src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
tree = ast.parse(src)
fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
def body(name): return ast.get_source_segment(src, fns[name])
assert "meeting_stamp(" in body("api_newborn_status"), "status handler"
assert "meeting_stamp(" in body("api_newborn_status_edit"), "edit handler"
done = body("api_newborn_status_done")
assert "meeting_at" not in done and 'm[skey] = ' not in done and "mm[skey] = " not in done, "done must not replace record"
print("OK")
