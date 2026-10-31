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


def soc_build_post(row, office_name, clean_desc, feats):
    """שורת נכס → {'body', 'ig_caption', 'images'}. בלי מספר בית, טלפון, שם סוכן או קישור."""
    rent = "שכר" in str(row.get("סוג עסקה") or "")
    rooms = _num(row.get("חדרים"))
    kind = _norm(row.get("סוג נכס"))
    nb, city = _norm(row.get("שכונה")), _norm(row.get("עיר / ישוב"))
    where = ", ".join(x for x in (nb, city) if x)
    what = " ".join(x for x in ((kind if kind and kind != "דירה" else ""),
                                 (rooms + " חדרים" if rooms and rooms != "0" else "")) if x) or (kind or "נכס")
    lines = [("🏡 " + ("להשכרה" if rent else "למכירה") + " · " + what + ((" ב" + where) if where else ""))]
    street = _norm(row.get("כתובת"))
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
    desc = _cut(re.sub(r"\s+\n", "\n", desc), DESC_MAX)
    parts = ["\n".join(lines)]
    if desc:
        parts.append(desc)
    parts.append(str(office_name or "").strip() + "\nלפרטים — הודעה לעמוד")
    body = "\n\n".join(p for p in parts if p.strip())
    tags = ["#נדלן", "#דירותלהשכרה" if rent else "#דירותלמכירה"]
    if city:
        tags.append("#" + city.replace(" ", "").replace("-", ""))
    tags.append("#רימקספמילי")
    return {"body": body, "ig_caption": body + "\n\n" + " ".join(tags), "images": soc_images(row)}


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
        if st not in ("ok", "unknown"):
            continue
        t = _ts(h.get("created_at"))
        if t is None or now - t >= REPEAT_DAYS * 86400:
            continue
        if _key(h.get("property_key")) != key and not _same_apartment(akey, afl, h.get("addr_key")):
            continue
        if st == "unknown" and _day(t) == _day(now):
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


def soc_plan_round(rows, state, history, now, hidden, blocked):
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
    for k in [k for k, t in st["waiting"].items() if now - float(t) > WAIT_DAYS * 86400 or k not in by_key]:
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
        fg = im.copy()
        fg.thumbnail((S, S))
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


def soc_fetch_jpeg(http, src_url, square):
    """הורדה מהמקור והמרה ל-JPEG; כל כשל → None (התמונה מדולגת)."""
    try:
        r = http.get(src_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if getattr(r, "status_code", 0) >= 400:
            return None
        return soc_jpeg(getattr(r, "content", b""), square)
    except Exception:
        return None
