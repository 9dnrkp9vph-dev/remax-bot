"""goals.py — 'היעדים שלי להיום': ספירה טהורה ויעדים לכל סוכן (אייל 28/10).

מודול טהור — בלי Flask ובלי גישה לרשת. כל מקור נתונים מגיע מוכן (או החריגה שנזרקה בשליפתו), והפונקציה
`canon` (איחוד כתיבי שמות) מוזרקת מבחוץ. 'היום' = יום קלנדרי בשעון ישראל, חצות עד חצות.
מקור שנכשל → היעד שלו None (מוצג '—'), ושאר היעדים נספרים כרגיל.
"""
from __future__ import annotations
import datetime as _dt
import re
import threading as _threading
import time as _tm

try:
    from zoneinfo import ZoneInfo
    _IL = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover
    _IL = _dt.timezone(_dt.timedelta(hours=2))

DEFAULTS = {"listings": 2, "meetings": 2, "nb_wa": 10, "buyers": 3, "past_clients": 5, "reviews": 2}
WEEKLY_GOALS = ("listings",)            # [GOALS2 29/10, אייל] גיוס נכסים — יעד שבועי (2 בשבוע), לא יומי
ACT_NB_WA = "📲 וואטסאפ — נכס נולד"      # [GOALS2 29/10] פניות לנכס נולד (אייל: כמות הוואטסאפים שנשלחו)
ACTIVE_DAYS = 10                        # יעד המשרד = הסוכנים שנכנסו לאפי ב-10 הימים האחרונים (אייל 29/10)
ACT_REMIND = "תזכורת ללקוח עבר"
ACT_REVIEW_MANUAL = "בקשת ביקורת — ידני"
ACT_BPAGE = "דף קונה — שליחה"
_MAX_TARGET = 50
_SUM_KEYS = ("listings", "meetings", "nb_wa", "buyers", "buyers_sign", "bpage", "past_clients", "reviews", "missed")
SRC_TTL = 60


def _clock():
    """שעון — נקודת החלפה לבדיקות."""
    return _tm.time()


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


def _anchor(a):
    """עוגן-כתובת (כמו ef_addr_anchor): עד וכולל המספר הראשון — אותו נכס בכתיב שונה = אחד."""
    k = re.sub(r"[^א-ת0-9a-z]", "", str(a or "").lower().replace("קריית", "קרית"))
    m = re.match(r"^(\D*?\d+)", k)
    return m.group(1) if m else k


def count_listings(agent, bounds, sigs, canon):
    """[GOALS2 29/10] גיוס נכסים = הסכמי בלעדיות שנחתמו בתקופה, נכס ייחודי (עוגן-כתובת) — הכלל של 'שאל את אפי'
    (ef_gius). sigs = [{agent, address, type, signed, ts}]. None = המקור לא זמין."""
    if _bad(sigs):
        return None
    seen = set()
    for g in sigs or []:
        if g.get("type") != "בלעדיות" or not g.get("signed") or "בדיקה בדיקה" in str(g.get("address") or ""):
            continue
        if _same(g.get("agent"), agent, canon) and _in(parse_ts(g.get("ts")), bounds):
            seen.add(_anchor(g.get("address")))
    return len(seen)


def week_bounds(day):
    """מתחילת השבוע (ראשון) עד סוף `day` — ליעד השבועי."""
    s = day - _dt.timedelta(days=(day.weekday() + 1) % 7)
    return day_bounds(s)[0], day_bounds(day)[1]


def count_agent(agent, bounds, src, canon):
    nb = src.get("nb"); buyers = src.get("buyers"); bpages = src.get("bpages")
    activity = src.get("activity"); reviews = src.get("reviews"); missed = src.get("missed")
    today = _dt.datetime.fromtimestamp(bounds[0], _IL).date()
    out = {"listings": None, "meetings": None, "nb_wa": None, "buyers": None, "buyers_sign": None, "bpage": None,
           "past_clients": None, "reviews": None, "followups": None, "missed": None}

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
        n = sign = 0
        for b in buyers or []:
            if _same(b.get("agent"), agent, canon) and _in(parse_ts(b.get("date")), bounds):
                n += 1
                if str(b.get("summary") or "").strip().startswith("מהחתמת"):
                    sign += 1                   # נכנס אוטומטית מהחתמת מתעניין — כלול בסך הקונים
                if b.get("row") is not None:
                    rows.add(b.get("row"))
        out["buyers"] = n
        out["buyers_sign"] = sign
        if not _bad(bpages):
            sent = set()
            for p in bpages or []:
                if p.get("row") is not None and p.get("row") in rows and _in(parse_ts(p.get("last_sent_at")), bounds):
                    sent.add(p.get("row"))
            out["bpage"] = len(sent)

    if not _bad(activity):
        phones, nbw = set(), set()
        for a in activity or []:
            act = str(a.get("action") or "")
            if not _same(a.get("name"), agent, canon):
                continue
            if act == ACT_REMIND:
                phones.add(str(a.get("detail") or "").strip())
            elif act.startswith(ACT_NB_WA):
                ts = parse_ts(a.get("ts"))
                if _in(ts, bounds):             # אותה מודעה פעמיים באותו יום = פנייה אחת
                    d = _dt.datetime.fromtimestamp(ts, _IL).date().isoformat()
                    nbw.add((d, str(a.get("detail") or "").strip()))
        out["past_clients"] = len(phones)
        out["nb_wa"] = len(nbw)

    if not _bad(reviews):
        n = 0
        for r in reviews or []:
            ag = r.get("agents") or []
            if ag and _same(ag[0], agent, canon) and _in(parse_ts(r.get("at")), bounds):
                n += 1
        out["reviews"] = n

    if not _bad(missed):
        out["missed"] = sum(1 for m in (missed or []) if _same(m.get("agent"), agent, canon))
    out["listings"] = count_listings(agent, week_bounds(today), src.get("sigs"), canon)   # תמיד מתחילת השבוע
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
    return {"counts": counts, "targets": tsum, "partial": partial, "agents": len(targets)}


def _roster_names(src, canon):
    """(שמות ייחודיים לפי canon, האם הרשימה נכשלה)."""
    roster = src.get("roster")
    if _bad(roster):
        return [], True
    names, done = [], set()
    for name in roster or []:
        if name and canon(name) not in done:
            done.add(canon(name))
            names.append(name)
    return names, False


def _seen_set(src, canon):
    seen_src = src.get("seen")
    return set() if _bad(seen_src) else {canon(n) for n in (seen_src or []) if n}


def _cfg_of(src):
    cfg = src.get("cfg")
    return cfg if isinstance(cfg, dict) else {}


def _active_set(src, canon):
    """[GOALS2 29/10] מי שנכנס לאפי ב-ACTIVE_DAYS הימים האחרונים. None = לא ידוע (אין מקור / נכשל) → כולם."""
    a = src.get("active")
    if a is None or _bad(a):
        return None
    return {canon(n) for n in a if n}


def _did_any(c):
    return any(isinstance(v, (int, float)) and v > 0 for k, v in (c or {}).items() if k != "missed")


def _assemble(src, canon, count, targets):
    """הליבה המשותפת ל-build_office וללוח הבקרה: שורה לכל סוכן ברשימה + סכום המשרד.
    count(name) → ספירות, targets(name) → יעדים. רשימה שנכשלה → בלי שורות, partial=True.
    [GOALS2 29/10, אייל] יעד המשרד = סכום היעדים של מי שנכנס לאפי ב-10 הימים האחרונים (src['active']).
    מי שלא נכנס ולא עשה כלום — לא מוצג; מי שלא נכנס אבל נספר לו משהו (למשל קונה מהחתמה) — מוצג ונספר
    בסכום, בלי יעד."""
    names, roster_bad = _roster_names(src, canon)
    seen = _seen_set(src, canon)
    active = _active_set(src, canon)
    rows, per, tg = [], {}, {}
    for name in names:
        k = canon(name)
        c, t = count(name), targets(name)
        is_active = active is None or k in active
        if not is_active and not _did_any(c):
            continue
        rows.append({"name": name, "counts": c, "targets": t, "seen_today": k in seen, "active": is_active})
        per[k] = c
        if is_active:
            tg[k] = t
    total = rollup(per, tg)
    if roster_bad:
        total["partial"] = True
    return rows, per, tg, total


def build_office(src, day, canon):
    """שורה לכל סוכן ברשימה (src['roster']) + סכום. src['cfg'] = הקונפיג (ליעדים), src['seen'] = מי נכנס היום.
    רשימה שנכשלה בשליפה → בלי שורות, partial=True."""
    bounds = day_bounds(day)
    cfg = _cfg_of(src)
    rows, _, _, total = _assemble(src, canon, lambda n: count_agent(n, bounds, src, canon),
                                  lambda n: targets_for(cfg, n, canon))
    return {"rows": rows, "total": total}


# ── לוח הבקרה ב-CRM: היום / אתמול / השבוע, מול אותה תקופה לפני שבוע ─────────────────────
GOAL_KEYS = tuple(DEFAULTS)


