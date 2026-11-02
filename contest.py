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
                  _row("בן ובנימין", "בנימין אביטן", "בן קדוש"), _row("עוז דנילוב"), _row("ליאור גרונפינקל"),
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
    pts = contest.get("pts") or {}
    for k, label in (("gius", "גיוס"), ("meeting", "פגישה")):
        v = pts.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v > MAX_PTS:
            return "נקודות ל%s חייבות להיות בין 0 ל-%d" % (label, MAX_PTS)
    groups = contest.get("groups") or []
    if len(groups) != 2:
        return "בתחרות חייבות להיות בדיוק שתי קבוצות"
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


def ledger_update(ledger, nb, contest, now, display):
    old = ledger or {}
    if _bad(nb) or not isinstance(nb, dict):
        return copy.deepcopy(old)
    b0, b1 = day_bounds(_d(contest["start"]))[0], day_bounds(_d(contest["end"]))[1]
    new = {}
    for key, rec in nb.items():
        if not isinstance(rec, dict) or rec.get("status") != "meeting":
            continue
        at = parse_ts(rec.get("meeting_at"))
        if at is None or not (b0 <= at < b1):
            continue
        by = str(rec.get("by") or "").strip()
        new[key] = {"agent": str(rec.get("agent") or by).strip(), "by": display(by, rec.get("by_phone")) if by else "",
                    "at": at, "when": parse_ts(rec.get("date"))}
    for key, row in old.items():
        if key not in new:
            w = row.get("when")
            if w is not None and w <= now:
                new[key] = copy.deepcopy(row)
    return new


def listing_anchors(names, bounds, sigs, canon):
    if _bad(sigs):
        return None
    keys = {canon(n) for n in names}
    seen = set()
    for g in sigs or []:
        if g.get("type") != "בלעדיות" or not g.get("signed") or "בדיקה בדיקה" in str(g.get("address") or ""):
            continue
        ts = parse_ts(g.get("ts"))
        if ts is not None and bounds[0] <= ts < bounds[1] and canon(g.get("agent")) in keys:
            seen.add(_anchor(g.get("address")))
    return seen


def _adj_sum(adjs, group, kind, label, canon):
    t = 0
    for a in adjs or []:
        if a.get("kind") == kind and canon(a.get("label")) == canon(label) and str(a.get("group")) in (group["name"], str(group.get("_i"))):
            t += int(a.get("pts") or 0)
    return t


def score(contest, ledger, sigs, adjustments, canon, now):
    pts = contest["pts"]
    s, e = _d(contest["start"]), _d(contest["end"])
    cb = (day_bounds(s)[0], day_bounds(e)[1])
    ps, pe = prev_month(s)
    pb = (day_bounds(ps)[0], day_bounds(pe)[1])
    today = _dt.datetime.fromtimestamp(now, _IL).date()
    rows_l = list((ledger or {}).values())
    out_groups, totals = [], []
    for gi, g in enumerate(contest["groups"]):
        g = dict(g, _i=gi)
        rows = []
        for r in g["rows"]:
            mem = {canon(m) for m in r["members"]}
            meetings = sum(1 for x in rows_l if canon(x.get("agent")) in mem)
            a = listing_anchors(r["members"], cb, sigs, canon)
            p = listing_anchors(r["members"], pb, sigs, canon)
            adj = _adj_sum(adjustments, g, "row", r["label"], canon)
            gius = None if a is None else len(a)
            o = {"label": r["label"], "members": list(r["members"]), "meetings": meetings, "gius": gius,
                 "adj": adj, "points": (gius or 0) * pts["gius"] + meetings * pts["meeting"] + adj,
                 "pd": None if p is None else len(p)}
            if a is None:
                o["partial"] = True
            rows.append(o)
        rows.sort(key=lambda x: -x["points"])
        for i, o in enumerate(rows):
            o["rank"] = rows[i - 1]["rank"] if i and rows[i - 1]["points"] == o["points"] else i + 1
        coords = []
        for n in g.get("coords") or []:
            k = canon(n)
            m = sum(1 for x in rows_l if canon(x.get("by")) == k and canon(x.get("agent")) != k)
            adj = _adj_sum(adjustments, g, "coord", n, canon)
            coords.append({"name": n, "meetings": m, "adj": adj, "points": m * pts["meeting"] + adj})
        total = sum(o["points"] for o in rows)
        totals.append(total)
        out_groups.append({"name": g["name"], "total": total, "rows": rows, "coords": coords})
    return {"id": contest["id"], "name": contest["name"], "start": contest["start"], "end": contest["end"],
            "days_left": max(0, (e - today).days + 1), "pts": dict(pts), "groups": out_groups,
            "leader": None if totals[0] == totals[1] else (0 if totals[0] > totals[1] else 1)}


