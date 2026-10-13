from site_api import prop_flags, can_edit_prop
from tests.siteweb.conftest import Store

ROWS = [{"מספר מודעה": "a1", "סוכן 1": "חי חיים אלבז"}, {"מספר מודעה": "b2", "סוכן 1": "רפי"}]
owns = lambda row, name, phones: row.get("סוכן 1") == name

def sess(role="agent", name="חי חיים אלבז", dev=False):
    return {"name": name, "role": role, "phone": "0521112222", "drole": "developer" if dev else ("manager" if role == "admin" else role)}

def test_prop_flags():
    rows = [{"kind": "prop", "key": "a", "data": {"hidden": True}}, {"kind": "prop", "key": "b", "data": {"featured": True}},
            {"kind": "page", "key": "pages", "data": {}}]
    assert prop_flags(rows) == ({"a"}, ["b"])

def test_can_edit_prop():
    assert can_edit_prop(sess(role="admin", name="x"), ROWS[1], owns, False)
    assert can_edit_prop(sess(name="x"), ROWS[1], owns, True)            # מפתח
    assert can_edit_prop(sess(), ROWS[0], owns, False)
    assert not can_edit_prop(sess(), ROWS[1], owns, False)

def mk(make_app, s, store=None):
    store = store or Store()
    app = make_app(store=store, _web_auth=lambda: s, fetch_sheet_rows=lambda: ROWS, _agent_owns_row=owns,
                   _is_dev=lambda ph: False, _phones_for_name=lambda n: [])
    return app.test_client(), store, app

def test_state_and_toggle(make_app):
    c, store, app = mk(make_app, sess())
    assert c.get("/v2/api/site/state").get_json() == {"ok": True, "hidden": [], "featured": [], "max_featured": 6, "available": True}
    r = c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True}).get_json()
    assert r["ok"] and store.puts[-1][:3] == ("prop", "a1", {"hidden": True, "featured": False})
    assert any("הסתרת נכס" in a[3] for a in app.logs)
    assert c.get("/v2/api/site/state").get_json()["hidden"] == ["a1"]

def test_foreign_and_missing(make_app):
    c, store, _ = mk(make_app, sess())
    assert c.post("/v2/api/site/prop", json={"key": "b2", "hidden": True}).status_code == 403
    assert c.post("/v2/api/site/prop", json={"key": "zz", "hidden": True}).status_code == 404
    assert store.puts == []

def test_unauth(make_app):
    c, _, _ = mk(make_app, None)
    assert c.get("/v2/api/site/state").status_code == 401

def test_featured_cap(make_app):
    store = Store()
    store.rows = [{"kind": "prop", "key": "k%d" % i, "data": {"featured": True}} for i in range(6)]
    active = ROWS + [{"מספר מודעה": "k%d" % i, "סוכן 1": "x"} for i in range(6)]   # 6 מומלצים פעילים
    app = make_app(store=store, _web_auth=lambda: sess(role="admin", name="x"), fetch_sheet_rows=lambda: active,
                   _agent_owns_row=owns, _is_dev=lambda ph: False, _phones_for_name=lambda n: [])
    c = app.test_client()
    r = c.post("/v2/api/site/prop", json={"key": "a1", "featured": True}).get_json()
    assert r == {"ok": False, "reason": "featured_full"}

def test_table_missing(make_app):
    c, store, _ = mk(make_app, sess(), Store(available=False))
    assert c.get("/v2/api/site/state").get_json()["available"] is False
    assert c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True}).get_json() == {"ok": False, "reason": "no_table"}

def test_search_excludes_hidden(make_app, monkeypatch):
    monkeypatch.setenv("SITE_KEY", "s")
    store = Store(); store.rows = [{"kind": "prop", "key": "a1", "data": {"hidden": True}}]
    app = make_app(store=store, _parse_props_query=lambda q: {"summary_he": "x"},
                   search_listings_in_sheet=lambda p: [(9, ROWS[0], 0), (8, ROWS[1], 0)])
    assert app.test_client().post("/site/api/search", json={"key": "s", "q": "x"}).get_json()["keys"] == ["b2"]
