"""[13/11] אייל: 'שהמערכת תרוץ אוטומטית' — כשאין מספיק עסקאות דומות בדיוק, מרחיבים בשלבים
(בלי שטח → דירות רגילות → כל העיר) ומציינים לפי מה חושב, במקום להחזיר None ולחכות לבוט."""
import datetime as dt
import cma

T = dt.date(2026, 11, 13)


def _d(street, house, price, sqm=110, rooms=5, ptype="דירה", nb="נווה גנים", city="קרית מוצקין"):
    return {"street": street, "house": house, "city": city, "nb": nb, "deal_date": "2026-03-10",
            "rooms": rooms, "sqm": sqm, "price": price, "ppm": price // sqm, "ptype": ptype}


def _subj(**k):
    s = {"street": "הערבה", "house": 4, "city": "קרית מוצקין", "rooms": 5, "sqm": None, "ptype": "דירה"}
    s.update(k)
    return s


def test_strict_result_has_no_fallback():
    deals = [_d("הערבה", 2, 2000000 + i * 10000) for i in range(5)]
    res = cma.cma_auto(_subj(), deals, [], T)
    assert res and not res.get("fallback")


def test_area_dropped_when_sizes_far():
    deals = [_d("הערבה", 2, 2000000 + i * 10000, sqm=110) for i in range(5)]
    assert cma.cma_compute(_subj(sqm=257), deals, [], T) is None
    res = cma.cma_auto(_subj(sqm=257), deals, [], T)
    assert res and res["fallback"] == "nosqm" and res["basis"] == "price" and res["fallback_text"]


def test_garden_falls_back_to_regular_apartments():
    deals = [_d("הערבה", 2, 2000000 + i * 10000) for i in range(5)] + [_d("הרב קוק", 2, 2800000, ptype="דירת גן")]
    res = cma.cma_auto(_subj(ptype="דירת גן", sqm=257), deals, [], T)
    assert res and res["fallback"] == "type" and "רגילות" in res["fallback_text"]
    assert res["n_used"] == 5


def test_city_wide_when_neighborhood_empty():
    deals = [_d("ויצמן", i, 1900000 + i * 10000, nb="מוצקין הוותיקה") for i in range(1, 6)]
    deals.append(_d("ויצמן", 9, 1500000, nb="אחר", city="קרית ביאליק"))
    res = cma.cma_auto(_subj(), deals, [], T)
    assert res and res["fallback"] == "city" and res["level"] == "city"
    assert res["n_used"] == 5   # עסקה מעיר אחרת לא נכנסת


def test_nothing_at_all_is_none():
    assert cma.cma_auto(_subj(), [], [], T) is None
    assert cma.cma_auto(_subj(), [_d("ויצמן", 1, 1900000, city="קרית ביאליק")], [], T) is None


def test_cma_full_uses_auto(monkeypatch):
    deals = [_d("הערבה", 2, 2000000 + i * 10000, sqm=110) for i in range(5)]
    monkeypatch.setattr(cma, "_cached_inputs", lambda G: (deals, [], {"הערבה"}))
    monkeypatch.setattr(cma, "_today_il", lambda: T)
    res = cma.cma_full({}, {"רחוב": "הערבה 4", "עיר / ישוב": "קרית מוצקין", "חדרים": "5", "sqm": "257", "ptype": "דירת גן"})
    assert res and res["fallback"] in ("nosqm", "type")
