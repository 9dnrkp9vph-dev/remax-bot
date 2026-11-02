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
STALE_S = 1800   # רינדור/פרסום שלא התקדם חצי שעה = נקטע (דפלוי/אתחול באמצע)
CTA = "חייגו"   # [02/11] אייל — במקום "שלחו הודעה ונחזור אליכם"


# ── טקסטים ותזמון ────────────────────────────────────────────────────────────────
def _pos(v):
    """מספר חיובי כמחרוזת, אחרת '' (מחיר 0 / '—' / טקסט לא נכנסים למסך)."""
    try:
        return v if float(str(v).replace(",", "")) > 0 else ""
    except ValueError:
        return ""


def vid_texts(row, feats, highlight, agent, vphone, office_phone):
    """שורת נכס → הטקסטים שעל המסך, לפי קטע. בלי מספר בית, בלי טלפון בעלים, בלי 'None'."""
    rent = "שכר" in str(row.get("סוג עסקה") or "")
    rooms = _pos(SP._num(row.get("חדרים")))
    kind = SP._norm(row.get("סוג נכס")) or "נכס"
    deal = "להשכרה" if rent else "למכירה"
    what = (rooms + " חדרים") if rooms and rooms != "0" else kind
    nb, city = SP._norm(row.get("שכונה")), SP._norm(row.get("עיר / ישוב"))
    pr = SP._price(row.get("מחיר")) if _pos(SP._num(row.get("מחיר"))) else ""
    price = (pr + " ₪" + (" לחודש" if rent else "")) if pr else ""
    size, fl = _pos(SP._num(row.get('מ"ר'))), SP.soc_floor(row)
    spec = " · ".join(x for x in ((size + ' מ"ר') if size and size != "0" else "", ("קומה " + fl) if fl else "") if x)
    ft = " · ".join([f for f in (feats or []) if f][:3])
    hl = SP.soc_scrub_house(SP.soc_scrub_phones(highlight or ""), row.get("כתובת")).strip(" ·-,")
    s3 = {"main": hl, "sub": ft} if hl else {"main": ft, "sub": ""}
    return {
        "open": {"chip": "",   # [02/11] אייל: בלי "חדש בשוק"
                 "title": what + " " + deal,
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
        if st in ("rendering", "publishing"):
            if now - (SP._ts(h.get("updated_at") or h.get("created_at")) or 0) < STALE_S:
                return False, "כבר בתהליך"
            continue
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


# ── הרכבה ב-ffmpeg ───────────────────────────────────────────────────────────────
def vid_ffmpeg():
    """נתיב ffmpeg: החבילה imageio-ffmpeg (בינארי סטטי, Render) ואחרת ffmpeg של המערכת."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        import shutil
        return shutil.which("ffmpeg")


def _music_dir():
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "music")


def vid_music(key):
    """קטע מוזיקה לנכס (בחירה קבועה לפי מספר המודעה) מ-assets/music; אין קטעים → פד שקט שמיוצר
    פעם אחת ב-ffmpeg (צלילים סינתטיים שלנו — בלי רישיון של אף אחד)."""
    import os, hashlib, tempfile, subprocess
    d = _music_dir()
    tracks = sorted(f for f in (os.listdir(d) if os.path.isdir(d) else []) if f.lower().endswith((".mp3", ".m4a")))
    if tracks:
        i = int(hashlib.md5(str(key or "").encode()).hexdigest(), 16) % len(tracks)
        return os.path.join(d, tracks[i])
    pad = os.path.join(tempfile.gettempdir(), "effie_pad_v1.m4a")
    if os.path.exists(pad) and os.path.getsize(pad) > 1000:
        return pad
    ff = vid_ffmpeg()
    if not ff:
        return None
    # Am7 → Fmaj7 בשקט, עם נשימה איטית (טרמולו) — רקע עדין בלבד
    expr = ("0.06*(sin(2*PI*220*t)+sin(2*PI*261.63*t)+sin(2*PI*329.63*t)+0.6*sin(2*PI*392*t))*lt(t,7)"
            "+0.06*(sin(2*PI*174.61*t)+sin(2*PI*220*t)+sin(2*PI*261.63*t)+0.6*sin(2*PI*329.63*t))*gte(t,7)")
    try:
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc='%s':s=48000:d=15" % expr, "-af",
                        "tremolo=f=0.25:d=0.35,lowpass=f=1800,afade=in:d=1.5,afade=out:st=12.5:d=2.5",
                        "-c:a", "aac", "-b:a", "128k", pad], check=True, capture_output=True, timeout=60)
        return pad
    except Exception:
        return None


def _jpeg_to_file(data, path):
    with open(path, "wb") as f:
        f.write(data)
    return path


def vid_compose(clip_path, slides, layers, timeline, music_path, out_path, run=None):
    """קליפ AI (או Ken Burns על slides[0]) + שקפים בתנועה + שכבות טקסט + מוזיקה → MP4 9:16.
    slides = [(jpeg_bytes, wm|None)]: [0]=תמונת ה-AI, [1:]=שקפים; הסיום על השקף הרביעי אם יש, אחרת האחרון.
    → {'ok', 'duration', 'cover', 'error'}."""
    import os, subprocess, tempfile
    from PIL import Image
    import io
    run = run or subprocess.run
    ff = vid_ffmpeg()
    if not ff:
        return {"ok": False, "error": "אין ffmpeg"}
    tmp = tempfile.mkdtemp(prefix="vid_")
    segs, durs = [], [d for _, d in timeline]
    n = len(timeline)
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", "-an",
           "-threads", "1"]

    def sh(cmd):
        run(cmd, check=True, capture_output=True, timeout=RENDER_TIMEOUT_S)

    try:
        slide_i = 1
        for i, (name, dur) in enumerate(timeline):
            seg_d = dur + (XFADE if i < n - 1 else 0)
            seg = os.path.join(tmp, "s%d.mp4" % i)
            ov = layers[name]
            if name == "ai" and clip_path:
                fc = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,"
                      "tpad=stop_mode=clone:stop_duration=2[v];[v][1:v]overlay[o]")
                sh([ff, "-v", "error", "-y", "-i", clip_path, "-i", ov, "-filter_complex", fc, "-map", "[o]",
                    "-t", "%.2f" % seg_d] + enc + [seg])
            elif name in ("ai", "kb"):
                data, wm = slides[0]
                im = Image.open(io.BytesIO(data)).convert("RGB")
                box = vid_crop_box(im.width, im.height, wm) or vid_crop_box(im.width, im.height, None)
                p = os.path.join(tmp, "kb.jpg")
                im.crop(box).resize((1440, 2560), Image.LANCZOS).save(p, quality=92)
                fr = int(round(seg_d * 30))
                fc = ("[0:v]zoompan=z='1+0.08*on/%d':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=1080x1920:fps=30,"
                      "setsar=1[v];[v][1:v]overlay[o]" % (fr, fr))
                sh([ff, "-v", "error", "-y", "-i", p, "-i", ov, "-filter_complex", fc, "-map", "[o]",
                    "-frames:v", str(fr)] + enc + [seg])
            else:
                if name == "end" and len(slides) > 3:
                    idx = 3
                else:
                    idx = min(slide_i, len(slides) - 1)
                if name != "end":
                    slide_i += 1
                data, wm = slides[idx]
                im = Image.open(io.BytesIO(data)).convert("RGB")
                rng = vid_pan_range(im.width, im.height, wm) or (0.5, 0.5)
                a, b = (rng[1], rng[0]) if name == "s3" else rng   # כיוון מתחלף בין שקפים
                p = os.path.join(tmp, "sl%d.jpg" % i)
                im.resize((max(1125, int(im.width * 2000 / im.height)), 2000), Image.LANCZOS).save(p, quality=92)
                xexp = "(iw-ow)*(%.4f+(%.4f)*t/%.2f)" % (a, b - a, seg_d)
                fc = ("[0:v]fps=30,crop=1125:2000:'%s':0,scale=1080:1920,setsar=1[v];[v][1:v]overlay[o]" % xexp)
                sh([ff, "-v", "error", "-y", "-loop", "1", "-t", "%.2f" % seg_d, "-i", p, "-i", ov,
                    "-filter_complex", fc, "-map", "[o]", "-t", "%.2f" % seg_d] + enc + [seg])
            segs.append(seg)
        total = sum(durs)
        cmd = [ff, "-v", "error", "-y"]
        for s in segs:
            cmd += ["-i", s]
        if music_path:
            cmd += ["-i", music_path]
        else:
            cmd += ["-f", "lavfi", "-t", "%.2f" % total, "-i", "anullsrc=r=48000:cl=stereo"]
        parts, last, off = [], "[0:v]", 0.0
        for i in range(1, len(segs)):
            off += durs[i - 1]
            lab = "[x%d]" % i if i < len(segs) - 1 else "[v]"
            parts.append("%s[%d:v]xfade=transition=fade:duration=%.2f:offset=%.2f%s" % (last, i, XFADE, off, lab))
            last = lab
        if len(segs) == 1:
            parts.append("[0:v]null[v]")
        ai = len(segs)
        parts.append("[%d:a]atrim=0:%.2f,asetpts=PTS-STARTPTS,volume=0.35,afade=in:d=0.5,afade=out:st=%.2f:d=1.0,"
                     "aresample=48000[a]" % (ai, total, max(0, total - 1.0)))
        cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-t", "%.2f" % total,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
                "-c:a", "aac", "-ar", "48000", "-b:a", "128k", "-movflags", "+faststart", "-threads", "1", out_path]
        sh(cmd)
        cover = out_path.rsplit(".", 1)[0] + "-cover.jpg"
        sh([ff, "-v", "error", "-y", "-ss", "0.5", "-i", out_path, "-frames:v", "1", "-q:v", "3", cover])
        return {"ok": True, "duration": _duration(ff, out_path, run) or total, "cover": cover}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"")[-300:]
        return {"ok": False, "error": "ffmpeg: %s" % (tail.decode("utf-8", "replace") if isinstance(tail, bytes) else tail)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _duration(ff, path, run):
    """משך הקובץ בשניות — מתוך הפלט של ffmpeg -i (בלי ffprobe, שאין ב-imageio-ffmpeg)."""
    import subprocess
    try:
        r = subprocess.run([ff, "-i", path], capture_output=True, text=True, timeout=30)
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr or "")
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    except Exception:
        return None


# ── fal.ai (image-to-video) ──────────────────────────────────────────────────────
FAL_DEFAULT_MODEL = "fal-ai/kling-video/v2.5-turbo/pro/image-to-video"
_NEG = "people, person, text, logo, watermark, new furniture, distortion, blur"
MODEL_ARGS = {"kling": {"duration": "5", "negative_prompt": _NEG},
              "hailuo": {"duration": "6", "prompt_optimizer": False}}
FAL_COST = {"kling": 0.35, "hailuo": 0.19}


class FalError(Exception):
    def __init__(self, msg, code=None, unknown=False):
        super().__init__(msg)
        self.code, self.unknown = code, unknown


def vid_prompt(room):
    r = str(room or "").strip() or "room"
    if "facade" in r or "building" in r or "חזית" in r:
        return ("Slow cinematic push-in on the building facade, natural daylight, smooth stable camera, realistic, "
                "keep the building exactly as in the photo, do not invent details, no people, no text, no logos, vertical 9:16")
    return ("Slow cinematic dolly-in through the %s, natural daylight, smooth stable camera, realistic, "
            "keep the room exactly as in the photo, do not invent details, no people, no text, no logos, vertical 9:16" % r)


class Fal:
    """fal queue REST. המפתח רק בכותרת Authorization; כל הודעת שגיאה עוברת _scrub."""

    def __init__(self, http, key, model=None, sleep=None, clock=None):
        import time as _t
        self.http, self.key = http, key
        self.model = (model or FAL_DEFAULT_MODEL).strip()
        self.sleep, self.clock = sleep or _t.sleep, clock or _t.time

    def _family(self):
        return "hailuo" if ("hailuo" in self.model or "minimax" in self.model) else "kling"

    def args(self):
        return dict(MODEL_ARGS[self._family()])

    def cost(self):
        return FAL_COST[self._family()]

    def _err(self, msg, code=None, unknown=False):
        return FalError(SP._scrub(msg, [self.key]), code=code, unknown=unknown)

    def clip(self, jpeg, prompt):
        import base64
        hd = {"Authorization": "Key " + self.key, "Content-Type": "application/json"}
        body = dict(self.args(), prompt=prompt, image_url="data:image/jpeg;base64," + base64.b64encode(jpeg).decode())
        try:
            r = self.http.post("https://queue.fal.run/" + self.model, headers=hd, json=body, timeout=60)
        except Exception as e:
            raise self._err("fal submit: %s" % e, unknown=True)
        if getattr(r, "status_code", 200) >= 400:
            raise self._err("fal %s: %s" % (r.status_code, str(getattr(r, "text", ""))[:200]), code=r.status_code)
        try:
            j = r.json() or {}
        except Exception as e:
            raise self._err("fal submit reply: %s" % e, unknown=True)
        st_url, res_url = j.get("status_url"), j.get("response_url")
        if not st_url or not res_url:
            raise self._err("fal: no request urls")
        t0 = self.clock()
        while True:
            if self.clock() - t0 > FAL_TIMEOUT_S:
                raise self._err("fal: timeout", unknown=True)
            try:
                s = (self.http.get(st_url, headers=hd, timeout=30).json() or {}).get("status")
            except Exception:
                s = "IN_PROGRESS"   # תקלת רשת רגעית בבדיקת הסטטוס — ממשיכים לחכות
            if not s:
                s = "IN_PROGRESS"   # תשובה בלי status (4xx/זמני) — לא כשל ודאי; ממשיכים עד ה-timeout
            if s == "COMPLETED":
                break
            if s not in ("IN_QUEUE", "IN_PROGRESS"):
                raise self._err("fal job %s" % s)
            self.sleep(8)
        try:   # מכאן העבודה כבר הושלמה (ומחויבת) — כל תקלה = unknown, בלי הגשה חוזרת
            res = self.http.get(res_url, headers=hd, timeout=30).json() or {}
            url = (res.get("video") or {}).get("url")
            data = self.http.get(url, timeout=120).content if url else b""
        except Exception as e:
            raise self._err("fal result: %s" % e, unknown=True)
        if not url:
            raise self._err("fal: no video url", unknown=True)
        if not data:
            raise self._err("fal: empty video")
        return data


def vid_ai_clip(fal, jpeg, room):
    """→ (bytes|None, קוד שגיאה|'timeout'|None, עלות). ניסיון חוזר אחד רק לכשל ודאי שאינו הרשאה/קרדיט."""
    cost = 0.0
    for attempt in range(2):
        try:
            data = fal.clip(jpeg, vid_prompt(room))
            return data, None, cost + fal.cost()
        except FalError as e:
            if e.code in (401, 402, 403):
                return None, e.code, cost
            cost += fal.cost() if e.code is None else 0
            if e.unknown:
                return None, "timeout", cost
            if attempt == 1:
                return None, e.code or "failed", cost
    return None, "failed", cost


# ── בחירת תמונות (Claude vision) ─────────────────────────────────────────────────
WM_DEFAULT = (0.02, 0.02, 0.18, 0.14)   # הפינה השמאלית-העליונה — המקום הנפוץ של "Yad2"
CLAUDE_MODEL = "claude-sonnet-4-5"
_PICK_PROMPT = """These are photos of one apartment for sale (numbered from 0).
Return ONLY a JSON object, no prose:
{"ai": <index of the single best photo for a slow cinematic camera move: bright living room or building front, no people, no text>,
 "room": "<short English room type of that photo, e.g. living room / kitchen / bedroom / balcony / building facade>",
 "slides": [<up to 3 other indexes, different rooms, best first>],
 "highlight": "<up to 4 Hebrew words taken ONLY from the description below, the strongest selling point, or empty>",
 "wm": {"<index>": [x0, y0, x1, y1] or null},   // box of any "Yad2" watermark per photo, fractions 0-1 of width/height
 "skip": [<indexes with people, floor plans, text-only or 'photos coming soon' placeholders>]}
Description: """


def _fallback_pick(n):
    return {"ai": 0, "room": "room", "slides": list(range(1, min(n, 4))), "highlight": "",
            "wm": {i: WM_DEFAULT for i in range(n)}, "skip": []}


def _small_jpeg(data, px=512):
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((px, px))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    return b.getvalue()


def vid_pick(http, api_key, images, desc, feats):
    """→ {'ai','room','slides','highlight','wm','skip'}; כל כשל → בחירה לפי סדר יד2."""
    import base64, json
    n = len(images or [])
    fb = _fallback_pick(n)
    if not http or not api_key or n < 2:
        return fb
    try:
        content = []
        for i, im in enumerate(images[:8]):
            content.append({"type": "text", "text": "Photo %d:" % i})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(_small_jpeg(im)).decode()}})
        content.append({"type": "text", "text": _PICK_PROMPT + str(desc or "")[:1500]})
        r = http.post("https://api.anthropic.com/v1/messages",
                      headers={"anthropic-version": "2023-06-01", "x-api-key": api_key, "content-type": "application/json"},
                      json={"model": CLAUDE_MODEL, "max_tokens": 600, "messages": [{"role": "user", "content": content}]},
                      timeout=90)
        if getattr(r, "status_code", 200) >= 400:
            return fb
        text = "".join(c.get("text", "") for c in (r.json() or {}).get("content") or [])
        m = re.search(r"\{.*\}", text, re.S)
        j = json.loads(m.group()) if m else None
        m_ = min(n, 8)
        ai = j.get("ai") if isinstance(j, dict) else None
        if not isinstance(ai, int) or not 0 <= ai < m_:
            return fb
        skip = [i for i in (j.get("skip") or []) if isinstance(i, int) and 0 <= i < m_ and i != ai]
        slides = []
        for i in j.get("slides") or []:
            if isinstance(i, int) and 0 <= i < m_ and i != ai and i not in skip and i not in slides:
                slides.append(i)
        if not slides:
            slides = [i for i in range(m_) if i != ai and i not in skip][:3]
        wm = {}
        for i in range(n):
            v = (j.get("wm") or {}).get(str(i), WM_DEFAULT) if isinstance(j.get("wm"), dict) else WM_DEFAULT
            ok = isinstance(v, (list, tuple)) and len(v) == 4 and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in v)
            wm[i] = tuple(float(x) for x in v) if ok else (None if v is None else WM_DEFAULT)
        hl = SP.soc_scrub_phones(str(j.get("highlight") or "")).strip()
        words = hl.split()
        if len(words) > 4 or any(w.strip(".,·\"'") not in str(desc or "") for w in words):
            hl = ""
        return {"ai": ai, "room": str(j.get("room") or "room")[:40], "slides": slides[:3], "highlight": hl,
                "wm": wm, "skip": skip}
    except Exception:
        return fb


# ── תזמור: יצירה ופרסום ──────────────────────────────────────────────────────────
class VidStore:
    """קבצי הסרטונים על הדיסק הקבוע (MAP_CACHE_DIR/social_videos), בשם טוקן אקראי."""

    def __init__(self, root=None):
        import os, tempfile
        base = root or os.path.join(os.environ.get("MAP_CACHE_DIR") or tempfile.gettempdir(), "social_videos")
        os.makedirs(base, exist_ok=True)
        self.root = base

    def new_token(self):
        import secrets
        return secrets.token_urlsafe(12).replace("-", "x").replace("_", "y")

    def path(self, tok):
        import os
        return os.path.join(self.root, "%s.mp4" % tok)

    def cover(self, tok):
        import os
        return os.path.join(self.root, "%s-cover.jpg" % tok)

    def exists(self, tok):
        import os
        return bool(tok) and re.fullmatch(r"[A-Za-z0-9]+", str(tok)) is not None and os.path.exists(self.path(tok))

    def files(self):
        import os
        out = []
        for f in os.listdir(self.root):
            m = re.fullmatch(r"([A-Za-z0-9]+)\.mp4", f)
            if m:
                p = os.path.join(self.root, f)
                out.append((m.group(1), os.path.getsize(p), os.path.getmtime(p)))
        return out

    def remove(self, tok):
        import os
        for p in (self.path(tok), self.cover(tok)):
            try:
                os.remove(p)
            except OSError:
                pass


_VLOCK = None
_VINFLIGHT = set()


def _vlock():
    global _VLOCK
    if _VLOCK is None:
        import threading
        _VLOCK = threading.Lock()
    return _VLOCK


_RENDER_LOCK = None


def _render_lock():
    """רינדור אחד בכל רגע (worker יחיד — לא להאט את השרת שמשרת סוכנים)."""
    global _RENDER_LOCK
    if _RENDER_LOCK is None:
        import threading
        _RENDER_LOCK = threading.Lock()
    return _RENDER_LOCK


def _office(G):
    return ((G["_load_config"]() or {}).get("v2_office")) or {}


def _iso(t):
    return SP._dt.datetime.fromtimestamp(t, SP._dt.timezone.utc).isoformat()


def _base(env):
    return str(env.get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/")


def _row_by_key(G, key):
    return next((r for r in SP.soc_office_rows(G) if SP._key(r.get("מספר מודעה")) == key), None)


def _logo_path():
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "family-logo.png")


def vid_create_one(G, key, trigger, by_phone, http=None, now=None, env=None, store=None):
    """יוצר סרטון לנכס אחד. → {'ok','id','status','reason','ai'}. preview: נשמר לכרטיס; publish: נשלח לאישור."""
    k0 = SP._key(key)
    with _vlock():
        if k0 in _VINFLIGHT:
            return {"ok": False, "id": "", "status": "", "reason": "הנכס כבר בתהליך", "ai": False}
        _VINFLIGHT.add(k0)
    try:
        return _vid_create_one(G, k0, trigger, by_phone, http, now, env, store)
    finally:
        with _vlock():
            _VINFLIGHT.discard(k0)


def _vid_create_one(G, key, trigger, by_phone, http, now, env, store):
    import time as _t, os, tempfile, shutil
    env = SP._env(env)
    now = _t.time() if now is None else now
    mode = SP.soc_mode(env)
    res = {"ok": False, "id": "", "status": "", "reason": "", "ai": False}
    if mode == "off":
        res["reason"] = "כבוי"
        return res
    row = _row_by_key(G, key)
    if not row:
        res["reason"] = "הנכס לא נמצא"
        return res
    try:
        hist = G["_sbdb"].video_recent(31) or []
    except Exception:
        if mode == "publish":
            res["reason"] = "לא ניתן לקרוא את היסטוריית הסרטונים"
            return res
        hist = []
    hidden = SP.soc_hidden(G)
    if hidden is None:
        if mode == "publish":
            res["reason"] = "לא ניתן לבדוק הסתרה מהאתר"
            return res
        hidden = set()
    for ok, why in (vid_can_create(row, hist, now, hidden, trigger), vid_caps(hist, now, trigger)):
        if not ok:
            res["reason"] = why
            return res
    if http is None:
        import requests as http
    store = store or VidStore()
    tok = store.new_token()
    secrets_ = [str(env.get(k) or "") for k in ("FAL_KEY", "CLAUDE_API_KEY", "META_TOKEN")]
    rec = {"property_key": key, "addr_key": SP.soc_addr_key(row) + "#" + SP.soc_floor(row), "floor": SP.soc_floor(row),
           "trigger": trigger, "mode": mode, "by_phone": str(by_phone or ""), "status": "rendering",
           "video_token": tok, "ai": False}
    saved = G["_sbdb"].video_insert(rec)
    if not saved or not saved.get("id"):
        res["reason"] = "לא ניתן לרשום את הסרטון"
        return res
    vid = res["id"] = saved["id"]
    name, role = SP._who(G, trigger, by_phone)
    tmp = tempfile.mkdtemp(prefix="vidc_")
    upd = {}
    try:
        imgs = []
        for src in SP.soc_images(row)[:8]:
            data = SP.soc_fetch_jpeg(http, src, False)
            if data:
                imgs.append(data)
        if len(imgs) < 2:
            raise RuntimeError("פחות מ-2 תמונות ירדו")
        desc = SP._clean_desc(G)(row.get("_desc_ae") or row.get("תיאור") or "")
        feats = [f for f in (G["_row_feats"](row) or []) if f]
        pick = vid_pick(http, str(env.get("CLAUDE_API_KEY") or ""), imgs, desc, feats)
        ai_i = pick["ai"]
        order = [ai_i] + [i for i in pick["slides"] if i != ai_i]
        if len(order) < 2:
            order = [ai_i] + [i for i in range(len(imgs)) if i != ai_i][:3]
        slides = [(imgs[i], pick["wm"].get(i)) for i in order]
        clip_path, cost = None, 0.0
        fal_key = str(env.get("FAL_KEY") or "").strip()
        if fal_key:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(imgs[ai_i])).convert("RGB")
            box = vid_crop_box(im.width, im.height, pick["wm"].get(ai_i))
            if box:
                b = io.BytesIO()
                im.crop(box).save(b, "JPEG", quality=92)
                fal = Fal(http, fal_key, model=str(env.get("FAL_VIDEO_MODEL") or "") or None)
                data, err, cost = vid_ai_clip(fal, b.getvalue(), pick["room"])
                upd["ai_cost_usd"] = round(cost, 2)
                if data:
                    clip_path = os.path.join(tmp, "clip.mp4")
                    with open(clip_path, "wb") as f:
                        f.write(data)
                    upd["ai_model"] = fal.model
                    upd["ai"] = True   # שולם — נספר בעלות/במכסה גם אם הרינדור ייכשל
                elif err in (401, 402, 403):
                    SP.soc_daily_alert(G, "fal", "סרטונים לרשתות", "חשבון fal — צריך לטעון קרדיט או מפתח חדש", now)
        ai = clip_path is not None
        agent = str(row.get("סוכן 1") or "").strip()
        try:
            vphone = G["_vphone_for_name"](agent) if agent else ""
        except Exception:
            vphone = ""
        texts = vid_texts(row, feats, pick["highlight"], agent, vphone, str(_office(G).get("phone") or ""))
        tl = vid_timeline(min(2, len(slides) - 1), ai)
        layers = vid_layers(texts, tl, _logo_path(), ai, os.path.join(tmp, "L"))
        music = vid_music(key)
        with _render_lock():
            out = vid_compose(clip_path, slides, layers, tl, music, store.path(tok))
        if not out.get("ok"):
            raise RuntimeError(out.get("error") or "רינדור נכשל")
        upd.update(ai=ai, ai_cost_usd=round(cost, 2), texts=texts, music=os.path.basename(music or ""))
        if mode == "publish":
            import secrets
            upd.update(status="pending", sent_at=_iso(now), review_token=secrets.token_urlsafe(16))
            G["_sbdb"].video_update(vid, upd)
            full = dict(saved, **upd)
            try:
                upd2 = {"recipients": vid_send_review(G, full, _base(env), env) or []}
            except Exception as e:
                upd2 = {"recipients": [], "error": SP._scrub("אישור: %s" % e, secrets_)[:300]}
            G["_sbdb"].video_update(vid, upd2)
            upd.update(upd2)
        else:
            upd["status"] = "preview"
            G["_sbdb"].video_update(vid, upd)
        res.update(ok=True, status=upd["status"], ai=ai)
        G["_log_activity"](name, role, by_phone or "", "סרטון לרשתות — נוצר" + ("" if ai else " (ללא AI)"), key)
    except Exception as e:
        msg = SP._scrub(str(e), secrets_)[:600]
        G["_sbdb"].video_update(vid, dict(upd, status="failed", error=msg))
        store.remove(tok)
        res.update(status="failed", reason=msg)
        G["_log_activity"](name, role, by_phone or "", "סרטון לרשתות — נכשל", key)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return res


CHANNELS = ("ig_story", "ig_reel", "fb_story", "fb_reel")
_PUBLISHABLE = ("approved", "partial", "publishing")


def vid_new_link(G, rec, channel):
    """קוד קישור וואטסאפ חדש (social_links) → code."""
    import secrets
    for _ in range(3):
        code = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")[:7]
        if G["_sbdb"].link_insert({"code": code, "video_id": rec.get("id"), "property_key": rec.get("property_key"),
                                   "channel": channel}):
            return code
    return ""


def vid_publish(G, vid, http=None, now=None, env=None, store=None, channels=None):
    """מעלה סרטון מאושר לערוצים שעוד לא הצליחו. → {'ok','status','reason', <ערוץ>: מצב}."""
    import time as _t
    env = SP._env(env)
    now = _t.time() if now is None else now
    res = {"ok": False, "status": "", "reason": ""}
    rec = G["_sbdb"].video_get(vid)
    if not rec:
        res["reason"] = "הסרטון לא נמצא"
        return res
    if SP.soc_mode(env) != "publish":
        res["reason"] = "מצב בדיקה"
        return res
    if rec.get("status") not in _PUBLISHABLE:
        res["reason"] = "הסרטון לא מאושר לפרסום"
        return res
    store = store or _store()
    tok = rec.get("video_token")

    def stop(reason, **f):   # יציאה מוקדמת — לא משאירים את השורה תקועה ב'אושר'
        res["reason"] = reason
        G["_sbdb"].video_update(vid, dict({"status": "failed", "error": reason}, **f))
        return res
    if not store.exists(tok):
        return stop("הסרטון לא זמין — צור מחדש")
    token = str(env.get("META_TOKEN") or "").strip()
    if not token:
        return stop("אין META_TOKEN")
    row = _row_by_key(G, rec.get("property_key"))
    if not row:
        return stop("הנכס לא נמצא")
    if http is None:
        import requests as http
    scfg = SP._cfg_social(G)
    if float(scfg.get("paused_until") or 0) > now:
        res["reason"] = "מושהה עד מחר (הגבלת קצב של Meta)"
        G["_sbdb"].video_update(vid, {"status": "approved", "publish_at": _iso(float(scfg["paused_until"]))})
        return res
    base = _base(env)
    vurl, curl = "%s/v2/social/vid/%s.mp4" % (base, tok), "%s/v2/social/vid/%s-cover.jpg" % (base, tok)
    # [02/11] אייל: שם הסוכן + הוואטסאפ האישי שלו גם בטקסט הריל (אינסטגרם: מספר; פייסבוק: קישור /w/)
    l9 = _agent_personal(G, row)
    agent = {"name": str(row.get("סוכן 1") or "").strip(), "phone": ("0" + l9) if l9 else ""}
    post = SP.soc_build_post(row, _office(G).get("name", ""), SP._clean_desc(G), G["_row_feats"], agent=agent)
    want = [c for c in (channels or CHANNELS) if c in CHANNELS and rec.get(c + "_status") not in ("ok", "unknown")]
    page_id = str(scfg.get("page_id") or SP.PAGE_ID_DEFAULT)
    upd, errs = {}, []
    g = SP.Graph(http, token, env)
    ig_id = None
    for c in want:
        try:
            if c.startswith("ig"):
                ig_id = ig_id or scfg.get("ig_id") or g.page_ig_id(page_id)
                if not ig_id:
                    raise SP.MetaError("אינסטגרם לא מקושר לעמוד")
                if c == "ig_story":
                    upd["ig_story_id"], _ = g.ig_video(ig_id, "STORIES", vurl, ai=bool(rec.get("ai")))
                else:
                    upd["ig_reel_id"], upd["ig_reel_permalink"] = g.ig_video(ig_id, "REELS", vurl, post["ig_caption"], curl,
                                                                             ai=bool(rec.get("ai")))
            elif c == "fb_story":
                upd["fb_story_id"] = g.fb_video_story(page_id, vurl)
            else:
                code = vid_new_link(G, rec, "fb_reel")
                desc = SP.soc_build_post(row, _office(G).get("name", ""), SP._clean_desc(G), G["_row_feats"], agent=agent,
                                         wa_link=("%s/w/%s" % (base, code)) if code else None)["body"]
                upd["fb_reel_id"], upd["fb_reel_permalink"] = g.fb_reel(page_id, vurl, desc)
            upd[c + "_status"] = res[c] = "ok"
        except SP.MetaError as e:
            upd[c + "_status"] = res[c] = "unknown" if getattr(e, "unknown", False) else "failed"
            errs.append("%s: %s" % (c, SP._scrub(str(e), [token])))
            code_ = getattr(e, "code", None)
            if code_ in (190, 102):
                SP._social_mutate(G, lambda s2: s2.__setitem__("token_bad", True))
                SP.soc_daily_alert(G, "token", "פרסום ברשתות", "החיבור לפייסבוק נותק — צריך טוקן חדש ב-Render", now)
                break
            if code_ in SP._RATE_CODES:
                SP._social_mutate(G, lambda s2: s2.__setitem__("paused_until", SP._next_midnight(now)))
                break
        except Exception as e:
            upd[c + "_status"] = res[c] = "unknown"
            errs.append("%s: %s" % (c, SP._scrub("שגיאה: %s" % e, [token])))
    merged = dict(rec, **upd)
    oks = [c for c in CHANNELS if merged.get(c + "_status") == "ok"]
    upd["status"] = res["status"] = "published" if len(oks) == len(CHANNELS) else "partial"
    if errs:
        upd["error"] = " | ".join(errs)[:900]
    G["_sbdb"].video_update(vid, upd)
    res["ok"] = bool(oks)
    res["reason"] = " · ".join(errs)
    name = rec.get("decided_by") or "אפי"
    G["_log_activity"](name, "system", "", "סרטון לרשתות — " + ("פורסם" if upd["status"] == "published" else "פורסם חלקית"),
                       "%s %d/4" % (rec.get("property_key"), len(oks)))
    return res


# ── אישור בוואטסאפ ───────────────────────────────────────────────────────────────
_CH_HE = {"fb_reel": "בריל בפייסבוק", "ig_reel": "בריל באינסטגרם", "fb_story": "בסטורי בפייסבוק",
          "ig_story": "בסטורי באינסטגרם"}


def _l9(s):
    return re.sub(r"\D", "", str(s or ""))[-9:]


def _wa(l9):
    d = re.sub(r"\D", "", str(l9 or "")).lstrip("0")
    if d.startswith("972"):
        return d
    return "972" + d if d else ""


def _agent_personal(G, row):
    """הנייד האישי של הסוכן של הנכס (בלי מספרי מרכזיה) → 9 ספרות או ''."""
    agent = str((row or {}).get("סוכן 1") or "").strip()
    if not agent:
        return ""
    try:
        virt = set(G["_agent_vphones9"]() or ())
    except Exception:
        virt = set()
    try:
        phones = G["_phones_for_name"](agent) or []
    except Exception:
        phones = []
    for p in phones:
        l9 = _l9(p)
        if len(l9) == 9 and l9.startswith("5") and l9 not in virt:
            return l9
    return ""


def _blocked_now(G, t):
    try:
        return bool(G["_shabbat_quiet_now"]()) or bool(G["_quiet_mode"]()) or SP._is_night(t)
    except Exception:
        return SP._is_night(t)


def _summary(rec):
    o = ((rec.get("texts") or {}).get("open")) or {}
    s = "סרטון סטורי + ריל מוכן — " + ", ".join(x for x in (o.get("title"), o.get("place")) if x)
    if o.get("price"):
        s += " · " + o["price"]
    return s + ("" if rec.get("ai") else " (ללא AI)")


def vid_send_review(G, rec, base, env):
    """שולח את הסרטון לאישור לאייל ולסוכן. → רשימת 9 ספרות של מי שקיבל. בשעות שקט — review_due ולא שולח."""
    try:
        quiet = bool(G["_quiet_hours"]()) or bool(G["_shabbat_quiet_now"]())
    except Exception:
        quiet = False
    if quiet:
        G["_sbdb"].video_update(rec["id"], {"review_due": True})
        return []
    who = []
    appr = _l9(env.get("SOCIAL_VIDEO_APPROVER")) or next(iter(sorted(G.get("DEV_PHONES") or [])), "")
    if appr:
        who.append(appr)
    ag = _agent_personal(G, _row_by_key(G, rec.get("property_key")))
    if ag and ag not in who:
        who.append(ag)
    vurl = "%s/v2/social/vid/%s.mp4" % (base, rec.get("video_token"))
    text = _summary(rec)
    ids = ("vid:%s:pub" % rec["id"], "vid:%s:skip" % rec["id"])
    tpl = str(env.get("WA_TPL_VIDEO") or "").strip()
    sent = []
    for l9 in who:
        to = _wa(l9)
        try:
            if G["_wa_window_open"](to):
                G["_d360_post_message"]({"messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
                                         "type": "video", "video": {"link": vurl}})
                G["_d360_post_message"]({"messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
                                         "type": "interactive", "interactive": {
                                             "type": "button", "body": {"text": text[:1000]},
                                             "action": {"buttons": [
                                                 {"type": "reply", "reply": {"id": ids[0], "title": "פרסם"}},
                                                 {"type": "reply", "reply": {"id": ids[1], "title": "דלג"}}]}}})
            elif tpl:
                G["_d360_post_message"]({"messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
                                         "type": "template", "template": {
                                             "name": tpl, "language": {"code": str(env.get("WA_TPL_LANG") or "he")},
                                             "components": [
                                                 {"type": "header", "parameters": [{"type": "video", "video": {"link": vurl}}]},
                                                 {"type": "body", "parameters": [{"type": "text", "text": text[:900]}]},
                                                 {"type": "button", "sub_type": "quick_reply", "index": "0",
                                                  "parameters": [{"type": "payload", "payload": ids[0]}]},
                                                 {"type": "button", "sub_type": "quick_reply", "index": "1",
                                                  "parameters": [{"type": "payload", "payload": ids[1]}]}]}})
            else:
                G["send_text"](to, "%s\nלצפייה ולאישור: %s/v2/social/review/%s" % (text, base, rec.get("review_token")))
            sent.append(l9)
        except Exception:
            pass
    return sent


def _spawn(fn):
    import threading
    threading.Thread(target=fn, daemon=True, name="social-video").start()


def _decide(G, rec, action, who, now, env):
    """מכונת המצבים + מעבר אטומי + הפעלת פרסום. → הודעה למי שלחץ."""
    new, msg = vid_decide(rec, action, who, now)
    if new is None:
        return msg
    if new == "approved" and not _store().exists(rec.get("video_token")):
        G["_sbdb"].video_claim(rec["id"], "pending", "failed", {"error": "הקובץ לא נמצא בשרת"})
        return "הסרטון לא זמין — צור מחדש"
    fields = {"decided_by": who, "decided_at": _iso(now)}
    if new == "approved" and _blocked_now(G, now):
        when = vid_publish_when(now, True)
        fields["publish_at"] = _iso(when)
        msg = "אושר — יעלה ב-%s" % SP._dt.datetime.fromtimestamp(when, SP._IL).strftime("%H:%M %d/%m")
    if not G["_sbdb"].video_claim(rec["id"], "pending", new, fields if new != "expired" else {}):
        cur = G["_sbdb"].video_get(rec["id"]) or {}
        if cur.get("status") == "pending":
            return "שגיאה — נסו שוב"
        return vid_decide(cur, action, who, now)[1]
    if new == "approved" and "publish_at" not in fields:
        vid = rec["id"]
        _spawn(lambda: vid_publish(G, vid, env=env))
    G["_log_activity"](who, "system", "", "סרטון לרשתות — " + {"approved": "אושר", "skipped": "דולג",
                                                                "expired": "פג"}[new], rec.get("property_key", ""))
    return msg


def vid_on_button(G, from_phone, payload, now=None, env=None):
    """לחיצה על "פרסם"/"דלג" בוואטסאפ. → הודעת התשובה (נשלחת ללוחץ), או None להתעלמות."""
    import time as _t
    m = re.fullmatch(r"vid:([A-Za-z0-9-]+):(pub|skip)", str(payload or ""))
    if not m:
        return None
    rec = G["_sbdb"].video_get(m.group(1))
    l9 = _l9(from_phone)
    if not rec or l9 not in [_l9(x) for x in (rec.get("recipients") or [])]:
        return None
    env = SP._env(env)
    now = _t.time() if now is None else now
    try:
        who = G["_display_name_for"]("", l9) or l9
    except Exception:
        who = l9
    msg = _decide(G, rec, m.group(2), who, now, env)
    try:
        G["send_text"](from_phone, msg)
    except Exception:
        pass
    return msg


def _by_review(G, tok):
    if not tok or not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", str(tok)):
        return None
    try:
        return next((r for r in (G["_sbdb"].video_recent(APPROVE_H // 24 + 3) or []) if r.get("review_token") == tok), None)
    except Exception:
        return None


_PAGE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>אישור סרטון</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;800&display=swap" rel="stylesheet">
<style>body{margin:0;background:#F2EFE7;font-family:Heebo,sans-serif;color:#1E3A5F}
.w{max-width:440px;margin:0 auto;padding:16px}.c{background:#fff;border-radius:22px;padding:16px;
box-shadow:0 6px 20px rgba(30,58,95,.06)}h1{font-size:20px;font-weight:800;margin:4px 0 12px}
video{width:100%%;border-radius:16px;background:#0E1D33}p{color:#5B6472;font-size:15px}
.b{display:flex;gap:10px;margin-top:14px}button{flex:1;min-height:48px;border-radius:14px;font:800 16px Heebo,sans-serif;cursor:pointer}
.p{background:#2E6BD6;color:#fff;border:none}.s{background:#fff;color:#1E3A5F;border:1.5px solid #DCD6C8}
#m{margin-top:12px;font-weight:800}</style></head><body><div class="w"><div class="c">
<h1>%(title)s</h1>%(body)s</div></div>
<script>function go(a){var m=document.getElementById('m');m.textContent='שולח…';
fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})})
.then(function(r){return r.text()}).then(function(t){m.textContent=t;var b=document.querySelector('.b');if(b)b.remove()})
.catch(function(){m.textContent='שגיאה — נסו שוב'})}</script></body></html>"""


def _esc(s):
    import html
    return html.escape(str(s or ""))


def vid_review_page(G, tok, now):
    """דף אישור (נפתח מקישור בוואטסאפ מחוץ לחלון 24ש'). → (קוד, html)."""
    rec = _by_review(G, tok)
    if not rec:
        return 404, _PAGE % {"title": "הקישור לא נמצא", "body": "<p>ייתכן שהסרטון נמחק.</p>"}
    st = vid_decide(rec, "pub", "", now)
    if rec.get("status") != "pending" or st[0] == "expired":
        return 200, _PAGE % {"title": "אישור סרטון", "body": "<p>%s</p>" % _esc(st[1])}
    body = ('<video controls playsinline preload="metadata" poster="/v2/social/vid/%(t)s-cover.jpg" '
            'src="/v2/social/vid/%(t)s.mp4"></video><p>%(s)s</p><div class="b">'
            '<button class="p" onclick="go(\'pub\')">פרסם</button><button class="s" onclick="go(\'skip\')">דלג</button>'
            '</div><div id="m"></div>') % {"t": _esc(rec.get("video_token")), "s": _esc(_summary(rec))}
    return 200, _PAGE % {"title": "אישור סרטון לרשתות", "body": body}


def vid_review_action(G, tok, action, now, env):
    """POST מדף האישור. → (קוד, הודעה)."""
    rec = _by_review(G, tok)
    if not rec or action not in ("pub", "skip"):
        return 404, "הקישור לא נמצא"
    return 200, _decide(G, rec, action, "קישור אישור", now, SP._env(env))


def vid_wa_redirect(G, code, env):
    """/w/<code> → (302, כתובת wa.me לנייד האישי של הסוכן עם הודעה מוכנה) או (404, '')."""
    from urllib.parse import quote
    if not code or not re.fullmatch(r"[A-Za-z0-9]{2,16}", str(code)):
        return 404, ""
    link = G["_sbdb"].link_get(code)
    if not link:
        return 404, ""
    row = _row_by_key(G, link.get("property_key")) or {}
    l9 = _agent_personal(G, row)
    to = _wa(l9) if l9 else _wa(_office(G).get("phone"))
    if not to:
        return 404, ""
    t = vid_texts(row, [], "", "", "", "")["open"] if row else {}
    what = ", ".join(x for x in (t.get("title"), t.get("place"), t.get("price")) if x)
    msg = "היי, ראיתי %s את הדירה — %s (מודעה %s). אשמח לפרטים" % (
        _CH_HE.get(link.get("channel"), "ברשתות"), what or "הנכס", link.get("property_key"))
    try:
        G["_sbdb"].link_click(code)
    except Exception:
        pass
    return 302, "https://wa.me/%s?text=%s" % (to, quote(msg))


# ── הסבב האוטומטי + תחזוקה ───────────────────────────────────────────────────────
_STORE = None


def _store():
    global _STORE
    if _STORE is None:
        _STORE = VidStore()
    return _STORE


def _recover_stale(G, recs, now):
    """שאריות של דפלוי/אתחול באמצע: רינדור תקוע → failed; אושר/בפרסום בלי התקדמות → partial (כפתור 'נסה שוב')."""
    for r in recs or []:
        st = r.get("status")
        t = SP._ts(r.get("updated_at") or r.get("decided_at") or r.get("created_at")) or now
        if now - t < STALE_S:
            continue
        if st == "rendering":
            G["_sbdb"].video_update(r["id"], {"status": "failed", "error": "נקטע באמצע (אתחול השרת)"})
            r["status"] = "failed"
        elif st == "publishing" or (st == "approved" and not r.get("publish_at")):
            G["_sbdb"].video_update(r["id"], {"status": "partial"})
            r["status"] = "partial"


def _housekeeping(G, now, env, store):
    """פג (48ש'), פרסום מתוזמן שהגיע זמנו, אישורים שחיכו לסוף השקט, ניקוי קבצים."""
    try:
        recs = G["_sbdb"].video_recent(KEEP_MAX_DAYS + 1) or []
    except Exception:
        return
    _recover_stale(G, recs, now)
    base = _base(env)
    for r in recs:
        st = r.get("status")
        if st == "pending":
            sent = SP._ts(r.get("sent_at"))
            if sent is not None and now - sent > APPROVE_H * 3600:
                G["_sbdb"].video_claim(r["id"], "pending", "expired", {})
                continue
            if r.get("review_due"):
                to = vid_send_review(G, r, base, env)
                if to:
                    G["_sbdb"].video_update(r["id"], {"review_due": False, "recipients": to})
        elif st == "approved" and r.get("publish_at"):
            t = SP._ts(r.get("publish_at"))
            if t is not None and t <= now and not _blocked_now(G, now):
                vid = r["id"]
                G["_sbdb"].video_update(vid, {"publish_at": None})
                _spawn(lambda vid=vid: vid_publish(G, vid, env=env))
    try:
        by_tok = {r.get("video_token"): r for r in recs if r.get("video_token")}
        for tok in vid_gc(store.files(), by_tok, now):
            store.remove(tok)
    except Exception:
        pass


def vid_auto_tick(G, now, env=None, store=None):
    """סבב אחד: רק SOCIAL_VIDEO_AUTO=1 + publish + META_TOKEN. נכסים חדשים (מספר מודעה שלא ראינו) → עד 3 ביום."""
    env = SP._env(env)
    if str(env.get("SOCIAL_VIDEO_AUTO") or "0").strip() != "1" or SP.soc_mode(env) != "publish" \
            or not str(env.get("META_TOKEN") or "").strip():
        return {"ran": False}
    store = store or _store()
    _housekeeping(G, now, env, store)
    rows = SP.soc_office_rows(G)
    keys = [SP._key(r.get("מספר מודעה")) for r in rows if SP._key(r.get("מספר מודעה"))]
    scfg = SP._cfg_social(G)
    gap = now - float(scfg.get("vid_last_tick") or 0)
    if not scfg.get("vid_enabled_at") or gap > 86400:
        seed = {"vid_known": {k: now for k in keys}, "vid_waiting": {}, "vid_last_tick": now,
                "vid_enabled_at": scfg.get("vid_enabled_at") or now}
        SP._social_mutate(G, lambda s: s.update(seed))
        return {"ran": True, "seeded": len(keys)}
    known = {k: v for k, v in (scfg.get("vid_known") or {}).items() if now - float(v or 0) < SP.KNOWN_TTL_DAYS * 86400}
    waiting = {k: v for k, v in (scfg.get("vid_waiting") or {}).items()
               if k in keys and now - float(v or 0) < SP.WAIT_DAYS * 86400}
    new = [k for k in keys if k not in known and k not in waiting]
    for k in new:
        waiting[k] = now
    for k in keys:
        known.setdefault(k, now)
    out = {"ran": True, "created": []}
    if len(new) > SP.FLOOD:
        for k in new:
            waiting.pop(k, None)
        SP.soc_daily_alert(G, "vid_flood", "סרטונים לרשתות", "%d נכסים חדשים בבת אחת — נראה כמו הזרמה, לא נוצרו סרטונים" % len(new), now)
        out["flood"] = True
    elif not _blocked_now(G, now) and waiting:
        try:
            hist = G["_sbdb"].video_recent(31) or []
        except Exception:
            hist = None
        if hist is not None:
            today = SP._day(now)
            left = DAILY_CAP - sum(1 for h in hist if h.get("trigger") == "auto" and SP._ts(h.get("created_at"))
                                   and SP._day(SP._ts(h.get("created_at"))) == today)
            for k in sorted(waiting, key=lambda x: -float(waiting[x])):
                if left <= 0:
                    break
                waiting.pop(k, None)
                r = vid_create_one(G, k, "auto", "", env=env, store=store)
                out["created"].append(k)
                if (r or {}).get("ok") or (r or {}).get("status") == "failed":
                    left -= 1
    SP._social_mutate(G, lambda s: s.update(vid_known=known, vid_waiting=waiting, vid_last_tick=now))
    return out


# ── Flask ────────────────────────────────────────────────────────────────────────
def register(app, G):
    import os
    import time as _t
    import threading
    from flask import jsonify, request, Response, send_file, redirect

    def dev():
        s = G["_web_auth"]()
        if not s:
            return None, (jsonify({"ok": False, "auth": False}), 401)
        if s.get("drole") != "developer":
            return None, (jsonify({"ok": False, "error": "forbidden"}), 403)
        return s, None

    def hist():
        try:
            return G["_sbdb"].video_recent(31) or []
        except Exception:
            return []

    @app.route("/v2/api/social/video", methods=["POST"])
    def vid_api_create():
        s, err = dev()
        if err:
            return err
        key = SP._key((request.get_json(silent=True) or {}).get("key"))
        if not key:
            return jsonify({"ok": False, "error": "key"}), 400
        by = s.get("phone", "")
        _spawn(lambda: vid_create_one(G, key, "manual", by))
        return jsonify({"ok": True, "queued": True})

    @app.route("/v2/api/social/videos")
    def vid_api_list():
        s, err = dev()
        if err:
            return err
        keys = [SP._key(k) for k in str(request.args.get("keys") or "").split(",") if SP._key(k)][:200]
        h = hist()
        now, hidden = _t.time(), SP.soc_hidden(G) or set()
        _recover_stale(G, h, now)
        rows = {SP._key(r.get("מספר מודעה")): r for r in SP.soc_office_rows(G)}
        items = {}
        for k in keys:
            if k not in rows:
                continue
            last = next((x for x in h if SP._key(x.get("property_key")) == k), None)
            ok, why = vid_can_create(rows[k], h, now, hidden, "manual")
            items[k] = {"last": {f: last.get(f) for f in ("id", "status", "created_at", "ai", "decided_by", "error",
                                                          "ig_story_status", "ig_reel_status", "fb_story_status",
                                                          "fb_reel_status", "ig_reel_permalink", "fb_reel_permalink",
                                                          "video_token")} if last else None,
                        "can": {"ok": ok, "reason": why}}
        return jsonify({"ok": True, "mode": SP.soc_mode(os.environ), "items": items})

    @app.route("/v2/api/social/video/retry", methods=["POST"])
    def vid_api_retry():
        s, err = dev()
        if err:
            return err
        j = request.get_json(silent=True) or {}
        rec = G["_sbdb"].video_get(str(j.get("id") or ""))
        t = SP._ts((rec or {}).get("created_at"))
        if not rec or rec.get("status") != "partial" or t is None or _t.time() - t > RETRY_DAYS * 86400:
            return jsonify({"ok": False, "error": "אין מה לנסות שוב"})
        if not G["_sbdb"].video_claim(rec["id"], "partial", "publishing", {}):
            return jsonify({"ok": False, "error": "כבר בתהליך"})
        ch = [c for c in (j.get("channels") or []) if c in CHANNELS] or None
        vid = rec["id"]
        _spawn(lambda: vid_publish(G, vid, channels=ch))
        return jsonify({"ok": True, "queued": True})

    @app.route("/v2/api/social/video/health")
    def vid_api_health():
        s, err = dev()
        if err:
            return err
        h, now = hist(), _t.time()
        m0 = _month_start(now)
        mon = [x for x in h if x.get("ai") and (SP._ts(x.get("created_at")) or 0) >= m0]
        return jsonify({"ok": True, "mode": SP.soc_mode(os.environ),
                        "auto": str(os.environ.get("SOCIAL_VIDEO_AUTO") or "0") == "1",
                        "fal": "set" if str(os.environ.get("FAL_KEY") or "").strip() else "missing",
                        "fal_bad": (SP._cfg_social(G).get("alerts") or {}).get("fal") == SP._day(now).isoformat(),
                        "model": os.environ.get("FAL_VIDEO_MODEL") or FAL_DEFAULT_MODEL,
                        "month_n": len(mon), "month_cap": MONTH_AI_CAP,
                        "month_cost": round(sum(float(x.get("ai_cost_usd") or 0) for x in mon), 2),
                        "recent": [{f: x.get(f) for f in ("id", "property_key", "status", "created_at", "ai", "decided_by",
                                                          "video_token", "error", "ig_story_status", "ig_reel_status",
                                                          "fb_story_status", "fb_reel_status")} for x in h[:6]]})

    @app.route("/v2/social/vid/<name>")
    def vid_file(name):
        m = re.fullmatch(r"([A-Za-z0-9]+)(-cover\.jpg|\.mp4)", str(name or ""))
        st = _store()
        if not m or not st.exists(m.group(1)):
            return Response("not found", status=404)
        p = st.path(m.group(1)) if m.group(2) == ".mp4" else st.cover(m.group(1))
        if not os.path.exists(p):
            return Response("not found", status=404)
        r = send_file(p, mimetype="video/mp4" if m.group(2) == ".mp4" else "image/jpeg", conditional=True)
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.route("/v2/social/review/<tok>", methods=["GET", "POST"])
    def vid_review(tok):
        if request.method == "POST":
            code, txt = vid_review_action(G, tok, str((request.get_json(silent=True) or {}).get("action") or ""),
                                          _t.time(), os.environ)
            return Response(txt, status=code, mimetype="text/plain")
        code, html = vid_review_page(G, tok, _t.time())
        return Response(html, status=code, mimetype="text/html", headers={"Cache-Control": "no-store"})

    @app.route("/w/<code>")
    def vid_wa(code):
        c, loc = vid_wa_redirect(G, code, os.environ)
        return redirect(loc, code=302) if c == 302 else Response("not found", status=404)

    thr = {"t": None, "pid": 0}
    lock = threading.Lock()

    def loop():
        _t.sleep(150)
        while True:
            try:
                vid_auto_tick(G, _t.time())
            except Exception as e:
                lg = G.get("log")
                if lg:
                    lg.error("social video auto: %s" % SP._scrub(str(e), [os.environ.get("META_TOKEN", ""),
                                                                           os.environ.get("FAL_KEY", "")]))
            _t.sleep(LOOP_SEC)

    @app.before_request
    def _video_kick():
        t = thr["t"]
        if t is not None and t.is_alive() and thr["pid"] == os.getpid():
            return
        with lock:
            t = thr["t"]
            if t is not None and t.is_alive() and thr["pid"] == os.getpid():
                return
            thr["t"] = threading.Thread(target=loop, daemon=True, name="social-video-auto")
            thr["t"].start()
            thr["pid"] = os.getpid()
