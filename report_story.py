# -*- coding: utf-8 -*-
"""תמונות סטורי לדוח היומי (אייל 05/10): "באותו מייל כמה תמונות לסטורי של האינסטוש, אם ארצה להשתמש".

מודול טהור (בלי Flask/רשת): נתוני הדוח היומי (build_office_report → data) → 4 תמונות 1080×1920 JPEG,
שנשלחות כקבצים מצורפים במייל של 07:00. רק נתונים שנעים להראות החוצה (החלטת אייל):
  1. פתיחה — המקום שלנו בשוק (נכסים בפרסום ביד2)
  2. נכסים חדשים שלנו החודש (כולל בלעדיות)
  3. החתמות החודש — סך הכול, בלעדיות, קונים
  4. פודיום הסוכנים — שלושת המובילים
בכוונה לא: שיחות/מענה, עו"ד, תובנות, זמני שימוש. אין כאן שום פרסום לאינסטגרם — רק ציור.
פרימיטיבי הציור (גרדיאנט, טקסט RTL דרך python-bidi, פונט Heebo המשתנה) מהענף ig-story (10/09)."""
import os, io, math, datetime as dt
from collections import defaultdict

try:
    from bidi.algorithm import get_display as _bidi
except Exception:   # pragma: no cover — ב-Render החבילה קיימת (requirements)
    def _bidi(s):
        return s

W, H = 1080, 1920
PAD = 72
NAVY0, NAVY1, NAVY2 = (0x0E, 0x1D, 0x33), (0x1E, 0x3A, 0x5F), (0x2C, 0x4C, 0x77)
GOLD = (0xE4, 0xC5, 0x6B)
WHITE = (255, 255, 255)
SILVER, BRONZE = (0xC9, 0xCD, 0xD4), (0xD9, 0xA0, 0x66)
HDAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]   # date.weekday(): שני=0
_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Heebo-VF.ttf")
_FONT_CACHE = {}


