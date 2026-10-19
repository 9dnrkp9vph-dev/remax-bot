# tests/crm/test_team_db.py — supabase_db: אנשי צוות (team_contacts) — קריאה בסדר, upsert לפי שם, החלפת שם
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import supabase_db as S
S.SB_OFFICE_ID = "off"
class R:
    def __init__(s, j=None): s._j = j if j is not None else []; s.status_code = 200
    def raise_for_status(s): pass
    def json(s): return s._j
GET, POST, PATCH = [], [], []
ROWS = [{"id": "1", "name": "דנה לוי", "phone": "0501111111", "vphone": "", "license": "123", "email": "d@x.co", "active": True, "sort": 2},
        {"id": "2", "name": "רועי כהן", "phone": "0502222222", "vphone": "0529000000", "license": "", "email": "", "active": False, "sort": 1}]
def fget(url, headers=None, params=None, timeout=None):
    GET.append(params); return R(ROWS if int((params or {}).get("offset", 0)) == 0 else [])
S.requests.get = fget
S.requests.post = lambda url, headers=None, params=None, json=None, timeout=None: (POST.append((params, json, headers)), R())[1]
S.requests.patch = lambda url, headers=None, params=None, json=None, timeout=None: (PATCH.append((params, json)), R())[1]
rows = S.team_fetch()
ck([r["name"] for r in rows] == ["רועי כהן", "דנה לוי"], ("sorted by sort then name", rows))
ck(S.team_fetch(active_only=True) and all(r["active"] for r in S.team_fetch(active_only=True)), "active only")
S.team_upsert([{"name": "דנה לוי", "phone": "0501111111"}], "אייל")
p, j, h = POST[-1]
ck(p["on_conflict"] == "office_id,name" and "merge-duplicates" in h["Prefer"] and j[0]["office_id"] == "off" and j[0]["updated_by"] == "אייל", POST[-1])
S.team_update("1", {"name": "דנה כהן", "email": "x@y.co", "bogus": 1}, "אייל")
p, j = PATCH[-1]
ck(p["id"] == "eq.1" and p["office_id"] == "eq.off" and j["name"] == "דנה כהן" and "bogus" not in j, PATCH[-1])
print("team_db OK", n)
