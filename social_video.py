"""social_video.py — סרטוני סטורי + ריל לנכסי המשרד (Kling ב-fal + ffmpeg), אישור בוואטסאפ, פרסום ל-Meta.

ספק: docs/superpowers/specs/2026-11-02-social-video-stories-reels-design.md
תוכנית: docs/superpowers/plans/2026-11-02-social-video.md
החלק העליון טהור (טקסטים, תזמון, חיתוך, תקרות, מכונת מצבים); הרינדור, fal, Claude ו-Graph מוזרקים.
SOCIAL_MODE: רק 'publish' שולח וואטסאפ אישור וכותב ל-Meta (social_publish.soc_mode).
"""
from __future__ import annotations
import re

import social_publish as SP

DAILY_CAP = 3
MONTH_AI_CAP = 100
APPROVE_H = 48
RETRY_DAYS = 3
REPEAT_DAYS = 14
KEEP_FINAL_DAYS = 3
KEEP_MAX_DAYS = 10
DIR_MAX_BYTES = 1_000_000_000
FAL_TIMEOUT_S = 480
RENDER_TIMEOUT_S = 180
W, H = 1080, 1920
SAFE = (65, 290, 1015, 1240)
XFADE = 0.4
LOOP_SEC = 600
CTA = "שלחו הודעה ונחזור אליכם"


# ── טקסטים ותזמון ────────────────────────────────────────────────────────────────
def vid_texts(row, feats, highlight, agent, vphone, office_phone):
    """שורת נכס → הטקסטים שעל המסך, לפי קטע. בלי מספר בית, בלי טלפון בעלים, בלי 'None'."""
    rent = "שכר" in str(row.get("סוג עסקה") or "")
    rooms = SP._num(row.get("חדרים"))
    kind = SP._norm(row.get("סוג נכס")) or "נכס"
    deal = "להשכרה" if rent else "למכירה"
    what = (rooms + " חדרים") if rooms and rooms != "0" else kind
    nb, city = SP._norm(row.get("שכונה")), SP._norm(row.get("עיר / ישוב"))
    pr = SP._price(row.get("מחיר"))
    price = (pr + " ₪" + (" לחודש" if rent else "")) if pr else ""
    size, fl = SP._num(row.get('מ"ר')), SP.soc_floor(row)
    spec = " · ".join(x for x in ((size + ' מ"ר') if size and size != "0" else "", ("קומה " + fl) if fl else "") if x)
    ft = " · ".join([f for f in (feats or []) if f][:3])
    hl = SP.soc_scrub_house(SP.soc_scrub_phones(highlight or ""), row.get("כתובת")).strip(" ·-,")
    s3 = {"main": hl, "sub": ft} if hl else {"main": ft, "sub": ""}
    return {
        "open": {"chip": "חדש בשוק", "title": what + " " + deal,
                 "place": ", ".join(x for x in (nb, city) if x), "price": price},
        "s2": {"main": spec, "sub": ""},
        "s3": s3,
        "end": {"recap": " · ".join(x for x in ((rooms + " חדרים") if rooms and rooms != "0" else "", pr and pr + " ₪") if x),
                "agent": str(agent or "").strip(), "phone": str(vphone or office_phone or "").strip(), "cta": CTA},
    }


def vid_timeline(n_slides, ai):
    """רשימת (קטע, אורך בשניות) — ~14ש' כולל. n_slides = תמונות מצגת אחרי תמונת ה-AI (1 או יותר)."""
    first = "ai" if ai else "kb"
    if n_slides <= 1:
        return [(first, 5), ("s2", 4.5), ("end", 4.5)]
    return [(first, 5), ("s2", 4), ("s3", 2.5), ("end", 2.5)]


# ── חיתוך ל-9:16 בלי סימן המים ──────────────────────────────────────────────────
def _free_spans(w, cw, wm):
    """קטעי x0 (שלמים, כולל) שבהם חלון ברוחב cw לא חופף אופקית לתיבת wm (שברים)."""
    if not wm:
        return [(0, w - cw)]
    a, b = wm[0] * w, wm[2] * w
    out = []
    if a - cw >= 0:
        out.append((0, int(a - cw)))
    if b + cw <= w:
        out.append((int(b + 0.999), w - cw))
    return [(x, y) for x, y in out if y >= x]


