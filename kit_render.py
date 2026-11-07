# -*- coding: utf-8 -*-
"""תיק פרזנטציה לבעל נכס — ציור העמודים (1080×1920, פרופורציה של טלפון) מתוך הצילום של kit_core.build_snapshot.

מודול טהור (Pillow + python-bidi + Heebo): בלי רשת, בלי DB, בלי AI. כל טקסט שמגיע מהנתונים נשבר לשורות או מוקטן
כך שלא יעבור את רוחב הכרטיס; בלוק ריק (המלצה, טקסט אישי, רישיון, מועד) לא מצויר בכלל.
העיצוב לפי הדוגמה שאושרה (mockup v2: 300px = 1080, פי 3.6). עמוד ניתוח שוק — רק כשיש snap['cma']."""
import io
import os
import re
import datetime as _dt

from report_story import _font as _rs_font

try:
    from bidi.algorithm import get_display as _bidi
except Exception:   # pragma: no cover — ב-Render החבילה קיימת (requirements)
    def _bidi(s):
        return s

W, H = 1080, 1920
PAD = 72
CARD_R = 32
NAVY = (0x1E, 0x3A, 0x5F)
NAVY2 = (0x2C, 0x4C, 0x77)
CREAM = (0xF2, 0xEF, 0xE7)
GOLD = (0xC2, 0x94, 0x35)
GOLD2 = (0xE4, 0xC5, 0x6B)
ONGOLD = (0x23, 0x17, 0x00)
GREEN = (0x15, 0x7A, 0x43)
MUTED = (0x6B, 0x72, 0x80)
MUTED2 = (0x5B, 0x64, 0x72)
KICK = (0x7A, 0x5E, 0x1C)          # זהב כהה לטקסט קטן על קרם (כמו בדוגמה שאושרה)
WHITE = (255, 255, 255)
LIGHT = (0xDF, 0xE6, 0xEF)         # טקסט משני על נייבי
FOOT_NAVY = (0x9F, 0xB0, 0xC6)
INSET_NAVY = (0x30, 0x4A, 0x6C)    # מלבן שקוף-למחצה על נייבי (לבן 8%)
_DAYS = ["ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳", "א׳"]


def _font(weight, size):
    return _rs_font(weight, int(size))


def _rtl(s):
    return _bidi(str(s or ""))


def _tl(d, s, f):
    return d.textlength(s, font=f)


# ── שבירת שורות ───────────────────────────────────────────────────────────────
def _split_long(d, word, font, width):
    """מילה אחת שלא נכנסת בשורה — חותכים לפי אותיות."""
    out, cur = [], ""
    for ch in word:
        if cur and _tl(d, _rtl(cur + ch), font) > width:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _wrap_logical(d, text, font, width):
    words = []
    for w in str(text or "").split():
        if _tl(d, _rtl(w), font) > width:
            words.extend(_split_long(d, w, font, width))
        else:
            words.append(w)
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w) if cur else w
        if cur and _tl(d, _rtl(t), font) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def wrap_rtl(draw, text, font, width):
    """טקסט → שורות לתצוגה (כל שורה כבר אחרי bidi), כל אחת ברוחב עד width."""
    out = []
    for para in str(text or "").split("\n"):
        out.extend(_rtl(l) for l in _wrap_logical(draw, para, font, width))
    return out


def _block(d, text, weight, size, width, max_lines, min_size=None):
    """שבירה לשורות עם הקטנה עד max_lines; אם עדיין ארוך — חיתוך עם '…'. → (font, lines logical)."""
    min_size = min_size or max(24, int(size * 0.6))
    s = size
    while True:
        f = _font(weight, s)
        lines = []
        for para in str(text or "").split("\n"):
            lines.extend(_wrap_logical(d, para, f, width))
        if len(lines) <= max_lines or s <= min_size:
            break
        s -= 4
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and _tl(d, _rtl(last + "…"), f) > width:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return f, lines


