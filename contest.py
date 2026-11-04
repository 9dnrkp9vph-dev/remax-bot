# contest.py — תחרות בין שתי קבוצות סוכנים: ליבת החישוב (פונקציות טהורות).
# גיוס = בלעדיות שנחתמה בתאריכי התחרות (נכס ייחודי לפי עוגן-כתובת, כמו goals.count_listings);
# פגישה = רשומת nbStatus עם status='meeting' שנקבעה (meeting_at) בתוך התחרות, גם ידנית.
# הרישום (ledger) שומר פגישות שנספרו: פגישה שנמחקה לפני מועדה יורדת, אחרי מועדה נשארת.
# השליפה, הראוטים וה-UI נבנים מעל הממשקים כאן.
import copy
import datetime as _dt

from goals import _IL, _anchor, _bad, day_bounds, parse_ts

WINNER_DAYS = 3
MAX_PTS = 1000


def _row(label, *members):
    return {"label": label, "members": list(members or [label])}


NOV_2026 = {
    "id": "2026-11", "name": "תחרות נובמבר", "start": "2026-11-01", "end": "2026-11-30",
    "pts": {"gius": 30, "meeting": 5},
    "groups": [
        {"name": "קבוצה א'",
         "rows": [_row("נדב רייזר"), _row("רויטל גל"), _row("אירנה אוברוב"), _row("עידן חלווה"), _row("אלמוג וייל"),
                  _row("בן ובנימין", "בינימין אביטן", "בן קדוש"), _row("עוז דנילוב"), _row("ליאור גורפינקל"),
                  _row("נחמי זקס"), _row("מירי ישראלוב")],
         "coords": ["נוי רבן", "נויה"]},
        {"name": "קבוצה ב'",
         "rows": [_row("אור צוקרמן"), _row("אלעד לוי"), _row("אלי ויהודית", "אלי שמול", "יהודית שמול"),
                  _row("חי חיים אלבז"), _row("יאיר חנוכאייב"), _row("רפי דה פיצ'וטו"), _row("ליקה אוברוב"),
                  _row("מתן הרשקו"), _row("קובי חמו"), _row("רוי אזולאי"), _row("ירין לוי")],
         "coords": ["הודיה צרויה", "אוצר בן חמו"]},
    ],
}


def contests(cfg):
    lst = ((cfg or {}).get("v2_contests") or {}).get("list") if isinstance(cfg, dict) else None
    return lst if lst else [NOV_2026]


def _d(s):
    return _dt.date.fromisoformat(str(s))


def pick(cfg, today):
    best = None
    for ct in contests(cfg):
        try:
            s, e = _d(ct["start"]), _d(ct["end"])
        except Exception:
            continue
        mode = "live" if s <= today <= e else "winner" if e < today <= e + _dt.timedelta(days=WINNER_DAYS) else None
        if mode and (best is None or s > best[2]):
            best = (ct, mode, s)
    return (best[0], best[1]) if best else (None, None)


def prev_month(start):
    last = start.replace(day=1) - _dt.timedelta(days=1)
    return last.replace(day=1), last


def validate(contest, canon):
    try:
        s, e = _d(contest.get("start")), _d(contest.get("end"))
    except Exception:
        return "תאריך התחלה או סיום לא תקין"
    if e < s:
        return "תאריך הסיום לפני תאריך ההתחלה"
    pts = contest.get("pts")
    if not isinstance(pts, dict):
        return "נקודות לגיוס ולפגישה חסרות"
    for k, label in (("gius", "גיוס"), ("meeting", "פגישה")):
        v = pts.get(k)
        if type(v) is not int or v < 0 or v > MAX_PTS:
            return "נקודות ל%s חייבות להיות מספר שלם בין 0 ל-%d" % (label, MAX_PTS)
    groups = contest.get("groups")
    if not isinstance(groups, list) or len(groups) != 2:
        return "בתחרות חייבות להיות בדיוק שתי קבוצות"
    for g in groups:   # [FIX4] מבנה — הגדרה שבורה לא נשמרת (ואחר כך לא מפילה את הניקוד)
        if not isinstance(g, dict) or not isinstance(g.get("name"), str) or not g["name"].strip():
            return "לכל קבוצה חייב להיות שם"
        rows, coords = g.get("rows"), g.get("coords", [])
        if not isinstance(rows, list) or not isinstance(coords, list):
            return "השורות או המתאמות בקבוצה \"%s\" לא תקינות" % g["name"]
        for r in rows:
            if not isinstance(r, dict) or not isinstance(r.get("label"), str) or not r["label"].strip():
                return "לכל שורה בקבוצה \"%s\" חייבת להיות תווית" % g["name"]
            mem = r.get("members")
            if not isinstance(mem, list) or not mem or not all(isinstance(m, str) and m.strip() for m in mem):
                return "בשורה \"%s\" חייב להיות לפחות חבר אחד" % r["label"]
        if not all(isinstance(n, str) for n in coords):
            return "שמות המתאמות בקבוצה \"%s\" לא תקינים" % g["name"]
    seen = set()
    for g in groups:
        names = [m for r in g.get("rows") or [] for m in r.get("members") or []] + list(g.get("coords") or [])
        for n in names:
            k = canon(n)
            if not k:
                continue
            if k in seen:
                return "השם \"%s\" מופיע יותר מפעם אחת בתחרות" % k
            seen.add(k)
    return None


def _generic(name):
    n = str(name or "").strip()
    return not n or n.startswith("מנהל")


def ledger_update(ledger, nb, contest, now, display):
    old = ledger or {}
    if _bad(nb) or not isinstance(nb, dict):
        return copy.deepcopy(old)
    b0, b1 = day_bounds(_d(contest["start"]))[0], day_bounds(_d(contest["end"]))[1]
    new, seen = {}, set()
    dkey = lambda ag, when, addr: (" ".join(str(ag or "").split()), when, " ".join(str(addr or "").split()))
    for key, rec in sorted(nb.items(), key=lambda kv: str(kv[0])):
        if not isinstance(rec, dict) or rec.get("status") != "meeting":
            continue
        at = parse_ts(rec.get("meeting_at"))
        if at is None or not (b0 <= at < b1):
            continue
        by = str(rec.get("by") or "").strip()
        nb_by = display(by, rec.get("by_phone")) if by else ""
        prev = str((old.get(key) or {}).get("by") or "")
        if _generic(nb_by) and prev and not _generic(prev):   # [FIX-m3] שם גנרי לא דורס שם אמיתי שכבר נרשם
            nb_by = prev
        ag = str(rec.get("agent") or by).strip()
        if _generic(ag):   # [02/11] מתאמת שקבעה בלי לבחור סוכן — הסוכן נשמר כ'מנהל'
            ag = display(ag, rec.get("by_phone")) or ag
        when = parse_ts(rec.get("date"))
        dk = dkey(ag, when, rec.get("addr"))
        if when is not None and dk in seen:   # [02/11 'נחמי זקס 9'] אותה פגישה שנשמרה כמה פעמים = פגישה אחת
            continue
        seen.add(dk)
        new[key] = {"agent": ag, "by": nb_by, "at": at, "when": when, "addr": str(rec.get("addr") or "")}
    for key, row in old.items():
        if key not in new:
            if row.get("addr") is not None and row.get("when") is not None and dkey(row.get("agent"), row.get("when"), row.get("addr")) in seen:
                continue
            w = row.get("when")
            if w is not None and w <= now:
                new[key] = copy.deepcopy(row)
    return new


def listing_anchor_times(names, bounds, sigs, canon):
    """עוגן-כתובת → זמן החתימה הראשונה בתקופה (נכס שנחתם פעמיים — הראשונה קובעת). None = החתימות לא נטענו."""
    if _bad(sigs):
        return None
    keys = {canon(n) for n in names}
    seen = {}
    for g in sigs or []:
        if g.get("type") != "בלעדיות" or not g.get("signed") or "בדיקה בדיקה" in str(g.get("address") or ""):
            continue
        ts = parse_ts(g.get("ts"))
        if ts is not None and bounds[0] <= ts < bounds[1] and canon(g.get("agent")) in keys:
            a = _anchor(g.get("address"))
            if a not in seen or ts < seen[a]:
                seen[a] = ts
    return seen


def listing_anchors(names, bounds, sigs, canon):
    t = listing_anchor_times(names, bounds, sigs, canon)
    return None if t is None else set(t)


# [POWER-DAY 04/11, אייל] יום שהמנהל קובע — הניקוד בתחרות כפול (גיוס 60, פגישה 10). גיוס לפי יום החתימה,
# פגישה לפי יום הקביעה (כמו הספירה הרגילה). תיקונים ידניים לא מוכפלים. התאריך מוסתר עד היום עצמו.
POWER_MULT = 2


def il_day(ts):
    return _dt.datetime.fromtimestamp(ts, _IL).date().isoformat()


def power_days(cfg, cid):
    """רשימת ה-Power Days של התחרות (תאריכי ISO, ממוינים) — v2_contest_power[cid] בקונפיג."""
    v = ((cfg or {}).get("v2_contest_power") or {}) if isinstance(cfg, dict) else {}
    lst = v.get(cid) if isinstance(v, dict) else None
    out = []
    for d in lst or []:
        try:
            out.append(_d(d).isoformat())
        except Exception:
            pass
    return sorted(set(out))


def _adj_sum(adjs, group, kind, label, canon):
    t = 0
    for a in adjs or []:
        if a.get("kind") == kind and canon(a.get("label")) == canon(label) and str(a.get("group")) in (group["name"], str(group.get("_i"))):
            t += int(a.get("pts") or 0)
    return t


# [03/11] מאז הפגישה נספרת רק למי שתיאם (14:35 שעון ישראל)
BOOKER_ONLY_FROM = _dt.datetime(2026, 11, 3, 14, 35, tzinfo=_IL).timestamp()


