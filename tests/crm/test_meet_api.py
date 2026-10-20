# tests/crm/test_meet_api.py — /v2/crm/meetings: הראוט האמיתי מעל nbStatus מזויף
import os, sys, warnings, datetime; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"   # 21/10: הבדיקות כאן = בעל המשרד בטוקן האפליקציה (מסלול החזרה); הכניסה עם Google נבדקת בנפרד
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
from zoneinfo import ZoneInfo
A._web_auth = lambda: {"phone": "505709865", "name": "אייל", "role": "admin"}
A._is_dev = lambda p: True
class SB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
A._sbdb = SB()
today = datetime.datetime.now(ZoneInfo("Asia/Jerusalem")).date().isoformat()
A._nb_statuses = lambda: {"רפי::a1": {"status": "meeting", "date": today + "T23:30", "agent": "רפי", "by": "אוצר", "pkey": "a1", "addr": "הנשיא 4"},
                          "רפי::manual:1": {"status": "followup", "date": "2026-01-05", "agent": "רפי", "by": "רפי", "pkey": "manual:1"}}
c = A.app.test_client()
m = c.get("/v2/api/crm/meetings/meta").get_json()
ck(m["ok"] and m["title"] == "פגישות" and m["counts"]["all"] == 2 and m["counts"]["today"] == 1 and m["counts"]["manual"] == 1, m.get("counts"))
ck(any(x[0] == "meetings" for x in m["modules"]) and m["agents"] == ["רפי"], (m["modules"], m["agents"]))
l = c.get("/v2/api/crm/meetings/list?view=coordinated").get_json()
ck(l["total"] == 1 and l["rows"][0]["by"] == "אוצר" and l["rows"][0]["source"] == "נכס נולד", l)
ck(c.post("/v2/api/crm/meetings/record", json={"fields": {}}).status_code == 400, "read only")
ck("אוצר" in c.get("/v2/api/crm/meetings/export").get_data(as_text=True), "export")
ck(c.get("/v2/crm/meetings").status_code == 200, "page")
print("meet_api OK", n)
