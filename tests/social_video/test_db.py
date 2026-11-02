# tests/social_video/test_db.py — supabase_db: social_videos / social_links
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import supabase_db as S
S.SB_OFFICE_ID = "off"
S.SUPABASE_URL = "https://sb.test"
class R:
    def __init__(s, j=None, code=200): s._j = j if j is not None else []; s.status_code = code
    def raise_for_status(s):
        if s.status_code >= 400: raise RuntimeError("http %d" % s.status_code)
    def json(s): return s._j
CALLS = []
ST = {"claim": [{"id": "v1"}], "link": [{"code": "ab12", "clicks": 4}]}
def fpost(url, headers=None, params=None, json=None, timeout=None):
    CALLS.append(("POST", url, params, json, headers)); return R([dict(json[0], id="v1")])
def fpatch(url, headers=None, params=None, json=None, timeout=None):
    CALLS.append(("PATCH", url, params, json, headers))
    return R(ST["claim"] if "social_videos" in url else [])
def fget(url, headers=None, params=None, timeout=None):
    CALLS.append(("GET", url, params, None, headers))
    if "social_links" in url: return R(ST["link"])
    return R([{"id": "v1", "status": "pending"}] if int((params or {}).get("offset", 0)) == 0 else [])
S.requests.post, S.requests.patch, S.requests.get = fpost, fpatch, fget

r = S.video_insert({"property_key": "abc", "status": "rendering"})
m, url, p, j, h = CALLS[-1]
ck(m == "POST" and url.endswith("/rest/v1/social_videos") and j[0]["office_id"] == "off", CALLS[-1])
ck(r and r["id"] == "v1", r)

ck(S.video_update("v1", {"status": "pending"}) is True, "update")
m, url, p, j, h = CALLS[-1]
ck(p["id"] == "eq.v1" and p["office_id"] == "eq.off" and j["status"] == "pending" and j.get("updated_at"), (p, j))

ck(S.video_claim("v1", "pending", "approved", {"decided_by": "אייל"}) is True, "claim ok")
m, url, p, j, h = CALLS[-1]
ck(p["status"] == "eq.pending" and j["status"] == "approved" and j["decided_by"] == "אייל", (p, j))
ck("return=representation" in h.get("Prefer", ""), h)
ST["claim"] = []
ck(S.video_claim("v1", "pending", "approved", {}) is False, "claim lost")

g = S.video_get("v1")
ck(g and g["id"] == "v1", g)
rec = S.video_recent(31)
m, url, p, j, h = [c for c in CALLS if c[0] == "GET" and "social_videos" in c[1]][-1]
ck(str(p.get("created_at", "")).startswith("gte.") and p.get("order") == "created_at.desc", p)

ck(S.link_insert({"code": "ab12", "property_key": "abc", "channel": "fb_reel"})["id"] == "v1", "link insert")
ck(CALLS[-1][1].endswith("/rest/v1/social_links") and CALLS[-1][3][0]["office_id"] == "off", CALLS[-1])
ck(S.link_get("ab12")["clicks"] == 4, "link get")
S.link_click("ab12")
m, url, p, j, h = CALLS[-1]
ck(m == "PATCH" and url.endswith("/rest/v1/social_links") and p["code"] == "eq.ab12" and j["clicks"] == 5 and j.get("last_click_at"), CALLS[-1])

def boom(*a, **k): raise RuntimeError("down")
S.requests.post = S.requests.patch = S.requests.get = boom
ck(S.video_insert({}) is None and S.video_update("v1", {}) is False and S.video_claim("v1", "a", "b", {}) is False, "failures")
ck(S.video_get("v1") is None and S.link_get("x") is None, "get failures")
print("video_db OK", n)