def vid_crop_box(w, h, wm, aspect=9 / 16, bias=0.5):
    """חלון 9:16 לכל הגובה (או לכל הרוחב בתמונה צרה) שלא כולל את סימן המים; None אם אין."""
    if w / h < aspect:
        ch = int(w / aspect)
        y0 = (h - ch) // 2
        return (0, y0, w, y0 + ch)
    cw = int(h * aspect)
    want = bias * (w - cw)
    spans = _free_spans(w, cw, wm)
    if not spans:
        return None
    x0 = min((min(max(want, a), b) for a, b in spans), key=lambda x: abs(x - want))
    x0 = int(round(x0))
    return (x0, 0, x0 + cw, h)


def vid_pan_range(w, h, wm, aspect=9 / 16):
    """טווח תנועת המצלמה (שברים 0–1 של iw-ow) שלא נכנס לסימן המים; None אם אין."""
    cw = int(h * aspect)
    room = w - cw
    if room <= 0:
        return (0.5, 0.5)
    if not wm:
        return (0.25, 0.75)
    spans = _free_spans(w, cw, wm)
    if not spans:
        return None
    a, b = max(spans, key=lambda s: s[1] - s[0])
    return (round(a / room, 4), round(b / room, 4))


# ── מותר ליצור / תקרות ───────────────────────────────────────────────────────────
_FINAL_BAD = ("failed", "skipped", "expired")


def vid_can_create(row, history_videos, now, hidden, trigger):
    """(True,'') או (False, סיבה). אותם כללי משרד/פעיל/הסתרה/מסחרי כמו בפוסטים + 2 תמונות + 14 יום לאותה דירה."""
    ok, why = SP.soc_can_publish(row, "ig", [], now, hidden)
    if not ok and why != "מחכה לתמונות":
        return False, why
    if len(SP.soc_images(row)) < 2:
        return False, "צריך לפחות 2 תמונות"
    key = SP._key(row.get("מספר מודעה"))
    akey, afl = SP.soc_addr_key(row), SP.soc_floor(row)
    for h in history_videos or []:
        st = str(h.get("status") or "")
        mine = SP._key(h.get("property_key")) == key or SP._same_apartment(akey, afl, h.get("addr_key"))
        if not mine:
            continue
        if st in ("rendering",):
            return False, "כבר בתהליך"
        if st in _FINAL_BAD or st == "preview":
            continue
        t = SP._ts(h.get("created_at"))
        if t is not None and now - t < REPEAT_DAYS * 86400:
            return False, "כבר נוצר סרטון ב-%s" % SP._dm(t)
    return True, ""


def _month_start(now):
    d = SP._dt.datetime.fromtimestamp(now, SP._IL)
    return SP._dt.datetime(d.year, d.month, 1, tzinfo=SP._IL).timestamp()


def vid_caps(history_videos, now, trigger):
    """תקרה יומית (אוטומטי בלבד) ותקרה חודשית לקליפי AI (הכל)."""
    today, m0 = SP._day(now), _month_start(now)
    day_n = mon_n = 0
    for h in history_videos or []:
        t = SP._ts(h.get("created_at"))
        if t is None:
            continue
        if h.get("trigger") == "auto" and SP._day(t) == today:
            day_n += 1
        if h.get("ai") and t >= m0:
            mon_n += 1
    if trigger == "auto" and day_n >= DAILY_CAP:
        return False, "תקרה יומית (%d)" % DAILY_CAP
    if mon_n >= MONTH_AI_CAP:
        return False, "תקרה חודשית (%d קליפים)" % MONTH_AI_CAP
    return True, ""


# ── מכונת מצבים של האישור ────────────────────────────────────────────────────────
_DONE_WORD = {"approved": "פורסם", "published": "פורסם", "partial": "פורסם", "skipped": "דולג"}


