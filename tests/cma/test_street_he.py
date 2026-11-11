import datetime as dt
import cma


def _d(street, house, price, sqm=120, rooms=5):
    return {"street": street, "house": house, "city": "קרית ביאליק", "nb": "הפרפר", "deal_date": "2026-01-10",
            "rooms": rooms, "sqm": sqm, "price": price, "ppm": price // sqm, "ptype": "דירה"}


def test_he_prefix_matches_both_ways():
    deals = [_d("פטל", 31, 2100000), _d("פטל", 29, 2150000), _d("הפטל", 19, 2200000), _d("פטל", 33, 2050000)]
    for st in ("הפטל", "פטל"):
        subj = {"street": st, "house": 31, "city": "קרית ביאליק", "rooms": 5, "sqm": None, "ptype": "דירה"}
        res = cma.cma_compute(subj, deals, [], dt.date(2026, 11, 11))
        assert res and res["n_used"] == 4, st


def test_short_names_not_stripped():
    assert cma._skey("הדר") == "הדר"
    assert not cma._same_street({"street": ""}, {"street": "הפטל"})
