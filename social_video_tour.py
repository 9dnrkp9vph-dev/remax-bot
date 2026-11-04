"""social_video_tour.py — סגנון "סיור בדירה" לסרטוני הנכסים (אייל 04/11: "הסרטון מדהים").

6–7 תמונות בקצב מהיר, כל תמונה שלמה במסגרת (לא נחתכת ל-9:16 — תמונות יד2 קטנות ונמרחות בחיתוך),
כיתוב קצר לכל חדר, מחיר לאורך כל הסרטון וכרטיס סוכן בסוף. בלי קליפ AI (בלי עלות fal).
3 עיצובים מתחלפים בין סרטון לסרטון (tour_theme). תמונה עם סימן יד2 — חותכים אותו החוצה, ואם אי אפשר — מדלגים.
החלק העליון טהור (נבדק ב-tests/social_video/test_tour.py); הרינדור — Pillow פריים-פריים לצינור של ffmpeg.
"""
from __future__ import annotations
import re

import social_publish as SP

W, H, FPS = 1080, 1920, 30
SHOT = 1.75          # שניות לתמונה
FADE = 0.25
END = 3.0
MAX_SHOTS = 7
MIN_SHOTS = 3
THEMES = ("dark", "cream", "split")
NAVY0, NAVY1, NAVY = (14, 29, 51), (44, 76, 119), (30, 58, 95)
GOLD, WHITE, GREEN, CREAM = (228, 197, 107), (255, 255, 255), (31, 175, 94), (242, 239, 231)
RENDER_TIMEOUT_S = 240


# ── טהור ─────────────────────────────────────────────────────────────────────────
def tour_theme(n_prev):
    """עיצוב לפי מספר הסרטונים הקודמים — שני סרטונים רצופים אף פעם לא באותו עיצוב."""
    return THEMES[int(n_prev or 0) % len(THEMES)]


def tour_photo_box(w, h, wm, aspect=1.5):
    """אזור 3:2 הגדול ביותר בתמונה שלא נוגע בתיבת סימן המים (שברים 0-1) → (x0,y0,x1,y1) או None.
    בלי סימן → כל התמונה בחיתוך מרכזי ל-3:2. סימן שאי אפשר לחתוך החוצה בלי להשאיר פחות מ-55% מהרוחב → None."""
    def fit(x0, y0, x1, y1):
        bw, bh = x1 - x0, y1 - y0
        if bw <= 0 or bh <= 0:
            return None
        if bw / bh > aspect:
            cw, ch = bh * aspect, bh
        else:
            cw, ch = bw, bw / aspect
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return (int(round(cx - cw / 2)), int(round(cy - ch / 2)), int(round(cx + cw / 2)), int(round(cy + ch / 2)))
    if not wm:
        return fit(0, 0, w, h)
    a, b, c, d = wm[0] * w, wm[1] * h, wm[2] * w, wm[3] * h
    pad = 0.02 * max(w, h)
    cands = [fit(0, 0, max(0, a - pad), h), fit(min(w, c + pad), 0, w, h),
             fit(0, 0, w, max(0, b - pad)), fit(0, min(h, d + pad), w, h)]
    best = max((x for x in cands if x), key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), default=None)
    if not best or (best[2] - best[0]) < 0.55 * min(w, h * aspect):
        return None
    return best


def _he_ok(s, maxw=5):
    s = SP.soc_scrub_phones(str(s or "")).strip(" ·-,.\"'")
    if not s or len(s.split()) > maxw or len(s) > 32 or not re.search(r"[֐-׿]", s):
        return ""
    if re.search(r"\d{3,}|https?:|www\.", s):
        return ""
    return s


def tour_plan(texts, order, captions, feats):
    """→ רשימת שקפים [{'i': אינדקס תמונה, 'title', 'sub'}] (עד MAX_SHOTS).
    השקף הראשון — הכותרת של הנכס (מה + איפה); אחר כך כיתוב החדר מ-Claude, ובהיעדרו מאפיין מהמודעה."""
    o = (texts or {}).get("open") or {}
    spec = ((texts or {}).get("s2") or {}).get("main") or ""
    pool = [f for f in (feats or []) if f]
    shots = []
    for k, i in enumerate(order[:MAX_SHOTS]):
        cap = _he_ok((captions or {}).get(i))
        if k == 0:
            shots.append({"i": i, "title": cap or o.get("title") or "", "sub": o.get("place") or ""})
            continue
        if not cap and pool:
            cap = pool.pop(0)
        sub = spec if k == 1 else ""
        shots.append({"i": i, "title": cap, "sub": sub})
    return shots


