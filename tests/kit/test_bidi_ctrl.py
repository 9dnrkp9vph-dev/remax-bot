"""[18/11] תיק של ליקה: 'התיק אינו זמין' — טקסט עם סימן כיוון נסתר (FSI) הפיל את python-bidi והעמודים לא נבנו."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import kit_render as kr
from test_render import sample

FSI, PDI, LRI = "⁨", "⁩", "⁦"


def test_rtl_strips_isolates():
    assert kr._rtl(FSI + "ורד 28" + PDI) == kr._rtl("ורד 28")
    assert kr._rtl("שלום " + LRI + "abc" + PDI) == kr._rtl("שלום abc")


def test_pages_render_with_isolates_everywhere():
    s = sample()
    s["owner"] = FSI + (s.get("owner") or "משה") + PDI
    s["street"] = FSI + "ורד" + PDI
    s["cma"] = {"title": "x", "subject": {"street": "ורד", "rooms": 4.5, "sqm": 94}, "level": "street",
                "street_count": 5, "since_year": 2023, "ppm_median": 17000, "competing": 1, "range": [1, 2],
                "ppm_range": [1, 2], "basis": "sqm", "n_used": 4,
                "comps": [{"street": FSI + "ורד" + PDI, "house": i, "date": "2025-03-01", "rooms": 4.5, "sqm": 94,
                           "floor": "2", "price": 1600000, "ppm": 17000, "ours": i == 0, "used": True} for i in range(4)],
                "listings": [{"source": "יד2", "rooms": 4.5, "sqm": 94, "price": 1650000, "same_street": True}]}
    pages = kr.render_pages(s)
    assert len(pages) >= 2
