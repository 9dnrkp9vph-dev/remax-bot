# tests/crm/test_crm_team_admin.py — [23/11] ניהול הצוות ב-CRM: בעל המשרד, או צוות + עריכה + היקף 'הכל' (אוריין)
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ.pop("CRM_ALLOW_APP_TOKEN", None)
os.environ["CRM_OWNER_EMAILS"] = "owner@example.com"
os.environ["CRM_AGENT_KEY"] = "test-agent-key-123"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
import effie_v2 as E
ta = E.crm_team_admin
ck(ta({"owner": True}), "owner")
ck(ta({"modules": ["team"], "edit": True, "scope": "all"}), "team+edit+all")
ck(not ta({"modules": ["team"], "edit": True, "scope": "team"}), "team scope only")
ck(not ta({"modules": ["team"], "edit": False, "scope": "all"}), "no edit")
ck(not ta({"modules": ["calls"], "edit": True, "scope": "all"}), "no team module")
ck(not ta({"owner": True, "agent_key": True}), "agent key never")
ck(not ta(None), "none")
MODS = ["team", "calls"]
CFG = {"v2_crm_access": {
    "orian@example.com": {"name": "אוריין", "phone": "0541111111", "modules": MODS, "scope": "all", "export": True, "edit": True},
    "udi@example.com": {"name": "אודי", "phone": "0542222222", "modules": MODS, "scope": "team", "export": True, "edit": True},
    "ro@example.com": {"name": "רו", "phone": "0543333333", "modules": MODS, "scope": "all", "export": False, "edit": False}}}
A._load_config = lambda: CFG
A._session_from_phone = lambda p: {"role": "admin", "name": "מנהל", "agents": [], "agent_names": []}
A._is_dev = lambda p: False
A._is_suspended = lambda p: False
A._gauth_all = lambda: {}
A._log_activity = lambda *a: None
A._contacts_source = lambda: "supabase"
A._contacts_rows_sheet = lambda: []
class SB:
    def enabled(s): return True
    def team_fetch(s): return [{"id": 1, "name": "x"}]
    def crm_overrides_fetch(s, m): return {}
    def team_upsert(s, rows, who): ADDED.extend(rows); return len(rows)
ADDED = []
A._sbdb = SB()
c = A.app.test_client()
H = lambda ph, em: {"X-Auth-Token": A._mint_crm_token(ph, em)}
ck(c.get("/v2/api/crm/team/status", headers=H("0541111111", "orian@example.com")).status_code == 200, "orian sees team tools")
ck(c.get("/v2/api/crm/team/status", headers=H("0542222222", "udi@example.com")).status_code == 403, "team scope blocked")
ck(c.get("/v2/api/crm/team/status", headers=H("0543333333", "ro@example.com")).status_code == 403, "read-only blocked")
r = c.post("/v2/api/crm/team/record", headers=H("0542222222", "udi@example.com"), json={"fields": {"name": "חדש", "phone": "0549999999"}})
ck(r.status_code == 403, ("team-scope cannot add", r.status_code))
r = c.post("/v2/api/crm/team/record", headers=H("0541111111", "orian@example.com"), json={"fields": {"name": "חדש", "phone": "0549999999"}})
ck(r.status_code == 200 and r.get_json().get("ok") and ADDED and ADDED[0]["name"] == "חדש", ("orian adds an agent", r.status_code, r.get_json()))
ck(c.post("/v2/api/crm/team/import", headers=H("0541111111", "orian@example.com")).status_code == 403, "import stays owner only")
# תמונה לסוכן — נשמרת בטבלת avatars (משם האתר מושך אותה)
import io, base64
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (600, 400), (30, 58, 95)).save(buf, "JPEG")
img = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
import supabase_db as _S
AV = {}
_S.enabled = lambda: True
_S.avatar_save = lambda p, b64: AV.__setitem__(p, b64)
A.web_phone_name_map = lambda: {}
A.web_contacts_phone_name = lambda: {}
r = c.post("/v2/api/crm/team/avatar", headers=H("0541111111", "orian@example.com"), json={"phone": "0549999999", "name": "חדש", "img": img})
ck(r.status_code == 200 and r.get_json()["ok"] and "549999999" in AV, ("orian uploads an agent photo", r.status_code, r.get_json(), list(AV)))
r = c.post("/v2/api/crm/team/avatar", headers=H("0542222222", "udi@example.com"), json={"phone": "0549999999", "img": img})
ck(r.status_code == 403, "team-scope cannot change photos")
import shutil; shutil.rmtree(A._AV_DIR if hasattr(A, "_AV_DIR") else "v2_avatars", ignore_errors=True)
print("crm_team_admin OK", n)
