# tests/kit/test_routes.py — ראוטים של תיק הפרזנטציה לסוכן + הגדרות בעל המשרד (בלי רשת)
import os, sys, contextlib, datetime as dt, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from flask import Flask
import kit_core as KC
import kit as K


class SBK:
    """presentation_kits בזיכרון."""
    def __init__(self):
        self.kits, self._lk = [], threading.Lock()
    def enabled(self): return True
    def kit_insert(self, rec):
        r = dict(rec, id="k%d" % (len(self.kits) + 1))
        r.setdefault("created_at", dt.datetime.now(dt.timezone.utc).isoformat())
        r.setdefault("views", {})
        self.kits.append(r); return dict(r)
    def kit_update(self, kid, f):
        for r in self.kits:
            if r["id"] == kid: r.update(f)
        return True
    def kit_claim(self, kid, frm, to, f, match=None):
        with self._lk:
            for r in self.kits:
                if r["id"] == kid and r.get("status") == frm and all(r.get(k) == v for k, v in (match or {}).items()):
                    r.update(f, status=to); return True
            return False
    def kit_sent_for_phone(self, phone9):
        rs = sorted((r for r in self.kits if r.get("status") == "sent" and r.get("owner_phone") == phone9),
                    key=lambda r: (str(r.get("sent_at") or ""), r["id"]))
        return {k: rs[0].get(k) for k in ("id", "agent_name", "sent_at")} if rs else None
    def kit_get(self, kid):
        return next((dict(r) for r in self.kits if r["id"] == kid), None)
    def kit_list(self, agent_phone=None, days=90):
        return [dict(r) for r in reversed(self.kits) if not agent_phone or r.get("agent_phone") == agent_phone]


NB = {"מזהה": "77", "שם בעל הנכס": "משה כהן", "טלפון בעל הנכס-": "054-444 8065", "רחוב1": "הנוטר 12",
      "עיר": "קרית ביאליק", "חדרים": "4", "מחיר": "1890000", 'מ"ר': "110", "סוג נכס": "דירה"}
CFG = {"v2_office": {"name": "רימקס פמילי"},
       "nbStatus": {"דנה כהן::id:77": {"status": "meeting", "agent": "דנה כהן", "pkey": "id:77", "owner": "משה כהן",
                                        "ophone": "0544448065", "addr": "הנוטר 12", "price": "1,890,000",
                                        "date": "2026-11-11T17:00"}}}
st = {"acts": [], "reviews": [], "src": []}
sb = SBK()
SESS = {"t": None}
G = {"_web_auth": lambda: SESS["t"], "_sbdb": sb, "_load_config": lambda: CFG,
     "_config_mutate": lambda fn: (True, fn(CFG)),
     "fetch_newborn": lambda: [NB], "_nb_key": lambda r: "id:" + str(r.get("מזהה") or ""),
     "_log_activity": lambda *a: st["acts"].append(a),
     "_display_name_for": lambda nm, p: {"501111111": "דנה כהן", "503333333": "נוי רבן",
                                         "505709865": "אייל שמול"}.get(p, nm),
     "_phones_for_name": lambda nm: {"רון לוי": ["0502222222"], "דנה כהן": ["0501111111"]}.get(nm, []),
     "_is_dev": lambda p: str(p)[-9:] == "505709865", "_last9": lambda p: "".join(c for c in str(p) if c.isdigit())[-9:],
     "_canon_key": lambda s: " ".join(str(s or "").split()),
     "_norm_name": lambda s: " ".join(str(s or "").split()),
     "_coordinators_all": lambda: {"503333333": {"name": "נוי רבן", "agents": {"502222222"}, "names": {"רון לוי"}}}}


def fake_snap(G_, src):
    st["src"].append(dict(src))
    return {"owner": src.get("owner"), "owner_first": (src.get("owner") or "").split(" ")[0],
            "street": KC.street_only(src.get("street")), "city": src.get("city"), "agent": {"name": src.get("agent_name")},
            "office": {"office": "רימקס פמילי"}, "meet_at": src.get("meet_at") or ""}

@contextlib.contextmanager
def patched():
    """מחליף את build_snapshot / send_review / _spawn רק בתוך בדיקה — סדר הייבוא של pytest לא משנה."""
    saved = (KC.build_snapshot, K.send_review, K._spawn)
    KC.build_snapshot = fake_snap
    K.send_review = lambda G_, rec, base: (st["reviews"].append(rec["id"]), True)[1]
    K._spawn = lambda fn: fn()
    try:
        yield
    finally:
        KC.build_snapshot, K.send_review, K._spawn = saved