def tour_phone(p):
    """0529125049 / +972-52-9125049 → 052-912-5049 (קווי: 04-600-0800); אחרת כמו שהוא."""
    d = re.sub(r"\D", "", str(p or ""))
    if d.startswith("972"):
        d = "0" + d[3:]
    if len(d) == 10 and d.startswith("0"):
        return "%s-%s-%s" % (d[:3], d[3:6], d[6:])
    if len(d) == 9 and d.startswith("0"):
        return "%s-%s-%s" % (d[:2], d[2:5], d[5:])
    return str(p or "").strip()


def tour_duration(n_shots):
    return round(n_shots * SHOT + END, 2)


# ── בחירת תמונות + כיתובים (Claude vision) ───────────────────────────────────────
_TOUR_PROMPT = """These are photos of one apartment for sale (numbered from 0). Plan a short vertical "apartment tour" reel.
Return ONLY a JSON object, no prose:
{"order": [<up to 7 indexes in tour order: the single most impressive shot first (view / bright living room / facade),
            then living room, kitchen, dining, balcony, master bedroom, bathroom; different rooms, no near-duplicates>],
 "captions": {"<index>": "<2-4 Hebrew words naming what is shown, using ONLY facts from the description when describing
              quality (e.g. 'מטבח משודרג' only if the description says so; otherwise just 'המטבח')>"},
 "wm": {"<index>": [x0, y0, x1, y1] or null},
 "skip": [<indexes with people, floor plans, maps, text-only images or 'photos coming soon' placeholders>]}
"wm" = box of any "Yad2" / "יד2" watermark: semi-transparent white or grey text or logo that can appear ANYWHERE
(corners, centre, bottom). Look carefully, it is often faint. Fractions 0-1 of width/height. The office's own
"RE/MAX" logo is NOT a watermark to report.
Description: """


def tour_pick(http, api_key, images, desc, model):
    """→ {'order','captions','wm','skip'}; כל כשל → סדר יד2, בלי כיתובים, סימן ברירת מחדל בפינה."""
    import base64, json, io
    from PIL import Image
    n = len(images or [])
    wm_def = (0.02, 0.02, 0.18, 0.14)
    fb = {"order": list(range(min(n, MAX_SHOTS))), "captions": {}, "wm": {i: wm_def for i in range(n)}, "skip": []}
    if not http or not api_key or n < 2:
        return fb
    try:
        content = []
        for i, data in enumerate(images[:10]):
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((768, 768))
            b = io.BytesIO()
            im.save(b, "JPEG", quality=82)
            content.append({"type": "text", "text": "Photo %d:" % i})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(b.getvalue()).decode()}})
        content.append({"type": "text", "text": _TOUR_PROMPT + str(desc or "")[:1500]})
        r = http.post("https://api.anthropic.com/v1/messages",
                      headers={"anthropic-version": "2023-06-01", "x-api-key": api_key, "content-type": "application/json"},
                      json={"model": model, "max_tokens": 900, "messages": [{"role": "user", "content": content}]},
                      timeout=120)
        if getattr(r, "status_code", 200) >= 400:
            return fb
        text = "".join(c.get("text", "") for c in (r.json() or {}).get("content") or [])
        m = re.search(r"\{.*\}", text, re.S)
        j = json.loads(m.group()) if m else None
        if not isinstance(j, dict):
            return fb
        m_ = min(n, 10)
        skip = [i for i in (j.get("skip") or []) if isinstance(i, int) and 0 <= i < m_]
        order = []
        for i in j.get("order") or []:
            if isinstance(i, int) and 0 <= i < m_ and i not in skip and i not in order:
                order.append(i)
        if len(order) < 2:
            return fb
        caps = {}
        for k, v in (j.get("captions") or {}).items() if isinstance(j.get("captions"), dict) else ():
            try:
                i = int(k)
            except (TypeError, ValueError):
                continue
            c = _he_ok(v, 4)
            if c and 0 <= i < m_:
                caps[i] = c
        wm = {}
        has = isinstance(j.get("wm"), dict)   # Claude ענה על סימנים — מה שלא ברשימה נקי; לא ענה → ברירת מחדל
        raw = j.get("wm") if has else {}
        for i in range(n):
            v = raw.get(str(i)) if has else wm_def
            ok = isinstance(v, (list, tuple)) and len(v) == 4 and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in v)
            wm[i] = tuple(float(x) for x in v) if ok else None
        return {"order": order[:MAX_SHOTS], "captions": caps, "wm": wm, "skip": skip}
    except Exception:
        return fb


