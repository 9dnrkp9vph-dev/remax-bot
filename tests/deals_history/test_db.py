# tests/deals_history/test_db.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import supabase_db as S
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
calls = []
class R:
    def __init__(s, j=None): s._j = j
    def raise_for_status(s): pass
    def json(s): return s._j
class Q:
    def post(s, url, headers=None, params=None, json=None, timeout=None):
        calls.append(("post", url, params, json)); return R([])
    def get(s, url, headers=None, params=None, timeout=None):
        calls.append(("get", url, params, None)); return R([{"id": "1", "agent": "משה"}])
S.requests = Q(); S.SUPABASE_URL = "https://x"; S.SB_OFFICE_ID = "OFF"
rows = [{"src_key": "motzkin|2025|s|1", "agent": "משה", "raw": {"a": "b"}},
        {"src_key": "motzkin|2025|s|1", "agent": "משה כהן", "raw": {}},
        {"src_key": "motzkin|2025|s|2", "agent": "דנה"}]
ck(S.deal_history_upsert(rows) == 2, "dedup by src_key")
p = calls[0]
ck(p[1].endswith("/rest/v1/deal_history") and p[2]["on_conflict"] == "office_id,src_key", p[2])
ck(all(r["office_id"] == "OFF" for r in p[3]) and set(p[3][0]) == set(p[3][1]), "office + uniform cols")
ck([r["agent"] for r in p[3] if r["src_key"].endswith("|1")] == ["משה כהן"], "last wins")
out = S.deal_history_all()
g = calls[-1]
ck(g[0] == "get" and "raw" not in g[2]["select"].split(",") and out[0]["agent"] == "משה", g[2]["select"])   # עמודת raw (jsonb) לא נמשכת; agent_raw כן
print("OK", n, "checks")
