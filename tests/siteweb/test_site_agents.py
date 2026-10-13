from site_api import agents_directory

def test_agents_directory_merges_sources():
    full = {"חיחייםאלבז": {"name": "חי חיים אלבז", "phone": "0521112222", "license": ""},
            "קוביחמו": {"name": "קובי חמו", "phone": "0543334444", "license": "777"}}
    vph = {"חי חיים אלבז": "0529125944"}
    cfg = {"agents": [{"name": "חי חיים אלבז", "aliases": ["חי אלבז"]}, {"name": "מנהל בדיקה"}, {"name": "נמחק"}],
           "v2_licenses": {"521112222": "12345"}, "removedAgents": ["נמחק"]}
    out = {a["name"]: a for a in agents_directory(full, vph, cfg, lambda n: n.replace(" ", ""))}
    assert out["חי חיים אלבז"] == {"name": "חי חיים אלבז", "aliases": ["חי אלבז"], "phone": "0521112222",
                                    "vphone": "0529125944", "license": "12345"}
    assert out["קובי חמו"]["license"] == "777" and out["קובי חמו"]["vphone"] == ""
    assert "מנהל בדיקה" in out and "נמחק" not in out

def test_agents_route_keyed(make_app, monkeypatch):
    monkeypatch.setenv("SITE_KEY", "k")
    app = make_app(fetch_agents_full=lambda: {"x": {"name": "רפי", "phone": "0501231234", "license": ""}},
                   fetch_agent_virtual_phones=lambda: {}, _load_config=lambda: {}, _name_key=lambda n: n)
    c = app.test_client()
    assert c.post("/site/api/agents", json={"key": "bad"}).status_code == 403
    j = c.post("/site/api/agents", json={"key": "k"}).get_json()
    assert j["ok"] and j["agents"][0]["phone"] == "0501231234"
