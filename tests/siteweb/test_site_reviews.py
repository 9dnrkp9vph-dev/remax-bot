"""המלצות לקוחות — ניהול מאפי (אייל 18/10): סוכן מוסיף על עצמו, מנהל/מזכירה/מפתח על כל סוכן."""
from site_api import reviews_active, OLD_REVIEWS
from tests.siteweb.conftest import Store
from tests.siteweb.test_site_props import sess

CFG = {"agents": [{"name": "קובי חמו"}, {"name": "רויטל גל"}]}


def mk(make_app, s, store=None):
    store = store or Store()
    app = make_app(store=store, _web_auth=lambda: s, _is_dev=lambda ph: False,
                   _load_config=lambda: CFG, _name_key=lambda n: "".join(str(n or "").split()))
    return app.test_client(), store, app


def test_reviews_active_skips_deleted_and_sorts_newest_first():
    rows = [{"kind": "review", "key": "a", "data": {"agents": ["x"], "text": "1", "at": "2026-01-01"}},
            {"kind": "review", "key": "b", "data": {"agents": ["x"], "text": "2", "at": "2026-05-01"}},
            {"kind": "review", "key": "c", "data": {"agents": ["x"], "text": "3", "at": "2026-06-01", "deleted": True}},
            {"kind": "prop", "key": "p", "data": {}}]
    assert [r["id"] for r in reviews_active(rows)] == ["b", "a"]


def test_first_get_seeds_old_reviews(make_app):
    c, store, _ = mk(make_app, sess("manager", "מנהל"))
    j = c.get("/v2/api/site/reviews").get_json()
    assert j["ok"] and len(j["reviews"]) == len(OLD_REVIEWS) == 4
    assert len([p for p in store.puts if p[0] == "review"]) == 4
    c.get("/v2/api/site/reviews")                       # פעם שנייה — לא זורע שוב
    assert len([p for p in store.puts if p[0] == "review"]) == 4


def test_agent_sees_and_adds_only_own(make_app):
    c, store, app = mk(make_app, sess("agent", "קובי חמו"))
    j = c.get("/v2/api/site/reviews").get_json()
    assert j["can_all"] is False and all("קובי חמו" in r["agents"] for r in j["reviews"]) and len(j["reviews"]) == 2
    r = c.post("/v2/api/site/reviews", json={"agent": "רויטל גל", "text": "שירות מעולה", "by": "דנה"}).get_json()
    assert r["ok"] and r["review"]["agents"] == ["קובי חמו"]          # סוכן תמיד על עצמו
    assert any("המלצה" in a[3] for a in app.logs)


def test_manager_adds_for_agent_and_validates(make_app):
    c, store, _ = mk(make_app, sess("manager", "מנהל"))
    assert c.post("/v2/api/site/reviews", json={"agent": "רויטל גל", "text": "  "}).status_code == 400
    assert c.post("/v2/api/site/reviews", json={"agent": "לא קיים", "text": "טוב"}).status_code == 400
    r = c.post("/v2/api/site/reviews", json={"agent": "רויטל גל", "text": "א\nב", "title": "תודה", "by": "משפחת כהן"}).get_json()
    assert r["review"]["agents"] == ["רויטל גל"] and r["review"]["text"] == "א\nב"


def test_delete_permissions(make_app):
    store = Store()
    store.rows = [{"kind": "review", "key": "k1", "data": {"agents": ["רויטל גל"], "text": "x", "at": "2026"}}]
    c, store, _ = mk(make_app, sess("agent", "קובי חמו"), store)
    assert c.post("/v2/api/site/reviews/delete", json={"id": "k1"}).status_code == 403
    c, store, _ = mk(make_app, sess("agent", "רויטל גל"), store)
    assert c.post("/v2/api/site/reviews/delete", json={"id": "k1"}).get_json()["ok"]
    assert store.puts[-1][2]["deleted"] is True


def test_unauth(make_app):
    c, _, _ = mk(make_app, None)
    assert c.get("/v2/api/site/reviews").status_code == 401


def test_seeds_old_reviews_even_if_a_new_one_exists_first(make_app):
    store = Store()
    store.rows = [{"kind": "review", "key": "rv-1", "data": {"agents": ["רויטל גל"], "text": "חדש", "at": "2026-10-19"}}]
    c, store, _ = mk(make_app, sess("manager", "מנהל"), store)
    assert len(c.get("/v2/api/site/reviews").get_json()["reviews"]) == 5


def test_deleted_old_review_not_reseeded(make_app):
    store = Store()
    store.rows = [{"kind": "review", "key": "old-1", "data": {"agents": ["רויטל גל"], "text": "x", "deleted": True}}]
    c, store, _ = mk(make_app, sess("manager", "מנהל"), store)
    j = c.get("/v2/api/site/reviews").get_json()
    assert len(j["reviews"]) == 3 and "old-1" not in [r["id"] for r in j["reviews"]]
