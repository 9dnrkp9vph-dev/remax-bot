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
    out = {"meetings": None, "meetings_by": [], "meetings_coord": [], "buyers_sign": None, "buyers_sign_by": [], "gius": None, "gius_by": [],
           "deals_new": None, "deals_new_by": [], "open_now": None, "closed": None, "closed_by": [], "closed_month": None,
           "excl_now": None if _bad(excl_now) else int(excl_now)}

    if not _bad(nb_status):
        # [02/11 אייל+מתן, 'פגישות / מי תיאם' שגוי] לפי הסוכן שהפגישה שלו; מי שתיאם לסוכן אחר — בשורה נפרדת
        by, coord = _Counter(), _Counter()
        for rec in (nb_status or {}).values():
            if isinstance(rec, dict) and rec.get("status") == "meeting" and _in(parse_ts(rec.get("meeting_at")), b):
                ag = nm(rec.get("agent") or rec.get("by"))
                by[ag] += 1
                cb = nm(rec.get("by")) if str(rec.get("by") or "").strip() else ag
                if cb != ag:
                    coord[cb] += 1
        out["meetings"], out["meetings_by"], out["meetings_coord"] = sum(by.values()), _top(by), _top(coord)

    if not _bad(sigs):
        sby = _Counter()
        seen = set()
        for g in sigs or []:
            if not _in(parse_ts(g.get("ts")), b):
                continue
            if g.get("type") == "קונים":
                if g.get("signed"):              # רק מה שנחתם (ts = שעת החתימה) — אייל 01/11
                    sby[nm(g.get("agent"))] += 1
            elif g.get("type") == "בלעדיות" and g.get("signed") and "בדיקה בדיקה" not in str(g.get("address") or ""):
                seen.add((nm(g.get("agent")), _anchor(g.get("address"))))
        out["buyers_sign"], out["buyers_sign_by"] = sum(sby.values()), _top(sby)
        gby = _Counter(a for a, _ in seen)
        out["gius"], out["gius_by"] = sum(gby.values()), _top(gby)

    if not _bad(deals):
        # [02/11 מתן: 'תהליכים לא טוב · בן קדוש 2 · רויטל 3', 'עסקאות שנחתמו — אלי ויהודית 1'] תהליך/עסקה משותפים
        # נזקפים לכל אחד מהסוכנים שבהם (לא רק לראשון); המספר הכולל = מספר התהליכים / העסקאות
        def who(it):
            names = [nm(a) for a in (it.get("agents") or []) if str(a or "").strip()] or [nm(it.get("by"))]
            return list(dict.fromkeys(names))
        new, closed = _Counter(), _Counter()
        open_now = closed_month = n_new = n_closed = 0
        m0 = day_bounds(day.replace(day=1))[0]          # מתחילת החודש עד סוף היום
        for it in deals or []:
            if not isinstance(it, dict):
                continue
            if not it.get("deal"):
                open_now += 1
            c = parse_ts(it.get("created")) if it.get("created") else parse_ts(it.get("ts"))
            if _in(c, b):
                n_new += 1
                for a in who(it):
                    new[a] += 1
            if it.get("deal"):
                cts = parse_ts(it.get("close_date"))
                if _in(cts, b):
                    n_closed += 1
                    for a in who(it):
                        closed[a] += 1
                if _in(cts, (m0, b[1])):
                    closed_month += 1
        out.update(deals_new=n_new, deals_new_by=_top(new), open_now=open_now,
                   closed=n_closed, closed_by=_top(closed), closed_month=closed_month)
    return out


def _v(x):
    return "—" if x is None else str(x)


def _who(pairs):
    return (" (" + ", ".join("%s %d" % (a, k) for a, k in pairs) + ")") if pairs else ""


def day_wa_text(c, day_str, office=""):
    """[01/11 אייל, 'אני רוצה אותו ככה'] כותרת, תאריך, מדדי היום, ואז הסיכומים. שורה לכל מדד — נקרא גם כשתבנית
    family_update מאחדת את השורות לשורה אחת. office נשאר בחתימה לתאימות, לא מוצג."""
    return "\n".join([
        "דוח סיכום יום",
        day_str,
        "",
        "פגישות שתואמו היום: %s%s" % (_v(c["meetings"]), _who(c["meetings_by"])),
    ] + (["מתוכן תיאמו לסוכנים: " + ", ".join("%s %d" % (a, k) for a, k in c["meetings_coord"])]
         if c.get("meetings_coord") else []) + [
        "גיוסים היום: %s%s" % (_v(c["gius"]), _who(c["gius_by"])),
        "החתמות קונים היום: %s%s" % (_v(c["buyers_sign"]), _who(c["buyers_sign_by"])),
        "תהליכים חדשים היום: %s%s" % (_v(c["deals_new"]), _who(c["deals_new_by"])),
        "עסקאות שנחתמו היום: %s%s" % (_v(c["closed"]), _who(c["closed_by"])),
        "",
        "סה\"כ תהליכים פתוחים: %s" % _v(c["open_now"]),
        "סה\"כ נכסים בבלעדיות: %s" % _v(c["excl_now"]),
        "סה\"כ עסקאות שנסגרו החודש: %s" % _v(c.get("closed_month")),
    ])


def day_wa_due(now, rec, quiet, hour, now_ts=None):
    """פעם ביום מ-hour ואילך; לא בשבת ולא בחלון שבת/חג; כשל → ניסיון חוזר כל 15 דק', עד 8."""
    now_ts = _t.time() if now_ts is None else now_ts
    rec = rec or {}
    if now.hour < hour or now.weekday() == WEEKEND_DAY or quiet or rec.get("ok"):
        return False
    return int(rec.get("tries") or 0) < 8 and (now_ts - float(rec.get("ts") or 0)) >= 900