def week_start(day):
    """יום ראשון של השבוע (שבוע ישראלי)."""
    return day - _dt.timedelta(days=(day.weekday() + 1) % 7)


def workday_weight(day):
    """א'–ה' = 1, שישי = חצי, שבת = 0."""
    return {4: 0.5, 5: 0.0}.get(day.weekday(), 1.0)


def workdays_elapsed(day):
    """ימי העבודה מיום ראשון עד היום (כולל)."""
    s = week_start(day)
    return sum(workday_weight(s + _dt.timedelta(days=i)) for i in range((day - s).days + 1))


def _num(v):
    return int(v) if float(v).is_integer() else round(float(v), 1)


def _sum_counts(parts):
    out = {}
    for k in ("meetings", "nb_wa", "buyers", "buyers_sign", "bpage", "past_clients", "reviews"):
        vals = [p.get(k) for p in parts]
        out[k] = None if (not vals or any(v is None for v in vals)) else sum(vals)
    fu = [p.get("followups") for p in parts]
    out["followups"] = None if (not fu or any(f is None for f in fu)) else \
        {"due": sum(f["due"] for f in fu), "done": sum(f["done"] for f in fu)}
    return out


def count_days(agent, days, src, canon):
    """ספירה לכמה ימים — כל יום לחוד (פולו-אפ ולקוחות עבר הם לפי יום) ומסכמים. יומן הפעולות מסונן לכל יום;
    'שיחות פתוחות' הוא מצב נוכחי — נספר פעם אחת, לא לכל יום."""
    act = src.get("activity")
    parts = []
    for d in days:
        b = day_bounds(d)
        a = act if _bad(act) else [x for x in (act or []) if _in(parse_ts(x.get("ts")), b)]
        parts.append(count_agent(agent, b, dict(src, activity=a, missed=[]), canon))
    out = _sum_counts(parts)
    # יעד שבועי (גיוס נכסים): מתחילת השבוע של היום האחרון בתקופה — לא סכום של ימים
    out["listings"] = parts[-1].get("listings") if parts else None
    missed = src.get("missed")
    out["missed"] = None if _bad(missed) else sum(1 for m in (missed or []) if _same(m.get("agent"), agent, canon))
    return out


def _met(counts, targets):
    """כמה מהיעדים הושלמו במלואם, ומתוך כמה."""
    met = 0
    for k in GOAL_KEYS:
        t = (targets or {}).get(k) or 0
        c = counts.get(k)
        if c is not None and c >= t:        # כמו goalIsDone באפליקציה: יעד 0 (שבת) = הושלם
            met += 1
    return met, len(GOAL_KEYS)


def _trend(cur, prev):
    return {k: (None if cur.get(k) is None or prev.get(k) is None else cur[k] - prev[k]) for k in GOAL_KEYS}


def build_periods(src, today, canon):
    """[GOALS 28/10] טבלת 'יעדי היום' בלוח הבקרה: לכל תקופה (היום / אתמול / השבוע) שורה לכל סוכן ושורת משרד,
    עם 'עמידה' (כמה יעדים הושלמו) ומגמה מול אותה תקופה לפני שבוע. בשבוע: סכום מיום ראשון, והיעד = היעד היומי
    כפול ימי העבודה עד היום (שישי חצי); גם היום/אתמול לפי משקל היום (שישי חצי, שבת 0 — רק בלוח הבקרה,
    בכרטיס באפליקציה היעד היומי המלא). seen_today = נכנס היום (רלוונטי לתצוגת 'היום')."""
    import functools
    canon = functools.lru_cache(maxsize=None)(canon)     # אלפי השוואות שמות לכל בנייה
    cfg = _cfg_of(src)
    yday = today - _dt.timedelta(days=1)
    ws = week_start(today)
    week = [ws + _dt.timedelta(days=i) for i in range((today - ws).days + 1)]
    periods = {"today": ([today], workday_weight(today)), "yesterday": ([yday], workday_weight(yday)),
               "week": (week, workdays_elapsed(today))}
    out = {}
    for pk, (days, scale) in periods.items():
        prev_days = [d - _dt.timedelta(days=7) for d in days]
        rows, per, tg, total = _assemble(
            src, canon, lambda n, days=days: count_days(n, days, src, canon),
            lambda n, scale=scale: {g: (v if g in WEEKLY_GOALS else _num(v * scale))
                                    for g, v in targets_for(cfg, n, canon).items()})
        prev_per = {}
        for r in rows:
            pc = count_days(r["name"], prev_days, src, canon)
            prev_per[canon(r["name"])] = pc
            r["met"], r["goals_n"] = _met(r["counts"], r["targets"])
            r["trend"] = _trend(r["counts"], pc)
        rows.sort(key=lambda r: (-r["met"], r["name"]))
        total["targets"] = {g: _num(v) for g, v in total["targets"].items()}
        total["met"], total["goals_n"] = _met(total["counts"], total["targets"])
        total["trend"] = _trend(total["counts"], rollup(prev_per, tg)["counts"])
        out[pk] = {"day": days[0].isoformat(), "to": days[-1].isoformat(), "rows": rows, "total": total,
                   "workdays": _num(scale) if pk == "week" else None}
    return out


# ── [GOALS-WEEKLY 29/10] סיכום יעדים שבועי לכל סוכן בוואטסאפ הרשמי (אייל) ─────────────────────────
GOAL_LABELS = {"listings": "גיוס נכסים", "meetings": "פגישות מנכס נולד", "nb_wa": "פניות לנכס נולד",
               "buyers": "קונים חדשים", "past_clients": "הודעות ללקוחות עבר", "reviews": "המלצות"}
WEEKLY_HOUR = 10                 # אייל 29/10: ביום ראשון ב-10:00
WEEKLY_SEEN_DAYS = 10            # רק מי שנכנס לאפי ב-10 הימים שלפני ההודעה
WEEKLY_RETRY_SEC = 900           # כשל → ניסיון חוזר כל 15 דק'
WEEKLY_MAX_TRIES = 8
REC_UP, REC_DOWN = 1.3, 0.5      # הושג 130%+ → להעלות; מתחת ל-50% → להוריד


def weekly_period(today):
    """השבוע שהסתיים (ראשון–שבת) לפני השבוע של today. ביום שני אחרי חג ביום ראשון — עדיין אותו שבוע."""
    s = week_start(today) - _dt.timedelta(days=7)
    return s, s + _dt.timedelta(days=6)


def weekly_scale():
    """ימי העבודה בשבוע מלא (א'–ה' 1, שישי חצי) = 5.5."""
    s = week_start(_dt.date(2026, 1, 4))
    return sum(workday_weight(s + _dt.timedelta(days=i)) for i in range(7))


def weekly_due(now_il, blocked, state, hour=WEEKLY_HOUR):
    """מפתח השבוע (ISO של יום ראשון) אם צריך לשלוח עכשיו, אחרת None. ראשון–חמישי מ-hour; blocked = חג/שבת/השתקה.
    יום ראשון שהוא חג → נשלח ביום העבודה הבא (אייל 29/10), עד חמישי."""
    if blocked or now_il.weekday() not in (6, 0, 1, 2, 3) or now_il.hour < hour:
        return None
    key = weekly_period(now_il.date())[0].isoformat()
    if ((state or {}).get(key) or {}).get("done"):
        return None
    return key


def weekly_recommend(count, wtarget, daily):
    """(up/down/keep, יעד יומי מוצע). הושג 130%+ → +1 לפחות (או 25%); מתחת ל-50% → -1 לפחות (או 25%), לא מתחת ל-1."""
    import math
    daily = int(daily or 0)
    if count is None or not wtarget or daily <= 0:
        return "keep", daily
    r = float(count) / float(wtarget)
    if r >= REC_UP:
        return "up", min(_MAX_TARGET, max(daily + 1, int(round(daily * 1.25))))
    if r < REC_DOWN:
        new = max(1, min(daily - 1, int(math.floor(daily * 0.75))))
        return ("down", new) if new < daily else ("keep", daily)
    return "keep", daily


def build_weekly(src, sunday, canon):
    """שורה לכל סוכן ברשימה שנכנס לאפי (src['seen']) — ספירה לשבוע ראשון–שבת מול היעד השבועי
    (יעד יומי × 5.5), כמה יעדים הושגו והמלצה לכל יעד. אותה ספירה כמו טבלת 'השבוע' בלוח הבקרה (count_days)."""
    import functools
    canon = functools.lru_cache(maxsize=None)(canon)
    cfg = _cfg_of(src)
    days = [sunday + _dt.timedelta(days=i) for i in range(7)]
    scale = weekly_scale()
    seen = _seen_set(src, canon)
    names, _bad_roster = _roster_names(src, canon)
    rows = []
    for name in names:
        if canon(name) not in seen:
            continue
        c = count_days(name, days, src, canon)
        daily = targets_for(cfg, name, canon)
        wt = {k: (v if k in WEEKLY_GOALS else _num(v * scale)) for k, v in daily.items()}   # גיוס — יעד שבועי
        met, n = _met(c, wt)
        rows.append({"name": name, "counts": c, "targets": wt, "daily": daily, "met": met, "goals_n": n,
                     "rec": {k: weekly_recommend(c.get(k), wt.get(k), daily.get(k)) for k in GOAL_KEYS},
                     "from": days[0].isoformat(), "to": days[-1].isoformat()})
    return rows