def score(contest, ledger, sigs, adjustments, canon, now, power=None):
    pts = contest["pts"]
    s, e = _d(contest["start"]), _d(contest["end"])
    cb = (day_bounds(s)[0], day_bounds(e)[1])
    today = _dt.datetime.fromtimestamp(now, _IL).date()
    pw = {d for d in (power or ()) if d <= today.isoformat()}   # יום עתידי לא נספר ולא נחשף
    mul = lambda ts: POWER_MULT if ts is not None and il_day(ts) in pw else 1
    rows_l = list((ledger or {}).values())
    # [03/11 אייל] מ-03/11 14:35 פגישה נספרת רק למי שתיאם: מתאמת — למתאמת, סוכן — לסוכן; בלי מתאם ידוע — לסוכן.
    # פגישות שנקבעו לפני כן — לפי הכלל הקודם (לסוכן, ומתאמת שקבעה לסוכן — גם לה), כי אייל יישר אותן ידנית.
    booker = lambda x: x.get("agent") if _generic(str(x.get("by") or "").strip()) else x.get("by")
    cut = contest.get("booker_only_from", BOOKER_ONLY_FROM)
    is_new = lambda x: (x.get("at") or 0) >= cut
    mem_of = lambda x: canon(booker(x)) if is_new(x) else canon(x.get("agent"))
    coord_of = lambda x, k: canon(booker(x)) == k if is_new(x) else (canon(x.get("by")) == k and canon(x.get("agent")) != k)
    out_groups, totals = [], []
    for gi, g in enumerate(contest["groups"]):
        g = dict(g, _i=gi)
        rows = []
        for r in g["rows"]:
            mem = {canon(m) for m in r["members"]}
            mine = [x for x in rows_l if mem_of(x) in mem]
            meetings = len(mine)
            m_pts = sum(mul(x.get("at")) * pts["meeting"] for x in mine)
            a = listing_anchor_times(r["members"], cb, sigs, canon)
            adj = _adj_sum(adjustments, g, "row", r["label"], canon)
            gius = None if a is None else len(a)
            g_pts = sum(mul(t) * pts["gius"] for t in (a or {}).values())
            pw_g = sum(1 for t in (a or {}).values() if mul(t) > 1)
            pw_m = sum(1 for x in mine if mul(x.get("at")) > 1)
            o = {"label": r["label"], "members": list(r["members"]), "meetings": meetings, "gius": gius,
                 "adj": adj, "points": g_pts + m_pts + adj,
                 "power_gius": pw_g, "power_meetings": pw_m,
                 "power_pts": sum(mul(t) * pts["gius"] for t in (a or {}).values() if mul(t) > 1) +
                 pw_m * POWER_MULT * pts["meeting"]}
            if a is None:
                o["partial"] = True
            rows.append(o)
        rows.sort(key=lambda x: -x["points"])
        for i, o in enumerate(rows):
            o["rank"] = rows[i - 1]["rank"] if i and rows[i - 1]["points"] == o["points"] else i + 1
        coords = []
        for n in g.get("coords") or []:
            k = canon(n)
            cm = [x for x in rows_l if coord_of(x, k)]
            adj = _adj_sum(adjustments, g, "coord", n, canon)
            pw_m = sum(1 for x in cm if mul(x.get("at")) > 1)
            coords.append({"name": n, "meetings": len(cm), "adj": adj,
                           "points": sum(mul(x.get("at")) * pts["meeting"] for x in cm) + adj,
                           "power_meetings": pw_m, "power_pts": pw_m * POWER_MULT * pts["meeting"]})
        total = sum(o["points"] for o in rows)
        totals.append(total)
        out_groups.append({"name": g["name"], "total": total, "rows": rows, "coords": coords})
    out = {"id": contest["id"], "name": contest["name"], "start": contest["start"], "end": contest["end"],
           "days_left": max(0, (e - today).days + 1), "pts": dict(pts), "groups": out_groups,
           "leader": None if totals[0] == totals[1] else (0 if totals[0] > totals[1] else 1),
           "power_today": today.isoformat() in pw, "power_days": sorted(pw), "power_mult": POWER_MULT}
    if _bad(sigs):   # [FIX2] בלי חתימות הסכומים חסרים — אין מובילה, והתצוגה מראה 'לא זמין'
        out["partial"] = True
        out["leader"] = None
    return out


# ── ראוטים ──────────────────────────────────────────────────────────────────
import copy as _copy
import hmac as _hmac
import os as _os
import threading as _threading
import time as _time
import uuid as _uuid

import goals as _goals


def _now():
    return _time.time()


# ── [POWER-DAY 04/11] הודעת וואטסאפ ב-09:00 למשתתפים, למתאמות ולבעלי המשרד ───────────────
POWER_HOUR, POWER_END_HOUR = 9, 20          # שולחים רק בין 09:00 ל-20:00 (יום שנקבע אחרי 09:00 — מיד עם השמירה)
POWER_RETRY_SEC, POWER_MAX_TRIES = 900, 8
POWER_EXTRA_DEFAULT = "אייל שמול,אודי שמול,מתן ביטון"


def power_text(ct):
    """שורה אחת — מחוץ לחלון 24 השעות ההודעה עוברת בתבנית, ופרמטר תבנית לא מקבל ירידות שורה."""
    p = ct.get("pts") or {}
    g, m = int(p.get("gius") or 0) * POWER_MULT, int(p.get("meeting") or 0) * POWER_MULT
    nm = str(ct.get("name") or "התחרות").strip()
    return ("היום POWER DAY ב%s! כל גיוס בלעדיות שווה היום %d נקודות וכל פגישה %d — פי שניים. "
            "יום אחד יכול להפוך את הטבלה. מי לוקח אותו?") % (nm, g, m)


def power_recipients(ct, extras, canon):
    """כל המשתתפים בשתי הקבוצות + המתאמות + בעלי המשרד; כל אדם פעם אחת."""
    out, seen = [], set()
    names = [m for g in ct.get("groups") or [] for r in g.get("rows") or [] for m in r.get("members") or []]
    names += [n for g in ct.get("groups") or [] for n in g.get("coords") or []]
    names += list(extras or [])
    for n in names:
        n = str(n or "").strip()
        k = canon(n)
        if n and k and k not in seen:
            seen.add(k)
            out.append(n)
    return out


def power_due(now_il, days, blocked):
    """היום, אם הוא Power Day ועכשיו בין 09:00 ל-20:00 ולא שבת/חג/השתקה. אחרת None."""
    d = now_il.date().isoformat()
    if blocked or d not in (days or ()) or not (POWER_HOUR <= now_il.hour < POWER_END_HOUR):
        return None
    return d


def power_pending(names, rec, now, canon):
    out = []
    for n in names:
        x = (rec or {}).get(canon(n)) or {}
        if x.get("r") in ("sent", "no_phone") or int(x.get("tries") or 0) >= POWER_MAX_TRIES:
            continue
        if x and now - float(x.get("ts") or 0) < POWER_RETRY_SEC:
            continue
        out.append(n)
    return out


def power_sent_summary(cfg, cid):
    st = (((cfg or {}).get("v2_contest_power_sent") or {}).get(cid)) or {}
    out = {}
    for d, rec in st.items():
        if isinstance(rec, dict):
            c = {"sent": 0, "fail": 0, "no_phone": 0}
            for x in rec.values():
                r = (x or {}).get("r")
                if r in c:
                    c[r] += 1
            out[d] = c
    return out


def power_run(G, now, canon):
    """סבב אחד: אם היום Power Day והגיעה השעה — שולח למי שטרם קיבל. מחזיר כמה נשלחו."""
    if (_os.environ.get("CONTEST_POWER_WA", "1") or "1").strip() == "0" or not G["_d360_on"]():
        return 0
    now_il = _dt.datetime.fromtimestamp(now, _IL)
    try:
        blocked = bool(G["_quiet_mode"]()) or bool(G["_switch_off"]("wa_official_off"))
    except Exception:
        blocked = True
    cfg = G["_load_config"]() or {}
    ct, mode = pick(cfg, now_il.date())
    if not ct or mode != "live":
        return 0
    cid = ct["id"]
    day = power_due(now_il, power_days(cfg, cid), blocked)
    if not day:
        return 0
    rec = _copy.deepcopy(((((cfg.get("v2_contest_power_sent") or {}).get(cid)) or {}).get(day)) or {})
    raw = (_os.environ.get("CONTEST_POWER_EXTRA") or POWER_EXTRA_DEFAULT)
    names = power_recipients(ct, [x.strip() for x in raw.split(",") if x.strip()], canon)
    todo = power_pending(names, rec, now, canon)
    if not todo:
        return 0
    ag_ph = G["fetch_agents_phones"]() or {}
    try:
        vph = G["_agent_vphones9"]() or set()
    except Exception:
        vph = set()
    text = power_text(ct)
    n_sent = 0
    for n in todo:
        wa = _goals._weekly_phone(G, n, ag_ph, vph)
        if not wa:
            res = "no_phone"
        else:
            try:
                res = "sent" if G["send_text"](wa, text) else "fail"
            except Exception:
                res = "fail"
        x = rec.get(canon(n)) or {}
        rec[canon(n)] = {"n": n, "r": res, "ts": now, "tries": int(x.get("tries") or 0) + 1}
        n_sent += res == "sent"
        G["_log_activity"]("אפי", "system", "", "תחרות — הודעת Power Day " +
                           {"sent": "נשלחה", "fail": "נכשלה", "no_phone": "אין טלפון"}[res], n[:60])

    def _mut(c, _cid=cid, _d=day, _v=rec):
        m = c.get("v2_contest_power_sent") if isinstance(c.get("v2_contest_power_sent"), dict) else {}
        per = m.get(_cid) if isinstance(m.get(_cid), dict) else {}
        per[_d] = _v
        m[_cid] = per
        c["v2_contest_power_sent"] = m
    try:
        G["_config_mutate"](_mut)
    except Exception:
        pass
    return n_sent


_LAST_GOOD = {}   # [FIX2] הלוח התקין האחרון לכל תחרות — כשהחתימות נופלות מציגים אותו (stale) ולא סכומים חסרים
_GEN = [0]        # [FIX-m2] דור המטמון: עולה בכל שמירה/תיקון, כך שבנייה ישנה שעוד רצה לא ממלאת את המפתח הגלוי