k1 = k2 = k3 = k4 = MAN = None

app = Flask(__name__); K.register(app, G); c = app.test_client()
AG = {"name": "דנה כהן", "role": "agent", "drole": "agent", "phone": "501111111"}
CO = {"name": "מנהל", "role": "coordinator", "drole": "coordinator", "phone": "503333333"}
DEV = {"name": "מנהל", "role": "admin", "drole": "developer", "phone": "505709865", "dev": True}


def test_binding():
    # ── route binding (לקח 16f7d7f) ──
    global k1, k2, k3, k4, MAN
    with patched():
        VF = app.view_functions
        for ep, fn in (("kit_api_create", "kit_api_create"), ("kit_api_mine", "kit_api_mine"), ("kit_api_resend", "kit_api_resend"),
                       ("kit_api_sent", "kit_api_sent"), ("kit_api_settings", "kit_api_settings")):
            ck(ep in VF and VF[ep].__name__ == fn, ep)
        RULES = {r.rule: r.endpoint for r in app.url_map.iter_rules()}
        ck(RULES.get("/v2/api/kit/create") == "kit_api_create" and RULES.get("/v2/api/kit/mine") == "kit_api_mine"
           and RULES.get("/v2/api/kit/resend") == "kit_api_resend" and RULES.get("/v2/api/kit/sent") == "kit_api_sent"
           and RULES.get("/v2/api/kit/settings") == "kit_api_settings", RULES)



def test_unauth():
    # ── 401 ──
    global k1, k2, k3, k4, MAN
    with patched():
        SESS["t"] = None
        for path, meth in (("/v2/api/kit/create", "post"), ("/v2/api/kit/mine", "get"), ("/v2/api/kit/resend", "post"),
                           ("/v2/api/kit/sent", "post"), ("/v2/api/kit/settings", "get"), ("/v2/api/kit/settings", "post")):
            ck(getattr(c, meth)(path, json={}).status_code == 401, path)



