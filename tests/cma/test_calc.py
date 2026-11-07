"""CMA — שיוך העסקאות שלנו וחישוב הטווח (תוכנית 2026-11-06-cma, משימה 2).
הנתונים: עסקאות 5 חדרים אמיתיות במנחם בגין, קרית מוצקין (טבלת מדלן שאייל הוריד 06/11)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import cma  # noqa: E402

TODAY = dt.date(2026, 11, 6)
KNOWN = {"מנחם בגין", "תמרי נחמיה"}
NB = "נווה גנים ומוצקין הצעירה"


def m(house, date, price, sqm, rooms=5, ptype="דירה", street="מנחם בגין", floor="3", bad="", nb=NB):
    return {"source": "madlan", "nb": nb, "deal_date": date, "city": "קרית מוצקין", "street": street,
            "house": house, "project": "", "ptype": ptype, "rooms": rooms, "sqm": sqm, "floor": floor,
            "price": price, "ppm": round(price / sqm) if sqm else None, "bad": bad,
            "uploaded_at": "2026-11-06T10:00:00+00:00", "ours": False}


BEGIN5 = [m(10, "2025-01-08", 1800000, 102), m(16, "2026-02-26", 1500000, 111), m(16, "2025-10-20", 2100000, 182),
          m(18, "2025-12-21", 1650000, 122), m(6, "2025-02-03", 1850000, 102), m(25, "2024-12-24", 2030000, 121),
          m(28, "2026-06-30", 2270000, 93), m(31, "2025-08-31", 2450000, 146), m(32, "2024-03-28", 1900000, 102),
          m(34, "2025-01-01", 1800007, 107), m(36, "2026-08-31", 2070000, 123), m(36, "2025-04-07", 2190000, 122),
          m(36, "2024-03-04", 1870000, 123)]
SUBJ = {"street": "מנחם בגין", "house": 12, "city": "קרית מוצקין", "rooms": 5, "sqm": 107, "ptype": "דירה", "key": "nb:x"}


def test_range_from_seven_nearest():
    r = cma.cma_compute(SUBJ, BEGIN5, [], TODAY)
    assert r["range"] == [1620000, 1910000]
    assert r["n_used"] == 7 and r["basis"] == "sqm"
    assert {c["house"] for c in r["comps"] if c["used"]} == {10, 16, 18, 6, 25, 32, 34}


def test_dropped_reasons():
    comps = cma.cma_compute(SUBJ, BEGIN5, [], TODAY)["comps"]
    big = [c for c in comps if c["sqm"] in (182, 146)]
    assert big and all(not c["used"] and c["reason"] == "גדולה/קטנה מדי" for c in big)
    hi = [c for c in comps if c["house"] == 28]
    assert hi and not hi[0]["used"] and hi[0]["reason"] == "חריג"


def test_no_sqm_uses_price_basis():
    r = cma.cma_compute(dict(SUBJ, sqm=None), BEGIN5, [], TODAY)
    assert r["basis"] == "price" and r["range"][0] < r["range"][1]


def test_no_house_number_does_not_raise():
    r = cma.cma_compute(dict(SUBJ, house=None), BEGIN5, [], TODAY)
    assert r and r["n_used"] >= 4


def test_too_few_returns_none():
    assert cma.cma_compute(SUBJ, BEGIN5[:3], [], TODAY) is None


def test_old_deals_ignored():
    old = [dict(x, deal_date="2022-01-01") for x in BEGIN5]
    assert cma.cma_compute(SUBJ, old, [], TODAY) is None


def test_teaser_street_count_and_median():
    r = cma.cma_compute(SUBJ, BEGIN5, [], TODAY)
    assert r["street_count"] == 13 and r["level"] == "street" and r["since_year"] == 2023
    assert r["ppm_median"] % 100 == 0 and 16000 <= r["ppm_median"] <= 17500


def test_teaser_neighborhood_level():
    other = [dict(x, street="תמרי נחמיה") for x in BEGIN5]
    deals = BEGIN5[:2] + other
    r = cma.cma_compute(SUBJ, deals, [], TODAY)
    assert r["level"] == "neighborhood" and r["street_count"] == 15


def test_bad_rows_never_used():
    deals = BEGIN5 + [m(12, "2026-01-25", 596666, 103, bad="ppm")]
    r = cma.cma_compute(SUBJ, deals, [], TODAY)
    assert all(c["price"] != 596666 for c in r["comps"])
    assert r["street_count"] == 13


def L(addr, rooms, price, sqm=100, key="k", delisted=False, deal="מכירה", typ="דירה"):
    return {"key": key, "source": "פרטי", "address": addr, "city": "קרית מוצקין", "rooms": rooms, "sqm": sqm,
            "price": price, "delisted": delisted, "deal": deal, "type": typ}


def test_competing():
    lst = [L("מנחם בגין 29", 5, 2100000, key="a"), L("מנחם בגין 18", 4, 1780000, key="b"),
           L("מנחם בגין 2", 3, 1450000, key="c"), L("מנחם בגין 35", 5, 2550000, key="d", delisted=True),
           L("מנחם בגין 12", 5, 1620000, key="nb:x"), L("תמרי נחמיה 4", 5, 1900000, key="e"),
           L("מנחם בגין 29", 5, 2100000, key="f")]
    r = cma.cma_compute(SUBJ, BEGIN5, lst, TODAY)
    assert r["competing"] == 2
    assert {x["house"] for x in r["listings"]} == {29, 18}


def test_link_ours_matches_and_keeps_unmatched():
    market = [m(6, "2026-10-01", 1270000, 67, rooms=3)]
    ours = [{"source": "ours", "deal_date": "2026-09-30", "city": "קרית מוצקין", "street": "מנחם בגין", "house": 6,
             "price": 1270000},
            {"source": "ours", "deal_date": "2026-11-04", "city": "קרית מוצקין", "street": "מנחם בגין", "house": 12,
             "price": 1250000}]
    out = cma.link_ours(market, ours)
    assert len(out) == 2
    six = [r for r in out if r["house"] == 6][0]
    assert six["ours"] is True and six["rooms"] == 3
    twelve = [r for r in out if r["house"] == 12][0]
    assert twelve["ours"] is True and twelve["rooms"] is None


def test_ours_rows_collapse_and_filter():
    dh = [{"deal_date": "2026-09-30", "city": "מוצקין", "street": "מנחם בגין 6", "side": "מוכר", "deal_amount": 1270000},
          {"deal_date": "2026-10-02", "city": "מוצקין", "street": "מנחם בגין 6", "side": "קונה", "deal_amount": 1270000},
          {"deal_date": "2026-05-01", "city": "מוצקין", "street": "מנחם בגין 8", "side": "משכיר", "deal_amount": 5000},
          {"deal_date": "2026-05-01", "city": "מוצקין", "street": "מנחם בגין 9", "side": "מוכר", "deal_amount": 1500000,
           "missing_since": "2026-06-01T00:00:00Z"},
          {"deal_date": "2016-03-12", "city": "", "street": "בגין12 ק.מוצקין", "side": "מוכר", "deal_amount": 940000,
           "client_name": "סוד", "client_phone": "0500000000"}]
    out = cma.ours_rows(dh, KNOWN)
    assert len(out) == 2
    six = [r for r in out if r["house"] == 6][0]
    assert six["street"] == "מנחם בגין" and six["price"] == 1270000
    twelve = [r for r in out if r["house"] == 12][0]
    assert twelve["street"] == "מנחם בגין" and "מוצקין" in twelve["city"]
    assert all("client_name" not in r and "client_phone" not in r for r in out)


def test_subject_from_listing():
    s = cma.subject_from_listing({"רחוב": "מנחם בגין 12", "עיר / ישוב": "קרית מוצקין", "חדרים": "5", "sqm": "107"})
    assert s["house"] == 12 and s["street"] == "מנחם בגין" and s["ptype"] == "דירה" and s["sqm"] == 107
    assert cma.subject_from_listing({"עיר": "קרית מוצקין"}) is None


def test_subject_nb():
    assert cma.subject_nb("מנחם בגין", "קרית מוצקין", BEGIN5) == NB
    assert cma.subject_nb("רחוב אחר", "קרית מוצקין", BEGIN5) == ""


def test_city_spellings_match():
    deals = [dict(x, city="מוצקין") for x in BEGIN5]
    assert cma.cma_compute(SUBJ, deals, [], TODAY)["range"] == [1620000, 1910000]


def test_ptype_garden_not_mixed():
    r = cma.cma_compute(dict(SUBJ, ptype="דירת גן"), BEGIN5, [], TODAY)
    assert r is None
