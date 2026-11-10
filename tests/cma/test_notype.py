"""עסקאות מבוט מדלן מגיעות בלי סוג נכס — נספרות כדירה (דן 39, 10/11)."""
import datetime, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import cma


def _row(i, house, rooms, sqm, price, d, ptype=""):
    return {"id": i, "source": "madlan", "nb": "קרית ביאליק", "deal_date": d, "city": "קרית ביאליק",
            "street": "דן", "house": house, "ptype": ptype, "rooms": rooms, "sqm": sqm, "floor": "1",
            "price": price, "ppm": round(price / sqm), "bad": ""}


def test_untyped_deals_count_as_apartment():
    rows = [_row(i, 30 + i, 4, 90, 1400000 + i * 10000, "2025-0%d-01" % (i + 1)) for i in range(5)]
    subj = {"street": "דן", "house": 39, "city": "קרית ביאליק", "rooms": 4.0, "sqm": 90,
            "ptype": "דירה", "price": None, "key": ""}
    res = cma.cma_compute(subj, rows, [], datetime.date(2026, 11, 10))
    assert res and res["range"], res


def test_untyped_not_used_for_house():
    rows = [_row(i, 30 + i, 4, 90, 1400000, "2025-0%d-01" % (i + 1)) for i in range(5)]
    subj = {"street": "דן", "house": 39, "city": "קרית ביאליק", "rooms": 4.0, "sqm": 90,
            "ptype": "קוטג'", "price": None, "key": ""}
    assert cma.cma_compute(subj, rows, [], datetime.date(2026, 11, 10)) is None
