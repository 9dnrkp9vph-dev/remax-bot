# tests/goals/test_monthly.py — [GOALS-MONTHLY 29/10] סיכום חודשי לכל סוכן + לבעל המשרד (אייל).
# החלטות: שתי הודעות נפרדות ביום ראשון המשותף (החודשי אחרי השבועי); לבעל המשרד הודעה קצרה + קישור לעמוד.
# python3 tests/goals/test_monthly.py
import os, sys, copy, tempfile, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from zoneinfo import ZoneInfo
import goals as g

IL = ZoneInfo("Asia/Jerusalem")
canon = lambda n: " ".join(str(n or "").split())
N = [0]
def ck(c, m=""):
    assert c, m
    N[0] += 1

def at(y, mo, d, h=10, mi=25):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IL)

# ── התקופה ומתי ───────────────────────────────────────────────────────────────
ck(g.month_period(dt.date(2026, 11, 1)) == (dt.date(2026, 10, 1), dt.date(2026, 10, 31)), "Oct")
ck(g.month_period(dt.date(2026, 1, 4)) == (dt.date(2025, 12, 1), dt.date(2025, 12, 31)), "Dec across year")
ck(g.first_sunday(dt.date(2026, 11, 1)) == dt.date(2026, 11, 1), "Nov 1 2026 is Sunday")
ck(g.first_sunday(dt.date(2026, 12, 1)) == dt.date(2026, 12, 6), "Dec 2026 → 6/12")
ck(g.monthly_due(at(2026, 11, 1), False, {}) == "2026-10", "first Sunday 10:25")
ck(g.monthly_due(at(2026, 11, 1, 10, 5), False, {}) is None, "after the weekly (10:20)")
ck(g.monthly_due(at(2026, 11, 1), True, {}) is None, "holiday / quiet")
ck(g.monthly_due(at(2026, 11, 2), False, {}) == "2026-10", "holiday Sunday → Monday")
ck(g.monthly_due(at(2026, 11, 6), False, {}) is None, "not Friday")
ck(g.monthly_due(at(2026, 11, 8), False, {}) is None, "not the second Sunday")
ck(g.monthly_due(at(2026, 11, 1), False, {"2026-10": {"done": True}}) is None, "once a month")
ck(g.monthly_due(at(2026, 12, 6), False, {}) == "2026-11", "Dec 6 → November")
ck(g.monthly_due(at(2026, 12, 1), False, {}) is None, "Tuesday 1/12 — before the first Sunday")

# ── יעד חודשי ────────────────────────────────────────────────────────────────
ck(g.month_scale(dt.date(2026, 10, 1), dt.date(2026, 10, 31)) == 23.5, g.month_scale(dt.date(2026, 10, 1), dt.date(2026, 10, 31)))
ck(g.month_weeks(dt.date(2026, 10, 1), dt.date(2026, 10, 31)) == 4.4, g.month_weeks(dt.date(2026, 10, 1), dt.date(2026, 10, 31)))
ck(g.month_label(dt.date(2026, 10, 1)) == "אוקטובר 2026", g.month_label(dt.date(2026, 10, 1)))

# ── בנייה ────────────────────────────────────────────────────────────────────
def ts(y, mo, d, h=11):
    return dt.datetime(y, mo, d, h, tzinfo=IL).timestamp()
nb = {"a": {"agent": "דנה כהן", "status": "meeting", "meeting_at": ts(2026, 10, 5), "pkey": "1"},
      "b": {"agent": "דנה כהן", "status": "meeting", "meeting_at": ts(2026, 10, 29), "pkey": "2"},
      "c": {"agent": "דנה כהן", "status": "meeting", "meeting_at": ts(2026, 9, 10), "pkey": "3"},      # חודש קודם
      "d": {"agent": "דנה כהן", "status": "meeting", "meeting_at": ts(2026, 11, 1), "pkey": "4"}}      # לא בחודש
sigs = [{"agent": "דנה כהן", "address": "הרצל 5, חיפה", "type": "בלעדיות", "signed": True, "ts": ts(2026, 10, 3)},
        {"agent": "דנה כהן", "address": "הרצל 9, חיפה", "type": "בלעדיות", "signed": True, "ts": ts(2026, 10, 28)},
        {"agent": "דנה כהן", "address": "בגין 1", "type": "בלעדיות", "signed": True, "ts": ts(2026, 9, 28)}]
buyers = [{"agent": "דנה כהן", "date": "06/10/2026 10:00", "summary": "מהחתמת מתעניין"},
          {"agent": "דנה כהן", "date": "07/10/2026 10:00"}]
src = {"nb": nb, "sigs": sigs, "buyers": buyers, "bpages": [], "activity": [], "reviews": [], "missed": [],
       "roster": ["דנה כהן", "רון לוי", "יוסי ישן"], "seen": ["דנה כהן", "רון לוי"],
       "seen_month": ["דנה כהן"], "cfg": {}}