def test_create_nb():
    # ── create nb ──
    global k1, k2, k3, k4, MAN
    with patched():
        SESS["t"] = AG
        r = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77", "meet_at": "2026-11-11T17:00"})
        j = r.json
        ck(j["ok"] and j["status"] == "pending" and j["id"] == "k1", j)
        ck(len(sb.kits) == 1 and st["reviews"] == ["k1"], (sb.kits, st["reviews"]))
        k1 = sb.kits[0]
        ck(k1["agent_name"] == "דנה כהן" and k1["agent_phone"] == "501111111" and k1["owner_phone"] == "544448065"
           and k1["owner_name"] == "משה כהן" and k1["source"] == "nb" and k1["listing_key"] == "id:77", k1)
        ck(k1["review_token"] and k1["view_token"] and k1["review_token"] != k1["view_token"] and k1["sent_review_at"], k1)
        ck("544448065" not in str(k1["snapshot"]) and "12" not in str(k1["snapshot"].get("street")), k1["snapshot"])
        s0 = st["src"][-1]
        ck(s0["sqm"] == "110" and s0["ptype"] == "דירה" and s0["listing_key"] == "id:77" and s0["street"] == "הנוטר 12"
           and s0["rooms"] == "4" and s0["price"] == "1890000" and s0["meet_at"] == "2026-11-11T17:00", s0)
        ck(len(st["acts"]) == 1 and st["acts"][0][3] == "תיק פרזנטציה — נשלח לאישור" and st["acts"][0][4] == "משה כהן · הנוטר", st["acts"])

        # nb missing owner / phone / key
        NB2 = dict(NB, **{"מזהה": "78", "שם בעל הנכס": ""}); NB3 = dict(NB, **{"מזהה": "79", "טלפון בעל הנכס-": "05"})
        G["fetch_newborn"] = lambda: [NB, NB2, NB3]
        ck(c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:78"}).json["reason"] == "owner", "owner")
        ck(c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:79"}).json["reason"] == "phone", "phone")
        ck(c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:nope"}).json["reason"] == "not_found", "nf")
        ck(c.post("/v2/api/kit/create", json={"source": "zzz"}).json["reason"] == "source", "source")



def test_manual_and_agent_choice():
    # ── manual ──
    global k1, k2, k3, k4, MAN
    with patched():
        MAN = {"source": "manual", "owner": "רינה לוי", "phone": "+972544448065", "street": "שדרות ירושלים 5",
               "city": "קרית ים", "rooms": "3"}
        r = c.post("/v2/api/kit/create", json=MAN)
        ck(r.json["ok"] is False and r.json["reason"] == "price", r.json)
        ck(c.post("/v2/api/kit/create", json=dict(MAN, price="1200000", phone="1234")).json["reason"] == "phone", "manual phone")
        r = c.post("/v2/api/kit/create", json=dict(MAN, price="1200000", sqm="80", agent="רון לוי"))
        ck(r.json["ok"], r.json)
        k2 = sb.kit_get(r.json["id"])
        ck(k2["agent_name"] == "דנה כהן" and k2["agent_phone"] == "501111111", k2)   # סוכן לא בוחר סוכן אחר
        ck(st["src"][-1]["ptype"] == "דירה" and st["src"][-1]["sqm"] == "80" and st["src"][-1]["listing_key"] == "", st["src"][-1])

        # coordinator may pick another agent
        SESS["t"] = CO
        r = c.post("/v2/api/kit/create", json=dict(MAN, price="1200000", agent="רון לוי"))
        k3 = sb.kit_get(r.json["id"])
        ck(r.json["ok"] and k3["agent_name"] == "רון לוי" and k3["agent_phone"] == "502222222"
           and k3["created_by"] == "נוי רבן" and k3["created_by_phone"] == "503333333", k3)
        # [R6] מתאמת — רק סוכן מהצוות שלה; סוכן מבחוץ → היא עצמה
        r = c.post("/v2/api/kit/create", json=dict(MAN, price="1200000", agent="  רון   לוי "))
        ck(r.json["ok"] and sb.kit_get(r.json["id"])["agent_name"] == "רון לוי", r.json)
        r = c.post("/v2/api/kit/create", json=dict(MAN, price="1200000", agent="דנה כהן"))
        kx = sb.kit_get(r.json["id"])
        ck(r.json["ok"] and kx["agent_name"] == "נוי רבן" and kx["agent_phone"] == "503333333", kx)
        # admin — כל סוכן
        SESS["t"] = DEV
        r = c.post("/v2/api/kit/create", json=dict(MAN, price="1200000", agent="דנה כהן"))
        ck(r.json["ok"] and sb.kit_get(r.json["id"])["agent_name"] == "דנה כהן", r.json)



def test_meet():
    # ── meet ──
    global k1, k2, k3, k4, MAN
    with patched():
        SESS["t"] = AG
        r = c.post("/v2/api/kit/create", json={"source": "meet", "skey": "דנה כהן::id:77"})
        k4 = sb.kit_get(r.json["id"])
        ck(r.json["ok"] and k4["source"] == "meet" and k4["listing_key"] == "id:77" and k4["owner_phone"] == "544448065", k4)
        ck(st["src"][-1]["meet_at"] == "2026-11-11T17:00" and st["src"][-1]["city"] == "קרית ביאליק"
           and st["src"][-1]["rooms"] == "4" and st["src"][-1]["sqm"] == "110", st["src"][-1])
        ck(c.post("/v2/api/kit/create", json={"source": "meet", "skey": "nope"}).json["reason"] == "not_found", "meet nf")
        SESS["t"] = CO   # הפגישה של דנה — לא בצוות של המתאמת
        ck(c.post("/v2/api/kit/create", json={"source": "meet", "skey": "דנה כהן::id:77"}).json["reason"] == "forbidden", "coord meet outside")
        SESS["t"] = {"name": "רון לוי", "role": "agent", "drole": "agent", "phone": "502222222"}
        ck(c.post("/v2/api/kit/create", json={"source": "meet", "skey": "דנה כהן::id:77"}).json["reason"] == "forbidden", "meet other")



def test_mine():
    # ── mine ──
    global k1, k2, k3, k4, MAN
    with patched():
        SESS["t"] = AG
        j = c.get("/v2/api/kit/mine").json
        ids = [x["id"] for x in j["kits"]]
        ck(j["ok"] and "k1" in ids and "k3" not in ids, ids)
        m1 = next(x for x in j["kits"] if x["id"] == "k1")
        ck(m1["status"] == "pending" and "wa" not in m1 and "url" not in m1 and "text" not in m1, m1)
        ck(m1["owner"] == "משה כהן" and m1["street"] == "הנוטר" and set(m1["views"]) == {"opens", "secs", "last"}, m1)
        ck("544448065" not in str(m1), m1)
        sb.kit_update("k1", {"status": "approved"})
        m1 = next(x for x in c.get("/v2/api/kit/mine").json["kits"] if x["id"] == "k1")
        ck(m1["status"] == "approved" and m1["wa"] == "972544448065" and m1["url"].endswith("/k/" + k1["view_token"]), m1)
        ck(m1["text"].endswith("\n" + m1["url"]) and m1["text"].startswith("שלום משה"), m1["text"])
        ck("{" not in m1["text"] and "כאן דנה כהן מרימקס פמילי." in m1["text"], m1["text"])   # צילום בצורה האמיתית (dicts)
        # expired by eff_status
        sb.kit_update("k2", {"sent_review_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=49)).isoformat()})
        m2 = next(x for x in c.get("/v2/api/kit/mine").json["kits"] if x["id"] == "k2")
        ck(m2["status"] == "expired" and "wa" not in m2, m2)
        # admin all
        SESS["t"] = DEV
        ids = [x["id"] for x in c.get("/v2/api/kit/mine?all=1").json["kits"]]
        ck("k1" in ids and "k3" in ids, ids)
        SESS["t"] = AG
        ids = [x["id"] for x in c.get("/v2/api/kit/mine?all=1").json["kits"]]
        ck("k3" not in ids, "agent ignores all")
        # [R6] מתאמת עם all=1 — הצוות שלה (+ שלה), לא כל המשרד
        SESS["t"] = CO
        ks = c.get("/v2/api/kit/mine?all=1").json["kits"]
        names = {x["agent"] for x in ks}
        ck("k3" in [x["id"] for x in ks] and names <= {"רון לוי", "נוי רבן"} and "נוי רבן" in names, ks)
        ck("k1" not in [x["id"] for x in c.get("/v2/api/kit/mine").json["kits"]], "coord mine own only")
        SESS["t"] = AG



def test_resend():
    # ── resend ──
    global k1, k2, k3, k4, MAN
    with patched():
        ck(c.post("/v2/api/kit/resend", json={"id": "k1"}).json["ok"] is False, "resend approved")
        sb.kit_update(k4["id"], {"status": "rejected", "reject_reason": "חסר"})
        old = sb.kit_get(k4["id"])
        nrev = len(st["reviews"])
        SESS["t"] = {"name": "רון לוי", "role": "agent", "drole": "agent", "phone": "502222222"}
        ck(c.post("/v2/api/kit/resend", json={"id": k4["id"]}).json["ok"] is False, "resend not owner")
        SESS["t"] = AG
        r = c.post("/v2/api/kit/resend", json={"id": k4["id"]})
        new = sb.kit_get(k4["id"])
        ck(r.json["ok"] and new["status"] == "pending" and not new["reject_reason"]
           and new["review_token"] != old["review_token"] and new["view_token"] != old["view_token"], (r.json, new))
        ck(len(st["reviews"]) == nrev + 1 and st["src"][-1]["owner"] == "משה כהן" and st["src"][-1]["phone"] == "544448065", st["src"][-1])
        # expired → resend allowed
        r = c.post("/v2/api/kit/resend", json={"id": "k2"})
        ck(r.json["ok"] and sb.kit_get("k2")["status"] == "pending", r.json)



def test_sent():
    # ── sent ──
    global k1, k2, k3, k4, MAN
    with patched():
        ck(c.post("/v2/api/kit/sent", json={"id": k4["id"]}).json["ok"] is False, "sent on pending")
        r = c.post("/v2/api/kit/sent", json={"id": "k1"})
        ck(r.json["ok"] and sb.kit_get("k1")["status"] == "sent" and sb.kit_get("k1")["sent_at"], r.json)
        ck(st["acts"][-1][3] == "תיק פרזנטציה — נשלח לבעל הנכס", st["acts"][-1])
        m1 = next(x for x in c.get("/v2/api/kit/mine").json["kits"] if x["id"] == "k1")
        ck(m1["status"] == "sent" and m1["wa"] == "972544448065", m1)
        sb.kit_update("k1", {"status": "approved"})   # הבדיקות הבאות פותחות עוד תיקים לאותו בעל נכס (כלל 'נשלח ראשון' — test_taken)



def test_settings():
    # ── settings ──
    global k1, k2, k3, k4, MAN
    with patched():
        SESS["t"] = AG
        ck(c.get("/v2/api/kit/settings").status_code == 403 and c.post("/v2/api/kit/settings", json={}).status_code == 403, "agent 403")
        SESS["t"] = DEV
        j = c.get("/v2/api/kit/settings").json
        ck(j["ok"] and j["settings"]["g_rating"] == "4.9", j)
        r = c.post("/v2/api/kit/settings", json={"coop": "  70 אחוז  ", "rank": "מקום 1", "g_rating": "4.8", "g_count": "120",
                                                  "g_url": " https://g.page/x "})
        ck(r.json["ok"] and CFG["v2_kit"] == {"coop": "70 אחוז", "rank": "מקום 1", "g_rating": "4.8", "g_count": "120",
                                                "g_url": "https://g.page/x"}, (r.json, CFG.get("v2_kit")))
        ck(st["acts"][-1][3].startswith("תיק פרזנטציה — הגדרות"), st["acts"][-1])
        r = c.post("/v2/api/kit/settings", json={"g_url": "http://x"})
        ck(r.json["ok"] is False and CFG["v2_kit"]["g_url"] == "https://g.page/x", r.json)
        r = c.post("/v2/api/kit/settings", json={"instagram": "https://instagram.com/remax", "facebook": "facebook.com/x"})
        ck(r.json == {"ok": False, "reason": "facebook"} and "instagram" not in CFG["v2_kit"], r.json)
        r = c.post("/v2/api/kit/settings", json={"instagram": "https://instagram.com/remax"})
        ck(r.json["ok"] and CFG["v2_kit"]["instagram"] == "https://instagram.com/remax", r.json)
        good = G["_config_mutate"]
        G["_config_mutate"] = lambda fn: (False, None)
        try:
            ck(c.post("/v2/api/kit/settings", json={"rank": "z"}).json["ok"] is False, "mutate fail")
        finally:
            G["_config_mutate"] = good


def test_review_fixes():
    """Fix round 1: הרשאות לפי drole, פגישה בלי סוכן, סוכן לא ידוע, מתאמת על תיקי הצוות, נרמול שם בפגישה."""
    with patched():
        MANX = {"source": "manual", "owner": "רינה לוי", "phone": "0544448065", "street": "שדרות ירושלים 5",
                "city": "קרית ים", "rooms": "3", "price": "1200000"}
        # 1 — הנה"ח / מזכירה (role=admin) הם סוכנים רגילים
        SESS["t"] = DEV
        r = c.post("/v2/api/kit/create", json=dict(MANX, agent="רון לוי"))
        kron = sb.kit_get(r.json["id"])
        ck(kron["agent_name"] == "רון לוי", kron)
        sb.kit_update(kron["id"], {"status": "rejected"})
        for dr, ph in (("accountant", "506666666"), ("secretary", "507777777")):
            S = {"name": "חגית " + dr, "role": "admin", "drole": dr, "phone": ph}
            SESS["t"] = S
            r = c.post("/v2/api/kit/create", json=dict(MANX, agent="רון לוי"))
            kk = sb.kit_get(r.json["id"])
            ck(r.json["ok"] and kk["agent_name"] == S["name"] and kk["agent_phone"] == ph, (dr, kk))
            ids = [x["id"] for x in c.get("/v2/api/kit/mine?all=1").json["kits"]]
            ck(kron["id"] not in ids and kk["id"] in ids, (dr, ids))
            ck(c.post("/v2/api/kit/resend", json={"id": kron["id"]}).json["ok"] is False, dr + " resend")
            sb.kit_update(kk["id"], {"status": "approved"})
            sb.kit_update(kron["id"], {"status": "approved"})
            ck(c.post("/v2/api/kit/sent", json={"id": kron["id"]}).json["ok"] is False, dr + " sent other")
            ck(c.post("/v2/api/kit/sent", json={"id": kk["id"]}).json["ok"] is True, dr + " sent own")
            sb.kit_update(kk["id"], {"status": "approved"})   # אותו בעל נכס בהמשך — לא נועלים אותו כאן
            sb.kit_update(kron["id"], {"status": "rejected"})
            ck(c.post("/v2/api/kit/settings", json={}).status_code == 403, dr + " settings")
        # 2 — פגישה בלי סוכן: רק מי שקבע אותה
        CFG["nbStatus"]["::id:77"] = dict(CFG["nbStatus"]["דנה כהן::id:77"], agent="", by_phone="501111111")
        SESS["t"] = {"name": "רון לוי", "role": "agent", "drole": "agent", "phone": "502222222"}
        ck(c.post("/v2/api/kit/create", json={"source": "meet", "skey": "::id:77"}).json.get("reason") == "forbidden", "no-agent meet other")
        SESS["t"] = AG
        r = c.post("/v2/api/kit/create", json={"source": "meet", "skey": "::id:77"})
        ck(r.json["ok"] and sb.kit_get(r.json["id"])["agent_name"] == "דנה כהן", r.json)
        # 3 — מנהל עם סוכן לא ידוע: בלי שורה
        SESS["t"] = DEV
        before = len(sb.kits)
        r = c.post("/v2/api/kit/create", json=dict(MANX, agent="יוסי לא קיים"))
        ck(r.json["ok"] is False and r.json["reason"] == "agent" and len(sb.kits) == before, r.json)
        # 4 — מתאמת: שליחה חוזרת/נשלח על תיק של סוכן מהצוות (שהמנהל יצר) ועל תיק שהיא יצרה
        SESS["t"] = CO
        r = c.post("/v2/api/kit/create", json=dict(MANX, agent="רון לוי"))
        kc_ = sb.kit_get(r.json["id"])
        ck(kc_["agent_name"] == "רון לוי" and kc_["created_by_phone"] == "503333333", kc_)
        sb.kit_update(kc_["id"], {"status": "rejected"})
        ck(c.post("/v2/api/kit/resend", json={"id": kc_["id"]}).json["ok"], "coord resend own-created")
        ck(c.post("/v2/api/kit/resend", json={"id": kron["id"]}).json["ok"], "coord resend team")
        sb.kit_update(kron["id"], {"status": "approved"})
        ck(c.post("/v2/api/kit/sent", json={"id": kron["id"]}).json["ok"], "coord sent team")
        sb.kit_update(kron["id"], {"status": "approved"})
        kd = next(r for r in sb.kits if r["agent_name"] == "דנה כהן" and r.get("created_by_phone") == "501111111")
        sb.kit_update(kd["id"], {"status": "rejected"})
        ck(c.post("/v2/api/kit/resend", json={"id": kd["id"]}).json["ok"] is False, "coord not outside team")
        # 5 — שם הסוכן בפגישה מנורמל
        CFG["nbStatus"]["x::id:77"] = dict(CFG["nbStatus"]["דנה כהן::id:77"], agent="  דנה   כהן ")
        SESS["t"] = DEV
        r = c.post("/v2/api/kit/create", json={"source": "meet", "skey": "x::id:77"})
        kn = sb.kit_get(r.json["id"])
        ck(r.json["ok"] and kn["agent_name"] == "דנה כהן" and kn["agent_phone"] == "501111111", kn)
        SESS["t"] = AG   # הסוכנת עצמה — אותה השוואה בשני הצדדים
        ck(c.post("/v2/api/kit/create", json={"source": "meet", "skey": "x::id:77"}).json["ok"], "self meet spaced")



def test_meet_generic_agent():
    """פגישה שנשמרה על שם כניסה גנרי ('מנהל') — הסוכן לפי הטלפון של מי שקבע, ואחרת הסוכן של הסשן."""
    with patched():
        base = dict(CFG["nbStatus"]["דנה כהן::id:77"], agent="מנהל")
        CFG["nbStatus"]["g1::id:77"] = dict(base, by_phone="501111111")
        CFG["nbStatus"]["g2::id:77"] = dict(base, by_phone="509999999")
        SESS["t"] = DEV
        r = c.post("/v2/api/kit/create", json={"source": "meet", "skey": "g1::id:77"})
        k = sb.kit_get(r.json["id"])
        ck(r.json["ok"] and k["agent_name"] == "דנה כהן" and k["agent_phone"] == "501111111", k)
        r = c.post("/v2/api/kit/create", json={"source": "meet", "skey": "g2::id:77"})
        k = sb.kit_get(r.json["id"])
        ck(r.json["ok"] and k["agent_name"] == "אייל שמול" and k["agent_phone"] == "505709865", k)
        SESS["t"] = AG
        r = c.post("/v2/api/kit/create", json={"source": "meet", "skey": "g1::id:77"})
        ck(r.json["ok"] and sb.kit_get(r.json["id"])["agent_name"] == "דנה כהן", r.json)
        ck(c.post("/v2/api/kit/create", json={"source": "meet", "skey": "g2::id:77"}).json.get("reason") == "forbidden", "g2 agent")



def test_taken():
    """תיק אחד לכל בעל נכס — מי ששולח ראשון."""
    with patched():
        MT = {"source": "manual", "owner": "יוסי בר", "phone": "052-123 4567", "street": "הגפן 3", "city": "קרית ים",
              "rooms": "3", "price": "1500000"}
        SESS["t"] = AG
        a = sb.kit_get(c.post("/v2/api/kit/create", json=MT).json["id"])
        SESS["t"] = DEV
        b = sb.kit_get(c.post("/v2/api/kit/create", json=dict(MT, agent="רון לוי")).json["id"])   # כמה תיקים בהכנה — מותר
        ck(a and b and a["owner_phone"] == b["owner_phone"] == "521234567", (a, b))
        sb.kit_update(a["id"], {"status": "approved"}); sb.kit_update(b["id"], {"status": "approved"})
        SESS["t"] = AG
        ck(c.post("/v2/api/kit/sent", json={"id": a["id"]}).json["ok"], "first send wins")
        SESS["t"] = DEV
        mb = next(x for x in c.get("/v2/api/kit/mine?all=1").json["kits"] if x["id"] == b["id"])
        ck(mb["status"] == "taken" and mb["taken_by"] == "דנה כהן" and not ({"wa", "url", "text"} & set(mb)), mb)
        ma = next(x for x in c.get("/v2/api/kit/mine?all=1").json["kits"] if x["id"] == a["id"])
        ck(ma["status"] == "sent" and ma.get("wa"), ma)
        j = c.post("/v2/api/kit/sent", json={"id": b["id"]}).json
        ck(j == {"ok": False, "reason": "taken", "by": "דנה כהן"} and sb.kit_get(b["id"])["status"] == "approved", j)
        before = len(sb.kits)
        j = c.post("/v2/api/kit/create", json=dict(MT, phone="+972521234567"))
        ck(j.json == {"ok": False, "reason": "taken", "by": "דנה כהן"} and len(sb.kits) == before, j.json)
        sb.kit_update(b["id"], {"status": "rejected"})
        j = c.post("/v2/api/kit/resend", json={"id": b["id"]}).json
        ck(j["reason"] == "taken" and sb.kit_get(b["id"])["status"] == "rejected", j)
        # מרוץ: שניהם עברו את הבדיקה המוקדמת — המוקדם ב-sent_at נשאר, השני חוזר ל'מוכן לשליחה'
        d = sb.kit_get(c.post("/v2/api/kit/create", json=dict(MT, phone="0529998887")).json["id"])
        e = sb.kit_get(c.post("/v2/api/kit/create", json=dict(MT, phone="0529998887", agent="רון לוי")).json["id"])
        sb.kit_update(d["id"], {"status": "sent", "sent_at": "2026-01-01T00:00:00+00:00"})
        sb.kit_update(e["id"], {"status": "approved"})
        real, calls = sb.kit_sent_for_phone, []
        sb.kit_sent_for_phone = lambda p: (calls.append(p), None if len(calls) == 1 else real(p))[1]
        try:
            j = c.post("/v2/api/kit/sent", json={"id": e["id"]}).json
        finally:
            sb.kit_sent_for_phone = real
        ek = sb.kit_get(e["id"])
        ck(j["reason"] == "taken" and j["by"] == "אייל שמול" and ek["status"] == "approved" and not ek.get("sent_at"), (j, ek))
        # בעל נכס אחר — לא מושפע
        ck(c.post("/v2/api/kit/create", json=dict(MT, phone="0527776665")).json["ok"], "other owner")


if __name__ == "__main__":
    for _f in (test_binding, test_unauth, test_create_nb, test_manual_and_agent_choice, test_meet, test_mine, test_resend, test_sent, test_settings, test_review_fixes, test_meet_generic_agent, test_taken):
        _f()
    print("OK", n)
