"""office_presence.py — 'במשרד / מחוץ למשרד' לפי כתובת ה-IP (אייל 19/10: 'לדעת מי נמצא במשרד ומשתמש או מהבית').

כתובות ה-IP החיצוניות של הסניפים נשמרות בקונפיג `v2_office_ips` ([{branch, ip}]) מכרטיס בניהול.
כל פעימה (/v2/api/ping, כל ~45ש') נבדקת מול הרשימה; רק **מעבר** בין במשרד/מחוץ (או יום חדש) נרשם ביומן הפעילות
('מיקום: במשרד · ביאליק' / 'מיקום: מחוץ למשרד', פירוט: IP · מכשיר). מהשורות האלה יומן השימוש מחשב זמן במשרד.
בלי כתובות משרד מוגדרות — לא נרשם מיקום (רק IP ומכשיר בשורת הכניסה).
מגבלה: 'מחוץ למשרד' = לא ב-WiFi של אף סניף (בית, רכב, סלולר) — אי אפשר להבחין ביניהם.
נרשם מ-app.py:  office_presence.register(app, globals())
"""
from __future__ import annotations
import ipaddress
import re
import threading

ACTION_IN, ACTION_OUT = "מיקום: במשרד · ", "מיקום: מחוץ למשרד"
MAX_ENTRIES = 20


def _now_il():
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("Asia/Jerusalem"))
    except Exception:
        return _dt.datetime.utcnow() + _dt.timedelta(hours=3)


def norm_ip(s):
    """כתובת תקינה בכתיב אחיד ('' אם לא תקינה)."""
    try:
        return str(ipaddress.ip_address(str(s or "").strip()))
    except ValueError:
        return ""


def client_ip(headers, remote_addr):
    """הכתובת של המשתמש: CF-Connecting-IP (Cloudflare מול Render), אחרת הראשונה ב-X-Forwarded-For."""
    h = headers or {}
    for v in (h.get("CF-Connecting-IP"), (h.get("X-Forwarded-For") or "").split(",")[0], remote_addr):
        ip = norm_ip(v)
        if ip:
            return ip
    return ""


def device_label(ua):
    u = str(ua or "")
    if not u:
        return ""
    if "iPad" in u:
        return "אייפד"
    if "iPhone" in u:
        return "אייפון"
    if "Android" in u:
        return "אנדרואיד"
    return "מחשב"


def clean_entries(entries):
    """רשימת הכתובות מהקונפיג — רק תקינות, בלי כפולות, עד MAX_ENTRIES."""
    out, seen = [], set()
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        ip, br = norm_ip(e.get("ip")), re.sub(r"\s+", " ", str(e.get("branch", "") or "")).strip()[:30]
        if ip and br and ip not in seen:
            seen.add(ip)
            out.append(dict(e, ip=ip, branch=br))
    return out[:MAX_ENTRIES]


def place_for_ip(ip, entries):
    """שם הסניף שהכתובת שלו, או '' (מחוץ למשרד)."""
    ip = norm_ip(ip)
    if not ip:
        return ""
    for e in clean_entries(entries):
        if e["ip"] == ip:
            return e["branch"]
    return ""


def where_label(headers, remote_addr, entries):
    """פירוט לשורת הכניסה ביומן: 'IP 1.2.3.4 · אייפון · במשרד ביאליק' (התווית רק כשהוגדרו כתובות משרד)."""
    h = headers or {}
    ip = client_ip(h, remote_addr)
    parts = ["IP " + ip] if ip else []
    dev = device_label(h.get("User-Agent"))
    if dev:
        parts.append(dev)
    if clean_entries(entries) and ip:
        pl = place_for_ip(ip, entries)
        parts.append(("במשרד " + pl) if pl else "מחוץ למשרד")
    return " · ".join(parts)


def presence_change(state, phone, place, now):
    """state: טלפון → {place, day, ts}. מחזיר שם פעולה לרישום כשהמקום השתנה או שהתחיל יום חדש, אחרת None."""
    day = now.strftime("%Y-%m-%d")
    prev = state.get(phone)
    state[phone] = {"place": place, "day": day, "ts": now.timestamp()}
    if prev and prev.get("place") == place and prev.get("day") == day:
        return None
    return (ACTION_IN + place) if place else ACTION_OUT


def timeline_from_activity(items):
    """שורות 'מיקום' מיומן הפעילות → טלפון(9 ספרות) → [(ts, במשרד?)] ממוין."""
    out = {}
    for it in items or []:
        a = str(it.get("action", "") or "")
        if not a.startswith("מיקום:"):
            continue
        ph = re.sub(r"\D", "", str(it.get("phone", "") or ""))[-9:]
        try:
            ts = float(it.get("ts") or 0)
        except (TypeError, ValueError):
            continue
        if ph and ts:
            out.setdefault(ph, []).append((ts, a.startswith(ACTION_IN)))
    for v in out.values():
        v.sort()
    return out


