# tests/buyers/test_bstat_per_buyer.py — אייל 22/10: "עוז דנילוב הוסיף קונה ואנחנו לא רואים אותו".
# הסטטוס נשמר לפי טלפון בלבד — 'סגר' של קונה ישן (מתן, אותו נייד) הסתיר כל קונה חדש עם המספר,
# ומאז 07/10 אין טאב 'סגרו'. עכשיו: סטטוס לכל קונה (טלפון + סוכן), והמפתחות הישנים מומרים פעם אחת.
import os, ast, re, datetime as dt
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
src = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
ns = {"_re": re, "_CRM_BSTAT": {"active": "פעיל", "hot": "חם", "frozen": "בהקפאה", "closed": "סגר"},
      "_crm_int": lambda v: v, "_crm_bpage_sum": lambda p: ""}
for node in ast.parse(src).body:
    if isinstance(node, (ast.FunctionDef, ast.Assign)) and getattr(node, "name", None) in (
            "bstat_key", "bstat_of", "bstat_migrate", "bstat_set_times", "crm_buyer_records") or (
            isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_BSTAT_CUTOFF" for t in node.targets)):
        exec(compile(ast.Module([node], []), "effie_v2.py", "exec"), ns)
key, of, mig, times = ns["bstat_key"], ns["bstat_of"], ns["bstat_migrate"], ns["bstat_set_times"]
canon = lambda s: re.sub(r"\s", "", s)
EP = lambda s: dt.datetime.strptime(s, "%d/%m/%Y").timestamp() if s else 0
T = lambda s: dt.datetime.strptime(s, "%d/%m/%Y %H:%M").timestamp()
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
old = {"row": 300, "phone": "054-444-8065", "agent": "מתן ביטון", "date": "01/10/2026", "name": "בדיקה"}
oz = [{"row": r, "phone": "0544448065", "agent": "עוז דנילוב", "date": d, "name": "ק" + str(r)}
      for r, d in ((896, "20/10/2026"), (902, "21/10/2026"), (912, "22/10/2026"))]
nophone = {"row": 50, "phone": "", "agent": "עוז דנילוב", "date": "01/01/2026"}
ck(key(old, canon) == "544448065|מתןביטון", key(old, canon))
ck(key(nophone, canon) == "r50", key(nophone, canon))
# לפני ההמרה (קובץ ישן) — ההתנהגות הישנה נשמרת
legacy = {"544448065": "closed", "r50": "hot"}
ck(of(oz[0], legacy, canon) == "closed" and of(nophone, legacy, canon) == "hot", "legacy read")
# ההמרה: הסטטוס נקבע ב-05/10 (יומן) → רק קונה שנכנס עד אז
st = times([{"ts": T("05/10/2026 12:00"), "action": "עדכון סטטוס קונה", "detail": "544448065 → closed"},
            {"ts": T("03/10/2026 12:00"), "action": "עדכון סטטוס קונה", "detail": "544448065 → hot"}], [], canon)
ck(st == {"544448065": T("05/10/2026 12:00")}, st)
m2 = mig(legacy, [old] + oz + [nophone], st, EP, canon)
ck(m2.get("544448065|מתןביטון") == "closed" and "544448065" not in m2 and m2.get("r50") == "hot" and m2["_v"] == 2, m2)
ck(of(old, m2, canon) == "closed", "old still closed")
ck(all(of(b, m2, canon) is None for b in oz), "Oz's buyers active")
# בלי רישום ביומן — הסטטוס נחשב ישן (לפני 25/08): קונים מאז לא מושפעים
m3 = mig({"544448065": "frozen"}, [dict(old, date="01/07/2026")] + oz, {}, EP, canon)
ck(m3.get("544448065|מתןביטון") == "frozen" and of(oz[2], m3, canon) is None, m3)
# שינוי מה-CRM (נרשם לפי שם) — נחשב כמועד הקביעה לטלפון של הקונה באותו שם
st2 = times([{"ts": T("21/10/2026 09:00"), "action": "קונים (CRM) — עריכה", "detail": "ק896 · סטטוס"}], oz, canon)
ck(st2 == {"544448065": T("21/10/2026 09:00")}, st2)
later = {"row": 920, "phone": "0544448065", "agent": "אלי שמול", "date": "22/10/2026"}
m4 = mig({"544448065": "hot"}, oz + [later], st2, EP, canon)
ck(of(oz[2], m4, canon) == "hot", "same agent+phone = same buyer")   # קונה אחד לכל סוכן
ck(of(later, m4, canon) is None, m4)
# המרה חוזרת לא משנה; מפתח חדש קיים לא נדרס
ck(mig(m2, [old] + oz, st, EP, canon) == m2, "idempotent")
# CRM records משתמשים באותו כלל
recs = ns["crm_buyer_records"]([old] + oz, m2, EP, canon=canon)
ck([r["status_code"] for r in recs] == ["closed", "active", "active", "active"], [r["status_code"] for r in recs])
print("OK", n, "checks")
