from site_api import can_edit_prop
from tests.siteweb.conftest import Store

ROWS = [{"מספר מודעה": "a1", "סוכן 1": "חי"}]
owns = lambda row, name, phones: row.get("סוכן 1") == name

def S(drole, name="x"):
    return {"name": name, "role": "agent" if drole == "agent" else "admin", "phone": "0500000000", "drole": drole}

def test_only_secretary_manager_dev_hide():
    assert can_edit_prop(S("secretary"), ROWS[0], owns, False)
    assert can_edit_prop(S("manager"), ROWS[0], owns, False)
    assert can_edit_prop(S("agent", name="x"), ROWS[0], owns, True)          # מפתח
    assert not can_edit_prop(S("agent", name="חי"), ROWS[0], owns, False)    # סוכן — גם לא לנכס שלו
    assert not can_edit_prop(S("accountant"), ROWS[0], owns, False)

def mk(make_app, s, store=None):
    store = store or Store()
    return make_app(store=store, _web_auth=lambda: s, fetch_sheet_rows=lambda: ROWS, _agent_owns_row=owns,
                    _is_dev=lambda p: False, _phones_for_name=lambda n: []).test_client(), store

def test_state_reports_permission(make_app):
    assert mk(make_app, S("secretary"))[0].get("/v2/api/site/state").get_json()["can_edit"] is True
    assert mk(make_app, S("agent", name="חי"))[0].get("/v2/api/site/state").get_json()["can_edit"] is False

def test_featured_removed(make_app):
    c, store = mk(make_app, S("secretary"))
    r = c.post("/v2/api/site/prop", json={"key": "a1", "featured": True}).get_json()
    assert r == {"ok": False, "reason": "bad_field"} and store.puts == []
    assert c.post("/v2/api/site/prop", json={"key": "a1", "hidden": True}).get_json()["ok"] is True
    assert store.puts[-1][2] == {"hidden": True}

def test_props_screen_has_no_featured_button():
    import pathlib
    src = pathlib.Path("effie_v2.py").read_text(encoding="utf-8")
    assert "מומלץ באתר" not in src and "SITE.can" in src