def _font(weight, size):
    from PIL import ImageFont
    k = (weight, size)
    f = _FONT_CACHE.get(k)
    if f is None:
        f = ImageFont.truetype(_FONT_PATH, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        _FONT_CACHE[k] = f
    return f


# ── נתונים: אותם חישובים כמו המייל המעוצב (render_office_report_email) ──────────────
def rs_market(d):
    """→ {pos, n, active, active_excl, leader} — מקום המשרד בשוק לפי נכסים בפרסום ביד2."""
    office = d.get("office") or ""
    o_act, o_act_ex = int(d.get("office_active") or 0), int(d.get("office_active_excl") or 0)
    xact, xex = d.get("shtaf_active_by_office") or {}, d.get("shtaf_active_excl_by_office") or {}
    market = sorted([(office, o_act, o_act_ex, True)] + [(o, n, xex.get(o, 0), False) for o, n in xact.items()],
                    key=lambda t: -t[1])
    pos = next((i + 1 for i, t in enumerate(market) if t[3]), 1)
    return {"pos": pos, "n": len(market), "active": o_act, "active_excl": o_act_ex, "leader": market[0][0]}


def rs_podium(d, k=3):
    """שלושת המובילים — אותו דירוג משולב כמו "פודיום הסוכנים" במייל."""
    sc = defaultdict(lambda: {"calls": 0, "sigs": 0, "buyers": 0, "closed": 0})
    for key, src, per in (("calls", "calls_by_agent", "week"), ("sigs", "signings_by_agent", "month"),
                          ("buyers", "buyers_by_agent", "month"), ("closed", "deals_closed_by_agent", "year")):
        for a, n in ((d.get(src) or {}).get(per) or {}).items():
            sc[a][key] += n
    sc.pop("—", None); sc.pop("", None)
    rank = sorted(sc.items(), key=lambda kv: -(kv[1]["calls"] + 5 * kv[1]["sigs"] + 3 * kv[1]["buyers"] + 20 * kv[1]["closed"]))
    return [a for a, _ in rank[:k]]


def rs_date_line(day_iso):
    try:
        dd = dt.date.fromisoformat(str(day_iso))
    except Exception:
        return ""
    return "יום %s · %s" % (HDAYS[dd.weekday()], dd.strftime("%d/%m/%Y"))


def rs_slides(d):
    """נתוני הדוח → רשימת שקפים (dict). שקף בלי תוכן אמיתי (פודיום ריק) — לא נכלל."""
    m = rs_market(d)
    o_new, o_excl = d.get("office_new") or {}, d.get("office_new_excl") or {}
    lab = d.get("signings_by_label") or {}
    s_all = d.get("signings") or {}
    def _m(dct, key="month"):
        try:
            return int((dct or {}).get(key) or 0)
        except Exception:
            return 0
    slides = [
        {"kind": "market", "kicker": "המצב בשוק",
         "big": "מקום 1 בשוק" if m["pos"] == 1 else "מקום %d" % m["pos"],
         "sub": ("מתוך %d משרדים" % m["n"]) if m["n"] > 1 else "",
         "tiles": [(m["active"], "נכסים בפרסום ביד2"), (m["active_excl"], "מתוכם בבלעדיות")]},
        {"kind": "tiles", "kicker": "נכסים חדשים שלנו", "big": "החודש",
         "tiles": [(_m(o_new), "נכסים חדשים"), (_m(o_excl), "מתוכם בבלעדיות"), (_m(o_new, "year"), "מתחילת השנה")]},
        {"kind": "tiles", "kicker": "החתמות", "big": "החודש",
         "tiles": [(_m(s_all), "החתמות"), (_m(lab.get("בלעדיות")), "בלעדיות"), (_m(lab.get("קונים")), "קונים")]},
    ]
    top = rs_podium(d)
    if top:
        slides.append({"kind": "podium", "kicker": "המובילים במשרד", "big": "הפודיום", "names": top})
    office, dl = d.get("office") or "", rs_date_line(d.get("day"))
    for s in slides:
        s["office"], s["date"] = office, dl
    return slides


# ── ציור ────────────────────────────────────────────────────────────────────────
def _gradient(w, h):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (w, h))
    dr = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        if t <= 0.55:
            a = t / 0.55; col = tuple(int(NAVY0[i] + (NAVY1[i] - NAVY0[i]) * a) for i in range(3))
        else:
            b = (t - 0.55) / 0.45; col = tuple(int(NAVY1[i] + (NAVY2[i] - NAVY1[i]) * b) for i in range(3))
        dr.line([(0, y), (w, y)], fill=col + (255,))
    return im


def _rgba(col, alpha):
    return (col[0], col[1], col[2], int(round(255 * alpha)))


def _rr(layer, box, r, fill=None, outline=None, width=2):
    from PIL import ImageDraw
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _txt_r(d, text, font, x_right, y, fill):
    vis = _bidi(str(text if text is not None else ""))
    w = font.getlength(vis)
    d.text((x_right - w, y), vis, font=font, fill=fill)
    return w


def _txt_c(d, text, font, cx, y, fill):
    vis = _bidi(str(text if text is not None else ""))
    w = font.getlength(vis)
    d.text((cx - w / 2, y), vis, font=font, fill=fill)
    return w


def _fit(text, weight, size, max_w, min_size=40):
    """גודל פונט שמכניס את הטקסט ברוחב — שם ארוך / מספר גדול לא נחתך."""
    vis = _bidi(str(text))
    while size > min_size and _font(weight, size).getlength(vis) > max_w:
        size -= 4
    return _font(weight, size)


def _num(v):
    try:
        return format(int(v), ",")
    except Exception:
        return str(v if v not in (None, "") else "—")


