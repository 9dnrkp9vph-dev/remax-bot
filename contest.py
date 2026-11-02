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
        return jsonify({"ok": True, "mode": mode, "board": board, "me": _me(s, ct) if s else None,
                        "can_edit": edit, "adjustments": adjs, "def": dfn})

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
      font-size:11px;font-weight:800;border-radius:99px;padding:2px 10px;white-space:nowrap}
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
  .ck.tv{padding:26px 34px 30px;border-radius:28px}
  .ck.tv .ck-top{font-size:22px}
  .ck.tv .ck-trophy{width:76px;height:76px;margin:10px auto 6px}
  .ck.tv .ck-h{font-size:48px}.ck.tv .ck-sub,.ck.tv .ck-gap{font-size:24px}
  .ck-cols{display:flex;gap:28px;margin-top:22px}
  .ck-col{flex:1;min-width:0;border-radius:24px;padding:18px 22px;background:rgba(255,255,255,.07);border:2px solid rgba(255,255,255,.12)}
  .ck-col.lead{background:rgba(228,197,107,.13);border-color:#E4C56B}
  .ck-col .ch{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
  .ck-col .cn{font-size:34px;font-weight:800}
  .ck-col .cp{font-size:64px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}
  .ck-col.lead .cp{color:#E4C56B}
  .ck-col .cp small{font-size:20px;font-weight:600;opacity:.75;margin-inline-start:8px}
  .ck-col .cr{display:flex;align-items:center;gap:14px;margin-top:10px;font-size:26px;border-top:1px solid rgba(255,255,255,.12);padding-top:10px}
  .ck-col .cr .pos{width:38px;height:38px;border-radius:50%;background:rgba(255,255,255,.12);font-weight:800;font-size:20px;
      display:flex;align-items:center;justify-content:center;flex:none}
  .ck-col .cr:first-of-type .pos{background:#E4C56B;color:#231700}
  .ck-col .cr .l{flex:1;min-width:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ck-col .cr .v{font-weight:800;font-variant-numeric:tabular-nums}
  .ck.tv .ck-track{height:14px;margin-top:22px}
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
    '</b> (לפי יום הקביעה) · <bdi dir="ltr">P.D.</bdi> = גיוסים בחודש הקודם';
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
  var r = m.r, gi = cNum(r.gius), pd = cNum(r.pd);
  if (gi != null && pd != null && gi > pd) return 'כבר עקפת את החודש הקודם';
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
    chips = '<div class="ck-chip"><b>' + cShow(r.meetings) + '</b><span>פגישות</span></div>';
    return '<div class="ck-me"><div class="t">הניקוד שלך</div><div class="big">' + cShow(r.points) +
      ' <small>נק\' · מתאמת</small></div><div class="ck-chips">' + chips + '</div></div>';
  }
  chips = '<div class="ck-chip g"><b>' + cShow(r.gius) + '</b><span>גיוסים</span></div>' +
    '<div class="ck-chip"><b>' + cShow(r.meetings) + '</b><span>פגישות</span></div>' +
    '<div class="ck-chip"><b>' + cShow(r.pd) + '</b><span><bdi dir="ltr">P.D.</bdi></span></div>';
  var nd = contestNudge(j);
  return '<div class="ck-me"><div class="t">הניקוד שלך</div><div class="big">' + cShow(r.points) +
    ' <small>נק\' · מקום ' + cShow(r.rank) + ' בקבוצה</small></div><div class="ck-chips">' + chips + '</div>' +
    (nd ? '<div class="ck-push">' + cEsc(nd) + '</div>' : '') + '</div>';
}
function contestTeamsHtml(j){
  var b = j.board, me = j.me, gs = b.groups || [];
  var t = gs.map(function(g, i){
    return '<div class="ck-team' + (b.leader === i ? ' lead' : '') + '">' +
      (me && me.group === i ? '<div class="mine">הקבוצה שלך</div>' : '') +
      '<div class="nm">' + cEsc(g.name) + '</div><div class="pts">' + cShow(g.total) + '</div><div class="u">נקודות</div></div>';
  });
  return '<div class="ck-vs">' + t.join('<div class="ck-vsx">מול</div>') + '</div>';
}
function contestTvHtml(j){
  var b = j && j.board;
  if (!b || !b.groups || b.groups.length < 2) return '';
  var gs = b.groups, win = j.mode === 'winner';
  var head = b.leader == null ? 'תיקו' : cEsc(gs[b.leader].name) + (win ? ' ניצחה' : ' מובילה');
  var cols = gs.map(function(g, i){
    var rows = (g.rows || []).slice().sort(function(x, y){ return (cNum(y.points) || 0) - (cNum(x.points) || 0); }).slice(0, 5);
    return '<div class="ck-col' + (b.leader === i ? ' lead' : '') + '"><div class="ch"><div class="cn">' + cEsc(g.name) +
      '</div><div class="cp">' + cShow(g.total) + '<small>נק\'</small></div></div>' +
      rows.map(function(r, k){
        return '<div class="cr"><div class="pos">' + (k + 1) + '</div><div class="l">' + cEsc(r.label) + '</div><div class="v">' + cShow(r.points) + '</div></div>';
      }).join('') + '</div>';
  }).join('');
  var a = Math.max(0, cNum(gs[0].total) || 0), c = Math.max(0, cNum(gs[1].total) || 0);
  var pa = (a + c) ? Math.round(a * 100 / (a + c)) : 50, gap = Math.abs((cNum(gs[0].total) || 0) - (cNum(gs[1].total) || 0));
  return '<div class="ck tv"><div class="ck-top"><span>' + cEsc(b.name) + '</span><span>' +
    cEsc(win ? contestRange(b.start, b.end) : contestDays(b.days_left)) + '</span></div>' +
    '<div class="ck-trophy">' + CONTEST_TROPHY + '</div><div class="ck-h">' + head + '</div>' +
    '<div class="ck-sub">' + (win ? 'התחרות הסתיימה' : (gap ? 'פער של ' + gap + ' נקודות' : 'תיקו')) + '</div>' +
    '<div class="ck-cols">' + cols + '</div>' +
    '<div class="ck-track"><i class="' + (b.leader === 0 ? 'lead' : '') + '" style="width:' + pa + '%"></i>' +
    '<i class="' + (b.leader === 1 ? 'lead' : '') + '" style="width:' + (100 - pa) + '%"></i></div></div>';
}
function contestCardHtml(j, opts){
  opts = opts || {};
  if (opts.tv) return contestTvHtml(j);
  if (j && j.mode === 'winner') return contestWinnerHtml(j, opts);
  var b = j && j.board;
  if (!b || !b.groups || b.groups.length < 2) return '';
  var gs = b.groups, a = Math.max(0, cNum(gs[0].total) || 0), c = Math.max(0, cNum(gs[1].total) || 0);
  var pa = (a + c) ? Math.round(a * 100 / (a + c)) : 50;
  var head = b.leader == null ? 'תיקו' : cEsc(gs[b.leader].name) + ' מובילה';
  var gap = Math.abs((cNum(gs[0].total) || 0) - (cNum(gs[1].total) || 0)), gapL = '';
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
    contestTeamsHtml(j) +
    '<div class="ck-track"><i class="' + (b.leader === 0 ? 'lead' : '') + '" style="width:' + pa + '%"></i>' +
    '<i class="' + (b.leader === 1 ? 'lead' : '') + '" style="width:' + (100 - pa) + '%"></i></div>' +
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
  var head = b.leader == null ? 'תיקו' : cEsc(b.groups[b.leader].name) + ' ניצחה';
  return '<div class="ck' + (opts.story ? ' story' : '') + (opts.tv ? ' tv' : '') + '">' +
    '<div class="ck-top"><span>' + cEsc(b.name) + '</span><span>' + cEsc(contestRange(b.start, b.end)) + '</span></div>' +
    '<div class="ck-trophy">' + CONTEST_TROPHY + '</div>' +
    '<div class="ck-h">' + head + '</div><div class="ck-sub">התחרות הסתיימה</div>' +
    contestTeamsHtml(j) + (top ? '<div class="ck-top3">' + top + '</div>' : '') +
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
  var me = j.me, ed = !!(j && j.can_edit);
  var rows = (g.rows || []).map(function(r){
    var mine = me && me.kind === 'row' && me.group === gi && me.label === r.label;
    return '<tr class="' + (mine ? 'me' : '') + (r.rank === 1 && r.points > 0 ? ' top1' : '') + '">' +
      '<td class="pos">' + cShow(r.rank) + '</td><td class="n">' + cEsc(r.label) + '</td>' +
      '<td>' + cShow(r.meetings) + '</td><td>' + cShow(r.gius) + '</td>' +
      contestPtsCell(j, gi, 'row', r.label, r.points, cNum(r.adj) || 0) +
      '<td class="pd">' + cShow(r.pd) + '</td>' + contestEditCell(j, gi, 'row', r.label) + '</tr>';
  }).join('');
  return '<table><tr><th></th><th>סוכן</th><th>פגישות</th><th>גיוסים</th><th>ניקוד</th><th><bdi dir="ltr">P.D.</bdi></th>' +
    (ed ? '<th></th>' : '') + '</tr>' + rows + '</table>';
}
function contestCoordsHtml(j, gi){
  var g = j && j.board && j.board.groups && j.board.groups[gi];
  if (!g || !(g.coords || []).length) return '';
  var me = j.me, ed = !!(j && j.can_edit);
  var rows = g.coords.map(function(c){
    var mine = me && me.kind === 'coord' && me.group === gi && me.label === c.name;
    return '<tr class="' + (mine ? 'me' : '') + '"><td class="n">' + cEsc(c.name) + '</td><td>' + cShow(c.meetings) + '</td>' +
      contestPtsCell(j, gi, 'coord', c.name, c.points, cNum(c.adj) || 0) + contestEditCell(j, gi, 'coord', c.name) + '</tr>';
  }).join('');
  return '<table><tr><th>מתאמת</th><th>פגישות</th><th>ניקוד</th>' + (ed ? '<th></th>' : '') + '</tr>' + rows + '</table>';
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
  th{font-size:11.5px;color:#5B6472;font-weight:600;text-align:center;padding:4px 2px}
  th:first-child,td:first-child{text-align:right}
  td{text-align:center;padding:8px 2px;border-top:1px solid #F0ECE3;font-variant-numeric:tabular-nums}
  td.pos{width:22px;color:#5B6472;font-weight:700;font-size:12px}
  td.n{font-weight:600;text-align:right}
  td.p{font-weight:800;color:#1E3A5F;white-space:nowrap}
  td.pd{color:#5B6472}
  td.ed{width:52px}
  tr.me td{background:#FFF8E6}
  tr.me td.n::after{content:" (את/ה)";color:#7A5E1C;font-size:11px;font-weight:700}
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
  if (SEL == null) SEL = (j.me && j.me.group != null) ? j.me.group : (b.leader != null ? b.leader : 0);
  var gs = b.groups, g = gs[SEL] || gs[0];
  var mini = gs.map(function(x, i){ return '<div class="' + (b.leader === i ? 'lead' : '') + '"><b>' + cShow(x.total) + '</b><span>' + cEsc(x.name) + '</span></div>'; }).join('');
  var seg = gs.map(function(x, i){ return '<button class="' + (i === SEL ? 'on' : '') + '" onclick="pick(' + i + ')">' + cEsc(x.name) + '</button>'; }).join('');
  var co = contestCoordsHtml(j, SEL);
  el('app').innerHTML =
    '<div class="hero"><div class="top"><button class="back" onclick="location.href=\'/v2/home\'" aria-label="חזרה">' + BACK_SVG + '</button>' +
      '<span>' + cEsc(j.mode === 'winner' ? 'התחרות הסתיימה' : contestDays(b.days_left)) + '</span></div>' +
      '<h2>' + cEsc(b.name) + '</h2><div class="sub">קבוצה מול קבוצה · ' + cEsc(contestRange(b.start, b.end)) + '</div>' +
      '<div class="mini-vs">' + mini + '</div></div>' +
    '<div class="rules">' + contestRules(b.pts) + '</div>' +
    (j.can_edit ? '<div class="adm"><button class="btn sec" onclick="editOpen()">עריכת התחרות</button>' +
      '<button class="btn sec" onclick="copyOpen()">תחרות חדשה (העתק)</button></div>' : '') +
    '<div class="seg">' + seg + '</div>' +
    '<div class="card"><h3>' + cEsc(g.name) + ' <span>' + cShow(g.total) + ' נק\'</span></h3>' + contestTableHtml(j, SEL, {}) + '</div>' +
    (co ? '<div class="card"><h3>המתאמות של ' + cEsc(g.name) + '</h3><p class="s">פגישות שתיאמו לסוכנים — נספרות להן וגם לסוכן, לא בסך הקבוצה</p>' + co + '</div>' : '') +
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
