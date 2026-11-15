"""[15/11] אייל: בלי אישור שלו — הסוכן בוחר אילו עסקאות ('נמכרו') ומודעות ('מתחרות בך') נכנסות לתיק,
הטווח מחושב מחדש רק מהן (גם עסקה שאפי סימנה חריגה), ורק אז התיק מוכן ונשלחת לסוכן הודעה."""
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from flask import Flask
import pytest
import kit_core as KC
import kit as K
import cma
from test_flow_1011 import SBK


class SBP(SBK):
    def kit_claim(self, kid, frm, to, f, match=None):
        for r in self.kits:
            if r["id"] == kid and r.get("status") == frm:
                r.update(f, status=to)
                return True
        return False


def comp(i, ppm, sqm=100, **kw):
    return dict({"street": "הנוטר", "house": i, "date": "2025-0%d-01" % (i % 9 + 1), "rooms": 4, "sqm": sqm, "floor": "2",
                 "price": ppm * sqm, "ppm": ppm, "ours": False, "used": False, "reason": "", "extra": False}, **kw)


CMA = {"title": "x", "subject": {"street": "הנוטר", "city": "קרית ביאליק", "rooms": 4, "sqm": 110, "ptype": "דירה"},
       "basis": "sqm", "range": [0, 0], "ppm_range": [0, 0], "n_used": 7, "competing": 4, "level": "street",
       "comps": [comp(i, 15000 + i * 100, used=i < 7) for i in range(9)] + [comp(9, 30000, reason="חריג")],
       "listings": [{"source": "יד2", "rooms": 4, "sqm": 100, "price": 1700000 + i, "same_street": True} for i in range(4)],
       "_lst_addr": ["הנוטר 3", "הנוטר 5", "הנוטר 9", "הנוטר 14"]}


def test_apply_pick_recomputes_from_chosen():
    new, why = cma.apply_pick(CMA, [0, 1, 2, 9], [3])
    assert why == "" and new["n_used"] == 4 and new["competing"] == 1 and new["picked"]
    vals = sorted([15000, 15100, 15200, 30000])
    q1, q3 = cma._quart(vals)
    assert new["range"] == [cma._round10k(q1 * 110), cma._round10k(q3 * 110)]
    used = [c for c in new["comps"] if c["used"]]
    assert [c["house"] for c in used] == [0, 1, 2, 9] and new["comps"][:4] == used   # הנבחרות קודם
    assert new["listings"] == [CMA["listings"][3]] and "_lst_addr" not in new


def test_apply_pick_limits():
    assert cma.apply_pick(CMA, [0, 1, 2], [])[1] == "few"
    assert cma.apply_pick(CMA, list(range(8)), [])[1] == "many"
    assert cma.apply_pick(CMA, [0, 1, 2, 3], [0, 1, 2, 3])[1] == "many_listings"
    assert cma.apply_pick(dict(CMA, basis="price"), [0, 1, 2, 3], [])[0]["ppm_range"] == []


def test_strip_keeps_listing_addr_for_agent():
    res = {"subject": {"street": "הנוטר", "house": 12}, "comps": [],
           "listings": [{"street": "הנוטר", "house": 5, "price": 1}]}
    out = cma.strip_addresses(res)
    assert out["_lst_addr"] == ["הנוטר 5"] and "house" not in out["listings"][0] and "house" not in out["subject"]


NB = {"מזהה": "77", "שם בעל הנכס": "משה כהן", "טלפון בעל הנכס-": "0544448065", "רחוב1": "הנוטר 12",
      "עיר": "קרית ביאליק", "חדרים": "4", "מחיר": "1890000", 'מ"ר': "110"}
sb = SBP()
SESS, SENT, HAS = {"t": None}, [], {"cma": True}
G = {"_web_auth": lambda: SESS["t"], "_sbdb": sb, "_load_config": lambda: {}, "fetch_newborn": lambda: [NB],
     "_nb_key": lambda r: "id:" + str(r.get("מזהה")), "_log_activity": lambda *a: None,
     "_display_name_for": lambda nm, p: nm, "_phones_for_name": lambda nm: [], "_is_dev": lambda p: False,
     "_last9": lambda p: str(p)[-9:], "_canon_key": lambda s: " ".join(str(s or "").split()),
     "_norm_name": lambda s: " ".join(str(s or "").split()), "_coordinators_all": lambda: {},
     "_quiet_hours": lambda: False, "_shabbat_quiet_now": lambda: False,
     "send_text": lambda to, t: (SENT.append((to, t)), True)[1], "_kit_one_per_addr": False}


