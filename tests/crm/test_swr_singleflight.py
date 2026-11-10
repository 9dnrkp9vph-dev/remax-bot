# tests/crm/test_swr_singleflight.py — [10/11] אחרי פריסה ה-warmer ובקשות בנו את אותו מפתח במקביל
# (לוח הבקרה נתקע 60ש'+). עכשיו בנייה קרה של מפתח רצה פעם אחת, והשאר מחכים לתוצאה.
import os, sys, time, threading, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ["DISABLE_WARMER"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
calls = []
def build():
    calls.append(1); time.sleep(0.5); return {"v": len(calls)}
A._cache_clear("sftest")
out = []
ts = [threading.Thread(target=lambda: out.append(A._swr("sftest", 60, build))) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
ck(len(calls) == 1, ("one cold build for concurrent callers", len(calls)))
ck(len(out) == 4 and all(o == {"v": 1} for o in out), out)
# כשל בבנייה לא משאיר את המפתח נעול
A._cache_clear("sftest2")
def bad(): raise RuntimeError("x")
try:
    A._swr("sftest2", 60, bad)
except RuntimeError:
    pass
ck(A._swr("sftest2", 60, lambda: 7) == 7, "key usable after failed build")
print("swr_singleflight OK", n)
