"""15/11 (אייל, צילום החייגן של נחמי זקס: 'למה מופיעים כולם?') — סוכן רגיל רואה ברשימה רק את עצמו.
python3 tests/dialer/test_dialer_self.py"""
import os, sys, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask
import dialer as D

fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None

ROSTER = {"נחמי זקס": "0501111111", "רויטל גל": "0502222222", "רון בורנשטיין": "0503333333"}

def queue(sess, cfg_extra=None, coords=None):
    D._CACHE.update(t=0, v=None)
    cfg = {"nbStatus": {}, "v2_dialer_users": ["נחמי זקס"]}
    cfg.update(cfg_extra or {})
    G = AutoG(log=None, _web_auth=lambda: sess,
              _load_config=lambda: cfg, _config_mutate=lambda fn: (fn(cfg), (True, None))[1],
              _display_name_for=lambda n, p: n, _canon_key=lambda n: " ".join(str(n or "").split()),
              _canon_agent_name=lambda n: n, _last9=lambda p: re.sub(r"\D", "", str(p or ""))[-9:],
              _coordinators_all=lambda: coords or {}, _is_dev=lambda p: False,
              _phones_for_name=lambda n: {ROSTER.get(n, "")} - {""},
              fetch_newborn=lambda: [], fetch_sheet_rows=lambda: [], _fetch_manual_buyers=lambda: [],
              fetch_agents_phones=lambda: dict(ROSTER), web_phone_name_map=lambda: {},
              web_contacts_phone_name=lambda: {}, _price_dropped_map=lambda: {}, _fetch_newborn_contacts=lambda: {},
              _famexcl_addr_list=lambda: {}, _office_name=lambda: "המשרד", _c2c_agent_entry=lambda s: None)
    app = Flask(__name__); D.register(app, G)
    j = app.test_client().get("/v2/api/dialer/queue").get_json() or {}
    return [a["name"] for a in j.get("agents") or []]

agent = {"name": "נחמי זקס", "role": "agent", "drole": "agent", "phone": "501111111"}
check(queue(agent) == ["נחמי זקס"], "סוכנת שנבחרה לחייגן — רק היא ברשימה")
mgr = {"name": "נחמי זקס", "role": "admin", "drole": "manager", "phone": "501111111"}
check(len(queue(mgr)) == 3, "מנהלת שנבחרה — כל הסוכנים (כמו קודם)")
coord = {"name": "נחמי זקס", "role": "coordinator", "drole": "coordinator", "phone": "501111111"}
check(len(queue(coord)) == 3, "מתאמת — כל הסוכנים (הצוות שלה קודם)")
check(len(queue(agent, {"coordinators": [{"coordinator": "נחמי זקס"}]})) == 3, "סוכנת שמוגדרת מתאמת במסך המתאמות — כולם")
dev = {"name": "אייל", "role": "admin", "drole": "developer", "phone": "505709865", "dev": True}
check(len(queue(dev)) == 3, "בעל המשרד — כולם")

print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
