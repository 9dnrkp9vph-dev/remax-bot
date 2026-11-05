"""social_sold.py — סטורי SOLD (אייל 05/11): סרטון קצר של 8 שניות עם מוזיקה, לסטורי באינסטגרם ובפייסבוק בלבד.

שני מסלולים:
  • מוכר / מוכר+קונה — מכרטיס נכס ב"הנכסים שלי" (תמונת הנכס, כתובת, סוכן 1 + סוכן 2).
  • קונה — מכרטיס עסקה סגורה ב"תהליכים ועסקאות" (בלי תמונת נכס — עיצוב חגיגי עם מפתח וקונפטי).
זרימה: לחיצה → רינדור (≈חצי דקה) → צפייה → "פרסם לסטורי" (אינסטגרם + פייסבוק). בלי אישור בוואטסאפ — מי שלחץ מאשר.
הרשומות בקובץ JSON בדיסק הקבוע (sold_stories.json) — בלי טבלה חדשה; הסרטון עצמו בתיקיית הסרטונים (VidStore).
"""
from __future__ import annotations
import json
import logging
import math
import os
import random
import re
import threading

import social_publish as SP

_log = logging.getLogger("social_sold")

W, H, FPS = 1080, 1920, 30
DUR = 8.0
SIDES = ("seller", "both", "buyer")
SIDE_LINE = {"seller": "נמכר בהצלחה", "both": "ייצגנו את המוכר וגם את הקונה"}
SLOGAN = "מוכרים הכי הרבה דירות בקריות"
CHANNELS = ("ig_story", "fb_story")
KEEP = 200
NAVY0, NAVY1, NAVY = (14, 29, 51), (44, 76, 119), (30, 58, 95)
GOLD, WHITE, GREEN, RED = (228, 197, 107), (255, 255, 255), (31, 175, 94), (200, 38, 44)
MUTE, GRAY = (176, 192, 214), (91, 100, 114)
CITIES = ("קרית ביאליק", "קרית מוצקין", "קרית אתא", "קרית ים", "קרית חיים", "קרית שמואל", "חיפה", "נשר", "טירת כרמל",
          "עכו", "נהריה", "כפר ביאליק", "רכסים", "כפר חסידים")


# ── טקסטים (טהור) ─────────────────────────────────────────────────────────────────
def sold_city(text):
    """עיר מתוך טקסט חופשי של עסקה ('קרית ביאליק', 'ק. מוצקין', 'קריית אתא') → '' אם לא נמצאה."""
    t = re.sub(r"\bק['.׳]?\s*(?=ביאליק|מוצקין|אתא|ים|חיים|שמואל)", "קרית ", str(text or ""))
    t = t.replace("קריית", "קרית")
    return next((c for c in CITIES if c in t), "")


def sold_agents_for_deal(deal):
    """הסוכנים שייצגו את הקונה בעסקה (side1/side2 מכילים 'קונה'); אף צד לא מסומן → כל הסוכנים."""
    ags = [str(a).strip() for a in (deal.get("agents") or []) if str(a).strip()]
    sides = [str(deal.get("side1") or ""), str(deal.get("side2") or "")]
    buy = [a for k, a in enumerate(ags) if k < 2 and "קונה" in sides[k]]
    return (buy or ags)[:2]


def sold_deal_ok(deal):
    """עסקה סגורה שייצגנו בה קונה (או שלא סומן צד) — רק אז יש כפתור סטורי קונה."""
    if not deal.get("deal"):
        return False
    sides = (str(deal.get("side1") or "") + " " + str(deal.get("side2") or "")).strip()
    return not sides or "קונה" in sides


def sold_texts_property(row, side):
    addr, num = SP._norm(row.get("כתובת")), SP._norm(row.get("מספר בית"))
    if num and not re.search(r"\b%s\b" % re.escape(num), addr):   # בגיליון הרחוב ומספר הבית בעמודות נפרדות
        addr = (addr + " " + num).strip()
    city = SP._norm(row.get("עיר / ישוב"))
    return {"kind": "seller", "addr": addr or city, "city": city if addr else "", "tag": SIDE_LINE[side],
            "slogan": SLOGAN}


def sold_texts_deal(deal):
    city = sold_city(deal.get("notes"))
    return {"kind": "buyer", "line": ("דירה ב" + city) if city else "רימקס פמילי · הקריות", "slogan": SLOGAN}


def sold_phone(p):
    import social_video_tour as T
    return T.tour_phone(p) if p else ""


