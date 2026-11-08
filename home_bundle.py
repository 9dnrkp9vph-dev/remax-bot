# home_bundle.py — [HOME-BUNDLE 06/11] "איך כל האפליקציות נראות מהירות?" (אייל) → "כן תבנה את 1 ו-2".
# (2) בקשה אחת למסך הבית: במקום 9 קריאות נפרדות שעומדות בתור על worker אחד, הבית מבקש
#     /v2/api/home/bundle — השרת מריץ את אותם ראוטים בדיוק (בלי לשכפל לוגיקה), במקביל,
#     ומחזיר רק את השדות שהבית צריך (במקום מאות KB של קונים/חתימות/נכס נולד).
# (1) "סל בית" מוכן מראש: thread רקע שבונה את המטמונים האישיים (דוח, בריף, קונים, חתימות…)
#     של המשתמשים הפעילים — מיד אחרי עליית שרת, בתחילת יום העבודה, וכל 10 דק' למי שפעיל
#     בשעות האחרונות. כך גם מי שפותח ראשון אחרי פריסה מקבל בית מהיר.
# הלוגיקה הטהורה למעלה (נבדקת), הראוטים וה-thread ב-register.
import datetime as _dt
import secrets as _secrets
import threading as _threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, wait as _fwait

try:
    from zoneinfo import ZoneInfo
    _IL = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover
    _IL = _dt.timezone(_dt.timedelta(hours=2))

# החלקים של הבית: מפתח → כתובת. הסדר קובע (פגישות לפני הדוח — היומן הוא המקור המועדף).
PARTS = (
    ("meets", "/api/newborn/meetings"),
    ("report", "/api/report?period=week"),
    ("buyers", "/api/my/buyers"),
    ("props", "/api/my/properties"),
    ("sigs", "/api/signatures"),
    ("drafts", "/v2/api/sign/drafts"),
    ("deals", "/api/deals"),
    ("nb", "/api/newborn?limit=120"),
    ("dialer", "/v2/api/dialer/access"),
)
# החימום: בלי נכס נולד (תוצאה אישית של ~5MB — דליפת הזיכרון של 05/11) ובלי החלקים הזולים
WARM_PATHS = ("/api/newborn/meetings", "/api/report?period=week", "/api/my/buyers",
              "/api/my/properties", "/api/signatures", "/v2/api/brief")

BUNDLE_TIMEOUT = 25        # חלק שלא חזר עד אז — לא נכלל; הקליינט מביא אותו לבד
WARM_EVERY = 600           # כל 10 דק'
WARM_RECENT = 3 * 3600     # בחימום התקופתי — מי שהשתמש ב-3 השעות האחרונות
WARM_DAYSTART = 2 * 86400  # בעלייה ובתחילת היום — מי שהשתמש ביומיים האחרונים
WARM_GAP = 1.5             # הפסקה בין משתמשים — שהחימום לא יתחרה בבקשות אמיתיות
WARM_USER_TIMEOUT = 90     # משתמש שהחימום שלו לא נגמר עד אז — מדלגים עליו (ה-thread שלו ממשיך ברקע)
WARM_STUCK_MAX = 3         # יותר מזה משתמשים תקועים בבת אחת — לא מתחילים סבב חדש עד שישתחררו


