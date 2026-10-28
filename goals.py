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
    out = []
    for g in G["get_signings"](since_day.strftime("%d/%m/%Y"), "31/12/2099") or []:
        lk = str(g.get("commission_pct", "") or "").strip()
        out.append({"agent": g.get("agent", ""), "address": g.get("address", ""),
                    "type": G["_deal_label"](g.get("deal_type", "")), "signed": bool(lk),
                    "ts": g.get("received_at", "")})       # parse_ts — שעון ישראל
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
           "sigs": g_safe(G, lambda: g_sigs(G, first)),
           "roster": g_safe(G, lambda: g_roster(G))}
    return build_periods(src, day, lambda n: g_canon(G, n))


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
