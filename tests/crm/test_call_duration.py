# [DUR 12/11] משך שיחה מקובץ ה-WAV של ההקלטה
import os, sys, struct, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
import effie_v2 as E

def wav(secs, rate=8000, bps=2):
    data = b"\x00" * int(secs * rate * bps)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * bps, bps, 16)
    return b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data

assert abs(A._wav_secs(wav(95)) - 95) < 0.01
assert A._wav_secs(b"ID3" + b"\x00" * 100) is None
assert A._wav_secs(b"") is None

DUR = {}
CACHE = {}
A._cache_get = lambda k, ttl=None: CACHE.get(k)
A._cache_put = lambda k, v: CACHE.__setitem__(k, v)
A._cache_clear = lambda *a: CACHE.clear()
SH = [{"caller_phone": "0549572532", "agent_phone": "0505068814", "received_at": "2026-11-09T12:43:20Z", "_source_key": "mk:u-1"},
      {"caller_phone": "529125944", "agent_phone": "", "received_at": "2026-11-09T15:00:15Z", "_source_key": "mk:u-2"},
      {"caller_phone": "0501111111", "agent_phone": "", "received_at": "2026-11-09T16:00:00Z", "_source_key": "mk:u-3"}]
class FakeSB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return dict(DUR) if m == "calldur" else {}
    def crm_overrides_put_many(s, m, items, by=""): assert m == "calldur"; DUR.update(items); return len(items)
    def fetch_shadow(s, st, since, until=None): return SH
    def transcript_get(s, sk): return None
A._sbdb = FakeSB()
os.environ["MASKYOO_TOKEN_ZIPPER"] = "tz"
AUD = {"u-1": wav(125), "u-2": wav(7)}
class Resp:
    def __init__(s, body): s.status_code = 200; s.content = body; s.headers = {"Content-Type": "audio/wav" if body else "application/json"}
E._requests.get = lambda url, params=None, headers=None, timeout=None: Resp(AUD.get(params["call_uuid"], b'{"error":1}' + b" " * 80))
A._call_dur_run()
d = DUR
assert d["u-1"]["s"] == 125 and d["u-2"]["s"] == 7, d
assert d["u-3"]["s"] == -1, d          # שעות אחרי — בלי הקלטה, לא מנסים שוב
calls = []
E._requests.get = lambda *a, **k: calls.append(1)
A._call_dur_run(); assert not calls, "no refetch of known"

ROWS = [{"event_id": "", "status": "ANSWER", "agent": "דנה", "agent_phone": "0505068814", "caller_phone": "0549572532", "received_at": "2026-11-09T12:43:00.000Z"},
        {"event_id": "", "status": "CALL2CALL", "agent": "אייל", "agent_phone": "0505709865", "caller_phone": "0545544748",
         "c2c_src_caller": "529125944", "c2c_src_agent": "", "received_at": "2026-11-09T15:00:00.000Z"},
        {"event_id": "", "status": "ANSWER", "agent": "x", "caller_phone": "0501111111", "received_at": "2026-11-09T16:00:00.000Z"},
        {"event_id": "", "status": "ANSWER", "agent": "y", "caller_phone": "0502222222", "duration_sec": "61", "received_at": "2026-11-09T17:00:00.000Z"}]
A.web_fetch_raw = lambda *a, **k: ROWS
A._fetch_hidden_calls = lambda: set()
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
CACHE.clear()
c = A.app.test_client()
rows = c.get("/v2/api/crm/calls/list?size=50").get_json()["rows"]
by = {r["caller_phone"]: r["duration"] for r in rows}
assert by["0549572532"] == "2:05", by
assert by["0545544748"] == "0:07", by
assert by["0501111111"] == "", by
assert by["0502222222"] == "1:01", by
print("ok")
