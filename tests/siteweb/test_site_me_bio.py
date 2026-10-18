"""סוכן עורך את הטקסט עליו באתר מהאזור האישי (אייל 18/10)."""
from tests.siteweb.conftest import Store
from tests.siteweb.test_site_props import sess

CFG = {"agents": [{"name": "עוז דנילוב"}]}


def mk(make_app, s, store=None):
    store = store or Store()
    app = make_app(store=store, _web_auth=lambda: s, _load_config=lambda: CFG,
                   _name_key=lambda n: "".join(str(n or "").split()),
                   _display_name_for=lambda n, p: n)
    return app.test_client(), store, app


def test_get_empty_and_save_keeps_order_and_shown(make_app):
    store = Store(); store.rows = [{"kind": "agent", "key": "עוז דנילוב", "data": {"shown": True, "order": 3, "bio": "ישן"}}]
    c, store, app = mk(make_app, sess("agent", "עוז דנילוב"), store)
    j = c.get("/v2/api/me/bio").get_json()
    assert j == {"ok": True, "agent": True, "bio": "ישן", "max": 1500}
    r = c.post("/v2/api/me/bio", json={"bio": "שורה א\nשורה ב"}).get_json()
    assert r["ok"] and store.puts[-1][:3] == ("agent", "עוז דנילוב", {"shown": True, "order": 3, "bio": "שורה א\nשורה ב"})
    assert any("טקסט" in a[3] for a in app.logs)


def test_new_agent_row(make_app):
    c, store, _ = mk(make_app, sess("agent", "עוז  דנילוב"))
    assert c.post("/v2/api/me/bio", json={"bio": "x" * 2000}).get_json()["ok"]
    assert store.puts[-1][1] == "עוז דנילוב" and len(store.puts[-1][2]["bio"]) == 1500


def test_not_an_agent(make_app):
    c, store, _ = mk(make_app, sess("manager", "מנהל"))
    assert c.get("/v2/api/me/bio").get_json()["agent"] is False
    assert c.post("/v2/api/me/bio", json={"bio": "x"}).status_code == 400 and store.puts == []


def test_unauth(make_app):
    c, _, _ = mk(make_app, None)
    assert c.get("/v2/api/me/bio").status_code == 401
