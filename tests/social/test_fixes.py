# tests/social/test_fixes.py — תיקוני הביקורת הסופית (C1, I1–I5)
import os, sys, time, threading, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from _fakes import ROW, make_G, FakeGraph, ImgHttp
from zoneinfo import ZoneInfo
IL = ZoneInfo("Asia/Jerusalem")
SP.Graph = FakeGraph
SP.soc_hidden = lambda G: set()
PUB = {"SOCIAL_MODE": "publish", "META_TOKEN": "T", "APP_BASE_URL": "https://a"}
def run(G, **kw): return SP.soc_run_one(G, kw.pop("key", "tok1"), kw.pop("trigger", "manual"), "5", http=ImgHttp(), env=PUB, **kw)

# C1a: שתי לחיצות במקביל → פרסום אחד
G, st, sb = make_G()
gate = threading.Event(); orig = FakeGraph.fb_post
def slow(self, *a):
    gate.wait(2); return orig(self, *a)
FakeGraph.fb_post = slow
FakeGraph.instances.clear()
out = []
t1 = threading.Thread(target=lambda: out.append(run(G))); t1.start(); time.sleep(0.2)
r2 = run(G); gate.set(); t1.join()
FakeGraph.fb_post = orig
ck(not r2["ok"] and "בתהליך" in r2["reason"], r2)
ck(sum(len([c for c in g.calls if c[0] == "fb"]) for g in FakeGraph.instances) == 1, "one fb post")

# C1: רשומה 'pending' לפני הכתיבה ל-Meta, ועדכון אחריה
G, st, sb = make_G(); seen = []
orig2 = FakeGraph.fb_post
def peek(self, *a):
    seen.append([dict(r) for r in sb.rows]); return orig2(self, *a)
FakeGraph.fb_post = peek
r = run(G); FakeGraph.fb_post = orig2
ck(seen and seen[0] and seen[0][-1]["fb_status"] == "pending", seen)
ck(len(sb.rows) == 1 and sb.rows[0]["fb_status"] == "ok", sb.rows)

# C1c: היסטוריה לא נקראת → לא מפרסמים
G, st, sb = make_G()
def boom(d): raise RuntimeError("db down")
sb.social_recent = boom
r = run(G); ck(not r["ok"] and "היסטורי" in r["reason"] and not sb.rows, r)

# C1: רישום נכשל → לא מפרסמים
G, st, sb = make_G(); sb.social_insert = lambda rec: None
FakeGraph.instances.clear(); r = run(G)
ck(not r["ok"] and not any(g.calls for g in FakeGraph.instances), r)

# C1d: חריגה לא צפויה אחרי פרסום → הרשומה נשמרת עם unknown
G, st, sb = make_G(); orig3 = FakeGraph.ig_post
FakeGraph.ig_post = lambda self, *a: (_ for _ in ()).throw(KeyError("id"))
r = run(G); FakeGraph.ig_post = orig3
ck(sb.rows and sb.rows[0]["fb_status"] == "ok" and sb.rows[0]["ig_status"] == "unknown", sb.rows)
ck(SP.soc_can_publish(ROW, "ig", sb.rows, time.time(), set()) == (False, "כבר נשלח היום"), "pending/unknown blocks today")
ck(SP.soc_can_publish(ROW, "fb", [dict(sb.rows[0], fb_status="pending")], time.time(), set())[1] == "כבר נשלח היום", "pending blocks")

# I3: הסתרה מהאתר לא נקראת → לא מפרסמים (preview מותר)
G, st, sb = make_G(); SP.soc_hidden = lambda G: None
r = run(G); ck(not r["ok"] and "הסתר" in r["reason"], r)
r = SP.soc_run_one(G, "tok1", "manual", "5", http=ImgHttp(), env={"META_TOKEN": "T"}); ck(r["ok"] and r["mode"] == "preview", r)
SP.soc_hidden = lambda G: set()

# I5: 5xx / קוד 1-2 בכתיבה הסופית → unknown
class R:
    def __init__(s, j, c): s._j, s.status_code = j, c
    def json(s): return s._j
class H:
    def __init__(s, resp): s.resp = resp
    def post(s, url, data=None, params=None, timeout=None): return s.resp
    def get(s, url, params=None, timeout=None): return R({}, 200)
for resp in (R({"error": {"message": "x"}}, 500), R({"error": {"code": 2, "message": "x"}}, 400)):
    from _fakes import REAL_GRAPH
    gg = REAL_GRAPH(H(resp), "T", PUB)
    try:
        gg._call("POST", "PAGE/feed", "T", {}, final=True); ck(False, "x")
    except SP.MetaError as e:
        ck(e.unknown, (resp.status_code, resp._j))
    try:
        gg._call("POST", "PAGE/photos", "T", {}, final=False); ck(False, "x")
    except SP.MetaError as e:
        ck(not e.unknown, "non-final stays failed")

# I2: נכס עם תמונה אחת לא נמחק מההמתנה לפני שעברו 72 שעות + WAIT_DAYS
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=IL).timestamp()
one = dict(ROW, **{"מספר מודעה": "one", "תמונות": ["https://x/1.jpg"], "_y2_first_seen": "31/10/2026 11:00"})
st0 = {"known": {"one": NOW}, "waiting": {"one": NOW - 3.1 * 86400}, "enabled_at": NOW - 9e5}
r = SP.soc_plan_round([one], st0, [], NOW, set(), False)
ck(r["publish"] == ["one"], r)

# I4: אוטומטי חזר אחרי הפסקה ארוכה → זריעה מחדש בלי פרסום
G, st, sb = make_G(rows=[dict(ROW, **{"מספר מודעה": k, "כתובת": "ר " + k}) for k in ("a", "b", "c")])
st["cfg"]["v2_social"] = {"enabled_at": NOW - 30 * 86400, "known": {"a": NOW - 9 * 86400}, "waiting": {}, "last_tick": NOW - 9 * 86400}
RUNS = []; real = SP.soc_run_one
SP.soc_run_one = lambda *a, **k: (RUNS.append(a[1]), {"ok": True})[1]
ON = dict(PUB, SOCIAL_AUTO="1")
res = SP.soc_auto_tick(G, NOW, ON, sleep=lambda s: None)
ck(not RUNS and res.get("reseeded") and set(st["cfg"]["v2_social"]["known"]) >= {"a", "b", "c"}, (res, RUNS))

# I1: שבת/לילה נבדקים שוב לפני כל פוסט בסבב
G, st, sb = make_G(rows=[dict(ROW, **{"מספר מודעה": k, "כתובת": "ר " + k}) for k in ("a", "n1", "n2")])
st["cfg"]["v2_social"] = {"enabled_at": NOW - 86400, "known": {"a": NOW}, "waiting": {}, "last_tick": NOW - 600}
calls = {"n": 0}
def quiet():
    calls["n"] += 1; return calls["n"] > 1      # פתוח בתכנון, סגור אחרי ההמתנה
G["_shabbat_quiet_now"] = quiet
RUNS.clear()
SP.soc_auto_tick(G, NOW, ON, sleep=lambda s: None)
ck(len(RUNS) == 1 and len(st["cfg"]["v2_social"]["waiting"]) == 1, (RUNS, st["cfg"]["v2_social"]["waiting"]))
SP.soc_run_one = real
print("social_fixes OK", n)