def fake_snap(G_, src):
    return {"owner": src["owner"], "street": KC.street_only(src["street"]), "city": src["city"],
            "rooms": src["rooms"], "price": KC._fmt_price(src["price"]), "listing": {"sqm": src["sqm"], "ptype": "דירה"},
            "made_at": "t", "cma": (dict(CMA) if HAS["cma"] else None)}


@pytest.fixture(autouse=True)
def _p():
    saved = (KC.build_snapshot, K._spawn)
    KC.build_snapshot, K._spawn = fake_snap, (lambda fn: fn())
    sb.kits.clear(); SENT.clear(); HAS["cma"] = True
    yield
    KC.build_snapshot, K._spawn = saved


app = Flask(__name__); K.register(app, G); c = app.test_client()
AG = {"name": "דנה כהן", "role": "agent", "drole": "agent", "phone": "501111111"}
AG2 = {"name": "רון לוי", "role": "agent", "drole": "agent", "phone": "502222222"}


def test_create_waits_for_agent_pick_not_approver():
    SESS["t"] = AG
    j = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json
    rec = sb.kit_get(j["id"])
    assert rec["status"] == "pending"
    assert [x[0] for x in SENT] == ["972501111111"] and SENT[0][1].endswith("/v2/cma?kit=" + j["id"])
    m = c.get("/v2/api/kit/mine").json["kits"][0]
    assert m["pick_url"] == "/v2/cma?kit=" + j["id"] and "price=1890000" in m["cma_q"] and "sqm=110" in m["cma_q"]


def test_no_cma_ready_immediately():
    SESS["t"] = AG; HAS["cma"] = False
    j = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json
    assert sb.kit_get(j["id"])["status"] == "approved"
    assert SENT and SENT[-1][1].startswith("תיק הפרזנטציה מוכן")


def test_pick_get_and_post():
    SESS["t"] = AG
    kid = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json["id"]
    g = c.get("/v2/api/kit/pick?id=" + kid).json
    assert g["ok"] and g["listing"]["address"] == "הנוטר 12" and g["listing"]["price"] == "1890000" and g["listing"]["rooms"] == "4"
    assert [x["addr"] for x in g["cma"]["listings"]] == CMA["_lst_addr"] and "_lst_addr" not in g["cma"]
    assert g["max_comps"] == 7 and g["max_listings"] == 3
    SESS["t"] = AG2
    assert c.get("/v2/api/kit/pick?id=" + kid).json == {"ok": False, "reason": "not_found"}
    assert c.post("/v2/api/kit/pick", json={"id": kid, "comps": [0, 1, 2, 3]}).json["reason"] == "not_found"
    SESS["t"] = AG
    assert c.post("/v2/api/kit/pick", json={"id": kid, "comps": [0, 1]}).json == {"ok": False, "reason": "few"}
    SENT.clear()
    p = c.post("/v2/api/kit/pick", json={"id": kid, "comps": [0, 1, 2, 9], "listings": [1, 2]}).json
    rec = sb.kit_get(kid)
    assert p["ok"] and rec["status"] == "approved" and rec["decided_by"] == "דנה כהן"
    cm = rec["snapshot"]["cma"]
    assert cm["n_used"] == 4 and cm["competing"] == 2 and "_lst_addr" not in cm and rec["snapshot"]["picked_at"]
    assert SENT and SENT[-1][1].startswith("תיק הפרזנטציה מוכן") and SENT[-1][0] == "972501111111"
    assert c.post("/v2/api/kit/pick", json={"id": kid, "comps": [0, 1, 2, 3]}).json["reason"] == "status"
    m = c.get("/v2/api/kit/mine").json["kits"][0]
    assert m["status"] == "approved" and "pick_url" not in m and m["wa"] == "972544448065"


def test_preparing_cannot_pick():
    SESS["t"] = AG
    kid = c.post("/v2/api/kit/create", json={"source": "nb", "key": "id:77"}).json["id"]
    sb.kit_update(kid, {"snapshot": dict(sb.kit_get(kid)["snapshot"], _building=True)})
    assert c.get("/v2/api/kit/pick?id=" + kid).json["reason"] == "preparing"
    assert "pick_url" not in c.get("/v2/api/kit/mine").json["kits"][0]