def register(app, G):
    from flask import jsonify, request

    def canon(n):
        n = str(n or "").strip()
        try:
            n = G["_canon_agent_name"](n) or n
        except Exception:
            pass
        return G["_canon_key"](n)

    def display(by, ph):
        return G["_display_name_for"](by or "", ph or "")

    def _today():
        return _dt.datetime.fromtimestamp(_now(), _IL).date()

    def _real(s):   # [FIX1] מנהלים ומתאמות נכנסים בשם הגנרי 'מנהל' — השם האמיתי לפי הטלפון
        try:
            return display(s.get("name"), s.get("phone")) or s.get("name")
        except Exception:
            return s.get("name")

    def _is_coord(s, cfg, ct):
        if s.get("role") == "coordinator" or s.get("drole") == "coordinator":
            return True
        k = canon(_real(s))
        if k:
            for it in (cfg or {}).get("coordinators") or []:
                if isinstance(it, dict) and k in (canon(it.get("coordinator")), canon(it.get("name"))):
                    return True
            try:
                if ct and any(canon(n) == k for g in ct.get("groups") or [] for n in g.get("coords") or []):
                    return True
            except Exception:
                pass
        try:
            if G["_last9"](s.get("phone")) in (G["_coordinators_all"]() or {}):
                return True
        except Exception:
            pass
        return False

    def _can_edit(s, cfg):
        if s.get("drole") not in ("manager", "developer"):
            return False
        return not _is_coord(s, cfg, pick(cfg, _today())[0] or _latest(cfg))

    def _latest(cfg):   # [FIX-m4] בלי תחרות פעילה — האחרונה לפי תאריך התחלה
        cts = [x for x in contests(cfg) if isinstance(x, dict)]
        return max(cts, key=lambda x: str(x.get("start") or "")) if cts else None

    def _me(s, ct):
        k = canon(_real(s))
        if not k or not ct:
            return None
        try:
            for gi, g in enumerate(ct["groups"]):
                for r in g["rows"]:
                    if k in {canon(m) for m in r["members"]}:
                        return {"group": gi, "kind": "row", "label": r["label"]}
                for n in g.get("coords") or []:
                    if canon(n) == k:
                        return {"group": gi, "kind": "coord", "label": n}
        except Exception:
            pass
        return None

    def _unmatched(ct):   # [FIX5] שמות בתחרות שלא נמצאו באפי (לעורכים) — בלי מקור שמות לא מחזירים כלום
        known = set()
        try:
            known |= {canon(n) for n in (G["fetch_agents_phones"]() or {})}
        except Exception:
            pass
        try:
            known |= {canon(n) for n in (_goals.g_roster(G) or [])}
        except Exception:
            pass
        known.discard("")
        if not known or not ct:
            return None
        out = []
        try:
            for g in ct.get("groups") or []:
                for n in [m for r in g.get("rows") or [] for m in r.get("members") or []] + list(g.get("coords") or []):
                    if canon(n) and canon(n) not in known and n not in out:
                        out.append(n)
        except Exception:
            return None
        return out

    def _build(ct, cfg):
        now = _now()
        lid = ct["id"]
        old = ((cfg.get("v2_contest_ledger") or {}).get(lid)) or {}
        new = ledger_update(old, cfg.get("nbStatus"), ct, now, display)
        if new != old:
            def fn(c):
                lg = c.get("v2_contest_ledger")
                if not isinstance(lg, dict):
                    lg = {}
                lg[lid] = new
                c["v2_contest_ledger"] = lg
            G["_config_mutate"](fn)
        sigs = _goals.g_safe(G, lambda: _goals.g_sigs(G, _d(ct["start"])))   # [POWER-DAY] בלי P.D. — אין צורך בחודש הקודם
        if isinstance(sigs, Exception):
            sigs = None
        adj = ((cfg.get("v2_contest_adj") or {}).get(lid)) or []
        b = score(ct, new, sigs, adj, canon, now, power_days(cfg, lid))
        if b.get("partial"):
            last = _LAST_GOOD.get(lid)
            if last:
                return dict(_copy.deepcopy(last), stale=True)
        else:
            _LAST_GOOD[lid] = _copy.deepcopy(b)
        return b

    @app.route("/v2/api/contest", methods=["GET"])
    def contest_get():
        tv = (_os.environ.get("TV_KEY") or "").strip()
        k = (request.args.get("k") or "").strip()
        s = G["_web_auth"]()
        if not (tv and k and _hmac.compare_digest(k, tv)) and not s:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        s = s or {}
        cfg = G["_load_config"]() or {}
        today = _today()
        ct, mode = pick(cfg, today)
        board = None
        if ct:
            try:   # [FIX4] הגדרה שבורה או מקור שנופל — אין לוח, לא 500
                board = G["_swr"]("contest:%s:%s:%d" % (ct["id"], today.isoformat(), _GEN[0]), 120,
                                  lambda: _build(ct, G["_load_config"]() or {}), max_stale=600)
            except Exception as e:
                lg = G.get("log")
                if lg:
                    try:
                        lg.warning("contest build failed: %s" % e)
                    except Exception:
                        pass
                board = None
        edit = bool(s) and _can_edit(s, cfg)
        adjs = []
        if ct and s:   # רשימת התיקונים לסימן שליד הניקוד; מי ביצע — רק לעורכים
            for a in ((cfg.get("v2_contest_adj") or {}).get(ct["id"])) or []:
                if isinstance(a, dict):
                    adjs.append({k: a.get(k) for k in ("id", "group", "kind", "label", "pts", "reason", "at")
                                 + (("by",) if edit else ())})
        dfn = None
        if edit:       # הגדרת התחרות לגיליון העריכה; בלי תחרות פעילה — האחרונה (לתחרות חדשה בהעתקה)
            dfn = ct
            if not dfn:
                cts = [x for x in contests(cfg) if isinstance(x, dict)]
                dfn = max(cts, key=lambda x: str(x.get("start") or "")) if cts else None
            dfn = _copy.deepcopy(dfn) if dfn else None
        out = {"ok": True, "mode": mode, "board": board, "me": _me(s, ct) if s else None,
               "can_edit": edit, "adjustments": adjs, "def": dfn}
        if edit:
            out["unmatched"] = _unmatched(ct or dfn) or []
            if ct:   # [POWER-DAY] כל הימים (גם עתידיים) — רק לעורכים; השאר רואים רק את מה שכבר הגיע (בלוח)
                out["power_all"] = power_days(cfg, ct["id"])
                out["power_sent"] = power_sent_summary(cfg, ct["id"])
        return jsonify(out)

    def _mgr():
        s = G["_web_auth"]()
        if not s or not _can_edit(s, G["_load_config"]() or {}):
            return None
        return s

    def _clear(cid):
        for d in (_today(), _today() + _dt.timedelta(days=1), _today() - _dt.timedelta(days=1)):
            G["_cache_clear"]("contest:%s:%s:%d" % (cid, d.isoformat(), _GEN[0]))
        _GEN[0] += 1

    def _log(s, action, detail):
        G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), action, detail)

    @app.route("/v2/api/contest/save", methods=["POST"])
    def contest_save():
        s = _mgr()
        if not s:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        cfg = G["_load_config"]() or {}
        if b.get("copy_from"):
            src = next((x for x in contests(cfg) if x.get("id") == b.get("copy_from")), None)
            if not src:
                return jsonify({"ok": False, "error": "התחרות המקורית לא נמצאה"}), 400
            ct = _copy.deepcopy(src)
            for k in ("id", "name", "start", "end"):
                ct[k] = str(b.get(k) or "").strip()
            if not ct["id"] or not ct["name"]:
                return jsonify({"ok": False, "error": "חסר מזהה או שם"}), 400
            if any(x.get("id") == ct["id"] for x in contests(cfg)):
                return jsonify({"ok": False, "error": "מזהה התחרות כבר קיים"}), 400
        else:
            ct = b.get("contest")
            if not isinstance(ct, dict) or not str(ct.get("id") or "").strip():
                return jsonify({"ok": False, "error": "חסרה תחרות"}), 400
        err = validate(ct, canon)
        if err:
            return jsonify({"ok": False, "error": err}), 400

        def fn(c):
            v = c.get("v2_contests")
            lst = list(v.get("list") or []) if isinstance(v, dict) else []
            if not lst:
                lst = [_copy.deepcopy(NOV_2026)]
            for i, x in enumerate(lst):
                if x.get("id") == ct["id"]:
                    lst[i] = ct
                    break
            else:
                lst.append(ct)
            c["v2_contests"] = {"list": lst}
        G["_config_mutate"](fn)
        _clear(ct["id"])
        _log(s, "תחרות — עדכון", ct.get("name", ""))
        return jsonify({"ok": True})

    @app.route("/v2/api/contest/adjust", methods=["POST"])
    def contest_adjust():
        s = _mgr()
        if not s:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        cid = str(b.get("contest") or "")
        cfg = G["_load_config"]() or {}
        if not any(x.get("id") == cid for x in contests(cfg)):
            return jsonify({"ok": False, "error": "התחרות לא נמצאה"}), 400
        if b.get("delete"):
            aid = str(b["delete"])
            hit = {}

            def fn(c):
                m = c.get("v2_contest_adj")
                m = m if isinstance(m, dict) else {}
                keep = []
                for a in m.get(cid) or []:
                    (hit.update(a) if a.get("id") == aid else keep.append(a))
                m[cid] = keep
                c["v2_contest_adj"] = m
            G["_config_mutate"](fn)
            if not hit:
                return jsonify({"ok": False, "error": "התיקון לא נמצא"}), 400
            _clear(cid)
            _log(s, "תחרות — מחיקת תיקון", "%s · %s · %s" % (hit.get("label"), hit.get("pts"), hit.get("reason")))
            return jsonify({"ok": True})
        p, reason, label = b.get("pts"), str(b.get("reason") or "").strip(), str(b.get("label") or "").strip()
        if isinstance(p, bool) or not isinstance(p, int) or p == 0 or abs(p) > MAX_PTS:
            return jsonify({"ok": False, "error": "נקודות חייבות להיות מספר שלם בין -1000 ל-1000, לא אפס"}), 400
        if not (1 <= len(reason) <= 200):
            return jsonify({"ok": False, "error": "חובה לציין סיבה (עד 200 תווים)"}), 400
        if b.get("kind") not in ("row", "coord") or type(b.get("group")) is not int or b.get("group") not in (0, 1) or not label:
            return jsonify({"ok": False, "error": "פרטי התיקון לא תקינים"}), 400
        a = {"id": _uuid.uuid4().hex[:8], "group": b["group"], "kind": b["kind"], "label": label, "pts": p,
             "reason": reason, "by": _real(s) or "", "at": _now()}

        def fn2(c):
            m = c.get("v2_contest_adj")
            m = m if isinstance(m, dict) else {}
            m[cid] = list(m.get(cid) or []) + [a]
            c["v2_contest_adj"] = m
        G["_config_mutate"](fn2)
        _clear(cid)
        _log(s, "תחרות — תיקון ידני", "%s · %s · %s" % (label, p, reason))
        return jsonify({"ok": True, "id": a["id"]})


    _pw = {"t": None, "pid": None}
    _pw_lock = _threading.Lock()

    def _pw_tick():
        try:
            power_run(G, _now(), canon)
        except Exception as e:
            lg = G.get("log")
            if lg:
                try:
                    lg.error("contest power day: %s" % e)
                except Exception:
                    pass

    def _pw_loop():
        _time.sleep(60)
        while True:
            _pw_tick()
            _time.sleep(120)

    @app.before_request
    def _contest_power_kick():   # הלולאה נולדת בתוך תהליך ההגשה (הלקח מ-15/09: thread מזמן הייבוא מת ב-fork)
        if _pw["t"] is not None and _pw["t"].is_alive() and _pw["pid"] == _os.getpid():
            return
        with _pw_lock:
            if _pw["t"] is not None and _pw["t"].is_alive() and _pw["pid"] == _os.getpid():
                return
            _pw["t"] = _threading.Thread(target=_pw_loop, daemon=True, name="contest-power")
            _pw["t"].start()
            _pw["pid"] = _os.getpid()

    @app.route("/v2/api/contest/power", methods=["POST"])
    def contest_power():
        s = _mgr()
        if not s:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        cid = str(b.get("contest") or "")
        cfg = G["_load_config"]() or {}
        ct = next((x for x in contests(cfg) if x.get("id") == cid), None)
        if not ct:
            return jsonify({"ok": False, "error": "התחרות לא נמצאה"}), 400
        try:
            day = _d(b.get("date"))
        except Exception:
            return jsonify({"ok": False, "error": "תאריך לא תקין"}), 400
        if not (_d(ct["start"]) <= day <= _d(ct["end"])):
            return jsonify({"ok": False, "error": "התאריך מחוץ לתאריכי התחרות"}), 400
        on, d = bool(b.get("on", True)), day.isoformat()

        def fn(c):
            m = c.get("v2_contest_power") if isinstance(c.get("v2_contest_power"), dict) else {}
            lst = set(power_days(c, cid))
            (lst.add(d) if on else lst.discard(d))
            m[cid] = sorted(lst)
            c["v2_contest_power"] = m
        G["_config_mutate"](fn)
        _clear(cid)
        _log(s, "תחרות — Power Day " + ("נקבע" if on else "בוטל"), d)
        if on and day == _today():   # נקבע להיום — ההודעה יוצאת מיד (אם כבר 09:00 ועד 20:00)
            _threading.Thread(target=_pw_tick, daemon=True, name="contest-power-now").start()
        return jsonify({"ok": True, "power_all": power_days(G["_load_config"]() or {}, cid)})