def _dm(iso):
    d = _dt.date.fromisoformat(iso)
    return f"{d.day}/{d.month}"


def _span(row):
    return _dm(row["from"]) + "–" + _dm(row["to"])


def weekly_message(row, office, link):
    """ההודעה לסוכן. שם המשרד מהקונפיג (v2_office.name) בלבד; בלי אימוג'ים."""
    first = (str(row.get("name") or "").split() or [""])[0]
    office = str(office or "").strip()
    lines = [f"שלום {first}, סיכום היעדים שלך" + (f" ב{office}" if office else "") + f" לשבוע {_span(row)}:", ""]
    for k in GOAL_KEYS:
        c, t = row["counts"].get(k), row["targets"].get(k)
        if c is None:
            lines.append(f"{GOAL_LABELS[k]}: אין נתון")
        else:
            lines.append(f"{GOAL_LABELS[k]}: {c} מתוך {t}" + (" — הושג" if c >= (t or 0) else ""))
        if k == "buyers" and row["counts"].get("buyers_sign"):
            lines[-1] += f" (מתוכם {row['counts']['buyers_sign']} מהחתמה)"
    lines += ["", f"הגעת ל-{row['met']} מתוך {row['goals_n']} יעדים.", "", "המלצה ליעד:"]
    for k in GOAL_KEYS:
        kind, n = row["rec"][k]
        per = "בשבוע" if k in WEEKLY_GOALS else "ביום"
        lines.append(f"{GOAL_LABELS[k]}: " + {"up": f"להעלות ל-{n} {per}", "down": f"להוריד ל-{n} {per}"}.get(
            kind, f"להשאיר {n} {per}"))
    lines += ["(את היעדים מעדכן מנהל המשרד)", "", f"למסך היעדים: {link}"]
    return "\n".join(lines)


def weekly_manager_summary(rows, office):
    """סיכום לבעל המשרד: רק ההמלצות לשינוי (להעלות/להוריד), לכל סוכן — כדי שיעדכן בעצמו במסך היעדים."""
    span = _span(rows[0]) if rows else ""
    out = ["סיכום יעדים שבועי" + (f" — {office}" if office else "") + (f" — {span}" if span else ""),
           f"נשלח ל-{len(rows)} סוכנים.", ""]
    any_rec = False
    for r in rows:
        ch = [(k, r["rec"][k]) for k in GOAL_KEYS if r["rec"][k][0] != "keep"]
        if not ch:
            continue
        any_rec = True
        out.append(f"{r['name']} ({r['met']}/{r['goals_n']}):")
        for k, (kind, n) in ch:
            out.append(f"{GOAL_LABELS[k]}: " + ("להעלות" if kind == "up" else "להוריד") + f" ל-{n}"
                       f" (היום {r['daily'][k]}; עשה {r['counts'][k]} מתוך {r['targets'][k]})")
        out.append("")
    if not any_rec:
        out.append("אין המלצות לשינוי השבוע.")
    return "\n".join(out).rstrip()


def weekly_mark(rec, name, result, now):
    """רישום ניסיון לסוכן: sent / fail / no_phone."""
    a = rec.setdefault("agents", {})
    cur = a.get(name) or {}
    a[name] = {"r": result, "ts": now, "tries": int(cur.get("tries") or 0) + 1}
    return rec


def weekly_pending(names, rec, now, canon):
    """מי עוד צריך לקבל: לא נשלח, לא 'אין טלפון', ובכשל — עברו 15 דק' ופחות מ-8 ניסיונות."""
    by = {canon(k): v for k, v in ((rec or {}).get("agents") or {}).items()}
    out = []
    for n in names:
        e = by.get(canon(n))
        if e:
            if e.get("r") in ("sent", "no_phone"):
                continue
            if int(e.get("tries") or 0) >= WEEKLY_MAX_TRIES or now - float(e.get("ts") or 0) < WEEKLY_RETRY_SEC:
                continue
        out.append(n)
    return out


# ── [GOALS-MONTHLY 29/10] סיכום חודשי לכל סוכן + לבעל המשרד (אייל: "כל יום ראשון אחרי חודש") ──────────
# החלטות אייל 29/10: ביום ראשון המשותף — שתי הודעות נפרדות (החודשי אחרי השבועי, מ-10:20);
# לבעל המשרד — הודעה קצרה + קישור לעמוד מסודר (/v2/goals/monthly).
MONTHLY_AT = (10, 20)
_HE_MONTHS = ("ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר")


def month_period(today):
    """החודש הקלנדרי שלפני החודש של today → (ראשון, אחרון)."""
    last = today.replace(day=1) - _dt.timedelta(days=1)
    return last.replace(day=1), last


def first_sunday(day):
    """יום ראשון הראשון מ-1 בחודש של day (כולל)."""
    f = day.replace(day=1)
    return f + _dt.timedelta(days=(6 - f.weekday()) % 7)


def month_label(day):
    return f"{_HE_MONTHS[day.month - 1]} {day.year}"


def month_scale(first, last):
    """ימי העבודה בחודש (א'–ה' 1, שישי חצי)."""
    return _num(sum(workday_weight(first + _dt.timedelta(days=i)) for i in range((last - first).days + 1)))


def month_weeks(first, last):
    """מספר השבועות בחודש (ימים / 7, ספרה אחת) — ליעד השבועי (גיוס נכסים)."""
    return round(((last - first).days + 1) / 7.0, 1)


def monthly_due(now_il, blocked, state):
    """מפתח החודש ('YYYY-MM' של החודש שהסתיים) אם צריך לשלוח עכשיו. ביום ראשון הראשון אחרי סוף החודש מ-10:20
    (אחרי השבועי); חג → יום העבודה הבא באותו שבוע (עד חמישי). פעם אחת."""
    d = now_il.date()
    fs = first_sunday(d)
    if blocked or now_il.weekday() not in (6, 0, 1, 2, 3) or not (0 <= (d - fs).days <= 4):
        return None
    if (now_il.hour, now_il.minute) < MONTHLY_AT:
        return None
    key = month_period(d)[0].strftime("%Y-%m")
    if ((state or {}).get(key) or {}).get("done"):
        return None
    return key


def _month_counts(name, first, last, src, canon):
    days = [first + _dt.timedelta(days=i) for i in range((last - first).days + 1)]
    c = count_days(name, days, src, canon)
    c["listings"] = count_listings(name, (day_bounds(first)[0], day_bounds(last)[1]), src.get("sigs"), canon)
    return c


def build_monthly(src, first, last, canon):
    """לכל סוכן שנכנס לאפי ב-10 הימים האחרונים (src['seen']): ספירת החודש מול יעד החודש (יומי × ימי עבודה;
    גיוס = שבועי × שבועות), כמה הושגו, החודש הקודם, המלצה. + סכום המשרד, 5 מובילים, מי לא נכנס בכלל בחודש
    (src['seen_month'])."""
    import functools
    canon = functools.lru_cache(maxsize=None)(canon)
    cfg = _cfg_of(src)
    pfirst, plast = month_period(first)
    scale, weeks = month_scale(first, last), month_weeks(first, last)
    pscale, pweeks = month_scale(pfirst, plast), month_weeks(pfirst, plast)
    seen = _seen_set(src, canon)
    sm = src.get("seen_month")
    seen_m = None if _bad(sm) else {canon(n) for n in (sm or []) if n}
    names, _rb = _roster_names(src, canon)
    rows, per, tg = [], {}, {}
    for name in names:
        if canon(name) not in seen:
            continue
        daily = targets_for(cfg, name, canon)
        c = _month_counts(name, first, last, src, canon)
        pc = _month_counts(name, pfirst, plast, src, canon)
        mt = {k: _num(round(v * (weeks if k in WEEKLY_GOALS else scale), 1)) for k, v in daily.items()}
        pt = {k: _num(round(v * (pweeks if k in WEEKLY_GOALS else pscale), 1)) for k, v in daily.items()}
        met, n = _met(c, mt)
        pmet, _ = _met(pc, pt)
        ratio = [min(2.0, (c.get(k) or 0) / mt[k]) for k in GOAL_KEYS if mt.get(k) and c.get(k) is not None]
        rows.append({"name": name, "counts": c, "prev": pc, "targets": mt, "daily": daily, "met": met,
                     "prev_met": pmet, "goals_n": n, "score": sum(ratio) / len(ratio) if ratio else 0,
                     "rec": {k: weekly_recommend(c.get(k), mt.get(k), daily.get(k)) for k in GOAL_KEYS},
                     "from": first.isoformat(), "to": last.isoformat()})
        per[canon(name)], tg[canon(name)] = c, mt
    total = rollup(per, tg)
    total["targets"] = {k: _num(round(v, 1)) for k, v in total["targets"].items()}
    total["met"], total["goals_n"] = _met(total["counts"], total["targets"])
    top = sorted(rows, key=lambda r: (-r["met"], -r["score"], r["name"]))[:5]
    inactive = [] if seen_m is None else [n for n in names if canon(n) not in seen_m]
    return {"rows": rows, "total": total, "top": top, "inactive": inactive, "label": month_label(first),
            "month": first.strftime("%Y-%m")}