def _in_office(timeline, phone, ts):
    st = False
    for t, inside in timeline.get(phone, ()):
        if t > ts:
            break
        st = inside
    return st


def office_minutes(pts, timeline):
    """pts: [(ts, phone9)] של סוכן אחד. אותו כלל סשנים כמו יומן השימוש (פער > 90ש' = סשן חדש, פעימה בודדת ≈ 0.75 דק');
    כל קטע בין שתי פעימות נזקף למקום של הפעימה הראשונה בו."""
    pts = sorted(pts)
    total = 0.0
    i = 0
    while i < len(pts):
        j = i
        while j + 1 < len(pts) and pts[j + 1][0] - pts[j][0] <= 90:
            j += 1
        if j == i or pts[j][0] - pts[i][0] < 45:
            total += 0.75 if _in_office(timeline, pts[i][1], pts[i][0]) else 0.0
        else:
            for k in range(i, j):
                if _in_office(timeline, pts[k][1], pts[k][0]):
                    total += (pts[k + 1][0] - pts[k][0]) / 60.0
        i = j + 1
    return total


def stale_warning(entries, state, now):
    """כתובות מוגדרות, יום א'-ה' אחרי 12:00, לפחות 3 משתמשים היום — ואף אחד לא זוהה במשרד → כנראה הכתובת השתנתה."""
    if not clean_entries(entries) or now.weekday() in (4, 5) or now.hour < 12:
        return False
    day = now.strftime("%Y-%m-%d")
    today = [v for v in (state or {}).values() if v.get("day") == day]
    return len(today) >= 3 and not any(v.get("place") for v in today)


def register(app, G):
    from flask import request, jsonify
    log = G.get("log")
    state, lock = {}, threading.Lock()

    def _entries():
        try:
            return clean_entries((G["_load_config"]() or {}).get("v2_office_ips") or [])
        except Exception:
            return []

    def presence_place(phone):
        """None = לא הוגדרו כתובות משרד / לא נראה; '' = מחוץ למשרד; אחרת שם הסניף."""
        if not _entries():
            return None
        with lock:
            v = state.get(str(phone or "")[-9:])
        return None if v is None else v["place"]
    app.presence_place = presence_place

    @app.before_request
    def _presence_ping():
        if request.method != "POST" or request.path != "/v2/api/ping":
            return None
        try:
            ents = _entries()
            if not ents:
                return None
            s = G["_web_auth"]()
            if not s:
                return None
            ph = G["_last9"](s.get("phone", ""))
            ip = client_ip(request.headers, request.remote_addr)
            with lock:
                act = presence_change(state, ph, place_for_ip(ip, ents), _now_il())
            if act:
                dev = device_label(request.headers.get("User-Agent"))
                G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), act,
                                   " · ".join(x for x in ("IP " + ip if ip else "", dev) if x))
        except Exception as e:
            if log: log.warning(f"presence ping: {e}")
        return None

    def _guard():
        s = G["_web_auth"]()
        return s if (s and G["_is_dev"](s.get("phone", ""))) else None

    @app.route("/v2/api/admin/office_ips", methods=["GET", "POST"])
    def v2_api_office_ips():
        s = _guard()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        if request.method == "POST":
            b = request.get_json(silent=True) or {}
            act = b.get("action")
            ip = norm_ip(b.get("ip"))
            br = re.sub(r"\s+", " ", str(b.get("branch", "") or "")).strip()[:30]
            if not ip:
                return jsonify({"ok": False, "reason": "bad_ip"})
            if act == "add" and not br:
                return jsonify({"ok": False, "reason": "no_branch"})
            if act not in ("add", "del"):
                return jsonify({"ok": False, "reason": "bad_action"}), 400

            def _mut(cfg):
                cur = [e for e in clean_entries(cfg.get("v2_office_ips") or []) if e["ip"] != ip]
                if act == "add":
                    cur.append({"branch": br, "ip": ip, "by": s.get("name", ""), "at": _now_il().strftime("%d/%m/%Y")})
                cfg["v2_office_ips"] = cur[:MAX_ENTRIES]
            ok = G["_config_mutate"](_mut)
            if isinstance(ok, tuple):
                ok = ok[0]
            if not ok:
                return jsonify({"ok": False, "reason": "save_failed"})
            G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), "כתובות המשרד",
                               ("נוספה " + br + " · " if act == "add" else "נמחקה ") + ip)
        ents = _entries()
        my = client_ip(request.headers, request.remote_addr)
        with lock:
            warn = stale_warning(ents, state, _now_il())
        return jsonify({"ok": True, "entries": ents, "my_ip": my, "my_place": place_for_ip(my, ents), "warn": warn})
