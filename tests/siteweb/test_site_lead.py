"""'סוכן AI אישי' (14/10): קוד ליד, פענוח הודעת הלקוח ונוסחי התשובה."""
from site_api import new_lead_code, parse_lead_message, lead_reply, lead_no_match, LEAD_ALPHABET

def test_code_shape():
    c = new_lead_code()
    assert len(c) == 4 and all(ch in LEAD_ALPHABET for ch in c)

def test_parse_lead_message():
    assert parse_lead_message("היי, אני מחפש/ת: 4 חדרים באפקה עד 2 מיליון\n(קוד 7K3F)") == {"q": "4 חדרים באפקה עד 2 מיליון", "code": "7K3F"}
    assert parse_lead_message("היי, אני מחפש/ת: דירה בים") == {"q": "דירה בים", "code": ""}
    assert parse_lead_message("  היי,  אני מחפשת:  קוטג'  ") == {"q": "קוטג'", "code": ""}
    for t in ("שלום, אני מחפש דירה", "בוקר טוב", "היי, אני מחפש/ת:", "", None, "תודה, היי, אני מחפש/ת: דירה"):
        assert parse_lead_message(t) is None

def test_texts():
    assert lead_reply("דנה", "רימקס פמילי", 4, "U", False).startswith("שלום דנה, כאן הסוכן האישי של רימקס פמילי.")
    assert "מצאתי 4 נכסים" in lead_reply("דנה", "X", 4, "U", False) and "ונחזור אליכם." in lead_reply("", "X", 4, "U", False)
    assert "מצאתי נכס אחד" in lead_reply("", "X", 1, "U", False) and lead_reply("", "X", 2, "U", False).startswith("שלום,")
    assert "עדכנתי לך את הדף האישי" in lead_reply("א", "X", 2, "U", True)
    assert "ונחזור אליכם עם אפשרויות" in lead_no_match("דנה", "X")

def test_lead_route_stores_code(make_app, monkeypatch):
    monkeypatch.setenv("SITE_KEY", "k")
    cfg = {}
    def mut(fn):
        fn(cfg); return True
    app = make_app(_config_mutate=mut, _load_config=lambda: cfg)
    c = app.test_client()
    assert c.post("/site/api/lead", json={"key": "x", "q": "a b"}).status_code == 403
    j = c.post("/site/api/lead", json={"key": "k", "q": "4 חדרים באפקה", "src": "home"}).get_json()
    assert j["ok"] and cfg["v2_site_leads"][j["code"]]["q"] == "4 חדרים באפקה"
    assert c.post("/site/api/lead", json={"key": "k", "q": " "}).get_json()["ok"] is False
    monkeypatch.setenv("SITE_LEADS", "0")
    assert c.post("/site/api/lead", json={"key": "k", "q": "דירה בים"}).get_json()["ok"] is False
