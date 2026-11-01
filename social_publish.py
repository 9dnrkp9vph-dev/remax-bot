"""social_publish.py — פרסום נכסי המשרד בעמוד הפייסבוק ובאינסטגרם ישירות מאפי (Meta Graph API).

ספק: docs/superpowers/specs/2026-10-31-social-publish-meta-design.md (אייל אישר 31/10).
החלק העליון טהור — בלי Flask ובלי רשת; תלויות (ניקוי תיאור, תגיות, http) מוזרקות.
SOCIAL_MODE: רק 'publish' מתיר כתיבה ל-Meta; כל ערך אחר = תצוגה מקדימה.
"""
from __future__ import annotations
import datetime as _dt
import json as _json
import re

try:
    from zoneinfo import ZoneInfo
    _IL = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover
    _IL = _dt.timezone(_dt.timedelta(hours=2))

DAILY_CAP = 5
ROUND_CAP = 3
FLOOD = 40
GAP_MIN = 20
REPEAT_DAYS = 14
WAIT_DAYS = 3
RETRY_DAYS = 3
ONE_IMG_HOURS = 72
MAX_IMAGES = 10
DESC_MAX = 600
NIGHT = (22, 8)
KNOWN_TTL_DAYS = 60
IMG_TTL_H = 24
IMG_MAX_PX = 1440
LOOP_SEC = 600

PHONE_RE = re.compile(r"(?:\+?972[-\s]?|\b0)(?:5\d|[2-9])(?:[-\s]?\d){7}\b")


def soc_scrub_phones(text):
    """מוחק מספרי טלפון (אותו ביטוי כמו באתר) ומיישר רווחים כפולים שנשארו."""
    t = PHONE_RE.sub("", str(text or ""))
    return re.sub(r"[ \t]{2,}", " ", t)


def soc_scrub_house(text, street):
    """מוחק מספר בית שבא אחרי שם הרחוב של הנכס (גם אחרי המילה האחרונה בלבד, 'מס'' ו-'14א').
    הכותרת כבר בלי מספר בית — זה מכסה את התיאור שבעל הנכס כתב. רחובות אחרים ומספרים אחרים לא נוגעים."""
    t = str(text or "")
    words = re.sub(r"[\d/]+[א-ת]?\s*$", "", _norm(street)).split()
    if not words:
        return t
    num = r"\s*(?:מס['׳]?\s*)?\d+[א-ת]?(?:/\d+)?(?!\d|[.,]\d)"
    for name in {" ".join(words), words[-1]}:
        if len(name) < 2:
            continue
        t = re.sub("(" + re.escape(name).replace(r"\ ", r"\s+") + ")" + num, r"\1", t)
    return re.sub(r"[ \t]{2,}", " ", t)


def _num(v):
    """'4' / '4.0' / '4.5' / 4 → '4' / '4.5'; לא-מספר → מחרוזת נקייה."""
    s = str(v if v is not None else "").strip()
    try:
        f = float(s.replace(",", ""))
        return str(int(f)) if f == int(f) else ("%g" % f)
    except ValueError:
        return s


