# tests/crm/test_team_fix.py — תיקוני נתוני הצוות: מייל מעמודה D, רישיון מהאזור האישי, נרמול טלפונים, 'עודכן ע"י' אמיתי
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("team_phone_norm", "team_fix_plan", "_TEAM_GENERIC_BY")
norm, plan = ns["team_phone_norm"], ns["team_fix_plan"]
# טלפונים: (ערך מנורמל, תקין?)
ck(norm("546612292") == ("0546612292", True), norm("546612292"))
ck(norm("054-6000808") == ("0546000808", True), "dashes removed")
ck(norm("+972 52-912-6164") == ("0529126164", True), "972 prefix")
ck(norm("04-6000800") == ("046000800", True), "landline")
ck(norm("58264698") == ("58264698", False), "broken number kept as-is, flagged")
ck(norm("") == ("", True), "empty is fine")
rows = [
    {"id": "1", "name": "אבי לף", "phone": "58264698", "vphone": "", "license": "avilap1@gmail.com", "email": "", "updated_by": "מנהל"},
    {"id": "2", "name": "אווה אזולאי", "phone": "546612292", "vphone": "052-9706880", "license": "even3277@gmail.com", "email": "", "updated_by": "מנהל"},
    {"id": "3", "name": "דנה", "phone": "0501111111", "vphone": "", "license": "3123", "email": "d@x.co", "updated_by": "אייל שמול"},
    {"id": "4", "name": "רועי", "phone": "050-2222222", "vphone": "", "license": "", "email": "", "updated_by": "מנהל"},
]
lic = {"546612292": "4321", "502222222": "777"}
p = {x["id"]: x for x in plan(rows, lic, "אייל שמול")}
a = p["1"]
ck(a["changes"]["email"] == ["", "avilap1@gmail.com"] and a["changes"]["license"] == ["avilap1@gmail.com", ""], a)
ck("phone" not in a["changes"] and a["warn"] == ["טלפון לא תקין: 58264698"], a)
ck(a["changes"]["updated_by"] == ["מנהל", "אייל שמול"], "generic updater replaced")
e = p["2"]
ck(e["changes"]["email"][1] == "even3277@gmail.com" and e["changes"]["license"] == ["even3277@gmail.com", "4321"], ("email moved, license from personal area", e))
ck(e["changes"]["phone"] == ["546612292", "0546612292"] and e["changes"]["vphone"] == ["052-9706880", "0529706880"], e)
ck("3" not in p, "clean row → no entry")
r = p["4"]
ck(r["changes"]["license"] == ["", "777"] and r["changes"]["phone"] == ["050-2222222", "0502222222"], r)
# כבר במייל — לא דורסים מייל קיים; רישיון קיים לא נדרס מהאזור האישי
x = plan([{"id": "5", "name": "ש", "phone": "0503333333", "vphone": "", "license": "a@b.co", "email": "keep@x.co", "updated_by": "ש"}], {"503333333": "99"}, "אייל")
ck(x[0]["changes"]["license"] == ["a@b.co", "99"] and "email" not in x[0]["changes"], ("existing email kept", x))
y = plan([{"id": "6", "name": "נקי", "phone": "0504444444", "vphone": "", "license": "1", "email": "a@b.co", "updated_by": "מנהל"}], {}, "אייל שמול")
ck(y and y[0]["changes"] == {"updated_by": ["מנהל", "אייל שמול"]}, ("generic updater alone is fixed", y))
print("team_fix OK", _load.n)
