# tests/crm/test_calls_ingest.py — CRM שלב 1: supabase_db (requests מזויף) + הראוט האמיתי /v2/api/calls/ingest
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)
n = 0
def ck(c, m):
    global n; assert c, m; n += 1

# ── חלק א: supabase_db ──
import supabase_db as S
class R:
    def __init__(s, j=None): s._j = j if j is not None else []; s.status_code = 201
    def raise_for_status(s): pass
    def json(s): return s._j
sent = []
def fpost(url, headers=None, params=None, json=None, timeout=None):
    sent.append((url.rsplit("/", 1)[-1], params, json, headers)); return R()
S.requests.post = fpost
S.SB_OFFICE_ID = "off"
ck(S.shadow_upsert("calls", "mk:u1", "2026-10-18", {"a": 1}), "shadow ok")
t, p, j, h = sent[-1]
ck(t == "ingest_shadow" and p["on_conflict"] == "office_id,stream,source_key" and "merge-duplicates" in h["Prefer"], sent[-1])
ck(j[0]["stream"] == "calls" and j[0]["source_key"] == "mk:u1" and j[0]["office_id"] == "off" and j[0]["raw"] == {"a": 1}, j)
sent.clear()
ck(S.transcript_upsert("mk:u1", "mk:u1", "", "") is False and not sent, "no empty transcript row")
ck(S.transcript_upsert("mk:u1", "mk:u1", "שלום", "") and sent[-1][0] == "call_transcripts"
   and sent[-1][1]["on_conflict"] == "office_id,source_key" and sent[-1][2][0]["transcript"] == "שלום", sent)
raw = {"event_id": "mk:u1", "status": "ANSWER", "agent": "א", "agent_phone": "1", "caller_phone": "2",
       "duration_sec": "30", "transcript_summary": "s", "received_at": "18/10/2026 17:08"}
ck(S.call_upsert_direct("mk:u1", "2026-10-18", raw), "direct")
t, p, j, h = sent[-1]
ck(t == "calls" and p["on_conflict"] == "office_id,source_key" and j[0]["received_at"] == "2026-10-18"
   and j[0]["status"] == "ANSWER" and j[0]["transcript_summary"] == "s" and j[0]["raw"] == raw, j)

# ── חלק ב: הראוט ──
os.environ["CALLS_INGEST_KEY"] = "k1"
import app as A
class FakeSB:
    def __init__(s): s.shadow, s.calls, s.tr = {}, {}, {}
    def enabled(s): return True
    def shadow_upsert(s, st, sk, iso, raw): s.shadow[(st, sk)] = raw; return True
    def call_upsert_direct(s, sk, iso, raw): s.calls[sk] = raw; return True
    def transcript_upsert(s, sk, eid, tr, rec):
        if not (tr or rec): return False
        s.tr[sk] = tr; return True
fs = FakeSB(); A._sbdb = fs
logs = []; A._log_activity = lambda *a: logs.append(a); A._cache_clear = lambda *a: None
c = A.app.test_client()
body = {"call_uuid": "u1", "callstatus": "ANSWER", "agent": "אלי שמול", "created": "18/10/2026 17:08", "summary": "s", "transcript": "t"}
ck(c.post("/v2/api/calls/ingest", json=body, headers={"X-Ingest-Key": "bad"}).status_code == 403, "bad key")
ck(c.post("/v2/api/calls/ingest", json=body).status_code == 403, "no key")
H = {"X-Ingest-Key": "k1"}
os.environ.pop("CALLS_DIRECT", None)
j = c.post("/v2/api/calls/ingest", json=body, headers=H).get_json()
ck(j["ok"] and j["mode"] == "shadow" and j["source_key"] == "mk:u1", j)
ck(len(fs.shadow) == 1 and not fs.calls and fs.tr == {"mk:u1": "t"} and not logs, (fs.shadow, fs.calls, logs))
c.post("/v2/api/calls/ingest", json=body, headers=H)
ck(len(fs.shadow) == 1, "retry → same key")
os.environ["CALLS_DIRECT"] = "live"
j = c.post("/v2/api/calls/ingest", json=body, headers=H).get_json()
ck(j["mode"] == "live" and "mk:u1" in fs.calls and len(fs.shadow) == 1 and logs, (j, logs))
ck(c.post("/v2/api/calls/ingest", json={"callstatus": "x"}, headers=H).get_json()["reason"] == "empty", "no uuid")
ck(c.post("/v2/api/calls/ingest", json={"call_uuid": "n", "transcript": ""}, headers=H).get_json()["ok"] and "mk:n" not in fs.tr, "no empty tr")
ck(A.app.view_functions[[r.endpoint for r in A.app.url_map.iter_rules() if r.rule == "/v2/api/calls/ingest"][0]].__name__ == "v2_api_calls_ingest", "route bound")
print("calls_ingest OK", n)
