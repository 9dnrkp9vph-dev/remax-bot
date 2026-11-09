# tests/kit/test_core.py — ליבה טהורה של תיק הפרזנטציה
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import kit_core as K

NOW = 1_800_000_000.0


def iso(sec):
    return dt.datetime.fromtimestamp(sec, dt.timezone.utc).isoformat()


def test_phones():
    assert K.phone9("054-444 8065") == "544448065"
    assert K.phone9("+972544448065") == "544448065"
    assert K.phone9("544448065") == "544448065"
    assert K.wa972("+972544448065") == "972544448065"
    assert K.wa972("054-444 8065") == "972544448065"
    assert K.phone9("12345") == ""
    assert K.wa972("12345") == ""
    assert K.phone9(None) == ""


def test_street_only():
    assert K.street_only("הנוטר 18") == "הנוטר"
    assert K.street_only("שדרות ההסתדרות 12א") == "שדרות ההסתדרות"
    assert K.street_only("עוזי חיטמן") == "עוזי חיטמן"
    assert K.street_only("הנוטר מס' 18/3") == "הנוטר"
    assert K.street_only("") == ""
    assert K.street_only("הנוטר 12 א") == "הנוטר"
    assert K.street_only("הנוטר 18, קרית ביאליק") == "הנוטר"
    assert K.street_only("הנוטר, קרית ביאליק") == "הנוטר"
    assert K.street_only("שדרות ההסתדרות הציונית העולמית 7 ב, חיפה") == "שדרות ההסתדרות הציונית העולמית"
    for raw, want in (("הנוטר 12 ב׳", "הנוטר"), ("הנוטר 12 א׳", "הנוטר"), ("בן גוריון 5 ב'", "בן גוריון"),
                      ("הנוטר 12-14", "הנוטר"), ("הנוטר 12 - 14", "הנוטר"), ("הרצל 3 / 7", "הרצל"),
                      ("הנוטר 18 דירה 4", "הנוטר"), ("הנוטר 12 קומה 3", "הנוטר"), ("ביאליק 12 כניסה ב", "ביאליק"),
                      ("18 הנוטר", "הנוטר"), ("הנוטר 12, קרית ביאליק", "הנוטר"), ("בגין12", "בגין"),
                      ("שדרות ירושלים", "שדרות ירושלים"), ('כ"ט בנובמבר', 'כ"ט בנובמבר'), ("הנוטר מס׳ 7", "הנוטר")):
        assert K.street_only(raw) == want, (raw, K.street_only(raw))


def test_eff_status():
    old = {"status": "pending", "sent_review_at": iso(NOW - 49 * 3600)}
    fresh = {"status": "pending", "sent_review_at": iso(NOW - 47 * 3600)}
    assert K.eff_status(old, NOW) == "expired"
    assert K.eff_status(fresh, NOW) == "pending"
    assert K.eff_status({"status": "approved", "sent_review_at": iso(NOW - 99 * 3600)}, NOW) == "approved"
    assert K.eff_status({"status": "pending"}, NOW) == "pending"


def test_decide():
    p = {"status": "pending", "sent_review_at": iso(NOW - 3600)}
    assert K.decide(p, "approve", "x", NOW) == ("approved", "אושר")
    assert K.decide(p, "reject", "x", NOW) == ("rejected", "נדחה")
    assert K.decide({"status": "approved"}, "approve", "x", NOW) == (None, "כבר אושר")
    assert K.decide({"status": "sent"}, "approve", "x", NOW) == (None, "כבר אושר")
    assert K.decide({"status": "rejected"}, "approve", "x", NOW) == (None, "כבר נדחה")
    ex = {"status": "pending", "sent_review_at": iso(NOW - 49 * 3600)}
    assert K.decide(ex, "approve", "x", NOW) == (None, "פג תוקף")


def test_owner_message():
    s = {"owner_first": "משה", "agent": "אוהד לוי", "office": "רימקס פמילי",
         "meet_at": "2026-11-11T17:00", "street": "הנוטר"}
    assert K.owner_message(s) == ("שלום משה, כאן אוהד לוי מרימקס פמילי. לקראת הפגישה שלנו ביום ד׳ 11/11 "
                                  "בשעה 17:00 הכנתי לך תיק אישי על הנכס שלך בהנוטר. אשמח שתעיף מבט לפני שנפגש.")
    s2 = dict(s, meet_at="2026-11-08T09:30")  # ראשון
    assert "ביום א׳ 08/11 בשעה 09:30" in K.owner_message(s2)
    s3 = dict(s, meet_at="2026-11-13T10:00")  # שישי
    assert "ביום ו׳ 13/11" in K.owner_message(s3)
    s4 = dict(s, meet_at="2026-11-14T10:00")  # שבת
    assert "ביום ש׳ 14/11" in K.owner_message(s4)
    s5 = dict(s, meet_at="")
    assert K.owner_message(s5) == ("שלום משה, כאן אוהד לוי מרימקס פמילי. הכנתי לך תיק אישי על הנכס שלך בהנוטר. "
                                   "אשמח שתעיף מבט לפני שנפגש.")


def test_file_name():
    assert K.file_name({"owner": "משה כהן"}) == "תיק אישי - משה כהן.pdf"


def test_view_add():
    v = K.view_add({}, 1000)
    assert v == {"first": 1000, "last": 1000, "opens": 1, "secs": 15}
    v = K.view_add(v, 1010)
    assert v["opens"] == 1 and v["secs"] == 30 and v["last"] == 1010 and v["first"] == 1000
    v = K.view_add(v, 1010 + 1801)
    assert v["opens"] == 2
    cap = {"first": 0, "last": 0, "opens": 1, "secs": 4 * 3600 - 5}
    assert K.view_add(cap, 10)["secs"] == 4 * 3600


def test_manual_validate():
    f = {"owner": "משה", "phone": "0544448065", "addr": "הנוטר 18", "city": "קרית ביאליק",
         "rooms": "5", "price": "2,350,000"}
    assert K.manual_validate(f) is None
    assert K.manual_validate({k: v for k, v in f.items() if k != "price"}) == "price"
    assert K.manual_validate(dict(f, owner="")) == "owner"
    assert K.manual_validate(dict(f, phone="05444")) == "phone"
    assert K.manual_validate(dict(f, phone="+972544448065")) is None
    assert K.manual_validate(dict(f, addr=" ")) == "addr"
    assert K.manual_validate(dict(f, rooms="")) == "rooms"


def test_kit_settings_social_fallback():
    cfg = {"v2_office": {"instagram": "https://instagram.com/x", "facebook": "http://bad"}, "v2_kit": {"facebook": "https://facebook.com/y"}}
    s = K.kit_settings(cfg)
    assert s["instagram"] == "https://instagram.com/x" and s["facebook"] == "https://facebook.com/y"
    assert K.kit_settings({"v2_office": {"facebook": "http://bad"}})["facebook"] == ""