def tour_slides(images, pick):
    """תמונות לפי הסדר, אחרי חיתוך סימן המים → [(jpeg_bytes, אינדקס)]. תמונה שאי אפשר לנקות — מדלגים;
    משלימים מהשאר (באותו כלל) עד MAX_SHOTS."""
    import io
    from PIL import Image
    out, used = [], set()
    rest = [i for i in range(len(images)) if i not in pick["order"] and i not in pick["skip"]]
    for i in list(pick["order"]) + rest:
        if len(out) >= MAX_SHOTS or i in used:
            continue
        used.add(i)
        try:
            im = Image.open(io.BytesIO(images[i])).convert("RGB")
        except Exception:
            continue
        box = tour_photo_box(im.width, im.height, pick["wm"].get(i))
        if not box:
            continue
        b = io.BytesIO()
        im.crop(box).save(b, "JPEG", quality=94)
        out.append((b.getvalue(), i))
    return out


# ── רינדור ───────────────────────────────────────────────────────────────────────
def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _cover(im, w, h):
    from PIL import Image
    import math
    r = max(w / im.width, h / im.height)
    im = im.resize((math.ceil(im.width * r), math.ceil(im.height * r)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _rounded(im, rad):
    from PIL import Image, ImageDraw
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), rad, fill=255)
    out = im.convert("RGBA")
    out.putalpha(m)
    return out


