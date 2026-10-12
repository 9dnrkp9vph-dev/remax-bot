# tests/deals_history/test_import_route.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["DEALS_IMPORT_KEY"] = "K123"
from flask import Flask, jsonify
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
ck(D.canon_agent("משה", "motzkin", {"motzkin|משה": "משה כהן"}, lambda x: x) == "משה כהן", "mapped")
ck(D.canon_agent("סיכום", "motzkin", {"motzkin|סיכום": "-"}, lambda x: x) == "", "not an agent")
ck(D.canon_agent("בן", "bialik", {}, lambda x: {"בן": "בן קדוש"}.get(x, x)) == "בן קדוש", "alias canon")
saved = []
class SB:
    def enabled(self): return True
    def deal_history_upsert(self, rows): saved.extend(rows); return len(rows)
G = {"_canon_agent_name": lambda x: x, "_web_auth": lambda: None, "_etag_wrap": lambda d: jsonify(d),
     "_log_activity": lambda *a, **k: None, "_sbdb": SB(), "_load_config": lambda: {}}
app = Flask("t")
D.register(app, G, lambda html: html)
c = app.test_client()
body = {"rows": [{"src_key": "motzkin|2025|s|1", "agent": "משה", "branch": "motzkin", "year": 2025},
                 {"src_key": "motzkin|2025|s|2", "agent": "סיכום", "branch": "motzkin", "year": 2025}],
        "amap": {"motzkin|משה": "משה כהן", "motzkin|סיכום": "-"}}
ck(c.post("/v2/api/deals/history/import", json=body).status_code == 403, "no key")
ck(c.post("/v2/api/deals/history/import", json=body, headers={"X-Import-Key": "bad"}).status_code == 403, "bad key")
r = c.post("/v2/api/deals/history/import", json=body, headers={"X-Import-Key": "K123"}).get_json()
ck(r["ok"] and r["saved"] == 1 and r["skipped_no_agent"] == 1, r)
ck(saved[0]["agent"] == "משה כהן" and saved[0]["agent_raw"] == "משה", saved[0])
os.environ["DEALS_IMPORT_KEY"] = ""
app2 = Flask("t2"); D.register(app2, G, lambda h: h)
ck(app2.test_client().post("/v2/api/deals/history/import", json=body, headers={"X-Import-Key": ""}).status_code == 403, "empty env = off")
print("OK", n, "checks")
