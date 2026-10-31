# tests/social/test_run.py — soc_run_one / soc_daily_alert
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from _fakes import ROW, make_G, FakeGraph, ImgHttp
SP.Graph = FakeGraph
SP.soc_hidden = lambda G: set()
PUB = {"SOCIAL_MODE": "publish", "META_TOKEN": "SECRET123", "APP_BASE_URL": "https://app.test"}
def run(G, env, **kw):
    FakeGraph.instances.clear()
    return SP.soc_run_one(G, kw.pop("key", "tok1"), kw.pop("trigger", "manual"), "505709865",
                          http=ImgHttp(), env=env, **kw)

G, st, sb = make_G()
r = run(G, {"META_TOKEN": "SECRET123"})
ck(r["mode"] == "preview" and r["fb"] == "preview" and r["ig"] == "preview", r)
ck(sb.rows[-1]["mode"] == "preview" and sb.rows[-1]["fb_status"] == "preview", sb.rows)
ck(not FakeGraph.instances or not any(g.calls for g in FakeGraph.instances), "no graph calls in preview")

G, st, sb = make_G()
r = run(G, PUB)
row = sb.rows[-1]
ck(r["ok"] and r["fb"] == "ok" and r["ig"] == "ok", r)
ck(row["fb_post_id"] == "P1" and row["ig_permalink"] == "https://ig/m1" and row["mode"] == "publish", row)
ck(row["addr_key"] == SP.soc_addr_key(ROW) + "#3", row["addr_key"])
g = FakeGraph.instances[-1]
fbu = [c for c in g.calls if c[0] == "fb"][0][3]
igu = [c for c in g.calls if c[0] == "ig"][0][3]
ck(len(fbu) == 2 and all(u.startswith("https://app.test/v2/social/img/") and u.endswith(".jpg") and not u.endswith("-sq.jpg") for u in fbu), fbu)
ck(all(u.endswith("-sq.jpg") for u in igu), igu)
ck(any("פרסום ברשתות — פורסם" in str(a) for a in st["acts"]), st["acts"])

G, st, sb = make_G(); FakeGraph.next_err = {"ig": SP.MetaError("boom SECRET123", code=1)}
r = run(G, PUB); FakeGraph.next_err = {}
ck(r["fb"] == "ok" and r["ig"] == "failed" and "SECRET123" not in (sb.rows[-1].get("error") or ""), sb.rows[-1])
ck(any("נכשל" in str(a) for a in st["acts"]), st["acts"])

# Review Focus 3
G, st, sb = make_G(); FakeGraph.next_err = {"fb": SP.MetaError("t", unknown=True)}
r = run(G, PUB); FakeGraph.next_err = {}
ck(r["fb"] == "unknown", r)
r2 = run(G, PUB)
ck(r2["fb"] == "skipped" and "כבר נשלח היום" in r2["reason"], r2)

# Review Focus 2
G, st, sb = make_G(rows=[dict(ROW, תמונות=["https://img/bad1.jpg", "https://img/bad2.jpg"])])
r = run(G, PUB)
ck(not r["ok"] and r["reason"] == "אין תמונות" and not any(g.calls for g in FakeGraph.instances), r)

# token 190 → push פעם ביום
G, st, sb = make_G(); FakeGraph.next_err = {"fb": SP.MetaError("bad", code=190), "ig": SP.MetaError("bad", code=190)}
run(G, PUB); run(G, PUB, channels=["fb"]); FakeGraph.next_err = {}
ck(len([p for p in st["push"] if "טוקן" in p[0] + p[1] or "נותק" in p[0] + p[1]]) == 1, st["push"])

# rate limit → paused_until
G, st, sb = make_G(); FakeGraph.next_err = {"fb": SP.MetaError("rl", code=4)}
run(G, PUB); FakeGraph.next_err = {}
ck(float(st["cfg"]["v2_social"]["paused_until"]) > 0, st["cfg"])
r = run(G, PUB, trigger="auto")
ck(not r["ok"] and "מושהה" in r["reason"], r)

G, st, sb = make_G()
r = run(G, PUB, channels=["ig"]); ck(r["fb"] == "skipped" and r["ig"] == "ok", r)
r = run(G, dict(PUB, SOCIAL_CHANNELS="fb"), key="tok1")
ck(r["ig"] == "skipped", r)

G, st, sb = make_G(); FakeGraph.next_quota = 0
r = run(G, PUB); FakeGraph.next_quota = 25
ck(r["ig"] == "skipped" and r["fb"] == "ok", r)

# Review Focus 5
G, st, sb = make_G()
r = run(G, dict(PUB, SOCIAL_MODE="true"))
ck(r["mode"] == "preview" and not any(g.calls for g in FakeGraph.instances), r)

G, st, sb = make_G()
r = run(G, PUB, key="nope"); ck(not r["ok"] and r["reason"] == "הנכס לא נמצא", r)
r = run(G, {"SOCIAL_MODE": "off"}); ck(not r["ok"], r)
print("social_run OK", n)
