# tests/crm/test_crm_page.py — עמוד /v2/crm/<module>: מבנה פיירברי, טוקן, RTL, JS תקין, בלי אימוג'ים
import os, sys, warnings, subprocess, tempfile, re; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
c = A.app.test_client()
r = c.get("/v2/crm/calls")
assert r.status_code == 200 and "text/html" in r.content_type, r.status_code
h = r.get_data(as_text=True)
for need in ("fbTok", "X-Auth-Token", "/v2/api/crm/", 'dir="rtl"', "Heebo", "/v2/crm/dashboard", "/v2/buyers?add=1", "wa.me"):
    assert need in h, need
assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", h), "no emoji icons in UI"
js = re.findall(r"<script>(.*?)</script>", h, re.S)
f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write("\n".join(js)); f.close()
subprocess.run(["node", "--check", f.name], check=True)
assert c.get("/v2/crm/dashboard").get_data(as_text=True).count("לוח בקרה") >= 1, "dashboard route still wins"
assert "j.source === 'supabase' && !nd" in h or "showCmp" in h, "sheet comparison hidden after the switch"
print("crm_page OK")
