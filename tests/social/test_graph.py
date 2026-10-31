# tests/social/test_graph.py — soc_mode / Graph / MetaError (http מזויף, בלי רשת)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP

for v, want in (("publish", "publish"), (" Publish ", "publish"), ("off", "off"), ("", "preview"),
                (None, "preview"), ("true", "preview"), ("1", "preview"), ("yes", "preview"), ("publsh", "preview")):
    env = {} if v is None else {"SOCIAL_MODE": v}
    ck(SP.soc_mode(env) == want, (v, SP.soc_mode(env)))

TOK, PTOK = "SYS_SECRET_1", "PAGE_SECRET_2"
class R:
    def __init__(s, j, code=200): s._j = j; s.status_code = code
    def json(s): return s._j
class Http:
    def __init__(s, script=None):
        s.calls = []; s.script = script or {}; s.polls = 0; s.ptok_calls = 0; s.fail190 = 0
    def _ret(s, method, url, params=None, data=None):
        s.calls.append((method, url, dict(params or {}), dict(data or {})))
        tok = (params or data or {}).get("access_token")
        for k, fn in s.script.items():
            if k in url and method == k.split(" ")[0] if " " in k else False:
                pass
        if method == "GET" and url.endswith("/PAGE") and (params or {}).get("fields") == "access_token":
            s.ptok_calls += 1; return R({"access_token": PTOK + ("x" * (s.ptok_calls - 1)), "id": "PAGE"})
        if "TIMEOUT:" + method + ":" + url.rsplit("/", 1)[-1] in s.script:
            raise TimeoutError("timed out")
        if method == "POST" and url.endswith("/PAGE/photos"):
            if s.fail190 > 0:
                s.fail190 -= 1; return R({"error": {"code": 190, "message": "bad " + tok}}, 400)
            return R({"id": "ph%d" % len([c for c in s.calls if c[1].endswith("/photos")])})
        if method == "POST" and url.endswith("/PAGE/feed"):
            return R({"id": "PAGE_post1"})
        if method == "GET" and url.endswith("/PAGE_post1"):
            return R({"permalink_url": "https://fb/p1"})
        if method == "POST" and url.endswith("/IG/media"):
            if s.script.get("ig_err"):
                return R({"error": {"code": 4, "message": "rate " + str(tok)}}, 400)
            return R({"id": "c%d" % len([c for c in s.calls if c[1].endswith("/IG/media")])})
        if method == "GET" and "/c" in url and (params or {}).get("fields") == "status_code":
            s.polls += 1
            if s.script.get("ig_status_error"):
                return R({"status_code": "ERROR"})
            return R({"status_code": "IN_PROGRESS" if s.polls == 1 else "FINISHED"})
        if method == "POST" and url.endswith("/IG/media_publish"):
            return R({"id": "m1"})
        if method == "GET" and url.endswith("/m1"):
            return R({"permalink": "https://ig/m1"})
        return R({})
    def get(s, url, params=None, timeout=None): return s._ret("GET", url, params=params)
    def post(s, url, data=None, params=None, timeout=None): return s._ret("POST", url, data=data, params=params)

PUB = {"SOCIAL_MODE": "publish"}
# preview → אין POST
for env in ({}, {"SOCIAL_MODE": "true"}):
    h = Http(); g = SP.Graph(h, TOK, env, sleep=lambda s: None)
    for fn in (lambda: g.fb_post("PAGE", "m", ["u1"]), lambda: g.ig_post("IG", "c", ["u1"])):
        try:
            fn(); ck(False, "should raise")
        except RuntimeError:
            ck(True, "raised")
    ck(not [c for c in h.calls if c[0] == "POST"], h.calls)   # Review Focus 5

h = Http(); g = SP.Graph(h, TOK, PUB, sleep=lambda s: None)
pid, link = g.fb_post("PAGE", "hello", ["u1", "u2", "u3"])
photos = [c for c in h.calls if c[1].endswith("/photos")]
ck(len(photos) == 3 and all(c[3].get("published") in ("false", False) and c[3].get("url") for c in photos), photos)
feed = [c for c in h.calls if c[1].endswith("/feed")][0]
import json
am = feed[3]["attached_media"]; am = json.loads(am) if isinstance(am, str) else am
ck([a["media_fbid"] for a in am] == ["ph1", "ph2", "ph3"] and feed[3]["message"] == "hello", feed)
ck(all((c[2].get("access_token") or c[3].get("access_token")) == PTOK for c in h.calls if "/PAGE/" in c[1] or c[1].endswith("PAGE_post1")), "page token used")
ck((pid, link) == ("PAGE_post1", "https://fb/p1"), (pid, link))
g.fb_post("PAGE", "again", ["u1"]); ck(h.ptok_calls == 1, "page token cached")

h = Http(); h.fail190 = 1; g = SP.Graph(h, TOK, PUB, sleep=lambda s: None)
g.fb_post("PAGE", "m", ["u1"]); ck(h.ptok_calls == 2, "190 -> re-derive page token")

h = Http(); g = SP.Graph(h, TOK, PUB, sleep=lambda s: None)
mid, ml = g.ig_post("IG", "cap", ["u1"])
media = [c for c in h.calls if c[1].endswith("/IG/media")]
ck(len(media) == 1 and media[0][3]["image_url"] == "u1" and media[0][3]["caption"] == "cap", media)
ck([c for c in h.calls if c[1].endswith("media_publish")][0][3]["creation_id"] == "c1" and (mid, ml) == ("m1", "https://ig/m1"), "single")
ck(all((c[2].get("access_token") or c[3].get("access_token")) == TOK for c in h.calls if "/IG/" in c[1]), "ig uses system token")

h = Http(); g = SP.Graph(h, TOK, PUB, sleep=lambda s: None)
g.ig_post("IG", "cap", ["u1", "u2", "u3"])
media = [c for c in h.calls if c[1].endswith("/IG/media")]
ck(len(media) == 4 and all(str(c[3].get("is_carousel_item")).lower() == "true" for c in media[:3]), media)
ck(media[3][3]["media_type"] == "CAROUSEL" and media[3][3]["children"] == "c1,c2,c3" and media[3][3]["caption"] == "cap", media[3])

h = Http({"ig_status_error": True}); g = SP.Graph(h, TOK, PUB, sleep=lambda s: None)
try:
    g.ig_post("IG", "cap", ["u1"]); ck(False, "x")
except SP.MetaError as e:
    ck(not e.unknown, e)
h = Http({"ig_err": True}); g = SP.Graph(h, TOK, PUB, sleep=lambda s: None)
try:
    g.ig_post("IG", "cap", ["u1"]); ck(False, "x")
except SP.MetaError as e:
    ck(e.code == 4 and TOK not in str(e), str(e))

# Review Focus 3: timeout בכתיבה הסופית → unknown, בלי ניסיון חוזר
for key, call in (("TIMEOUT:POST:feed", lambda g: g.fb_post("PAGE", "m", ["u1"])),
                  ("TIMEOUT:POST:media_publish", lambda g: g.ig_post("IG", "c", ["u1"]))):
    h = Http({key: True}); g = SP.Graph(h, TOK, PUB, sleep=lambda s: None)
    try:
        call(g); ck(False, "x")
    except SP.MetaError as e:
        ck(e.unknown, key)
    last = key.split(":")[-1]
    ck(len([c for c in h.calls if c[1].endswith("/" + last)]) == 1, "no retry " + key)

ck(SP._scrub("x " + TOK + " y " + PTOK, [TOK, PTOK]) == "x *** y ***", "scrub")
print("social_graph OK", n)
