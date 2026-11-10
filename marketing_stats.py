"""[10/11 אייל] מסך שיווק ב-CRM — כמה פרסמנו היום / השבוע / החודש, לכל המשרד ולפי סוכן.

מודול טהור (stdlib + goals.parse_ts). נספר רק מה שבאמת עלה: ערוץ במצב 'ok'; תיק פרזנטציה — כשנשלח.
פוסט/סרטון עולים לעמוד המשרד ונזקפים לסוכן של הנכס; SOLD — לכל הסוכנים שבסרטון; תיק — לסוכן שלו.
"""
import datetime as _dt

from goals import parse_ts

try:
    from zoneinfo import ZoneInfo
    _IL = ZoneInfo("Asia/Jerusalem")
except Exception:   # pragma: no cover
    _IL = _dt.timezone(_dt.timedelta(hours=2))

NO_AGENT = "ללא סוכן"
KINDS = ("posts", "reels", "stories", "sold", "kits")


def period_range(period, now_ts):
    """(start, end) באפוק: day = מ-00:00 היום · week = מיום ראשון 00:00 · month = מה-1 בחודש 00:00. אחר → week."""
    now = _dt.datetime.fromtimestamp(now_ts, _IL)
    mid = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        start = mid
    elif period == "month":
        start = mid.replace(day=1)
    else:
        start = mid - _dt.timedelta(days=(now.weekday() + 1) % 7)
    return start.timestamp(), now_ts


def _ok(rec, ch):
    return isinstance(rec, dict) and rec.get(ch + "_status") == "ok"


def _video_ts(v):
    """הסרטון עולה אחרי האישור, או במועד שנקבע (שבת/לילה) — המאוחר מביניהם; אחרת מועד היצירה."""
    t = [x for x in (parse_ts(v.get("decided_at")), parse_ts(v.get("publish_at"))) if x]
    return max(t) if t else parse_ts(v.get("created_at"))


def count(posts, videos, solds, kits, start, end, agent_of_key, canon=None):
    """→ {'totals': {posts/reels/stories: {n,fb,ig}, sold/kits: {n}, total}, 'agents': [{name, <kinds>, total}]}."""
    canon = canon or (lambda s: " ".join(str(s or "").split()))
    tot = {"posts": {"n": 0, "fb": 0, "ig": 0}, "reels": {"n": 0, "fb": 0, "ig": 0},
           "stories": {"n": 0, "fb": 0, "ig": 0}, "sold": {"n": 0}, "kits": {"n": 0}}
    rows, names = {}, {}

    def inn(t):
        return t is not None and start <= t <= end

    def credit(name, kind):
        name = " ".join(str(name or "").split()) or NO_AGENT
        k = NO_AGENT if name == NO_AGENT else (canon(name) or name)
        if k not in rows:
            rows[k] = dict({c: 0 for c in KINDS}, total=0)
            names[k] = name
        rows[k][kind] += 1
        rows[k]["total"] += 1

    def key_agent(rec):
        try:
            return agent_of_key(str(rec.get("property_key") or "")) or ""
        except Exception:
            return ""

    for p in posts or []:
        if not isinstance(p, dict) or not inn(parse_ts(p.get("created_at"))):
            continue
        fb, ig = _ok(p, "fb"), _ok(p, "ig")
        if fb or ig:
            tot["posts"]["n"] += 1
            tot["posts"]["fb"] += fb
            tot["posts"]["ig"] += ig
            credit(key_agent(p), "posts")

    for v in videos or []:
        if not isinstance(v, dict) or not inn(_video_ts(v)):
            continue
        for kind, fbc, igc in (("reels", "fb_reel", "ig_reel"), ("stories", "fb_story", "ig_story")):
            fb, ig = _ok(v, fbc), _ok(v, igc)
            if fb or ig:
                tot[kind]["n"] += 1
                tot[kind]["fb"] += fb
                tot[kind]["ig"] += ig
                credit(key_agent(v), kind)

    for s in solds or []:
        if not isinstance(s, dict) or not inn(parse_ts(s.get("ts"))):
            continue
        if _ok(s, "ig_story") or _ok(s, "fb_story"):
            tot["sold"]["n"] += 1
            ags = [a for a in (s.get("agents") or []) if str(a or "").strip()] if isinstance(s.get("agents"), list) else []
            seen = set()
            for a in ags or [""]:
                k = canon(a) if a else NO_AGENT
                if k not in seen:   # אותו סוכן פעמיים בסרטון → נספר פעם אחת
                    seen.add(k)
                    credit(a, "sold")

    for k in kits or []:
        if isinstance(k, dict) and k.get("status") == "sent" and inn(parse_ts(k.get("sent_at"))):
            tot["kits"]["n"] += 1
            credit(k.get("agent_name"), "kits")

    tot["total"] = sum(tot[c]["n"] for c in KINDS)
    agents = [dict(name=names[k], **{c: r[c] for c in KINDS}, total=r["total"]) for k, r in rows.items()]
    agents.sort(key=lambda a: (a["name"] == NO_AGENT, -a["total"], a["name"]))
    return {"totals": tot, "agents": agents}
