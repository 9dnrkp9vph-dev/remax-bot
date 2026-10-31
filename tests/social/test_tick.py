# tests/social/test_tick.py — soc_auto_tick: תנאי הפעלה, זריעה, הצפה, מרווח בין פוסטים
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from _fakes import ROW, make_G
from zoneinfo import ZoneInfo
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Jerusalem")).timestamp()
SP.soc_hidden = lambda G: set()
RUNS = []
SP.soc_run_one = lambda G, k, trig, ph, **kw: (RUNS.append((k, trig)), {"ok": True})[1]
ON = {"SOCIAL_AUTO": "1", "SOCIAL_MODE": "publish", "META_TOKEN": "T"}
def rows(*keys): return [dict(ROW, **{"מספר מודעה": k, "כתובת": "רחוב " + k}) for k in keys]

G, st, sb = make_G(rows("a", "b"))
for env in ({}, dict(ON, SOCIAL_AUTO="0"), dict(ON, SOCIAL_MODE="preview"), dict(ON, META_TOKEN="")):
    ck(SP.soc_auto_tick(G, NOW, env) == {"ran": False}, env)
r = SP.soc_auto_tick(G, NOW, ON)
ck(r.get("seeded") == 2 and set(st["cfg"]["v2_social"]["known"]) == {"a", "b"} and not RUNS, r)

G["fetch_sheet_rows"] = lambda: rows("a", "b", "c", "d")
SLEEPS = []
r = SP.soc_auto_tick(G, NOW, ON, sleep=SLEEPS.append)
ck([k for k, _ in RUNS] == ["c", "d"] or [k for k, _ in RUNS] == ["d", "c"], RUNS)
ck(all(t == "auto" for _, t in RUNS) and SLEEPS == [SP.GAP_MIN * 60], SLEEPS)

RUNS.clear()
G["fetch_sheet_rows"] = lambda: rows("a", "b", "c", "d", *["f%d" % i for i in range(41)])
r = SP.soc_auto_tick(G, NOW, ON, sleep=lambda s: None)
ck(r["flood"] and not RUNS and len(st["push"]) == 1, (r, st["push"]))
SP.soc_auto_tick(G, NOW + 60, ON, sleep=lambda s: None)
ck(not RUNS and len(st["push"]) == 1, "flood keys now known, one push a day")

G["_shabbat_quiet_now"] = lambda: True
G["fetch_sheet_rows"] = lambda: rows("a", "b", "c", "d", "z")
SP.soc_auto_tick(G, NOW, ON, sleep=lambda s: None)
ck(not RUNS and "z" in st["cfg"]["v2_social"]["waiting"], st["cfg"]["v2_social"]["waiting"])
st["cfg"]["v2_social"]["paused_until"] = NOW + 100
G["_shabbat_quiet_now"] = lambda: False
ck(SP.soc_auto_tick(G, NOW, ON).get("paused"), "paused")
print("social_tick OK", n)
