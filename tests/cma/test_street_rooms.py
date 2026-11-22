"""[22/11] אייל (תיק דורין, הברוש): עסקאות באותו רחוב עם הפרש של עד חדר אחד נכנסות לפני עסקאות בשכונה
עם מספר חדרים מדויק. דירת 4 חד' בהברוש קיבלה רק את הברוש 4 — כל שאר הרחוב 5 חד'."""
import datetime as dt
import cma

T = dt.date(2026, 11, 22)
NB = "נווה גנים, קרית מוצקין"


def _d(street, house, rooms, sqm, price, date):
    return {"street": street, "house": house, "city": "קרית מוצקין", "nb": NB, "deal_date": date,
            "rooms": rooms, "sqm": sqm, "price": price, "ppm": price // sqm, "ptype": "דירה"}


BROSH = [_d("הברוש", 4, 4, 109, 2000000, "2026-04-30"), _d("הברוש", 6, 5, 127, 2420000, "2026-08-12"),
         _d("הברוש", 9, 5, 122, 2340000, "2025-12-29"), _d("הברוש", 11, 5, 125, 2400000, "2025-11-06")]
NBRS = [_d("הדקל", h, 4, 108, 1950000 + h * 10000, "2026-0%d-10" % (h % 9 + 1)) for h in range(1, 9)]
SUBJ = {"street": "הברוש", "house": 5, "city": "קרית מוצקין", "rooms": 4, "sqm": 110, "ptype": "דירה"}


def _used(res):
    return [(c["street"], c["house"]) for c in res["comps"] if c["used"]]


def test_street_plus_one_room_before_neighborhood():
    res = cma.cma_compute(SUBJ, BROSH + NBRS, [], T)
    used = _used(res)
    assert ("הברוש", 6) in used and ("הברוש", 9) in used and ("הברוש", 11) in used and ("הברוש", 4) in used
    assert len(used) == 7


def test_street_two_rooms_off_not_in():
    far = [_d("הברוש", 13, 6, 112, 2300000, "2026-02-01")]
    res = cma.cma_compute(SUBJ, BROSH + far + NBRS, [], T)
    assert ("הברוש", 13) not in [(c["street"], c["house"]) for c in res["comps"]]


def test_neighborhood_still_exact_first():
    nb5 = [_d("הדקל", 20 + i, 5, 110, 2100000, "2026-06-01") for i in range(3)]
    res = cma.cma_compute(SUBJ, BROSH[:1] + NBRS + nb5, [], T)
    assert all(c["rooms"] == 4 for c in res["comps"] if c["used"])