def _norm(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s.replace("קריית", "קרית")


def soc_addr_key(row):
    """'<עיר>|<רחוב>|<מספר בית>|<חדרים>' מנורמל — לכלל 'אותה דירה' (בלי קומה)."""
    return "|".join((_norm(row.get("עיר / ישוב")), _norm(row.get("כתובת")),
                     _num(row.get("מספר בית")), _num(row.get("חדרים"))))


def soc_floor(row):
    """קומת הנכס: העמודה, אחרת מהתיאור ('קומה 7 מתוך 9'); לא ידוע → ''."""
    v = _num(row.get("קומה"))
    if v and re.fullmatch(r"-?\d+", v):
        return v
    txt = " ".join(str(row.get(k, "") or "") for k in ("_desc_ae", "תיאור"))
    m = re.search(r"קומה\s*(-?\d+)", txt)
    return m.group(1) if m else ""


def soc_images(row):
    """עד MAX_IMAGES כתובות מקור: 'תמונות' (רשימה / JSON / פסיקים), בלעדיה 'תמונה'; בלי כפילויות."""
    raw = row.get("תמונות")
    lst = []
    if isinstance(raw, (list, tuple)):
        lst = list(raw)
    elif isinstance(raw, str) and raw.strip():
        t = raw.strip()
        try:
            v = _json.loads(t) if t.startswith("[") else None
        except ValueError:
            v = None
        lst = v if isinstance(v, list) else [x for x in t.split(",")]
    if not lst and str(row.get("תמונה") or "").strip():
        lst = [row.get("תמונה")]
    out = []
    for u in lst:
        u = str(u or "").strip()
        if u.startswith("http") and u not in out:
            out.append(u)
    return out[:MAX_IMAGES]


def _price(v):
    s = re.sub(r"[^\d]", "", str(v or ""))
    try:
        return "{:,}".format(int(float(_num(v)))) if s else ""
    except ValueError:
        return ""


def _cut(t, n):
    t = str(t or "").strip()
    if len(t) <= n:
        return t
    t = t[:n - 1]
    sp = t.rfind(" ")
    if sp > n // 2:
        t = t[:sp]
    return t.rstrip(" ,.-·") + "…"


def soc_build_post(row, office_name, clean_desc, feats, agent=None, wa_link=None):
    """שורת נכס → {'body', 'ig_caption', 'images'}. בלי מספר בית; טלפונים מהתיאור נמחקים.
    agent = {'name','phone'} — שם הסוכן ווואטסאפ לנייד האישי שלו בסוף (01/11); בלי — 'לפרטים — הודעה לעמוד'."""
    rent = "שכר" in str(row.get("סוג עסקה") or "")
    rooms = _num(row.get("חדרים"))
    kind = _norm(row.get("סוג נכס"))
    nb, city = _norm(row.get("שכונה")), _norm(row.get("עיר / ישוב"))
    where = ", ".join(x for x in (nb, city) if x)
    what = " ".join(x for x in ((kind if kind and kind != "דירה" else ""),
                                 (rooms + " חדרים" if rooms and rooms != "0" else "")) if x) or (kind or "נכס")
    lines = [("🏡 " + ("להשכרה" if rent else "למכירה") + " · " + what + ((" ב" + where) if where else ""))]
    street = re.sub(r"\s*(?:מס['׳]?\s*)?[\d/]+[א-ת]?\s*$", "", _norm(row.get("כתובת")))
    if street:
        lines.append("📍 " + street)
    pr = _price(row.get("מחיר"))
    if pr:
        lines.append("💰 " + pr + " ₪" + (" לחודש" if rent else ""))
    fl = soc_floor(row)
    size = _num(row.get('מ"ר'))
    spec = [x for x in ((size + ' מ"ר') if size and size != "0" else "", ("קומה " + fl) if fl else "") if x]
    if spec:
        lines.append("📐 " + " · ".join(spec))
    ft = [f for f in (feats(row) or []) if f]
    if ft:
        lines.append("✔ " + " · ".join(ft))
    desc = soc_scrub_phones(clean_desc(row.get("_desc_ae") or row.get("תיאור") or ""))
    desc = soc_scrub_house(desc, row.get("כתובת"))
    desc = _cut(re.sub(r"\s+\n", "\n", desc), DESC_MAX)
    parts = ["\n".join(lines)]
    if desc:
        parts.append(desc)
    # [01/11] שם הסוכן ווואטסאפ לנייד האישי שלו (אייל: 'בפוסט עצמו'). בפייסבוק קישור wa.me;
    # באינסטגרם קישור בטקסט לא לחיץ — המספר. בלי שם אמיתי — כמו קודם, פניות לעמוד.
    ag = agent or {}
    an = _norm(ag.get("name"))
    digits = re.sub(r"\D", "", str(ag.get("phone") or ""))
    local = ("0" + digits[3:]) if digits.startswith("972") else digits
    if not an or not _real_agent(an):
        fb_end = ig_end = "לפרטים — הודעה לעמוד"
    elif len(local) == 10 and local.startswith("05"):
        # [02/11] קישור קצר של אפי (מפנה לוואטסאפ עם הודעה מוכנה); בלעדיו — wa.me ישיר
        fb_end = "לפרטים: %s\nוואטסאפ: %s" % (an, wa_link or ("https://wa.me/972" + local[1:]))
        # [02/11] באינסטגרם קישור לא לחיץ — המספר, ובקשה לציין מאיפה ועל איזו מודעה (שהסוכן יידע)
        ig_end = "לפרטים בוואטסאפ: %s · %s-%s-%s" % (an, local[:3], local[3:6], local[6:])
        k_ad = _key(row.get("מספר מודעה"))
        if k_ad:
            ig_end += "\nציינו בהודעה: מודעה %s מאינסטגרם" % k_ad
    else:
        fb_end = ig_end = "לפרטים: %s · הודעה לעמוד" % an
    office = str(office_name or "").strip()
    head = "\n\n".join(p for p in parts if p.strip())
    body = head + "\n\n" + (office + "\n" if office else "") + fb_end
    tags = ["#נדלן", "#דירותלהשכרה" if rent else "#דירותלמכירה"]
    if city:
        tags.append("#" + city.replace(" ", "").replace("-", ""))
    tags.append("#רימקספמילי")
    ig = head + "\n\n" + (office + "\n" if office else "") + ig_end
    return {"body": body, "ig_caption": ig + "\n\n" + " ".join(tags), "images": soc_images(row)}


def soc_wa_text(row, agent_name, office_name, src="fb"):
    """[02/11, אייל] ההודעה שהפונה שולח לסוכן מהפוסט: מאיפה הגיע ועל איזה נכס — בלי מספר בית."""
    rent = "שכר" in str(row.get("סוג עסקה") or "")
    rooms = _num(row.get("חדרים"))
    kind = _norm(row.get("סוג נכס"))
    nb, city = _norm(row.get("שכונה")), _norm(row.get("עיר / ישוב"))
    what = " ".join(x for x in ((kind if kind and kind != "דירה" else "דירה"),
                                 (rooms + " חדרים" if rooms and rooms != "0" else "")) if x)
    where = ", ".join(x for x in (nb, city) if x)
    street = re.sub(r"\s*(?:מס['׳]?\s*)?[\d/]+[א-ת]?\s*$", "", _norm(row.get("כתובת")))
    pr = _price(row.get("מחיר"))
    first = (_norm(agent_name).split() or [""])[0]
    place = "בעמוד הפייסבוק" if src != "ig" else "באינסטגרם"
    bits = [what + ((" ב" + where) if where else "")]
    if street:
        bits.append("רחוב " + street)
    if pr:
        bits.append(pr + " ₪" + (" לחודש" if rent else ""))
    key = _key(row.get("מספר מודעה"))
    return ("היי %s, ראיתי %s של %s את הנכס %s: %s%s. אשמח לפרטים."
            % (first, place, _norm(office_name) or "המשרד", "להשכרה" if rent else "למכירה",
               " · ".join(bits), (" (מודעה %s)" % key) if key else "")).replace("היי , ", "היי, ")


def _real_agent(name):
    """שם סוכן אמיתי — לא ממלא-מקום של הסורק ('סוכן 8719', 'משרד', '(לא משויך)')."""
    n = _norm(name)
    return bool(n) and not re.fullmatch(r"סוכן\s*\d*", n) and n not in ("משרד", "(לא משויך)", "לא משויך")


def soc_agent_for(G, row):
    """{'name', 'phone'}: הסוכן של הנכס והנייד האישי שלו מאנשי הקשר (לא טלפון המודעה). כשל → בלי טלפון."""
    name = _norm(row.get("סוכן 1") or row.get("סוכן"))
    phone = ""
    if name:
        try:
            book = G["fetch_agents_phones"]() or {}
            phone = book.get(name, "")
            if not phone:
                ck = G["_canon_key"](name)
                phone = next((v for k, v in book.items() if v and G["_canon_key"](k) == ck), "")
        except Exception:
            phone = ""
    return {"name": name, "phone": str(phone or "")}


# ── מתי מותר לפרסם ───────────────────────────────────────────────────────────────
def _ts(v):
    from goals import parse_ts   # מודול טהור (stdlib בלבד) — אותו פענוח תאריכים של היעדים
    return parse_ts(v)


def _day(ts):
    return _dt.datetime.fromtimestamp(ts, _IL).date()


def _dm(ts):
    return _dt.datetime.fromtimestamp(ts, _IL).strftime("%d/%m")


def _key(k):
    k = str(k or "").strip()
    return k[2:] if k.startswith("L:") else k


def _same_apartment(akey, afloor, hist_addr):
    h = str(hist_addr or "")
    hk, _, hf = h.partition("#")
    if not hk or hk != akey:
        return False
    return not (afloor and hf and afloor != hf)


def soc_can_publish(row, channel, history, now, hidden):
    """(True,'') או (False, סיבה). channel = 'fb' / 'ig'. history = שורות social_posts."""
    key = _key(row.get("מספר מודעה"))
    if str(row.get("ירד מפרסום") or "").strip() or str(row.get("delisted_at") or "").strip():
        return False, "ירד מפרסום"
    if key in {_key(h) for h in (hidden or ())}:
        return False, "מוסתר מהאתר"
    if "מסחר" in str(row.get("סוג עסקה") or ""):
        return False, "מסחרי"
    imgs = soc_images(row)
    if not imgs:
        return False, "אין תמונות"
    if len(imgs) < 2:
        fs = _ts(row.get("_y2_first_seen"))
        if fs is None or now - fs < ONE_IMG_HOURS * 3600:
            return False, "מחכה לתמונות"
    akey, afl = soc_addr_key(row), soc_floor(row)
    st_col = channel + "_status"
    last = None
    for h in history or []:
        if h.get("mode") != "publish":
            continue
        st = str(h.get(st_col) or "")
        if st not in ("ok", "unknown", "pending"):
            continue
        t = _ts(h.get("created_at"))
        if t is None or now - t >= REPEAT_DAYS * 86400:
            continue
        if _key(h.get("property_key")) != key and not _same_apartment(akey, afl, h.get("addr_key")):
            continue
        if st in ("unknown", "pending") and _day(t) == _day(now):
            return False, "כבר נשלח היום"
        last = t if last is None else max(last, t)
    if last is not None:
        return False, "פורסם %s · אפשר שוב מ-%s" % (_dm(last), _dm(last + REPEAT_DAYS * 86400))
    return True, ""


# ── הסבב האוטומטי ────────────────────────────────────────────────────────────────
def soc_seed_known(rows, now):
    """מצב התחלתי בהפעלה: כל מספרי המודעה הקיימים 'ידועים' — הם לא יתפרסמו אוטומטית."""
    return {"known": {_key(r.get("מספר מודעה")): now for r in rows or [] if _key(r.get("מספר מודעה"))},
            "waiting": {}, "enabled_at": now}


def _is_night(now):
    h = _dt.datetime.fromtimestamp(now, _IL).hour
    return h >= NIGHT[0] or h < NIGHT[1]


# [01/11, אייל] פרסום אוטומטי רק לנכסים של מי שהיה באפי לפחות ACTIVE_MIN דק' ב-ACTIVE_DAYS הימים האחרונים
# (פעימות הנוכחות, כולל CRM — אותו מקור של היעדים); לשאר — רק ידני דרך אייל.
ACTIVE_DAYS = 30
ACTIVE_MIN = 10
ACTIVE_TTL = 600
_ACTIVE_BOX = {}


def soc_active_agents(G, now):
    """קבוצת שמות קנוניים של מי שעבר את הסף, או None כשאין נתוני שימוש (Supabase כבוי/תקלה) — אז לא מפרסמים אוטומטית."""
    bx = _ACTIVE_BOX
    if bx.get("v") is not None and now - bx.get("t", 0) < ACTIVE_TTL:
        return bx["v"]
    from goals import g_canon, g_display
    d0 = _dt.datetime.fromtimestamp(now, _IL) - _dt.timedelta(days=ACTIVE_DAYS)
    try:
        rows = [r for r in (G["_usage_rows"](d0) or []) if r.get("name")]
    except Exception:
        return None
    if not rows:
        return None
    v = {g_canon(G, g_display(G, r["name"])) for r in rows if float(r.get("min") or 0) >= ACTIVE_MIN}
    bx.update(v=v, t=now)
    return v


def soc_plan_round(rows, state, history, now, hidden, blocked, allowed=None):
    """→ {'publish': [keys], 'state': state חדש, 'flood': bool, 'reason': str}.
    'חדש' = מספר מודעה שלא נראה (known) — לא _y2_first_seen, שנדרס בהזרמות ושחזורים."""
    st = {"known": dict((state or {}).get("known") or {}), "waiting": dict((state or {}).get("waiting") or {}),
          "enabled_at": (state or {}).get("enabled_at", now)}
    for k in [k for k, v in st["known"].items() if now - float(v or 0) > KNOWN_TTL_DAYS * 86400]:
        st["known"].pop(k, None)
    by_key = {}
    for r in rows or []:
        k = _key(r.get("מספר מודעה"))
        if k:
            by_key[k] = r
    new = [k for k in by_key if k not in st["known"]]
    for k in by_key:
        st["known"][k] = now
    out = {"publish": [], "state": st, "flood": False, "reason": ""}
    if len(new) > FLOOD:
        out.update(flood=True, reason="נראה כמו הזרמה — %d נכסים חדשים בבת אחת" % len(new))
        return out
    for k in new:
        st["waiting"].setdefault(k, now)
    def _expired(k, t):   # נכס עם תמונה אחת מחכה גם ל-72 השעות (ביקורת סופית — אחרת לא היה עולה אף פעם)
        extra = ONE_IMG_HOURS * 3600 if len(soc_images(by_key[k])) < 2 else 0
        return now - float(t) > WAIT_DAYS * 86400 + extra
    for k in [k for k, t in st["waiting"].items() if k not in by_key or _expired(k, t)]:
        st["waiting"].pop(k, None)
    if blocked or _is_night(now):
        out["reason"] = "שבת / השתקה / לילה"
        return out
    today, last_auto = 0, None
    for h in history or []:
        if h.get("trigger") != "auto" or h.get("mode") != "publish":
            continue
        t = _ts(h.get("created_at"))
        if t is None:
            continue
        if _day(t) == _day(now):
            today += 1
        last_auto = t if last_auto is None else max(last_auto, t)
    if last_auto is not None and now - last_auto < GAP_MIN * 60:
        out["reason"] = "מרווח בין פוסטים"
        return out
    slots = min(ROUND_CAP, DAILY_CAP - today)
    if slots <= 0:
        out["reason"] = "התקרה היומית"
        return out
    for k in sorted(st["waiting"], key=lambda x: -float(st["waiting"][x])):
        if len(out["publish"]) >= slots:
            break
        r = by_key[k]
        if allowed is not None and not allowed(r):   # [01/11] סוכן לא פעיל — נשאר בהמתנה (ידני עדיין אפשרי)
            continue
        if soc_can_publish(r, "fb", history, now, hidden)[0] or soc_can_publish(r, "ig", history, now, hidden)[0]:
            out["publish"].append(k)
            st["waiting"].pop(k, None)
    return out


# ── תמונות: JPEG זמני ש-Meta מושכת מאפי ──────────────────────────────────────────
def soc_jpeg(raw, square):
    """bytes של תמונה → JPEG. square=True: ריבוע IMG_MAX_PX, התמונה כולה במרכז ושוליים מטושטשים
    (אינסטגרם דוחה יחס מחוץ ל-4:5–1.91:1, ובקרוסלה כולן באותו יחס). לא תמונה → None."""
    import io
    try:
        from PIL import Image, ImageFilter, ImageOps
        im = Image.open(io.BytesIO(raw or b""))
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        return None
    if square:
        S = IMG_MAX_PX
        w, h = im.size
        sc = max(S / w, S / h)
        bg = im.resize((max(1, int(w * sc)), max(1, int(h * sc))))
        l, t = (bg.width - S) // 2, (bg.height - S) // 2
        bg = bg.crop((l, t, l + S, t + S)).filter(ImageFilter.GaussianBlur(28))
        # [01/11] התמונה ממלאת את הריבוע ברוחב (או בגובה, לתמונה לאורך) — גם מוגדלת. thumbnail לא מגדיל,
        # ותמונות יד2 (~800px) ישבו בחצי גודל באמצע ריבוע של 1440.
        fs = min(S / w, S / h)
        fg = im.resize((max(1, round(w * fs)), max(1, round(h * fs))), Image.LANCZOS)
        bg.paste(fg, ((S - fg.width) // 2, (S - fg.height) // 2))
        im = bg
    else:
        im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


class ImgStore:
    """טוקן אקראי → כתובת המקור, ל-IMG_TTL_H שעות. בכתובת שמוגשת ל-Meta אין שום פרט על הנכס."""

    def __init__(self):
        import threading
        self._d, self._lock = {}, threading.Lock()

    def put(self, src_url, now):
        import secrets
        tok = secrets.token_urlsafe(16)
        with self._lock:
            self.purge(now)
            self._d[tok] = (str(src_url), float(now))
        return tok

    def get(self, token, now):
        with self._lock:
            v = self._d.get(str(token or ""))
        if not v or now - v[1] > IMG_TTL_H * 3600:
            return None
        return v[0]

    def purge(self, now):
        for k in [k for k, v in self._d.items() if now - v[1] > IMG_TTL_H * 3600]:
            self._d.pop(k, None)


# [01/11] תמונות 'נכס חדש נולד · תמונות בקרוב' של המשרד — טביעת dHash (64 ביט) של 4 העיצובים שנמצאו
# בסריקת 478 נכסי המשרד (25 נכסים הציגו אחת מהן כתמונה ראשונה). מרחק עד PLACEHOLDER_DIST = אותה תמונה.
PLACEHOLDER_HASHES = (0x17b33633f1ecc45d, 0x4c0f03152f277517, 0x29b3d22a06e2f3b4, 0x960c44f2c26371a6)
PLACEHOLDER_DIST = 6


def soc_dhash(raw):
    """טביעת dHash של תמונה (עמידה להקטנה/דחיסה); לא תמונה → None."""
    import io
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw or b"")).convert("L").resize((9, 8), Image.LANCZOS)
    except Exception:
        return None
    p = list(im.getdata())
    return int("".join("1" if p[r * 9 + c] > p[r * 9 + c + 1] else "0" for r in range(8) for c in range(8)), 2)


def soc_is_placeholder(raw):
    h = soc_dhash(raw)
    return h is not None and any(bin(h ^ x).count("1") <= PLACEHOLDER_DIST for x in PLACEHOLDER_HASHES)


PLACEHOLDER_REASON = "יש רק תמונת 'תמונות בקרוב' — מחכה לתמונות אמיתיות"


def soc_real_images(http, images):
    """(התמונות האמיתיות, כמה היו 'תמונות בקרוב'): הורדה של כל תמונה; כשל הורדה — התמונה מדולגת."""
    real, ph = [], 0
    for src in images or []:
        j = soc_fetch_jpeg(http, src, False) if http is not None else None
        if not j:
            continue
        if soc_is_placeholder(j):
            ph += 1
        else:
            real.append(src)
    return real, ph


def soc_big_url(src_url):
    """[01/11] תמונת יד2 בגודל המלא: הכתובת הרגילה מחזירה ~384–720px, ו-?c=6 מחזירה את המקור (1100–2000px)."""
    u = str(src_url or "")
    if "img.yad2.co.il" not in u:
        return u
    return u.split("?", 1)[0] + "?c=6"


def soc_fetch_jpeg(http, src_url, square):
    """הורדה מהמקור והמרה ל-JPEG; קודם בגודל המלא, ואם נכשל — הכתובת המקורית. כל כשל → None (התמונה מדולגת)."""
    for url in dict.fromkeys((soc_big_url(src_url), src_url)):
        try:
            r = http.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if getattr(r, "status_code", 0) >= 400:
                continue
            j = soc_jpeg(getattr(r, "content", b""), square)
            if j:
                return j
        except Exception:
            continue
    return None


# ── לקוח Meta Graph ──────────────────────────────────────────────────────────────
GRAPH = "https://graph.facebook.com"
GRAPH_VER = "v23.0"   # לאמת מול התיעוד בהגדרה (ספק: 'הבונה מעדכן את הגרסה')


def soc_mode(env):
    """'off' / 'preview' / 'publish'. רק 'publish' (אחרי strip+lower) מתיר כתיבה; כל ערך אחר = preview."""
    v = str((env or {}).get("SOCIAL_MODE") or "").strip().lower()
    return v if v in ("off", "publish") else "preview"


def _scrub(msg, tokens):
    s = str(msg)
    for t in ([tokens] if isinstance(tokens, str) else (tokens or [])):
        if t:
            s = s.replace(t, "***")
    return s


class MetaError(Exception):
    def __init__(self, msg, code=None, unknown=False):
        super().__init__(msg)
        self.code, self.unknown = code, unknown


class Graph:
    """Meta Graph API. כל בקשת כתיבה עוברת _guard (SOCIAL_MODE=publish בלבד).
    עמוד: טוקן עמוד שנגזר מטוקן ה-System User; אינסטגרם: טוקן ה-System User."""

    def __init__(self, http, token, env, sleep=None, version=None):
        import time as _t
        self.http, self.token, self.env = http, token, env or {}
        self.sleep = sleep or _t.sleep
        self.ver = version or GRAPH_VER
        self._ptok = {}

    def _url(self, path):
        return "%s/%s/%s" % (GRAPH, self.ver, str(path).lstrip("/"))

    def _secrets(self):
        return [self.token] + list(self._ptok.values())

    def _guard(self):
        if soc_mode(self.env) != "publish":
            raise RuntimeError("SOCIAL_MODE is not publish")

    def _call(self, method, path, token, fields, final=False):
        args = dict(fields or {}, access_token=token)
        try:
            if method == "GET":
                r = self.http.get(self._url(path), params=args, timeout=30)
            else:
                r = self.http.post(self._url(path), data=args, timeout=60)
        except Exception as e:
            raise MetaError(_scrub("%s %s: %s" % (method, path, e), self._secrets()), unknown=final)
        try:
            j = r.json() or {}
        except Exception:
            j = {}
        if getattr(r, "status_code", 200) >= 400 or "error" in j:
            e = j.get("error") or {}
            code = e.get("code")
            # 5xx / קוד 1-2 בכתיבה הסופית: ייתכן שהפוסט נוצר — 'unknown', לא לנסות שוב (ביקורת סופית)
            unk = final and (getattr(r, "status_code", 200) >= 500 or code in (1, 2))
            raise MetaError(_scrub(e.get("message") or str(j)[:200], self._secrets()), code=code, unknown=unk)
        return j

    # קריאה
    def me(self):
        return self._call("GET", "me", self.token, {"fields": "id,name"})

    def page_ig_id(self, page_id):
        j = self._call("GET", page_id, self.token, {"fields": "instagram_business_account"})
        return ((j.get("instagram_business_account") or {}).get("id")) or None

    def page_token(self, page_id):
        if page_id not in self._ptok:
            j = self._call("GET", page_id, self.token, {"fields": "access_token"})
            if not j.get("access_token"):
                raise MetaError("no page access_token", code=190)
            self._ptok[page_id] = j["access_token"]
        return self._ptok[page_id]

    def invalidate_page_token(self, page_id=None):
        if page_id is None:
            self._ptok.clear()
        else:
            self._ptok.pop(page_id, None)

    def ig_quota(self, ig_id):
        j = self._call("GET", "%s/content_publishing_limit" % ig_id, self.token, {"fields": "config,quota_usage"})
        d = (j.get("data") or [{}])[0]
        total = ((d.get("config") or {}).get("quota_total"))
        used = d.get("quota_usage")
        return None if total is None or used is None else max(0, int(total) - int(used))

    # עמוד פייסבוק
    def _page(self, method, page_id, path, fields, final=False):
        try:
            return self._call(method, path, self.page_token(page_id), fields, final)
        except MetaError as e:
            if e.code != 190 or e.unknown:
                raise
            self.invalidate_page_token(page_id)
            return self._call(method, path, self.page_token(page_id), fields, final)

    def fb_post(self, page_id, message, image_urls):
        """תמונות כ-published=false ← פוסט אחד עם כולן. → (post_id, permalink_url)."""
        self._guard()
        ids = []
        for u in image_urls:
            ids.append(self._page("POST", page_id, "%s/photos" % page_id, {"url": u, "published": "false"})["id"])
        j = self._page("POST", page_id, "%s/feed" % page_id,
                       {"message": message, "attached_media": _json.dumps([{"media_fbid": i} for i in ids])},
                       final=True)
        pid = j.get("id")
        link = ""
        try:
            link = self._page("GET", page_id, pid, {"fields": "permalink_url"}).get("permalink_url") or ""
        except MetaError:
            pass
        return pid, link

    # אינסטגרם
    def _wait(self, cid, poll_max=40):
        for _ in range(poll_max):
            st = str(self._call("GET", cid, self.token, {"fields": "status_code"}).get("status_code") or "")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise MetaError("instagram container %s" % st)
            self.sleep(3)
        raise MetaError("instagram container not ready")

    def ig_post(self, ig_id, caption, image_urls):
        """תמונה אחת / קרוסלה ← polling ← media_publish. → (media_id, permalink)."""
        self._guard()
        if len(image_urls) == 1:
            cid = self._call("POST", "%s/media" % ig_id, self.token, {"image_url": image_urls[0], "caption": caption})["id"]
        else:
            kids = [self._call("POST", "%s/media" % ig_id, self.token,
                               {"image_url": u, "is_carousel_item": "true"})["id"] for u in image_urls]
            cid = self._call("POST", "%s/media" % ig_id, self.token,
                             {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption})["id"]
        self._wait(cid)
        mid = self._call("POST", "%s/media_publish" % ig_id, self.token, {"creation_id": cid}, final=True).get("id")
        link = ""
        try:
            link = self._call("GET", mid, self.token, {"fields": "permalink"}).get("permalink") or ""
        except MetaError:
            pass
        return mid, link


# ── הרצה של פרסום אחד ────────────────────────────────────────────────────────────
PAGE_ID_DEFAULT = "750680235046279"   # 'REMAX family רימקס פמילי קריות' (asset_id ב-Business Suite); v2_social.page_id גובר
_RATE_CODES = (4, 17, 32, 613)
_IMG = ImgStore()


def _env(env):
    import os
    return os.environ if env is None else env


def _cfg_social(G):
    return dict(((G["_load_config"]() or {}).get("v2_social")) or {})


def _social_mutate(G, fn):
    def apply(cfg):
        s = dict(cfg.get("v2_social") or {})
        fn(s)
        cfg["v2_social"] = s
        return s
    return G["_config_mutate"](apply)


def _next_midnight(now):
    d = _dt.datetime.fromtimestamp(now, _IL).date() + _dt.timedelta(days=1)
    return _dt.datetime(d.year, d.month, d.day, tzinfo=_IL).timestamp()


def soc_hidden(G):
    """מספרי המודעה שהוסתרו מהאתר (website_settings) — אותו כלל של refamily.co.il."""
    try:
        import site_api
        store = site_api.SettingsStore(G.get("_sbdb"))
        rows = store.all()
        if not store.available:
            return None   # לא ידוע — במצב publish לא מפרסמים (ביקורת סופית)
        return site_api.prop_flags(rows)[0]
    except Exception:
        return None


def soc_office_rows(G):
    rows = list(G["fetch_sheet_rows"]() or [])
    try:
        rows += list(G["fetch_sheet_rows_deal"]("השכרה") or [])
    except Exception:
        pass
    return rows


def _clean_desc(G):
    try:
        import effie_v2
        return effie_v2.y2_clean_desc
    except Exception:
        return lambda d: str(d or "")


def soc_daily_alert(G, kind, title, body, now):
    """פוש אחד ביום לכל סוג (token / flood). → True אם נשלח."""
    day = _dt.datetime.fromtimestamp(now, _IL).date().isoformat()
    if (_cfg_social(G).get("alerts") or {}).get(kind) == day:
        return False
    _social_mutate(G, lambda s: s.__setitem__("alerts", dict(s.get("alerts") or {}, **{kind: day})))
    try:
        G["send_push"](title, body)
    except Exception:
        pass
    return True


def _who(G, trigger, by_phone):
    if trigger == "auto" or not by_phone:
        return "אפי", "system"
    try:
        return G["_display_name_for"]("", by_phone) or "מפתח", "developer"
    except Exception:
        return "מפתח", "developer"


_RUN_LOCK = None
_INFLIGHT = set()


def _inflight_lock():
    global _RUN_LOCK
    if _RUN_LOCK is None:
        import threading
        _RUN_LOCK = threading.Lock()
    return _RUN_LOCK


def _wa_link(env, key):
    base = str((env or {}).get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/")
    return "%s/v2/social/wa/%s" % (base, _key(key))


def soc_run_one(G, key, trigger, by_phone, channels=None, http=None, now=None, env=None):
    """פרסום (או תצוגה מקדימה) של נכס אחד. → {'ok','mode','fb','ig','reason','row_id'}.
    נגד כפילות (ביקורת סופית): נכס אחד בכל רגע; רשומת pending לפני כל כתיבה ל-Meta."""
    k0 = _key(key)
    with _inflight_lock():
        if k0 in _INFLIGHT:
            return {"ok": False, "mode": soc_mode(_env(env)), "fb": "skipped", "ig": "skipped",
                    "reason": "הנכס כבר בתהליך פרסום", "row_id": ""}
        _INFLIGHT.add(k0)
    try:
        return _soc_run_one(G, k0, trigger, by_phone, channels, http, now, env)
    finally:
        with _inflight_lock():
            _INFLIGHT.discard(k0)


def _soc_run_one(G, key, trigger, by_phone, channels, http, now, env):
    import time as _t
    env = _env(env)
    now = _t.time() if now is None else now
    mode = soc_mode(env)
    res = {"ok": False, "mode": mode, "fb": "skipped", "ig": "skipped", "reason": "", "row_id": ""}
    if mode == "off":
        res["reason"] = "כבוי"
        return res
    row = next((r for r in soc_office_rows(G) if _key(r.get("מספר מודעה")) == key), None)
    if not row:
        res["reason"] = "הנכס לא נמצא"
        return res
    allowed = [c.strip() for c in str(env.get("SOCIAL_CHANNELS") or "fb,ig").split(",") if c.strip() in ("fb", "ig")]
    want = [c for c in (channels or allowed) if c in allowed]
    scfg = _cfg_social(G)
    if mode == "publish" and float(scfg.get("paused_until") or 0) > now:
        res["reason"] = "מושהה עד מחר (הגבלת קצב של Meta)"
        return res
    try:
        history = G["_sbdb"].social_recent(REPEAT_DAYS) or []
    except Exception:
        if mode == "publish":
            res["reason"] = "לא ניתן לקרוא את היסטוריית הפרסומים — לא מפרסמים"
            return res
        history = []
    hidden = soc_hidden(G)
    if hidden is None:
        if mode == "publish":
            res["reason"] = "לא ניתן לבדוק הסתרה מהאתר — לא מפרסמים"
            return res
        hidden = set()
    reasons, go = [], []
    for c in want:
        ok, why = soc_can_publish(row, c, history, now, hidden)
        if ok:
            go.append(c)
        else:
            reasons.append(("פייסבוק: " if c == "fb" else "אינסטגרם: ") + why)
    if not go:
        res["reason"] = " · ".join(reasons) or "אין ערוץ פעיל"
        return res
    post = soc_build_post(row, ((G["_load_config"]() or {}).get("v2_office") or {}).get("name", ""),
                          _clean_desc(G), G["_row_feats"], agent=soc_agent_for(G, row), wa_link=_wa_link(env, key))
    if http is None:
        import requests as http
    real, ph = soc_real_images(http, post["images"])   # [01/11] בלי תמונות 'תמונות בקרוב'
    if ph and not real:
        res.update(placeholder=True, reason=PLACEHOLDER_REASON)
        return res
    post["images"] = real
    rec = {"property_key": key, "addr_key": soc_addr_key(row) + "#" + soc_floor(row), "trigger": trigger,
           "mode": mode, "by_phone": str(by_phone or ""), "body": post["body"], "images": post["images"],
           "fb_status": "skipped", "ig_status": "skipped"}
    name, role = _who(G, trigger, by_phone)
    if mode == "preview":
        for c in go:
            rec[c + "_status"] = res[c] = "preview"
        saved = G["_sbdb"].social_insert(rec) or {}
        res.update(ok=True, row_id=saved.get("id", ""), reason=" · ".join(reasons))
        G["_log_activity"](name, role, by_phone or "", "פרסום ברשתות — תצוגה מקדימה", key)
        return res
    token = str(env.get("META_TOKEN") or "").strip()
    if not token:
        res["reason"] = "אין META_TOKEN"
        return res
    base = str(env.get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/")
    toks = [_IMG.put(src, now) for src in post["images"]]   # כבר הורדו ונבדקו למעלה
    if not toks:
        res["reason"] = "אין תמונות"
        return res
    for c in go:
        rec[c + "_status"] = "pending"
    saved = G["_sbdb"].social_insert(rec)
    if not saved or not saved.get("id"):
        res["reason"] = "לא ניתן לרשום את הפרסום — לא מפרסמים"
        return res
    res["row_id"] = rid = saved["id"]
    fb_urls = ["%s/v2/social/img/%s.jpg" % (base, t) for t in toks]
    ig_urls = ["%s/v2/social/img/%s-sq.jpg" % (base, t) for t in toks]
    page_id = str(scfg.get("page_id") or PAGE_ID_DEFAULT)
    errs = []

    def fail(c, e):
        res[c] = rec[c + "_status"] = "unknown" if getattr(e, "unknown", False) else "failed"
        errs.append(("fb: " if c == "fb" else "ig: ") + _scrub(str(e), [token]))
        code = getattr(e, "code", None)
        if code in (190, 102):
            _social_mutate(G, lambda s2: s2.__setitem__("token_bad", True))
            soc_daily_alert(G, "token", "פרסום ברשתות", "החיבור לפייסבוק נותק — צריך טוקן חדש ב-Render", now)
        elif code in _RATE_CODES:
            _social_mutate(G, lambda s2: s2.__setitem__("paused_until", _next_midnight(now)))

    try:
        g = Graph(http, token, env)
        if "fb" in go:
            try:
                rec["fb_post_id"], rec["fb_permalink"] = g.fb_post(page_id, post["body"], fb_urls)
                res["fb"] = rec["fb_status"] = "ok"
            except MetaError as e:
                fail("fb", e)
        if "ig" in go:
            try:
                ig_id = scfg.get("ig_id") or g.page_ig_id(page_id)
                if ig_id and not scfg.get("ig_id"):
                    _social_mutate(G, lambda s2: s2.__setitem__("ig_id", ig_id))
                q = None
                if ig_id:
                    try:
                        q = g.ig_quota(ig_id)
                    except Exception:
                        q = None
                if not ig_id:
                    res["ig"] = rec["ig_status"] = "skipped"
                    reasons.append("אינסטגרם: לא מקושר לעמוד")
                elif q is not None and q <= 0:
                    res["ig"] = rec["ig_status"] = "skipped"
                    reasons.append("אינסטגרם: נגמרה המכסה היומית של Meta")
                else:
                    rec["ig_media_id"], rec["ig_permalink"] = g.ig_post(ig_id, post["ig_caption"], ig_urls)
                    res["ig"] = rec["ig_status"] = "ok"
            except MetaError as e:
                fail("ig", e)
    except Exception as e:   # חריגה לא צפויה — ערוץ שעוד היה בתהליך ייתכן שפורסם: 'unknown', לא 'failed'
        for c in go:
            if rec[c + "_status"] == "pending":
                res[c] = rec[c + "_status"] = "unknown"
        errs.append(_scrub("שגיאה: %s" % e, [token]))
    finally:
        for c in go:
            if rec[c + "_status"] == "pending":
                res[c] = rec[c + "_status"] = "unknown"
        rec["error"] = " | ".join(errs)[:900]
        G["_sbdb"].social_update(rid, {f: rec.get(f) for f in ("fb_status", "ig_status", "fb_post_id", "fb_permalink",
                                                              "ig_media_id", "ig_permalink", "error")})
    res["ok"] = "ok" in (res["fb"], res["ig"])
    if res["ok"] and scfg.get("token_bad"):
        _social_mutate(G, lambda s2: s2.__setitem__("token_bad", False))
    res["reason"] = " · ".join(reasons + errs)
    G["_log_activity"](name, role, by_phone or "",
                       "פרסום ברשתות — " + ("פורסם" if res["ok"] and not errs else "נכשל"),
                       "%s fb:%s ig:%s" % (key, res["fb"], res["ig"]))
    return res


# ── הסבב האוטומטי (לולאה) ────────────────────────────────────────────────────────
def soc_auto_tick(G, now, env=None, sleep=None):
    """סבב אחד: רק כש-SOCIAL_AUTO=1, מצב publish ויש טוקן. הפעלה ראשונה, או חזרה אחרי הפסקה של יותר מיום,
    = זריעת 'ידועים' בלי פרסום (אחרת נכסים מתקופת ההפסקה היו עולים כ'חדשים')."""
    import time as _t
    env = _env(env)
    sleep = sleep or _t.sleep
    if str(env.get("SOCIAL_AUTO") or "0").strip() != "1" or soc_mode(env) != "publish" \
            or not str(env.get("META_TOKEN") or "").strip():
        return {"ran": False}
    rows = soc_office_rows(G)
    scfg = _cfg_social(G)
    gap = now - float(scfg.get("last_tick") or 0)
    if not scfg.get("enabled_at") or gap > 86400:
        seed = soc_seed_known(rows, now)
        if scfg.get("enabled_at"):
            seed["enabled_at"] = scfg["enabled_at"]
        seed["last_tick"] = now
        _social_mutate(G, lambda s: s.update(seed))
        return {"ran": True, "seeded": len(seed["known"]), "reseeded": bool(scfg.get("enabled_at"))}

    def blocked_now(t):
        try:
            return bool(G["_shabbat_quiet_now"]()) or bool(G["_quiet_mode"]()) or _is_night(t)
        except Exception:
            return _is_night(t)

    if float(scfg.get("paused_until") or 0) > now:
        _social_mutate(G, lambda s: s.__setitem__("last_tick", now))
        return {"ran": True, "paused": True}
    try:
        history = G["_sbdb"].social_recent(REPEAT_DAYS) or []
    except Exception:
        return {"ran": True, "skipped": "history"}
    hidden = soc_hidden(G)
    if hidden is None:
        return {"ran": True, "skipped": "hidden"}
    waiting0 = dict(scfg.get("waiting") or {})
    act = soc_active_agents(G, now)

    def allowed(r):
        from goals import g_canon, g_display
        name = _norm(r.get("סוכן 1") or r.get("סוכן"))
        return bool(act) and _real_agent(name) and g_canon(G, g_display(G, name)) in act

    plan = soc_plan_round(rows, scfg, history, now, hidden, blocked_now(now), allowed=allowed)
    _social_mutate(G, lambda s: s.update(known=plan["state"]["known"], waiting=plan["state"]["waiting"], last_tick=now))
    if plan["flood"]:
        soc_daily_alert(G, "flood", "פרסום ברשתות", plan["reason"] + " — לא פורסם", now)
    done = []
    for i, k in enumerate(plan["publish"]):
        if i:
            sleep(GAP_MIN * 60)
            t = _t.time() if now is None else now + i * GAP_MIN * 60
            if blocked_now(t):   # שבת / השתקה / לילה התחילו בזמן ההמתנה — השאר חוזרים להמתנה
                rest = plan["publish"][i:]
                _social_mutate(G, lambda s: s.__setitem__("waiting", dict(s.get("waiting") or {}, **{x: now for x in rest})))
                break
        res = soc_run_one(G, k, "auto", "", env=env)
        done.append(res)
        if (res or {}).get("placeholder"):   # [01/11] חוזר להמתנה עם הזמן המקורי — עד שיעלו תמונות אמיתיות (או שיפוג)
            t0 = float(waiting0.get(k, now))
            _social_mutate(G, lambda s, k=k, t0=t0: s.__setitem__("waiting", dict(s.get("waiting") or {}, **{k: t0})))
    return {"ran": True, "published": plan["publish"], "results": done, "flood": plan["flood"]}


# ── Flask ────────────────────────────────────────────────────────────────────────
_HTTP = None   # requests (נקבע ב-register); בבדיקות מוחלף


def _spawn(fn):
    import threading
    threading.Thread(target=fn, daemon=True, name="social-run").start()


def _last_by_key(history):
    out = {}
    for h in history or []:          # social_recent: החדש קודם
        k = _key(h.get("property_key"))
        if k and h.get("mode") == "publish" and k not in out:
            out[k] = {f: h.get(f) for f in ("created_at", "fb_status", "ig_status", "fb_permalink",
                                            "ig_permalink", "error")}
    return out


def register(app, G):
    import os
    import time as _t
    import threading
    from flask import jsonify, request, Response
    global _HTTP
    if _HTTP is None:
        import requests
        _HTTP = requests

    def dev():
        s = G["_web_auth"]()
        if not s:
            return None, (jsonify({"ok": False, "auth": False}), 401)
        if s.get("drole") != "developer":
            return None, (jsonify({"ok": False, "error": "forbidden"}), 403)
        return s, None

    def can_map(row, history, now, hidden):
        return {c: dict(zip(("ok", "reason"), soc_can_publish(row, c, history, now, hidden))) for c in ("fb", "ig")}

    def hist():
        try:
            return G["_sbdb"].social_recent(REPEAT_DAYS) or []
        except Exception:
            return []

    @app.route("/v2/api/social/publish", methods=["POST"])
    def soc_api_publish():
        s, err = dev()
        if err:
            return err
        j = request.get_json(silent=True) or {}
        key = _key(j.get("key"))
        ch = [c for c in (j.get("channels") or []) if c in ("fb", "ig")] or None
        if not key:
            return jsonify({"ok": False, "error": "key"}), 400
        _spawn(lambda: soc_run_one(G, key, "manual", s.get("phone", ""), channels=ch))
        return jsonify({"ok": True, "queued": True})

    @app.route("/v2/api/social/preview")
    def soc_api_preview():
        s, err = dev()
        if err:
            return err
        key = _key(request.args.get("key"))
        row = next((r for r in soc_office_rows(G) if _key(r.get("מספר מודעה")) == key), None)
        if not row:
            return jsonify({"ok": False, "error": "הנכס לא נמצא"})
        post = soc_build_post(row, ((G["_load_config"]() or {}).get("v2_office") or {}).get("name", ""),
                              _clean_desc(G), G["_row_feats"], agent=soc_agent_for(G, row),
                              wa_link=_wa_link(os.environ, key))
        can = can_map(row, hist(), _t.time(), soc_hidden(G))
        real, ph = soc_real_images(_HTTP, post["images"])   # [01/11] גם בתצוגה המקדימה — בלי 'תמונות בקרוב'
        post["images"] = real
        if ph and not real:
            can = {c: {"ok": False, "reason": PLACEHOLDER_REASON} for c in ("fb", "ig")}
        return jsonify(dict(post, ok=True, key=key, can=can))

    @app.route("/v2/api/social/status")
    def soc_api_status():
        s, err = dev()
        if err:
            return err
        keys = [_key(k) for k in str(request.args.get("keys") or "").split(",") if _key(k)][:200]
        h = hist()
        last = _last_by_key(h)
        rows = {_key(r.get("מספר מודעה")): r for r in soc_office_rows(G)}
        now, hidden = _t.time(), soc_hidden(G)
        items = {}
        for k in keys:
            items[k] = {"last": last.get(k), "can": can_map(rows[k], h, now, hidden) if k in rows else None}
        return jsonify({"ok": True, "mode": soc_mode(os.environ), "items": items})

    @app.route("/v2/api/social/health")
    def soc_api_health():
        s, err = dev()
        if err:
            return err
        token = str(os.environ.get("META_TOKEN") or "").strip()
        scfg = _cfg_social(G)
        out = {"ok": True, "mode": soc_mode(os.environ), "auto": str(os.environ.get("SOCIAL_AUTO") or "0") == "1",
               "connected": False, "page_id": scfg.get("page_id") or PAGE_ID_DEFAULT, "ig_id": scfg.get("ig_id"),
               "paused_until": scfg.get("paused_until"), "recent": hist()[:10]}
        if token:
            g = Graph(_HTTP, token, os.environ)
            try:
                me = g.me()
                out.update(connected=True, account=me.get("name"))
                ig = g.page_ig_id(out["page_id"])
                if ig:
                    out["ig_id"] = ig
                    if ig != scfg.get("ig_id"):
                        _social_mutate(G, lambda s2: s2.__setitem__("ig_id", ig))
                    try:
                        out["ig_quota"] = g.ig_quota(ig)
                    except MetaError:
                        pass
            except MetaError as e:
                out.update(connected=False, error=_scrub(str(e), [token]), token_bad=e.code in (190, 102))
        return jsonify(out)

    @app.route("/v2/social/wa/<key>")
    def soc_wa(key):
        """[02/11] ציבורי: מהקישור בפוסט → וואטסאפ לנייד האישי של הסוכן, עם הודעה מוכנה על הנכס ועל המקור."""
        from flask import redirect
        from urllib.parse import quote
        k = _key(key)
        src = "ig" if request.args.get("s") == "ig" else "fb"
        row = next((r for r in soc_office_rows(G) if _key(r.get("מספר מודעה")) == k), None) if k else None
        ag = soc_agent_for(G, row) if row else {}
        d = re.sub(r"\D", "", str(ag.get("phone") or ""))
        local = ("0" + d[3:]) if d.startswith("972") else d
        if not row or not (len(local) == 10 and local.startswith("05")) or not _real_agent(ag.get("name")):
            html = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                    "<p dir=rtl style='font-family:sans-serif;font-size:18px;margin:40px 16px'>"
                    "המודעה או הסוכן כבר לא זמינים. אפשר לשלוח הודעה לעמוד.</p>")
            return html, 404, {"Content-Type": "text/html; charset=utf-8", "X-Robots-Tag": "noindex"}
        office = ((G["_load_config"]() or {}).get("v2_office") or {}).get("name", "")
        text = soc_wa_text(row, ag["name"], office, src)
        try:
            G["_log_activity"]("פונה מהרשתות", "public", "", "פרסום ברשתות — פנייה בוואטסאפ",
                               "%s · %s · %s" % (k, "אינסטגרם" if src == "ig" else "פייסבוק", ag["name"]))
        except Exception:
            pass
        r = redirect("https://wa.me/972%s?text=%s" % (local[1:], quote(text)), 302)
        r.headers["X-Robots-Tag"] = "noindex"
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.route("/v2/social/img/<name>")
    def soc_img(name):
        m = re.fullmatch(r"([A-Za-z0-9_-]+?)(-sq)?\.jpg", str(name or ""))
        src = _IMG.get(m.group(1), _t.time()) if m else None
        data = soc_fetch_jpeg(_HTTP, src, bool(m.group(2))) if src else None
        if not data:
            return Response("not found", status=404)
        return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    thr = {"t": None, "pid": 0}
    lock = threading.Lock()

    def loop():
        _t.sleep(120)
        while True:
            try:
                soc_auto_tick(G, _t.time())
            except Exception as e:
                lg = G.get("log")
                if lg:
                    lg.error("social auto: %s" % _scrub(str(e), [os.environ.get("META_TOKEN", "")]))
            _t.sleep(LOOP_SEC)

    @app.before_request
    def _social_kick():
        t = thr["t"]
        if t is not None and t.is_alive() and thr["pid"] == os.getpid():
            return
        with lock:
            t = thr["t"]
            if t is not None and t.is_alive() and thr["pid"] == os.getpid():
                return
            thr["t"] = threading.Thread(target=loop, daemon=True, name="social-auto")
            thr["t"].start()
            thr["pid"] = os.getpid()


# ── ריבוע בלוח הבקרה ─────────────────────────────────────────────────────────────
def social_health_tile(G, now, env=None):
    """{'key','label','status','last'} — none: לא מוגדר; bad: הטוקן נדחה; warn: כשל היום; ok אחרת."""
    env = _env(env)
    base = {"key": "social", "label": "פרסום ברשתות"}
    if soc_mode(env) == "off" or not str(env.get("META_TOKEN") or "").strip():
        return dict(base, status="none", last=None)
    if _cfg_social(G).get("token_bad"):
        return dict(base, status="bad", last=None)
    try:
        hist = [h for h in (G["_sbdb"].social_recent(REPEAT_DAYS) or []) if h.get("mode") == "publish"]
    except Exception:
        hist = []
    last = hist[0].get("created_at") if hist else None
    today = [h for h in hist if _ts(h.get("created_at")) and _day(_ts(h.get("created_at"))) == _day(now)]
    bad = any(h.get(c + "_status") in ("failed", "unknown") for h in today for c in ("fb", "ig"))
    return dict(base, status="warn" if bad else "ok", last=last)
