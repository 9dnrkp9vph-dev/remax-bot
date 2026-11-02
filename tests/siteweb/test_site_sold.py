# tests/siteweb/test_site_sold.py — 'אני מכרתי' במחיקת נכס מ'שלי' → הנכס עובר ל'נמכרו' באתר (אייל 02/11)
from tests.siteweb.conftest import Store
from tests.siteweb.test_site_props import sess, mk


def test_agent_marks_own_sold(make_app):
    c, store, app = mk(make_app, sess("agent", "חי חיים אלבז"))
    r = c.post("/v2/api/site/prop", json={"key": "a1", "sold": True}).get_json()
    assert r["ok"] and r["sold"] is True
    kind, key, data = store.puts[-1][:3]
    assert (kind, key) == ("prop", "a1")
    assert isinstance(data["sold"], int) and data["sold"] > 1_700_000_000   # תאריך המכירה
    assert any("נמכר" in a[3] for a in app.logs)


def test_agent_cannot_mark_others_sold(make_app):
    c, store, _ = mk(make_app, sess("agent", "חי חיים אלבז"))
    assert c.post("/v2/api/site/prop", json={"key": "b2", "sold": True}).status_code == 403
    assert store.puts == []


def test_sold_keeps_other_flags_and_can_clear(make_app):
    store = Store(); store.rows = [{"kind": "prop", "key": "a1", "data": {"first_hand": True}}]
    c, store, _ = mk(make_app, sess("agent", "חי חיים אלבז"), store)
    c.post("/v2/api/site/prop", json={"key": "a1", "sold": True})
    d = store.puts[-1][2]
    assert d["first_hand"] is True and d["sold"]
    store.rows = [{"kind": "prop", "key": "a1", "data": d}]
    c.post("/v2/api/site/prop", json={"key": "a1", "sold": False})
    assert store.puts[-1][2] == {"first_hand": True, "sold": False}


def test_still_one_field(make_app):
    c, _, _ = mk(make_app, sess())
    assert c.post("/v2/api/site/prop", json={"key": "a1", "sold": True, "hidden": True}).status_code == 400