def monthly_message(row, office, link, label):
    first = (str(row.get("name") or "").split() or [""])[0]
    office = str(office or "").strip()
    lines = [f"שלום {first}, סיכום היעדים שלך" + (f" ב{office}" if office else "") + f" לחודש {label}:", ""]
    for k in GOAL_KEYS:
        c, t, p = row["counts"].get(k), row["targets"].get(k), (row.get("prev") or {}).get(k)
        if c is None:
            lines.append(f"{GOAL_LABELS[k]}: אין נתון")
            continue
        ln = f"{GOAL_LABELS[k]}: {c} מתוך {t}" + (" — הושג" if c >= (t or 0) else "")
        if k == "buyers" and row["counts"].get("buyers_sign"):
            ln += f" (מתוכם {row['counts']['buyers_sign']} מהחתמה)"
        if p is not None:
            ln += f" (בחודש הקודם: {p})"
        lines.append(ln)
    lines += ["", f"הגעת ל-{row['met']} מתוך {row['goals_n']} יעדים (בחודש הקודם: {row.get('prev_met', 0)}).", "",
              "המלצה ליעד:"]
    for k in GOAL_KEYS:
        kind, n = row["rec"][k]
        per = "בשבוע" if k in WEEKLY_GOALS else "ביום"
        lines.append(f"{GOAL_LABELS[k]}: " + {"up": f"להעלות ל-{n} {per}", "down": f"להוריד ל-{n} {per}"}.get(
            kind, f"להשאיר {n} {per}"))
    lines += ["(את היעדים מעדכן מנהל המשרד)", "", f"למסך היעדים: {link}"]
    return "\n".join(lines)


def monthly_owner_summary(M, office, link):
    """לבעל המשרד — קצר: סכום המשרד מול היעד, 5 המובילים, כמה לא נכנסו, כמה המלצות; הפירוט בעמוד."""
    t = M["total"]
    out = [f"סיכום יעדים חודשי — {M['label']}" + (f" — {office}" if office else ""),
           f"{len(M['rows'])} סוכנים פעילים · המשרד הגיע ל-{t['met']} מתוך {t['goals_n']} יעדים.", ""]
    for k in GOAL_KEYS:
        c = t["counts"].get(k)
        out.append(f"{GOAL_LABELS[k]}: " + ("אין נתון" if c is None else f"{c} מתוך {t['targets'].get(k)}"))
    if M["top"]:
        out += ["", "המובילים: " + ", ".join(f"{r['name']} ({r['met']}/{r['goals_n']})" for r in M["top"])]
    nrec = sum(1 for r in M["rows"] for k in GOAL_KEYS if r["rec"][k][0] != "keep")
    out += ["", f"לא נכנסו לאפי בחודש: {len(M['inactive'])}", f"המלצות לשינוי יעד: {nrec}", "",
            f"הפירוט המלא: {link}"]
    return "\n".join(out)


def meeting_stamp(prev, new_status, now):
    """חותמת 'מתי נקבעה הפגישה' — קבועה לתמיד: קיימת נשמרת; אחרת now אם הסטטוס meeting; אחרת None."""
    ex = (prev or {}).get("meeting_at")
    if ex:
        return ex
    return now if new_status == "meeting" else None


# ── שליפת המקורות (משותף לראוטי היעדים וללוח הבקרה) ─────────────────────────────────
def g_canon(G, n):
    return G["_canon_key"](str(n or "").strip())


def g_display(G, n):
    n = str(n or "").strip()
    try:
        return G["_canon_agent_name"](n) or n
    except Exception:
        return n


def g_safe(G, fn):
    """מקור שנכשל → החריגה עצמה (היעד שלו יוצג '—'), בלי להפיל את השאר."""
    try:
        return fn()
    except Exception as e:
        lg = G.get("log")
        if lg:
            try:
                lg.warning(f"goals source failed: {e}")
            except Exception:
                pass
        return e


def g_roster(G):
    """הצוות שיכול להיכנס — אותה רשימה כמו טבלת הסוכנים בלוח הבקרה (effie_v2.crm_roster)."""
    import effie_v2 as _ev
    return [g_display(G, n) for n in _ev.crm_roster(G)]


def g_missed(G, now):
    import effie_v2 as _ev
    frm = (_dt.datetime.fromtimestamp(now, _IL) - _dt.timedelta(days=3)).strftime("%d/%m/%Y")
    calls = G["web_fetch_raw"]("שיחות", frm, "31/12/2099") or []
    h = {"ts": _ev.crm_ts, "answered": lambda st: bool(G["_is_answered_status"](str(st or ""))),
         "nb_key": lambda r: ""}
    return _ev.crm_todo(calls, [], [], [], {}, now, h, limit=None)["missed"]


def g_sigs(G, since_day):
    """[GOALS2 29/10] שורות חתימה מ-since_day: {agent, address, type, signed, ts} (signed = קישור חתום או עמלה)."""
    times = {}
    try:      # שעת החתימה האמיתית (sign_docs) — כמו מסך החתימות; received_at = שעת שליחה / עדכון אחרון בפיירברי
        sb = G.get("_sbdb")
        if sb is not None and sb.enabled():
            times = sb.signdoc_times() or {}
    except Exception:
        times = {}
    out = []
    for g in G["get_signings"](since_day.strftime("%d/%m/%Y"), "31/12/2099") or []:
        lk = str(g.get("commission_pct", "") or "").strip()
        ts = g.get("received_at", "")
        if "/s/" in lk:
            ts = times.get(lk.rsplit("/s/", 1)[-1].strip("/ ")) or ts
        out.append({"agent": g.get("agent", ""), "address": g.get("address", ""),
                    "type": G["_deal_label"](g.get("deal_type", "")), "signed": bool(lk),
                    "ts": ts})       # parse_ts — שעון ישראל
    return out


def g_reviews(G):
    import site_api as _sa
    return _sa.reviews_active(_sa.review_rows(G.get("_sbdb")))


def g_seen(G, day):
    start = _dt.datetime(day.year, day.month, day.day, tzinfo=_IL)
    return [r.get("name") for r in (G["_usage_rows"](start) or []) if r.get("name")]


_ACTIVE_BOX = {"k": None, "t": 0.0, "v": None}
ACTIVE_TTL = 600


def g_active(G, day, days=ACTIVE_DAYS):
    """[GOALS2 29/10] מי שנכנס לאפי ב-`days` הימים האחרונים (כולל היום) — לפי פעימות הנוכחות.
    מטמון 10 דק' (10 ימים של פעימות). אין אף אחד (Supabase כבוי / ריק) → None = לא ידוע, וכולם נספרים."""
    key = (day.isoformat(), days)
    bx = _ACTIVE_BOX
    if bx["k"] == key and (_clock() - bx["t"]) < ACTIVE_TTL:
        return bx["v"]
    d0 = day - _dt.timedelta(days=days - 1)
    start = _dt.datetime(d0.year, d0.month, d0.day, tzinfo=_IL)
    names = [g_display(G, r.get("name")) for r in (G["_usage_rows"](start) or []) if r.get("name")]
    v = names or None
    bx.update(k=key, t=_clock(), v=v)
    return v


def dashboard_goals(G, now):
    """[GOALS 28/10] כרטיס 'יעדי היום' בלוח הבקרה — היום / אתמול / השבוע, מול אותה תקופה לפני שבוע.
    יומן הפעולות נשלף פעם אחת מתחילת השבוע הקודם (או משמונה ימים אחורה, המוקדם) — רק 'תזכורת ללקוח עבר', סינון בשרת."""
    day = _dt.datetime.fromtimestamp(now, _IL).date()
    first = min(week_start(day) - _dt.timedelta(days=7), day - _dt.timedelta(days=8))
    t0 = day_bounds(first)[0]

    def activity():
        sb = G.get("_sbdb")
        if sb is not None and sb.enabled():
            return sb.fetch_activity_actions(t0, (ACT_REMIND, ACT_NB_WA)) or []
        return G["_activity_fetch"](t0, today=False)

    cfg = g_safe(G, G["_load_config"])
    src = {"nb": cfg if _bad(cfg) else ((cfg or {}).get("nbStatus") or {}),
           "cfg": cfg if isinstance(cfg, dict) else {},
           "buyers": g_safe(G, G["_fetch_manual_buyers"]),
           "bpages": g_safe(G, lambda: G["_sbdb"].bpage_all()),
           "activity": g_safe(G, activity),
           "reviews": g_safe(G, lambda: g_reviews(G)),
           "missed": g_safe(G, lambda: g_missed(G, now)),
           "seen": g_safe(G, lambda: g_seen(G, day)),
           "active": g_safe(G, lambda: g_active(G, day)),
           "sigs": g_safe(G, lambda: g_sigs(G, min(first, week_start(day - _dt.timedelta(days=8))))),   # גם שבוע-קודם של 'אתמול' ביום ראשון
           "roster": g_safe(G, lambda: g_roster(G))}
    return build_periods(src, day, lambda n: g_canon(G, n))


