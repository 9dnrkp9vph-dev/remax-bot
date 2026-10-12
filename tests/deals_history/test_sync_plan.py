# tests/deals_history/test_sync_plan.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import deals_history as D
import supabase_db as S
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
E = [{"name": "מעקב עסקאות 2026.xlsx", "path": "/a/1", "rev": "1", "server_modified": "2026-07-09T10:47:00Z"},
     {"name": "מעקב עסקאות 2026 (Ohad Peled's conflicted copy 2026-02-11).xlsx", "path": "/a/2", "rev": "2", "server_modified": "2026-10-11T13:52:00Z"},
     {"name": "~$מעקב עסקאות 2026.xlsx", "path": "/a/3", "rev": "3", "server_modified": "2026-10-12T00:00:00Z"},
     {"name": "סיכום_עסקאות_אפריל_2026.txt", "path": "/a/4", "rev": "4", "server_modified": "2026-10-12T00:00:00Z"}]
ck(D.pick_latest(E)["path"] == "/a/2", "newest tracking file, conflicted allowed, ~$ and txt ignored")
ck(D.pick_latest([]) is None, "empty")
ck(D.pick_latest([{"name": "2026 קרית ים.xlsx", "path": "/k", "rev": "1", "server_modified": "2026-09-29T06:31:00Z"}])["path"] == "/k", "KY file name without מעקב")
ck(D.pick_latest([{"name": "גיבוי מעקב עסקאות 2026.xlsx", "path": "/g", "rev": "1", "server_modified": "2026-12-01T00:00:00Z"},
                  {"name": "מעקב עסקאות 2026.xlsx", "path": "/m", "rev": "1", "server_modified": "2026-07-01T00:00:00Z"}])["path"] == "/m", "backup not picked")
a = {"src_key": "b|2026|s|1", "agent": "x", "deal_amount": 1, "raw": {"z": 1}}
ck(D.row_hash(a) == D.row_hash(dict(a, raw={"z": 2}, _x=5)) and D.row_hash(a) != D.row_hash(dict(a, deal_amount=2)), "hash ignores raw/_")
ex = [dict(src_key="k1", src_hash=D.row_hash({"src_key": "k1", "v": 1})),
      dict(src_key="k2", src_hash="old"), dict(src_key="k3", src_hash="h"),
      dict(src_key="k4", src_hash="h", missing_since="2026-10-01T00:00:00Z")]
inc = [{"src_key": "k1", "v": 1}, {"src_key": "k2", "v": 2}, {"src_key": "k4", "v": 4}, {"src_key": "k5", "v": 5}]
p = D.sync_plan(ex, inc, switched=False)
ck(sorted(r["src_key"] for r in p["upsert"]) == ["k2", "k4", "k5"], p["upsert"])
ck(all(r.get("src_hash") for r in p["upsert"]), "upserts carry hash")
ck(p["missing"] == ["k3"] and p["back"] == ["k4"] and not p["guarded"], p)
few = D.sync_plan(ex, [{"src_key": "k5", "v": 5}], switched=True)
ck(few["missing"] == [] and few["guarded"], "switched file with <60% → no missing marks")
ck(D.sync_plan(ex, [{"src_key": "k5", "v": 5}], switched=False)["missing"] == ["k1", "k2", "k3"], "same file → missing marked")
# שכבת נתונים
calls = []
class Rq:
    def patch(s, url, headers=None, params=None, json=None, timeout=None):
        calls.append((params, json));
        class X:
            def raise_for_status(self): pass
        return X()
S.requests = Rq(); S.SUPABASE_URL = "https://x"; S.SB_OFFICE_ID = "OFF"
ck(S.deal_history_set_missing(["k1", 'a"b'], "2026-10-12T00:00:00Z") == 2, "count")
ck(calls[0][1] == {"missing_since": "2026-10-12T00:00:00Z"} and calls[0][0]["src_key"].startswith("in.(") and calls[0][0]["office_id"] == "eq.OFF", calls[0])
ck('"a\\"b"' in calls[0][0]["src_key"], "quoted keys")
ck(S.deal_history_set_missing([], None) == 0, "empty")
ck("src_hash" in S._DH_COLS and "src_path" in S._DH_COLS and "agent_raw" in S._DH_COLS, "cols")
print("OK", n, "checks")