def _fit(d, text, weight, size, width, min_size=24):
    s = size
    f = _font(weight, s)
    while s > min_size and _tl(d, _rtl(text), f) > width:
        s -= 2
        f = _font(weight, s)
    return f


def _clip(d, text, f, maxw):
    """רשת ביטחון: שורה שעדיין רחבה מדי (אחרי הקטנה) נחתכת עם '…' — אף פעם לא עוברת את שולי העמוד."""
    t = str(text or "")
    if _tl(d, _rtl(t), f) <= maxw:
        return _rtl(t)
    while t and _tl(d, _rtl(t + "…"), f) > maxw:
        t = t[:-1].rstrip()
    return _rtl(t + "…")


def _line_r(d, text, f, xr, y, fill):
    vis = _clip(d, text, f, xr - PAD)
    d.text((xr - _tl(d, vis, f), y), vis, font=f, fill=fill)


def _line_c(d, text, f, cx, y, fill):
    vis = _clip(d, text, f, W - 2 * PAD)
    d.text((cx - _tl(d, vis, f) / 2, y), vis, font=f, fill=fill)


def _lines(d, lines, f, x, y, fill, lh, center=False):
    for l in lines:
        (_line_c if center else _line_r)(d, l, f, x, y, fill)
        y += lh
    return y


def _rich(d, segs, xr, y, width, lh, center=False):
    """טקסט עם כמה משקלים באותה שורה (מודגש + רגיל), מימין לשמאל. segs=[(text, weight, size, color)]."""
    toks = []
    for text, wgt, size, col in segs:
        f = _font(wgt, size)
        for w in str(text or "").split():
            toks.append((w, f, col))
    lines, cur, cw = [], [], 0
    for w, f, col in toks:
        ww = _tl(d, _rtl(w), f)
        sp = _tl(d, " ", f) if cur else 0
        if cur and cw + sp + ww > width:
            lines.append((cur, cw))
            cur, cw, sp = [], 0, 0
        cur.append((w, f, col, ww, sp))
        cw += sp + ww
    if cur:
        lines.append((cur, cw))
    for line, lw in lines:
        x = (xr - (width - lw) / 2) if center else xr
        for w, f, col, ww, sp in line:
            x -= sp
            d.text((x - ww, y), _rtl(w), font=f, fill=col)
            x -= ww
        y += lh
    return y


# ── רכיבים ───────────────────────────────────────────────────────────────────
def _page(bg):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


def _site_host():
    u = os.environ.get("SITE_PUBLIC_URL", "https://refamily.co.il")
    return re.sub(r"^https?://", "", u).rstrip("/")


def _footer(d, snap, n, dark):
    col = FOOT_NAVY if dark else MUTED
    office = ((snap.get("office") or {}).get("office") or "").strip()
    f = _font(500, 40)
    left = "%d" % n
    label = (office + " · " if office else "") + _site_host()
    y = H - 40 - 52
    f2 = _fit(d, label, 500, 40, W - 2 * PAD - 80)
    _line_r(d, label, f2, W - PAD, y, col)
    d.text((PAD, y), left, font=f, fill=col)


def _kicker(d, text, dark, y=PAD):
    _line_r(d, text, _font(800, 40), W - PAD, y, GOLD2 if dark else KICK)
    return y + 60


def _card(d, y0, y1, fill=WHITE):
    d.rounded_rectangle((PAD, y0, W - PAD, y1), radius=CARD_R, fill=fill)


def _initials(name):
    parts = [p for p in str(name or "").split() if p]
    return "".join(p[0] for p in parts[:2])


