# tests/newborn/test_nb_plaindial.py — 'חייג' בנכס נולד בחיוג רגיל (מתג בניהול, 28/10).
# 04/11 (אייל): ברירת המחדל = חיוג רגיל לכולם; כיבוי = newbornPlainDial: False מפורש.
import os, sys, copy, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("WARMUP_ON_BOOT", "0")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)
import app as A

n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1

CFG = {"agents": [{"name": "דנה כהן", "phone": "521111111", "newbornPlainDial": True}, {"name": "יוסי לוי", "phone": "522222222"}, {"name": "רון כבוי", "phone": "523333333", "newbornPlainDial": False}]}
A._load_config = lambda: CFG
c = A.app.test_client()
def who(sess):
    A._web_auth = lambda: sess
    return c.get("/api/auth/whoami").get_json()
ck(who({"name": "דנה כהן", "role": "agent", "phone": "0521111111"})["nbPlainDial"] is True, "enabled agent")
ck(who({"name": "יוסי לוי", "role": "agent", "phone": "0522222222"})["nbPlainDial"] is True, "default on")
ck(who({"name": "רון כבוי", "role": "agent", "phone": "0523333333"})["nbPlainDial"] is False, "explicit off")
ck(who({"name": "חדש", "role": "agent", "phone": "0529999999"})["nbPlainDial"] is True, "no config entry = on")
ck(who({"name": "מנהל", "role": "admin", "phone": "0521111111"})["nbPlainDial"] is True, "found by phone")

saved = {}
def fake_mutate(fn):
    cfg = copy.deepcopy(CFG); fn(cfg); saved["cfg"] = cfg; return True, cfg
A._config_mutate = fake_mutate
A._log_activity = lambda *a, **k: None
A._web_auth = lambda: {"name": "אייל שמול", "role": "admin", "phone": "0505709865"}
r = c.post("/api/dev/agent_update", json={"name": "יוסי לוי", "newbornPlainDial": True}).get_json()
ck(r["ok"] and [a for a in saved["cfg"]["agents"] if a["name"] == "יוסי לוי"][0].get("newbornPlainDial") is None, "turn on (already default)")
r = c.post("/api/dev/agent_update", json={"name": "דנה כהן", "newbornPlainDial": False}).get_json()
ck([a for a in saved["cfg"]["agents"] if a["name"] == "דנה כהן"][0].get("newbornPlainDial") is False, "turn off = explicit False")
r = c.post("/api/dev/agent_update", json={"name": "רון כבוי", "newbornPlainDial": True}).get_json()
ck("newbornPlainDial" not in [a for a in saved["cfg"]["agents"] if a["name"] == "רון כבוי"][0], "turn on = default (removed)")
print("ok", n)
