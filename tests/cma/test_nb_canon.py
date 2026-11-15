import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cma


def test_adds_city():
    assert cma.nb_canon("מרכז העיר", "קרית אתא") == "מרכז העיר, קרית אתא"


def test_keeps_when_city_inside():
    assert cma.nb_canon("מרכז העיר, קרית אתא", "קרית אתא") == "מרכז העיר, קרית אתא"
    assert cma.nb_canon("בית וגן, קרית אתא", "ק. אתא") == "בית וגן, קרית אתא"
    assert cma.nb_canon("קרית חיים מזרחית, חיפה", "חיפה") == "קרית חיים מזרחית, חיפה"


def test_empty():
    assert cma.nb_canon("", "קרית אתא") == ""
    assert cma.nb_canon("מרכז העיר", "") == "מרכז העיר"


def test_old_and_new_rows_merge_in_compute():
    import datetime as dt
    today = dt.date(2026, 11, 15)
    rows = []
    for i, nb in enumerate(["מרכז העיר"] * 3 + ["מרכז העיר, קרית אתא"] * 3):
        rows.append({"source": "yad2", "nb": cma.nb_canon(nb, "קרית אתא"), "city": "קרית אתא",
                     "street": "סוקולוב%d" % i, "house": 10, "ptype": "דירה בבית קומות", "rooms": 4,
                     "sqm": 100, "price": 1400000 + i * 10000, "deal_date": "2026-0%d-01" % (i + 1), "bad": ""})
    assert len({r["nb"] for r in rows}) == 1