def vid_decide(rec, action, who, now):
    """(מצב חדש | None, הודעה למי שלחץ). רק מ-pending; אחרי 48ש' — פג."""
    st = str(rec.get("status") or "")
    if st == "expired":
        return None, "הסרטון כבר לא בתוקף"
    if st != "pending":
        w = _DONE_WORD.get(st)
        return None, ("כבר %s ע\"י %s" % (w, rec.get("decided_by") or "מישהו")) if w else "הסרטון לא ממתין לאישור"
    sent = SP._ts(rec.get("sent_at"))
    if sent is not None and now - sent > APPROVE_H * 3600:
        return "expired", "הסרטון כבר לא בתוקף"
    if action == "pub":
        return "approved", "יעלה עכשיו"
    return "skipped", "דולג — לא יעלה"


def vid_publish_when(now, blocked):
    """עכשיו, או 08:00 הבא כשחסום (לילה). שבת/חג — הקורא מעביר blocked והלולאה תנסה שוב."""
    if not blocked:
        return now
    d = SP._dt.datetime.fromtimestamp(now, SP._IL)
    t8 = d.replace(hour=8, minute=0, second=0, microsecond=0)
    if d >= t8:
        t8 = t8 + SP._dt.timedelta(days=1)
    return SP._dt.datetime(t8.year, t8.month, t8.day, 8, 0, tzinfo=SP._IL).timestamp()


# ── ניקוי קבצים ──────────────────────────────────────────────────────────────────
_FINAL = ("skipped", "expired", "failed", "published", "preview")


def vid_gc(files, recs_by_token, now):
    """files=[(token, size, mtime)] → טוקנים למחיקה (הישן קודם)."""
    D = 86400
    out, keep = [], []
    for tok, size, mt in sorted(files, key=lambda f: f[2]):
        r = recs_by_token.get(tok)
        if r is None:   # קובץ בלי רשומה (רינדור שנכשל באמצע) — אחרי יום
            if now - mt > D:
                out.append(tok)
            else:
                keep.append((tok, size, mt))
            continue
        st = str(r.get("status") or "")
        upd = SP._ts(r.get("updated_at")) or mt
        if now - mt > KEEP_MAX_DAYS * D:
            out.append(tok)
        elif st in _FINAL and now - upd > KEEP_FINAL_DAYS * D:
            out.append(tok)
        elif st == "partial" and now - upd > RETRY_DAYS * D:
            out.append(tok)
        else:
            keep.append((tok, size, mt))
    total = sum(s for _, s, _ in keep)
    for tok, size, mt in keep:
        if total <= DIR_MAX_BYTES:
            break
        r = recs_by_token.get(tok) or {}
        if str(r.get("status") or "") in _FINAL:
            out.append(tok)
            total -= size
    return out


# ── שכבות טקסט (Pillow + bidi + Heebo) — גרסה א' "קולנועי" ──────────────────────
NAVY0 = (14, 29, 51)
GOLD = (228, 197, 107)
WHITE = (255, 255, 255)
SHADE = (8, 16, 30)
_FONT_PATH = None


