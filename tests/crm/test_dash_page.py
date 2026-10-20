# tests/crm/test_dash_page.py — עמוד /v2/crm/dashboard: טוקן הכניסה של אפי, RTL, Chart.js בגרסה קבועה, JS תקין
import os, sys, warnings, subprocess, tempfile, re; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
r = A.app.test_client().get("/v2/crm/dashboard")
assert r.status_code == 200 and "text/html" in r.content_type, r.status_code
h = r.get_data(as_text=True)
for need in ("fbTok", "X-Auth-Token", "/v2/api/crm/dashboard", 'dir="rtl"', "Heebo",
             "cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js", "/v2/crm/parallel"):
    assert need in h, need
js = re.findall(r"<script>(.*?)</script>", h, re.S)
assert js, "inline script"
f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write("\n".join(js)); f.close()
subprocess.run(["node", "--check", f.name], check=True)
print("dash_page OK")
# קישור מהניהול (בעל המשרד) ללוח הבקרה
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "effie_v2.py"), encoding="utf-8").read()
_adm = _src[_src.index("location.href='/v2/dev'") - 3000:_src.index("location.href='/v2/dev'")]
assert "location.href='/v2/crm/dashboard'" in _adm, "admin link to dashboard"
print("dash_admin_link OK")
# 20/10: 'מחכה לטיפול' + טבלת הסוכנים — הפונקציות האמיתיות מהדף, על נתונים לדוגמה
import re as _re2, subprocess as _sp2, json as _js2
_m = _re2.search(r"<script>(\s*var P='month'.*?)</script>", h, _re2.S)
assert _m, "dashboard script"
_D = {"todo": {"missed": [{"phone": "972542222222", "agent": "דנה", "ts": 1800000000, "tries": 2}], "missed_n": 1,
               "pending_sigs": [{"client": "א<b>", "agent": "רפי", "type": "קונים", "ts": 1800000000, "link": "/s/x"}], "pending_n": 1,
               "likes": [], "nb_untouched": {"n": 1, "list": [{"address": "הנשיא 4", "price": "2000000", "link": "https://y/1"}]}},
      "agents": {"month": [{"name": "רפי", "calls": 5, "answered": 3, "sigs": 2, "buyers": 1, "bpage": 4, "nb": 0, "min": 90}]},
      "listings": {"rows": [{"name": "רפי", "excl": 3, "reg": 1, "total": 5, "rent": 1}, {"name": "אוצר", "excl": 0, "reg": 0, "total": 0, "rent": 0}],
                   "total": {"excl": 3, "reg": 1, "total": 5, "rent": 1}}}
_js = ("var document={getElementById:function(){return {}}},localStorage={getItem:function(){return ''}},fetch=function(){return {then:function(){return {then:function(){return {catch:function(){}}},catch:function(){}}}}},setInterval=function(){};"
       + _m.group(1).split("function render(){")[0] + ";D=" + _js2.dumps(_D, ensure_ascii=False) + ";console.log(todoCard()+'\\n@@\\n'+agentsCard()+'\\n@@\\n'+listingsCard());")
_out = _sp2.run(["node", "-e", _js], capture_output=True, text=True)
assert _out.returncode == 0, _out.stderr[-600:]
_t, _a, _l = _out.stdout.split("@@")
assert "כל המשרד" in _l and "<td>רפי</td><td>3</td><td>1</td><td><b>5</b></td>" in _l and 'class="z"><td>אוצר' in _l, _l
assert "054-2222222" in _t and "2 ניסיונות" in _t and "א&lt;b&gt;" in _t and 'href="/s/x"' in _t and "אין סימונים חדשים" in _t and "₪2,000,000" in _t, _t
assert "<td>רפי</td>" in _a and "3<span" in _a and "90 דק׳" in _a and "החודש" in _a, _a
print("dash_page todo/agents OK")
