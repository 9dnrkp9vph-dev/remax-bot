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