def _rec_last(rec):
    tss = [float((v or {}).get("ts") or 0) for v in ((rec or {}).get("agents") or {}).values()]
    tss.append(float(((rec or {}).get("mgr") or {}).get("ts") or 0))
    m = max(tss) if tss else 0
    return m or None


def weekly_health(state, now, quiet, enabled=True):
    """[29/10 אייל: 'בדשבורד בריבועים למעלה — תקין או לא'] ריבוע בלוח הבקרה: ok = הסיכום של השבוע שהסתיים נשלח
    (או שעוד לא הגיע הזמן — ראשון לפני 11:00); warn = נשלח אבל חלק נכשלו, או מאחר (ראשון אחרי 11:00 / שני עד 12:00);
    bad = לא נשלח עד שני בצהריים; quiet = שבת/חג; none = כבוי."""
    base = {"key": "goals_weekly", "label": "סיכום יעדים שבועי"}
    if not enabled:
        return dict(base, status="none", last=None)
    now_il = _dt.datetime.fromtimestamp(now, _IL)
    key = weekly_period(now_il.date())[0]
    rec = (state or {}).get(key.isoformat()) or {}
    prev = (state or {}).get((key - _dt.timedelta(days=7)).isoformat()) or {}
    if rec.get("done"):
        bad = any((v or {}).get("r") == "fail" for v in (rec.get("agents") or {}).values()) or \
            (rec.get("mgr") or {}).get("r") == "fail"
        return dict(base, status="warn" if bad else "ok", last=_rec_last(rec))
    wd, hr = now_il.weekday(), now_il.hour
    if wd == 6 and hr < WEEKLY_HOUR + 1:                     # ראשון לפני 11:00 — עוד לא מאחר
        return dict(base, status="ok", last=_rec_last(rec) or _rec_last(prev))
    if quiet:
        return dict(base, status="quiet", last=_rec_last(rec) or _rec_last(prev))
    late = "warn" if (wd == 6 or (wd == 0 and hr < 12)) else "bad"
    return dict(base, status=late, last=_rec_last(rec) or _rec_last(prev))


def weekly_disk_path():
    import os as _o
    return _o.path.join(_o.environ.get("MAP_CACHE_DIR", "") or _o.path.dirname(_o.path.abspath(__file__)),
                        "goals_weekly.json")


def weekly_health_tile(G, now):
    """הריבוע מהמצב החי: הקונפיג + העותק בדיסק (כמו weekly_run)."""
    import os as _o
    cfg = G["_load_config"]() or {}
    state = dict(cfg.get("v2_goals_weekly") or {})
    for k, v in _weekly_disk(weekly_disk_path()).items():
        if (v or {}).get("done") or k not in state:
            state[k] = v
    try:
        quiet = bool(G["_quiet_mode"]())
    except Exception:
        quiet = False
    on = (_o.environ.get("GOALS_WEEKLY_WA", "1") or "1").strip() != "0"
    return weekly_health(state, now, quiet, enabled=on)


# ── [GOALS-WEEKLY 29/10] הריצה: מקורות, שליחה, תצוגה מקדימה (G = globals() של app.py) ─────────────
def weekly_src(G, sunday, now, src_override=None):
    """אותם מקורות כמו לוח הבקרה, לשבוע ראשון–שבת; seen = מי שנכנס לאפי ב-10 הימים שלפני now."""
    t0 = day_bounds(sunday)[0]

    def activity():
        sb = G.get("_sbdb")
        if sb is not None and sb.enabled():
            return sb.fetch_activity_actions(t0, (ACT_REMIND, ACT_NB_WA)) or []
        return G["_activity_fetch"](t0, today=False)

    def seen():   # [29/10] אותו 'מי נכנס ב-10 ימים' כמו יעד המשרד (g_active, מטמון 10 דק')
        return g_active(G, _dt.datetime.fromtimestamp(now, _IL).date()) or []

    cfg = g_safe(G, G["_load_config"])
    src = {"nb": cfg if _bad(cfg) else ((cfg or {}).get("nbStatus") or {}),
           "cfg": cfg if isinstance(cfg, dict) else {}, "missed": []}
    over = src_override or {}
    for k, fn in (("buyers", lambda: G["_fetch_manual_buyers"]()), ("bpages", lambda: G["_sbdb"].bpage_all()),
                  ("activity", activity), ("reviews", lambda: g_reviews(G)), ("seen", seen),
                  ("sigs", lambda: g_sigs(G, sunday)),
                  ("roster", lambda: g_roster(G))):
        src[k] = over[k] if k in over else g_safe(G, fn)
    return src


def _weekly_phone(G, name, ag_ph, vph):
    """הנייד האישי של הסוכן מאנשי הקשר (התאמת שם עם _canon_key, כמו 'קונה שמפרסם נכס'); מספר מרכזיה — לא."""
    ck = g_canon(G, name)
    ph = ag_ph.get(name) or next((v for k, v in ag_ph.items() if v and g_canon(G, k) == ck), "")
    if not ph or G["_last9"](ph) in vph:
        return ""
    return G["_wa_phone"](ph) or ""


def _weekly_disk(path, key=None, val=None):
    import json as _json
    try:
        with open(path, encoding="utf-8") as f:
            d = _json.load(f)
    except Exception:
        d = {}
    if key is not None:
        d[key] = val
        for k in sorted(d)[:-8]:
            d.pop(k, None)
        try:
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(d, f, ensure_ascii=False)
        except Exception:
            pass
    return d


