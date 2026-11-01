# day_wa.py — [DAY-WA 01/11 אייל] דוח ערב בוואטסאפ לבעל המשרד, כל יום ב-21:00:
# 'כמה פגישות תואמו מהבוקר ועל ידי מי, החתמות קונים, תהליכים חדשים (סה"כ פתוחים), כמות נכסים בבלעדיות עדכני,
# כמה גיוסים מהבוקר ומי גייס, וכמות עסקאות מהבוקר'. פונקציות טהורות; השליפה והשליחה ב-app.py (_day_wa_tick).
# 'מהבוקר' = היום הקלנדרי בשעון ישראל. מקור שנכשל (None / חריגה) → '—' בשורה שלו, בלי להפיל את השאר.
from collections import Counter as _Counter
import time as _t

from goals import _IL, _anchor, day_bounds, parse_ts

WEEKEND_DAY = 5   # שבת (datetime.weekday)


def _bad(v):
    return v is None or isinstance(v, Exception)


def _top(cnt):
    """Counter → [(שם, מספר)] מהגדול לקטן, ואז לפי שם."""
    return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))


def _in(ts, b):
    return ts is not None and b[0] <= ts < b[1]


def day_wa_counts(day, nb_status, sigs, deals, excl_now, canon):
    """nb_status = cfg['nbStatus'] (פגישות: status='meeting' + meeting_at = מתי נקבעה; 'by' = מי תיאם);
    sigs = [{agent, address, type, signed, ts}] (goals.g_sigs); deals = _deals_load(); excl_now = נכסי משרד בבלעדיות."""
    b = day_bounds(day)
    nm = lambda s: canon(str(s or "").strip()) or "—"
    out = {"meetings": None, "meetings_by": [], "buyers_sign": None, "buyers_signed": None, "gius": None, "gius_by": [],
           "deals_new": None, "deals_new_by": [], "open_now": None, "closed": None, "closed_by": [],
           "excl_now": None if _bad(excl_now) else int(excl_now)}

    if not _bad(nb_status):
        by = _Counter()
        for rec in (nb_status or {}).values():
            if isinstance(rec, dict) and rec.get("status") == "meeting" and _in(parse_ts(rec.get("meeting_at")), b):
                by[nm(rec.get("by") or rec.get("agent"))] += 1
        out["meetings"], out["meetings_by"] = sum(by.values()), _top(by)

    if not _bad(sigs):
        n = signed = 0
        seen = set()
        for g in sigs or []:
            if not _in(parse_ts(g.get("ts")), b):
                continue
            if g.get("type") == "קונים":
                n += 1
                signed += 1 if g.get("signed") else 0
            elif g.get("type") == "בלעדיות" and g.get("signed") and "בדיקה בדיקה" not in str(g.get("address") or ""):
                seen.add((nm(g.get("agent")), _anchor(g.get("address"))))
        out["buyers_sign"], out["buyers_signed"] = n, signed
        gby = _Counter(a for a, _ in seen)
        out["gius"], out["gius_by"] = sum(gby.values()), _top(gby)

    if not _bad(deals):
        first = lambda it: nm((it.get("agents") or [it.get("by")])[0])
        new, closed = _Counter(), _Counter()
        open_now = 0
        for it in deals or []:
            if not isinstance(it, dict):
                continue
            if not it.get("deal"):
                open_now += 1
            c = parse_ts(it.get("created")) if it.get("created") else parse_ts(it.get("ts"))
            if _in(c, b):
                new[first(it)] += 1
            if it.get("deal") and _in(parse_ts(it.get("close_date")), b):
                closed[first(it)] += 1
        out.update(deals_new=sum(new.values()), deals_new_by=_top(new), open_now=open_now,
                   closed=sum(closed.values()), closed_by=_top(closed))
    return out


def _v(x):
    return "—" if x is None else str(x)


def _who(pairs):
    return (" (" + ", ".join("%s %d" % (a, k) for a, k in pairs) + ")") if pairs else ""


def day_wa_text(c, day_str, office):
    """שורה לכל מדד — נקרא גם כשתבנית family_update מאחדת את השורות לשורה אחת."""
    head = "דוח ערב · %s" % day_str + (" · %s" % office if office else "")
    sign = _v(c["buyers_sign"]) + ((" (נחתמו %d)" % c["buyers_signed"]) if c["buyers_sign"] else "")
    lines = [head, "",
             "פגישות שתואמו: %s%s" % (_v(c["meetings"]), _who(c["meetings_by"])),
             "החתמות קונים: %s" % sign,
             "תהליכים חדשים: %s%s · סה\"כ פתוחים: %s" % (_v(c["deals_new"]), _who(c["deals_new_by"]), _v(c["open_now"])),
             "נכסים בבלעדיות: %s" % _v(c["excl_now"]),
             "גיוסים: %s%s" % (_v(c["gius"]), _who(c["gius_by"])),
             "עסקאות שנסגרו: %s%s" % (_v(c["closed"]), _who(c["closed_by"]))]
    return "\n".join(lines)


def day_wa_due(now, rec, quiet, hour, now_ts=None):
    """פעם ביום מ-hour ואילך; לא בשבת ולא בחלון שבת/חג; כשל → ניסיון חוזר כל 15 דק', עד 8."""
    now_ts = _t.time() if now_ts is None else now_ts
    rec = rec or {}
    if now.hour < hour or now.weekday() == WEEKEND_DAY or quiet or rec.get("ok"):
        return False
    return int(rec.get("tries") or 0) < 8 and (now_ts - float(rec.get("ts") or 0)) >= 900
