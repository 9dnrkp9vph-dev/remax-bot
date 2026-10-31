# tests/crm/test_dash_site_contacts.py — [31/10 אייל: 'למה לקוחות לא משאירים פרטים באתר?'] פניות מהאתר בלוח הבקרה
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_site_contacts")
F = ns["crm_site_contacts"]
NOW = 1_800_000_000.0
b = {"day": NOW - 3600, "week": NOW - 3 * 86400, "month": NOW - 20 * 86400, "year": NOW - 200 * 86400}
rows = [{"ts": NOW - 60, "action": "לחיצה מהאתר — וואטסאפ לסוכן", "detail": "רפי · גושן 5, קרית מוצקין · גוגל"},
        {"ts": NOW - 90, "action": "לחיצה מהאתר — טלפון לסוכן", "detail": "רפי · גושן 5, קרית מוצקין · ישיר"},
        {"ts": NOW - 5 * 86400, "action": "לחיצה מהאתר — וואטסאפ לסוכן", "detail": "דנה · — · גוגל"},
        {"ts": NOW - 100 * 86400, "action": "לחיצה מהאתר — טלפון לסוכן", "detail": "דנה · הנרקיס · ישיר"},
        {"ts": NOW - 120, "action": "פנייה מהאתר — הערכת שווי", "detail": "x"},
        {"ts": NOW - 4 * 86400, "action": "ליד מהאתר — סוכן AI אישי", "detail": "y"},
        {"ts": NOW - 10, "action": "חיפוש נכסים", "detail": "z"}]
o = F(rows, b)
p = o["periods"]
ck(p["day"] == {"wa": 1, "tel": 1, "form": 1, "ai": 0}, p["day"])
ck(p["week"] == {"wa": 1, "tel": 1, "form": 1, "ai": 0} and p["month"] == {"wa": 2, "tel": 1, "form": 1, "ai": 1}, p)
ck(p["year"]["tel"] == 2, p["year"])
t = o["month_top"]
ck(t["agents"] == [["רפי", 2], ["דנה", 1]] and t["listings"] == [["גושן 5, קרית מוצקין", 2]], t)
ck(t["src"] == [["גוגל", 2], ["ישיר", 1]] and o["since"] == NOW - 100 * 86400, (t, o["since"]))
ck(F([], b)["since"] is None and F([], b)["periods"]["day"]["wa"] == 0, "empty")
print("dash_site_contacts OK", _load.n)
# הכרטיס בדף — הפונקציה האמיתית מהדף, על הנתונים למעלה
import re as _re, json as _json, subprocess as _sp, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
h = A.app.test_client().get("/v2/crm/dashboard").get_data(as_text=True)
m = _re.search(r"<script>(\s*var P='month'.*?)</script>", h, _re.S)
js = ("var document={getElementById:function(){return {}}},localStorage={getItem:function(){return ''}},fetch=function(){return {then:function(){return {then:function(){return {catch:function(){}}},catch:function(){}}}}},setInterval=function(){};"
      + m.group(1).split("function render(){")[0] + ";D={site_contacts:" + _json.dumps(o, ensure_ascii=False) + "};console.log(siteCt());D={};console.log('['+siteCt()+']');")
out = _sp.run(["node", "-e", js], capture_output=True, text=True)
ck(out.returncode == 0, out.stderr[-500:])
ck("פניות מהאתר" in out.stdout and "וואטסאפ לסוכן" in out.stdout and "רפי · 2" in out.stdout and "גושן 5" in out.stdout, out.stdout[:600])
ck(out.stdout.strip().endswith("[]"), "no data → no card")
ck("siteCt()" in h.split("function render(){")[-1], "card wired into render")
print("dash_site_contacts card OK", _load.n)
