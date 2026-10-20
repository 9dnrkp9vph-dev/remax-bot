# tests/crm/test_props_branch.py — [21/10 אייל: 'לחלק את הנכסים במשרד לפי 3 המשרדים'] סניף לכל נכס משרד + תצוגה לכל סניף
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_props_records", "_crm_int", "_crm_rooms", "CRM_VIEWS", "CRM_MODULES", "_crm_day", "crm_query", "_crm_norm",
                "inv_phone9", "_CRM_Y2_BRANCH")
rec, q, BR = ns["crm_props_records"], ns["crm_query"], ns["_CRM_Y2_BRANCH"]
NOW = 1_800_000_000.0
ck(set(BR) == {"5625538", "5628636", "8532791"} and all(BR.values()) and len(set(BR.values())) == 3, BR)
of = [{"סוכן 1": "א", "כתובת": "רח %d" % i, "מחיר": "1000000", "_y2_office_id": oid, "_ep": NOW - 3600}
      for i, oid in enumerate(["5625538", "5628636", "5628636", "8532791", ""])]
h = {"prop_ep": lambda r: r["_ep"], "prop_pkey": lambda r: "L:" + r["כתובת"], "agent_name": lambda n: n,
     "nb_ep": None, "nb_pkey": None, "nb_office": None, "excl_ep": None, "excl_pkey": None}
R = rec([], [], of, {}, NOW, h)
by = {r["address"]: r for r in R}
ck(by["רח 0"]["branch"] == BR["5625538"] and by["רח 1"]["branch"] == BR["5628636"] and by["רח 3"]["branch"] == BR["8532791"], R)
ck(by["רח 4"]["branch"] == "", "no office id → no branch (sheet-era row)")
cols = [c[0] for c in ns["CRM_MODULES"]["props"]["columns"]]
ck("branch" in cols and "branch" in ns["CRM_MODULES"]["props"]["default_cols"], cols)
views = dict((v[0], v[1]) for v in ns["CRM_MODULES"]["props"]["views"])
V = lambda v: q(R, "", {"view": v}, "date", "desc", 1, 50, NOW, module="props")["total"]
for oid, n in (("5625538", 1), ("5628636", 2), ("8532791", 1)):
    ck(views.get("br_" + oid) == "המשרד · " + BR[oid] and V("br_" + oid) == n, (oid, views, V("br_" + oid)))
ck(V("office") == 5, "office view still counts all branches")
# [21/10 אייל: 'אלי שמול ויהודית תעביר לביאליק'] — סוכן שנמצא בסניף אחר ביד2 משויך לסניף שלו
of2 = [{"סוכן 1": n, "כתובת": "ש %d" % i, "מחיר": "1", "_y2_office_id": "8532791", "_ep": NOW} for i, n in enumerate(["אלי שמול", "יהודית שמול", "קובי חמו"])]
R2 = {r["agent"]: r["branch"] for r in rec([], [], of2, {}, NOW, h)}
ck(R2 == {"אלי שמול": "ביאליק", "יהודית שמול": "ביאליק", "קובי חמו": "קרית ים"}, R2)
print("props_branch OK", _load.n)