# ── UI: הכרטיס המשותף (סטורי / טלוויזיה / מסך) ───────────────────────────────
# מוזרק ב-<!--CONTEST_KIT--> (המסך /v2/contest ב-effie_v2; בהמשך גם הבית והטלוויזיה).
V2_CONTEST_KIT = r"""<style>
  .ck{font-family:'Heebo',sans-serif;background:linear-gradient(165deg,#0E1D33 0%,#16294A 55%,#2C4C77 100%);color:#fff;
      border-radius:22px;padding:16px 18px 18px;display:flex;flex-direction:column;text-align:right}
  .ck.story{min-height:100%;border-radius:0;padding:4px 18px 20px;background:transparent}
  .ck-top{display:flex;justify-content:space-between;align-items:center;font-size:13px;opacity:.8}
  .ck-trophy{width:58px;height:58px;border-radius:50%;background:rgba(228,197,107,.14);border:1.5px solid #E4C56B;
      display:flex;align-items:center;justify-content:center;margin:16px auto 8px}
  .ck-h{text-align:center;font-size:25px;font-weight:800;line-height:1.25}
  .ck-sub{text-align:center;font-size:14px;opacity:.8;margin-top:2px}
  .ck-vs{display:flex;align-items:stretch;gap:10px;margin-top:22px}
  .ck-team{flex:1;border-radius:20px;padding:14px 10px;text-align:center;background:rgba(255,255,255,.07);
      border:1.5px solid rgba(255,255,255,.12);position:relative;min-width:0}
  .ck-team.lead{background:rgba(228,197,107,.13);border-color:#E4C56B}
  .ck-team .nm{font-size:15px;font-weight:700}
  .ck-team .pts{font-size:40px;font-weight:800;line-height:1.1;margin-top:6px;font-variant-numeric:tabular-nums}
  .ck-team.lead .pts{color:#E4C56B}
  .ck-team .u{font-size:12px;opacity:.75}
  .ck-team .mine{position:absolute;top:-11px;left:50%;transform:translateX(-50%);background:#fff;color:#1E3A5F;
      font-size:12px;font-weight:800;border-radius:99px;padding:2px 10px;white-space:nowrap}
  .ck-vsx{align-self:center;font-weight:800;opacity:.6;font-size:14px}
  .ck-track{height:10px;border-radius:99px;background:rgba(255,255,255,.12);margin:12px 4px 0;overflow:hidden;display:flex}
  .ck-track i{display:block;height:100%;background:rgba(255,255,255,.45)}
  .ck-track i.lead{background:#E4C56B}
  .ck-gap{margin-top:12px;text-align:center;font-size:14px}
  .ck-gap b{color:#E4C56B}
  .ck-me{margin-top:20px;background:#fff;color:#14192B;border-radius:20px;padding:14px}
  .ck-me .t{font-size:13px;color:#5B6472;font-weight:600}
  .ck-me .big{font-size:30px;font-weight:800;color:#1E3A5F;margin-top:4px;font-variant-numeric:tabular-nums}
  .ck-me .big small{font-size:14px;color:#5B6472;font-weight:600}
  .ck-chips{display:flex;gap:8px;margin-top:10px}
  .ck-chip{flex:1;background:#F6F3EC;border-radius:14px;padding:8px;text-align:center}
  .ck-chip b{display:block;font-size:18px;color:#1E3A5F}
  .ck-chip span{font-size:12px;color:#5B6472}
  .ck-chip.g b{color:#7A5E1C}
  .ck-push{margin-top:10px;font-size:13px;color:#7A5E1C;font-weight:700;text-align:center}
  .ck-full{display:flex;align-items:center;justify-content:center;min-height:46px;border-radius:14px;margin-top:18px;
      background:#2E6BD6;color:#fff;font:700 15px 'Heebo',sans-serif;text-decoration:none}
  .ck-top3{margin-top:20px;background:#fff;color:#14192B;border-radius:20px;padding:6px 14px}
  .ck-top3 .r{display:flex;align-items:center;gap:10px;min-height:48px;border-top:1px solid #F0ECE3}
  .ck-top3 .r:first-child{border-top:0}
  .ck-top3 .pos{width:28px;height:28px;border-radius:50%;background:#F6F3EC;color:#7A5E1C;font-weight:800;font-size:13px;
      display:flex;align-items:center;justify-content:center;flex:none}
  .ck-top3 .r:first-child .pos{background:#E4C56B;color:#231700}
  .ck-top3 .nm{flex:1;min-width:0;font-weight:700;font-size:14.5px}
  .ck-top3 .nm small{display:block;font-weight:500;font-size:12px;color:#5B6472}
  .ck-top3 .p{font-weight:800;color:#1E3A5F;font-variant-numeric:tabular-nums}
  /* [TV-BIG 03/11] אייל: "יותר מקום לתחרות בטלוויזיה" — הכרטיס ממלא את כל המסך, כל המשתתפים + המתאמות */
  .ck.tv{padding:clamp(14px,2vh,26px) 34px clamp(14px,2.2vh,28px);border-radius:28px;height:100%;box-sizing:border-box;min-height:0}
  .ck.tv .ck-top{font-size:22px}
  .ck-tvh{display:flex;align-items:center;justify-content:center;gap:22px;margin-top:4px}
  .ck.tv .ck-trophy{width:64px;height:64px;margin:0;flex:none}
  .ck.tv .ck-h{font-size:clamp(34px,4.6vh,52px);text-align:right}
  .ck.tv .ck-sub,.ck.tv .ck-gap{font-size:clamp(18px,2.3vh,26px);text-align:right}
  .ck-cols{display:flex;gap:28px;margin-top:clamp(10px,1.6vh,20px);flex:1;min-height:0}
  .ck-col{flex:1;min-width:0;border-radius:24px;padding:14px 22px;background:rgba(255,255,255,.07);border:2px solid rgba(255,255,255,.12);
      display:flex;flex-direction:column;min-height:0}
  .ck-col.lead{background:rgba(228,197,107,.13);border-color:#E4C56B}
  .ck-col .ch{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding-bottom:6px}
  .ck-col .cn{font-size:clamp(28px,3.6vh,40px);font-weight:800}
  .ck-col .cp{font-size:clamp(48px,6.4vh,76px);font-weight:800;line-height:1;font-variant-numeric:tabular-nums}
  .ck-col.lead .cp{color:#E4C56B}
  .ck-col .cp small{font-size:20px;font-weight:600;opacity:.75;margin-inline-start:8px}
  .ck-col .crs{flex:1;min-height:0;display:flex;flex-direction:column}
  .ck-col .cr{flex:1 1 0;min-height:0;display:flex;align-items:center;gap:14px;font-size:clamp(17px,2.6vh,30px);
      border-top:1px solid rgba(255,255,255,.12)}
  .ck-col .cr.z{opacity:.5}
  .ck-col .cr .pos{width:1.4em;height:1.4em;border-radius:50%;background:rgba(255,255,255,.12);font-weight:800;font-size:.72em;
      display:flex;align-items:center;justify-content:center;flex:none}
  .ck-col .crs .cr:first-child .pos{background:#E4C56B;color:#231700}
  .ck-col .cr .l{flex:1;min-width:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ck-col .cr .l small{font-size:.65em;font-weight:500;opacity:.7;margin-inline-start:10px}
  .ck-col .cr .v{font-weight:800;font-variant-numeric:tabular-nums}
  .ck-col .cct{font-size:clamp(14px,1.8vh,19px);font-weight:700;color:#E4C56B;margin-top:8px;padding-top:6px;border-top:2px solid rgba(228,197,107,.35)}
  .ck-col .cc .cr{flex:none;min-height:clamp(30px,4.6vh,52px)}
  .ck.tv .ck-track{height:14px;margin-top:clamp(10px,1.6vh,20px);flex:none}
  /* [POWER-DAY 04/11] יום ניקוד כפול — באנר זהב */
  .ck-pow{margin-top:14px;border-radius:18px;padding:12px 14px;background:linear-gradient(135deg,#E4C56B,#C29435);color:#231700;
      text-align:center;box-shadow:0 6px 20px rgba(194,148,53,.35)}
  .ck-pow b{display:block;font-size:22px;font-weight:900;letter-spacing:.02em}
  .ck-pow span{font-size:14px;font-weight:700}
  .ck.tv .ck-pow{margin-top:clamp(8px,1.2vh,14px);padding:clamp(8px,1.2vh,14px) 22px;display:flex;align-items:center;
      justify-content:center;gap:26px;flex:none}
  .ck.tv .ck-pow b{display:inline;font-size:clamp(28px,3.8vh,44px)}
  .ck.tv .ck-pow span{font-size:clamp(18px,2.4vh,28px)}
  .ck-pow-strip{margin:14px 46px 0;border-radius:18px;padding:10px 22px;background:linear-gradient(135deg,#E4C56B,#C29435);color:#231700;
      display:flex;align-items:center;justify-content:center;gap:24px;font-family:'Heebo',sans-serif;box-shadow:0 6px 24px rgba(194,148,53,.4)}
  .ck-pow-strip b{font-size:34px;font-weight:900;letter-spacing:.02em}
  .ck-pow-strip span{font-size:22px;font-weight:700}
</style>
<script>
var CONTEST_MONTHS = ['בינואר','בפברואר','במרץ','באפריל','במאי','ביוני','ביולי','באוגוסט','בספטמבר','באוקטובר','בנובמבר','בדצמבר'];
var CONTEST_TROPHY = '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#E4C56B" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>';
function cEsc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function cEnc(s){ return encodeURIComponent(String(s == null ? '' : s)).replace(/'/g, '%27'); }
function cNum(v){ return (typeof v === 'number' && isFinite(v)) ? v : null; }
function cShow(v){ var x = cNum(v); return x == null ? '—' : String(x); }
/* [POWER-DAY 04/11] יום ניקוד כפול — מוצג רק ביום עצמו (השרת לא חושף ימים עתידיים) */
function contestPowerToday(b){ return !!(b && b.power_today); }
function contestPowerPts(b){
  var p = (b && b.pts) || {}, m = cNum(b && b.power_mult) || 2;
  return {g: (cNum(p.gius) || 0) * m, m: (cNum(p.meeting) || 0) * m};
}
function contestPowerBanner(b){
  if (!contestPowerToday(b)) return '';
  var x = contestPowerPts(b);
  return '<div class="ck-pow"><b>היום POWER DAY</b><span>ניקוד כפול · גיוס ' + x.g + ' · פגישה ' + x.m + '</span></div>';
}
function contestPowerStrip(j){
  var b = j && j.board;
  if (!contestPowerToday(b)) return '';
  var x = contestPowerPts(b);
  return '<div class="ck-pow-strip"><b>היום POWER DAY</b><span>ניקוד כפול בתחרות · גיוס ' + x.g + ' · פגישה ' + x.m + '</span></div>';
}
function contestHasPower(b){ return !!(b && b.power_days && b.power_days.length); }
function contestToday(){
  try{ return new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Jerusalem', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date()); }
  catch(e){ var d = new Date(); return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
}
/* מטמון לקוח: לאותו טוקן ולאותו יום בלבד */
function contestCachePut(tok, j){
  try{ if (j && j.ok) localStorage.setItem('v2c:contest', JSON.stringify({tok: tok, day: contestToday(), j: j})); }catch(e){}
}
function contestCacheGet(tok, day){
  try{
    var c = JSON.parse(localStorage.getItem('v2c:contest') || 'null');
    if (c && c.tok === tok && c.day === (day || contestToday()) && c.j && c.j.ok) return c.j;
  }catch(e){}
  return null;
}
/* [FIX2] לוח חלקי (החתימות לא נטענו) — בלי סכומי קבוצות ובלי מובילה */
function contestPartial(b){ return !!(b && b.partial); }
function contestTotal(b, g){ return contestPartial(b) ? 'לא זמין' : cShow(g && g.total); }
function contestLead(b){ return contestPartial(b) ? null : (b ? b.leader : null); }
function contestGapGius(gap, ptsGius){ return ptsGius > 0 ? Math.round(gap / ptsGius) : 0; }
function contestSplit(s){ return String(s || '').split(/[,،]/).map(function(x){ return x.trim(); }).filter(Boolean); }
function contestRange(a, b){
  var x = String(a || '').split('-'), y = String(b || '').split('-');
  if (x.length < 3 || y.length < 3) return '';
  var d1 = +x[2], d2 = +y[2], m1 = CONTEST_MONTHS[+x[1] - 1] || '', m2 = CONTEST_MONTHS[+y[1] - 1] || '';
  return (x[0] === y[0] && x[1] === y[1]) ? d1 + '–' + d2 + ' ' + m2 : d1 + ' ' + m1 + ' – ' + d2 + ' ' + m2;
}
function contestRules(p){
  p = p || {};
  return '<b>גיוס בבלעדיות = ' + cShow(p.gius) + '</b> (רק אחרי שנחתם) · <b>פגישה = ' + cShow(p.meeting) +
    '</b> (לפי יום הקביעה) · <b>Power Day</b> = ניקוד כפול, ביום שהמנהל קובע';
}
function contestDays(n){
  n = cNum(n);
  return n == null ? '' : n <= 0 ? 'התחרות הסתיימה' : n === 1 ? 'יום אחרון' : 'עוד ' + n + ' ימים';
}
/* השורה / המתאמת של המשתמש */
function contestMine(j){
  var b = j && j.board, me = j && j.me;
  if (!b || !me || !b.groups || !b.groups[me.group]) return null;
  var g = b.groups[me.group];
  if (me.kind === 'coord'){
    for (var i = 0; i < (g.coords || []).length; i++) if (g.coords[i].name === me.label) return {kind: 'coord', r: g.coords[i], g: g};
    return null;
  }
  for (var k = 0; k < (g.rows || []).length; k++) if (g.rows[k].label === me.label) return {kind: 'row', r: g.rows[k], g: g};
  return null;
}
function contestNudge(j){
  var m = contestMine(j);
  if (!m || m.kind !== 'row') return '';
  var r = m.r, b = j && j.board;
  if (contestPowerToday(b)){ var x = contestPowerPts(b); return 'היום כל גיוס שווה ' + x.g + ' נקודות וכל פגישה ' + x.m; }
  if (r.rank === 1) return 'אתה מוביל בקבוצה';
  var up = null;
  (m.g.rows || []).forEach(function(x){ if (x.points > r.points && (up == null || x.points < up)) up = x.points; });
  return up == null ? '' : 'עוד ' + (up - r.points) + ' נקודות למקום הבא';
}
function contestMeHtml(j){
  var m = contestMine(j);
  if (!m) return '';
  var r = m.r, chips;
  if (m.kind === 'coord'){
    chips = '<div class="ck-chip"><b>' + cShow(r.meetings) + '</b><span>פגישות</span></div>' +
      (contestHasPower(j.board) ? '<div class="ck-chip g"><b>' + cShow(r.power_pts) + '</b><span>ב-Power Day</span></div>' : '');
    return '<div class="ck-me"><div class="t">הניקוד שלך</div><div class="big">' + cShow(r.points) +
      ' <small>נק\' · מתאמת</small></div><div class="ck-chips">' + chips + '</div></div>';
  }
  chips = '<div class="ck-chip g"><b>' + cShow(r.gius) + '</b><span>גיוסים</span></div>' +
    '<div class="ck-chip"><b>' + cShow(r.meetings) + '</b><span>פגישות</span></div>' +
    (contestHasPower(j.board) ? '<div class="ck-chip g"><b>' + cShow(r.power_pts) + '</b><span>ב-Power Day</span></div>' : '');
  var nd = contestNudge(j);
  return '<div class="ck-me"><div class="t">הניקוד שלך</div><div class="big">' + cShow(r.points) +
    ' <small>נק\' · מקום ' + cShow(r.rank) + ' בקבוצה</small></div><div class="ck-chips">' + chips + '</div>' +
    (nd ? '<div class="ck-push">' + cEsc(nd) + '</div>' : '') + '</div>';
}
function contestTeamsHtml(j){
  var b = j.board, me = j.me, gs = b.groups || [];
  var t = gs.map(function(g, i){
    var pt = contestPartial(b);
    return '<div class="ck-team' + (contestLead(b) === i ? ' lead' : '') + '">' +
      (me && me.group === i ? '<div class="mine">הקבוצה שלך</div>' : '') +
      '<div class="nm">' + cEsc(g.name) + '</div><div class="pts"' + (pt ? ' style="font-size:22px"' : '') + '>' + contestTotal(b, g) +
      '</div><div class="u">' + (pt ? 'הניקוד יתעדכן בקרוב' : 'נקודות') + '</div></div>';
  });
  return '<div class="ck-vs">' + t.join('<div class="ck-vsx">מול</div>') + '</div>';
}
function contestTvHtml(j){
  var b = j && j.board;
  if (!b || !b.groups || b.groups.length < 2) return '';
  var gs = b.groups, win = j.mode === 'winner', pt = contestPartial(b), ld = contestLead(b);
  var head = pt ? 'הניקוד לא זמין כרגע' : ld == null ? 'תיקו' : cEsc(gs[ld].name) + (win ? ' ניצחה' : ' מובילה');
  var cols = gs.map(function(g, i){
    var rows = (g.rows || []).slice().sort(function(x, y){ return (cNum(y.points) || 0) - (cNum(x.points) || 0); });
    var co = (g.coords || []).slice().sort(function(x, y){ return (cNum(y.points) || 0) - (cNum(x.points) || 0); });
    return '<div class="ck-col' + (ld === i ? ' lead' : '') + '"><div class="ch"><div class="cn">' + cEsc(g.name) +
      '</div><div class="cp">' + (pt ? '<span style="font-size:32px">לא זמין</span>' : cShow(g.total) + '<small>נק\'</small>') + '</div></div>' +
      '<div class="crs">' + rows.map(function(r, k){
        return '<div class="cr' + (!pt && !cNum(r.points) ? ' z' : '') + '"><div class="pos">' + (k + 1) + '</div><div class="l">' + cEsc(r.label) +
          '</div><div class="v">' + cShow(pt ? null : r.points) + '</div></div>';
      }).join('') + '</div>' +
      (co.length ? '<div class="cct">מתאמות · לא נספרות בסך הקבוצה</div><div class="cc">' + co.map(function(c){
        return '<div class="cr"><div class="l">' + cEsc(c.name) + '<small>' + cShow(c.meetings) + ' פגישות</small></div><div class="v">' +
          cShow(c.points) + '</div></div>';
      }).join('') + '</div>' : '') + '</div>';
  }).join('');
  var a = Math.max(0, cNum(gs[0].total) || 0), c = Math.max(0, cNum(gs[1].total) || 0);
  var pa = (a + c && !pt) ? Math.round(a * 100 / (a + c)) : 50, gap = pt ? 0 : Math.abs((cNum(gs[0].total) || 0) - (cNum(gs[1].total) || 0));
  return '<div class="ck tv"><div class="ck-top"><span>' + cEsc(b.name) + '</span><span>' +
    cEsc(win ? contestRange(b.start, b.end) : contestDays(b.days_left)) + '</span></div>' +
    '<div class="ck-tvh"><div class="ck-trophy">' + CONTEST_TROPHY + '</div><div><div class="ck-h">' + head + '</div>' +
    '<div class="ck-sub">' + (win ? 'התחרות הסתיימה' : pt ? 'החתימות לא נטענו — הניקוד יתעדכן בקרוב' : (gap ? 'פער של ' + gap + ' נקודות' : 'תיקו')) + '</div></div></div>' +
    (win ? '' : contestPowerBanner(b)) +
    '<div class="ck-cols">' + cols + '</div>' +
    '<div class="ck-track"><i class="' + (ld === 0 ? 'lead' : '') + '" style="width:' + pa + '%"></i>' +
    '<i class="' + (ld === 1 ? 'lead' : '') + '" style="width:' + (100 - pa) + '%"></i></div></div>';
}
function contestCardHtml(j, opts){
  opts = opts || {};
  if (opts.tv) return contestTvHtml(j);
  if (j && j.mode === 'winner') return contestWinnerHtml(j, opts);
  var b = j && j.board;
  if (!b || !b.groups || b.groups.length < 2) return '';
  var gs = b.groups, a = Math.max(0, cNum(gs[0].total) || 0), c = Math.max(0, cNum(gs[1].total) || 0);
  var pt = contestPartial(b), ld = contestLead(b);
  var pa = (a + c && !pt) ? Math.round(a * 100 / (a + c)) : 50;
  var head = pt ? 'הניקוד לא זמין כרגע' : ld == null ? 'תיקו' : cEsc(gs[ld].name) + ' מובילה';
  var gap = pt ? 0 : Math.abs((cNum(gs[0].total) || 0) - (cNum(gs[1].total) || 0)), gapL = '';
  if (gap){
    var k = contestGapGius(gap, (b.pts || {}).gius);
    gapL = '<div class="ck-gap">פער של <b>' + gap + ' נקודות</b>' +
      (k === 1 ? ' — גיוס אחד בערך' : k > 1 ? ' — ' + k + ' גיוסים בערך' : '') + '</div>';
  }
  var p = b.pts || {};
  return '<div class="ck' + (opts.story ? ' story' : '') + (opts.tv ? ' tv' : '') + '">' +
    '<div class="ck-top"><span>' + cEsc(b.name) + '</span><span>' + cEsc(contestDays(b.days_left)) + '</span></div>' +
    '<div class="ck-trophy">' + CONTEST_TROPHY + '</div>' +
    '<div class="ck-h">' + head + '</div>' +
    '<div class="ck-sub">גיוס בבלעדיות ' + cShow(p.gius) + ' נק\' · פגישה ' + cShow(p.meeting) + ' נק\'</div>' +
    contestPowerBanner(b) +
    contestTeamsHtml(j) +
    '<div class="ck-track"><i class="' + (ld === 0 ? 'lead' : '') + '" style="width:' + pa + '%"></i>' +
    '<i class="' + (ld === 1 ? 'lead' : '') + '" style="width:' + (100 - pa) + '%"></i></div>' +
    gapL + (opts.tv ? '' : contestMeHtml(j)) +
    (opts.story ? '<a class="ck-full" href="/v2/contest" onclick="event.stopPropagation()">לטבלה המלאה</a>' : '') +
    '</div>';
}
function contestWinnerHtml(j, opts){
  opts = opts || {};
  if (opts.tv) return contestTvHtml(j);
  var b = j && j.board;
  if (!b || !b.groups || b.groups.length < 2) return '';
  var all = [];
  b.groups.forEach(function(g){ (g.rows || []).forEach(function(r){ all.push({r: r, g: g.name}); }); });
  all.sort(function(x, y){ return (cNum(y.r.points) || 0) - (cNum(x.r.points) || 0); });
  var top = all.slice(0, 3).map(function(x, i){
    return '<div class="r"><div class="pos">' + (i + 1) + '</div><div class="nm">' + cEsc(x.r.label) +
      '<small>' + cEsc(x.g) + '</small></div><div class="p">' + cShow(x.r.points) + '</div></div>';
  }).join('');
  var ld = contestLead(b);
  var head = contestPartial(b) ? 'הניקוד לא זמין כרגע' : ld == null ? 'תיקו' : cEsc(b.groups[ld].name) + ' ניצחה';
  return '<div class="ck' + (opts.story ? ' story' : '') + (opts.tv ? ' tv' : '') + '">' +
    '<div class="ck-top"><span>' + cEsc(b.name) + '</span><span>' + cEsc(contestRange(b.start, b.end)) + '</span></div>' +
    '<div class="ck-trophy">' + CONTEST_TROPHY + '</div>' +
    '<div class="ck-h">' + head + '</div><div class="ck-sub">התחרות הסתיימה</div>' +
    contestTeamsHtml(j) + (top && !contestPartial(b) ? '<div class="ck-top3">' + top + '</div>' : '') +
    (opts.story ? '<a class="ck-full" href="/v2/contest" onclick="event.stopPropagation()">לטבלה המלאה</a>' : '') +
    '</div>';
}
/* ── המסך: טבלאות ── */
function contestAdjFor(adjs, gi, kind, label){
  return (adjs || []).filter(function(a){ return a && +a.group === gi && a.kind === kind && a.label === label; });
}
function contestPtsCell(j, gi, kind, label, pts, adj){
  var mark = adj ? ' <button class="cAdj" onclick="adjOpen(' + gi + ',\'' + kind + '\',\'' + cEnc(label) +
    '\')" aria-label="תיקונים בניקוד">' + (adj > 0 ? '+' : '') + adj + '</button>' : '';
  return '<td class="p">' + cShow(pts) + mark + '</td>';
}
function contestEditCell(j, gi, kind, label){
  return j && j.can_edit ? '<td class="ed"><button class="cFix" onclick="adjOpen(' + gi + ',\'' + kind + '\',\'' +
    cEnc(label) + '\')" aria-label="תיקון ידני">תיקון</button></td>' : '';
}
function contestTableHtml(j, gi, opts){
  var g = j && j.board && j.board.groups && j.board.groups[gi];
  if (!g) return '';
  var me = j.me, ed = !!(j && j.can_edit), hp = contestHasPower(j.board);
  var rows = (g.rows || []).map(function(r){
    var mine = me && me.kind === 'row' && me.group === gi && me.label === r.label;
    return '<tr class="' + (mine ? 'me' : '') + (r.rank === 1 && r.points > 0 ? ' top1' : '') + '">' +
      '<td class="pos">' + cShow(r.rank) + '</td><td class="n">' + cEsc(r.label) + '</td>' +
      '<td>' + cShow(r.meetings) + '</td><td>' + cShow(r.gius) + '</td>' +
      contestPtsCell(j, gi, 'row', r.label, r.points, cNum(r.adj) || 0) +
      (hp ? '<td class="pd">' + cShow(r.power_pts) + '</td>' : '') + contestEditCell(j, gi, 'row', r.label) + '</tr>';
  }).join('');
  return '<table><tr><th></th><th>סוכן</th><th>פגישות</th><th>גיוסים</th><th>ניקוד</th>' + (hp ? '<th>Power Day</th>' : '') +
    (ed ? '<th></th>' : '') + '</tr>' + rows + '</table>';
}
function contestCoordsHtml(j, gi){
  var g = j && j.board && j.board.groups && j.board.groups[gi];
  if (!g || !(g.coords || []).length) return '';
  var me = j.me, ed = !!(j && j.can_edit), hp = contestHasPower(j.board);
  var rows = g.coords.map(function(c){
    var mine = me && me.kind === 'coord' && me.group === gi && me.label === c.name;
    return '<tr class="' + (mine ? 'me' : '') + '"><td class="n">' + cEsc(c.name) + '</td><td>' + cShow(c.meetings) + '</td>' +
      contestPtsCell(j, gi, 'coord', c.name, c.points, cNum(c.adj) || 0) +
      (hp ? '<td class="pd">' + cShow(c.power_pts) + '</td>' : '') + contestEditCell(j, gi, 'coord', c.name) + '</tr>';
  }).join('');
  return '<table><tr><th>מתאמת</th><th>פגישות</th><th>ניקוד</th>' + (hp ? '<th>Power Day</th>' : '') + (ed ? '<th></th>' : '') + '</tr>' + rows + '</table>';
}
</script>"""


