# tests/newborn/test_nb_rent.py — השכרות בנכס נולד לסוכנים מסוימים (מתג בניהול). על app.py האמיתי.
import os, sys, time, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("WARMUP_ON_BOOT", "0")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)
import supabase_db as SB
import app as A

n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1

today = time.strftime("%d/%m/%Y %H:%M")
SALE = {"מזהה": "s1", "עיר": "קרית ביאליק", "רחוב1": "הרצל 5", "סוג עסקה": "מכירה", "מחיר": "1900000",
        "נוצר בתאריך": today, "נראה לראשונה": today}
RENT = {"מזהה": "r1", "עיר": "קרית מוצקין", "רחוב1": "בגין 12", "סוג עסקה": "השכרה", "מחיר": "4500",
        "נוצר בתאריך": today, "נראה לראשונה": today}
HAIFA_RENT = dict(RENT, **{"מזהה": "r2", "עיר": "חיפה", "רחוב1": "הרצל 1"})

# ── supabase_db: קריאה אחת, עם/בלי השכרות ──────────────────────────────────
SB._get_all = lambda table, cols, **k: [{"source_key": "id:" + r["מזהה"], "raw": r} for r in (SALE, RENT, HAIFA_RENT)]
ck([r["מזהה"] for r in SB.fetch_newborn_rows()] == ["s1"], "default = sale only (unchanged)")
ck([r["מזהה"] for r in SB.fetch_newborn_rows(include_rent=True)] == ["s1", "r1"], "include_rent keeps city filter")

# ── app: fetch_newborn (מכירה) + fetch_newborn_rent מאותה קריאה ───────────────
reads = []
class FakeSB:
    def enabled(self): return True
    def fetch_newborn_rows(self, include_rent=False):
        reads.append(include_rent); return [dict(SALE), dict(RENT)]
A._sbdb = FakeSB(); A.NEWBORN_SOURCE = "supabase"
A._cache_clear("newborn_rows"); A._cache_clear("newborn_rent")
ck([r["מזהה"] for r in A.fetch_newborn()] == ["s1"], "fetch_newborn = sale")
ck([r["מזהה"] for r in A.fetch_newborn_rent()] == ["r1"], "fetch_newborn_rent = rent")
ck(reads == [True], "one DB read for both lists")
ck(A._nb_cal_row(A._nb_key(RENT)) is not None, "calendar row lookup finds rentals")

# ── הרשאה ──────────────────────────────────────────────────────────────────
CFG = {"agents": [{"name": "דנה כהן", "aliases": ["דנה"], "newbornRent": True}, {"name": "יוסי לוי"}]}
A._load_config = lambda: CFG
A._is_dev = lambda ph: str(ph).endswith("505709865")
ck(A._nb_rent_allowed("דנה כהן", "0521111111") is True, "enabled agent")
ck(A._nb_rent_allowed("דנה", "0521111111") is True, "alias match")
ck(A._nb_rent_allowed("יוסי לוי", "0522222222") is False, "not enabled")
ck(A._nb_rent_allowed("אייל שמול", "0505709865") is True, "office owner always")

# ── /api/newborn ───────────────────────────────────────────────────────────
for nm in ("_fetch_newborn_contacts", "_nb_statuses"):
    setattr(A, nm, lambda: {})
A._famexcl_addr_list = lambda: {}
A._scan_price_changes = lambda: None
A._price_dropped_map = lambda: {}
A._nb_notes_for = lambda *a, **k: []
c = A.app.test_client()
def get(sess, qs=""):
    A._web_auth = lambda: sess
    A._NB_RESULT_VER[0] += 1
    return c.get("/api/newborn" + qs).get_json()
yossi = {"name": "יוסי לוי", "role": "agent", "phone": "0522222222"}
dana = {"name": "דנה כהן", "role": "agent", "phone": "0521111111"}
j = get(yossi)
ck(j["ok"] and [r["key"] for r in j["results"]] == [A._nb_key(SALE)], "sale feed for everyone")
ck(j["rentAllowed"] is False and j["results"][0]["rent"] is False, "flags for non-enabled agent")
j = get(yossi, "?deal=rent")
ck(j["ok"] and j["results"] == [] and j["rentAllowed"] is False, "rent blocked for non-enabled agent")
j = get(dana)
ck(j["rentAllowed"] is True and len(j["results"]) == 1, "enabled agent: sale feed + flag")
j = get(dana, "?deal=rent")
ck([r["key"] for r in j["results"]] == [A._nb_key(RENT)] and j["results"][0]["rent"] is True, "rent feed")
ck(j.get("deal") == "rent", "response echoes deal")

# ── ניהול: agent_update + people ─────────────────────────────────────────────
saved = {}
def fake_mutate(fn):
    import copy; cfg = copy.deepcopy(CFG); fn(cfg); saved["cfg"] = cfg; return True, cfg
A._config_mutate = fake_mutate
A._log_activity = lambda *a, **k: None
A._web_auth = lambda: {"name": "אייל שמול", "role": "admin", "phone": "0505709865"}
r = c.post("/api/dev/agent_update", json={"name": "יוסי לוי", "newbornRent": True}).get_json()
ck(r["ok"] and [a for a in saved["cfg"]["agents"] if a["name"] == "יוסי לוי"][0].get("newbornRent") is True, "turn on")
r = c.post("/api/dev/agent_update", json={"name": "דנה כהן", "newbornRent": False}).get_json()
ck("newbornRent" not in [a for a in saved["cfg"]["agents"] if a["name"] == "דנה כהן"][0], "turn off = removed")
print("ok", n)
