# tests/goals/test_weekly_run.py — [GOALS-WEEKLY 29/10] הריצה המתוזמנת עם G מזויף: למי נשלח, פעם אחת, ניסיון חוזר,
# סיכום למנהל, יומן, כיבוי ב-env, חג/השתקה. python3 tests/goals/test_weekly_run.py
import os, sys, copy, tempfile, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from zoneinfo import ZoneInfo
import goals as g

IL = ZoneInfo("Asia/Jerusalem")
N = [0]
def ck(c, m=""):
    assert c, m
    N[0] += 1

def at(y, mo, d, h=10, mi=5):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IL).timestamp()

def make_G(fail_to=(), quiet=False):
    cfg = {"v2_office": {"name": "המשרד שלנו"}, "nbStatus": {}, "v2_goals": {}}
    sent, logs = [], []
    def send_text(to, text):
        sent.append((to, text))
        return to not in fail_to
    def mutate(fn):
        c = copy.deepcopy(cfg); r = fn(c); cfg.clear(); cfg.update(c); return True, r
    G = {"_load_config": lambda: cfg, "_config_mutate": mutate, "send_text": send_text,
         "_log_activity": lambda *a: logs.append(a), "_d360_on": lambda: True, "_quiet_mode": lambda: quiet,
         "_switch_off": lambda n: False,
         "fetch_agents_phones": lambda: {"דנה כהן": "050-1111111", "רון לוי": "0522222222", "מזכירה": "0533333333"},
         "_agent_vphones9": lambda: {"522222222"},
         "_wa_phone": lambda p: "972" + "".join(ch for ch in str(p) if ch.isdigit())[-9:],
         "_last9": lambda p: "".join(ch for ch in str(p) if ch.isdigit())[-9:],
         "_canon_key": lambda n: " ".join(str(n or "").split()), "_canon_agent_name": lambda n: n,
         "_fetch_manual_buyers": lambda: [], "_activity_fetch": lambda t0, today=False: [], "_sbdb": None,
         "_DEV_PHONES_RAW": ["0505709865"], "log": None}
    return G, cfg, sent, logs

src_override = {"roster": ["דנה כהן", "רון לוי", "שקט"], "seen": ["דנה כהן", "רון לוי", "מזכירה"],
                "reviews": [], "bpages": [], "missed": []}
tmp = tempfile.mkdtemp()
SUN = at(2026, 11, 1)            # ראשון 10:05

# ── שליחה רגילה ─────────────────────────────────────────────────────────────
G, cfg, sent, logs = make_G()
os.environ.pop("GOALS_WEEKLY_WA", None)
r = g.weekly_run(G, SUN, os.path.join(tmp, "a.json"), src_override=src_override)
to = [t for t, _ in sent]
ck("972501111111" in to, to)
ck("972522222222" not in to, "vphone never")                     # רון — רק מספר מרכזיה
ck("972505709865" in to and to[-1] == "972505709865", "manager summary last")
ck(len(to) == 2, to)                                              # דנה + מנהל
st = cfg["v2_goals_weekly"]["2026-10-25"]
ck(st["agents"]["דנה כהן"]["r"] == "sent" and st["agents"]["רון לוי"]["r"] == "no_phone", st)
ck(st.get("done") and st.get("mgr", {}).get("r") == "sent", st)
ck(any("סיכום יעדים שבועי" in str(a) for a in logs), logs)
ck("שלום דנה" in sent[0][1] and "/v2/goals" in sent[0][1], sent[0][1])

# פעם אחת בשבוע — גם אם הקונפיג נמחק (העותק בדיסק)
sent.clear()
g.weekly_run(G, SUN + 3600, os.path.join(tmp, "a.json"), src_override=src_override)
ck(sent == [], "once a week")
cfg.pop("v2_goals_weekly")
g.weekly_run(G, SUN + 7200, os.path.join(tmp, "a.json"), src_override=src_override)
ck(sent == [], "disk copy guards a wiped config")

