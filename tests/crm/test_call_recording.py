# tests/crm/test_call_recording.py — [REC 10/11] הקלטת שיחה ממסקיו בכרטיס השיחה ב-CRM (ראוט אמיתי, מסקיו מזויף)
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["CRM_ALLOW_APP_TOKEN"] = "1"
os.environ.pop("MASKYOO_TOKEN_ZIPPER", None); os.environ.pop("MASKYOO_TOKEN_BISLANI", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
import effie_v2 as E
A._web_auth = lambda: {"phone": "505709865", "name": "אייל שמול", "role": "admin"}
A._is_dev = lambda p: True
ROWS = [{"event_id": "mk:abc-1", "status": "ANSWER", "agent": "דנה לוי", "agent_phone": "0505068814", "caller_phone": "0549572532",
         "received_at": "2026-11-09T12:43:00.000Z"},
        {"event_id": "e-old", "status": "ANSWER", "agent": "רועי", "caller_phone": "0523807638", "received_at": "2026-09-01T10:00:00.000Z"}]
A.web_fetch_raw = lambda *a, **k: ROWS
A._fetch_hidden_calls = lambda: set()
CACHE = {}
A._cache_get = lambda k, ttl=None: CACHE.get(k)
A._cache_put = lambda k, v: CACHE.__setitem__(k, v)
A._cache_clear = lambda *a: CACHE.clear()
LOG = []; A._log_activity = lambda *a: LOG.append(a)
class FakeSB:
    def enabled(s): return True
    def crm_overrides_fetch(s, m): return {}
    def transcript_get(s, sk): return {"transcript": "שלום", "recording_url": None} if sk == "mk:abc-1" else None
    def fetch_shadow(s, st, since, until=None): return []
A._sbdb = FakeSB()
c = A.app.test_client()

# בלי טוקן מסקיו — אין נגן
r = c.get("/v2/api/crm/calls/record?key=mk:abc-1").get_json()
ck(r["ok"] and r["recording"] == "", ("no token -> no player", r))

os.environ["MASKYOO_TOKEN_ZIPPER"] = "tz"; os.environ["MASKYOO_TOKEN_BISLANI"] = "tb"
r = c.get("/v2/api/crm/calls/record?key=mk:abc-1").get_json()
ck(r["recording"] == "/v2/api/crm/calls/audio?key=mk%3Aabc-1", r["recording"])
r2 = c.get("/v2/api/crm/calls/record?key=e-old").get_json()
ck(r2["recording"] == "", ("old call without uuid -> no player", r2))

WAV = b"RIFF" + b"\x00" * 200
CALLS = []
class Resp:
    def __init__(s, code, ct, body): s.status_code = code; s.headers = {"Content-Type": ct}; s.content = body
def fake_get(url, params=None, headers=None, timeout=None):
    CALLS.append((url, params.get("call_uuid"), headers["Authorization"]))
    if "zipper_993" in url:
        return Resp(200, "application/json", b'{"status":"error","message":"not found"}' + b" " * 80)
    return Resp(200, "audio/x-wav", WAV)
E._requests.get = fake_get

a = c.get("/v2/api/crm/calls/audio?key=mk:abc-1")
ck(a.status_code == 200 and a.data == WAV and a.mimetype.startswith("audio/"), (a.status_code, a.mimetype))
ck([x[0].split("/")[3] for x in CALLS] == ["zipper_993", "bislani_763"] and CALLS[1][1] == "abc-1" and CALLS[1][2] == "Bearer tb", CALLS)
ck(any("האזנה להקלטה" in str(x) for x in LOG), "listen logged")
p = c.get("/v2/api/crm/calls/audio?key=mk:abc-1", headers={"Range": "bytes=0-9"})
ck(p.status_code == 206 and p.data == WAV[:10] and p.headers["Content-Range"] == "bytes 0-9/%d" % len(WAV), (p.status_code, p.headers))
ck(len(CALLS) == 2, ("cached, no second fetch", CALLS))
ck(sum("האזנה להקלטה" in str(x) for x in LOG) == 1, "log throttled")
ck(c.get("/v2/api/crm/calls/audio?key=e-old").status_code == 404, "no uuid -> 404")
ck(c.get("/v2/api/crm/calls/audio?key=nope").status_code == 404, "unknown -> 404")

# מסקיו לא מחזירה אודיו בשום חשבון
E._requests.get = lambda *a, **k: Resp(200, "application/json", b'{"error":1}' + b" " * 80)
ROWS.append({"event_id": "mk:zzz", "status": "ANSWER", "agent": "דנה לוי", "caller_phone": "0501111111", "received_at": "2026-11-09T13:00:00.000Z"})
CACHE.clear()
nr = c.get("/v2/api/crm/calls/audio?key=mk:zzz")
ck(nr.status_code == 404 and nr.get_json()["reason"] == "no_recording", nr.data)

# בלי הרשאה
A._web_auth = lambda: None
ck(c.get("/v2/api/crm/calls/audio?key=mk:abc-1").status_code in (401, 403), "auth required")
print("ok", n)