def trim_part(key, j):
    """מצמצם תשובת ראוט לשדות שמסך הבית קורא. None = לא לכלול (שגיאה/מבנה לא צפוי)."""
    if not isinstance(j, dict) or j.get("ok") is False:
        return None
    if key == "report":
        sm = j.get("summary") or {}
        sl = sm.get("sigsList") or []
        return {"ok": True, "label": j.get("label"), "listings": j.get("listings") or 0,
                "meetings": j.get("meetings"),
                "summary": {"calls": {"total": ((sm.get("calls") or {}).get("total") or 0)},
                            "sigs": {"total": ((sm.get("sigs") or {}).get("total") or 0)},
                            "sigsList": sl[:1],
                            "exclusives": [{} for _ in (sm.get("exclusives") or [])]}}
    if key == "buyers":
        return {"ok": True, "results": [{"date": b.get("date", ""), "agent": b.get("agent", "")}
                                        for b in (j.get("results") or []) if isinstance(b, dict)]}
    if key == "props":
        return {"ok": True, "count": j.get("count") or 0}
    if key == "sigs":
        cut = _time.time() - 8 * 86400   # הבית סופר גיוסים של 7 ימים — יום מרווח
        out = []
        for g in (j.get("signatures") or []):
            if not isinstance(g, dict):
                continue
            try:
                ts = float(g.get("ts") or 0)
            except Exception:
                ts = 0
            if ts >= cut:
                out.append({"type": g.get("type", ""), "ts": g.get("ts") or 0,
                            "address": g.get("address", ""), "client": g.get("client", "")})
        return {"ok": True, "signatures": out}
    if key == "deals":
        return {"ok": True, "items": [{"deal": bool(x.get("deal"))}
                                      for x in (j.get("items") or []) if isinstance(x, dict)]}
    if key == "nb":
        res = [r for r in (j.get("results") or []) if isinstance(r, dict)]
        return {"ok": True, "total": j.get("total") or len(res),
                "dropsToday": j.get("dropsToday") or {"nb": 0, "office": 0},   # [HOME-TILES 08/11]
                "results": [{"ageDays": r.get("ageDays"), "address": r.get("address", ""),
                             "city": r.get("city", "")} for r in res if r.get("ageDays") == 0]}
    if key == "dialer":
        return {"ok": True, "allowed": bool(j.get("allowed"))}
    return j   # meets / drafts — כמות שהם (הבית משתמש בכל השדות)


def work_hours(now):
    """שעות עבודה (שעון ישראל): א'-ה' 07:30-20:00, ו' 07:30-14:00. שבת — לא."""
    wd = now.weekday()   # 0=שני … 4=שישי, 5=שבת, 6=ראשון
    if wd == 5:
        return False
    m = now.hour * 60 + now.minute
    if m < 7 * 60 + 30:
        return False
    return m < (14 * 60 if wd == 4 else 20 * 60)


def warm_targets(seen, now_ts, window):
    """טלפונים שנראו בחלון — הפעיל ביותר קודם."""
    return [p for p, t in sorted(seen.items(), key=lambda kv: -kv[1]) if now_ts - t <= window]


