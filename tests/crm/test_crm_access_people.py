# tests/crm/test_crm_access_people.py — מסך 'הרשאות': רשימת אנשי הצוות + המייל של כל אחד + ההרשאה הקיימת
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_access_people", "crm_access_clean", "CRM_MODULES", "CRM_ACCESS_MODULES")
people, clean = ns["crm_access_people"], ns["crm_access_clean"]
team = [["הודיה צרויה", "054-1111111", "", "", "hodaya.work@gmail.com"], ["רפי", "0542222222", "", "", ""], ["סוכן בדיקה", "0503333333"]]
gauth = {"hodaya@gmail.com": {"phone": "541111111"}, "rafi@gmail.com": {"phone": "0542222222"}}
acc = {"hodaya@gmail.com": {"name": "הודיה צרויה", "phone": "0541111111", "modules": ["meetings"], "scope": "team"},
       "old@gmail.com": {"name": "מישהו שעזב", "phone": "", "modules": ["calls"], "scope": "own"}}
P = people(team, gauth, acc, lambda p: "coordinator" if p.endswith("1111111") else "agent")
by = {p["name"]: p for p in P}
ck(by["הודיה צרויה"]["email"] == "hodaya@gmail.com" and by["הודיה צרויה"]["access"]["scope"] == "team" and by["הודיה צרויה"]["role"] == "coordinator",
   ("Google email linked to her phone wins over the contact email; existing access attached", by["הודיה צרויה"]))
ck(by["רפי"]["email"] == "rafi@gmail.com" and by["רפי"]["access"] is None, by["רפי"])
ck("סוכן בדיקה" not in by, "test accounts hidden")
ck(by["מישהו שעזב"]["email"] == "old@gmail.com" and by["מישהו שעזב"]["access"]["modules"] == ["calls"], ("access without a team row still listed", by["מישהו שעזב"]))
ck([p["name"] for p in P][0] == "הודיה צרויה", ("people with access first", [p["name"] for p in P]))
# שמירה: ניקוי קלט
ok = clean({"email": " Hodaya@Gmail.com ", "name": "הודיה", "phone": "054-1111111", "modules": ["meetings", "x", "dashboard"],
            "scope": "team", "export": 1, "edit": 0})
ck(ok == ("hodaya@gmail.com", {"name": "הודיה", "phone": "0541111111", "modules": ["meetings", "dashboard"], "scope": "team",
                                "export": True, "edit": False}), ok)
ck(clean({"email": "not-an-email", "modules": []}) is None and clean({"email": "a@b.co", "scope": "zzz"})[1]["scope"] == "own", "validation")
print("crm_access_people OK")