# ── UI: מסך התחרות /v2/contest (הראוט ב-effie_v2.register, דרך _page) ─────────
V2_CONTEST_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>תחרות</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;min-height:100vh;min-height:100dvh;color:#14192B}
  .wrap{max-width:600px;margin:0 auto;padding-bottom:calc(env(safe-area-inset-bottom,0px) + 30px)}
  .hero{background:linear-gradient(160deg,#0E1D33,#2C4C77);color:#fff;padding:calc(env(safe-area-inset-top,0px) + 12px) 18px 18px;border-radius:0 0 26px 26px}
  .hero .top{display:flex;justify-content:space-between;align-items:center;font-size:13px;opacity:.9}
  .back{width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  .hero h2{font-size:22px;font-weight:800;margin-top:4px}
  .hero .sub{font-size:13px;opacity:.8}
  .mini-vs{display:flex;gap:8px;margin-top:12px}
  .mini-vs div{flex:1;border-radius:14px;padding:8px;text-align:center;background:rgba(255,255,255,.08)}
  .mini-vs div.lead{background:rgba(228,197,107,.16);outline:1.5px solid #E4C56B}
  .mini-vs b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
  .mini-vs .lead b{color:#E4C56B}
  .mini-vs span{font-size:12px;opacity:.8}
  .rules{margin:12px 16px 0;font-size:12.5px;color:#5B6472;text-align:center;line-height:1.55}
  .rules b{color:#1E3A5F}
  .adm{display:flex;gap:8px;margin:12px 14px 0;flex-wrap:wrap}
  .btn{display:flex;align-items:center;justify-content:center;gap:6px;min-height:44px;border-radius:14px;font:700 14.5px 'Heebo',sans-serif;
      border:0;cursor:pointer;padding:0 14px;flex:1}
  .btn.blue{background:#2E6BD6;color:#fff}
  .btn.sec{background:#fff;color:#1E3A5F;border:1.5px solid #D5D9E0}
  .btn:disabled{opacity:.6}
  .err{color:#7A5E1C;font-size:13px;font-weight:700;text-align:center;margin:6px 14px 0;min-height:0}
  .seg{display:flex;margin:12px 14px 0;background:#fff;border-radius:14px;padding:4px;gap:4px;box-shadow:0 6px 20px rgba(30,58,95,.06)}
  .seg button{flex:1;min-height:44px;border-radius:11px;font:700 14px 'Heebo',sans-serif;color:#5B6472;background:none;border:0;cursor:pointer}
  .seg button.on{background:#1E3A5F;color:#fff}
  .card{margin:12px 14px 0;background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:6px 10px 8px}
  .card h3{font-size:15px;color:#1E3A5F;padding:8px 4px 6px;display:flex;justify-content:space-between}
  .card h3 span{color:#7A5E1C}
  .card p.s{font-size:12px;color:#5B6472;padding:0 4px 4px}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  th{font-size:12px;color:#5B6472;font-weight:600;text-align:center;padding:4px 2px}
  th:first-child,td:first-child{text-align:right}
  td{text-align:center;padding:8px 2px;border-top:1px solid #F0ECE3;font-variant-numeric:tabular-nums}
  td.pos{width:22px;color:#5B6472;font-weight:700;font-size:12px}
  td.n{font-weight:600;text-align:right}
  td.p{font-weight:800;color:#1E3A5F;white-space:nowrap}
  td.pd{color:#5B6472}
  td.ed{width:52px}
  tr.me td{background:#FFF8E6}
  tr.me td.n::after{content:" (את/ה)";color:#7A5E1C;font-size:12px;font-weight:700}
  tr.top1 td.p{color:#7A5E1C}
  .cAdj{position:relative;font:700 11px 'Heebo',sans-serif;color:#7A5E1C;background:#FBF3DF;border:1px solid #E4C56B;border-radius:99px;
      padding:1px 6px;cursor:pointer;vertical-align:middle}
  .cAdj::after,.cFix::after{content:"";position:absolute;inset:-12px -6px}
  .cFix{position:relative;font:700 12px 'Heebo',sans-serif;color:#2E6BD6;background:#EEF3FC;border:0;border-radius:10px;min-height:32px;padding:0 8px;cursor:pointer}
  .note{font-size:12px;color:#5B6472;text-align:center;margin:14px 20px 0;line-height:1.5}
  .empty{margin:30px 16px 0;background:#fff;border-radius:22px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:26px 20px;text-align:center}
  .empty .ic{width:64px;height:64px;border-radius:50%;background:#FBF3DF;border:1.5px solid #E4C56B;display:flex;align-items:center;justify-content:center;margin:0 auto 12px}
  .empty h3{font-size:18px;color:#1E3A5F;font-weight:800}
  .empty p{font-size:14px;color:#5B6472;margin-top:6px;line-height:1.55}
  .empty .btn{margin:16px auto 0;max-width:240px}
  #ovl{position:fixed;inset:0;background:rgba(23,37,60,.45);display:none;z-index:60}
  #sheet{position:fixed;left:0;right:0;bottom:0;z-index:61;background:#F7F5EE;border-radius:28px 28px 0 0;
      box-shadow:0 -12px 40px rgba(23,37,60,.3);padding:16px 18px calc(env(safe-area-inset-bottom,0px) + 18px);
      display:none;flex-direction:column;gap:10px;max-height:88vh;overflow:auto;max-width:600px;margin:0 auto}
  #sheet .st{font-size:17px;font-weight:800;text-align:center;color:#1E3A5F}
  #sheet .ss{font-size:12.5px;color:#5B6472;text-align:center;line-height:1.5}
  #sheet .fl{display:flex;flex-direction:column;gap:4px;font-size:13px;font-weight:700;color:#5B6472}
  #sheet input{width:100%;min-height:44px;border:1.5px solid #D5D9E0;border-radius:12px;padding:0 12px;
      font:600 16px 'Heebo',sans-serif;font-size:16px;color:#14192B;background:#fff}
  #sheet input:focus{outline:none;border-color:#2E6BD6}
  #sheet .two{display:flex;gap:8px}
  #sheet .two>*{flex:1;min-width:0}
  #sheet .grp{background:#fff;border-radius:20px;padding:12px;display:flex;flex-direction:column;gap:8px;box-shadow:0 6px 20px rgba(30,58,95,.06)}
  #sheet .grp h4{font-size:14px;color:#1E3A5F}
  #sheet .rw{display:flex;gap:6px;align-items:center}
  #sheet .rw input.l{flex:0 0 38%}
  #sheet .rw input.m{flex:1;min-width:0}
  .trash{width:44px;height:44px;flex:none;border-radius:12px;background:#FBEDED;border:0;display:flex;align-items:center;justify-content:center;cursor:pointer}
  .adjl{display:flex;align-items:center;gap:10px;background:#fff;border-radius:16px;padding:8px 12px;min-height:56px}
  .adjl .v{font-weight:800;color:#1E3A5F;min-width:44px;font-variant-numeric:tabular-nums}
  .adjl .r{flex:1;min-width:0;font-size:14px}
  .adjl .r small{display:block;color:#5B6472;font-size:12px}
  .sg{display:flex;background:#fff;border-radius:12px;padding:3px;gap:3px}
  .sg button{flex:1;min-height:40px;border:0;border-radius:10px;font:700 14px 'Heebo',sans-serif;color:#5B6472;background:none;cursor:pointer}
  .sg button.on{background:#1E3A5F;color:#fff}
  #toast{position:fixed;bottom:40px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;
      font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;
      pointer-events:none;z-index:95;white-space:nowrap}
</style></head><body>
<div class="wrap" id="app"><div style="text-align:center;color:#5B6472;font-size:14px;padding:60px 0">טוען את התחרות…</div></div>
<div id="ovl" onclick="sheetClose()"></div>
<div id="sheet"></div>
<div id="toast" role="status" aria-live="polite"></div>
<!--CONTEST_KIT-->
<script>
var TOK = null;
try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function el(id){ return document.getElementById(id); }
function GET(u){ return fetch(u, {headers:{'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function POST(u, d){
  return fetch(u, {method:'POST', headers:{'Content-Type':'application/json', 'X-Auth-Token': TOK}, body: JSON.stringify(d)})
    .then(function(r){ return r.json().catch(function(){ return {ok:false}; }); });
}
function toast(m){ var t = el('toast'); t.textContent = m; t.style.opacity = '1'; clearTimeout(t._h); t._h = setTimeout(function(){ t.style.opacity = '0'; }, 2000); }
var CJ = null, SEL = null, ED = null, ADJ = null;
var BACK_SVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>';
var TRASH_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C24040" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>';
function render(){
  var j = CJ, b = j && j.board;
  if (!b){
    el('app').innerHTML = '<div class="hero"><div class="top"><button class="back" onclick="location.href=\'/v2/home\'" aria-label="חזרה">' + BACK_SVG + '</button><span></span></div><h2>תחרות</h2></div>' +
      '<div class="empty"><div class="ic">' + CONTEST_TROPHY + '</div><h3>אין תחרות פעילה כרגע</h3>' +
      '<p>כשתתחיל תחרות בין הקבוצות, הניקוד והטבלה של כל קבוצה יופיעו כאן.</p>' +
      (j && j.can_edit ? '<button class="btn blue" onclick="copyOpen()">צור תחרות</button>' : '') + '</div>';
    return;
  }
  if (SEL == null) SEL = (j.me && j.me.group != null) ? j.me.group : (contestLead(b) != null ? contestLead(b) : 0);
  var gs = b.groups, g = gs[SEL] || gs[0];
  var mini = gs.map(function(x, i){ return '<div class="' + (contestLead(b) === i ? 'lead' : '') + '"><b>' + contestTotal(b, x) + '</b><span>' + cEsc(x.name) + '</span></div>'; }).join('');
  var um = (j.can_edit && j.unmatched && j.unmatched.length) ? '<div class="note" style="color:#7A5E1C;font-weight:700">שמות שלא נמצאו באפי: ' +
    j.unmatched.map(cEsc).join(', ') + '</div>' : '';
  var seg = gs.map(function(x, i){ return '<button class="' + (i === SEL ? 'on' : '') + '" onclick="pick(' + i + ')">' + cEsc(x.name) + '</button>'; }).join('');
  var co = contestCoordsHtml(j, SEL);
  el('app').innerHTML =
    '<div class="hero"><div class="top"><button class="back" onclick="location.href=\'/v2/home\'" aria-label="חזרה">' + BACK_SVG + '</button>' +
      '<span>' + cEsc(j.mode === 'winner' ? 'התחרות הסתיימה' : contestDays(b.days_left)) + '</span></div>' +
      '<h2>' + cEsc(b.name) + '</h2><div class="sub">קבוצה מול קבוצה · ' + cEsc(contestRange(b.start, b.end)) + '</div>' +
      '<div class="mini-vs">' + mini + '</div>' + (j.mode === 'winner' ? '' : contestPowerBanner(b)) + '</div>' +
    '<div class="rules">' + contestRules(b.pts) + '</div>' +
    (j.can_edit ? '<div class="adm"><button class="btn sec" onclick="editOpen()">עריכת התחרות</button>' +
      '<button class="btn sec" onclick="copyOpen()">תחרות חדשה (העתק)</button>' +
      (j.mode === 'live' ? '<button class="btn sec" onclick="powerOpen()">Power Day</button>' : '') + '</div>' : '') +
    '<div class="seg">' + seg + '</div>' +
    um + '<div class="card"><h3>' + cEsc(g.name) + ' <span>' + (contestPartial(b) ? 'לא זמין' : cShow(g.total) + ' נק\'') + '</span></h3>' + contestTableHtml(j, SEL, {}) + '</div>' +
    (co ? '<div class="card"><h3>המתאמות של ' + cEsc(g.name) + '</h3><p class="s">פגישות שהן תיאמו — נספרות להן בלבד, לא בסך הקבוצה</p>' + co + '</div>' : '') +
    '<div class="note">פגישה שנמחקה לפני המועד שלה יורדת מהניקוד. גיוס נספר רק אחרי שהבלעדיות נחתמה.</div>';
}
function pick(i){ SEL = i; render(); }
function load(tries){
  GET('/v2/api/contest').then(function(j){
    if (!j || !j.ok) throw new Error('contest');
    CJ = j; contestCachePut(TOK, j); render();
  }).catch(function(){
    if ((tries || 0) < 2){ setTimeout(function(){ load((tries || 0) + 1); }, 4000); return; }
    if (!CJ){ CJ = {ok: true, board: null}; render(); toast('לא הצלחנו לטעון את התחרות'); }
  });
}
function sheetShow(html){ el('sheet').innerHTML = html; el('ovl').style.display = 'block'; el('sheet').style.display = 'flex'; }
function sheetClose(){ el('ovl').style.display = 'none'; el('sheet').style.display = 'none'; ED = null; ADJ = null; }
function shErr(m){ var e = el('shErr'); if (e) e.textContent = m || ''; }
/* ── תיקונים ── */
function adjOpen(gi, kind, enc){
  var label = decodeURIComponent(enc), list = contestAdjFor(CJ.adjustments, gi, kind, label), ed = !!CJ.can_edit;
  ADJ = {gi: gi, kind: kind, label: label, sign: 1};
  var items = list.map(function(a){
    return '<div class="adjl"><div class="v">' + (a.pts > 0 ? '+' : '') + cShow(a.pts) + '</div><div class="r">' + cEsc(a.reason) +
      (a.by ? '<small>' + cEsc(a.by) + '</small>' : '') + '</div>' +
      (ed ? '<button class="trash" onclick="adjDel(\'' + cEnc(a.id) + '\')" aria-label="מחיקת התיקון">' + TRASH_SVG + '</button>' : '') + '</div>';
  }).join('');
  sheetShow('<div class="st">' + (ed ? 'תיקון ידני · ' : 'תיקונים בניקוד · ') + cEsc(label) + '</div>' +
    (items || '<div class="ss">אין תיקונים בניקוד הזה</div>') +
    (ed ? '<div class="sg"><button id="sgP" class="on" onclick="adjSign(1)">הוספה</button><button id="sgM" onclick="adjSign(-1)">הורדה</button></div>' +
      '<label class="fl">נקודות<input id="aPts" type="text" inputmode="numeric" autocomplete="off"></label>' +
      '<label class="fl">סיבה<input id="aReason" type="text" maxlength="200" autocomplete="off"></label>' +
      '<button class="btn blue" id="aSave" onclick="adjSave()">שמירת התיקון</button><div class="err" id="shErr"></div>' : '') +
    '<button class="btn sec" onclick="sheetClose()">סגירה</button>');
}
function adjSign(s){ if (!ADJ) return; ADJ.sign = s; el('sgP').className = s > 0 ? 'on' : ''; el('sgM').className = s < 0 ? 'on' : ''; }
function adjSave(){
  if (!ADJ) return;
  var v = String(el('aPts').value || '').replace(/[^\d]/g, ''), n = parseInt(v, 10), reason = String(el('aReason').value || '').trim();
  if (!n || n > 1000){ shErr('מספר נקודות בין 1 ל-1,000'); return; }
  if (!reason){ shErr('חובה לציין סיבה'); return; }
  el('aSave').disabled = true;
  POST('/v2/api/contest/adjust', {contest: CJ.board.id, group: ADJ.gi, kind: ADJ.kind, label: ADJ.label, pts: n * ADJ.sign, reason: reason})
    .then(function(r){
      el('aSave').disabled = false;
      if (r && r.ok){ sheetClose(); toast('התיקון נשמר'); load(0); }
      else shErr((r && r.error && r.error !== 'forbidden') ? r.error : r && r.error === 'forbidden' ? 'אין הרשאה' : 'לא נשמר — נסה שוב');
    }).catch(function(){ el('aSave').disabled = false; shErr('לא נשמר — נסה שוב'); });
}
function adjDel(id){
  if (!confirm('למחוק את התיקון?')) return;
  POST('/v2/api/contest/adjust', {contest: CJ.board.id, delete: decodeURIComponent(id)}).then(function(r){
    if (r && r.ok){ sheetClose(); toast('התיקון נמחק'); load(0); }
    else toast((r && r.error && r.error !== 'forbidden') ? r.error : 'לא נמחק — נסה שוב');
  }).catch(function(){ toast('לא נמחק — נסה שוב'); });
}
/* ── [POWER-DAY 04/11] ימי ניקוד כפול — מנהל שאינו מתאמת ── */
var POW_WD = ['ראשון','שני','שלישי','רביעי','חמישי','שישי','שבת'];
function powerLabel(d){
  var x = String(d).split('-'), dt = new Date(+x[0], +x[1] - 1, +x[2]);
  return 'יום ' + POW_WD[dt.getDay()] + ' ' + (+x[2]) + '/' + (+x[1]);
}
function powerOpen(){
  var b = CJ && CJ.board;
  if (!b) return;
  var today = contestToday(), sent = CJ.power_sent || {};
  var items = (CJ.power_all || []).map(function(d){
    var st = d === today ? 'היום' : d < today ? 'עבר' : 'עתידי · מוסתר מכולם עד הבוקר', sm = sent[d];
    var msg = sm ? ' · הודעה נשלחה ל-' + sm.sent + (sm.fail ? ' · ' + sm.fail + ' נכשלו' : '') + (sm.no_phone ? ' · ' + sm.no_phone + ' בלי טלפון' : '') : '';
    return '<div class="adjl"><div class="r"><b>' + cEsc(powerLabel(d)) + '</b><small>' + cEsc(st + msg) + '</small></div>' +
      '<button class="trash" onclick="powerSet(\'' + cEnc(d) + '\', false)" aria-label="ביטול ה-Power Day">' + TRASH_SVG + '</button></div>';
  }).join('');
  var x = contestPowerPts(b);
  sheetShow('<div class="st">Power Day · ניקוד כפול</div>' +
    '<div class="ss">ביום שתבחר כל גיוס שווה ' + x.g + ' נקודות וכל פגישה ' + x.m + '. התאריך מוסתר מכולם עד היום עצמו. ' +
    'ב-09:00 יוצאת הודעת וואטסאפ לכל המשתתפים, למתאמות, לאייל, לאודי ולמתן ביטון (יום שנקבע אחרי 09:00 — מיד). יום שכבר עבר — הניקוד מתעדכן, בלי הודעה.</div>' +
    (items || '<div class="ss">עדיין לא נקבע Power Day</div>') +
    '<label class="fl">תאריך<input id="pDate" type="date" min="' + cEsc(b.start) + '" max="' + cEsc(b.end) + '" value="' + cEsc(today) + '"></label>' +
    '<button class="btn blue" id="pSave" onclick="powerAdd()">קביעת Power Day</button><div class="err" id="shErr"></div>' +
    '<button class="btn sec" onclick="sheetClose()">סגירה</button>');
}
function powerAdd(){
  var d = el('pDate').value;
  if (!d){ shErr('בחר תאריך'); return; }
  if (d === contestToday() && !confirm('לקבוע את היום כ-Power Day? ההודעה בוואטסאפ תצא עכשיו לכל המשתתפים.')) return;
  powerSet(encodeURIComponent(d), true);
}
function powerSet(enc, on){
  var d = decodeURIComponent(enc);
  if (!on && !confirm('לבטל את ה-Power Day של ' + powerLabel(d) + '? הניקוד הכפול של היום הזה יחזור לרגיל.')) return;
  var btn = el('pSave'); if (btn) btn.disabled = true;
  POST('/v2/api/contest/power', {contest: CJ.board.id, date: d, on: on}).then(function(r){
    if (btn) btn.disabled = false;
    if (r && r.ok){ CJ.power_all = r.power_all || []; toast(on ? 'ה-Power Day נקבע' : 'ה-Power Day בוטל'); powerOpen(); load(0); }
    else shErr((r && r.error && r.error !== 'forbidden') ? r.error : r && r.error === 'forbidden' ? 'אין הרשאה' : 'לא נשמר — נסה שוב');
  }).catch(function(){ if (btn) btn.disabled = false; shErr('לא נשמר — נסה שוב'); });
}
/* ── עריכת התחרות ── */
function rowHtml(gi, label, members){
  var m = (members || []).join(', ');
  if (m === label) m = '';
  return '<div class="rw"><input class="l" placeholder="תווית" value="' + cEsc(label) + '">' +
    '<input class="m" placeholder="חברים, מופרדים בפסיק" value="' + cEsc(m) + '">' +
    '<button class="trash" onclick="this.parentNode.remove()" aria-label="הסרת השורה">' + TRASH_SVG + '</button></div>';
}
function rowAdd(gi){ var d = document.createElement('div'); d.innerHTML = rowHtml(gi, '', []); el('rows' + gi).appendChild(d.firstChild); }
function editOpen(){
  var d = CJ && CJ.def;
  if (!d) return;
  ED = {id: d.id};
  var p = d.pts || {};
  var grp = (d.groups || []).map(function(g, gi){
    return '<div class="grp"><h4>קבוצה ' + (gi + 1) + '</h4><label class="fl">שם הקבוצה<input id="gn' + gi + '" value="' + cEsc(g.name) + '"></label>' +
      '<div class="fl">שורות (תווית + חברים)</div><div id="rows' + gi + '">' +
      (g.rows || []).map(function(r){ return rowHtml(gi, r.label, r.members); }).join('') + '</div>' +
      '<button class="btn sec" onclick="rowAdd(' + gi + ')">הוספת שורה</button>' +
      '<label class="fl">מתאמות (מופרדות בפסיק)<input id="gc' + gi + '" value="' + cEsc((g.coords || []).join(', ')) + '"></label></div>';
  }).join('');
  sheetShow('<div class="st">עריכת התחרות</div>' +
    '<label class="fl">שם<input id="eName" value="' + cEsc(d.name) + '"></label>' +
    '<div class="two"><label class="fl">התחלה<input id="eStart" type="date" value="' + cEsc(d.start) + '"></label>' +
    '<label class="fl">סיום<input id="eEnd" type="date" value="' + cEsc(d.end) + '"></label></div>' +
    '<div class="two"><label class="fl">נקודות לגיוס<input id="eG" type="text" inputmode="numeric" value="' + cShow(p.gius) + '"></label>' +
    '<label class="fl">נקודות לפגישה<input id="eM" type="text" inputmode="numeric" value="' + cShow(p.meeting) + '"></label></div>' +
    grp + '<button class="btn blue" id="eSave" onclick="editSave()">שמירה</button><div class="err" id="shErr"></div>' +
    '<button class="btn sec" onclick="sheetClose()">ביטול</button>');
}
function editCollect(){
  var d = CJ.def, out = {id: ED.id, name: el('eName').value.trim(), start: el('eStart').value, end: el('eEnd').value,
    pts: {gius: parseInt(el('eG').value, 10), meeting: parseInt(el('eM').value, 10)}, groups: []};
  (d.groups || []).forEach(function(g, gi){
    var rows = [];
    Array.prototype.forEach.call(el('rows' + gi).querySelectorAll('.rw'), function(rw){
      var l = rw.querySelector('.l').value.trim(), m = contestSplit(rw.querySelector('.m').value);
      if (l) rows.push({label: l, members: m.length ? m : [l]});
    });
    out.groups.push({name: el('gn' + gi).value.trim() || g.name, rows: rows, coords: contestSplit(el('gc' + gi).value)});
  });
  return out;
}
function editSave(){
  if (!ED) return;
  var c = editCollect();
  if (!c.name){ shErr('חסר שם לתחרות'); return; }
  if (isNaN(c.pts.gius) || isNaN(c.pts.meeting)){ shErr('נקודות חייבות להיות מספר'); return; }
  el('eSave').disabled = true;
  POST('/v2/api/contest/save', {contest: c}).then(function(r){
    el('eSave').disabled = false;
    if (r && r.ok){ sheetClose(); toast('התחרות נשמרה'); load(0); }
    else shErr((r && r.error && r.error !== 'forbidden') ? r.error : r && r.error === 'forbidden' ? 'אין הרשאה' : 'לא נשמר — נסה שוב');
  }).catch(function(){ el('eSave').disabled = false; shErr('לא נשמר — נסה שוב'); });
}
function copyOpen(){
  var d = CJ && CJ.def;
  if (!d) return;
  ED = {copy: d.id};
  sheetShow('<div class="st">תחרות חדשה</div><div class="ss">הקבוצות, החברים והנקודות מועתקים מ"' + cEsc(d.name) + '". אפשר לשנות אחר כך בעריכה.</div>' +
    '<label class="fl">שם<input id="cName" placeholder="למשל תחרות דצמבר"></label>' +
    '<div class="two"><label class="fl">התחלה<input id="cStart" type="date"></label><label class="fl">סיום<input id="cEnd" type="date"></label></div>' +
    '<button class="btn blue" id="cSave" onclick="copySave()">יצירת התחרות</button><div class="err" id="shErr"></div>' +
    '<button class="btn sec" onclick="sheetClose()">ביטול</button>');
}
function copySave(){
  if (!ED || !ED.copy) return;
  var name = el('cName').value.trim(), s = el('cStart').value, e = el('cEnd').value;
  if (!name || !s || !e){ shErr('צריך שם, תאריך התחלה ותאריך סיום'); return; }
  el('cSave').disabled = true;
  POST('/v2/api/contest/save', {copy_from: ED.copy, id: s, name: name, start: s, end: e}).then(function(r){
    el('cSave').disabled = false;
    if (r && r.ok){ sheetClose(); toast('התחרות נוצרה'); SEL = null; load(0); }
    else shErr((r && r.error && r.error !== 'forbidden') ? r.error : r && r.error === 'forbidden' ? 'אין הרשאה' : 'לא נשמר — נסה שוב');
  }).catch(function(){ el('cSave').disabled = false; shErr('לא נשמר — נסה שוב'); });
}
(function(){
  var c = contestCacheGet(TOK);
  if (c){ CJ = c; render(); }
  load(0);
})();
</script></body></html>'''