# ── רינדור ───────────────────────────────────────────────────────────────────────
def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _back(t):
    """כניסה עם קפיצה קטנה (overshoot) — לחותמת ה-SOLD."""
    t = max(0.0, min(1.0, t))
    c = 1.7
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def _fade(im, a):
    """RGBA עם שקיפות מוכפלת ב-a (0..1)."""
    if a >= 1:
        return im
    out = im.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return out


class _Sprites:
    def __init__(self, kind, photo, texts, agents, logo_path):
        import social_video as V
        from PIL import Image, ImageDraw, ImageFilter
        self.V, self.Image, self.ImageDraw, self.ImageFilter = V, Image, ImageDraw, ImageFilter
        self.kind, self.texts = kind, texts
        self.bg = self._grad()
        self.logo = self._logo(logo_path)
        self.agents = self._agents(agents)
        if kind == "buyer":
            self._buyer_prep()
        else:
            self._seller_prep(photo)

    # עזרים
    def _grad(self):
        g = self.Image.new("RGB", (1, 256))
        for y in range(256):
            k = y / 255
            g.putpixel((0, y), tuple(int(NAVY0[c] + (NAVY1[c] - NAVY0[c]) * k) for c in range(3)))
        return g.resize((W, H), self.Image.BILINEAR)

    def _layer(self, w, h):
        return self.Image.new("RGBA", (w, h), (0, 0, 0, 0))

    def _text_sprite(self, s, size, weight, fill, maxw=W - 140):
        V = self.V
        L = self._layer(W, int(size * 1.6))
        d = self.ImageDraw.Draw(L)
        d.text((W // 2, L.height // 2), V._rtl(s), font=V._fit(d, s, size, weight, maxw), fill=fill, anchor="mm")
        return L

    def _pill_sprite(self, s, size, fg, bg, h):
        V = self.V
        L = self._layer(W, h)
        d = self.ImageDraw.Draw(L)
        f = V._font(size, 800)
        tw = d.textlength(V._rtl(s), font=f)
        d.rounded_rectangle((W / 2 - tw / 2 - 40, 0, W / 2 + tw / 2 + 40, h - 1), h // 2, fill=bg)
        d.text((W // 2, h // 2), V._rtl(s), font=f, fill=fg, anchor="mm")
        return L

    def _logo(self, path):
        Image, ImageDraw = self.Image, self.ImageDraw
        try:
            lg = Image.open(path).convert("RGBA")
        except Exception:
            return None
        h = 120
        lg = lg.resize((max(1, int(lg.width * (h - 36) / lg.height)), h - 36), Image.LANCZOS)
        c = self._layer(lg.width + 64, h)
        ImageDraw.Draw(c).rounded_rectangle((0, 0, c.width - 1, h - 1), 22, fill=(255, 255, 255, 250))
        c.alpha_composite(lg, (32, 18))
        return c

    def _avatar(self, name, size, photo):
        import social_video_tour as T
        Image, ImageDraw = self.Image, self.ImageDraw
        ring = max(6, size // 17)
        out = self._layer(size, size)
        ImageDraw.Draw(out).ellipse((0, 0, size - 1, size - 1), fill=GOLD)
        inner = size - 2 * ring
        a = None
        if photo:
            try:
                a = T._cover(Image.open(photo).convert("RGB"), inner, inner)
            except Exception:
                a = None
        if a is None:
            a = Image.new("RGB", (inner, inner), NAVY)
            ImageDraw.Draw(a).text((inner // 2, inner // 2), self.V._rtl((name or " ")[0]),
                                   font=self.V._font(int(inner * .45), 800), fill=WHITE, anchor="mm")
        m = Image.new("L", (inner, inner), 0)
        ImageDraw.Draw(m).ellipse((0, 0, inner - 1, inner - 1), fill=255)
        out.paste(a, (ring, ring), m)
        return out

    def _shadowed(self, card, rad, blur=26, alpha=110, pad=50):
        L = self._layer(card.width + 2 * pad, card.height + 2 * pad)
        s = self._layer(L.width, L.height)
        self.ImageDraw.Draw(s).rounded_rectangle((pad, pad + 12, pad + card.width, pad + card.height + 12), rad,
                                                 fill=(0, 0, 0, alpha))
        L.alpha_composite(s.filter(self.ImageFilter.GaussianBlur(blur)))
        L.alpha_composite(card, (pad, pad))
        return L

    def _agents(self, agents):
        """כרטיס הסוכן/ים (לבן, תמונה בטבעת זהב, שם, טלפון בירוק) → RGBA ברוחב המסך."""
        V, ImageDraw = self.V, self.ImageDraw
        agents = [a for a in (agents or []) if a.get("name")][:2]
        if not agents:
            return None
        if len(agents) == 1:
            a = agents[0]
            # [05/11 אייל] "תן יותר מקום לסוכנים" — כרטיס גדול: תמונה 250, שם 76, טלפון 52
            bw, bh = 960, 300
            card = self._layer(bw, bh)
            d = ImageDraw.Draw(card)
            d.rounded_rectangle((0, 0, bw - 1, bh - 1), 44, fill=WHITE)
            card.alpha_composite(self._avatar(a["name"], 250, a.get("photo")), (bw - 275, 25))
            rx = bw - 305
            d.text((rx, 82), V._rtl(a["name"]), font=V._fit(d, a["name"], 76, 800, rx - 30), fill=NAVY, anchor="rm")
            d.text((rx, 150), V._rtl("רימקס פמילי"), font=V._font(40, 500), fill=GRAY, anchor="rm")
            if a.get("phone"):
                f = V._font(52, 800)
                tw = d.textlength(a["phone"], font=f)
                d.rounded_rectangle((rx - tw - 70, 196, rx, 266), 35, fill=GREEN)
                d.text((rx - 35 - tw / 2, 231), a["phone"], font=f, fill=WHITE, anchor="mm")
            cards = [card]
        else:
            bw, bh = 500, 470
            cards = []
            for a in agents:
                card = self._layer(bw, bh)
                d = ImageDraw.Draw(card)
                d.rounded_rectangle((0, 0, bw - 1, bh - 1), 44, fill=WHITE)
                card.alpha_composite(self._avatar(a["name"], 220, a.get("photo")), (bw // 2 - 110, 24))
                d.text((bw // 2, 296), V._rtl(a["name"]), font=V._fit(d, a["name"], 62, 800, bw - 40), fill=NAVY,
                       anchor="mm")
                if a.get("phone"):
                    f = V._font(46, 800)
                    tw = d.textlength(a["phone"], font=f)
                    d.rounded_rectangle((bw / 2 - tw / 2 - 32, 352, bw / 2 + tw / 2 + 32, 418), 33, fill=GREEN)
                    d.text((bw // 2, 385), a["phone"], font=f, fill=WHITE, anchor="mm")
                cards.append(card)
        sh = [self._shadowed(c, 40) for c in cards]
        gap = 20 - 100   # הצל מוסיף 50 מכל צד
        tw = sum(s.width for s in sh) + gap * (len(sh) - 1)
        L = self._layer(W, max(s.height for s in sh))
        x = (W - tw) // 2
        for s in sh:
            L.alpha_composite(s, (x, 0))
            x += s.width + gap
        return L

    # מוכר
    def _seller_prep(self, photo):
        import io
        Image, ImageDraw = self.Image, self.ImageDraw
        self.PH = 960   # [05/11] תמונה קצרה יותר — יותר מקום לכרטיס הסוכן
        src = Image.open(io.BytesIO(photo)).convert("RGB")
        # [04/11 קובי] סימני מים בפינות (יד2 / RE/MAX) — חותכים שוליים מכל צד, רצועה תחתונה רחבה יותר
        src = src.crop((int(src.width * .08), int(src.height * .1), int(src.width * .92), int(src.height * .86)))
        import social_video_tour as T
        self.photo = T._cover(src, int(W * 1.16), int(self.PH * 1.16))
        fade = self._layer(W, 420)
        dd = ImageDraw.Draw(fade)
        for y in range(420):
            dd.line((0, y, W, y), fill=NAVY0 + (int(255 * (y / 419) ** 1.6),))
        top = self._layer(W, 260)
        dt = ImageDraw.Draw(top)
        for y in range(260):
            dt.line((0, y, W, y), fill=(0, 0, 0, int(120 * (1 - y / 259))))
        self.fade, self.top = fade, top
        self.ribbon = self._ribbon()
        tx = self.texts
        self.tag = self._pill_sprite(tx.get("tag") or "", 40, (35, 23, 0), GOLD, 84)
        self.addr = self._text_sprite(tx.get("addr") or "", 92, 800, WHITE)
        self.city = self._text_sprite(tx.get("city") or "", 50, 500, MUTE) if tx.get("city") else None
        self.slogan = self._text_sprite(tx.get("slogan") or "", 44, 700, GOLD)

    def _ribbon(self):
        V, Image, ImageDraw, ImageFilter = self.V, self.Image, self.ImageDraw, self.ImageFilter
        band = self._layer(W + 600, 170)
        d = ImageDraw.Draw(band)
        d.rectangle((0, 0, band.width, 170), fill=RED + (255,))
        d.rectangle((0, 10, band.width, 14), fill=WHITE + (230,))
        d.rectangle((0, 156, band.width, 160), fill=WHITE + (230,))
        d.text((band.width // 2, 86), "SOLD", font=V._font(118, 900), fill=WHITE, anchor="mm")
        sh = self._layer(band.width, band.height)
        ImageDraw.Draw(sh).rectangle((0, 0, band.width, 170), fill=(0, 0, 0, 120))
        L = self._layer(band.width + 80, band.height + 80)
        L.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)), (48, 58))
        L.alpha_composite(band, (40, 40))
        return L.rotate(-12, expand=True, resample=Image.BICUBIC)

    def seller(self, t):
        Image = self.Image
        fr = self.bg.convert("RGBA")
        z = 1.16 - 0.10 * _ease(t / DUR)   # התקרבות איטית לאורך כל הסרטון
        pw, ph = int(W * z), int(self.PH * z)
        im = self.photo.resize((pw, ph), Image.BILINEAR)
        ox, oy = (pw - W) // 2, (ph - self.PH) // 2
        fr.paste(im.crop((ox, oy, ox + W, oy + self.PH)), (0, 0))
        fr.alpha_composite(self.fade, (0, self.PH - 420))
        fr.alpha_composite(self.top, (0, 0))
        if self.logo:
            fr.alpha_composite(_fade(self.logo, _ease(t / 0.5)), ((W - self.logo.width) // 2, 70))
        # חותמת SOLD: נכנסת גדולה ונוחתת עם קפיצה
        a = (t - 0.35) / 0.55
        if a > 0:
            s = 1.0 + 0.9 * (1 - _back(a))
            rb = self.ribbon
            if abs(s - 1.0) > 0.003:
                rb = rb.resize((max(1, int(rb.width * s)), max(1, int(rb.height * s))), Image.BILINEAR)
            rb = _fade(rb, min(1.0, a * 2.2))
            fr.alpha_composite(rb, ((W - rb.width) // 2, 520 - rb.height // 2))
        y = self.PH - 40

        def up(sp, yc, t0, d=0.5):
            b = _ease((t - t0) / d)
            if b > 0 and sp is not None:
                fr.alpha_composite(_fade(sp, b), (0, int(yc - sp.height / 2 + (1 - b) * 46)))
        up(self.tag, y, 1.05)
        up(self.addr, y + 125, 1.25)
        up(self.city, y + 215, 1.45)
        b = _ease((t - 1.65) / 0.5)
        if b > 0:
            w = int(140 * b)
            self.ImageDraw.Draw(fr).line((W // 2 - w // 2, y + 272, W // 2 + w // 2, y + 272), fill=GOLD, width=4)
        up(self.slogan, y + 322, 1.8)
        self._agent_in(fr, t, 2.2, self._agent_cy())
        return fr.convert("RGB")

    def _agent_cy(self):
        """מרכז כרטיס הסוכן: אחד — נמוך; צוות (כרטיסים גבוהים) — מעט גבוה יותר."""
        return H - 250 if self.agents is None or self.agents.height < 500 else H - 300

    def _agent_in(self, fr, t, t0, cy):
        if self.agents is None:
            return
        b = _ease((t - t0) / 0.6)
        if b > 0:
            A = self.agents
            fr.alpha_composite(_fade(A, b), (0, int(cy - A.height / 2 + (1 - b) * 140)))

    # קונה
    def _buyer_prep(self):
        Image, ImageDraw, ImageFilter = self.Image, self.ImageDraw, self.ImageFilter
        glow = self._layer(W, H)
        ImageDraw.Draw(glow).ellipse((W // 2 - 360, 250, W // 2 + 360, 950), fill=GOLD + (60,))
        bg = self.bg.convert("RGBA")
        bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
        self.bgb = bg
        self.key = self._key(290)
        rnd = random.Random(7)
        self.conf = []
        for _ in range(64):
            c = rnd.choice([GOLD, GOLD, WHITE, (46, 107, 214)])
            w, h = rnd.randint(10, 18), rnd.randint(22, 38)
            self.conf.append({"im": Image.new("RGBA", (w, h), c + (235,)), "x": rnd.uniform(20, W - 20),
                              "y0": rnd.uniform(-900, 150), "v": rnd.uniform(220, 380), "sw": rnd.uniform(20, 60),
                              "ph": rnd.uniform(0, 6.28), "rot": rnd.uniform(-200, 200), "a0": rnd.uniform(0, 360)})
        tx = self.texts
        self.sold = self._text_sprite("S  O  L  D", 60, 800, GOLD)
        self.h1 = self._text_sprite("עוד משפחה", 120, 900, WHITE)
        self.h2 = self._text_sprite("מצאה בית!", 120, 900, WHITE)
        self.line = self._text_sprite(tx.get("line") or "", 50, 500, MUTE)
        self.slogan = self._text_sprite(tx.get("slogan") or "", 44, 700, GOLD)

    def _key(self, size):
        """מפתח זהב מצויר (ראש עגול + להב עם שיניים)."""
        S = size * 4
        im = self._layer(S, S)
        d = self.ImageDraw.Draw(im)
        r, cx, cy = int(S * .2), int(S * .3), int(S * .3)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD)
        d.ellipse((cx - r * .45, cy - r * .45, cx + r * .45, cy + r * .45), fill=(0, 0, 0, 0))
        w, ex, ey = int(S * .085), int(S * .86), int(S * .86)
        d.line((cx + r * .55, cy + r * .55, ex, ey), fill=GOLD, width=w)
        for k in (0.58, 0.74):
            px, py = cx + (ex - cx) * k, cy + (ey - cy) * k
            d.line((px, py, px + S * .1, py - S * .1), fill=GOLD, width=w)
        return im.resize((size, size), self.Image.LANCZOS)

    def buyer(self, t):
        Image, ImageDraw = self.Image, self.ImageDraw
        fr = self.bgb.copy()
        for c in self.conf:   # קונפטי נופל לאורך כל הסרטון
            y = (c["y0"] + c["v"] * t + 900) % 1960 - 900   # חוזר מלמעלה — קונפטי לאורך כל הסרטון
            if not -60 < y < 940:
                continue
            x = c["x"] + c["sw"] * math.sin(c["ph"] + t * 2.2)
            p = c["im"].rotate(c["a0"] + c["rot"] * t, expand=True, resample=Image.BILINEAR)
            fr.alpha_composite(p, (int(x), int(y)))
        if self.logo:
            fr.alpha_composite(_fade(self.logo, _ease(t / 0.5)), ((W - self.logo.width) // 2, 110))
        cx, cy, R = W // 2, 590, 220
        a = _back((t - 0.2) / 0.6)
        if a > 0:
            ring = self._layer(2 * R + 20, 2 * R + 20)
            dr = ImageDraw.Draw(ring)
            dr.ellipse((10, 10, 2 * R + 10, 2 * R + 10), outline=GOLD, width=6)
            dr.ellipse((34, 34, 2 * R - 14, 2 * R - 14), fill=(255, 255, 255, 22))
            s = max(0.05, a)
            ring = ring.resize((max(1, int(ring.width * s)), max(1, int(ring.height * s))), Image.BILINEAR)
            fr.alpha_composite(ring, (cx - ring.width // 2, cy - ring.height // 2))
            k = self.key.rotate(12 * math.sin(t * 2.4) * min(1.0, t), resample=Image.BICUBIC)
            if s < 1:
                k = k.resize((max(1, int(k.width * s)), max(1, int(k.height * s))), Image.BILINEAR)
            fr.alpha_composite(k, (cx - k.width // 2, cy - k.height // 2))

        def up(sp, yc, t0, d=0.5):
            b = _ease((t - t0) / d)
            if b > 0:
                fr.alpha_composite(_fade(sp, b), (0, int(yc - sp.height / 2 + (1 - b) * 46)))
        up(self.sold, 880, 0.8)
        up(self.h1, 985, 1.0)
        up(self.h2, 1110, 1.2)
        up(self.line, 1215, 1.5)
        up(self.slogan, 1285, 1.7)
        self._agent_in(fr, t, 2.1, self._agent_cy())
        return fr.convert("RGB")

    def frame(self, t):
        return self.buyer(t) if self.kind == "buyer" else self.seller(t)


def sold_compose(kind, photo, texts, agents, music_path, out_path, logo_path, popen=None):
    """→ {'ok','duration','cover','error'} (אותו חוזה של social_video.vid_compose). kind = 'seller' / 'buyer'."""
    import subprocess, time
    import social_video as V
    ff = V.vid_ffmpeg()
    if not ff:
        return {"ok": False, "error": "אין ffmpeg"}
    if kind != "buyer" and not photo:
        return {"ok": False, "error": "אין תמונה לנכס"}
    popen = popen or subprocess.Popen
    try:
        P = _Sprites(kind, photo, texts, agents, logo_path)
        ain = ["-i", music_path] if music_path else ["-f", "lavfi", "-t", "%.2f" % DUR, "-i",
                                                      "anullsrc=r=48000:cl=stereo"]
        cmd = [ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
               "-r", str(FPS), "-i", "-"] + ain + [
               "-filter_complex", "[1:a]atrim=0:%.2f,asetpts=PTS-STARTPTS,volume=0.5,afade=in:d=0.3,"
               "afade=out:st=%.2f:d=1.0,aresample=48000[a]" % (DUR, DUR - 1.0),
               "-map", "0:v", "-map", "[a]", "-t", "%.2f" % DUR,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-g", "60",
               "-c:a", "aac", "-ar", "48000", "-b:a", "128k", "-movflags", "+faststart", "-threads", "1", out_path]
        proc = popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        t0, cover = time.time(), None
        try:
            for f in range(int(DUR * FPS)):
                if time.time() - t0 > V.RENDER_TIMEOUT_S:
                    proc.kill()
                    return {"ok": False, "error": "timeout"}
                img = P.frame(f / FPS)
                if f == int(4 * FPS):
                    cover = img
                proc.stdin.write(img.tobytes())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.stderr.read() if proc.stderr else b""
        if proc.wait(timeout=60) != 0:
            return {"ok": False, "error": "ffmpeg: %s" % (err or b"")[-300:].decode("utf-8", "replace")}
        cp = out_path.rsplit(".", 1)[0] + "-cover.jpg"
        (cover or P.frame(4.0)).save(cp, quality=88)
        return {"ok": True, "duration": DUR, "cover": cp}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def sold_music(env=None):
    """הקטע הקצבי (SOLD_MUSIC ב-Render = שם קובץ מ-assets/music); ברירת מחדל Rising Forest."""
    import social_video as V
    d = V._music_dir()
    name = str(SP._env(env).get("SOLD_MUSIC") or "mixkit-rising-forest.mp3").strip()
    p = os.path.join(d, os.path.basename(name))
    if os.path.exists(p):
        return p
    try:
        fs = sorted(f for f in os.listdir(d) if f.endswith(".mp3"))
    except OSError:
        fs = []
    return os.path.join(d, fs[-1]) if fs else None


# ── רשומות (JSON בדיסק הקבוע) ─────────────────────────────────────────────────────
class SoldDB:
    def __init__(self, path=None):
        import tempfile
        self.path = path or os.path.join(os.environ.get("MAP_CACHE_DIR") or tempfile.gettempdir(), "sold_stories.json")
        self._lk = threading.Lock()

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, list) else []
        except (OSError, ValueError):
            return []

    def _write(self, items):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items[-KEEP:], f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def insert(self, rec):
        import secrets
        with self._lk:
            items = self._read()
            r = dict(rec, id="s" + secrets.token_hex(6))
            items.append(r)
            self._write(items)
            return dict(r)

    def update(self, sid, f):
        with self._lk:
            items = self._read()
            for r in items:
                if r.get("id") == sid:
                    r.update(f)
            self._write(items)

    def claim(self, sid, frm, to):
        """מעבר מצב אטומי (לחיצה כפולה על 'פרסם' לא מפרסמת פעמיים)."""
        with self._lk:
            items = self._read()
            for r in items:
                if r.get("id") == sid and r.get("status") in frm:
                    r["status"] = to
                    self._write(items)
                    return True
            return False

    def get(self, sid):
        return next((dict(r) for r in self._read() if r.get("id") == sid), None)

    def last(self, ref):
        return next((dict(r) for r in reversed(self._read()) if r.get("ref") == ref), None)

    def all(self):
        return self._read()


_DB = None


def _db():
    global _DB
    if _DB is None:
        _DB = SoldDB()
    return _DB


# ── יצירה ופרסום ────────────────────────────────────────────────────────────────
_STALE_S = 900


def _agent(G, name):
    """{'name','phone','photo'} — הטלפון הווירטואלי (כמו בסרטוני הנכסים), אחרת הנייד האישי, אחרת טלפון המשרד."""
    import social_video as V
    try:
        ph = G["_vphone_for_name"](name) or ""
    except Exception:
        ph = ""
    if not ph:
        l9 = V._agent_personal(G, {"סוכן 1": name})
        ph = ("0" + l9) if l9 else str(V._office(G).get("phone") or "")
    try:
        photo = V._agent_photo(G, {"סוכן 1": name})
    except Exception:
        photo = None
    return {"name": name, "phone": sold_phone(ph), "photo": photo}


def _deal(G, did):
    try:
        return next((d for d in (G["_deals_load"]() or []) if str(d.get("id")) == str(did)), None)
    except Exception:
        return None


def sold_create(G, ref_kind, ref, side, by_phone, http=None, env=None, store=None, db=None):
    """ref_kind = 'prop' (מספר מודעה, side seller/both) או 'deal' (מזהה עסקה, side buyer).
    → {'ok','id','status','reason'}. מרנדר ושומר — הפרסום בלחיצה נפרדת (sold_publish)."""
    import time as _t
    import social_video as V
    env = SP._env(env)
    db = db or _db()
    store = store or V._store()
    res = {"ok": False, "id": "", "status": "", "reason": ""}
    if SP.soc_mode(env) == "off":
        res["reason"] = "כבוי"
        return res
    if ref_kind == "prop":
        if side not in ("seller", "both"):
            res["reason"] = "צד לא תקין"
            return res
        row = V._row_by_key(G, SP._key(ref))
        if not row:
            res["reason"] = "הנכס לא נמצא"
            return res
        names = [str(row.get(c) or "").strip() for c in ("סוכן 1", "סוכן 2")]
        texts, kind, key = sold_texts_property(row, side), "seller", "p:" + SP._key(ref)
    elif ref_kind == "deal":
        deal = _deal(G, ref)
        if not deal or not sold_deal_ok(deal):
            res["reason"] = "העסקה לא נמצאה או לא נסגרה"
            return res
        names, texts, kind, key, side, row = sold_agents_for_deal(deal), sold_texts_deal(deal), "buyer", \
            "d:" + str(ref), "buyer", None
    else:
        res["reason"] = "סוג לא תקין"
        return res
    last = db.last(key)
    if last and last.get("status") in ("rendering", "publishing") and \
            _t.time() - (last.get("ts") or 0) < _STALE_S:
        res["reason"] = "כבר בהכנה"
        return res
    seen, agents = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            agents.append(_agent(G, n))
    tok = store.new_token()
    rec = db.insert({"ref": key, "kind": kind, "side": side, "status": "rendering", "video_token": tok,
                     "by_phone": str(by_phone or ""), "ts": _t.time(), "mode": SP.soc_mode(env)})
    res["id"] = rec["id"]
    try:
        photo = None
        if kind == "seller":
            if http is None:
                import requests as http
            for src in SP.soc_images(row)[:3]:
                photo = SP.soc_fetch_jpeg(http, src, False)
                if photo:
                    break
            if not photo:
                raise RuntimeError("התמונה של הנכס לא ירדה")
        with V._render_lock():
            out = sold_compose(kind, photo, texts, agents, sold_music(env), store.path(tok), V._logo_path())
        if not out.get("ok"):
            raise RuntimeError(out.get("error") or "רינדור נכשל")
        db.update(rec["id"], {"status": "ready", "ts": _t.time(), "agents": [a["name"] for a in agents]})
        res.update(ok=True, status="ready")
        _log.info("sold-story create ref=%s id=%s status=ready", key, rec["id"])
    except Exception as e:
        msg = SP._scrub(str(e), [str(env.get("META_TOKEN") or "")])[:400]
        db.update(rec["id"], {"status": "failed", "error": msg, "ts": _t.time()})
        store.remove(tok)
        res.update(status="failed", reason=msg)
        _log.warning("sold-story create ref=%s id=%s status=failed reason=%s", key, rec["id"], msg)
    return res


def sold_publish(G, sid, http=None, env=None, store=None, db=None):
    """מעלה סטורי מוכן לאינסטגרם ולפייסבוק (ערוצים שעוד לא הצליחו). → {'ok','status','reason'}."""
    import time as _t
    import social_video as V
    env = SP._env(env)
    db = db or _db()
    store = store or V._store()
    res = {"ok": False, "status": "", "reason": ""}
    rec = db.get(sid)
    if not rec:
        res["reason"] = "הסטורי לא נמצא"
        return res
    if SP.soc_mode(env) != "publish":
        res["reason"] = "מצב בדיקה — לא מפרסמים"
        return res
    if not store.exists(rec.get("video_token")):
        res["reason"] = "הסרטון כבר לא זמין — צור מחדש"
        return res
    token = str(env.get("META_TOKEN") or "").strip()
    if not token:
        res["reason"] = "אין META_TOKEN"
        return res
    if not db.claim(sid, ("ready", "partial"), "publishing"):
        res["reason"] = "כבר בפרסום"
        return res
    if http is None:
        import requests as http
    scfg = SP._cfg_social(G)
    vurl = "%s/v2/social/vid/%s.mp4" % (V._base(env), rec["video_token"])
    page_id = str(scfg.get("page_id") or SP.PAGE_ID_DEFAULT)
    g = SP.Graph(http, token, env)
    upd, errs = {}, []
    for c in [c for c in CHANNELS if rec.get(c + "_status") != "ok"]:
        try:
            if c == "ig_story":
                ig_id = scfg.get("ig_id") or g.page_ig_id(page_id)
                if not ig_id:
                    raise SP.MetaError("אינסטגרם לא מקושר לעמוד")
                upd["ig_story_id"], _ = g.ig_video(ig_id, "STORIES", vurl, ai=False)
            else:
                upd["fb_story_id"] = g.fb_video_story(page_id, vurl)
            upd[c + "_status"] = "ok"
        except Exception as e:
            upd[c + "_status"] = "failed"
            errs.append("%s: %s" % (c, SP._scrub(str(e), [token])))
            if getattr(e, "code", None) in (190, 102):
                break
    merged = dict(rec, **upd)
    oks = [c for c in CHANNELS if merged.get(c + "_status") == "ok"]
    upd.update(status="published" if len(oks) == len(CHANNELS) else "partial", ts=_t.time(),
               published_at=_t.time(), error=" | ".join(errs)[:600])
    db.update(sid, upd)
    res.update(ok=bool(oks), status=upd["status"], reason=upd["error"])
    _log.info("sold-story publish ref=%s id=%s status=%s %s%s", rec.get("ref"), sid, upd["status"],
              " ".join("%s=%s" % (c, merged.get(c + "_status") or "-") for c in CHANNELS),
              (" errors: " + upd["error"]) if errs else "")
    try:
        G["_log_activity"]("אפי", "system", "", "סטורי SOLD — " + ("פורסם" if oks else "נכשל"), rec.get("ref"))
    except Exception:
        pass
    return res


def sold_view(rec, now):
    """מה שהכרטיס צריך: מצב, קישור צפייה, תוצאה לכל ערוץ. רינדור שנתקע (אתחול באמצע) → נכשל."""
    if not rec:
        return None
    st = rec.get("status")
    if st in ("rendering", "publishing") and now - (rec.get("ts") or 0) > _STALE_S:
        st = "failed" if st == "rendering" else "partial"
    return {"id": rec.get("id"), "status": st, "side": rec.get("side"), "token": rec.get("video_token"),
            "ig": rec.get("ig_story_status"), "fb": rec.get("fb_story_status"), "error": rec.get("error") or "",
            "when": rec.get("published_at") or rec.get("ts")}


def register(app, G):
    from flask import jsonify, request
    import time as _t
    import social_video as V

    def dev():
        s = G["_web_auth"]()
        if not s:
            return None, (jsonify({"ok": False, "auth": False}), 401)
        if s.get("drole") != "developer":
            return None, (jsonify({"ok": False, "error": "forbidden"}), 403)
        return s, None

    @app.route("/v2/api/social/sold", methods=["POST"])
    def sold_api_create():
        s, err = dev()
        if err:
            return err
        j = request.get_json(silent=True) or {}
        if j.get("deal"):
            kind, ref, side = "deal", str(j.get("deal")), "buyer"
        else:
            kind, ref, side = "prop", SP._key(j.get("key")), str(j.get("side") or "seller")
        if not ref:
            return jsonify({"ok": False, "error": "חסר נכס/עסקה"}), 400
        by = s.get("phone", "")
        V._spawn(lambda: sold_create(G, kind, ref, side, by))
        return jsonify({"ok": True, "queued": True})

    @app.route("/v2/api/social/sold/publish", methods=["POST"])
    def sold_api_publish():
        s, err = dev()
        if err:
            return err
        sid = str((request.get_json(silent=True) or {}).get("id") or "")
        rec = _db().get(sid)
        if not rec or rec.get("status") not in ("ready", "partial"):
            return jsonify({"ok": False, "error": "הסטורי לא מוכן לפרסום"})
        if SP.soc_mode(os.environ) != "publish":
            return jsonify({"ok": False, "error": "מצב בדיקה — לא מפרסמים"})
        V._spawn(lambda: sold_publish(G, sid))   # אינסטגרם מעבד את הסרטון עד כמה דקות — לא מחזיקים את הבקשה
        return jsonify({"ok": True, "queued": True})

    @app.route("/v2/api/social/sold/list")
    def sold_api_list():
        s, err = dev()
        if err:
            return err
        db, now = _db(), _t.time()
        refs = ["p:" + SP._key(k) for k in str(request.args.get("keys") or "").split(",") if SP._key(k)][:200]
        refs += ["d:" + k.strip() for k in str(request.args.get("deals") or "").split(",") if k.strip()][:200]
        last = {}
        for r in db.all():
            if r.get("ref") in refs:
                last[r["ref"]] = r
        return jsonify({"ok": True, "mode": SP.soc_mode(os.environ), "items": {k: sold_view(v, now) for k, v in last.items()}})
