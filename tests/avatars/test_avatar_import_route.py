# tests/avatars/test_avatar_import_route.py — הראוט האמיתי של effie_v2 עם סביבה מזויפת
import sys, os, re, tempfile, base64
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
os.environ["MAP_CACHE_DIR"] = tempfile.mkdtemp()
from flask import Flask, request
class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None
import supabase_db as S
import effie_v2
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
saved, logs = {}, []
DB = {"505709865"}                      # לאייל כבר יש תמונה באפי
S.enabled = lambda: True
S.avatar_phones = lambda ps: {p for p in ps if p in DB | set(saved)}
S.avatar_save = lambda p, b64: saved.__setitem__(p, b64) or True
key = lambda s: re.sub(r"[\s'\"׳״.\-]", "", str(s or ""))
SES = {"D": {"phone": "505709865", "name": "אייל שמול", "role": "admin"}, "A": {"phone": "527245668", "name": "רפי", "role": "agent"}}
G = AutoG(_web_auth=lambda: SES.get(request.headers.get("X-Auth-Token", "")),
          _is_dev=lambda p: p == "505709865", _log_activity=lambda *a: logs.append(a), _canon_key=key,
          _load_config=lambda: {"removedAgents": ["סוכן שנמחק"]},
          web_contacts_phone_name=lambda: {"527245668": "רפי דה פיצ'וטו", "505709865": "אייל שמול",
                                           "541111111": "סוכן שנמחק", "542222222": "דנה חדשה"},
          web_phone_name_map=lambda: {"522265921": "רפי דה פיצוטו", "509999999": "eyal-shmul"})
app = Flask("t"); effie_v2.register(app, G); c = app.test_client()
U = "/v2/api/admin/avatars/import_site"
ck(c.post(U, json={}, headers={"X-Auth-Token": "A"}).status_code == 403, "agents can't run it")
j = c.post(U, json={"dry": True}, headers={"X-Auth-Token": "D"}).get_json()
ck(j["ok"] and j["dry"] and j["toImport"] == ["רפי דה פיצ'וטו"] or j["toImport"] == ["רפי דה פיצוטו"], j)
ck(j["has"] == ["אייל שמול"] and j["missing"] == ["דנה חדשה"] and not saved, j)
j = c.post(U, json={}, headers={"X-Auth-Token": "D"}).get_json()
ck(len(j["done"]) == 1 and set(saved) == {"527245668", "522265921"}, (j, list(saved)))
raw = open(os.path.join(ROOT, "site_photos", [x for x in __import__("json").load(open(os.path.join(ROOT, "site_photos", "index.json"), encoding="utf-8")) if x["name"] == "רפי דה פיצ'וטו"][0]["file"]), "rb").read()
ck(base64.b64decode(saved["527245668"]) == raw, "same bytes as the website (sha match)")
ck(c.get("/v2/api/avatar?p=527245668").data == raw, "served by Effie's avatar route")
ck(logs and "השלמת תמונות" in logs[-1][3], logs)
j = c.post(U, json={}, headers={"X-Auth-Token": "D"}).get_json()
ck(j["done"] == [] and len(j["has"]) == 2, "second run: nothing to do")
S.avatar_phones = lambda ps: None
ck(c.post(U, json={}, headers={"X-Auth-Token": "D"}).get_json()["reason"] == "avatars_lookup_failed", "lookup failure → no writes")
print("OK", n, "checks")