M = g.build_monthly(src, dt.date(2026, 10, 1), dt.date(2026, 10, 31), canon)
rows = M["rows"]
ck([r["name"] for r in rows] == ["דנה כהן", "רון לוי"], [r["name"] for r in rows])
d = rows[0]
ck(d["counts"]["meetings"] == 2 and d["prev"]["meetings"] == 1, (d["counts"], d["prev"]))
ck(d["counts"]["listings"] == 2 and d["prev"]["listings"] == 1, "listings over the whole month")
ck(d["targets"]["meetings"] == 47 and d["targets"]["listings"] == 8.8 and d["targets"]["nb_wa"] == 235, d["targets"])
ck(d["counts"]["buyers"] == 2 and d["counts"]["buyers_sign"] == 1, d["counts"])
ck(d["rec"]["meetings"] == ("down", 1), d["rec"])
ck(M["inactive"] == ["רון לוי", "יוסי ישן"], M["inactive"])         # לא נכנסו בכלל בחודש
ck(M["total"]["counts"]["meetings"] == 2 and M["total"]["targets"]["meetings"] == 94, M["total"])
ck(M["top"][0]["name"] == "דנה כהן", M["top"])
ck(M["label"] == "אוקטובר 2026", M["label"])

msg = g.monthly_message(d, "המשרד שלנו", "https://x/v2/goals", "אוקטובר 2026")
ck(msg.startswith("שלום דנה,") and "לחודש אוקטובר 2026" in msg and "המשרד שלנו" in msg, msg)
ck(msg.split("\n")[2].startswith("גיוס נכסים: 2 מתוך 8.8"), msg)
ck("פגישות מנכס נולד: 2 מתוך 47 (בחודש הקודם: 1)" in msg, msg)
ck("(מתוכם 1 מהחתמה)" in msg, msg)
ck("בחודש הקודם:" in msg.split("הגעת ל-")[1].split("\n")[0], msg)
ck(msg.rstrip().endswith("https://x/v2/goals"), msg)
ck(not any(0x1F300 <= ord(ch) <= 0x1FAFF for ch in msg), "no emoji")

own = g.monthly_owner_summary(M, "המשרד שלנו", "https://x/v2/goals/monthly")
ck("אוקטובר 2026" in own and "דנה כהן" in own and "https://x/v2/goals/monthly" in own, own)
ck("לא נכנסו לאפי בחודש: 2" in own, own)
ck(len(own) < 1000, len(own))

# ── הריצה ────────────────────────────────────────────────────────────────────
def make_G(fail_to=(), quiet=False):
    cfg = {"v2_office": {"name": "המשרד שלנו"}, "nbStatus": nb}
    sent, logs = [], []
    def send_text(to, text):
        sent.append((to, text)); return to not in fail_to
    def mutate(fn):
        c = copy.deepcopy(cfg); r = fn(c); cfg.clear(); cfg.update(c); return True, r
    G = {"_load_config": lambda: cfg, "_config_mutate": mutate, "send_text": send_text,
         "_log_activity": lambda *a: logs.append(a), "_d360_on": lambda: True, "_quiet_mode": lambda: quiet,
         "_switch_off": lambda n: False,
         "fetch_agents_phones": lambda: {"דנה כהן": "050-1111111", "רון לוי": "0522222222"},
         "_agent_vphones9": lambda: set(),
         "_wa_phone": lambda p: "972" + "".join(ch for ch in str(p) if ch.isdigit())[-9:],
         "_last9": lambda p: "".join(ch for ch in str(p) if ch.isdigit())[-9:],
         "_canon_key": canon, "_canon_agent_name": lambda n: n,
         "_DEV_PHONES_RAW": ["0505709865"], "log": None}
    return G, cfg, sent, logs
over = {k: src[k] for k in ("sigs", "buyers", "bpages", "activity", "reviews", "roster", "seen", "seen_month")}
tmp = tempfile.mkdtemp()
G, cfg, sent, logs = make_G()
os.environ.pop("GOALS_MONTHLY_WA", None)
now = at(2026, 11, 1).timestamp()
g.monthly_run(G, now, os.path.join(tmp, "m.json"), src_override=over)
to = [t for t, _ in sent]
ck(to == ["972501111111", "972522222222", "972505709865"], to)
ck(cfg["v2_goals_monthly"]["2026-10"]["done"], cfg)
ck(any("סיכום יעדים חודשי" in str(a) for a in logs), logs)
sent.clear(); cfg.pop("v2_goals_monthly")
g.monthly_run(G, now + 3600, os.path.join(tmp, "m.json"), src_override=over)
ck(sent == [], "once a month, disk guards a wiped config")
G, cfg, sent, logs = make_G(quiet=True)
g.monthly_run(G, now, os.path.join(tmp, "q.json"), src_override=over)
ck(sent == [], "quiet")
G, cfg, sent, logs = make_G()
os.environ["GOALS_MONTHLY_WA"] = "0"
g.monthly_run(G, now, os.path.join(tmp, "o.json"), src_override=over)
ck(sent == [], "env off")
os.environ.pop("GOALS_MONTHLY_WA")
pv = g.monthly_preview(G, now, src_override=over)
ck(sent == [] and pv["month"] == "2026-10" and len(pv["messages"]) == 2 and "owner" in pv and pv["inactive"], pv.keys())
print("monthly ok", N[0])

# ── ראוטים: מנהלים בלבד, לא שולחים ──────────────────────────────────────────
import flask
app = flask.Flask("m")
G, cfg, sent, logs = make_G()
who = {"s": None}
G["_web_auth"] = lambda: who["s"]
g.register_weekly(app, G)
c = app.test_client()
ck(c.get("/v2/api/goals/monthly/preview").status_code == 403, "no auth")
who["s"] = {"drole": "agent"}
ck(c.get("/v2/api/goals/monthly/preview").status_code == 403, "agent")
r = c.get("/v2/goals/monthly")
ck(r.status_code == 200 and "סיכום יעדים חודשי" in r.get_data(as_text=True), "page")
ck(sent == [], "routes never send")
print("monthly routes ok", N[0])
