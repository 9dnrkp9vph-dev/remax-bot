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
