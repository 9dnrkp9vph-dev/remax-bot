# tests/crm/test_props_excl_split.py — [16/11 אייל: 'כמה רגיל וכמה בלעדי בסניף ביאליק ובמוצקין?']
# במסך הנכסים שורה מעל הטבלה: בלעדי N · רגיל M, לפי הסינון הנוכחי (סניף, חיפוש, סוכן, תקופה).
import os, sys, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, ck, _SRC
import _load
ns = load("crm_excl_split", "crm_query", "_crm_norm", "inv_phone9", extra={"CRM_VIEWS": {"props": {}}})
f = ns["crm_excl_split"]
R = [{"key": str(i), "excl": e, "branch": b, "agent": a, "date": 0}
     for i, (e, b, a) in enumerate([("בלעדי", "ביאליק", "רפי"), ("בלעדי", "ביאליק", "דנה"), ("רגיל", "ביאליק", "רפי"),
                                     ("בלעדי", "מוצקין", "רפי"), ("", "ביאליק", "רפי")])]
out = f(R, "", {"view": "all"}, 0)
ck(out == {"excl": 3, "reg": 1}, out)
out = f(R, "", {"view": "all", "agent": "רפי"}, 0)
ck(out == {"excl": 2, "reg": 1}, ("agent filter", out))
# כפתור הסינון של המשתמש על עמודת הבלעדיות לא מאפס את הספירה
out = f(R, "", {"view": "all", "excl": "רגיל"}, 0)
ck(out == {"excl": 3, "reg": 1}, ("ignores excl filter", out))
# הראוט מחזיר את הספירה למודול הנכסים
i = _SRC.index('def v2_api_crm_list(module):'); seg = _SRC[i:i + 2600]
ck('module == "props"' in seg and 'crm_excl_split(' in seg, "list route returns excl split")
# הדף מציג את השורה
s = _SRC
j = s.index("function renderExcl("); body = s[j:s.index("\n", s.index("}", j) + 1)]
code = "var document={getElementById:function(){return E}},E={innerHTML:''};function esc(x){return String(x)}" + ";" + s[j:s.index("\nfunction", j + 10)] + \
       ";renderExcl({excl:122,reg:64});var a=E.innerHTML;renderExcl(null);var b=E.innerHTML;renderExcl({excl:0,reg:0});console.log(JSON.stringify([a,b,E.innerHTML]))"
r = subprocess.run(["node", "-e", code], capture_output=True, text=True)
ck(r.returncode == 0, r.stderr)
a, b, c = json.loads(r.stdout)
ck("122" in a and "64" in a and "בלעדי" in a and "רגיל" in a and "186" in a, a)
ck(b == "" and c == "", (b, c))
ck("renderExcl(j.excl)" in s, "called after load")
print("props_excl_split OK", _load.n)
