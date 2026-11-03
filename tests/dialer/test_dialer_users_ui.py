"""[DIALER-USERS 03/11] כרטיס 'חייגן חכם — מי רואה' במסך הניהול — הקוד האמיתי של הדף ב-node.
python3 tests/dialer/test_dialer_users_ui.py"""
import ast, os, re, json, subprocess

SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "effie_v2.py"), encoding="utf-8").read()
HTML = None
for node in ast.parse(SRC).body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "V2_ADMIN_HTML" for t in node.targets):
        HTML = ast.literal_eval(node.value)
assert HTML, "V2_ADMIN_HTML not found"
assert 'id="dlrCard"' in HTML and 'id="dlrList"' in HTML, "הכרטיס בדף"
assert "dlrLoad();" in HTML.split("function boot()")[1].split("function ")[0], "נטען בעליית הדף"

m = re.search(r"(var DLR = .*?\nfunction dlrSave\(\)\{.*?\n\})\n", HTML, re.S)
assert m, "dlr code not found"
code = m.group(1)

js = r"""
var BOX = {innerHTML: ''}, POSTS = [], TOASTS = [];
function el(id){ return id === 'dlrList' ? BOX : null; }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
var ROLE_LABEL = {agent:'סוכן', coordinator:'מתאמת', manager:'מנהל', developer:'בעל המשרד'};
function toast(m){ TOASTS.push(m); }
function unesc(s){ return s.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&'); }
function inputs(){
  var out = [], re = /<input type="checkbox" data-dlr="([^"]*)"([^>]*)>/g, mm;
  while ((mm = re.exec(BOX.innerHTML))) out.push({nm: unesc(mm[1]), checked: / checked/.test(mm[2]), disabled: / disabled/.test(mm[2]),
    getAttribute: function(){ return this.nm; }});
  return out;
}
var document = {
  querySelectorAll: function(){ return inputs(); },
  querySelector: function(sel){
    var mm = /data-dlr="(.*)"\]$/.exec(sel); if (!mm) return null;
    var want = mm[1].replace(/\\"/g, '"');
    return inputs().filter(function(i){ return i.nm === want; })[0] || null;
  }
};
var REPLY = null;
function POST(u, d){ POSTS.push({u: u, d: d}); return {then: function(f){ f(REPLY || {ok: true, names: d.names}); return {catch: function(){}}; }}; }
function GET(u){ return {then: function(f){ f({ok: true, names: ['דנה לוי'], coords: ['אוצר בן חמו']}); return {catch: function(){}}; }}; }
var PEOPLE = [
  {name: 'אייל שמול', role: 'developer'}, {name: 'אוצר בן חמו', role: 'manager'}, {name: 'נוי רבן', role: 'manager'},
  {name: 'דנה לוי', role: 'agent'}, {name: 'לירון חג\'ג\'', role: 'agent'}, {name: 'מושהה', role: 'agent', suspended: true},
  {name: 'הודיה צרויה', role: 'coordinator'}
];
for (var i = 1; i <= 10; i++) PEOPLE.push({name: 'סוכן ' + i, role: 'agent'});
""" + code + r"""
var R = {};
dlrLoad();
var a = inputs();
R.firstShown = a.map(function(x){ return x.nm; });
R.ownerHidden = a.every(function(x){ return x.nm !== 'אייל שמול' && x.nm !== 'מושהה'; });
R.otzar = a.filter(function(x){ return x.nm === 'אוצר בן חמו'; })[0];
R.hodaya = a.filter(function(x){ return x.nm === 'הודיה צרויה'; })[0];
R.dana = a.filter(function(x){ return x.nm === 'דנה לוי'; })[0];
R.hasShowAll = /הצג את כולם \(15\)/.test(BOX.innerHTML);
DLR_ALL = true; dlrRender();
R.allCount = inputs().length;
// מסמנים את נוי ושומרים
BOX.innerHTML = BOX.innerHTML.replace('data-dlr="נוי רבן"', 'data-dlr="נוי רבן" checked');
dlrSave();
R.post = POSTS[POSTS.length - 1];
R.toast = TOASTS[TOASTS.length - 1];
// כשל שמירה — הודעה ורינדור מחדש לפי מה שנשמר
REPLY = {ok: false, reason: 'save_failed'};
dlrSave();
R.failToast = TOASTS[TOASTS.length - 1];
console.log(JSON.stringify(R));
"""
out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
assert out.returncode == 0, out.stderr[:800]
R = json.loads(out.stdout)
fails = []


def check(c, msg):
    print(("  ✓ " if c else "  ✗ ") + msg)
    if not c:
        fails.append(msg)


check(R["ownerHidden"], "בעל המשרד ומושהה לא ברשימה")
check(R["otzar"] and R["otzar"]["checked"] and R["otzar"]["disabled"], "אוצר (מתאמת מזוהה) — מסומנת ונעולה")
check(R["hodaya"] and R["hodaya"]["checked"] and R["hodaya"]["disabled"], "תפקיד מתאמת — מסומנת ונעולה")
check(R["dana"] and R["dana"]["checked"] and not R["dana"]["disabled"], "דנה (נבחרה) — מסומנת וניתנת לשינוי")
check(set(R["firstShown"][:3]) == {"אוצר בן חמו", "דנה לוי", "הודיה צרויה"}, "המסומנים ראשונים")
check(len(R["firstShown"]) == 8 and R["hasShowAll"], "8 ראשונים + 'הצג את כולם (15)'")
check(R["allCount"] == 15, "הצג את כולם — 15 (בלי בעל המשרד והמושהה)")
check(R["post"]["u"] == "/v2/api/dialer/users" and sorted(R["post"]["d"]["names"]) == ["דנה לוי", "נוי רבן"],
      "שמירה: רק הנבחרים (בלי המתאמות הנעולות)")
check(R["toast"] == "נשמר · 2 עם חייגן", "הודעת שמירה")
check(R["failToast"] == "השמירה נכשלה", "כשל — הודעה")

print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
raise SystemExit(1 if fails else 0)
