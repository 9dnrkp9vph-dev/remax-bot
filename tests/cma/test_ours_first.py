"""[13/11] אייל (עפרה חזה 18): עסקה שלנו נכנסת לעסקאות התיק לפני עסקאות אחרות — רק אם היא מהשנה האחרונה."""
import datetime as dt
import cma

T = dt.date(2026, 11, 13)


def _d(house, price, date, ours=False, nb="לב מוצקין"):
    return {"street": "עפרה חזה", "house": house, "city": "קרית מוצקין", "nb": nb, "deal_date": date,
            "rooms": 5, "sqm": 123, "price": price, "ppm": price // 123, "ptype": "דירה", "ours": ours}


SUBJ = {"street": "עפרה חזה", "house": 18, "city": "קרית מוצקין", "rooms": 5, "sqm": 132, "ptype": "דירה"}
NEAR = [_d(18, 1900000, "2026-07-19")] + [_d(14, 2050000 + i * 40000, "2026-0%d-10" % (i + 4)) for i in range(6)]


def _used(res):
    return [(c["house"], c["ours"]) for c in res["comps"] if c["used"]]


def test_recent_ours_enters_seven():
    res = cma.cma_compute(SUBJ, NEAR + [_d(12, 2160000, "2026-04-30", ours=True)], [], T)
    assert (12, True) in _used(res) and len(_used(res)) == 7


def test_old_ours_not_preferred():
    res = cma.cma_compute(SUBJ, NEAR + [_d(12, 2160000, "2025-06-30", ours=True)], [], T)
    assert (12, True) not in _used(res)


def test_ours_outlier_still_dropped():
    res = cma.cma_compute(SUBJ, NEAR + [_d(12, 3900000, "2026-04-30", ours=True)], [], T)
    assert (12, True) not in _used(res)


def test_without_ours_unchanged():
    res = cma.cma_compute(SUBJ, NEAR, [], T)
    assert len(_used(res)) == 7 and all(not o for _, o in _used(res))
