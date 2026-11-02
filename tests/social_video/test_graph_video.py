# tests/social_video/test_graph_video.py — Graph: סטורי/ריל לאינסטגרם ולעמוד (http מזויף)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
TOK, PTOK = "SYS_SECRET_1", "PAGE_SECRET_2"
class R:
    def __init__(s, j, code=200): s._j = j; s.status_code = code
    def json(s): return s._j
class Http:
    def __init__(s, fail=None): s.calls, s.fail = [], fail or {}
    def get(s, url, params=None, timeout=None, headers=None):
        s.calls.append(("GET", url, dict(params or {}), dict(headers or {})))
        if url.endswith("/PAGE") and (params or {}).get("fields") == "access_token":
            return R({"access_token": PTOK})
        if (params or {}).get("fields") == "status_code":
            return R({"status_code": "FINISHED"})
        if (params or {}).get("fields") == "permalink":
            return R({"permalink": "https://ig/reel1"})
        if (params or {}).get("fields") == "permalink_url":
            return R({"permalink_url": "https://fb/reel1"})
        return R({})
    def post(s, url, data=None, timeout=None, headers=None, params=None):
        s.calls.append(("POST", url, dict(data or {}), dict(headers or {})))
        if "upload" in s.fail and ("rupload" in url or "upload.example" in url):
            return R({"error": {"message": "bad upload " + PTOK}}, 400)
        if url.endswith("/IG/media"):
            return R({"id": "C1"})
        if url.endswith("/IG/media_publish"):
            return R({"id": "M1"})
        if url.endswith("/PAGE/video_stories"):
            ph = (data or {}).get("upload_phase")
            return R({"video_id": "VS1", "upload_url": "https://upload.example/vs1"} if ph == "start" else {"success": True, "post_id": "ST1"})
        if url.endswith("/PAGE/video_reels"):
            ph = (data or {}).get("upload_phase")
            return R({"video_id": "VR1"} if ph == "start" else {"success": True})
        if "rupload" in url or "upload.example" in url:
            return R({"success": True})
        return R({})

env = {"SOCIAL_MODE": "publish"}
h = Http(); g = SP.Graph(h, TOK, env, sleep=lambda s: None)
mid, link = g.ig_video("IG", "STORIES", "https://app/v.mp4")
c0 = [c for c in h.calls if c[1].endswith("/IG/media")][0][2]
ck(mid == "M1" and c0["media_type"] == "STORIES" and c0["video_url"] == "https://app/v.mp4", c0)
ck("caption" not in c0 and "share_to_feed" not in c0 and c0.get("is_ai_generated") == "true", c0)
ck(link == "", link)

h = Http(); g = SP.Graph(h, TOK, env, sleep=lambda s: None)
mid, link = g.ig_video("IG", "REELS", "https://app/v.mp4", caption="cap", cover_url="https://app/c.jpg")
c0 = [c for c in h.calls if c[1].endswith("/IG/media")][0][2]
ck(c0["media_type"] == "REELS" and c0["share_to_feed"] == "true" and c0["cover_url"] == "https://app/c.jpg" and c0["caption"] == "cap", c0)
ck(link == "https://ig/reel1", link)

h = Http(); g = SP.Graph(h, TOK, env, sleep=lambda s: None)
sid = g.fb_video_story("PAGE", "https://app/v.mp4")
seq = [(c[0], c[1].rsplit("/", 1)[-1], c[2].get("upload_phase")) for c in h.calls if c[0] == "POST"]
ck(seq == [("POST", "video_stories", "start"), ("POST", "vs1", None), ("POST", "video_stories", "finish")], seq)
up = [c for c in h.calls if "upload.example" in c[1]][0]
ck(up[3].get("file_url") == "https://app/v.mp4" and up[3].get("Authorization") == "OAuth " + PTOK, up[3])
ck(sid == "ST1", sid)

h = Http(); g = SP.Graph(h, TOK, env, sleep=lambda s: None)
vid, link = g.fb_reel("PAGE", "https://app/v.mp4", "תיאור")
posts = [c for c in h.calls if c[0] == "POST"]
ck(posts[0][1].endswith("/PAGE/video_reels") and posts[0][2]["upload_phase"] == "start", posts[0])
ck("rupload.facebook.com/video-upload/" in posts[1][1] and posts[1][1].endswith("/VR1") and posts[1][3]["file_url"] == "https://app/v.mp4", posts[1])
ck(posts[2][2]["upload_phase"] == "finish" and posts[2][2]["video_state"] == "PUBLISHED" and posts[2][2]["description"] == "תיאור", posts[2])
ck(vid == "VR1" and link == "https://fb/reel1", (vid, link))

h = Http(fail={"upload": 1}); g = SP.Graph(h, TOK, env, sleep=lambda s: None)
try:
    g.fb_reel("PAGE", "https://app/v.mp4", "x"); ck(False, "should raise")
except SP.MetaError as e:
    ck(PTOK not in str(e) and TOK not in str(e), str(e))

for meth, args in (("ig_video", ("IG", "STORIES", "u")), ("fb_video_story", ("PAGE", "u")), ("fb_reel", ("PAGE", "u", "d"))):
    h = Http(); g = SP.Graph(h, TOK, {"SOCIAL_MODE": "preview"})
    try:
        getattr(g, meth)(*args); ck(False, meth)
    except RuntimeError:
        ck(h.calls == [], (meth, h.calls))
print("video_graph OK", n)
