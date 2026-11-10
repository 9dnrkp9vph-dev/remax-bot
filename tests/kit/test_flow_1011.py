"""[10/11] תיק פרזנטציה: תשובה מיידית, אישור רק אחרי ניתוח השוק, תיק אחד לכל נכס (אייל)."""
import os, sys, time, datetime as dt, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from flask import Flask
import kit_core as KC
import kit as K
import cma, cma_bot


class SBK:
    def __init__(self):
        self.kits = []
    def enabled(self): return True
    def kit_insert(self, rec):
        r = dict(rec, id="k%d" % (len(self.kits) + 1), created_at=dt.datetime.now(dt.timezone.utc).isoformat(), views={})
        self.kits.append(r); return dict(r)
    def kit_update(self, kid, f):
        for r in self.kits:
            if r["id"] == kid: r.update(f)
        return True
    def kit_claim(self, kid, frm, to, f, match=None): return False
    def kit_sent_for_phone(self, p9): return None
    def kit_get(self, kid): return next((dict(r) for r in self.kits if r["id"] == kid), None)
    def kit_list(self, agent_phone=None, days=90):
        return [dict(r) for r in reversed(self.kits) if not agent_phone or r.get("agent_phone") == agent_phone]


NB = {"מזהה": "77", "שם בעל הנכס": "משה כהן", "טלפון בעל הנכס-": "0544448065", "רחוב1": "הנוטר 12",
      "עיר": "קרית ביאליק", "חדרים": "4", "מחיר": "1890000", 'מ"ר': "110"}
CFG = {"v2_office": {"name": "רימקס פמילי"}}
SESS, REV, SNAPS = {"t": None}, [], []
sb = SBK()
G = {"_web_auth": lambda: SESS["t"], "_sbdb": sb, "_load_config": lambda: CFG, "_config_mutate": lambda fn: (True, fn(CFG)),
     "fetch_newborn": lambda: [NB], "_nb_key": lambda r: "id:" + str(r.get("מזהה")),
     "_log_activity": lambda *a: None, "_display_name_for": lambda nm, p: nm, "_phones_for_name": lambda nm: [],
     "_is_dev": lambda p: str(p)[-9:] == "505709865", "_last9": lambda p: "".join(c for c in str(p) if c.isdigit())[-9:],
     "_canon_key": lambda s: " ".join(str(s or "").split()), "_norm_name": lambda s: " ".join(str(s or "").split()),
     "_coordinators_all": lambda: {}}
CMA_ON = {"v": False}


def fake_snap(G_, src):
    SNAPS.append(dict(src))
    return {"owner": src.get("owner"), "street": KC.street_only(src.get("street")), "city": src.get("city"),
            "cma": ({"range": [1, 2]} if CMA_ON["v"] else None)}


import pytest


@pytest.fixture(autouse=True)
def _patched():
    saved = (KC.build_snapshot, K.send_review, K._spawn)
    KC.build_snapshot = fake_snap
    K.send_review = lambda G_, rec, base: (REV.append(rec["id"]), True)[1]
    K._spawn = lambda fn: fn()
    yield
    KC.build_snapshot, K.send_review, K._spawn = saved


app = Flask(__name__); K.register(app, G); c = app.test_client()
AG = {"name": "דנה כהן", "role": "agent", "drole": "agent", "phone": "501111111"}
AG2 = {"name": "רון לוי", "role": "agent", "drole": "agent", "phone": "502222222"}
DEV = {"name": "מנהל", "role": "admin", "drole": "developer", "phone": "505709865", "dev": True}


def _reset():
    sb.kits.clear(); REV.clear(); SNAPS.clear(); CFG.pop(cma_bot.REQ_CFG, None); CFG.pop(cma_bot.CFG, None); CMA_ON["v"] = False


def _bot_pending(rid="cma-x", age=10):
    subj = cma.subject_from_listing({"רחוב": "הנוטר 12", "חדרים": "4", "עיר / ישוב": KC._norm_city("קרית ביאליק")})
    CFG[cma_bot.REQ_CFG] = {rid: {"ts": time.time() - age, "address": "x", "akey": cma_bot.addr_key(cma.bot_address(subj)), "ok": True}}


def test_immediate_and_review_when_cma_ready():
    _reset(); SESS["t"] = AG; CMA_ON["v"] = True
    j = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json
    assert j["ok"] and REV == [j["id"]]
    assert "_building" not in sb.kit_get(j["id"])["snapshot"]


def test_waits_for_bot_then_reviews():
    _reset(); SESS["t"] = AG; _bot_pending("cma-a")
    j = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json
    rec = sb.kit_get(j["id"])
    assert j["ok"] and REV == [] and rec["snapshot"]["_cma_wait"]["rid"] == "cma-a"
    SESS["t"] = DEV
    m = next(x for x in c.get("/v2/api/kit/mine?all=1").json["kits"] if x["id"] == j["id"])
    assert m.get("preparing") and "review_url" not in m
    CMA_ON["v"] = True
    cma_bot.kit_release(G, "cma-other")
    assert REV == []
    cma_bot.kit_release(G, "cma-a")
    rec = sb.kit_get(j["id"])
    assert REV == [j["id"]] and "_cma_wait" not in rec["snapshot"] and rec["snapshot"]["cma"]


def test_timeout_releases_without_cma():
    _reset(); SESS["t"] = AG; _bot_pending("cma-b")
    j = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json
    assert REV == []
    for r in sb.kits: r["snapshot"]["_cma_wait"]["since"] -= 10000
    assert G["_kit_cma_release"](older=K.CMA_WAIT_SEC) == 1 and REV == [j["id"]]


def test_answered_request_does_not_wait():
    _reset(); SESS["t"] = AG; _bot_pending("cma-c"); CFG[cma_bot.CFG] = [{"request_id": "cma-c"}]
    j = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json
    assert REV == [j["id"]]


def test_one_kit_per_property_owner_exempt():
    _reset(); SESS["t"] = AG; CMA_ON["v"] = True
    assert c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json["ok"]
    SESS["t"] = AG2
    j = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json
    assert j == {"ok": False, "reason": "exists", "by": "דנה כהן"}
    SESS["t"] = AG
    assert c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json["reason"] == "exists"
    SESS["t"] = DEV
    assert c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json["ok"]


def test_early_bot_ask_before_build():
    _reset(); SESS["t"] = AG; CMA_ON["v"] = True
    calls, real = [], cma_bot.request_bot
    cma_bot.request_bot = lambda G_, addr, by="", force=False: (calls.append((addr, len(SNAPS))), {"ok": True})[1]
    try:
        sb.market_street_count = lambda street, since: 1
        c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"})
        assert calls == [("הנוטר 12, קרית ביאליק", 0)]   # לפני שהצילום נבנה
        _reset(); SESS["t"] = AG; CMA_ON["v"] = True; calls.clear()
        sb.market_street_count = lambda street, since: 12
        c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"})
        assert calls == []
    finally:
        cma_bot.request_bot = real
        del sb.market_street_count
