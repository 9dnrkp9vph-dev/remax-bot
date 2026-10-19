# tests/crm/test_signdoc_headers.py — כותרות מסמכי חתימה לפי טוקן (עמודת token בטבלת sign_docs), במנות
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import supabase_db as S
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
calls = []
class R:
    def __init__(s, toks): s.toks = toks
    def raise_for_status(s): pass
    def json(s): return [{"token": t, "header": "H:" + t} for t in s.toks if t != "missing00"]
def get(url, headers=None, params=None, timeout=None):
    calls.append((url, params))
    return R(params["token"][4:-1].split(","))
S.requests.get = get
toks = ["tok%05d" % i for i in range(150)] + ["missing00", "bad'tok"]
out = S.signdoc_headers(toks)
ck(len(calls) == 2 and calls[0][0].endswith("/sign_docs") and calls[0][1]["select"] == "token,header", calls[0])
ck(out["tok00007"] == "H:tok00007" and out["missing00"] == "" and "bad'tok" not in out, ("batched, missing = empty, unsafe token skipped", len(out)))
print("signdoc_headers OK", n)
