"""CMA — קליטת קבצי מדלן: נרמול רחוב, כתובת, כפילויות, חריגים (תוכנית 2026-11-06-cma, משימה 1)."""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import cma  # noqa: E402

H = cma.MADLAN_HEADERS


def row(date, addr, price, rooms="5", sqm="107", floor="3", ptype="דירה", ppm="", year="2000"):
    vals = (date, addr, price, ptype, rooms, sqm, floor, ppm, year)
    return dict(zip(H, vals))


KNOWN = {"מנחם בגין", "יצחק בן צבי", "הערבה", "החשמונאים"}


def test_canon_street_rotation():
    assert cma.canon_street("בגין מנחם", {"מנחם בגין"}) == "מנחם בגין"


def test_canon_street_suffix():
    assert cma.canon_street("בן צבי", {"יצחק בן צבי"}) == "יצחק בן צבי"


def test_canon_street_leading_he():
    assert cma.canon_street("ערבה", {"הערבה"}) == "הערבה"


def test_canon_street_unknown_kept():
    assert cma.canon_street("רחוב חדש", set()) == "רחוב חדש"


def test_canon_street_krayot_spelling():
    assert cma.canon_street("קריית ספר", {"קרית ספר"}) == "קרית ספר"


def test_parse_addr_house():
    a = cma.parse_madlan_addr("בגין מנחם 12, קרית מוצקין")
    assert a["street"] == "בגין מנחם" and a["house"] == 12 and a["city"] == "קרית מוצקין"


def test_parse_addr_project():
    a = cma.parse_madlan_addr("Dori Dream קרית מוצקין")
    assert a["house"] is None and a["street"] == "" and a["project"]


def test_exact_dups_dropped():
    t = [row("22.11.2021", "בגין מנחם 12, קרית מוצקין", "890,000", rooms="3", sqm="60", floor="7")] * 2
    rows, st = cma.madlan_rows(t, "נווה גנים", "t.xlsx", KNOWN)
    assert len(rows) == 1 and st["dups"] == 1
    assert rows[0]["street"] == "מנחם בגין" and rows[0]["house"] == 12 and rows[0]["nb"] == "נווה גנים"


def test_columns_in_other_order():
    r = row("1.10.2026", "בגין מנחם 6, קרית מוצקין", "1,270,000", rooms="3", sqm="67", floor="2")
    shuffled = {k: r[k] for k in reversed(H)}
    rows, _ = cma.madlan_rows([shuffled], "נ", "t.xlsx", KNOWN)
    assert rows[0]["price"] == 1270000 and rows[0]["rooms"] == 3 and rows[0]["sqm"] == 67


def test_missing_header_raises():
    r = row("1.10.2026", "בגין מנחם 6, קרית מוצקין", "1,270,000")
    del r["חדרים"]
    with pytest.raises(ValueError):
        cma.madlan_rows([r], "נ", "t.xlsx", KNOWN)


def test_dup_project_group_all_bad():
    g = [row("10.6.2021", a, "1,620,000", rooms="5", sqm="116", floor="12") for a in (
        "בגין מנחם 37, קרית מוצקין", "NEVE NOFAR קרית מוצקין", "Dori Dream קרית מוצקין",
        "החשמונאים 45 - פרויקט G קרית מוצקין")]
    rows, _ = cma.madlan_rows(g, "נ", "t.xlsx", KNOWN)
    assert len(rows) == 4 and all(r["bad"] == "dup_project" for r in rows)


def test_dup_project_single_street_kept():
    g = [row("19.7.2021", "בגין מנחם 28, קרית מוצקין", "1,650,000", sqm="129", floor="8"),
         row("22.7.2021", "ARTOWER 3 קרית מוצקין", "1,650,000", sqm="129", floor="8")]
    rows, _ = cma.madlan_rows(g, "נ", "t.xlsx", KNOWN)
    by = {r["house"]: r for r in rows}
    assert by[28]["bad"] == "" and by[None]["bad"] == "dup_project"


def test_bad_ppm_and_price():
    rows, _ = cma.madlan_rows([row("25.1.2026", "בגין מנחם 21, קרית מוצקין", "596,666", rooms="4", sqm="103"),
                               row("1.1.2026", "בגין מנחם 9, קרית מוצקין", "120,000", rooms="3", sqm="")],
                              "נ", "t.xlsx", KNOWN)
    by = {r["house"]: r for r in rows}
    assert by[21]["bad"] == "ppm"
    assert by[9]["bad"] == "price"


def test_half_room_and_empty_sqm():
    rows, _ = cma.madlan_rows([row("14.12.2022", "בגין מנחם 14, קרית מוצקין", "1,415,000", rooms="3.5", sqm="")],
                              "נ", "t.xlsx", KNOWN)
    assert rows[0]["rooms"] == 3.5 and rows[0]["sqm"] is None and rows[0]["ppm"] is None
    assert rows[0]["deal_date"] == "2022-12-14"


def test_odd_price_parsed():
    rows, _ = cma.madlan_rows([row("1.1.2025", "בגין מנחם 34, קרית מוצקין", "1,800,007", sqm="107")],
                              "נ", "t.xlsx", KNOWN)
    assert rows[0]["price"] == 1800007 and rows[0]["ppm"] == round(1800007 / 107)


def test_deal_key_stable():
    a = cma.madlan_rows([row("1.1.2025", "בגין מנחם 34, קרית מוצקין", "1,800,007")], "א", "a.xlsx", KNOWN)[0][0]
    b = cma.madlan_rows([row("1.1.2025", "בגין מנחם 34, קרית מוצקין", "1,800,007")], "ב", "b.xlsx", KNOWN)[0][0]
    assert a["deal_key"] == b["deal_key"]


def test_stats():
    t = [row("1.10.2026", "בגין מנחם 6, קרית מוצקין", "1,270,000"),
         row("8.1.2025", "בגין מנחם 10, קרית מוצקין", "1,800,000")]
    _, st = cma.madlan_rows(t, "נ", "t.xlsx", KNOWN)
    assert st["n"] == 2 and st["min_date"] == "2025-01-08" and st["max_date"] == "2026-10-01"
    assert st["streets"] == 1


def test_real_xlsx_through_ibs_parse_table():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(H))
    ws.append(["1.10.2026", "בגין מנחם 6, קרית מוצקין", "1,270,000", "דירה", "3", "67", "2", "18,955", "1992"])
    ws.append(["24.9.2026", "בגין מנחם 10, קרית מוצקין", "1,230,000", "דירה", "3", "67", "2", "18,358", "1998"])
    buf = io.BytesIO()
    wb.save(buf)
    import effie_v2
    table = effie_v2.ibs_parse_table("t.xlsx", buf.getvalue())
    rows, st = cma.madlan_rows(table, "נ", "t.xlsx", KNOWN)
    assert st["n"] == 2 and {r["house"] for r in rows} == {6, 10}
