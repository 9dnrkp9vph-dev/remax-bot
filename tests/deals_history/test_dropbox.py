# tests/deals_history/test_dropbox.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.update(DROPBOX_APP_KEY="k", DROPBOX_APP_SECRET="s", DROPBOX_REFRESH_TOKEN="rt")
import dropbox_api as X
X._TOK.update(v="", exp=0)
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
calls = []
class R:
    def __init__(s, code=200, j=None, content=b"", headers=None): s.status_code, s._j, s.content, s.headers = code, j, content, headers or {}
    def json(s): return s._j
    def raise_for_status(s):
        if s.status_code >= 400: raise RuntimeError("http %d" % s.status_code)
class H:
    def post(s, url, data=None, headers=None, json=None, timeout=None):
        calls.append((url, data, headers, json))
        if "oauth2/token" in url:
            return R(j={"access_token": "AT", "expires_in": 14400})
        if url.endswith("list_folder"):
            return R(j={"entries": [{".tag": "file", "name": "a.xlsx", "path_display": "/p/a.xlsx", "rev": "r1",
                                     "server_modified": "2026-10-11T13:52:00Z", "size": 5},
                                    {".tag": "folder", "name": "old", "path_display": "/p/old"}], "has_more": False})
        if url.endswith("download"):
            return R(content=b"XLSX", headers={"Dropbox-API-Result": json_mod.dumps({"rev": "r9"})})
        return R(500)
json_mod = json
h = H()
ck(X.configured(), "configured")
ck(X.access_token(h) == "AT" and calls[0][1]["refresh_token"] == "rt", "refresh")
X.access_token(h); ck(len([c for c in calls if "oauth2" in c[0]]) == 1, "token cached")
lst = X.list_folder("/p", h)
ck(lst == [{"name": "a.xlsx", "path": "/p/a.xlsx", "rev": "r1", "server_modified": "2026-10-11T13:52:00Z", "size": 5}], lst)
ck(calls[-1][2]["Authorization"] == "Bearer AT" and calls[-1][3]["path"] == "/p", "list call")
data, rev = X.download("/p/a.xlsx", h)
ck(data == b"XLSX" and rev == "r9" and json.loads(calls[-1][2]["Dropbox-API-Arg"])["path"] == "/p/a.xlsx", "download")
ck(all(ord(ch) < 128 for ch in calls[-1][2]["Dropbox-API-Arg"]), "header is ASCII (Hebrew path escaped)")
os.environ["DROPBOX_REFRESH_TOKEN"] = ""
ck(not X.configured(), "not configured without token")
print("OK", n, "checks")