def _font(size, weight=800):
    from PIL import ImageFont
    import os
    global _FONT_PATH
    if _FONT_PATH is None:
        _FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Heebo-VF.ttf")
    f = ImageFont.truetype(_FONT_PATH, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def _rtl(s):
    try:
        from bidi.algorithm import get_display
        return get_display(str(s or ""))
    except Exception:   # pragma: no cover
        return str(s or "")


def _fit(d, s, size, weight, maxw):
    """מקטין את הגופן עד שהשורה נכנסת לרוחב maxw."""
    f = _font(size, weight)
    while size > 24 and d.textlength(_rtl(s), font=f) > maxw:
        size -= 4
        f = _font(size, weight)
    return f


def _txt(d, x, y, s, size, weight, fill, anchor="ra"):
    if not s:
        return
    f = _fit(d, s, size, weight, SAFE[2] - SAFE[0])
    d.text((x, y), _rtl(s), font=f, fill=fill, anchor=anchor)


def _logo(L, path, y=SAFE[1], h=150):
    """לוגו המשרד על מלבן לבן (פינות ישרות), ממורכז (אייל: גדול, מלבני)."""
    from PIL import Image, ImageDraw
    try:
        lg = Image.open(path).convert("RGBA")
    except Exception:
        return
    r = (h - 40) / lg.height
    lg = lg.resize((max(1, int(lg.width * r)), h - 40), Image.LANCZOS)
    pw = lg.width + 64
    box = Image.new("RGBA", (pw, h), (0, 0, 0, 0))
    ImageDraw.Draw(box).rectangle((0, 0, pw - 1, h - 1), fill=(255, 255, 255, 240))
    box.alpha_composite(lg, (32, 20))
    L.alpha_composite(box, ((W - pw) // 2, y))


def _shade(top=0.30, bottom=0.55, a_top=150, a_bot=210):
    from PIL import Image, ImageDraw
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    for y in range(H):
        a = 0
        if y < H * top:
            a = int(a_top * (1 - y / (H * top)))
        if y > H * (1 - bottom):
            a = max(a, int(a_bot * ((y - H * (1 - bottom)) / (H * bottom))))
        if a:
            d.line([(0, y), (W, y)], fill=SHADE + (a,))
    return L


def _band(L, y0, y1, a=150, soft=120):
    """רצועה כהה רכה מאחורי טקסט באמצע התמונה."""
    from PIL import Image, ImageDraw
    B = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(B)
    for y in range(max(0, y0 - soft), min(H, y1 + soft)):
        k = 1.0 if y0 <= y <= y1 else 1 - min(abs(y - y0), abs(y - y1)) / soft
        d.line([(0, y), (W, y)], fill=SHADE + (int(a * k),))
    return Image.alpha_composite(L, B)


def _chip(d, xr, y, s, size=34, h=64, pad=22):
    if not s:
        return
    f = _font(size, 800)
    w = d.textlength(_rtl(s), font=f) + pad * 2
    d.rounded_rectangle((xr - w, y, xr, y + h), radius=h // 2, fill=GOLD + (255,))
    d.text((xr - pad, y + h // 2), _rtl(s), font=f, fill=NAVY0 + (255,), anchor="rm")


def vid_layers(texts, timeline, logo_path, ai, out_dir):
    """PNG שקוף 1080×1920 לכל קטע בציר הזמן → {שם קטע: נתיב}."""
    from PIL import Image, ImageDraw
    import os
    os.makedirs(out_dir, exist_ok=True)
    xr, cx = SAFE[2] - 5, W // 2
    o, s2, s3, e = texts["open"], texts["s2"], texts["s3"], texts["end"]
    out = {}
    for name, _dur in timeline:
        if name in ("ai", "kb"):
            L = _shade()
            _logo(L, logo_path)
            d = ImageDraw.Draw(L)
            _chip(d, xr, 760, o.get("chip"))
            _txt(d, xr, 846, o.get("title"), 96, 800, WHITE)
            _txt(d, xr, 966, o.get("place"), 46, 600, WHITE)
            _txt(d, xr, 1040, o.get("price"), 104, 800, GOLD)
            if name == "ai":
                _txt(d, xr, 1205, "הדמיית תנועה", 26, 500, (255, 255, 255, 215))
        elif name in ("s2", "s3"):
            t = s2 if name == "s2" else s3
            L = _band(_shade(top=0.3, bottom=0.2, a_bot=90), 890, 1080) if t.get("main") else _shade(top=0.3, bottom=0.2, a_bot=90)
            _logo(L, logo_path)
            d = ImageDraw.Draw(L)
            first, second = (WHITE, GOLD) if name == "s2" else (GOLD, WHITE)
            _txt(d, cx, 900, t.get("main"), 80 if name == "s2" else 84, 800, first, anchor="ma")
            _txt(d, cx, 1010, t.get("sub"), 56, 700, second, anchor="ma")
        else:
            L = Image.alpha_composite(Image.new("RGBA", (W, H), SHADE + (165,)), _shade())
            _logo(L, logo_path)
            d = ImageDraw.Draw(L)
            _txt(d, cx, 790, e.get("recap"), 52, 700, WHITE, anchor="ma")
            if e.get("agent") or e.get("phone"):
                _txt(d, cx, 900, "לפרטים", 40, 500, (220, 225, 235), anchor="ma")
            _txt(d, cx, 955, e.get("agent"), 88, 800, WHITE, anchor="ma")
            _txt(d, cx, 1068, e.get("phone"), 80, 800, GOLD, anchor="ma")
            _txt(d, cx, 1180, e.get("cta"), 40, 500, WHITE, anchor="ma")
        p = os.path.join(out_dir, "%s.png" % name)
        L.save(p)
        out[name] = p
    return out
