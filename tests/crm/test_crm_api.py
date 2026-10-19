# tests/crm/test_crm_api.py — ה-API של מסכי ה-CRM (ראוט אמיתי, מקורות מזויפים)
import os, sys, warnings, json; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
ROWS = [{"event_id": "e1", "status": "ANSWER", "agent": "דנה לוי", "agent_phone": "0505068814", "caller_phone": "0549572532",
         "transcript_summary": "מחפש 4 חדרים", "received_at": "2026-10-19T12:43:00.000Z"},
        {"event_id": "e2", "status": "NOANSWER", "agent": "רועי", "caller_phone": "0523807638", "received_at": "2026-10-19T10:00:00.000Z"}]
A.web_fetch_raw = lambda *a, **k: ROWS
HID = set(); WRITES = []; LOG = []
A._fetch_hidden_calls = lambda: set(HID)
def hw(op, eid):
    WRITES.append((op, eid)); (HID.add if op == "hidecall" else HID.discard)(eid); return {"ok": True}
A._hidden_write = hw
CACHE = {}
A._cache_get = lambda k, ttl=None: CACHE.get(k)
A._cache_put = lambda k, v: CACHE.__setitem__(k, v)
A._cache_clear = lambda *a: [CACHE.pop(k, None) for k in list(CACHE) if not a or any(str(k).startswith(x) for x in a)]
A._log_activity = lambda *a: LOG.append(a)
class FakeSB:
    def __init__(s): s.ov = {}; s.calls = {}; s.ovreads = 0; s.shadow_args = []
    def enabled(s): return True
    def crm_overrides_fetch(s, m): s.ovreads += 1; return {k: dict(v) for k, v in s.ov.items()}
    def crm_override_upsert(s, m, k, f, by): s.ov.setdefault(k, {}).update(f); return s.ov[k]
    def transcript_get(s, sk): return {"transcript": "שלום, כאן דנה", "recording_url": None} if sk == "mk:u1" else None
    def fetch_shadow(s, st, since, until=None): s.shadow_args.append((since, until)); return [{"caller_phone": "549572532", "agent_phone": "505068814", "received_at": "2026-10-19T12:44:00Z", "_source_key": "mk:u1"}]
    def call_upsert_direct(s, sk, iso, raw): s.calls[sk] = raw; return True
sb = FakeSB(); A._sbdb = sb
c = A.app.test_client()
m = c.get("/v2/api/crm/calls/meta").get_json()
ck(m["ok"] and m["title"] == "לוג שיחות" and [v[0] for v in m["views"]][:2] == ["all", "today"] and m["columns"][0][0] == "agent", m)
ck(m["counts"]["all"] == 2, m["counts"])
j = c.get("/v2/api/crm/calls/list?q=דנה").get_json()
ck(j["total"] == 1 and j["rows"][0]["key"] == "e1", j)
r = c.get("/v2/api/crm/calls/record?key=e1").get_json()
ck(sb.shadow_args and sb.shadow_args[-1][1] is not None, ("bounded shadow lookup", sb.shadow_args))
ck(r["ok"] and r["record"]["agent"] == "דנה לוי" and r["transcript"] == "שלום, כאן דנה", ("transcript matched via shadow call", r))
ck(c.post("/v2/api/crm/calls/record", json={"key": "e1", "fields": {"agent": "דנה כהן", "bogus": "x"}}).get_json()["ok"], "edit")
ck(sb.ov["e1"] == {"agent": "דנה כהן"}, ("only editable fields", sb.ov))
ck(c.get("/v2/api/crm/calls/list?q=כהן").get_json()["total"] == 1, "edit visible")
_r0 = sb.ovreads; c.get("/v2/api/crm/calls/list"); c.get("/v2/api/crm/calls/list?q=x")
ck(sb.ovreads == _r0, ("overrides cached between requests", sb.ovreads, _r0))
ck(c.post("/v2/api/crm/calls/record", json={"key": "e2", "delete": True}).get_json()["ok"] and ("hidecall", "e2") in WRITES, "delete = hide")
ck(c.get("/v2/api/crm/calls/list").get_json()["total"] == 1, "hidden gone")
ck(c.post("/v2/api/crm/calls/record", json={"key": "e2", "restore": True}).get_json()["ok"] and ("unhidecall", "e2") in WRITES, "restore")
nj = c.post("/v2/api/crm/calls/record", json={"fields": {"agent": "חדש", "caller_phone": "0501234567", "status": "ANSWER", "summary": "ידני"}}).get_json()
ck(nj["ok"] and nj["key"].startswith("crm:") and sb.calls[nj["key"]]["agent"] == "חדש", (nj, sb.calls))
ck(sb.calls[nj["key"]].get("manual") == "1", "manual marker")
ck(len(LOG) >= 4, "activity logged")
x = c.get("/v2/api/crm/calls/export?q=דנה")
ck(x.status_code == 200 and x.data.startswith(b"\xef\xbb\xbf") and "csv" in x.content_type, x.content_type)
A._config_mutate = lambda fn: fn(CFG)
CFG = {}
A._load_config = lambda: CFG
ck(c.post("/v2/api/crm/views?module=calls", json={"name": "דנה היום", "q": "דנה", "view": "today"}).get_json()["ok"], "save view")
ck(c.get("/v2/api/crm/views?module=calls").get_json()["views"][0]["name"] == "דנה היום", "list views")
ck(c.get("/v2/api/crm/nope/meta").status_code == 404, "unknown module")
A._is_dev = lambda p: False
ck(c.get("/v2/api/crm/calls/list").status_code == 403, "dev only")
print("crm_api OK", n)
