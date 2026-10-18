from site_api import prop_first_hand
from tests.siteweb.conftest import Store
from tests.siteweb.test_site_props import ROWS, owns, sess, mk


def test_prop_first_hand():
    rows = [{"kind": "prop", "key": "a", "data": {"first_hand": True}},
            {"kind": "prop", "key": "b", "data": {"hidden": True}}]
    assert prop_first_hand(rows) == {"a"}


def test_agent_marks_own_property(make_app):
    c, store, app = mk(make_app, sess("agent", "חי חיים אלבז"))
    r = c.post("/v2/api/site/prop", json={"key": "a1", "first_hand": True}).get_json()
    assert r == {"ok": True, "first_hand": True}
    assert store.puts[-1][:3] == ("prop", "a1", {"first_hand": True})
    assert any("יד ראשונה" in a[3] for a in app.logs)
    st = c.get("/v2/api/site/state").get_json()
    assert st["first_hand"] == ["a1"]


def test_agent_cannot_mark_others(make_app):
    c, store, _ = mk(make_app, sess("agent", "חי חיים אלבז"))
    assert c.post("/v2/api/site/prop", json={"key": "b2", "first_hand": True}).status_code == 403
    assert store.puts == []


def test_manager_marks_any(make_app):
    c, store, _ = mk(make_app, sess("manager", "מנהל"))
    assert c.post("/v2/api/site/prop", json={"key": "b2", "first_hand": True}).get_json()["ok"]


def test_flags_do_not_erase_each_other(make_app):
    store = Store(); store.rows = [{"kind": "prop", "key": "a1", "data": {"first_hand": True}}]
    c, store, _ = mk(make_app, sess(), store)
    c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True})
    assert store.puts[-1][2] == {"first_hand": True, "hidden": True}
    c2, store, _ = mk(make_app, sess("agent", "חי חיים אלבז"), store)
    c2.post("/v2/api/site/prop", json={"key": "a1", "first_hand": False})
    assert store.puts[-1][2] == {"first_hand": False, "hidden": True}


def test_agent_still_cannot_hide(make_app):
    c, store, _ = mk(make_app, sess("agent", "חי חיים אלבז"))
    assert c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True}).status_code == 403


def test_one_field_per_request(make_app):
    c, _, _ = mk(make_app, sess())
    assert c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True, "first_hand": True}).status_code == 400
