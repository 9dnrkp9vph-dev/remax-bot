# tests/crm/test_promote.py — CRM שלב 1 (ביקורת): בניתוק — העברת שיחות מהצל ל-calls כדי שלא יאבדו בחלון ה-deploy
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
A._cache_clear = lambda *a: None
A._log_activity = lambda *a: None
class FakeSB:
    def __init__(s): s.calls = {}
    def enabled(s): return True
    def fetch_shadow(s, st, since):
        s.since = since
        return [dict(event_id="mk:u1", status="ANSWER", received_at="2026-10-31T08:00:00Z", _source_key="mk:u1", _received_at="2026-10-31T08:00:00+00:00"),
                dict(event_id="mk:u2", status="BUSY", received_at="2026-10-31T22:30:00Z", _source_key="mk:u2", _received_at="2026-10-31T22:30:00+00:00")]
    def call_upsert_direct(s, sk, iso, raw): s.calls[sk] = (iso, raw)
fs = FakeSB(); A._sbdb = fs
c = A.app.test_client()
j = c.post("/v2/api/crm/promote_calls", json={"since": "2026-10-31"}).get_json()
ck(j["ok"] and j["promoted"] == 2 and set(fs.calls) == {"mk:u1", "mk:u2"}, (j, fs.calls))
ck(fs.calls["mk:u2"][0] == "2026-11-01", "date column = Israel day")
ck("_source_key" not in fs.calls["mk:u1"][1], "internal keys stripped")
c.post("/v2/api/crm/promote_calls", json={"since": "2026-10-31"})
ck(len(fs.calls) == 2, "idempotent")
ck(c.post("/v2/api/crm/promote_calls", json={}).get_json()["reason"] == "since", "since required")
A._is_dev = lambda p: False
ck(c.post("/v2/api/crm/promote_calls", json={"since": "2026-10-31"}).status_code == 403, "dev only")
print("promote OK", n)
