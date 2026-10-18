from site_api import prop_flags
from tests.siteweb.conftest import Store

ROWS = [{"מספר מודעה": "a1", "סוכן 1": "חי חיים אלבז", "כתובת": "אהוד מנור"}, {"מספר מודעה": "b2", "סוכן 1": "רפי"}]
owns = lambda row, name, phones: row.get("סוכן 1") == name

def sess(drole="secretary", name="מזכירה"):
    return {"name": name, "role": "agent" if drole == "agent" else "admin", "phone": "0521112222", "drole": drole}

def test_prop_flags():
    rows = [{"kind": "prop", "key": "a", "data": {"hidden": True}}, {"kind": "page", "key": "pages", "data": {}}]
    assert prop_flags(rows)[0] == {"a"}

def mk(make_app, s, store=None):
    store = store or Store()
    app = make_app(store=store, _web_auth=lambda: s, fetch_sheet_rows=lambda: ROWS, _agent_owns_row=owns,
                   _is_dev=lambda ph: False, _phones_for_name=lambda n: [])
    return app.test_client(), store, app

def test_state_and_toggle(make_app):
    c, store, app = mk(make_app, sess())
    assert c.get("/v2/api/site/state").get_json() == {"ok": True, "hidden": [], "can_edit": True, "first_hand": [], "available": True}
    r = c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True}).get_json()
    assert r["ok"] and store.puts[-1][:3] == ("prop", "a1", {"hidden": True})
    assert any("הסתרת נכס" in a[3] for a in app.logs)
    assert c.get("/v2/api/site/state").get_json()["hidden"] == ["a1"]

def test_agent_cannot_and_missing(make_app):
    c, store, _ = mk(make_app, sess("agent", "חי חיים אלבז"))
    assert c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True}).status_code == 403
    c, store2, _ = mk(make_app, sess())
    assert c.post("/v2/api/site/prop", json={"key": "zz", "hidden": True}).status_code == 404
    assert store.puts == [] and store2.puts == []

def test_unauth(make_app):
    c, _, _ = mk(make_app, None)
    assert c.get("/v2/api/site/state").status_code == 401

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