def _header(layer, d, s, logo, i, n):
    # פסי התקדמות (כמו סטורי)
    gap, y = 14, 64
    seg = (W - 2 * PAD - gap * (n - 1)) / max(1, n)
    for k in range(n):
        x0 = PAD + k * (seg + gap)
        _rr(layer, (x0, y, x0 + seg, y + 10), 5, fill=GOLD + (255,) if k <= i else _rgba(WHITE, .25))
    # לוגו המשרד + שם + תאריך
    x_r, top = W - PAD, 120
    if logo is not None:
        try:
            _rr(layer, (x_r - 132, top, x_r, top + 132), 36, fill=WHITE + (255,))
            lg = logo.convert("RGBA"); lg.thumbnail((104, 104))
            layer.paste(lg, (x_r - 66 - lg.width // 2, top + 66 - lg.height // 2), lg)
            x_r -= 160
        except Exception:
            pass
    _txt_r(d, s["office"], _font(800, 46), x_r, top + 14, WHITE)
    _txt_r(d, s["date"], _font(400, 32), x_r, top + 78, _rgba(WHITE, .6))


def _tiles(layer, d, tiles, y):
    """אריחים במלוא הרוחב, זה מתחת לזה: מספר גדול + תווית."""
    th, gap = 250, 34
    for k, (v, label) in enumerate(tiles):
        y0 = y + k * (th + gap)
        _rr(layer, (PAD, y0, W - PAD, y0 + th), 48, fill=_rgba(WHITE, .07), outline=_rgba(WHITE, .12), width=3)
        col = GOLD if k == 0 else WHITE
        _txt_r(d, _num(v), _fit(_num(v), 800, 120, W - 2 * PAD - 100), W - PAD - 54, y0 + 30, col)
        _txt_r(d, label, _font(500, 40), W - PAD - 54, y0 + 176, _rgba(WHITE, .65))
    return y + len(tiles) * (th + gap)


def rs_render(s, logo=None, i=0, n=1):
    """שקף → תמונת PIL (RGB)."""
    from PIL import Image, ImageDraw
    canvas = _gradient(W, H)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _header(layer, d, s, logo, i, n)
    x_r = W - PAD
    y = 420
    _txt_r(d, s["kicker"], _font(700, 44), x_r, y, GOLD)
    big = s["big"]
    _txt_r(d, big, _fit(big, 800, 150, W - 2 * PAD), x_r, y + 64, WHITE)
    y += 250
    if s.get("sub"):
        _txt_r(d, s["sub"], _font(500, 52), x_r, y, _rgba(WHITE, .8))
        y += 100
    y += 30
    if s["kind"] in ("market", "tiles"):
        _tiles(layer, d, s["tiles"], y)
    elif s["kind"] == "podium":
        cols = (GOLD, SILVER, BRONZE)
        for k, name in enumerate(s["names"][:3]):
            y0 = y + k * 250
            _rr(layer, (PAD, y0, W - PAD, y0 + 210), 48, fill=_rgba(WHITE, .07), outline=_rgba(cols[k], .55), width=4)
            cx, cy, r = W - PAD - 110, y0 + 105, 62
            ImageDraw.Draw(layer).ellipse((cx - r, cy - r, cx + r, cy + r), fill=cols[k] + (255,))
            _txt_c(d, str(k + 1), _font(800, 76), cx, cy - 52, (0x23, 0x17, 0x00))
            _txt_r(d, name, _fit(name, 800, 72, W - 2 * PAD - 260), W - PAD - 210, y0 + 62, WHITE)
    _txt_c(d, s["office"], _font(600, 32), W / 2, H - 120, _rgba(WHITE, .45))
    canvas.alpha_composite(layer)
    return canvas.convert("RGB")


def rs_jpeg(im, quality=88):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def rs_load_logo(path):
    if not path:
        return None
    try:
        from PIL import Image
        with open(path, "rb") as f:
            im = Image.open(io.BytesIO(f.read()))
            im.load()
        return im
    except Exception:
        return None


def rs_story_files(d, logo_path=None):
    """→ [(שם קובץ, bytes)] — התמונות לצירוף למייל."""
    slides = rs_slides(d)
    logo = rs_load_logo(logo_path)
    out = []
    for i, s in enumerate(slides):
        tag = {"market": "market", "podium": "podium"}.get(s["kind"]) or ("listings" if s["kicker"].startswith("נכסים") else "signings")
        out.append(("story-%d-%s-%s.jpg" % (i + 1, tag, str(d.get("day") or "")), rs_jpeg(rs_render(s, logo, i, len(slides)))))
    return out
