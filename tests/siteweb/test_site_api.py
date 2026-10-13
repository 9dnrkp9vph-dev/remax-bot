import site_api
from site_api import key_ok, search_result, form_email

def test_key_ok():
    assert key_ok("k", "k") is True
    assert not key_ok("", "") and not key_ok("x", "k") and not key_ok("k", "")

def row(lid, **kw):
    r = {"מספר מודעה": lid, "כתובת": "אהוד מנור", "טלפון 1": "0521234567"}
    r.update(kw); return r

def test_search_result_filters():
    m = [(90, row("a"), 0), (80, row("b", **{"ירד מפרסום": "05/10/2026"}), 0), (70, row("c"), 0), (60, row(""), 0), (50, row("a"), 0)]
    out = search_result({"summary_he": "דירה 3 חדרים"}, m, {"c"})
    assert out == {"ok": True, "keys": ["a"], "summary": "דירה 3 חדרים"}

def test_form_email_escapes():
    s, h, t = form_email("value", {"name": "<b>דנה</b>", "phone": "0521234567", "address": "הנרקיס 5", "x": "zz"}, "רימקס פמילי")
    assert s == "פנייה מהאתר — הערכת שווי — <b>דנה</b>"
    assert "&lt;b&gt;" in h and "<b>דנה</b>" not in h and "zz" not in h and "0521234567" in t

def test_search_route_key(make_app, monkeypatch):
    app = make_app(_parse_props_query=lambda q: {"summary_he": "דירה"},
                   search_listings_in_sheet=lambda p: [(90, row("a"), 0)])
    c = app.test_client()
    monkeypatch.delenv("SITE_KEY", raising=False)
    assert c.post("/site/api/search", json={"key": "", "q": "x"}).status_code == 403
    monkeypatch.setenv("SITE_KEY", "secret")
    assert c.post("/site/api/search", json={"key": "nope", "q": "x"}).status_code == 403
    r = c.post("/site/api/search", json={"key": "secret", "q": "3 חדרים"})
    assert r.status_code == 200 and r.get_json() == {"ok": True, "keys": ["a"], "summary": "דירה"}
    body = r.get_data(as_text=True)
    assert "0521234567" not in body and "אהוד" not in body

def test_form_route(make_app, monkeypatch):
    monkeypatch.setenv("SITE_KEY", "secret")
    sent = []
    app = make_app(_report_send_email=lambda s, h, t: (sent.append(s) or True, ""))
    c = app.test_client()
    r = c.post("/site/api/form", json={"key": "secret", "kind": "value", "fields": {"name": "דנה", "phone": "0521234567"}})
    assert r.get_json() == {"ok": True} and sent and app.logs
    assert c.post("/site/api/form", json={"key": "secret", "kind": "zzz", "fields": {}}).status_code == 400
    app2 = make_app(_report_send_email=lambda s, h, t: (False, "no channel"))
    assert app2.test_client().post("/site/api/form", json={"key": "secret", "kind": "contact", "fields": {"name": "א"}}).get_json() == {"ok": False}
