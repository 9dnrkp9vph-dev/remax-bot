# tests/social/test_tile.py — social_health_tile (ריבוע בלוח הבקרה) + token_bad בקונפיג
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from _fakes import make_G, FakeGraph, ImgHttp
SP.Graph = FakeGraph
SP.soc_hidden = lambda G: set()
PUB = {"SOCIAL_MODE": "publish", "META_TOKEN": "T"}

G, st, sb = make_G()
t = SP.social_health_tile(G, time.time(), env={})
ck(t["key"] == "social" and t["label"] == "פרסום ברשתות" and t["status"] == "none", t)
ck(SP.social_health_tile(G, time.time(), env=PUB)["status"] == "ok", "configured, nothing yet → ok")

FakeGraph.next_err = {"fb": SP.MetaError("bad", code=190), "ig": SP.MetaError("bad", code=190)}
SP.soc_run_one(G, "tok1", "manual", "5", http=ImgHttp(), env=PUB); FakeGraph.next_err = {}
ck(st["cfg"]["v2_social"].get("token_bad") is True, st["cfg"])
ck(SP.social_health_tile(G, time.time(), env=PUB)["status"] == "bad", "token bad → red")

G, st, sb = make_G(); st["cfg"]["v2_social"] = {"token_bad": True}
SP.soc_run_one(G, "tok1", "manual", "5", http=ImgHttp(), env=PUB)
ck(st["cfg"]["v2_social"].get("token_bad") is False, "success clears token_bad")
tl = SP.social_health_tile(G, time.time(), env=PUB)
ck(tl["status"] == "ok" and tl["last"], tl)

G, st, sb = make_G(); FakeGraph.next_err = {"ig": SP.MetaError("x", code=1)}
SP.soc_run_one(G, "tok1", "manual", "5", http=ImgHttp(), env=PUB); FakeGraph.next_err = {}
ck(SP.social_health_tile(G, time.time(), env=PUB)["status"] == "warn", "failure today → warn")
print("social_tile OK", n)
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "effie_v2.py"), encoding="utf-8").read()
assert '"social": lambda: __import__("social_publish").social_health_tile(G, now)' in src and 'sc = get("social", default=None)' in src
print("social_tile wiring OK")
