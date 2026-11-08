# tests/home/test_home_tiles.py — [HOME-TILES 08/11] ארבעת הריבועים בבית
# אייל: גיוס (יעד השבוע) · קונים (יעד השבוע) · ירידות מחיר היום בנכס נולד · ירידות מחיר היום במשרד;
# עיגולים בסגנון היעדים בסטורי; בלי יעד → יעד 1; לחיצות: חתימות-בלעדיות / קונים פעילים / נכס נולד / נכסי המשרד.
import ast, os, re, subprocess, json, tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SRC = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
CONSTS = {}
for node in ast.parse(SRC).body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if getattr(t, "id", "") in ("V2_HOME_HTML", "V2_PROPS_HTML", "V2_SIGS_HTML", "V2_BUYERS_HTML"):
                CONSTS[t.id] = ast.literal_eval(node.value)
HOME = CONSTS["V2_HOME_HTML"]

def node_run(js):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
    r = subprocess.run(["node", f.name], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout

def scripts(html):
    return [s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if s.strip()]

# 1) תחביר — כל הסקריפטים בדפים שנגעו בהם
for name, html in CONSTS.items():
    for i, sc in enumerate(scripts(html)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(sc)
        r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        assert r.returncode == 0, (name, i, r.stderr[:400])

# 2) ארבעה ריבועים, הלחיצות, בלי 'שיחות השבוע'
assert "שיחות השבוע" not in HOME and "stCalls" not in HOME
for href in ("/v2/sigs?tab=excl", "/v2/buyers?tab=active", "/v2/newborn", "/v2/props?drops=today"):
    assert "location.href='" + href + "'" in HOME, href
assert "repeat(4,minmax(0,1fr))" in HOME and "aspect-ratio:1/1" in HOME

# 3) ההתנהגות — הפונקציות האמיתיות
fn = re.search(r"(function homeRingSvg\(.*?\n\}\nfunction homeGoalWeek\(.*?\n\}\nfunction homeTiles\(\)\{.*?\n\})\n", HOME, re.S)
assert fn, "tiles functions not found"
js = r"""
var store = {};
function el(id){ if (!store[id]) store[id] = {innerHTML:'', textContent:'', attrs:{}, setAttribute:function(k,v){this.attrs[k]=v;}}; return store[id]; }
var M = {}, GJ;
%s
function ring(id){ var h = store[id].innerHTML; var m = h.match(/stroke-dashoffset="([\d.]+)"/); return {txt: (h.match(/>([^<]*)<\/text>/)||[])[1], off: m ? +m[1] : null, full: h.indexOf('rgba(255,255,255,.2)') < 0}; }
var out = {};
GJ = undefined; homeTiles(); out.loading = {l: ring('stLstR'), t: store.stLstT.textContent, nb: ring('stNbdR')};
GJ = {view:'agent', me:{week:{counts:{listings:1, buyers:4}, targets:{listings:3, buyers:0}}}};
M.dropsNb = 14; M.dropsOffice = 3; homeTiles();
out.agent = {l: ring('stLstR'), lt: store.stLstT.textContent, b: ring('stBuyR'), bt: store.stBuyT.textContent,
             nb: ring('stNbdR'), of: ring('stOfdR'), aria: store.stLst.attrs['aria-label']};
GJ = {view:'office', total:{week:{counts:{listings:23, buyers:51}, targets:{listings:40, buyers:60}}}};
homeTiles(); out.office = {l: ring('stLstR'), lt: store.stLstT.textContent, bt: store.stBuyT.textContent};
console.log(JSON.stringify(out));
""" % fn.group(1)
o = json.loads(node_run(js))
assert o["loading"]["l"]["txt"] == "—" and o["loading"]["nb"]["txt"] == "—", o
assert o["agent"]["l"]["txt"] == "1" and o["agent"]["lt"] == "/ 3", o
assert abs(o["agent"]["l"]["off"] - 182.2 * (1 - 1/3)) < 0.2, o
assert o["agent"]["bt"] == "/ 1" and o["agent"]["b"]["off"] == 0.0, o     # בלי יעד → יעד 1 (4/1 = עיגול מלא)
assert o["agent"]["nb"]["txt"] == "14" and o["agent"]["nb"]["full"] and o["agent"]["of"]["txt"] == "3", o
assert "1 מתוך 3" in o["agent"]["aria"], o
assert o["office"]["l"]["txt"] == "23" and o["office"]["lt"] == "/ 40" and o["office"]["bt"] == "/ 60", o

# 4) מסך הנכסים: ירידות מחיר היום — רק מהיום, בלי מודעות שירדו מפרסום, האחרונה למעלה
pr = CONSTS["V2_PROPS_HTML"]
f2 = re.search(r"(function dropsTodayList\(list\)\{.*?\n\})\n", pr, re.S)
assert f2
js = """%s
var mid = new Date(); mid.setHours(0,0,0,0); mid = mid.getTime()/1000;
var r = dropsTodayList([{a:1, priceDropAt: mid+100}, {a:2, priceDropAt: mid-5}, {a:3, priceDropAt: mid+500},
                        {a:4, priceDropAt: mid+50, delisted:'07/11'}, {a:5}]);
console.log(JSON.stringify(r.map(function(x){return x.a;})));""" % f2.group(1)
assert json.loads(node_run(js)) == [3, 1]
assert "if (DROPS_TODAY){ MODE = 'office'" in pr
assert "tab=excl" in CONSTS["V2_SIGS_HTML"] and "tab=active" in CONSTS["V2_BUYERS_HTML"]
print("ok")
