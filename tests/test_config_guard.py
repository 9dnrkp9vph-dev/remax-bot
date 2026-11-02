# tests/test_config_guard.py — הקונפיג לא נופל לעולם לגיליון הישן כשהמקור הוא Supabase (02/11)
# הבאג: קריאה שנכשלה ב-Supabase → נפילה לגיליון (קפוא מאוגוסט) → שמירה → setconfig →
# ה-Apps Script פיצל את הבלוב הישן ל-office_config ומחק כל מפתח חדש. אבדו הפגישות, השהיות ועוד.
import ast, os, threading

SRC = open(os.path.join(os.path.dirname(__file__), "..", "app.py"), encoding="utf-8").read()
tree = ast.parse(SRC)
WANT = ("_load_config", "_save_config", "_config_shrunk")


class Log:
    def __init__(self): self.lines = []
    def error(self, m): self.lines.append(m)
    warning = info = error


def build(sb_read=None, sb_fail_read=False, sb_fail_write=False):
    calls = {"apps": [], "saved": {}}

    class SB:
        def enabled(self): return True
        def fetch_config(self):
            if sb_fail_read: raise RuntimeError("supabase down")
            return dict(sb_read or {})
        def save_config_key(self, k, v):
            if sb_fail_write: raise RuntimeError("supabase down")
            calls["saved"][k] = v

    cache = {}
    ns = {"CONFIG_SOURCE": "supabase", "_sbdb": SB(), "_json": __import__("json"), "time": __import__("time"),
          "log": Log(), "_LAST_GOOD_CONFIG": None, "_CFG_BACKUP_MUTE_UNTIL": 0.0, "CONFIG_SHEET_BACKUP": False,
          "_CFG_DEGRADED": [False],
          "_cache_get": lambda k, t: cache.get(k), "_cache_put": lambda k, v: cache.__setitem__(k, v),
          "_cache_clear": lambda k: cache.pop(k, None),
          "_sf_lock": lambda k: threading.Lock(),
          "_buyers_apps_post": lambda a, p: (calls["apps"].append(a) or {"ok": True, "config": '{"old":1}'})}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANT:
            exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
    return ns, calls, cache


GOOD = {"agents": ["a"], "roles": {"1": "agent"}, "nbStatus": {str(i): {"status": "meeting"} for i in range(200)}}

# 1) קריאה תקינה — כמו קודם
ns, calls, _ = build(sb_read=GOOD)
assert ns["_load_config"]()["nbStatus"] == GOOD["nbStatus"]
assert calls["apps"] == []

# 2) קריאה נכשלת אחרי שהייתה תקינה → הקונפיג האחרון התקין, לא הגיליון
ns, calls, cache = build(sb_read=GOOD)
ns["_load_config"](); cache.clear()
ns["_sbdb"].fetch_config = lambda: (_ for _ in ()).throw(RuntimeError("down"))
c = ns["_load_config"]()
assert len(c["nbStatus"]) == 200 and calls["apps"] == [], calls

# 3) קריאה נכשלת מיד בעלייה → ריק + מצב 'פגוע', בלי גיליון; ושמירה נחסמת
ns, calls, _ = build(sb_fail_read=True)
assert ns["_load_config"]() == {}
assert "getconfig" not in calls["apps"], calls
assert ns["_save_config"]({"agents": ["a"], "nbStatus": {"x": {}}}) is False
assert calls["saved"] == {} and "setconfig" not in calls["apps"]

# 4) כתיבה נכשלת → לא נופלים ל-setconfig בגיליון
ns, calls, _ = build(sb_read=GOOD, sb_fail_write=True)
base = ns["_load_config"]()
cfg = dict(base, nbStatus=dict(base["nbStatus"], new={"status": "meeting"}))
assert ns["_save_config"](cfg) is False
assert "setconfig" not in calls["apps"], calls

# 5) שמירה רגילה של שינוי קטן — עוברת
ns, calls, _ = build(sb_read=GOOD)
base = ns["_load_config"]()
cfg = dict(base, nbStatus=dict(base["nbStatus"], new={"status": "meeting"}))
assert ns["_save_config"](cfg) is True and "nbStatus" in calls["saved"]

# 6) מחיקת פגישה אחת — עוברת
ns, calls, _ = build(sb_read=GOOD)
base = ns["_load_config"]()
nb = dict(base["nbStatus"]); nb.pop("5")
assert ns["_save_config"](dict(base, nbStatus=nb)) is True

# 7) כיווץ חריג (200 → 70 פגישות) — נחסם ונרשם בלוג
ns, calls, _ = build(sb_read=GOOD)
base = ns["_load_config"]()
small = {k: v for k, v in list(base["nbStatus"].items())[:70]}
assert ns["_save_config"](dict(base, nbStatus=small)) is False
assert calls["saved"] == {}
assert any("shrink" in l for l in ns["log"].lines), ns["log"].lines

print("ok 7")