class _Painter:
    def __init__(self, theme, shots, photos, texts, logo_path, agent_photo):
        import social_video as V
        from PIL import Image, ImageDraw, ImageFilter
        self.V, self.theme, self.shots, self.texts = V, theme, shots, texts
        self.Image, self.ImageDraw = Image, ImageDraw
        dark = theme != "cream"
        self.fg = WHITE if dark else NAVY
        self.fg2 = (225, 230, 238) if dark else (91, 100, 114)
        self.price_fg, self.price_bg = NAVY0, GOLD
        lg = Image.open(logo_path).convert("RGBA") if logo_path else None
        self.logo = None
        if lg:
            lg = lg.resize((max(1, int(lg.width * 64 / lg.height)), 64), Image.LANCZOS)
            card = Image.new("RGBA", (lg.width + 56, lg.height + 32), (0, 0, 0, 0))
            ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 18, fill=(255, 255, 255, 245))
            card.alpha_composite(lg, (28, 16))
            self.logo = card
        self.agent_photo = None
        if agent_photo:
            try:
                # 256 = גודל התמונה שנשמרת באזור האישי — בלי הגדלה (חדות)
                ap = _cover(Image.open(agent_photo).convert("RGB"), 256, 256)
                m = Image.new("L", (256, 256), 0)
                ImageDraw.Draw(m).ellipse((0, 0, 255, 255), fill=255)
                ap = ap.convert("RGBA")
                ap.putalpha(m)
                self.agent_photo = ap
            except Exception:
                self.agent_photo = None
        if theme == "split":
            self.FW, self.FH, self.FY = W, int(W * 2 / 3), 300
        else:
            self.FW = 1040
            self.FH = int(self.FW * 2 / 3)
            self.FY = (H - self.FH) // 2 + 40
        self.prep = []
        for s in shots:
            im = Image.open(__import__("io").BytesIO(photos[s["i"]])).convert("RGB")
            if theme == "dark":
                bg = _cover(im, W // 4, H // 4).filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
                bg = Image.blend(bg, Image.new("RGB", (W, H), NAVY0), 0.55)
            elif theme == "cream":
                bg = Image.new("RGB", (W, H), CREAM)
            else:
                bg = self._grad()
            self.prep.append((im, bg))
        self.end_bg = self._grad() if theme != "cream" else Image.new("RGB", (W, H), CREAM)

    def _grad(self):
        g = self.Image.new("RGB", (1, 256))
        for y in range(256):
            k = y / 255
            g.putpixel((0, y), tuple(int(NAVY0[c] + (NAVY1[c] - NAVY0[c]) * k) for c in range(3)))
        return g.resize((W, H), self.Image.BILINEAR)

    def _text(self, d, x, y, s, size, weight, fill, anchor="ma"):
        if not s:
            return
        V = self.V
        f = V._fit(d, s, size, weight, W - 120)
        d.text((x, y), V._rtl(s), font=f, fill=fill, anchor=anchor)

    def _pill(self, L, cx, y, s, size, fg, bg, padx=34):
        d = self.ImageDraw.Draw(L)
        V = self.V
        f = V._font(size, 800)
        tw = d.textlength(V._rtl(s), font=f)
        h = int(size * 1.9)
        d.rounded_rectangle((int(cx - tw / 2 - padx), y, int(cx + tw / 2 + padx), y + h), h // 2, fill=bg)
        d.text((cx, y + h // 2), V._rtl(s), font=f, fill=fg, anchor="mm")

    def shot(self, k, t):
        Image, ImageDraw = self.Image, self.ImageDraw
        im, bg = self.prep[k]
        s = self.shots[k]
        FW, FH, FY = self.FW, self.FH, self.FY
        fr = bg.convert("RGBA")
        z = 1.0 + 0.07 * (t / SHOT)
        pan = (0.5 - t / SHOT) * 0.06 if k % 2 else 0.0
        big = _cover(im, int(FW * z), int(FH * z))
        ox = int((big.width - FW) * (0.5 + pan))
        oy = (big.height - FH) // 2
        ph = big.crop((ox, oy, ox + FW, oy + FH))
        if self.theme == "split":
            fr.paste(ph, (0, FY))
        else:
            if self.theme == "cream":
                card = Image.new("RGBA", (FW + 24, FH + 24), (0, 0, 0, 0))
                ImageDraw.Draw(card).rounded_rectangle((0, 0, FW + 23, FH + 23), 34, fill=(255, 255, 255, 255))
                fr.alpha_composite(card, ((W - FW) // 2 - 12, FY - 12))
            fr.alpha_composite(_rounded(ph, 28), ((W - FW) // 2, FY))
        d = ImageDraw.Draw(fr)
        if self.logo:
            fr.alpha_composite(self.logo, ((W - self.logo.width) // 2, 150))
        a = _ease(t / 0.45)
        al = int(255 * a)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        price = ((self.texts.get("open") or {}).get("price")) or ""
        agent = ((self.texts.get("end") or {}).get("agent")) or ""
        if self.theme == "split":
            yb = FY + FH + 110 + int((1 - a) * 40)
            self._text(dl, W // 2, yb, s["title"], 92, 800, WHITE + (al,))
            self._text(dl, W // 2, yb + 120, s["sub"], 46, 500, (225, 230, 238, al))
            if price:
                self._pill(lay, W // 2, H - 420, price + ("  ·  " + agent if agent and k else ""), 46 if k else 64,
                           NAVY0 + (255,), GOLD + (240,))
        else:
            yb = FY - 230 + int((1 - a) * 40)
            self._text(dl, W // 2, yb, s["title"], 84, 800, self.fg + (al,))
            self._text(dl, W // 2, yb + 110, s["sub"], 44, 500, self.fg2 + (al,))
            if price and k == 0:
                b = _ease((t - 0.25) / 0.45)
                self._pill(lay, W // 2, FY + FH + 90 + int((1 - b) * 30), price, 70,
                           NAVY0 + (int(255 * b),), GOLD + (int(255 * b),))
            elif price:
                self._pill(lay, W // 2, FY + FH + 100, price + ("  ·  " + agent if agent else ""), 40,
                           NAVY0 + (255,), GOLD + (235,))
        fr.alpha_composite(lay)
        p = (k * SHOT + t) / (len(self.shots) * SHOT)
        bar = GOLD if self.theme != "cream" else NAVY
        d.rounded_rectangle((60, 96, 60 + max(8, int((W - 120) * p)), 104), 4, fill=bar + (230,))
        return fr.convert("RGB")

    def end(self, t):
        Image, ImageDraw = self.Image, self.ImageDraw
        e, o = self.texts.get("end") or {}, self.texts.get("open") or {}
        fr = self.end_bg.convert("RGBA")
        if self.logo:
            fr.alpha_composite(self.logo, ((W - self.logo.width) // 2, 220))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        al = int(255 * _ease(t / 0.5))
        cy = 640
        d.ellipse((W // 2 - 142, cy - 142, W // 2 + 142, cy + 142), fill=GOLD + (al,))
        if self.agent_photo:
            ap = self.agent_photo.copy()
            ap.putalpha(Image.eval(ap.getchannel("A"), lambda v: v * al // 255))
            lay.alpha_composite(ap, (W // 2 - 128, cy - 128))
        else:
            d.ellipse((W // 2 - 128, cy - 128, W // 2 + 128, cy + 128), fill=NAVY + (al,))
            if e.get("agent"):
                d.text((W // 2, cy), self.V._rtl(e["agent"][0]), font=self.V._font(140, 800), fill=WHITE + (al,), anchor="mm")
        self._text(d, W // 2, cy + 200, e.get("agent"), 80, 800, self.fg + (al,))
        self._text(d, W // 2, cy + 310, e.get("recap"), 46, 600, self.fg2 + (al,))
        if o.get("place"):
            self._text(d, W // 2, cy + 380, o["place"], 40, 500, self.fg2 + (al,))
        if o.get("price"):
            self._pill(lay, W // 2, cy + 480, o["price"], 72, NAVY0 + (al,), GOLD + (al,))
        if e.get("phone"):
            b = int(255 * _ease((t - 0.35) / 0.5))
            import math
            size = int(50 * (1 + 0.03 * math.sin(t * 6)))
            self._pill(lay, W // 2, cy + 700, (e.get("cta") or "חייגו") + "  " + tour_phone(e["phone"]), size,
                       WHITE + (b,), GREEN + (b,), padx=46)
        fr.alpha_composite(lay)
        return fr.convert("RGB")


def vid_compose_tour(photos, shots, texts, theme, music_path, out_path, logo_path, agent_photo=None, popen=None):
    """photos = [jpeg bytes] (אחרי ניקוי סימן מים), shots = tour_plan(...) → MP4 9:16 + כיסוי.
    → {'ok', 'duration', 'cover', 'error'} (אותו חוזה של social_video.vid_compose)."""
    import subprocess, time
    import social_video as V
    from PIL import Image
    ff = V.vid_ffmpeg()
    if not ff:
        return {"ok": False, "error": "אין ffmpeg"}
    if len(shots) < 2:
        return {"ok": False, "error": "פחות מ-2 תמונות נקיות"}
    popen = popen or subprocess.Popen
    total = tour_duration(len(shots))
    try:
        P = _Painter(theme, shots, photos, texts, logo_path, agent_photo)
        if music_path:
            ain = ["-i", music_path]
        else:
            ain = ["-f", "lavfi", "-t", "%.2f" % total, "-i", "anullsrc=r=48000:cl=stereo"]
        cmd = [ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
               "-r", str(FPS), "-i", "-"] + ain + [
               "-filter_complex", "[1:a]atrim=0:%.2f,asetpts=PTS-STARTPTS,volume=0.35,afade=in:d=0.5,"
               "afade=out:st=%.2f:d=1.2,aresample=48000[a]" % (total, max(0, total - 1.2)),
               "-map", "0:v", "-map", "[a]", "-t", "%.2f" % total,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-g", "60",
               "-c:a", "aac", "-ar", "48000", "-b:a", "128k", "-movflags", "+faststart", "-threads", "1", out_path]
        proc = popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        t0, n = time.time(), int(round(total * FPS))
        cover_frame = None
        try:
            for f in range(n):
                if time.time() - t0 > RENDER_TIMEOUT_S:
                    proc.kill()
                    return {"ok": False, "error": "timeout"}
                t = f / FPS
                k = int(t // SHOT)
                if k < len(shots):
                    lt = t - k * SHOT
                    img = P.shot(k, lt)
                    if lt > SHOT - FADE:
                        nxt = P.shot(k + 1, 0) if k + 1 < len(shots) else P.end(0)
                        img = Image.blend(img, nxt, (lt - (SHOT - FADE)) / FADE)
                else:
                    img = P.end(t - len(shots) * SHOT)
                if f == int(0.8 * FPS):
                    cover_frame = img
                proc.stdin.write(img.tobytes())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.stderr.read() if proc.stderr else b""
        if proc.wait(timeout=60) != 0:
            return {"ok": False, "error": "ffmpeg: %s" % (err or b"")[-300:].decode("utf-8", "replace")}
        cover = out_path.rsplit(".", 1)[0] + "-cover.jpg"
        (cover_frame or P.shot(0, SHOT / 2)).save(cover, quality=88)
        return {"ok": True, "duration": total, "cover": cover}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
