"""לחיצות וואטסאפ/טלפון לסוכן באתר → יומן אפי (אייל 31/10: 'למה לקוחות לא משאירים פרטים באתר?')."""
import site_api
from site_api import contact_detail


def test_detail_format():
    assert contact_detail({"agent": "חי חיים אלבז", "listing": "גושן 5, קרית מוצקין", "src": "google"}) == \
        "חי חיים אלבז · גושן 5, קרית מוצקין · גוגל"
    assert contact_detail({"page": "/צוות/x", "src": "zzz"}) == "המשרד · /צוות/x · ישיר"
    assert contact_detail({"agent": "א · ב\nג"}) == "א   ב ג · — · ישיר"


def test_route(make_app, monkeypatch):
    monkeypatch.setenv("SITE_KEY", "k")
    app = make_app(); c = app.test_client()
    assert c.post("/site/api/contact", json={"kind": "wa"}).status_code == 403
    assert c.post("/site/api/contact", json={"key": "k", "kind": "mail"}).status_code == 400
    r = c.post("/site/api/contact", json={"key": "k", "kind": "wa", "agent": "רפי", "listing": "הנרקיס 5", "src": "facebook"})
    assert r.get_json() == {"ok": True}
    assert app.logs == [("אתר", "site", "", "לחיצה מהאתר — וואטסאפ לסוכן", "רפי · הנרקיס 5 · פייסבוק")]
    c.post("/site/api/contact", json={"key": "k", "kind": "tel"})
    assert app.logs[-1][3] == "לחיצה מהאתר — טלפון לסוכן"