# ── כשל → ניסיון חוזר אחרי 15 דק' ──────────────────────────────────────────
G, cfg, sent, logs = make_G(fail_to=("972501111111",))
p = os.path.join(tmp, "b.json")
g.weekly_run(G, SUN, p, src_override=src_override)
ck(not cfg["v2_goals_weekly"]["2026-10-25"].get("done"), "not done after failure")
n1 = len(sent)
g.weekly_run(G, SUN + 60, p, src_override=src_override)
ck(len(sent) == n1, "waits 15 min")
g.weekly_run(G, SUN + 1000, p, src_override=src_override)
ck(len(sent) == n1 + 1 and sent[-1][0] == "972501111111", sent[-1])

# ── חג / השתקה / כיבוי / לפני 10:00 ────────────────────────────────────────
G, cfg, sent, logs = make_G(quiet=True)
g.weekly_run(G, SUN, os.path.join(tmp, "c.json"), src_override=src_override)
ck(sent == [], "quiet / holiday")
G, cfg, sent, logs = make_G()
g.weekly_run(G, at(2026, 11, 1, 9, 30), os.path.join(tmp, "d.json"), src_override=src_override)
ck(sent == [], "before 10")
os.environ["GOALS_WEEKLY_WA"] = "0"
g.weekly_run(G, SUN, os.path.join(tmp, "d.json"), src_override=src_override)
ck(sent == [], "env off")
os.environ.pop("GOALS_WEEKLY_WA")
# [GOALS4] יום שני רגיל — לא שולחים 'השלמה' (אייל: רק בימי ראשון)
G, cfg, sent, logs = make_G()
g.weekly_run(G, at(2026, 11, 2, 10, 30), os.path.join(tmp, "e0.json"), src_override=src_override)
ck(sent == [], "Monday after a normal Sunday — nothing")
# יום ראשון חג → שני
G, cfg, sent, logs = make_G()
G["_shabbat_windows"] = lambda ev: []
G["_in_shabbat_window"] = lambda d, w: d.date() == dt.date(2026, 11, 1)
g.weekly_run(G, at(2026, 11, 2, 10, 30), os.path.join(tmp, "e.json"), src_override=src_override)
ck(any(t == "972501111111" for t, _ in sent), "Monday after holiday")

# ── תצוגה מקדימה: בלי שליחה ובלי רישום ─────────────────────────────────────
G, cfg, sent, logs = make_G()
pv = g.weekly_preview(G, SUN, src_override=src_override)
ck(sent == [] and "v2_goals_weekly" not in cfg, "preview sends nothing")
ck([m["name"] for m in pv["messages"]] == ["דנה כהן", "רון לוי"], pv["messages"])
ck(pv["messages"][0]["phone"] == "972501111111" and pv["messages"][1]["phone"] == "", pv["messages"])
ck("סיכום יעדים שבועי" in pv["manager"] and pv["week"] == "2026-10-25", pv)
print("weekly run ok", N[0])

# ── ראוט התצוגה המקדימה: מנהלים בלבד ────────────────────────────────────────
try:
    import flask
except ImportError:
    flask = None
if flask:
    app = flask.Flask("t")
    G, cfg, sent, logs = make_G()
    who = {"s": None}
    G["_web_auth"] = lambda: who["s"]
    G["_usage_rows"] = lambda start: [{"name": "דנה כהן"}]
    G["_contacts_rows"] = lambda: []
    g.register_weekly(app, G)
    c = app.test_client()
    ck(c.get("/v2/api/goals/weekly/preview").status_code == 403, "no auth")
    who["s"] = {"name": "x", "drole": "agent"}
    ck(c.get("/v2/api/goals/weekly/preview").status_code == 403, "agent forbidden")
    ck(c.get("/v2/goals/weekly").status_code == 200, "page")
    ck(sent == [], "routes never send")
    print("weekly routes ok", N[0])
