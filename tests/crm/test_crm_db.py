# tests/crm/test_crm_db.py — supabase_db: שכבת העריכות של ה-CRM + קריאת תמלול (requests מזויף)
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
GET, POST = [], []
DB = {"crm_overrides": [{"record_key": "e1", "fields": {"agent": "דנה"}}],
      "call_transcripts": [{"source_key": "mk:u1", "transcript": "שלום", "recording_url": None}]}
def fget(url, headers=None, params=None, timeout=None):
    t = url.rsplit("/", 1)[-1]; GET.append((t, params)); return R(DB.get(t, []) if int((params or {}).get("offset", 0)) == 0 else [])
def fpost(url, headers=None, params=None, json=None, timeout=None):
    POST.append((url.rsplit("/", 1)[-1], params, json, headers)); return R()
S.requests.get, S.requests.post = fget, fpost
ck(S.crm_overrides_fetch("calls") == {"e1": {"agent": "דנה"}}, "fetch")
ck(GET[-1][1]["module"] == "eq.calls", GET[-1])
S.crm_override_upsert("calls", "e1", {"status": "ANSWER"}, "אייל")
t, p, j, h = POST[-1]
ck(t == "crm_overrides" and p["on_conflict"] == "office_id,module,record_key" and "merge-duplicates" in h["Prefer"], POST[-1])
ck(j[0]["fields"] == {"agent": "דנה", "status": "ANSWER"} and j[0]["updated_by"] == "אייל", ("merged with existing", j))
ck(S.transcript_get("mk:u1")["transcript"] == "שלום" and GET[-1][1]["source_key"] == "eq.mk:u1", GET[-1])
DB["call_transcripts"] = []
ck(S.transcript_get("nope") is None, "missing")
print("crm_db OK", n)
