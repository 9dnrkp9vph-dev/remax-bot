# tests/social/test_db.py — supabase_db: social_posts (insert / update / recent)
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
MODE = {"fail": False}
def fpost(url, headers=None, params=None, json=None, timeout=None):
    CALLS.append(("POST", url, params, json, headers))
    return R([], 500) if MODE["fail"] else R([dict(json[0], id="u1")])
def fpatch(url, headers=None, params=None, json=None, timeout=None):
    CALLS.append(("PATCH", url, params, json, headers)); return R()
def fget(url, headers=None, params=None, timeout=None):
    CALLS.append(("GET", url, params, None, headers))
    return R([{"id": "a"}] if int((params or {}).get("offset", 0)) == 0 else [])
S.requests.post, S.requests.patch, S.requests.get = fpost, fpatch, fget

row = S.social_insert({"property_key": "abc"})
m, url, p, j, h = CALLS[-1]
ck(m == "POST" and url.endswith("/rest/v1/social_posts"), CALLS[-1])
ck(j[0]["office_id"] == "off" and j[0]["property_key"] == "abc", j)
ck("return=representation" in h.get("Prefer", ""), h)
ck(row and row["id"] == "u1", row)

ck(S.social_update("u1", {"fb_status": "ok"}) is True, "update ok")
m, url, p, j, h = CALLS[-1]
ck(m == "PATCH" and p["id"] == "eq.u1" and p["office_id"] == "eq.off", p)
ck(j["fb_status"] == "ok" and j.get("updated_at"), j)

rows = S.social_recent(14)
m, url, p, j, h = [c for c in CALLS if c[0] == "GET"][0]
ck(url.endswith("/rest/v1/social_posts") and str(p.get("created_at", "")).startswith("gte.") and p.get("order") == "created_at.desc", p)
ck(rows == [{"id": "a"}], rows)

MODE["fail"] = True
ck(S.social_insert({"property_key": "x"}) is None, "insert failure -> None")
print("social_db OK", n)
