"""שליחת נכס ללקוח עם תמונות (אייל 01/11): בלי שם הסוכן, בלי מספר בית, בלי טלפונים וקישורים."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import prop_share as ps

ROW = {"סוג נכס": "דירה", "חדרים": "4.0", 'מ"ר': "110", "קומה": "3", "כתובת": "עוזי חיטמן", "מספר בית": "13",
       "שכונה": "נאות אפק", "עיר / ישוב": "קרית ביאליק", "מחיר": "1890000", "סוכן 1": "חי חיים אלבז",
       "_desc_ae": "דירה מהממת בעוזי חיטמן 13, התקשרו לחי חיים אלבז 054-6626165 או https://www.yad2.co.il/x",
       "תמונות": '["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg", "https://img.yad2.co.il/a.jpg"]'}


def _t(row=ROW):
    return ps.share_text(row, lambda d: str(d or ""), lambda r: ["מעלית", "ממ\"ד"])


def test_text_has_the_details():
    t = _t()
    assert "דירה 4 חדרים למכירה" in t and "110 מ\"ר" in t and "קומה 3" in t
    assert "עוזי חיטמן, נאות אפק, קרית ביאליק" in t
    assert "1,890,000 ₪" in t and "מעלית · ממ\"ד" in t and "דירה מהממת" in t


def test_text_hides_agent_house_phone_links():
    t = _t()
    assert "13" not in t and "חי חיים אלבז" not in t and "חיים אלבז" not in t and "054" not in t
    assert "http" not in t and "yad2" not in t


def test_rent_says_per_month():
    t = _t(dict(ROW, **{"סוג עסקה": "השכרה", "מחיר": "5200"}))
    assert "להשכרה" in t and "5,200 ₪ לחודש" in t


def test_images_unique_and_capped():
    assert ps.share_images(ROW) == ["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg"]
    many = dict(ROW, **{"תמונות": ",".join("https://x/%d.jpg" % i for i in range(20))})
    assert len(ps.share_images(many)) == 10


def test_no_emoji():
    assert not any(ord(ch) > 0x2600 and ord(ch) < 0x1FAFF for ch in _t())


def test_agent_first_name_only_as_whole_word():
    r = dict(ROW, **{"_desc_ae": "קרוב לחיפה ולמרכז, חי לבד בקומה"})
    t = _t(r)
    assert "לחיפה" in t


def _app(auth=True):
    from flask import Flask
    app = Flask("t")
    logged = []
    G = {"fetch_sheet_rows": lambda: [ROW], "fetch_sheet_rows_deal": lambda lbl: [], "OFFICE_DEALS": {"rent": "השכרה"},
         "_prop_price_key": lambda r: "L:abc" if r is ROW else "", "_row_feats": lambda r: [],
         "_web_auth": (lambda: {"name": "חי חיים אלבז", "role": "agent", "phone": "546626165"}) if auth else (lambda: None),
         "_log_activity": lambda *a: logged.append(a)}
    ps.register(app, G)
    return app.test_client(), logged


def test_route_returns_text_and_image_urls_and_logs():
    c, logged = _app()
    j = c.get("/v2/api/prop/share?key=L:abc").get_json()
    assert j["ok"] and "13" not in j["text"] and len(j["images"]) == 2
    assert logged and logged[0][3] == "שליחת נכס ללקוח" and "2 תמונות" in logged[0][4]


def test_route_requires_login_and_known_key():
    c, _ = _app(auth=False)
    assert c.get("/v2/api/prop/share?key=L:abc").status_code == 401
    assert c.get("/v2/api/prop/share/img?key=L:abc&i=0").status_code == 401
    c, _ = _app()
    assert c.get("/v2/api/prop/share?key=nope").status_code == 404
    assert c.get("/v2/api/prop/share/img?key=L:abc&i=5").status_code == 404


def test_image_proxy_fetches_and_converts(monkeypatch):
    calls = []
    monkeypatch.setattr(ps, "soc_fetch_jpeg", lambda http, url, sq: calls.append((url, sq)) or b"JPG")
    c, _ = _app()
    r = c.get("/v2/api/prop/share/img?key=L:abc&i=1")
    assert r.status_code == 200 and r.data == b"JPG" and calls == [("https://img.yad2.co.il/b.jpg", False)]
    c.get("/v2/api/prop/share/img?key=L:abc&i=1")
    assert len(calls) == 1   # מטמון
