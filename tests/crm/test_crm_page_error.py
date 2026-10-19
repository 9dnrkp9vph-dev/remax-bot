# tests/crm/test_crm_page_error.py — כשל בטעינת המודול (502/HTML) לא משאיר 'טוען…' לנצח: מוצג הקוד ויש ניסיון חוזר
import os, sys, warnings, subprocess, tempfile, re, json; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
h = A.app.test_client().get("/v2/crm/team").get_data(as_text=True)
js = "\n".join(re.findall(r"<script>(.*?)</script>", h, re.S))
s = js[js.index("function loadMeta"):]
s = s[:s.index("\nfunction ", 10)]
harness = """
var T={textContent:'טוען…'}, calls=0, timers=[];
var document={getElementById:function(id){ return id==='title'?T:{style:{},classList:{remove:function(){}}}; }};
function setTimeout(f){ timers.push(f); }
function api(){ calls++; return Promise.resolve({status:502, ok:false, json:function(){ return Promise.reject(new SyntaxError('html')); }}); }
var MOD='team', META=null, ST={}, META_TRIES=0; function refreshAll(){}
%s
loadMeta().catch(function(){}).then(function(){ return new Promise(function(r){ setImmediate(r); }); }).then(function(){
  console.log(JSON.stringify({title:T.textContent, calls:calls, retry:timers.length}));
});
""" % s
f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write(harness); f.close()
out = json.loads(subprocess.run(["node", f.name], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
assert out["title"] != "טוען…" and "502" in out["title"], out
assert out["retry"] >= 1, ("schedules a retry", out)
print("crm_page_error OK", out)
