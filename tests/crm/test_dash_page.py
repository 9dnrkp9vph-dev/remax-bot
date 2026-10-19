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
