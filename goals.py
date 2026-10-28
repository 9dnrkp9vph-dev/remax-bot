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


def build_office(src, day, canon):
    """שורה לכל סוכן ברשימה (src['roster']) + סכום. src['cfg'] = הקונפיג (ליעדים), src['seen'] = מי נכנס היום.
    רשימה שנכשלה בשליפה → בלי שורות, partial=True."""
    bounds = day_bounds(day)
    roster = src.get("roster")
    cfg = src.get("cfg")
    cfg = cfg if isinstance(cfg, dict) else {}
    seen_src = src.get("seen")
    seen = set() if _bad(seen_src) else {canon(n) for n in (seen_src or []) if n}
    rows, per, tg = [], {}, {}
    if not _bad(roster):
        done = set()
        for name in roster or []:
            k = canon(name)
            if not name or k in done:
                continue
            done.add(k)
            c = count_agent(name, bounds, src, canon)
            t = targets_for(cfg, name, canon)
            rows.append({"name": name, "counts": c, "targets": t, "seen_today": k in seen})
            per[k] = c
            tg[k] = t
    total = rollup(per, tg)
    if _bad(roster):
        total["partial"] = True
    return {"rows": rows, "total": total}


def meeting_stamp(prev, new_status, now):
    """חותמת 'מתי נקבעה הפגישה' — קבועה לתמיד: קיימת נשמרת; אחרת now אם הסטטוס meeting; אחרת None."""
    ex = (prev or {}).get("meeting_at")
    if ex:
        return ex
    return now if new_status == "meeting" else None


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
    import time as _time
    _keys_used = set()

    def canon(n):
        return G["_canon_key"](str(n or "").strip())

    def _display(n):
        n = str(n or "").strip()
        try:
            return G["_canon_agent_name"](n) or n
        except Exception:
            return n

    def _safe(fn):
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

    def _roster():
        """הצוות שיכול להיכנס — כמו טבלת הסוכנים בלוח הבקרה (בלי הנה"ח, מושהים, נמחקים וחשבונות בדיקה)."""
        people, susp, rem = [], G["_suspended_set"]() or set(), G["_removed_agent_keys"]() or set()
        for r in G["_contacts_rows"]() or []:
            nm = str((r[0] if r else "") or "").strip()
            l9 = G["_last9"](r[1] if len(r) > 1 else "")
            if not nm or "בדיקה" in nm or (l9 and l9 in susp) or G["_name_key"](nm) in rem:
                continue
            try:
                if l9 and (G["_resolve_roles"](l9) or ("", ""))[1] == "accountant":
                    continue
            except Exception:
                pass
            people.append(_display(nm))
        return people

    def _team(coord_phone):
        cc = (G["_coordinators_all"]() or {}).get(G["_last9"](coord_phone)) or {}
        names = [str(n) for n in (cc.get("names") or set()) if n]
        for ph in cc.get("agents") or set():
            nm = (G["web_phone_name_map"]() or {}).get(G["_last9"](ph)) \
                or (G["web_contacts_phone_name"]() or {}).get(G["_last9"](ph))
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
        import effie_v2 as _ev
        frm = (_dt.datetime.fromtimestamp(now, _IL) - _dt.timedelta(days=3)).strftime("%d/%m/%Y")
        calls = G["web_fetch_raw"]("שיחות", frm, "31/12/2099") or []
        h = {"ts": _ev.crm_ts, "answered": lambda st: bool(G["_is_answered_status"](str(st or ""))),
             "nb_key": lambda r: ""}
        return _ev.crm_todo(calls, [], [], [], {}, now, h, limit=None)["missed"]

    def _reviews():
        import site_api as _sa
        return _sa.reviews_active(_sa.review_rows(G.get("_sbdb")))

    def _seen(day):
        start = _dt.datetime(day.year, day.month, day.day, tzinfo=_IL)
        return [r.get("name") for r in (G["_usage_rows"](start) or []) if r.get("name")]

    def _fetch_src():
        now = _time.time()
        day = _dt.datetime.fromtimestamp(now, _IL).date()
        t0 = day_bounds(day)[0]
        cfg = _safe(G["_load_config"])
        return {"day": day.isoformat(),
                "nb": cfg if _bad(cfg) else ((cfg or {}).get("nbStatus") or {}),
                "buyers": _safe(G["_fetch_manual_buyers"]),
                "bpages": _safe(lambda: G["_sbdb"].bpage_all()),
                "activity": _safe(lambda: G["_activity_fetch"](t0, today=True)),
                "reviews": _safe(_reviews),
                "missed": _safe(lambda: _missed(now)),
                "seen": _safe(lambda: _seen(day)),
                "roster": _safe(_roster)}

    def _src():
        return G["_swr"]("goals:src", 60, _fetch_src)

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
            return build_office(src, day, canon)
        key = "goals:" + scope_key
        _keys_used.add(key)
        return G["_swr"](key, 60, build)

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
        team = _team(s.get("phone", "")) if coord else None
        if want and not mgr and not coord:
            want = ""                                  # סוכן — תמיד הנתונים שלו
        if want and coord and canon(want) not in {canon(n) for n in team}:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        res = {"ok": True, "can_edit": mgr}
        if want or not (mgr or coord):
            name = _display(want or s.get("name", ""))
            o = _build("agent:" + canon(name), lambda: [name])
            row = (o.get("rows") or [{}])[0] if o.get("rows") else None
            res.update(view="agent", me=({"counts": row["counts"], "targets": row["targets"]} if row else None),
                       total=None, agent=name)
        elif coord:
            o = _build("team:" + G["_last9"](s.get("phone", "")), lambda: list(team))
            res.update(view="team", me=None, total=o["total"], agents=o["rows"])
        else:
            o = _build("office", None)
            res.update(view="office", me=None, total=o["total"], agents=o["rows"])
        res["day"] = _src().get("day") or _dt.datetime.now(_IL).date().isoformat()
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