def ping_epoch(ts):
    """'2026-11-06T08:15:00+00:00' / '...Z' → epoch; לא תקין → 0."""
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def register(app, G):
    from flask import request, jsonify, g

    log = G["log"]
    _web_sessions = G["_web_sessions"]
    _last9 = G["_last9"]
    _seen = {}            # טלפון → מתי נראה לאחרונה (בית או חימום-מקדים מהפעימות)
    _seen_lock = _threading.Lock()

    def _call(path, tok, warm=False):
        """מריץ ראוט קיים בתוך השרת, עם הטוקן של המשתמש → (status, json)."""
        p, _, qs = path.partition("?")
        with app.test_request_context(p, query_string=qs, headers={"X-Auth-Token": tok}):
            g.effie_warm = warm   # _log_activity מדלג בחימום — לא נרשמות פעולות שאף אחד לא עשה
            ep, args = app.url_map.bind("").match(p, method="GET")
            resp = app.make_response(app.view_functions[ep](**args))
            return resp.status_code, resp.get_json(silent=True)

    def _note(phone):
        ph = _last9(phone)
        if ph:
            with _seen_lock:
                _seen[ph] = _time.time()

    @app.route("/v2/api/home/bundle", methods=["GET"])
    def home_bundle():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        tok = request.headers.get("X-Auth-Token") or request.args.get("token") or ""
        _note(s.get("phone", ""))
        t0 = _time.time()
        ex = ThreadPoolExecutor(max_workers=5)
        futs = {ex.submit(_call, path, tok): key for key, path in PARTS}
        done, _ = _fwait(futs, timeout=BUNDLE_TIMEOUT)
        ex.shutdown(wait=False)   # חלק איטי ממשיך ברקע וממלא את המטמון לפעם הבאה
        parts, miss = {}, []
        for f, key in futs.items():
            part = None
            if f in done:
                try:
                    st, j = f.result()
                    if st == 200:
                        part = trim_part(key, j)
                except Exception as e:
                    log.warning(f"home bundle part {key} failed: {e}")
            if part is None:
                miss.append(key)
            else:
                parts[key] = part
        dt = _time.time() - t0
        if miss or dt > 8:
            log.info(f"home bundle: {dt:.1f}s miss={','.join(miss) or '-'}")
        return jsonify({"ok": True, "parts": parts, "miss": miss})

    def _warm_one(phone):
        tok = "warm:" + _secrets.token_hex(12)
        try:
            sess = G["_session_from_phone"](phone)
            if not sess or G["_is_suspended"](phone):
                return
            _web_sessions[tok] = sess
            for path in WARM_PATHS:
                try:
                    _call(path, tok, warm=True)
                except Exception as e:
                    log.warning(f"home warm {path} failed: {e}")
        finally:
            _web_sessions.pop(tok, None)

    def _seed_from_pings():
        sb = G.get("_sbdb")
        if not sb or not sb.enabled():
            return
        frm = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=WARM_DAYSTART)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = sb.fetch_pings_today(frm) or []
        with _seen_lock:
            for r in rows:
                ph = _last9((r or {}).get("phone", ""))
                ts = ping_epoch((r or {}).get("ts"))
                if ph and ts and ts > _seen.get(ph, 0):
                    _seen[ph] = ts
        log.info(f"home warm: seeded {len(_seen)} users from pings")

    # [HOME-WARM-TIMEOUT 08/11] ב-06/11 החימום נעצר ב-10:01 ולא חזר עד הפריסה, בלי שגיאה בלוג —
    # כנראה בקשה אחת שנתקעה ותקעה את כל הלולאה. עכשיו כל משתמש רץ ב-thread עם תקרת זמן;
    # משתמש שנתקע נרשם בלוג והחימום ממשיך לבא בתור.
    _stuck = {"n": 0}

    def _warm_one_limited(ph):
        if _stuck["n"] >= WARM_STUCK_MAX:
            return False
        done = _threading.Event()

        def run():
            try:
                _warm_one(ph)
            finally:
                done.set()
                if getattr(run, "late", False):
                    _stuck["n"] = max(0, _stuck["n"] - 1)

        _threading.Thread(target=run, daemon=True, name="home-warm-user").start()
        if done.wait(WARM_USER_TIMEOUT):
            return True
        run.late = True
        _stuck["n"] += 1
        log.warning(f"home warm: user …{str(ph)[-4:]} stuck > {WARM_USER_TIMEOUT}s — skipped (stuck={_stuck['n']})")
        return False

    def _round(window, why):
        with _seen_lock:
            targets = warm_targets(dict(_seen), _time.time(), window)
        if not targets:
            return
        if _stuck["n"] >= WARM_STUCK_MAX:
            log.warning(f"home warm ({why}): skipped — {_stuck['n']} users still stuck")
            return
        log.info(f"home warm ({why}): start {len(targets)} users")
        t0 = _time.time()
        skipped = 0
        for ph in targets:
            if not _warm_one_limited(ph):
                skipped += 1
            _time.sleep(WARM_GAP)
        log.info(f"home warm ({why}): {len(targets)} users in {_time.time() - t0:.0f}s"
                 + (f" skipped={skipped}" if skipped else ""))

    def _loop():
        _time.sleep(25)   # אחרי ה-cache warmer הוותיק (שמביא את המקורות המשותפים)
        try:
            _seed_from_pings()
        except Exception as e:
            log.warning(f"home warm seed failed: {e}")
        day_done = None
        booted = False
        while True:
            try:
                now = _dt.datetime.now(_IL)
                quiet = False
                try:
                    quiet = bool(G["_shabbat_quiet_now"]())
                except Exception:
                    pass
                if work_hours(now) and not quiet:
                    today = now.date()
                    if day_done != today:   # עלייה / בוקר חדש — כל מי שעבד ביומיים האחרונים
                        if booted:
                            try:
                                _seed_from_pings()
                            except Exception:
                                pass
                        _round(WARM_DAYSTART, "day-start" if booted else "boot")
                        day_done = today
                    else:
                        _round(WARM_RECENT, "recent")
                booted = True
            except Exception as e:
                log.warning(f"home warm loop: {e}")
            _time.sleep(WARM_EVERY)

    import os
    if os.environ.get("HOME_WARM", "1") != "0":
        _threading.Thread(target=_loop, daemon=True, name="home-warm").start()
        log.info("home warm started")
    return {"warm_one": _warm_one, "seen": _seen, "seed": _seed_from_pings, "round": _round, "stuck": _stuck}
