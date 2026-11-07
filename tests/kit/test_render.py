# tests/kit/test_render.py — רינדור עמודי תיק הפרזנטציה (Pillow, בלי רשת)
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import kit_core as K
import kit_render as R

OUT = os.environ.get("KIT_PNG_DIR") or tempfile.gettempdir()
LONG_OWNER = "אברהם יצחק יעקב בן משה הכהן מקרית ביאליק"      # 40 תווים
LONG_STREET = "רחוב שדרות ההסתדרות הציונית העולמית"


def sample(**kw):
    s = {
        "owner": "משה כהן", "owner_first": "משה", "street": "הנוטר", "city": "קרית ביאליק", "rooms": "5",
        "price": "1,850,000", "meet_at": "2026-11-11T17:00",
        "agent": {"name": "אוהד לוי", "first": "אוהד", "license": "3123456",
                  "bio": "מתווך ותיק בקריות, מכיר כל רחוב ושכונה. אוהב לעבוד עם אנשים ולהביא תוצאות. " * 3,
                  "review": {"text": "אוהד ליווה אותנו במכירה מקצועית ונעימה, תוך חודשיים הדירה נמכרה. ממליצים בחום!",
                             "by": "משפחת לוי"},
                  "photo": None, "site_url": "https://refamily.co.il/צוות/אוהד-לוי", "phone": "0501111111"},
        "office": {"years": 10, "deals": 4622, "agents": 56, "office": "רימקס פמילי"},
        "buyers": {"mode": "match", "n": 14, "city": "קרית ביאליק",
                   "lines": [["תקציב של 1,800,000 ומעלה", 11], ["מחפשים 5 חדרים ומעלה", 9], ["מחפשים בקרית ביאליק", 14]]},
        "claims": dict(K.KIT_DEFAULTS, g_url="https://g.page/r/bialik"),
        "made_at": "2026-11-06T10:00:00+02:00", "cma": None,
    }
    s.update(kw)
    return s


def test_six_pages_and_png():
    imgs = R.render_pages(sample())
    assert len(imgs) == 6
    assert all(im.size == (1080, 1920) and im.mode == "RGB" for im in imgs)
    for i, im in enumerate(imgs, 1):
        im.save(os.path.join(OUT, "kit_p%d.png" % i))


def test_cma_page():
    imgs = R.render_pages(sample(cma={"title": "x"}))
    assert len(imgs) == 7
    assert imgs[5].getpixel((5, 5)) == R.CREAM and imgs[6].getpixel((5, 5)) == R.NAVY   # ניתוח שוק לפני הצעד הבא
    assert len(R.render_pages(sample(cma=None))) == 6


def test_pdf():
    b = R.render_pdf(R.render_pages(sample()))
    assert b[:4] == b"%PDF"


def test_wrap_rtl_fits():
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))
    width = 1080 - 2 * 72
    for txt, size in ((LONG_OWNER, 110), (LONG_STREET, 110), ("הכנו לך תוכנית אישית לנכס ב" + LONG_STREET + ", קרית ביאליק", 50)):
        f = R._font(800, size)
        lines = R.wrap_rtl(d, txt, f, width)
        assert lines and all(d.textlength(l, font=f) <= width for l in lines), (txt, lines)


def test_long_names_render():
    a = dict(sample()["agent"], name=LONG_OWNER)
    imgs = R.render_pages(sample(owner=LONG_OWNER, owner_first=LONG_OWNER, street=LONG_STREET, agent=a))
    assert len(imgs) == 6


def test_empty_agent_and_city_mode():
    snap = sample(agent={"name": "", "first": "", "license": "", "bio": "", "review": None, "photo": None, "site_url": ""},
                  buyers={"mode": "city", "n": 86, "city": "קרית ביאליק", "lines": []},
                  meet_at="", claims=dict(K.KIT_DEFAULTS))
    imgs = R.render_pages(snap)
    assert len(imgs) == 6
    imgs[1].save(os.path.join(OUT, "kit_p2_empty.png"))
    imgs[4].save(os.path.join(OUT, "kit_p5_city.png"))


def test_no_effie_word():
    import inspect
    assert "אפי" not in inspect.getsource(R)


def test_margins_clean_with_long_text():
    """שום דיו מחוץ לשוליים (72px מכל צד) גם עם שם בעלים/סוכן ורחוב ארוכים במיוחד."""
    a = dict(sample()["agent"], name=LONG_OWNER + " " + LONG_OWNER, bio=("מילה " * 400),
             review={"text": "המלצה " * 200, "by": LONG_OWNER})
    snap = sample(owner=LONG_OWNER, owner_first=LONG_OWNER + LONG_OWNER, street=LONG_STREET * 2, agent=a,
                  buyers={"mode": "match", "n": 14, "city": LONG_STREET,
                          "lines": [["מחפשים ב" + LONG_STREET * 2, 3]]})
    for im in R.render_pages(snap):
        bg = im.getpixel((5, 5))
        for x in list(range(0, R.PAD - 8)) + list(range(R.W - R.PAD + 8, R.W)):
            col = im.crop((x, 0, x + 1, R.H)).getcolors(4096)
            assert col and len(col) == 1 and col[0][1] == bg, x
