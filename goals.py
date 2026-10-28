"""goals.py — 'היעדים שלי להיום': ספירה טהורה ויעדים לכל סוכן (אייל 28/10).

מודול טהור — בלי Flask ובלי גישה לרשת. כל מקור נתונים מגיע מוכן (או החריגה שנזרקה בשליפתו), והפונקציה
`canon` (איחוד כתיבי שמות) מוזרקת מבחוץ. 'היום' = יום קלנדרי בשעון ישראל, חצות עד חצות.
מקור שנכשל → היעד שלו None (מוצג '—'), ושאר היעדים נספרים כרגיל.
"""
from __future__ import annotations
import datetime as _dt
import re

try:
    from zoneinfo import ZoneInfo
    _IL = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover
    _IL = _dt.timezone(_dt.timedelta(hours=2))

DEFAULTS = {"meetings": 2, "buyers": 3, "past_clients": 5, "reviews": 2}
ACT_REMIND = "תזכורת ללקוח עבר"
ACT_REVIEW_MANUAL = "בקשת ביקורת — ידני"
ACT_BPAGE = "דף קונה — שליחה"
_MAX_TARGET = 50
_SUM_KEYS = ("meetings", "buyers", "bpage", "past_clients", "reviews", "missed")


def day_bounds(day):
    """(התחלה, סוף) באפוק של יום ישראלי."""
    s = _dt.datetime(day.year, day.month, day.day, tzinfo=_IL)
    e = _dt.datetime.combine(day + _dt.timedelta(days=1), _dt.time(), tzinfo=_IL)
    return s.timestamp(), e.timestamp()


def parse_ts(s):
    """אפוק / DD/MM/YYYY[ HH:MM] / ISO (עם או בלי אזור; בלי אזור = שעון ישראל) → אפוק או None."""
    if s is None or isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        v = float(s)
        return v / 1000.0 if v > 1e11 else v
    t = str(s).strip()
    if not t:
        return None
    if re.fullmatch(r"\d{9,13}(\.\d+)?", t):
        v = float(t)
        return v / 1000.0 if v > 1e11 else v
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?:[ T,]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", t)
    try:
        if m:
            d, mo, y, hh, mi, ss = m.groups()
            dt = _dt.datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0), tzinfo=_IL)
            return dt.timestamp()
        iso = t.replace("Z", "+00:00").replace("z", "+00:00")
        dt = _dt.datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_IL)
        return dt.timestamp()
    except Exception:
        return None


def _clip(v):
    if isinstance(v, bool):
        return None
    try:
        n = int(float(str(v).strip())) if not isinstance(v, (int, float)) else int(v)
    except Exception:
        return None
    return max(0, min(_MAX_TARGET, n))


def targets_for(cfg, agent, canon):
    """ברירות מחדל ← cfg['v2_goals']['default'] ← cfg['v2_goals']['agents'][canon(agent)]."""
    out = dict(DEFAULTS)
    gl = (cfg or {}).get("v2_goals") or {}
    if not isinstance(gl, dict):
        return out

    def apply(d):
        if not isinstance(d, dict):
            return
        for k in DEFAULTS:
            if k in d:
                n = _clip(d[k])
                if n is not None:
                    out[k] = n
    apply(gl.get("default"))
    agents = gl.get("agents") or {}
    if isinstance(agents, dict):
        want = canon(agent)
        if want in agents:
            apply(agents[want])
        else:
            for k, v in agents.items():
                if canon(k) == want:
                    apply(v)
                    break
    return out


def _bad(v):
    return v is None or isinstance(v, BaseException)


def _same(a, b, canon):
    return bool(a) and canon(a) == canon(b)


def _in(ts, bounds):
    return ts is not None and bounds[0] <= ts < bounds[1]


def _date_is_today(s, today):
    t = str(s or "").strip()[:10]
    if not t:
        return False
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", t):
            return _dt.date.fromisoformat(t) == today
        m = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", t)
        if m:
            return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) == today
    except Exception:
        pass
    return False


def count_agent(agent, bounds, src, canon):
    nb = src.get("nb"); buyers = src.get("buyers"); bpages = src.get("bpages")
    activity = src.get("activity"); reviews = src.get("reviews"); missed = src.get("missed")
    today = _dt.datetime.fromtimestamp(bounds[0], _IL).date()
    out = {"meetings": None, "buyers": None, "bpage": None, "past_clients": None,
           "reviews": None, "followups": None, "missed": None}

    if not _bad(nb):
        mt = 0; fdue = 0; fdone = 0
        for key, rec in (nb or {}).items():
            if not isinstance(rec, dict) or not _same(rec.get("agent"), agent, canon):
                continue
            pk = str(rec.get("pkey") or "")
            if _in(parse_ts(rec.get("meeting_at")), bounds) and not pk.startswith("manual:") \
                    and not str(key).startswith("manual:"):
                mt += 1
            if rec.get("status") == "followup" and _date_is_today(rec.get("date"), today):
                fdue += 1
                if rec.get("done"):
                    fdone += 1
        out["meetings"] = mt
        out["followups"] = {"due": fdue, "done": fdone}

    if not _bad(buyers):
        rows = set()
        n = 0
        for b in buyers or []:
            if _same(b.get("agent"), agent, canon) and _in(parse_ts(b.get("date")), bounds):
                n += 1
                rows.add(b.get("row"))
        out["buyers"] = n
        if not _bad(bpages):
            sent = set()
            for p in bpages or []:
                if p.get("row") in rows and _in(parse_ts(p.get("last_sent_at")), bounds):
                    sent.add(p.get("row"))
            out["bpage"] = len(sent)

    if not _bad(activity):
        phones = set()
        for a in activity or []:
            if a.get("action") == ACT_REMIND and _same(a.get("name"), agent, canon):
                phones.add(str(a.get("detail") or "").strip())
        out["past_clients"] = len(phones)

    if not _bad(reviews):
        n = 0
        for r in reviews or []:
            ag = r.get("agents") or []
            if ag and _same(ag[0], agent, canon) and _in(parse_ts(r.get("at")), bounds):
                n += 1
        out["reviews"] = n

    if not _bad(missed):
        out["missed"] = sum(1 for m in (missed or []) if _same(m.get("agent"), agent, canon))
    return out


def rollup(per_agent, targets):
    """סכום היעדים והספירות; None = חסר (מסכמים את הידועים ו-partial=True)."""
    counts = {}
    partial = False
    for k in _SUM_KEYS:
        vals = [c.get(k) for c in per_agent.values()]
        known = [v for v in vals if v is not None]
        if len(known) != len(vals):
            partial = True
        counts[k] = sum(known) if known else None
    fv = [c.get("followups") for c in per_agent.values()]
    fk = [f for f in fv if f is not None]
    if len(fk) != len(fv):
        partial = True
    counts["followups"] = {"due": sum(f["due"] for f in fk), "done": sum(f["done"] for f in fk)} if fk else None
    tsum = {k: sum((t or {}).get(k, 0) for t in targets.values()) for k in DEFAULTS}
    return {"counts": counts, "targets": tsum, "partial": partial}


def meeting_stamp(prev, new_status, now):
    """חותמת 'מתי נקבעה הפגישה' — קבועה לתמיד: קיימת נשמרת; אחרת now אם הסטטוס meeting; אחרת None."""
    ex = (prev or {}).get("meeting_at")
    if ex:
        return ex
    return now if new_status == "meeting" else None