def _weekly_link():
    import os as _o
    return (_o.environ.get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/") + "/v2/goals"


def _weekly_mgr_phones(G):
    import os as _o
    raw = (_o.environ.get("GOALS_WEEKLY_MGR") or "").strip()
    lst = [x.strip() for x in raw.split(",") if x.strip()] if raw else list(G.get("_DEV_PHONES_RAW") or [])
    return [G["_wa_phone"](x) for x in lst if G["_wa_phone"](x)]


def weekly_preview(G, now, src_override=None):
    """מה יישלח לשבוע שהסתיים — בלי לשלוח ובלי לרשום."""
    day = _dt.datetime.fromtimestamp(now, _IL).date()
    sunday = weekly_period(day)[0]
    cfg = G["_load_config"]() or {}
    office = str(((cfg.get("v2_office") or {}).get("name")) or "").strip()
    rows = build_weekly(weekly_src(G, sunday, now, src_override), sunday, lambda n: g_canon(G, n))
    ag_ph = G["fetch_agents_phones"]() or {}
    vph = G["_agent_vphones9"]() or set()
    msgs = [{"name": r["name"], "phone": _weekly_phone(G, r["name"], ag_ph, vph), "met": r["met"],
             "text": weekly_message(r, office, _weekly_link())} for r in rows]
    return {"week": sunday.isoformat(), "messages": msgs, "manager": weekly_manager_summary(rows, office),
            "state": ((cfg.get("v2_goals_weekly") or {}).get(sunday.isoformat()) or {})}


def weekly_run(G, now, disk_path, src_override=None):
    """סבב אחד (כל כמה דקות): אם הגיע הזמן — שולח לכל סוכן שטרם קיבל, ואז סיכום לבעל המשרד. מחזיר כמה נשלחו."""
    import os as _o
    if (_o.environ.get("GOALS_WEEKLY_WA", "1") or "1").strip() == "0" or not G["_d360_on"]():
        return 0
    now_il = _dt.datetime.fromtimestamp(now, _IL)
    try:
        blocked = bool(G["_quiet_mode"]()) or bool(G["_switch_off"]("wa_official_off"))
    except Exception:
        blocked = True
    cfg = G["_load_config"]() or {}
    state = dict(cfg.get("v2_goals_weekly") or {})
    disk = _weekly_disk(disk_path)
    for k, v in disk.items():                       # הקונפיג נדרס בעבר בסנכרון — העותק בדיסק שומר על 'פעם אחת'
        if (v or {}).get("done") or k not in state:
            state[k] = v
    key = weekly_due(now_il, blocked, state)
    if not key:
        return 0
    sunday = _dt.date.fromisoformat(key)
    rec = _json_copy(state.get(key) or {})
    canon = lambda n: g_canon(G, n)
    office = str(((cfg.get("v2_office") or {}).get("name")) or "").strip()
    rows = build_weekly(weekly_src(G, sunday, now, src_override), sunday, canon)
    ag_ph = G["fetch_agents_phones"]() or {}
    vph = G["_agent_vphones9"]() or set()
    by = {canon(r["name"]): r for r in rows}
    n_sent = 0
    for name in weekly_pending([r["name"] for r in rows], rec, now, canon):
        r = by[canon(name)]
        wa = _weekly_phone(G, name, ag_ph, vph)
        if not wa:
            res = "no_phone"
        else:
            try:
                res = "sent" if G["send_text"](wa, weekly_message(r, office, _weekly_link())) else "fail"
            except Exception:
                res = "fail"
        weekly_mark(rec, name, res, now)
        n_sent += res == "sent"
        G["_log_activity"]("אפי", "system", "", "סיכום יעדים שבועי — " +
                           {"sent": "נשלח", "fail": "נכשל", "no_phone": "אין טלפון"}[res], name[:60])
    left = weekly_pending([r["name"] for r in rows], rec, now + WEEKLY_RETRY_SEC, canon)
    m = rec.get("mgr") or {}
    if m.get("r") != "sent" and int(m.get("tries") or 0) < WEEKLY_MAX_TRIES and \
            (not m or now - float(m.get("ts") or 0) >= WEEKLY_RETRY_SEC):
        ok = False
        for wa in _weekly_mgr_phones(G):
            try:
                ok = bool(G["send_text"](wa, weekly_manager_summary(rows, office))) or ok
            except Exception:
                pass
        rec["mgr"] = {"r": "sent" if ok else "fail", "ts": now, "tries": int(m.get("tries") or 0) + 1}
        G["_log_activity"]("אפי", "system", "", "סיכום יעדים שבועי — למנהל " + ("נשלח" if ok else "נכשל"),
                           f"{len(rows)} סוכנים")
    mg = rec.get("mgr") or {}
    rec["done"] = not left and (mg.get("r") == "sent" or int(mg.get("tries") or 0) >= WEEKLY_MAX_TRIES)
    rec["n"] = len(rows)

    def _mut(c, _k=key, _v=rec):
        d = c.get("v2_goals_weekly") if isinstance(c.get("v2_goals_weekly"), dict) else {}
        d[_k] = _v
        for kk in sorted(d)[:-8]:
            d.pop(kk, None)
        c["v2_goals_weekly"] = d
        return True
    try:
        G["_config_mutate"](_mut)
    except Exception:
        pass
    _weekly_disk(disk_path, key, rec)
    return n_sent


def _json_copy(v):
    import json as _json
    return _json.loads(_json.dumps(v, ensure_ascii=False))


def monthly_src(G, first, last, now, src_override=None):
    """מקורות מתחילת החודש הקודם (להשוואה) + מי נכנס בחודש (seen_month) ומי ב-10 הימים האחרונים (seen)."""
    pfirst = month_period(first)[0]
    t0 = day_bounds(pfirst)[0]

    def activity():
        sb = G.get("_sbdb")
        if sb is not None and sb.enabled():
            return sb.fetch_activity_actions(t0, (ACT_REMIND, ACT_NB_WA)) or []
        return G["_activity_fetch"](t0, today=False)

    def seen():
        return g_active(G, _dt.datetime.fromtimestamp(now, _IL).date()) or []

    def seen_month():
        a = _dt.datetime(first.year, first.month, first.day, tzinfo=_IL)
        b = _dt.datetime.combine(last + _dt.timedelta(days=1), _dt.time(), tzinfo=_IL)
        return [g_display(G, r.get("name")) for r in (G["_usage_rows"](a, b) or []) if r.get("name")]

    cfg = g_safe(G, G["_load_config"])
    src = {"nb": cfg if _bad(cfg) else ((cfg or {}).get("nbStatus") or {}),
           "cfg": cfg if isinstance(cfg, dict) else {}, "missed": []}
    over = src_override or {}
    for k, fn in (("buyers", lambda: G["_fetch_manual_buyers"]()), ("bpages", lambda: G["_sbdb"].bpage_all()),
                  ("activity", activity), ("reviews", lambda: g_reviews(G)), ("seen", seen),
                  ("seen_month", seen_month), ("sigs", lambda: g_sigs(G, pfirst)), ("roster", lambda: g_roster(G))):
        src[k] = over[k] if k in over else g_safe(G, fn)
    return src


def _monthly_link():
    return _weekly_link() + "/monthly"


def _monthly_owner_phones(G):
    import os as _o
    raw = (_o.environ.get("GOALS_MONTHLY_MGR") or "").strip()
    if raw:
        return [G["_wa_phone"](x) for x in raw.split(",") if x.strip() and G["_wa_phone"](x.strip())]
    return _weekly_mgr_phones(G)


def monthly_preview(G, now, src_override=None):
    """מה יישלח לחודש שהסתיים — בלי לשלוח ובלי לרשום. גם העמוד שבקישור לבעל המשרד."""
    first, last = month_period(_dt.datetime.fromtimestamp(now, _IL).date())
    cfg = G["_load_config"]() or {}
    office = str(((cfg.get("v2_office") or {}).get("name")) or "").strip()
    M = build_monthly(monthly_src(G, first, last, now, src_override), first, last, lambda n: g_canon(G, n))
    ag_ph = G["fetch_agents_phones"]() or {}
    vph = G["_agent_vphones9"]() or set()
    msgs = [{"name": r["name"], "phone": _weekly_phone(G, r["name"], ag_ph, vph), "met": r["met"],
             "prev_met": r["prev_met"], "rec": {k: list(v) for k, v in r["rec"].items()}, "daily": r["daily"],
             "counts": r["counts"], "targets": r["targets"],
             "text": monthly_message(r, office, _weekly_link(), M["label"])} for r in M["rows"]]
    return {"month": M["month"], "label": M["label"], "messages": msgs, "total": M["total"],
            "top": [{"name": r["name"], "met": r["met"], "goals_n": r["goals_n"]} for r in M["top"]],
            "inactive": M["inactive"], "labels": GOAL_LABELS, "keys": list(GOAL_KEYS),
            "owner": monthly_owner_summary(M, office, _monthly_link()),
            "state": ((cfg.get("v2_goals_monthly") or {}).get(M["month"]) or {})}


def monthly_run(G, now, disk_path, src_override=None):
    """סבב אחד: אם הגיע הזמן — לכל סוכן שטרם קיבל, ואז לבעל המשרד. אותם כללים כמו השבועי."""
    import os as _o
    if (_o.environ.get("GOALS_MONTHLY_WA", "1") or "1").strip() == "0" or not G["_d360_on"]():
        return 0
    now_il = _dt.datetime.fromtimestamp(now, _IL)
    try:
        blocked = bool(G["_quiet_mode"]()) or bool(G["_switch_off"]("wa_official_off"))
    except Exception:
        blocked = True
    cfg = G["_load_config"]() or {}
    state = dict(cfg.get("v2_goals_monthly") or {})
    for k, v in _weekly_disk(disk_path).items():
        if (v or {}).get("done") or k not in state:
            state[k] = v
    key = monthly_due(now_il, blocked, state)
    if not key:
        return 0
    first, last = month_period(now_il.date())
    rec = _json_copy(state.get(key) or {})
    canon = lambda n: g_canon(G, n)
    office = str(((cfg.get("v2_office") or {}).get("name")) or "").strip()
    M = build_monthly(monthly_src(G, first, last, now, src_override), first, last, canon)
    ag_ph = G["fetch_agents_phones"]() or {}
    vph = G["_agent_vphones9"]() or set()
    by = {canon(r["name"]): r for r in M["rows"]}
    n_sent = 0
    for name in weekly_pending([r["name"] for r in M["rows"]], rec, now, canon):
        wa = _weekly_phone(G, name, ag_ph, vph)
        if not wa:
            res = "no_phone"
        else:
            try:
                res = "sent" if G["send_text"](wa, monthly_message(by[canon(name)], office, _weekly_link(), M["label"])) else "fail"
            except Exception:
                res = "fail"
        weekly_mark(rec, name, res, now)
        n_sent += res == "sent"
        G["_log_activity"]("אפי", "system", "", "סיכום יעדים חודשי — " +
                           {"sent": "נשלח", "fail": "נכשל", "no_phone": "אין טלפון"}[res], name[:60])
    left = weekly_pending([r["name"] for r in M["rows"]], rec, now + WEEKLY_RETRY_SEC, canon)
    m = rec.get("mgr") or {}
    if m.get("r") != "sent" and int(m.get("tries") or 0) < WEEKLY_MAX_TRIES and \
            (not m or now - float(m.get("ts") or 0) >= WEEKLY_RETRY_SEC):
        ok = False
        for wa in _monthly_owner_phones(G):
            try:
                ok = bool(G["send_text"](wa, monthly_owner_summary(M, office, _monthly_link()))) or ok
            except Exception:
                pass
        rec["mgr"] = {"r": "sent" if ok else "fail", "ts": now, "tries": int(m.get("tries") or 0) + 1}
        G["_log_activity"]("אפי", "system", "", "סיכום יעדים חודשי — לבעל המשרד " + ("נשלח" if ok else "נכשל"),
                           f"{M['label']} · {len(M['rows'])} סוכנים")
    mg = rec.get("mgr") or {}
    rec["done"] = not left and (mg.get("r") == "sent" or int(mg.get("tries") or 0) >= WEEKLY_MAX_TRIES)
    rec["n"] = len(M["rows"])

    def _mut(c, _k=key, _v=rec):
        d = c.get("v2_goals_monthly") if isinstance(c.get("v2_goals_monthly"), dict) else {}
        d[_k] = _v
        for kk in sorted(d)[:-6]:
            d.pop(kk, None)
        c["v2_goals_monthly"] = d
        return True
    try:
        G["_config_mutate"](_mut)
    except Exception:
        pass
    _weekly_disk(disk_path, key, rec)
    return n_sent


def monthly_disk_path():
    return weekly_disk_path().replace("goals_weekly.json", "goals_monthly.json")


WEEKLY_PREVIEW_HTML = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>סיכום יעדים שבועי</title>
<style>body{margin:0;background:#F5F6F8;font-family:-apple-system,Arial,sans-serif;color:#1E3A5F}
.w{max-width:720px;margin:0 auto;padding:16px}h1{font-size:19px;margin:6px 0 4px}.s{color:#6E7683;font-size:13px;margin-bottom:14px}
.c{background:#fff;border:1px solid #E3E6EB;border-radius:14px;padding:14px;margin-bottom:12px}
.n{font-weight:700;font-size:15px;margin-bottom:6px}.p{font-size:12px;color:#6E7683;margin-bottom:8px}.bad{color:#B42318}
pre{white-space:pre-wrap;font-family:inherit;font-size:13.5px;line-height:1.6;margin:0}a{color:#2E6BD6}</style></head>
<body><div class="w"><a href="/v2/admin">חזרה לניהול</a><h1>סיכום יעדים שבועי — תצוגה מקדימה</h1>
<div class="s" id="sub">טוען…</div><div id="out"></div></div>
<script>
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
var tok='';try{tok=localStorage.getItem('fbTok')||'';}catch(e){}
fetch('/v2/api/goals/weekly/preview',{headers:{'X-Auth-Token':tok}}).then(function(r){return r.json();}).then(function(j){
  if(!j.ok){document.getElementById('sub').textContent='אין הרשאה (מנהלים בלבד).';return;}
  var st=j.state||{}, ag=st.agents||{};
  document.getElementById('sub').textContent='השבוע שמתחיל ב-'+j.week+' · '+j.messages.length+' סוכנים · '+(st.done?'נשלח':'טרם נשלח')+' · לא נשלח מכאן — תצוגה בלבד';
  var h='<div class="c"><div class="n">הסיכום אליך</div><pre>'+esc(j.manager)+'</pre></div>';
  j.messages.forEach(function(m){var s=ag[m.name]||{};
    h+='<div class="c"><div class="n">'+esc(m.name)+'</div><div class="p'+(m.phone?'':' bad')+'">'+(m.phone?esc(m.phone):'אין נייד אישי — לא יישלח')+(s.r?' · '+esc(s.r):'')+'</div><pre>'+esc(m.text)+'</pre></div>';});
  document.getElementById('out').innerHTML=h;
}).catch(function(){document.getElementById('sub').textContent='שגיאה בטעינה';});
</script></body></html>"""


MONTHLY_PAGE_HTML = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>סיכום יעדים חודשי</title>
<style>body{margin:0;background:#F5F6F8;font-family:-apple-system,Arial,sans-serif;color:#1E3A5F}
.w{max-width:820px;margin:0 auto;padding:16px}h1{font-size:19px;margin:6px 0 4px}h2{font-size:15px;margin:0 0 8px}
.s{color:#6E7683;font-size:13px;margin-bottom:14px}.c{background:#fff;border:1px solid #E3E6EB;border-radius:14px;padding:14px;margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px 4px;border-bottom:1px solid #EEF0F3;text-align:right}
th{color:#6E7683;font-weight:600}.ok{color:#2F8F5B;font-weight:700}.up{color:#2F8F5B}.down{color:#B42318}.mut{color:#6E7683}
.tw{overflow-x:auto}details{margin-top:6px}summary{cursor:pointer;color:#2E6BD6;font-size:13px}
pre{white-space:pre-wrap;font-family:inherit;font-size:13px;line-height:1.6;margin:8px 0 0}a{color:#2E6BD6}</style></head>
<body><div class="w"><a href="/v2/admin">חזרה לניהול</a><h1>סיכום יעדים חודשי</h1><div class="s" id="sub">טוען…</div><div id="out"></div></div>
<script>
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function v(x){return x==null?'—':x;}
var tok='';try{tok=localStorage.getItem('fbTok')||'';}catch(e){}
fetch('/v2/api/goals/monthly/preview',{headers:{'X-Auth-Token':tok}}).then(function(r){return r.json();}).then(function(j){
  if(!j.ok){document.getElementById('sub').textContent='אין הרשאה (מנהלים בלבד).';return;}
  var L=j.labels,K=j.keys,T=j.total||{},st=j.state||{};
  document.getElementById('sub').textContent=j.label+' · '+j.messages.length+' סוכנים פעילים · '+(st.done?'נשלח':'טרם נשלח')+' · העמוד לא שולח כלום';
  var h='<div class="c"><h2>המשרד — '+v(T.met)+' מתוך '+v(T.goals_n)+' יעדים</h2><table><tr><th>יעד</th><th>בפועל</th><th>יעד המשרד</th></tr>';
  K.forEach(function(k){var c=(T.counts||{})[k],t=(T.targets||{})[k];h+='<tr><td>'+esc(L[k])+'</td><td class="'+(c!=null&&c>=t?'ok':'')+'">'+v(c)+'</td><td>'+v(t)+'</td></tr>';});
  h+='</table></div><div class="c"><h2>5 המובילים</h2>'+(j.top.map(function(r,i){return (i+1)+'. '+esc(r.name)+' <span class="mut">('+r.met+'/'+r.goals_n+')</span>';}).join('<br>')||'<span class="mut">אין</span>')+'</div>';
  h+='<div class="c"><h2>לא נכנסו לאפי בחודש ('+j.inactive.length+')</h2>'+(j.inactive.map(esc).join(' · ')||'<span class="mut">כולם נכנסו</span>')+'</div>';
  var rr='';j.messages.forEach(function(m){K.forEach(function(k){var x=m.rec[k];if(x&&x[0]!=='keep')rr+='<tr><td>'+esc(m.name)+'</td><td>'+esc(L[k])+'</td><td class="'+x[0]+'">'+(x[0]==='up'?'להעלות':'להוריד')+' ל-'+x[1]+'</td><td class="mut">היום '+m.daily[k]+' · עשה '+v(m.counts[k])+' מתוך '+v(m.targets[k])+'</td></tr>';});});
  h+='<div class="c"><h2>המלצות לשינוי יעד</h2>'+(rr?'<div class="tw"><table><tr><th>סוכן</th><th>יעד</th><th>המלצה</th><th></th></tr>'+rr+'</table></div><div class="mut" style="margin-top:8px">לשינוי: <a href="/v2/goals">מסך היעדים</a></div>':'<span class="mut">אין המלצות לשינוי החודש</span>')+'</div>';
  h+='<div class="c"><h2>ההודעות לסוכנים</h2>';j.messages.forEach(function(m){h+='<details><summary>'+esc(m.name)+' · '+m.met+'/'+(m.rec?K.length:'')+(m.phone?'':' · אין נייד — לא יישלח')+'</summary><pre>'+esc(m.text)+'</pre></details>';});
  h+='</div><div class="c"><h2>ההודעה אליך</h2><pre>'+esc(j.owner)+'</pre></div>';
  document.getElementById('out').innerHTML=h;
}).catch(function(){document.getElementById('sub').textContent='שגיאה בטעינה';});
</script></body></html>"""


def register_weekly(app, G):
    """[GOALS-WEEKLY] הלולאה (מתחילה בבקשה הראשונה בתהליך ההגשה — הלקח מ-15/09) + תצוגה מקדימה למנהלים."""
    import os as _o
    from flask import jsonify, Response
    disk = weekly_disk_path()
    thr = {"t": None, "pid": 0}
    lock = _threading.Lock()

    def loop():
        _tm.sleep(90)
        while True:
            try:
                weekly_run(G, _clock(), disk)
            except Exception as e:
                lg = G.get("log")
                if lg:
                    lg.error(f"goals weekly: {e}", exc_info=True)
            try:                                   # [GOALS-MONTHLY] אחרי השבועי, באותה לולאה
                monthly_run(G, _clock(), monthly_disk_path())
            except Exception as e:
                lg = G.get("log")
                if lg:
                    lg.error(f"goals monthly: {e}", exc_info=True)
            _tm.sleep(300)

    @app.before_request
    def _goals_weekly_kick():
        import os as _os2
        t = thr["t"]
        if t is not None and t.is_alive() and thr["pid"] == _os2.getpid():
            return
        with lock:
            t = thr["t"]
            if t is not None and t.is_alive() and thr["pid"] == _os2.getpid():
                return
            thr["t"] = _threading.Thread(target=loop, daemon=True, name="goals-weekly")
            thr["t"].start()
            thr["pid"] = _os2.getpid()

    def _mgr():
        s = G["_web_auth"]()
        return s if s and s.get("drole") in ("manager", "developer") else None

    @app.route("/v2/api/goals/weekly/preview", methods=["GET"])
    def goals_weekly_preview():
        if not _mgr():
            return jsonify({"ok": False, "error": "forbidden"}), 403
        return jsonify(dict(weekly_preview(G, _clock()), ok=True))

    @app.route("/v2/goals/weekly", methods=["GET"])
    def goals_weekly_page():
        return Response(WEEKLY_PREVIEW_HTML, mimetype="text/html")

    @app.route("/v2/api/goals/monthly/preview", methods=["GET"])
    def goals_monthly_preview():
        if not _mgr():
            return jsonify({"ok": False, "error": "forbidden"}), 403
        return jsonify(dict(monthly_preview(G, _clock()), ok=True))

    @app.route("/v2/goals/monthly", methods=["GET"])
    def goals_monthly_page():
        return Response(MONTHLY_PAGE_HTML, mimetype="text/html")


def register(app, G):
    """ראוטי היעדים. G = globals() של app.py (או מקבילה בבדיקות)."""
    from flask import jsonify, request

    @app.route("/v2/api/goals/remind", methods=["POST"])
    def goals_remind():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "error": "unauthorized"}), 403
        b = request.get_json(silent=True) or {}
        act = {"remind": ACT_REMIND, "review": ACT_REVIEW_MANUAL}.get(b.get("kind"))
        digits = re.sub(r"\D", "", str(b.get("phone") or ""))
        if not act or len(digits) < 9:
            return jsonify({"ok": False, "error": "bad_request"}), 400
        G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), act, G["_last9"](digits))
        return jsonify({"ok": True})


    # ── היעדים להיום ────────────────────────────────────────────────────────────
    import hmac as _hmac
    import os as _os
    _keys_used = set()

    def canon(n):
        return g_canon(G, n)

    def _display(n):
        return g_display(G, n)

    def _safe(fn):
        return g_safe(G, fn)

    def _roster():
        return g_roster(G)

    def _team(coord_phone):
        cc = (G["_coordinators_all"]() or {}).get(G["_last9"](coord_phone)) or {}
        names = [str(n) for n in (cc.get("names") or set()) if n]
        phones = cc.get("agents") or set()
        if phones:
            m1 = G["web_phone_name_map"]() or {}
            m2 = G["web_contacts_phone_name"]() or {}
            for ph in phones:
                l9 = G["_last9"](ph)
                nm = m1.get(l9) or m2.get(l9)
                if nm:
                    names.append(nm)
        out, seen = [], set()
        for n in names:
            d = _display(n)
            if canon(d) not in seen:
                seen.add(canon(d))
                out.append(d)
        return out

    def _missed(now):
        return g_missed(G, now)

    def _reviews():
        return g_reviews(G)

    def _seen(day):
        return g_seen(G, day)

    def _activity(t0):
        sb = G.get("_sbdb")
        if sb is not None and hasattr(sb, "fetch_activity_actions") and sb.enabled():
            return sb.fetch_activity_actions(t0, (ACT_REMIND, ACT_NB_WA)) or []     # סינון בשרת — רק מה שנספר
        return G["_activity_fetch"](t0, today=True)

    def _fetch_src():
        now = _clock()
        day = _dt.datetime.fromtimestamp(now, _IL).date()
        t0 = day_bounds(day)[0]
        cfg = _safe(G["_load_config"])
        return {"day": day.isoformat(),
                "nb": cfg if _bad(cfg) else ((cfg or {}).get("nbStatus") or {}),
                "buyers": _safe(G["_fetch_manual_buyers"]),
                "bpages": _safe(lambda: G["_sbdb"].bpage_all()),
                "activity": _safe(lambda: _activity(t0)),
                "reviews": _safe(_reviews),
                "missed": _safe(lambda: _missed(now)),
                "seen": _safe(lambda: _seen(day)),
                "active": _safe(lambda: g_active(G, day)),
                "sigs": _safe(lambda: g_sigs(G, week_start(day))),
                "roster": _safe(_roster)}

    _src_box = {"t": 0.0, "v": None}
    _src_lock = _threading.Lock()

    def _today_iso():
        return _dt.datetime.fromtimestamp(_clock(), _IL).date().isoformat()

    def _src():
        """המקורות — עותק אחד לכל הצופים, טרי עד SRC_TTL ורק של היום (בלי 'ישן אבל מיידי' — אחרת
        הבנייה ברקע של כל צופה הייתה נשענת על מקורות ישנים, ואחרי חצות על אתמול)."""
        def fresh():
            v = _src_box["v"]
            return v is not None and (_clock() - _src_box["t"]) < SRC_TTL and v.get("day") == _today_iso()
        if fresh():
            return _src_box["v"]
        with _src_lock:
            if fresh():
                return _src_box["v"]
            v = _fetch_src()
            _src_box["t"], _src_box["v"] = _clock(), v
            return v

    def _cfg():
        try:
            return G["_load_config"]() or {}
        except Exception:
            return {}

    def _build(scope_key, roster_fn):
        def build():
            src = dict(_src())
            src["cfg"] = _cfg()
            day = _dt.date.fromisoformat(src["day"])
            if roster_fn is not None:
                src["roster"] = _safe(roster_fn)
            if scope_key.startswith("agent:"):
                src["active"] = None            # הסוכן שצופה בעצמו — תמיד מוצג
            return build_office(src, day, canon)
        key = "goals:" + _today_iso() + ":" + scope_key     # יום חדש = מפתח חדש = בנייה טרייה
        _keys_used.add(key)
        return G["_swr"](key, SRC_TTL, build, max_stale=1800)       # ישן עד 30 דק' מוחזר מיד, בנייה ברקע (המפתח כולל את היום)

    def _is_mgr(s):
        return s.get("drole") in ("manager", "developer")

    def _is_coord(s):
        return s.get("role") == "coordinator" or s.get("drole") == "coordinator"

    @app.route("/v2/api/goals/today", methods=["GET"])
    def goals_today():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "error": "unauthorized"}), 403
        mgr, coord = _is_mgr(s), (not _is_mgr(s)) and _is_coord(s)
        want = str(request.args.get("agent") or "").strip()
        team = _safe(lambda: _team(s.get("phone", ""))) if coord else None
        if want and not mgr and not coord:
            want = ""                                  # סוכן — תמיד הנתונים שלו
        if want and coord and (_bad(team) or canon(want) not in {canon(n) for n in team}):
            return jsonify({"ok": False, "error": "forbidden"}), 403
        res = {"ok": True, "can_edit": mgr}
        if want or not (mgr or coord):
            name = _display(want or s.get("name", ""))
            o = _build("agent:" + canon(name), lambda: [name])
            row = (o.get("rows") or [{}])[0] if o.get("rows") else None
            res.update(view="agent", me=({"counts": row["counts"], "targets": row["targets"]} if row else None),
                       total=None, agent=name)
        elif coord:
            def team_roster():
                if _bad(team):
                    raise team if isinstance(team, BaseException) else RuntimeError("team unavailable")
                return list(team)
            o = _build("team:" + G["_last9"](s.get("phone", "")), team_roster)
            res.update(view="team", me=None, total=o["total"], agents=o["rows"])
        else:
            o = _build("office", None)
            res.update(view="office", me=None, total=o["total"], agents=o["rows"])
        res["day"] = _today_iso()
        return jsonify(res)

    @app.route("/v2/api/goals/office", methods=["GET"])
    def goals_office():
        tv = (_os.environ.get("TV_KEY") or "").strip()
        k = (request.args.get("k") or "").strip()
        ok = bool(tv) and bool(k) and _hmac.compare_digest(k, tv)
        if not ok and not G["_web_auth"]():
            return jsonify({"ok": False, "error": "forbidden"}), 403
        o = _build("office", None)
        return jsonify({"ok": True, "total": o["total"]})   # סכומים בלבד — בלי שמות

    @app.route("/v2/api/goals/targets", methods=["POST"])
    def goals_targets():
        s = G["_web_auth"]()
        if not s or not _is_mgr(s):
            return jsonify({"ok": False, "error": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        tv = b.get("targets")
        if not isinstance(tv, dict):
            return jsonify({"ok": False, "error": "bad_request"}), 400
        vals = {}
        for k in DEFAULTS:
            if k in tv:
                n = _clip(tv[k])
                if n is not None:
                    vals[k] = n
        agent = _display(b.get("agent") or "")

        def fn(cfg):
            gl = cfg.get("v2_goals")
            if not isinstance(gl, dict):
                gl = {}
            if agent:
                ags = gl.get("agents") if isinstance(gl.get("agents"), dict) else {}
                hit = next((x for x in ags if canon(x) == canon(agent)), agent)
                cur = ags.pop(hit, None)
                cur = cur if isinstance(cur, dict) else {}
                cur.update(vals)
                ags[agent] = cur
                gl["agents"] = ags
            else:
                cur = gl.get("default") if isinstance(gl.get("default"), dict) else {}
                cur.update(vals)
                gl["default"] = cur
            cfg["v2_goals"] = gl
            return targets_for(cfg, agent, canon)

        ok, new = G["_config_mutate"](fn)
        if not ok:
            return jsonify({"ok": False, "error": "save_failed"}), 500
        for key in list(_keys_used):
            try:
                G["_cache_clear"](key)
            except Exception:
                pass
        det = (agent or "ברירת מחדל") + " · " + ", ".join(f"{k}={v}" for k, v in vals.items())
        G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), "יעדים — עדכון", det)
        return jsonify({"ok": True, "agent": agent, "targets": new})

    register_weekly(app, G)