def _avatar(im, d, photo, name, cx, cy, r, ring, ring_w, bg):
    from PIL import Image, ImageDraw
    box = (cx - r, cy - r, cx + r, cy + r)
    pasted = False
    if photo:
        try:
            ph = Image.open(photo).convert("RGB")
            s = min(ph.size)
            ph = ph.crop(((ph.width - s) // 2, (ph.height - s) // 2, (ph.width + s) // 2, (ph.height + s) // 2))
            ph = ph.resize((2 * r, 2 * r), Image.LANCZOS)
            m = Image.new("L", (2 * r, 2 * r), 0)
            ImageDraw.Draw(m).ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=255)
            im.paste(ph, (cx - r, cy - r), m)
            pasted = True
        except Exception:
            pasted = False
    if not pasted:
        d.ellipse(box, fill=bg)
        ini = _initials(name)
        if ini:
            f = _font(700, int(r * 0.8))
            vis = _rtl(ini)
            bb = d.textbbox((0, 0), vis, font=f)
            d.text((cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2), vis, font=f,
                   fill=WHITE if bg == NAVY2 else NAVY)
    d.ellipse(box, outline=ring, width=ring_w)


def _logo(im, path, xr, y, h):
    """לוגו המשרד על מלבן לבן מעוגל, מיושר לימין. → רוחב שצויר (0 אם אין)."""
    from PIL import Image
    try:
        lg = Image.open(path).convert("RGBA")
    except Exception:
        return 0
    inner = h - 28
    lg = lg.resize((max(1, int(lg.width * inner / lg.height)), inner), Image.LANCZOS)
    pw = lg.width + 48
    from PIL import ImageDraw
    ImageDraw.Draw(im).rounded_rectangle((xr - pw, y, xr, y + h), radius=20, fill=WHITE)
    im.paste(lg, (xr - pw + 24, y + 14), lg)
    return pw


def _logo_path():
    try:
        import social_video
        return social_video._logo_path()
    except Exception:
        return ""


def _check(d, x, y, s, col):
    """סימן וי בקווים (ל-Heebo אין גליף ✓)."""
    d.line([(x, y + s * 0.55), (x + s * 0.38, y + s * 0.9), (x + s, y + s * 0.12)], fill=col, width=max(4, int(s / 6)),
           joint="curve")


def _meet_line(meet_at):
    m = str(meet_at or "").strip()
    if not m:
        return ""
    try:
        t = _dt.datetime.fromisoformat(m)
    except ValueError:
        return ""
    return "נתראה ביום %s %s · %s" % (_DAYS[t.weekday()], t.strftime("%d/%m"), t.strftime("%H:%M"))


def _agents_n(snap):
    try:
        return int((snap.get("office") or {}).get("agents") or 0)
    except (TypeError, ValueError):
        return 0


def _fmt_n(v):
    try:
        return "{:,}".format(int(v))
    except (TypeError, ValueError):
        return ""


# ── העמודים ──────────────────────────────────────────────────────────────────
def _p_cover(snap, n):
    im, d = _page(NAVY)
    ag = snap.get("agent") or {}
    _logo(im, _logo_path(), W - PAD, PAD, 110)
    d.text((PAD, PAD + 34), _rtl("תיק אישי"), font=_font(500, 40), fill=GOLD2)
    width = W - 2 * PAD
    y = 340
    first = (snap.get("owner_first") or "").strip()
    if first:
        f, ls = _block(d, first + ",", 800, 52, width, 2)
        y = _lines(d, ls, f, W - PAD, y, GOLD2, 66) + 8
    f = _font(900, 112)
    for i, l in enumerate(("הנכס שלך", "ראוי למכירה", "מוצלחת.")):
        _line_r(d, l, f, W - PAD, y, GOLD2 if i == 2 else WHITE)
        y += 124
    y += 30
    place = ", ".join(x for x in (snap.get("street"), snap.get("city")) if x)
    rooms = str(snap.get("rooms") or "").strip()
    sub = "לנכס ב" + place if place else "לנכס שלך"
    if rooms:
        sub += " · %s חדרים" % rooms
    f = _font(500, 50)
    _line_r(d, "הכנו לך תוכנית אישית", f, W - PAD, y, LIGHT)
    y += 80
    f2, ls = _block(d, sub, 500, 50, width, 3)
    y = _lines(d, ls, f2, W - PAD, y, LIGHT, 80) + 70
    name = (ag.get("name") or "").strip()
    if name or ag.get("photo"):
        r = 86
        _avatar(im, d, ag.get("photo"), name, W - PAD - r, y + r, r, GOLD, 7, NAVY2)
        tx = W - PAD - 2 * r - 36
        fw = tx - PAD
        fn = _fit(d, name, 800, 56, fw, 34)
        _line_r(d, name, fn, tx, y + r - 66, WHITE)
        _line_r(d, "הסוכן שילווה אותך", _font(500, 44), tx, y + r + 6, LIGHT)
    meet = _meet_line(snap.get("meet_at"))
    if meet:
        y0 = H - 92 - 60 - 130
        d.rounded_rectangle((PAD, y0, W - PAD, y0 + 130), radius=CARD_R, fill=INSET_NAVY)
        _line_r(d, meet, _fit(d, meet, 700, 46, width - 80), W - PAD - 40, y0 + 38, WHITE)
    _footer(d, snap, n, True)
    return im


def _p_agent(snap, n):
    im, d = _page(CREAM)
    ag = snap.get("agent") or {}
    of = snap.get("office") or {}
    y = _kicker(d, "הסוכן שלך", False)
    width = W - 2 * PAD
    inner = width - 2 * 50
    r = 144
    y += 20
    _avatar(im, d, ag.get("photo"), ag.get("name"), W - PAD - r, y + r, r, GOLD, 11, (0xD9, 0xD3, 0xC4))
    tx = W - PAD - 2 * r - 44
    name = (ag.get("name") or "").strip()
    lic = (ag.get("license") or "").strip()
    fn, nls = _block(d, name, 900, 83, tx - PAD, 2, 48)
    nlh = int(fn.size * 1.15)
    nh = len(nls) * nlh + (66 if lic else 0)
    ny = y + r - nh / 2 - 10
    if name:
        ny = _lines(d, nls, fn, tx, ny, NAVY, nlh)
    if lic:
        _line_r(d, "רישיון תיווך מס׳ " + lic, _fit(d, "רישיון תיווך מס׳ " + lic, 500, 43, tx - PAD), tx, ny + 8, MUTED2)
    y += 2 * r + 40
    bottom = H - 150
    bio = (ag.get("bio") or "").strip()
    rev = ag.get("review") or None
    stats = [(of.get("years"), "שנות ניסיון"), (of.get("deals"), "עסקאות"), (of.get("agents"), "סוכנים")]
    stats = [(v, l) for v, l in stats if isinstance(v, int) and v > 0]
    stats_h = 300 if stats else 0
    site = (ag.get("site_url") or "").strip()
    site_h = 70 if site else 0
    rev_lines_max = 4
    rev_h = 0
    if rev and rev.get("text"):
        rf, rls = _block(d, rev["text"], 500, 43, inner - 40, rev_lines_max, 34)
        rev_h = 50 + len(rls) * int(rf.size * 1.6) + (70 if rev.get("by") else 0) + 30
    if bio:
        avail = bottom - y - stats_h - (rev_h + 36 if rev_h else 0) - site_h - 36 - 80
        lh_ratio = 1.65
        max_lines = max(2, int(avail / (47 * lh_ratio)))
        bf, bls = _block(d, bio, 400, 47, inner, max_lines, 36)
        lh = int(bf.size * lh_ratio)
        h = len(bls) * lh + 80
        _card(d, y, y + h)
        _lines(d, bls, bf, W - PAD - 50, y + 36, NAVY, lh)
        y += h + 36
    if stats:
        _card(d, y, y + 264, NAVY)
        _line_r(d, "מאחוריי עומד משרד עם", _font(800, 40), W - PAD - 50, y + 34, GOLD2)
        cols = len(stats)
        cw = width / cols
        for i, (v, l) in enumerate(stats):
            cx = W - PAD - cw * (i + 0.5)
            _line_c(d, _fmt_n(v), _font(900, 86), cx, y + 96, WHITE)
            _line_c(d, l, _font(500, 40), cx, y + 200, WHITE)
        y += 264 + 36
    if rev_h:
        _card(d, y, y + rev_h - 30)
        yy = y + 40
        lh = int(rf.size * 1.6)
        for i, l in enumerate(rls):
            if i == 0:
                l = "״" + l
            if i == len(rls) - 1:
                l = l + "״"
            _line_r(d, l, rf, W - PAD - 50, yy, NAVY)
            yy += lh
        if rev.get("by"):
            by = "— " + rev["by"]
            _line_r(d, by, _fit(d, by, 500, 40, inner), W - PAD - 50, yy + 12, MUTED)
        y += rev_h + 6
    if site:
        txt = "העמוד שלי באתר: " + re.sub(r"^https?://", "", site)
        _line_r(d, txt, _fit(d, txt, 600, 38, width, 26), W - PAD, y, KICK)
    _footer(d, snap, n, False)
    return im


def _p_power(snap, n):
    im, d = _page(NAVY)
    cl = snap.get("claims") or {}
    office = ((snap.get("office") or {}).get("office") or "").strip()
    y = _kicker(d, "הכוח שלנו", True)
    width = W - 2 * PAD
    coop = str(cl.get("coop") or "").replace("<office>", office or "המשרד").strip()
    m = re.search(r"(\d+)\s*%", coop)
    y += 60
    if m:
        big = m.group(1) + "%" + ("+" if "מעל" in coop else "")
        _line_c(d, big, _font(900, 300), W / 2, y, GOLD2)
        y += 340
    if coop:
        f, ls = _block(d, coop, 800, 61, width, 3)
        y = _lines(d, ls, f, W / 2, y, WHITE, int(f.size * 1.35), center=True) + 50
    for part in [p.strip() for p in str(cl.get("rank") or "").split("·") if p.strip()]:
        f, ls = _block(d, part, 600, 46, width, 2)
        y = _lines(d, ls, f, W / 2, y, WHITE, 66, center=True)
    y += 10
    rating, cnt = str(cl.get("g_rating") or "").strip(), str(cl.get("g_count") or "").strip()
    g = " · ".join(x for x in ((rating + " מתוך 5") if rating else "", ("מעל %s ביקורות בגוגל" % cnt) if cnt else "") if x)
    if g:
        f, ls = _block(d, g, 700, 46, width, 2)
        y = _lines(d, ls, f, W / 2, y, GOLD2, 66, center=True)
    url = str(cl.get("g_url") or "").strip()
    if url:
        t = re.sub(r"^https?://", "", url)
        _line_c(d, t, _fit(d, t, 500, 34, width, 22), W / 2, y + 6, FOOT_NAVY)
        y += 56
    y += 60
    z = _agents_n(snap)
    f = _font(500, 50)
    for l in ("כשאתה נותן לנו את הנכס,", "אתה לא מקבל סוכן אחד."):
        _line_c(d, l, f, W / 2, y, LIGHT)
        y += 82
    _line_c(d, ("אתה מקבל %s סוכנים" % _fmt_n(z)) if z else "אתה מקבל את כל סוכני המשרד", _font(900, 58), W / 2, y, WHITE)
    y += 86
    _line_c(d, "וכל הקונים שלהם.", f, W / 2, y, LIGHT)
    _footer(d, snap, n, True)
    return im


def _p_plan(snap, n):
    im, d = _page(CREAM)
    y = _kicker(d, "התוכנית לנכס שלך", False)
    f = _font(900, 86)
    for l in ("ככה נמכור", "את הנכס שלך"):
        _line_r(d, l, f, W - PAD, y + 10, NAVY)
        y += 100
    y += 50
    z = _agents_n(snap)
    steps = [
        ("יום 1", "פרסום בכל מקום:", "אתר המשרד, יד2, פייסבוק ואינסטגרם"),
        ("יום 1", "שליחה לקונים שכבר מחכים,", "כל אחד בדף קונה אישי"),
        ("שבוע 1", "נכס חם", " בסטורי ובמסך הטלוויזיה במשרד"),
        ("כל הזמן", ("%s סוכנים" % _fmt_n(z)) if z else "כל סוכני המשרד", " מציגים את הנכס לקונים שלהם"),
        ("בסוף", "חתימה דיגיטלית", " מהטלפון, וליווי עד המפתח"),
    ]
    xr = W - PAD - 50
    label_w = 200
    tw = W - 2 * PAD - 100 - label_w - 30
    rows, total = [], 0
    from PIL import Image, ImageDraw
    scratch = ImageDraw.Draw(Image.new("RGB", (W, 400)))
    for day, bold, rest in steps:
        segs = [(bold, 800, 46, NAVY), (rest, 400, 46, NAVY)]
        h = _rich(scratch, segs, xr - label_w - 30, 0, tw, 68) + 64
        rows.append((day, segs, h))
        total += h
    _card(d, y, y + total + 20)
    yy = y + 10
    for i, (day, segs, h) in enumerate(rows):
        _line_r(d, day, _font(800, 42), xr, yy + 36, GOLD)
        _rich(d, segs, xr - label_w - 30, yy + 32, tw, 68)
        yy += h
        if i < len(rows) - 1:
            d.line([(PAD + 50, yy), (W - PAD - 50, yy)], fill=CREAM, width=3)
    _footer(d, snap, n, False)
    return im


def _p_buyers(snap, n):
    im, d = _page(CREAM)
    b = snap.get("buyers") or {}
    y = _kicker(d, "הקונים שלנו", False)
    width = W - 2 * PAD
    cnt = int(b.get("n") or 0)
    city = (b.get("city") or snap.get("city") or "").strip()
    y += 60
    if b.get("mode") == "match" and cnt:
        _line_c(d, _fmt_n(cnt), _font(900, 260), W / 2, y, GOLD)
        y += 300
        f = _font(900, 68)
        for l in ("קונים כבר מחכים", "לנכס כמו שלך"):
            _line_c(d, l, f, W / 2, y, NAVY)
            y += 86
        _line_c(d, "והם יקבלו אותו ביום הראשון", _font(500, 43), W / 2, y + 10, MUTED2)
        y += 110
        lines = [l for l in (b.get("lines") or []) if l and int(l[1] or 0) > 0]
        if lines:
            mx = max(int(l[1]) for l in lines) or 1
            h = 60 + len(lines) * 150
            _card(d, y, y + h)
            yy = y + 44
            bar_w = width - 100
            for label, k in lines:
                fl = _fit(d, label, 700, 44, bar_w - 160, 30)
                vis = _clip(d, label, fl, bar_w - 160)
                d.text((W - PAD - 50 - _tl(d, vis, fl), yy), vis, font=fl, fill=NAVY)
                d.text((PAD + 50, yy), _fmt_n(k), font=_font(900, 46), fill=GOLD)
                by = yy + 70
                d.rounded_rectangle((PAD + 50, by, W - PAD - 50, by + 22), radius=11, fill=CREAM)
                fw = max(22, int(bar_w * int(k) / mx))
                d.rounded_rectangle((W - PAD - 50 - fw, by, W - PAD - 50, by + 22), radius=11, fill=NAVY)
                yy += 150
    else:
        if cnt:
            _line_c(d, _fmt_n(cnt), _font(900, 260), W / 2, y, GOLD)
            y += 300
            f, ls = _block(d, "קונים פעילים מחפשים עכשיו" + (" ב" + city if city else ""), 900, 68, width, 3)
        else:
            f, ls = _block(d, "הנכס שלך יגיע לכל הקונים הפעילים במשרד", 900, 68, width, 3)
        y = _lines(d, ls, f, W / 2, y, NAVY, 86, center=True)
        _line_c(d, "והם יקבלו אותו ביום הראשון", _font(500, 43), W / 2, y + 20, MUTED2)
    _footer(d, snap, n, False)
    return im


def _p_cma(snap, n):
    im, d = _page(CREAM)
    title = str((snap.get("cma") or {}).get("title") or "ניתוח שוק")
    f, ls = _block(d, title, 900, 86, W - 2 * PAD, 3)
    _lines(d, ls, f, W - PAD, PAD + 60, NAVY, 100)
    _footer(d, snap, n, False)
    return im


def _p_next(snap, n):
    im, d = _page(NAVY)
    ag = snap.get("agent") or {}
    y = _kicker(d, "הצעד הבא", True)
    f = _font(900, 104)
    for i, l in enumerate(("בוא נמכור", "את הנכס שלך", "ביחד.")):
        _line_r(d, l, f, W - PAD, y + 20, GOLD2 if i == 2 else WHITE)
        y += 120
    y += 90
    z = _agents_n(snap)
    pts = [("סוכן אחד שאחראי עליך, ו-%s שעובדים בשבילך" % _fmt_n(z)) if z else "סוכן אחד שאחראי עליך, וכל המשרד עובד בשבילך",
           "שיווק מלא מהיום הראשון", "עדכון שוטף על כל פנייה וכל ביקור"]
    width = W - 2 * PAD
    fp = _font(500, 47)
    for p in pts:
        _check(d, W - PAD - 44, y + 12, 44, GOLD2)
        ls = _wrap_logical(d, p, fp, width - 80)
        y = _lines(d, ls, fp, W - PAD - 76, y, WHITE, 72) + 30
    name = (ag.get("name") or "").strip()
    phone = (ag.get("phone") or "").strip()
    y0 = H - 92 - 60 - (130 if (name or phone) else 0) - 160
    d.rounded_rectangle((PAD, y0, W - PAD, y0 + 160), radius=CARD_R + 18, fill=GOLD)
    _line_c(d, "נתראה בפגישה ונתחיל", _font(900, 56), W / 2, y0 + 44, ONGOLD)
    if name or phone:
        yy = y0 + 200
        pw = (_tl(d, phone, _font(800, 44)) + 56) if phone else 0
        gap = 30 if (name and phone) else 0
        room = W - 2 * PAD - pw - gap
        fn = _fit(d, name, 700, 46, room, 30)
        vis = _clip(d, name, fn, room) if name else ""
        nw = _tl(d, vis, fn) if name else 0
        x = W / 2 + (nw + gap + pw) / 2
        if name:
            d.text((x - nw, yy + 6), vis, font=fn, fill=LIGHT)
            x -= nw + gap
        if phone:
            d.rounded_rectangle((x - pw, yy, x, yy + 72), radius=36, fill=GREEN)
            d.text((x - pw + 28, yy + 8), phone, font=_font(800, 44), fill=WHITE)
    _footer(d, snap, n, True)
    return im


def render_pages(snap):
    """צילום → רשימת עמודים (RGB 1080×1920): כריכה, סוכן, הכוח שלנו, תוכנית, קונים, [ניתוח שוק], הצעד הבא."""
    s = snap or {}
    order = [_p_cover, _p_agent, _p_power, _p_plan, _p_buyers]
    if s.get("cma"):
        order.append(_p_cma)
    order.append(_p_next)
    return [fn(s, i + 1) for i, fn in enumerate(order)]


def render_pdf(imgs):
    buf = io.BytesIO()
    imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:], resolution=150)
    return buf.getvalue()
