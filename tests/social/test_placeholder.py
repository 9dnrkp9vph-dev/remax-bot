# tests/social/test_placeholder.py — לא מפרסמים תמונת 'נכס חדש נולד · תמונות בקרוב' (אייל 01/11: 'כן, תבנה')
import io, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..")); sys.path.insert(0, HERE)
from PIL import Image
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from _fakes import ROW, make_G, FakeGraph

PH = open(os.path.join(HERE, "fixtures", "placeholder_gift.jpg"), "rb").read()   # התמונה של רוקח 23, מוקטנת
def png(color):
    b = io.BytesIO(); im = Image.new("RGB", (800, 600), color)
    for x in range(0, 800, 40):
        for y in range(0, 600, 40):
            im.paste((255 - color[0], 30, 90), (x, y, x + 20, y + 20))
    im.save(b, "PNG"); return b.getvalue()
REAL = png((10, 120, 200))

# זיהוי
ck(SP.soc_is_placeholder(PH), "gift placeholder detected (resized copy)")
ck(not SP.soc_is_placeholder(REAL), "real photo is not a placeholder")
ck(not SP.soc_is_placeholder(b"not an image"), "garbage is not a placeholder")
ck(len(SP.PLACEHOLDER_HASHES) == 4, SP.PLACEHOLDER_HASHES)

class Http:
    def __init__(s, plan): s.plan = plan
    def get(s, url, timeout=None, headers=None, params=None):
        class R: pass
        r = R(); r.status_code, r.content = 200, s.plan(url); return r

SP.Graph = FakeGraph
SP.soc_hidden = lambda G: set()
PUB = {"SOCIAL_MODE": "publish", "META_TOKEN": "SECRET123", "APP_BASE_URL": "https://app.test"}

# כל התמונות פלייסהולדר → לא מפרסמים, לא נרשם pending, אין קריאה ל-Meta
G, st, sb = make_G()
FakeGraph.instances.clear()
r = SP.soc_run_one(G, "tok1", "manual", "505709865", http=Http(lambda u: PH), env=PUB)
ck(not r["ok"] and r.get("placeholder") and "תמונות בקרוב" in r["reason"], r)
ck(not sb.rows, ("nothing recorded", sb.rows))
ck(not any(g.calls for g in FakeGraph.instances), "no graph calls")

# גם בתצוגה מקדימה רואים את זה
G, st, sb = make_G()
r = SP.soc_run_one(G, "tok1", "manual", "505709865", http=Http(lambda u: PH), env={"META_TOKEN": "x"})
ck(not r["ok"] and r.get("placeholder"), ("preview flags placeholder", r))

# תמונה אחת פלייסהולדר ואחת אמיתית → מפרסמים רק את האמיתית
G, st, sb = make_G()
FakeGraph.instances.clear()
r = SP.soc_run_one(G, "tok1", "manual", "505709865", http=Http(lambda u: PH if "a.jpg" in u else REAL), env=PUB)
ck(r["ok"] and r["fb"] == "ok", r)
ck(sb.rows[-1]["images"] == ["https://img/b.jpg"], sb.rows[-1]["images"])
fbu = [c for c in FakeGraph.instances[-1].calls if c[0] == "fb"][0][3]
ck(len(fbu) == 1, fbu)

# הסבב האוטומטי: נכס שנדחה בגלל פלייסהולדר חוזר להמתנה עם הזמן המקורי שלו
import datetime as dt
from zoneinfo import ZoneInfo
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Jerusalem")).timestamp()
ON = {"SOCIAL_AUTO": "1", "SOCIAL_MODE": "publish", "META_TOKEN": "T"}
rows = lambda *ks: [dict(ROW, **{"מספר מודעה": k, "כתובת": "רחוב " + k}) for k in ks]
G, st, sb = make_G(rows("a"))
SP.soc_auto_tick(G, NOW, ON)                                   # זריעה
G["fetch_sheet_rows"] = lambda: rows("a", "c")
real_run = SP.soc_run_one
SP.soc_run_one = lambda G, k, trig, ph, **kw: {"ok": False, "placeholder": True, "reason": "x"}
SP.soc_auto_tick(G, NOW + 60, ON, sleep=lambda s: None)
SP.soc_run_one = real_run
w = st["cfg"]["v2_social"]["waiting"]
ck("c" in w and abs(float(w["c"]) - (NOW + 60)) < 1, ("requeued with original time", w))
print("ok", n)
