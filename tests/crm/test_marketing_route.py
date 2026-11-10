# tests/crm/test_marketing_route.py — [10/11 אייל] מסך שיווק ב-CRM: הרשאה (בעל המשרד בלבד), חיווט המקורות, הדף
import os, sys, json, re, subprocess, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"   # בעל המשרד בטוקן האפליקציה (כמו test_dash_route)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import time
import app as A
import social_sold
from datetime import datetime, timezone
now_iso = datetime.now(timezone.utc).isoformat()

A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
A.fetch_sheet_rows = lambda *a, **k: [{"מספר מודעה": "L:k1", "סוכן 1": "דנה כהן"}]
A.fetch_sheet_rows_deal = lambda *a, **k: []
class FakeSB:
    def enabled(s): return True
    def social_recent(s, days):
        ck(days >= 31, days); return [{"property_key": "k1", "created_at": now_iso, "fb_status": "ok", "ig_status": "ok"}]
    def video_recent(s, days): return [{"property_key": "k1", "created_at": now_iso, "decided_at": now_iso, "ig_reel_status": "ok"}]
    def kit_list(s, agent_phone=None, days=90): raise RuntimeError("supabase down")
A._sbdb = FakeSB()
class FakeSold:
    def all(s): return [{"status": "published", "ts": time.time() - 5, "agents": ["רפי"], "ig_story_status": "ok"}]
social_sold._DB = FakeSold()

c = A.app.test_client()
r = c.get("/v2/api/crm/marketing?period=day")
j = r.get_json()
ck(r.status_code == 200 and j["ok"] and j["period"] == "day", (r.status_code, j))
T = j["totals"]
ck(T["posts"] == {"n": 1, "fb": 1, "ig": 1} and T["reels"]["n"] == 1 and T["sold"]["n"] == 1 and T["total"] == 3, T)
ck({a["name"]: a["total"] for a in j["agents"]} == {"דנה כהן": 2, "רפי": 1}, j["agents"])
ck(j["missing"] == ["תיקי פרזנטציה"] and T["kits"]["n"] == 0, j["missing"])   # מקור שנפל — מסומן, לא מפיל
ck(c.get("/v2/api/crm/marketing?period=junk").get_json()["period"] == "week", "bad period → week")
ck(c.get("/v2/crm/marketing").status_code == 200, "page")
A._is_dev = lambda p: False
ck(c.get("/v2/api/crm/marketing").status_code in (401, 403), "owner only")

# הדף: קישורים + רינדור הטבלה (node)
import effie_v2 as E
ck('href="/v2/crm/marketing">שיווק</a>' in E._CRM_DASH_HTML, "link from dashboard")
ck("""if (me.access) h += '<a class="mod" href="/v2/crm/marketing">שיווק</a>';""" in E._CRM_SCREEN_HTML, "link in CRM nav (owner)")
js = re.search(r"<script>(.*)</script>", E._CRM_MKT_HTML, re.S).group(1)
fn = re.search(r"function esc\(.*?\n(?=function segs)", js, re.S).group(0)
prog = fn + "\nvar j=" + json.dumps(dict(j, missing=["SOLD"]), ensure_ascii=False) + ";var h=mkHtml(j);" + \
    "console.log(JSON.stringify({h:h,empty:mkHtml({totals:{},agents:[]})}));"
out = json.loads(subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True).stdout)
h = out["h"]
ck("סה״כ פרסומים" in h and "<td>דנה כהן</td>" in h and "פייסבוק 1 · אינסטגרם 1" in h, h)
ck("חלק מהנתונים לא נטענו: SOLD" in h, "missing warning")
ck("אין פרסומים בתקופה הזו" in out["empty"], out["empty"])
ck(h.index("דנה כהן") < h.index("רפי"), "order kept")
print("marketing_route OK", n)
