"""CMA — תשובת בוט מדלן → שורות למאגר העסקאות (אייל 10/11). הנתונים: התשובה האמיתית לדולב 3, קרית ים."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import cma  # noqa: E402

BOT = [
    {"address": "דולב 3, קרית ים", "date": "2024-12-19", "floor": 1, "ppm": 15847, "price": 1870000, "rooms": 5, "sqm": 118, "type": None, "year_built": 2006},
    {"address": "דולב 3, קרית ים", "date": "2023-05-16", "floor": 1, "ppm": 23300, "price": 2330000, "rooms": 4, "sqm": 100, "type": None, "year_built": 2002},
    {"address": "דולב 1, קרית ים", "date": "2022-12-06", "floor": "ק", "ppm": 18750, "price": 1950000, "rooms": 4, "sqm": 104, "type": None, "year_built": 2006},
    {"address": "דולב 4, קרית ים", "date": "2022-07-21", "floor": 5, "ppm": None, "price": 1410000, "rooms": 4, "sqm": None, "type": None, "year_built": 2005},
    {"address": "דולב 4, קרית ים", "date": "2021-12-14", "floor": 6, "ppm": 10301, "price": 1401000, "rooms": 5, "sqm": 136, "type": None, "year_built": 1980},
    {"address": "דולב 4, קרית ים", "date": "2021-12-08", "floor": 6, "ppm": 10301, "price": 1401000, "rooms": 5, "sqm": 136, "type": None, "year_built": 2007},
    "junk", {"address": "דולב 9, קרית ים", "date": "", "price": 1500000},
]


def test_bot_rows_shape():
    rows, st = cma.bot_rows(BOT, "דולב 3, קרית ים", set(), [])
    assert st["n"] == 6
    r = [x for x in rows if x["price"] == 1870000][0]
    assert r["street"] == "דולב" and r["house"] == 3 and r["city"] == "קרית ים"
    assert r["deal_date"] == "2024-12-19" and r["rooms"] == 5 and r["sqm"] == 118 and r["floor"] == "1"
    assert r["ptype"] == "" and cma.ptype_key(r["ptype"]) == "דירה"
    assert r["file_name"].startswith("bot:") and r["nb"] == "קרית ים" and r["deal_key"]


def test_bot_rows_nb_from_stored_street():
    stored = [{"nb": "עין הים", "street": "דולב", "city": "קרית ים", "house": 7}]
    rows, _st = cma.bot_rows(BOT, "דולב 3, קרית ים", set(), stored)
    assert {r["nb"] for r in rows} == {"עין הים"}


def test_bot_rows_empty():
    assert cma.bot_rows([], "דולב 3, קרית ים", set(), []) == ([], {"n": 0, "dups": 0, "bad": 0, "min_date": None,
                                                                  "max_date": None, "streets": 0})


def test_near_duplicate_marked():
    rows, _st = cma.bot_rows(BOT, "דולב 3, קרית ים", set(), [])
    twins = sorted([r for r in rows if r["price"] == 1401000], key=lambda r: r["deal_date"])
    assert len(twins) == 2 and twins[0]["bad"] == "" and twins[1]["bad"] == "dup"


def test_near_duplicate_needs_same_details():
    a = {"street": "דולב", "house": 4, "price": 1401000, "sqm": 136, "floor": "6", "deal_date": "2021-12-08", "bad": ""}
    far = dict(a, deal_date="2022-02-01")
    other = dict(a, house=5, deal_date="2021-12-10")
    out = cma.mark_near_dups([dict(a), far, other])
    assert all(r["bad"] == "" for r in out)


def test_near_duplicate_across_sources_in_inputs():
    a = {"street": "דולב", "house": 4, "price": 1401000, "sqm": 136, "floor": "6", "deal_date": "2021-12-08", "bad": ""}
    b = dict(a, deal_date="2021-12-11")
    out = cma.mark_near_dups([b, a])
    assert sorted(r["bad"] for r in out) == ["", "dup"]


def test_city_from_request_when_missing():
    """[13/11] בוט לפי רחוב (nadlan.gov.il) — בעסקה 'עפרה חזה 11' בלי עיר; העיר מהבקשה."""
    import cma
    rows, st = cma.bot_rows([{"date": "09/12/2025", "address": "עפרה חזה 11", "price": "1,825,000",
                              "type": "דירה בבית קומות", "rooms": "4", "sqm": "123.65", "floor": "קומה 4"}],
                            "עפרה חזה 11, קרית מוצקין", set(), [])
    assert st["n"] == 1 and rows[0]["city"] == "קרית מוצקין" and cma.ptype_key(rows[0]["ptype"]) == "דירה"
