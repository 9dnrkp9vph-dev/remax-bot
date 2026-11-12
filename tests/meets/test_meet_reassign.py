# -*- coding: utf-8 -*-
"""[MEET-REASSIGN 12/11] (אייל: 'איך המתאמת יכולה בעריכה לשנות לסוכן אחר?')
עריכת פגישה עם agent אחר: המפתח עובר לסוכן החדש, היומן הישן נמחק ונוצר מחדש, 'תיאם' נשמר.
python3 tests/meets/test_meet_reassign.py"""
import ast, os, time, types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "api_newborn_status_edit")
fn.decorator_list = []
code = ast.get_source_segment(src, fn)
code = code[code.index("def "):]

CFG = {}
CREATED, DELETED, LOG = [], [], []
ST = {"sess": None, "body": {}}

class Req:
    def get_json(self, silent=True): return ST["body"]

def mutate(f):
    f(CFG); return True, None

def cal_create(rec, date, org):
    CREATED.append(rec.get("agent")); return [{"email": "x", "id": "ev-" + rec.get("agent", "")}]

ns = dict(
    request=Req(), jsonify=lambda *a, **k: (a[0] if a else k), time=time,
    _web_auth=lambda: ST["sess"],
    _coordinators_all=lambda: {"528899985": {"names": {"קובי חמו"}, "agents": set()}},
    web_phone_name_map=lambda: {"1": "קובי חמו", "2": "רפי דה פיצ'וטו", "3": "הודיה צרויה"},
    web_contacts_phone_name=lambda: {}, _load_config=lambda: CFG,
    _canon_key=lambda n: "".join(str(n or "").split()), _last9=lambda p: str(p)[-9:],
    _nb_cal_create=cal_create, _gauth_email_for_phone=lambda p: "coord@x",
    _goals=types.SimpleNamespace(meeting_stamp=lambda prev, st, t: None),
    _config_mutate=mutate, _nb_result_bump=lambda: None,
    _log_activity=lambda *a: LOG.append(a), gcal_delete_event=lambda e, i: DELETED.append(i),
)
exec(code, ns)
api = ns["api_newborn_status_edit"]

def reset():
    CFG.clear(); CREATED.clear(); DELETED.clear(); LOG.clear()
    CFG["nbStatus"] = {"קוביחמו::id:1": {"status": "meeting", "agent": "קובי חמו", "pkey": "id:1", "addr": "עפרה חזה 16",
                       "date": "2026-11-13T09:00", "by": "הודיה צרויה", "cal": [{"email": "x", "id": "old"}]}}

fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

COORD = {"name": "הודיה צרויה", "role": "coordinator", "phone": "0528899985"}
reset(); ST["sess"] = COORD
ST["body"] = {"skey": "קוביחמו::id:1", "date": "2026-11-13T09:00", "status": "meeting", "agent": "רפי דה פיצ'וטו"}
r = api()
m = CFG["nbStatus"]
check(r.get("ok") is True, "מתאמת מעבירה פגישה של הסוכן שלה לסוכן אחר במשרד")
check("קוביחמו::id:1" not in m and "רפידהפיצ'וטו::id:1" in m, "המפתח עבר לסוכן החדש")
nr = m.get("רפידהפיצ'וטו::id:1", {})
check(nr.get("agent") == "רפי דה פיצ'וטו" and nr.get("by") == "הודיה צרויה", "שם הסוכן התעדכן, 'תיאם' נשמר")
check(DELETED == ["old"] and CREATED == ["רפי דה פיצ'וטו"], "אירוע היומן הישן נמחק ונוצר חדש לסוכן החדש")
check("הועבר" in LOG[-1][4], "ביומן הפעילות כתוב שהועבר")

reset(); ST["sess"] = COORD
ST["body"] = {"skey": "קוביחמו::id:1", "date": "2026-11-13T09:00", "status": "meeting", "agent": "קובי חמו"}
api()
check("קוביחמו::id:1" in CFG["nbStatus"] and not DELETED, "אותו סוכן — בלי העברה ובלי נגיעה ביומן")

reset(); ST["sess"] = COORD
ST["body"] = {"skey": "קוביחמו::id:1", "date": "2026-11-13T09:00", "status": "meeting", "agent": "מישהו מבחוץ"}
r = api()
check(isinstance(r, tuple) and r[0].get("reason") == "agent" and "קוביחמו::id:1" in CFG["nbStatus"], "סוכן לא מוכר — נדחה, לא זז")

reset(); ST["sess"] = COORD
CFG["nbStatus"]["רפידהפיצ'וטו::id:1"] = {"status": "followup", "agent": "רפי דה פיצ'וטו", "pkey": "id:1", "date": "2026-11-20"}
ST["body"] = {"skey": "קוביחמו::id:1", "date": "2026-11-13T09:00", "status": "meeting", "agent": "רפי דה פיצ'וטו"}
r = api()
check(isinstance(r, tuple) and r[0].get("reason") == "agent_busy" and len(CFG["nbStatus"]) == 2, "לסוכן החדש כבר פגישה פתוחה בנכס — נדחה, שום דבר לא נדרס")

reset(); ST["sess"] = {"name": "קובי חמו", "role": "agent", "phone": "0500000001"}
ST["body"] = {"skey": "קוביחמו::id:1", "date": "2026-11-13T09:00", "status": "meeting", "agent": "רפי דה פיצ'וטו"}
api()
check("קוביחמו::id:1" in CFG["nbStatus"], "סוכן רגיל לא יכול להעביר (השדה מתעלם)")

print("FAIL" if fails else "OK"); raise SystemExit(1 if fails else 0)
