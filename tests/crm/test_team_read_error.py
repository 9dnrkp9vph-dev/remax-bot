# tests/crm/test_team_read_error.py — כשל בקריאת team_contacts: מסך הצוות מקבל הודעה עם הסיבה (לא 500), והבאנר מציג אותה
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
class Broken:
    def enabled(s): return True
    def team_fetch(s, active_only=False): raise RuntimeError("404 Client Error: relation team_contacts not found")
    def crm_overrides_fetch(s, m): return {}
A._sbdb = Broken()
A._contacts_rows_sheet = lambda: [["דנה", "050"]]
c = A.app.test_client()
for u in ("/v2/api/crm/team/meta", "/v2/api/crm/team/list"):
    r = c.get(u); j = r.get_json(silent=True)
    assert r.status_code == 200 and j and j.get("ok") is False and j.get("reason") == "table_error" and "team_contacts" in j.get("detail", ""), (u, r.status_code, r.get_data(as_text=True)[:200])
st = c.get("/v2/api/crm/team/status").get_json()
assert "team_contacts" in st.get("table_error", ""), st
h = c.get("/v2/crm/team").get_data(as_text=True)
assert "table_error" in h, "banner shows the table error"
print("team_read_error OK")
