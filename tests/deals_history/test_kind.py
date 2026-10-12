# tests/deals_history/test_kind.py — אייל 12/10: "תפריד בין עסקאות מכירה וקניה לבין שכירויות"
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from flask import Flask, jsonify, request
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
B = {"collection_status": "", "invoice_no": "", "receipt_no": "", "deposited": "", "remax_approved": "", "notes": "",
     "lawyer_notes": "", "other_broker": "", "lead_source": "", "commission_gross": None, "client_phone": "", "client_name": ""}
def row(i, side, date, comm, agent="משה כהן", br="bialik"):
    return dict(B, id=i, branch=br, year=int(date[:4]), deal_date=date, street="הגפן %s" % i, city="ביאליק", side=side,
                agent=agent, deal_amount=1000, commission_net=comm, paid_amount=None, reported_date=None)
R = [row("1", "מוכר", "2026-01-01", 20000), row("2", "קונה", "2026-02-01", 15000),
     row("3", "שוכר", "2026-03-01", 4000), row("4", "משכיר", "2026-04-01", 3000), row("5", "", "2026-05-01", 9000)]
ck([r["id"] for r in D.by_kind(R, "sale")] == ["1", "2", "5"] and [r["id"] for r in D.by_kind(R, "rent")] == ["3", "4"], "by_kind")
ck(D.by_kind(R, "") == R and D.by_kind(R, "zz") == R, "all")
st = D.stats(R, 2026)
ck(st["bySide"] == {"sale": {"n": 3, "commission": 44000}, "rent": {"n": 2, "commission": 7000}}, st.get("bySide"))
S = {"T": {"role": "agent", "drole": "agent", "name": "משה כהן", "phone": "1"}, "M": {"role": "admin", "drole": "manager", "name": "מנהל", "phone": "2"}}
class SB:
    def enabled(self): return True
    def deal_history_all(self): return R
kk = lambda x: x.replace(" ", "")
G = {"_web_auth": lambda: S.get(request.headers.get("X-Auth-Token", "")), "_canon_key": kk,
     "_scope_keys_phones": lambda role, name, ph, a=None, an=None: ({kk(name)}, set(), False),
     "_etag_wrap": lambda d: jsonify(d), "_canon_agent_name": lambda x: x, "_log_activity": lambda *a, **k: None, "_sbdb": SB()}
app = Flask("k"); D._HIST_CACHE["ts"] = 0; D.register(app, G, lambda h: h); c = app.test_client()
M, T = {"X-Auth-Token": "M"}, {"X-Auth-Token": "T"}
g = lambda u, h: c.get(u, headers=h).get_json()
ck([x["id"] for x in g("/v2/api/deals/history/mine?deal=rent", T)["results"]] == ["4", "3"], "mine rent, newest first")
ck(g("/v2/api/deals/history/mine?deal=sale", T)["n"] == 3, "mine sale")
s2 = g("/v2/api/deals/history/stats?year=2026&deal=rent", M)
ck(s2["total"] == {"n": 2, "commission": 7000} and s2["deal"] == "rent" and s2["bySide"]["sale"]["n"] == 3, s2)
ck([x["id"] for x in g("/v2/api/deals/history/open?kind=unpaid&deal=sale", M)["results"]] == ["5", "2", "1"], "open: sale only")
ck([x["id"] for x in g("/v2/api/deals/history/search?q=הגפן&deal=rent", M)["results"]] == ["4", "3"], "search: rent")
cm = g("/v2/api/deals/history/comps?q=הגפן&deal=rent", T)
ck(len(cm["results"]) == 2 and cm["n_sale"] == 0 and cm["n_rent"] == 2, cm)
print("OK", n, "checks")
