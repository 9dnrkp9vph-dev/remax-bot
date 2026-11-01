# tests/social/test_active.py — פרסום אוטומטי רק לסוכן שהיה באפי 10+ דק' ב-30 הימים האחרונים;
# לשאר — רק ידני דרך אייל (אייל 01/11)
import os, sys, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..")); sys.path.insert(0, HERE)
from zoneinfo import ZoneInfo
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from _fakes import ROW, make_G
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Jerusalem")).timestamp()
SP.soc_hidden = lambda G: set()
ON = {"SOCIAL_AUTO": "1", "SOCIAL_MODE": "publish", "META_TOKEN": "T"}
def rows(*pairs): return [dict(ROW, **{"מספר מודעה": k, "כתובת": "רחוב " + k, "סוכן 1": a}) for k, a in pairs]

def setup(usage):
    G, st, sb = make_G(rows(("a", "קובי חמו")))
    G["_canon_key"] = lambda s: " ".join(str(s).split())
    G["_canon_agent_name"] = lambda s: s
    G["_usage_rows"] = usage
    SP._ACTIVE_BOX.clear()
    SP.soc_auto_tick(G, NOW, ON)                      # זריעה
    return G, st
RUNS = []
real = SP.soc_run_one
SP.soc_run_one = lambda G, k, trig, ph, **kw: (RUNS.append(k), {"ok": True})[1]

# usage: קובי 25 דק', רויטל 4 דק'
SEEN = []
def usage(start):
    SEEN.append(start); return [{"name": "קובי  חמו", "min": 25}, {"name": "רויטל גל", "min": 4}]
G, st = setup(usage)
G["fetch_sheet_rows"] = lambda: rows(("a", "קובי חמו"), ("b", "קובי חמו"), ("c", "רויטל גל"), ("d", ""))
SP.soc_auto_tick(G, NOW, ON, sleep=lambda s: None)
ck(RUNS == ["b"], ("only the active agent's new listing", RUNS))
w = st["cfg"]["v2_social"]["waiting"]
ck("c" in w and "d" in w, ("inactive / no-agent stay waiting (manual still possible)", w))
ck(SEEN and abs((NOW - SEEN[-1].timestamp()) / 86400 - 30) < 1.01, ("30-day window", SEEN[-1]))

# סוכנת שנכנסה בינתיים (עדיין בתוך חלון ההמתנה) — עולה בסבב הבא
RUNS.clear(); SP._ACTIVE_BOX.clear()
G["_usage_rows"] = lambda start: [{"name": "רויטל גל", "min": 12}]
SP.soc_auto_tick(G, NOW + 25 * 60, ON, sleep=lambda s: None)
ck("c" in RUNS, ("becomes active -> published", RUNS))

# אין נתוני שימוש (Supabase כבוי) — לא מפרסמים אוטומטית בכלל
RUNS.clear()
G, st = setup(lambda start: [])
G["fetch_sheet_rows"] = lambda: rows(("a", "קובי חמו"), ("e", "קובי חמו"))
SP.soc_auto_tick(G, NOW, ON, sleep=lambda s: None)
ck(RUNS == [] and "e" in st["cfg"]["v2_social"]["waiting"], ("unknown usage -> no auto", RUNS))
RUNS.clear()
G, st = setup(lambda start: (_ for _ in ()).throw(RuntimeError("down")))
G["fetch_sheet_rows"] = lambda: rows(("a", "קובי חמו"), ("e", "קובי חמו"))
SP.soc_auto_tick(G, NOW, ON, sleep=lambda s: None)
ck(RUNS == [], ("usage error -> no auto", RUNS))

# הידני לא מושפע: soc_can_publish לא בודק פעילות
ck(SP.soc_can_publish(rows(("z", "רויטל גל"))[0], "fb", [], NOW, set())[0], "manual unaffected")
SP.soc_run_one = real
print("ok", n)
