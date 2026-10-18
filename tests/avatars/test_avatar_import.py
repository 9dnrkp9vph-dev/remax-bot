# tests/avatars/test_avatar_import.py — אייל 18/10: "סנכרון מלא — כל תמונה תופיע גם באפי וגם באתר" (אפשרות א)
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import avatar_import as A
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
key = lambda s: re.sub(r"[\s'\"׳״.\-]", "", str(s or ""))
# טלפון → שם (אנשי קשר + כניסות)
pmap = {"527245668": "רפי דה פיצ'וטו", "522265921": "רפי דה פיצוטו",   # שני איותים — אותו אדם
        "505709865": "אייל שמול", "541111111": "בינימין אביטן", "542222222": "דנה חדשה",
        "543333333": "מנהלת חשבונות"}
people = A.people_from(pmap, key, removed={key("מנהלת חשבונות")})
byn = {p["key"]: p for p in people}
ck(sorted(byn[key("רפי דה פיצ'וטו")]["phones"]) == ["522265921", "527245668"], byn)
ck(key("מנהלת חשבונות") not in byn, "removed agents skipped")
idx = [{"name": "רפי דה פיצ'וטו", "file": "r.jpg"}, {"name": "אייל שמול", "file": "e.jpg"},
       {"name": "בנימין אביטן", "file": "b.jpg"}]
has = lambda phones: "505709865" in phones           # לאייל כבר יש תמונה באפי
plan = A.plan(people, idx, key, has, aliases={"בינימין אביטן": "בנימין אביטן"})
imp = {x["name"]: x for x in plan["import"]}
ck(set(imp) == {"רפי דה פיצ'וטו", "בינימין אביטן"} or set(imp) == {"רפי דה פיצוטו", "בינימין אביטן"}, plan)
r = [x for x in plan["import"] if key(x["name"]) == key("רפי דה פיצ'וטו")][0]
ck(r["file"] == "r.jpg" and sorted(r["phones"]) == ["522265921", "527245668"], r)
ck([x for x in plan["import"] if x["file"] == "b.jpg"], "alias: בינימין → בנימין")
ck(plan["has"] == ["אייל שמול"], plan["has"])                 # לא דורסים תמונה קיימת
ck(plan["missing"] == ["דנה חדשה"], plan["missing"])           # אין תמונה באתר הישן
# בדיקת 'יש תמונה' שנכשלה (None) — לא מייבאים בלי לדעת
plan2 = A.plan(people, idx, key, lambda ph: None, aliases={})
ck(plan2["import"] == [] and len(plan2["unknown"]) == 2, plan2)
# הקבצים האמיתיים
import json
I = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "site_photos", "index.json"), encoding="utf-8"))
ck(len(I) == 50 and all(os.path.exists(os.path.join(os.path.dirname(__file__), "..", "..", "site_photos", x["file"])) for x in I), "files")
ck(any(x["name"] == "רפי דה פיצ'וטו" for x in I), "rafi in index")
print("OK", n, "checks")
