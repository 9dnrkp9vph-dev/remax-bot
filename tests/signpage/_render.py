# עוזר משותף: מרנדר את /s/<token> האמיתי (app.py) עם מסמכים מזויפים — בלי רשת
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import json
import app as A
DOCS = {}
A._signdoc_get = lambda t: {"ok": True, "found": True, "doc": DOCS[t]} if t in DOCS else {"ok": True, "found": False}
A._cache_get = lambda *a, **k: None
A._cache_put = lambda *a, **k: None
A.fetch_agents_full = lambda: {A._norm_name("רועי לוי"): {"phone": "0521234567", "license": "3123456"}}
A._load_config = lambda: {}
client = A.app.test_client()
HDR = ("תאריך: 10/11/2026 · המתווך/הסוכן: רועי לוי\n"
       "לקוח: שחר קרובי · טל' 0587816168 · ת״ז 041707985\n"
       "נכס: הנביאים 54 קרית אתא · מחיר מבוקש: 2,100,000 ₪")
def page(tok):
    r = client.get("/s/" + tok)
    return r.status_code, r.get_data(as_text=True)
def script_of(html):
    i = html.find("<script>")
    return html[i:html.find("</script>", i)] if i >= 0 else ""
