# kit_core.py — ליבה טהורה של תיק הפרזנטציה (בלי רשת, בלי DB, בלי AI)
import re
import datetime as _dt

APPROVE_H = 48
MIN_BUYERS = 3
BUYER_MIN = 60
_VIEW_GAP = 1800
_VIEW_CAP = 4 * 3600
_DAYS = ["ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳", "א׳"]  # Monday=0 → ב׳ ... Sunday=6 → א׳


def phone9(v):
    d = re.sub(r"\D", "", str(v or ""))
    return d[-9:] if len(d) >= 9 else ""


def wa972(v):
    p = phone9(v)
    return "972" + p if p else ""


def street_only(street):
    """שם הרחוב בלי מספר בית (אותו כלל כמו social_publish.soc_scrub_house)."""
    t = str(street or "").strip()
    t = re.sub(r"\s*(?:מס['׳]?\s*)?\d+[א-ת]?(?:/\d+)?\s*$", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _ts(v):
    try:
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace("Z", "+00:00")
        d = _dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=_dt.timezone.utc)
        return d.timestamp()
    except Exception:
        return None


def eff_status(rec, now):
    st = (rec or {}).get("status") or ""
    if st == "pending":
        t = _ts(rec.get("sent_review_at"))
        if t is not None and now - t > APPROVE_H * 3600:
            return "expired"
    return st


def decide(rec, action, who, now):
    st = eff_status(rec, now)
    if st == "expired":
        return None, "פג תוקף"
    if st in ("approved", "sent"):
        return None, "כבר אושר"
    if st == "rejected":
        return None, "כבר נדחה"
    if st != "pending":
        return None, "פג תוקף"
    if action == "approve":
        return "approved", "אושר"
    if action == "reject":
        return "rejected", "נדחה"
    return None, "פג תוקף"


def owner_message(snap):
    s = snap or {}
    head = "שלום %s, כאן %s מ%s." % (s.get("owner_first") or "", s.get("agent") or "", s.get("office") or "")
    meet = ""
    m = str(s.get("meet_at") or "")
    if m:
        try:
            d = _dt.datetime.fromisoformat(m)
            meet = " לקראת הפגישה שלנו ביום %s %s בשעה %s" % (_DAYS[d.weekday()], d.strftime("%d/%m"), d.strftime("%H:%M"))
        except Exception:
            meet = ""
    body = "הכנתי לך תיק אישי על הנכס שלך ב%s." % (s.get("street") or "")
    if meet:
        return "%s%s %s אשמח שתעיף מבט לפני שנפגש." % (head, meet, body)
    return "%s %s אשמח שתעיף מבט לפני שנפגש." % (head, body)


def file_name(snap):
    return "תיק אישי - %s.pdf" % ((snap or {}).get("owner") or "").strip()


def view_add(views, now, step=15):
    v = dict(views or {})
    first = v.get("first") or now
    last = v.get("last")
    opens = int(v.get("opens") or 0)
    secs = int(v.get("secs") or 0)
    if last is None or now - last > _VIEW_GAP:
        opens += 1
    secs = min(secs + step, _VIEW_CAP)
    return {"first": first, "last": now, "opens": opens, "secs": secs}


def manual_validate(form):
    f = form or {}
    if not str(f.get("owner") or "").strip():
        return "owner"
    if not phone9(f.get("phone")):
        return "phone"
    if not str(f.get("addr") or "").strip():
        return "addr"
    if not str(f.get("rooms") or "").strip():
        return "rooms"
    if not str(f.get("price") or "").strip():
        return "price"
    return None
