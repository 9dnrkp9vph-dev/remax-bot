# -*- coding: utf-8 -*-
"""🐞 04/11 (אייל, צילום יומן של אירנה): 'פולו-אפ לבעל נכס - דויד' 4 פעמים באותה שעה.
שמירה חוזרת של סטטוס לאותו נכס+סוכן יצרה אירוע חדש ביומן ודרסה את מזהי האירועים הקודמים
בלי למחוק אותם — כל שמירה השאירה אירוע יתום. עכשיו: האירועים הקודמים נמחקים אחרי שמירה מוצלחת.
python3 tests/meets/test_status_resave_cal.py"""
import ast, os, time, types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "api_newborn_status")
fn.decorator_list = []
code = ast.get_source_segment(src, fn)
code = code[code.index("def "):]

CFG = {"nbStatus": {}}
CREATED, DELETED = [], []
STATE = {"save_ok": True, "body": {}}


class Req:
    def get_json(self, silent=True):
        return STATE["body"]


class Thr:   # רץ מיד — הבדיקה סינכרונית
    def __init__(self, target=None, daemon=None, args=()):
        self.t, self.a = target, args

    def start(self):
        self.t(*self.a)


def mutate(fn):
    if not STATE["save_ok"]:
        return False, None
    fn(CFG)
    return True, None


def cal_create(rec, date, org):
    eid = "ev%d" % (len(CREATED) + 1)
    CREATED.append(eid)
    return [{"email": "irena@x", "id": eid}]


ns = dict(
    request=Req(), jsonify=lambda *a, **k: (a[0] if a else k), time=time,
    _web_auth=lambda: {"name": "אירנה אוברוב", "role": "agent", "phone": "0501234567"},
    _coordinators_all=lambda: {}, web_phone_name_map=lambda: {}, web_contacts_phone_name=lambda: {},
    _load_config=lambda: CFG, _canon_key=lambda n: "".join(str(n or "").split()),
    _last9=lambda p: str(p)[-9:], _NB_STATUS_LABELS={"meeting": "פגישה", "followup": "פולו-אפ", "none": "—"},
    _nb_cal_create=cal_create, _gauth_email_for_phone=lambda p: "irena@x",
    _goals=types.SimpleNamespace(meeting_stamp=lambda prev, st, t: None),
    _config_mutate=mutate, _NB_RESULT_VER=[0], _log_activity=lambda *a: None,
    gcal_delete_event=lambda email, eid: DELETED.append(eid),
    _threading=types.SimpleNamespace(Thread=Thr),
)
exec(code, ns)
api = ns["api_newborn_status"]
B = {"key": "id:57698991", "addr": "לילך 1", "owner": "דויד", "status": "followup", "date": "2026-11-08T10:30"}

fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

STATE["body"] = B
for _ in range(4):
    api()
rec = CFG["nbStatus"]["אירנהאוברוב::id:57698991"]
check(len(CREATED) == 4, "כל שמירה יוצרת אירוע")
check(DELETED == ["ev1", "ev2", "ev3"], "האירועים הקודמים נמחקו — נשאר אחד ביומן")
check([e["id"] for e in rec["cal"]] == ["ev4"], "הרשומה מחזיקה רק את האירוע האחרון")

STATE["body"] = dict(B, status="none", date="")
api()
check("ev4" in DELETED, "שינוי לסטטוס בלי תאריך — האירוע הישן נמחק")

STATE["body"] = B
api()   # ev5
STATE["save_ok"] = False
n_del = len(DELETED)
r = api()   # ev6 נוצר, השמירה נכשלה
check(r.get("ok") is False and len(DELETED) == n_del + 1 and DELETED[-1] == "ev6",
      "שמירה נכשלה — לא נוגעים באירוע הקיים, ומוחקים את האירוע החדש שלא נשמר")
check([e["id"] for e in CFG["nbStatus"]["אירנהאוברוב::id:57698991"]["cal"]] == ["ev5"], "האירוע הקיים נשאר ברשומה")

print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED" % len(fails))
raise SystemExit(1 if fails else 0)
