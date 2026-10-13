from site_api import clean_settings
from tests.siteweb.conftest import Store

NAMES = ["חי חיים אלבז", "רפי דה פיצ'וטו"]

def test_clean_settings_rules():
    body = {"pages": {"hero_sub": "x" * 900, "approach": "<script>alert(1)</script>שלום", "city:קרית ביאליק": "עיר יפה", "bogus": "z"},
            "branches": [{"name": "ביאליק", "phone": "04-6000800"}, {"name": "רע", "phone": "abc"}],
            "social": {"facebook": "javascript:alert(1)", "instagram": "https://www.instagram.com/remax.family", "youtube": "https://evil.com/x"},
            "agents": {"חי חיים אלבז": {"shown": False, "order": 3, "bio": "ב" * 900}, "לא קיים": {"shown": True}}}
    pages, branches, social, agents, errors = clean_settings(body, NAMES)
    assert len(pages["hero_sub"]) == 220 and "<" not in pages["approach"] and "bogus" not in pages
    assert pages["city:קרית ביאליק"] == "עיר יפה"
    assert branches == [{"name": "ביאליק", "phone": "046000800"}] and "branches" in errors
    assert social == {"instagram": "https://www.instagram.com/remax.family"} and "facebook" in errors and "youtube" in errors
    assert agents == {"חי חיים אלבז": {"shown": False, "order": 3, "bio": "ב" * 300}}

def mk(make_app, role, store=None):
    s = {"name": "x", "role": role, "phone": "0500000000", "drole": "manager" if role == "admin" else role}
    store = store or Store()
    cfg = {"agents": [{"name": n} for n in NAMES], "removedAgents": []}
    rows = [{"מספר מודעה": "a1", "סוכן 1": "חי חיים אלבז", "עיר / ישוב": "קרית ביאליק"}]
    app = make_app(store=store, _web_auth=lambda: s, _load_config=lambda: cfg, fetch_sheet_rows=lambda: rows,
                   _is_dev=lambda ph: False, _name_key=lambda n: n.replace(" ", ""))
    return app.test_client(), store, app

def test_settings_admin_only(make_app):
    c, store, _ = mk(make_app, "agent")
    assert c.get("/v2/api/site/settings").status_code == 403
    assert c.post("/v2/api/site/settings", json={}).status_code == 403
    assert store.puts == []

def test_settings_roundtrip(make_app):
    c, store, app = mk(make_app, "admin")
    j = c.get("/v2/api/site/settings").get_json()
    assert j["ok"] and [a["name"] for a in j["agents"]] == NAMES and j["agents"][0]["count"] == 1 and j["cities"] == ["קרית ביאליק"]
    r = c.post("/v2/api/site/settings", json={"pages": {"hero_sub": "חדש"}, "social": {"instagram": "https://instagram.com/x"},
                                               "branches": [{"name": "ביאליק", "phone": "046000800"}],
                                               "agents": {"רפי דה פיצ'וטו": {"shown": False, "order": 1, "bio": "ותיק"}}}).get_json()
    assert r["ok"] and r["errors"] == {}
    kinds = {(k, key) for k, key, d, by in store.puts}
    assert ("page", "pages") in kinds and ("page", "social") in kinds and ("page", "branches") in kinds and ("agent", "רפי דה פיצ'וטו") in kinds
    j = c.get("/v2/api/site/settings").get_json()
    assert j["pages"]["hero_sub"] == "חדש" and j["agents"][1]["shown"] is False
    assert any("עדכון הגדרות" in a[3] for a in app.logs)

def test_settings_errors_not_saved(make_app):
    c, store, _ = mk(make_app, "admin")
    r = c.post("/v2/api/site/settings", json={"social": {"facebook": "javascript:x"}}).get_json()
    assert r["ok"] is False and "facebook" in r["errors"] and store.puts == []

def test_site_page(make_app):
    c, _, _ = mk(make_app, "admin")
    h = c.get("/v2/site").get_data(as_text=True)
    assert "הצוות באתר" in h and 'dir="rtl"' in h
