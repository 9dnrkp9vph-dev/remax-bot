# tests/crm/test_crm_access_logic.py — הרשאות CRM (אייל 21/10): מי נכנס, אילו מודולים, ואיזה היקף נתונים
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_access_for", "crm_scope_filter", "CRM_MODULES", "CRM_ACCESS_MODULES", "_CRM_AGENTLESS")
acc, flt = ns["crm_access_for"], ns["crm_scope_filter"]
ALL = ns["CRM_ACCESS_MODULES"]
ck("dashboard" in ALL and "calls" in ALL and "access" not in ALL, ALL)
cfg = {"v2_crm_access": {"hodaya@gmail.com": {"name": "הודיה צרויה", "phone": "0541111111", "modules": ["buyers", "meetings", "bogus"],
                                              "scope": "team", "export": False, "edit": True}}}
own = {"eyalshmul@gmail.com"}
o = acc("eyalshmul@gmail.com", "", cfg, own, lambda p: False)
ck(o["owner"] and o["scope"] == "all" and o["export"] and o["edit"] and set(o["modules"]) == set(ALL) | {"access", "ai"}, o)
ck(acc("x@gmail.com", "505709865", cfg, own, lambda p: p == "505709865")["owner"], "Google email linked to a dev phone = owner")
h = acc("Hodaya@Gmail.com ", "", cfg, own, lambda p: False)
ck(h and not h["owner"] and h["modules"] == ["buyers", "meetings"] and h["scope"] == "team" and h["phone"] == "0541111111"
   and h["export"] is False and h["edit"] is True and h["name"] == "הודיה צרויה", ("unknown module dropped, email case-insensitive", h))
ck(acc("stranger@gmail.com", "", cfg, own, lambda p: False) is None, "not in the list → no access")
ck(acc("", "", cfg, own, lambda p: False) is None, "no email → no access")
cfg2 = {"v2_crm_access": {"z@gmail.com": {"modules": ["calls"], "scope": "weird"}}}
ck(acc("z@gmail.com", "", cfg2, own, lambda p: False)["scope"] == "own", "unknown scope → the narrowest")
# ── סינון לפי היקף ──
canon = lambda n: str(n or "").replace(" ", "")
keys = {"רפי", "דנה"}
R = [{"key": 1, "agent": "רפי"}, {"key": 2, "agent": "אוצר"}, {"key": 3, "agent": "רפי + אוצר"}, {"key": 4, "agent": ""}]
ck([r["key"] for r in flt("buyers", R, keys, canon)] == [1, 3], "own agents, joint deals count for each member")
ck([r["key"] for r in flt("buyers", R, None, canon)] == [1, 2, 3, 4], "scope all → no filter")
ck([r["key"] for r in flt("props", R, keys, canon)] == [1, 3, 4], "props: rows without agent (private / shtaf) stay")
M = [{"key": "a", "agent": "אוצר", "by": "דנה"}, {"key": "b", "agent": "אחר", "by": "אחר"}]
ck([r["key"] for r in flt("meetings", M, keys, canon)] == ["a"], "meetings: also by who coordinated")
for m in ns["_CRM_AGENTLESS"]:
    ck(flt(m, R, keys, canon) == [], m + ": no agent field → only for scope 'all'")
ck([r["key"] for r in flt("buyers", [{"key": 9, "agent": "אבי וייס"}], {"אביוייס"}, canon)] == [9], "a name with ' ו' is not split")
print("crm_access_logic OK")
