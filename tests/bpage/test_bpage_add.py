"""15/11 (אייל): 'לדף קונה' מתוך החיפוש — נכס נולד, המשרד ושת"פ; רק לקונה שלי שיש לו דף.
python3 tests/bpage/test_bpage_add.py"""
import os, sys, re, json, subprocess
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("HOME_WARM", "0")
from flask import Flask
import effie_v2 as E

fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

class SB:
    def __init__(self):
        self.pages = [{"id": "p1", "row": 10, "token": "TOK1", "last_sent_at": "2026-11-10T10:00:00Z", "expires_at": "2099-01-01T00:00:00Z", "query": {"q": "4 חדרים"}},
                      {"id": "p3", "row": 30, "token": "TOK3", "last_sent_at": "2026-11-12T10:00:00Z", "expires_at": "2099-01-01T00:00:00Z"}]
        self.items = [{"page_id": "p1", "prop_key": "old1"}]
        self.updates = []
    def bpage_all(self): return list(self.pages)
    def bpage_items(self, ids): return [i for i in self.items if i["page_id"] in ids]
    def bpage_by_row(self, row): return next((p for p in self.pages if str(p["row"]) == str(row)), None)
    def bpage_update(self, pid, d): self.updates.append((pid, d))
    def bpage_add_items(self, pid, its):
        out = []
        for it in its:
            if any(i["page_id"] == pid and i["prop_key"] == it["prop_key"] for i in self.items): continue
            self.items.append({"page_id": pid, "prop_key": it["prop_key"]}); out.append(it["prop_key"])
        return out

BUYERS = [{"row": 10, "name": "דנה כהן", "agent": "נחמי זקס", "agent_phone": "0501111111", "phone": "0521234567", "search": "4 חדרים בביאליק"},
          {"row": 20, "name": "יוסי לוי", "agent": "נחמי זקס", "agent_phone": "0501111111", "phone": "0527654321", "search": ""},   # בלי דף
          {"row": 30, "name": "רון בר", "agent": "רויטל גל", "agent_phone": "0502222222", "phone": "0529999999", "search": ""}]

class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None

LOG = []
def client(sess):
    sb = SB()
    E._BP_SB = sb
    G = AutoG(log=None, _web_auth=lambda: sess, _fetch_manual_buyers=lambda: BUYERS,
              _canon_key=lambda n: " ".join(str(n or "").split()), _last9=lambda p: re.sub(r"\D", "", str(p or ""))[-9:],
              _phones_for_name=lambda n: {"נחמי זקס": {"0501111111"}, "אייל שמול": {"0505709865"}}.get(n, set()),
              _scope_keys_phones=lambda role, nm, ph, a, an: ({" ".join(nm.split())}, set(ph), None),
              _display_name_for=lambda n, p: "אייל שמול" if n == "מנהל" else n,
              _log_activity=lambda *a: LOG.append(a), _wa_phone=lambda p: "972" + re.sub(r"\D", "", p)[1:],
              _load_config=lambda: {}, _config_mutate=lambda fn: (True, None))
    app = Flask(__name__); E.register(app, G)
    E._BP_SB = sb
    return app.test_client(), sb

def patch_sources():
    # מקורות חיים: מפתח לכל סוג
    src = {"office": {"o1": {"כתובת": "הנוטר 5"}}, "shtaf": {"x1": {"כתובת": "ורבורג 3"}}, "newborn": {"n1": {"כתובת": "אהוד מנור 4"}}}
    return src

agent = {"name": "נחמי זקס", "role": "agent", "phone": "0501111111"}
c, sb = client(agent)
# מקורות: עוקפים את בניית המקורות דרך המטמון הפנימי של הראוט
import types
for fn in c.application.view_functions.values():
    cl = getattr(fn, "__closure__", None) or ()
    for cell in cl:
        try:
            v = cell.cell_contents
        except ValueError:
            continue
        if isinstance(v, dict) and "src" in v and "new" in v:
            v["src"] = patch_sources(); v["ts"] = 9e18
E.bpage_snapshot = lambda so, r: {"a": r.get("כתובת")}

print("1. רשימת הקונים שלי עם דף")
j = c.get("/v2/api/bpage/mine").get_json()
check(j.get("ok") and [b["name"] for b in j["buyers"]] == ["דנה כהן"], "סוכנת — רק הקונה שלה שיש לו דף (לא בלי דף, לא של אחרת)")
check(j["buyers"][0]["total"] == 1, "מונה נכסים בדף")

print("2. הוספה")
for so, k in (("office", "o1"), ("shtaf", "x1"), ("newborn", "n1")):
    r = c.post("/v2/api/bpage/add", json={"row": 10, "source": so, "key": k}).get_json()
    check(r.get("ok") and r.get("added") == 1 and r.get("name") == "דנה כהן", "נוסף מ-" + so)