# ── ראוטים ──────────────────────────────────────────────────────────────────
import copy as _copy
import hmac as _hmac
import os as _os
import time as _time
import uuid as _uuid

import goals as _goals


def _now():
    return _time.time()


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

    def _is_coord(s, cfg, ct):
        if s.get("role") == "coordinator" or s.get("drole") == "coordinator":
            return True
        k = canon(s.get("name"))
        if k:
            for it in (cfg or {}).get("coordinators") or []:
                if isinstance(it, dict) and k in (canon(it.get("coordinator")), canon(it.get("name"))):
                    return True
            if ct and any(canon(n) == k for g in ct.get("groups") or [] for n in g.get("coords") or []):
                return True
        try:
            if G["_last9"](s.get("phone")) in (G["_coordinators_all"]() or {}):
                return True
        except Exception:
            pass
        return False

    def _can_edit(s, cfg):
        if s.get("drole") not in ("manager", "developer"):
            return False
        cts = contests(cfg)
        return not _is_coord(s, cfg, pick(cfg, _today())[0] or (cts[0] if cts else None))

    def _me(s, ct):
        k = canon(s.get("name"))
        if not k or not ct:
            return None
        for gi, g in enumerate(ct["groups"]):
            for r in g["rows"]:
                if k in {canon(m) for m in r["members"]}:
                    return {"group": gi, "kind": "row", "label": r["label"]}
            for n in g.get("coords") or []:
                if canon(n) == k:
                    return {"group": gi, "kind": "coord", "label": n}
        return None

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
        sigs = _goals.g_safe(G, lambda: _goals.g_sigs(G, prev_month(_d(ct["start"]))[0]))
        if isinstance(sigs, Exception):
            sigs = None
        adj = ((cfg.get("v2_contest_adj") or {}).get(lid)) or []
        return score(ct, new, sigs, adj, canon, now)

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
            board = G["_swr"]("contest:%s:%s" % (ct["id"], today.isoformat()), 120,
                              lambda: _build(ct, G["_load_config"]() or {}), max_stale=600)
        return jsonify({"ok": True, "mode": mode, "board": board, "me": _me(s, ct) if s else None,
                        "can_edit": bool(s) and _can_edit(s, cfg)})

    def _mgr():
        s = G["_web_auth"]()
        if not s or not _can_edit(s, G["_load_config"]() or {}):
            return None
        return s

    def _clear(cid):
        for d in (_today(), _today() + _dt.timedelta(days=1), _today() - _dt.timedelta(days=1)):
            G["_cache_clear"]("contest:%s:%s" % (cid, d.isoformat()))

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
        if b.get("kind") not in ("row", "coord") or b.get("group") not in (0, 1) or isinstance(b.get("group"), bool) or not label:
            return jsonify({"ok": False, "error": "פרטי התיקון לא תקינים"}), 400
        a = {"id": _uuid.uuid4().hex[:8], "group": b["group"], "kind": b["kind"], "label": label, "pts": p,
             "reason": reason, "by": s.get("name", ""), "at": _now()}

        def fn2(c):
            m = c.get("v2_contest_adj")
            m = m if isinstance(m, dict) else {}
            m[cid] = list(m.get(cid) or []) + [a]
            c["v2_contest_adj"] = m
        G["_config_mutate"](fn2)
        _clear(cid)
        _log(s, "תחרות — תיקון ידני", "%s · %s · %s" % (label, p, reason))
        return jsonify({"ok": True, "id": a["id"]})
