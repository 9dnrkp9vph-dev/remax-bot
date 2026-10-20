# tests/crm/test_review_login_off.py — חשבון הביקורת של אפל כבוי (אייל 20/10 'לכבות עכשיו'): אין כניסה בקוד הקבוע,
# וגם סשן קיים (בזיכרון או טוקן חתום) של המספר נחסם. להחזרה: env APPLE_REVIEW_LOGIN=1.
import os, sys, warnings, time; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ.pop("APPLE_REVIEW_LOGIN", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
ck(A._BYPASS_LOGINS == {}, A._BYPASS_LOGINS)
c = A.app.test_client()
r = c.post("/api/auth/verify", json={"phone": "0501234567", "code": "1905"}).get_json()
ck(not r.get("ok"), ("fixed code no longer logs in", r))
A._web_sessions["T1"] = {"phone": "501234567", "name": "סוכן", "role": "agent", "exp": time.time() + 3600}
with A.app.test_request_context("/", headers={"X-Auth-Token": "T1"}):
    ck(A._web_auth() is None and "T1" not in A._web_sessions, "existing in-memory session blocked and dropped")
A._verify_token = lambda tok: "501234567" if tok == "SIGNED" else None
with A.app.test_request_context("/", headers={"X-Auth-Token": "SIGNED"}):
    ck(A._web_auth() is None, "signed token of the review phone blocked")
A._web_sessions["T2"] = {"phone": "541111111", "name": "רפי", "role": "agent", "exp": time.time() + 3600}
with A.app.test_request_context("/", headers={"X-Auth-Token": "T2"}):
    ck((A._web_auth() or {}).get("name") == "רפי", "regular agents unaffected")
ck(A._display_name_for("סוכן", "0501234567") == "חשבון בדיקה", "history still labeled")
print("review_login_off OK", n)