check(not any("query" in d for _, d in sb.updates), "החיפוש השמור של הדף לא נדרס")
check(all("expires_at" in d for _, d in sb.updates), "תוקף הדף מתחדש")
r = c.post("/v2/api/bpage/add", json={"row": 10, "source": "office", "key": "o1"}).get_json()
check(r.get("ok") and r.get("added") == 0, "נכס שכבר בדף — לא מוסיף שוב")
check("1" in r.get("msg", "") or "נכס חדש" in r.get("msg", ""), "נוסח וואטסאפ מוכן")
check(c.post("/v2/api/bpage/add", json={"row": 20, "source": "office", "key": "o1"}).get_json().get("reason") == "no_page", "קונה בלי דף — לא נוצר דף")
check(c.post("/v2/api/bpage/add", json={"row": 30, "source": "office", "key": "o1"}).status_code == 403, "קונה של סוכנת אחרת — חסום")
check(c.post("/v2/api/bpage/add", json={"row": 10, "source": "office", "key": "zz"}).get_json().get("reason") == "not_found", "נכס לא קיים")

print("3. מנהל — רק הקונים שלו")
mgr = {"name": "מנהל", "role": "admin", "phone": "0505709865"}
c2, sb2 = client(mgr)
for fn in c2.application.view_functions.values():
    for cell in (getattr(fn, "__closure__", None) or ()):
        try: v = cell.cell_contents
        except ValueError: continue
        if isinstance(v, dict) and "src" in v and "new" in v: v["src"] = patch_sources(); v["ts"] = 9e18
check(c2.get("/v2/api/bpage/mine").get_json().get("buyers") == [], "מנהל בלי קונים משלו — רשימה ריקה")
check(c2.post("/v2/api/bpage/add", json={"row": 10, "source": "office", "key": "o1"}).status_code == 403, "מנהל לא מוסיף לקונה של סוכנת")

print("4. קליינט")
src = open(os.path.join(os.path.dirname(E.__file__), "effie_v2.py"), encoding="utf-8").read()
kit = re.search(r'V2_BPADD_KIT = r"""(.*?)"""', src, re.S).group(1)
js = re.search(r"<script>(.*?)</script>", kit, re.S).group(1)
harness = r"""
var DOM = {}; function mk(id){ return DOM[id] = DOM[id] || {id: id, innerHTML: '', textContent: '', style: {}, classList: {s: {}, add: function(c){ this.s[c] = 1; }, remove: function(c){ delete this.s[c]; }}}; }
function el(id){ return mk(id); } var document = {activeElement: null}; var TO = []; function toast(m){ TO.push(m); }
var REQ = []; var OPEN = [];
function GET(u){ REQ.push(['GET', u]); return {then: function(f){ f({ok: true, buyers: [{row: 10, name: 'דנה כהן', search: '4 חד', total: 2, expired: false}]}); return {catch: function(){}}; }}; }
function POST(u, d){ REQ.push(['POST', u, d]); return {then: function(f){ f({ok: true, added: 1, name: 'דנה כהן', wa: '972521234567', msg: 'היי דנה'}); return {catch: function(){}}; }}; }
var window = {open: function(u){ OPEN.push(u); }}; var localStorage = {removeItem: function(){}};
function setTimeout(){ return 1; } function clearTimeout(){}
function nbKitRows(){ return [{key: 'n1', address: 'אהוד מנור 4', city: 'קרית ביאליק'}]; }
""" + js + r"""
bpAddNb(0);
var listed = DOM.bpaSh.innerHTML.indexOf('דנה כהן') >= 0 && DOM.bpaOv.classList.s.on;
bpaPick(0);
var post = REQ.filter(function(r){ return r[0] === 'POST'; })[0];
var bar = DOM.bpaTxt.textContent;
DOM.bpaWa.onclick();
console.log(JSON.stringify({listed: listed, post: post, bar: bar, closed: !DOM.bpaOv.classList.s.on, open: OPEN}));
"""
out = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
R = json.loads(out.stdout or "{}") if out.stdout else {}
if not out.stdout: print(out.stderr[:800])
check(R.get("listed"), "החלון נפתח עם הקונה")
check(R.get("post") and R["post"][2] == {"row": 10, "source": "newborn", "key": "n1"}, "שולח את הנכס הנכון")
check(R.get("bar") == "נוסף לדף של דנה כהן" and R.get("closed"), "פס 'נוסף לדף של…' והחלון נסגר")
check(R.get("open") and "wa.me/972521234567" in R["open"][0], "'שלח לקונה בוואטסאפ' פותח וואטסאפ")

print("5. הכפתורים בכרטיסים ובדפים")
check("bpAddNb(" in src and "typeof bpAdd === 'function'" in src, "כרטיס נכס נולד — כפתור רק כשהערכה טעונה")
check(src.count("V2_NB_KIT + V2_BPADD_KIT") == 2, "הוזרק במסך הנכסים ובמסך נכס נולד (לא בחלון ההתאמות)")
check("acts + bpaBtn(p, i) + shareRow" in src, "כרטיס משרד/שלי/שת\"פ — שורת 'הוסף לדף קונה'")

print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
