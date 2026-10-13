import threading
import site_api
from site_api import can_edit_prop
from tests.siteweb.conftest import Store

ROWS = [{"מספר מודעה": "a1", "סוכן 1": "חי"}, {"מספר מודעה": "b2", "סוכן 1": "רפי"}]
owns = lambda row, name, phones: row.get("סוכן 1") == name

def S(drole, role="admin", name="x"):
    return {"name": name, "role": role, "phone": "0500000000", "drole": drole}

# 1: מסך "האתר" — מנהל/מפתח בלבד (לא הנה"ח ולא מזכירה, שגם הן role=admin באפי).
#    "הסתר מהאתר" בכרטיס — המזכירה כן (אייל 13/10: "הכל דרך המזכירה"); הנה"ח לא.
def test_accountant_and_secretary_cannot_manage(make_app):
    assert not can_edit_prop(S("accountant"), ROWS[1], owns, False)
    assert can_edit_prop(S("secretary"), ROWS[1], owns, False)
    for dr in ("accountant", "secretary"):
        app = make_app(store=Store(), _web_auth=lambda dr=dr: S(dr), _load_config=lambda: {"agents": []},
                       fetch_sheet_rows=lambda: ROWS, _is_dev=lambda p: False, _name_key=lambda n: n)
        assert app.test_client().get("/v2/api/site/settings").status_code == 403
    assert can_edit_prop(S("manager"), ROWS[1], owns, False)

def test_menu_gated_on_manager_drole():
    import pathlib
    src = pathlib.Path("effie_v2.py").read_text(encoding="utf-8")
    assert "el('menuSite')" in src and "j.drole === 'manager'" in src

# 3: חיפוש מהאתר מוגבל גם באפי — עד 2 במקביל ותקרה לדקה
def _search_app(make_app, monkeypatch, per_min="60"):
    monkeypatch.setenv("SITE_KEY", "k"); monkeypatch.setenv("SITE_SEARCH_PER_MIN", per_min)
    return make_app(_parse_props_query=lambda q: {"summary_he": "x"}, search_listings_in_sheet=lambda p: [])

def test_search_concurrency_cap(make_app, monkeypatch):
    app = _search_app(make_app, monkeypatch)
    sem = app.site_search_sem
    assert sem.acquire(blocking=False) and sem.acquire(blocking=False)
    try:
        assert app.test_client().post("/site/api/search", json={"key": "k", "q": "x"}).get_json() == {"ok": False, "reason": "busy"}
    finally:
        sem.release(); sem.release()

def test_search_global_minute_cap(make_app, monkeypatch):
    app = _search_app(make_app, monkeypatch, per_min="2")
    c = app.test_client()
    res = [c.post("/site/api/search", json={"key": "k", "q": "q%d" % i}).get_json() for i in range(3)]
    assert res[0]["ok"] and res[1]["ok"] and res[2] == {"ok": False, "reason": "busy"}

# 4: שם עיר מיד2 מוצג מוגן במסך האתר
def test_site_screen_escapes_labels():
    assert "'<div><label for=\"' + id + '\">' + esc(label)" in site_api.V2_SITE_HTML
