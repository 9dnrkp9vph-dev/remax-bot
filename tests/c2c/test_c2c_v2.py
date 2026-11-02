# -*- coding: utf-8 -*-
"""click2call דרך create_maskyoo_call_v2 (02/11/2026): הסוכן מצלצל ראשון ואז הלקוח.
מריצים על הקוד האמיתי ב-app.py דרך חילוץ ast.   python3 tests/c2c/test_c2c_v2.py"""
import ast, sys, types, json, re, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(ROOT, "app.py")
SRC = open(APP, encoding="utf-8").read()
TREE = ast.parse(SRC)
V2 = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()


def _src(name):
    for n in TREE.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(SRC, n)
    raise AssertionError(f"function {name} not found in app.py")


def _load(names, G):
    for nm in names:
        exec(_src(nm), G)
    return G


fails = []
def check(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)


class R:
    def __init__(self, code, body): self.status_code = code; self._b = body; self.text = json.dumps(body)
    def json(self): return self._b


# ── 1. make_c2c_run — payload ל-Make כולל agent_phone ─────────────────────────
print("1. make_c2c_run")
calls = []
def post_ok(url, headers=None, json=None, timeout=None):
    calls.append({"url": url, "json": json}); return R(200, {"executionId": "x", "status": 1})
G = _load(["make_c2c_run"], {"requests": types.SimpleNamespace(post=post_ok), "json": json,
                             "log": types.SimpleNamespace(warning=lambda *a, **k: None),
                             "MAKE_API_TOKEN": "tok", "MAKE_ZONE": "eu1.make.com", "MAKE_C2C_SCENARIO": "7321077",
                             "C2C_FIRST_TARGET": "destination"})
mk = G["make_c2c_run"]
ok, msg, link = mk("052-9125944", "050-1234567", "050-5709865")
check(ok is True, "status 1 → מחייג")
d = calls[-1]["json"]["data"]
check(d.get("from_phone") == "052-9125944" and d.get("to_phone") == "050-1234567", "from/to נשלחים")
check(d.get("agent_phone") == "050-5709865", "agent_phone (הנייד של הסוכן) נשלח ל-Make")
check(d.get("first_target") == "destination" and "dial" not in d, "first_target מ-C2C_FIRST_TARGET (ברירת מחדל: הלקוח ראשון), בלי dial")
check(calls[-1]["json"].get("responsive") is True, "responsive")
ok, msg, link = mk("052-9125944", "050-1234567")
check(ok is True and calls[-1]["json"]["data"].get("agent_phone") == "", "בלי agent_phone → נשלח ריק (Make נופל לקו הווירטואלי)")
def post_err(url, **k): return R(200, {"executionId": "x", "status": 3, "error": {"message": "Maskyoo: error the maskyoo is either invalid or empty (קוד 3031)"}})
G["requests"] = types.SimpleNamespace(post=post_err)
ok, msg, link = mk("0501234567", "0525640615", "0505709865")
check(ok is False and "3031" in msg, "status 3 → הודעת השגיאה של Maskyoo מוחזרת")

# ── 2. api_click2call — הנייד של הסוכן ─────────────────────────────────────
print("2. api_click2call")
class Req:
    def __init__(self, body): self._b = body
    def get_json(self, silent=True): return self._b
acts = []
def build(session, body, agents, vphones=None):
    def entry(who):
        phones = set()
        if isinstance(who, dict):
            phones = {re.sub(r"\D", "", str(who.get("phone", "")))[-9:]}
            for ag in agents:
                if re.sub(r"\D", "", ag.get("phone", ""))[-9:] in phones: return ag
        nm = who if isinstance(who, str) else who.get("name", "")
        for ag in agents:
            if ag.get("name") == nm: return ag
        return None
    G4 = {"jsonify": lambda d: d, "request": Req(body), "_web_auth": lambda: session,
          "_vphone_for_name": lambda n: (vphones or {}).get(n, ""), "MAKE_API_TOKEN": "tok",
          "make_c2c_run": lambda f, t, a="": (acts.append(("mk", f, t, a)) or (True, "call in progress", "")),
          "_c2c_enabled_for": lambda w: True, "_c2c_agent_entry": entry,
          "_log_activity": lambda *a: acts.append(("log",) + a),
          "log": types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
          "C2C_PILOT": "", "_last9": lambda p: re.sub(r"\D", "", str(p or ""))[-9:]}
    _load(["api_click2call"], G4)
    return G4["api_click2call"]()
def _r(x): return x if isinstance(x, tuple) else (x, 200)
AG = [{"name": "אוצר בן חמו", "phone": "052-1111111", "vphone": "052-9706880"},
      {"name": "רפי", "phone": "052-7245668", "vphone": "052-9120222"}]
acts.clear()
r, code = _r(build({"role": "coordinator", "name": "מנהל", "phone": "521111111"}, {"to": "0501234567"}, AG))
check(code == 200 and r.get("ok") is True, "סוכן מזוהה לפי טלפון → ok")
check(("mk", "052-9706880", "0501234567", "052-1111111") in acts, "Make מקבל: הקו הווירטואלי, הלקוח, והנייד של הסוכן מרשומת הצוות")
acts.clear()
r, code = _r(build({"role": "agent", "name": "סוכנת", "phone": "0509999999"}, {"to": "0501234567"}, [], {"סוכנת": "052-9000000"}))
check(("mk", "052-9000000", "0501234567", "0509999999") in acts, "בלי רשומת צוות → הנייד = טלפון הסשן")
acts.clear()
r, code = _r(build({"role": "admin", "name": "מנהל", "phone": "505709865"}, {"to": "0501234567", "as": "רפי"}, AG))
check(("mk", "052-9120222", "0501234567", "052-7245668") in acts, "מנהל ב'צפה כסוכן' → הקו והנייד של הסוכן הנבחר (לא של המנהל)")
acts.clear()
r, code = _r(build({"role": "admin", "name": "מנהל", "phone": "505709865"}, {"to": "0501234567", "as": "סוכן בלי טלפון"},
                   [{"name": "סוכן בלי טלפון", "phone": "", "vphone": "052-9000001"}]))
check(r.get("ok") is False and "נייד" in (r.get("error") or ""), "כסוכן בלי נייד ברשומה → שגיאה ברורה, לא מצלצלים למנהל")
check(not any(a[0] == "mk" for a in acts), "ולא נקרא Make")

# ── 3. טקסטים בקליינט — הסוכן ראשון ─────────────────────────────────────────
print("3. effie_v2 texts")
check(V2.count("הטלפון שלך יצלצל ראשון, ואז הלקוח") >= 2, "toast + גיליון חיוג: 'הטלפון שלך יצלצל ראשון, ואז הלקוח'")

# ── 4. קישור click2call_link ישן בסיכום לא משמש יותר ל'חייג חזרה' ────────────
print("4. dead click2call_link callback")
check('if "click2call_link" in callback: callback = ""' in SRC, "השרת מנקה callback של click2call_link (חייג חזרה → c2cDial)")

print("\nRESULT:", "ALL GREEN" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
