"""CMA בתיק הפרזנטציה: עמוד הטיזר, שורת הטווח בדף האישור, ושהטווח האמיתי לא מגיע לבעל הנכס.
הרצה: python3 -m pytest tests/cma/test_kit_page.py -q"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "kit"))   # test_routes של התיק, לא של ה-CMA
import importlib.util  # noqa: E402
import cma  # noqa: E402
import kit_render as KR  # noqa: E402
sys.modules.pop("test_routes", None)
import test_review_view as RV  # noqa: E402
_spec = importlib.util.spec_from_file_location("cma_test_calc", os.path.join(HERE, "test_calc.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

LIST = [T.L("מנחם בגין 29", 5, 2100000, key="a"), T.L("מנחם בגין 18", 4, 1780000, key="b")]


def block(**kw):
    return dict(cma.strip_addresses(cma.cma_compute(T.SUBJ, T.BEGIN5, LIST, T.TODAY)), **kw)


def snap(c):
    s = RV.sample()
    s["cma"] = c
    return s


def drawn(monkeypatch, s):
    from PIL import ImageDraw
    seen = []
    orig = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", lambda self, xy, t, *a, **k: (seen.append(str(t)), orig(self, xy, t, *a, **k))[1])
    im = KR._p_cma(s, 6)
    return im, " ".join(seen)


def test_page_size_and_no_secrets(monkeypatch):
    c = block()
    lo, hi = c["range"]
    im, text = drawn(monkeypatch, snap(c))
    assert im.size == (1080, 1920)
    for bad in (str(lo), "{:,}".format(lo), str(hi), "{:,}".format(hi), "מדלן", "עסקה שלנו"):
        assert bad not in text and bad[::-1] not in text
    body = text.rsplit(" ", 1)[0]          # בלי מספר העמוד שבסוף
    for h in {x["house"] for x in cma.cma_compute(T.SUBJ, T.BEGIN5, LIST, T.TODAY)["comps"]}:
        assert (" %d " % h) not in (" " + body + " ")


def test_competing_zero_hidden(monkeypatch):
    _im, text = drawn(monkeypatch, snap(block(competing=0)))
    assert "מתחרות" not in text and "מתחרות"[::-1] not in text
    _im, text = drawn(monkeypatch, snap(block()))
    assert "מתחרות" in text or "מתחרות"[::-1] in text


def test_pages_with_and_without_cma():
    s = RV.sample()
    s.pop("cma", None)
    assert len(KR.render_pages(s)) == 6
    assert len(KR.render_pages(snap(block()))) == 7


def test_review_shows_range_owner_view_does_not():
    c = block()
    lo, hi = c["range"]
    rec = RV.mk()
    RV.sb.kit_update(rec["id"], {"snapshot": snap(c)})
    h = RV.c.get("/v2/kit/review/" + rec["review_token"]).get_data(as_text=True)
    assert "{:,}".format(lo) in h and "{:,}".format(hi) in h and "מבוסס על 7 עסקאות" in h
    assert "מנחם בגין 10" not in h
    v = RV.mk("approved")
    RV.sb.kit_update(v["id"], {"snapshot": snap(c)})
    hv = RV.c.get("/k/" + v["view_token"]).get_data(as_text=True)
    assert "{:,}".format(lo) not in hv and "{:,}".format(hi) not in hv and hv.count("<img") == 7


def test_review_without_cma_has_no_line():
    rec = RV.mk()
    h = RV.c.get("/v2/kit/review/" + rec["review_token"]).get_data(as_text=True)
    assert "טווח ה-CMA" not in h


def test_cma_query_for_agent_button():
    import kit
    from urllib.parse import parse_qs
    q = parse_qs(kit.cma_query({"street": "מנחם בגין 12", "city": "קרית מוצקין", "rooms": "5", "sqm": "", "ptype": "דירה"}))
    assert q == {"street": ["מנחם בגין"], "house": ["12"], "city": ["קרית מוצקין"], "rooms": ["5"], "ptype": ["דירה"]}
