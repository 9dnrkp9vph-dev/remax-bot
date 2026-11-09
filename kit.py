# kit.py — תיק פרזנטציה לבעל נכס: ראוטים לסוכן (יצירה, רשימה, שליחה חוזרת, נשלח) והגדרות בעל המשרד.
# בלי AI. הנתונים נצלמים פעם אחת (kit_core.build_snapshot) ואייל מאשר לפני שמשהו מגיע לבעל הנכס.
import os
import re
import secrets
import threading
import time as _t
import datetime as _dt
import logging

import kit_core as kc

log = logging.getLogger(__name__)

# סמלי הרשתות לכפתורים בדף בעל הנכס (SVG בתוך הדף — בלי בקשות לאתרים חיצוניים)
_IS = "<svg class=\"ic\" viewBox=\"0 0 24 24\" width=\"22\" height=\"22\" aria-hidden=\"true\">"
_ICON = {
    "instagram": _IS + "<defs><linearGradient id=\"igg\" x1=\"0\" y1=\"1\" x2=\"1\" y2=\"0\"><stop offset=\"0\" stop-color=\"#FEDA75\"/>"
                 "<stop offset=\".35\" stop-color=\"#FA7E1E\"/><stop offset=\".6\" stop-color=\"#D62976\"/>"
                 "<stop offset=\"1\" stop-color=\"#4F5BD5\"/></linearGradient></defs>"
                 "<rect width=\"24\" height=\"24\" rx=\"6.5\" fill=\"url(#igg)\"/>"
                 "<rect x=\"5\" y=\"5\" width=\"14\" height=\"14\" rx=\"4\" fill=\"none\" stroke=\"#fff\" stroke-width=\"1.8\"/>"
                 "<circle cx=\"12\" cy=\"12\" r=\"3.4\" fill=\"none\" stroke=\"#fff\" stroke-width=\"1.8\"/>"
                 "<circle cx=\"16.4\" cy=\"7.6\" r=\"1.1\" fill=\"#fff\"/></svg>",
    "facebook": _IS + "<circle cx=\"12\" cy=\"12\" r=\"12\" fill=\"#1877F2\"/>"
                "<path d=\"M13.4 19.5v-6h2l.3-2.4h-2.3V9.6c0-.7.2-1.2 1.2-1.2h1.2V6.3a16 16 0 0 0-1.8-.1c-1.8 0-3 1.1-3 3.1v1.8H9v2.4h2v6z\" fill=\"#fff\"/></svg>",
    "google": _IS + "<circle cx=\"12\" cy=\"12\" r=\"12\" fill=\"#fff\"/>"
              "<path d=\"M19.6 12.2c0-.6 0-1.1-.2-1.6H12v3h4.3a3.7 3.7 0 0 1-1.6 2.4v2h2.6c1.5-1.4 2.3-3.4 2.3-5.8z\" fill=\"#4285F4\"/>"
              "<path d=\"M12 20c2.2 0 4-.7 5.3-2l-2.6-2a4.8 4.8 0 0 1-7.2-2.5H4.8v2A8 8 0 0 0 12 20z\" fill=\"#34A853\"/>"
              "<path d=\"M7.5 13.5a4.8 4.8 0 0 1 0-3v-2H4.8a8 8 0 0 0 0 7z\" fill=\"#FBBC05\"/>"
              "<path d=\"M12 7.2c1.2 0 2.3.4 3.2 1.2l2.3-2.3A8 8 0 0 0 4.8 8.5l2.7 2A4.8 4.8 0 0 1 12 7.2z\" fill=\"#EA4335\"/></svg>",
}

SETTINGS_KEYS = ("coop", "rank", "g_rating", "g_count", "g_url", "instagram", "facebook")
_SHOW_LINK = ("approved", "sent")


TICK_SEC = 600
_TOK_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
_IMG_CACHE_MAX = 20
_PING_GAP = 10


def _approver9(G):
    a = kc.phone9(os.environ.get("KIT_APPROVER"))
    if a:
        return a
    try:
        devs = sorted(G["DEV_PHONES"])
    except Exception:
        devs = []
    return kc.phone9(devs[0]) if devs else ""


def send_review(G, rec, base) -> bool:
    """שולח לאייל (או KIT_APPROVER) בוואטסאפ קישור לאישור התיק. בשעות שקט/שבת — מסמן review_due לסבב הבא."""
    sb = G["_sbdb"]
    if G["_quiet_hours"]() or G["_shabbat_quiet_now"]():
        sb.kit_update(rec["id"], {"review_due": True})
        return False
    to9 = _approver9(G)
    if not to9:
        return False
    snap = rec.get("snapshot") or {}
    place = ", ".join(x for x in (snap.get("street") or "", snap.get("city") or "") if x)
    text = "תיק פרזנטציה חדש לאישור\n%s · %s · %s\nלצפייה ולאישור: %s/v2/kit/review/%s" % (
        rec.get("agent_name") or "", rec.get("owner_name") or snap.get("owner") or "", place,
        base, rec.get("review_token") or "")
    ok = False
    try:
        ok = bool(G["send_text"]("972" + to9, text))
    except Exception as e:
        log.warning("kit send_review: send_text failed: %s", e)
    if ok:
        sb.kit_update(rec["id"], {"sent_review_at": _now_iso(), "review_due": False})
    else:   # הסבב הבא ינסה שוב
        sb.kit_update(rec["id"], {"review_due": True})
    return ok


def _kit_tick_once(G):
    """סבב אחד: תיקים ממתינים (שלא פגו) שסומנו review_due — נשלחים לאישור."""
    if G["_quiet_hours"]() or G["_shabbat_quiet_now"]():
        return 0
    now, base, sent = _t.time(), _base(), 0
    for r in G["_sbdb"].kit_list(None) or []:
        if r.get("review_due") and kc.eff_status(r, now) == "pending":
            if send_review(G, r, base):
                sent += 1
    return sent


def _kit_tick(G):
    """לולאת הרקע (thread daemon): כל TICK_SEC שניות."""
    _t.sleep(60)
    while True:
        try:
            _kit_tick_once(G)
        except Exception as e:
            log.warning("kit tick failed: %s", e)
        _t.sleep(TICK_SEC)


def _spawn(fn):
    threading.Thread(target=fn, daemon=True).start()


def _base():
    return os.environ.get("APP_BASE_URL", "https://remax-bot.onrender.com").rstrip("/")


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _s(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _nb_src(r):
    """שורת נכס נולד → שדות התיק (טלפון בעל הנכס נשאר מחוץ לצילום)."""
    r = r or {}
    return {"owner": _s(r.get("שם בעל הנכס")),
            "phone": kc.phone9(r.get("טלפון בעל הנכס-") or r.get("טלפון בעל הנכס")),
            "street": _s(r.get("רחוב1") or r.get("רחוב")), "city": _s(r.get("עיר")),
            "rooms": _s(r.get("חדרים")), "price": _s(r.get("מחיר")),
            "sqm": _s(r.get('מ"ר') or r.get('גודל במ"ר')), "ptype": _s(r.get("סוג נכס"))}


def register(app, G):
    from flask import jsonify, request

    def sb():
        return G["_sbdb"]

    def auth():
        s = G["_web_auth"]()
        if not s:
            return None, (jsonify({"ok": False, "auth": False}), 401)
        return s, None

    def real_name(s):
        try:
            return G["_display_name_for"](s.get("name") or "", s.get("phone") or "") or s.get("name") or ""
        except Exception:
            return s.get("name") or ""

    def canon(x):
        try:
            return G["_canon_key"](x)
        except Exception:
            return _s(x)

    def is_owner(s):
        return bool(s) and bool(s.get("dev") or G["_is_dev"](s.get("phone", "")))

    def is_admin(s):
        """מנהל/מפתח/בעל המשרד בלבד (כמו dialer.py) — הנה"ח ומזכירה (role=admin) הם כאן סוכנים רגילים."""
        return bool(s) and (s.get("drole") in ("manager", "developer") or is_owner(s))

    def norm(x):
        try:
            return G["_norm_name"](x)
        except Exception:
            return _s(x)

    def coord_team(s):
        """מתאמת — שמות הסוכנים המשויכים אליה (מנורמלים); אחרת None."""
        if not (s.get("role") == "coordinator" or s.get("drole") == "coordinator"):
            return None
        try:
            rec = (G["_coordinators_all"]() or {}).get(G["_last9"](s.get("phone", ""))) or {}
        except Exception:
            rec = {}
        return {norm(x) for x in (rec.get("names") or set()) if norm(x)}

    def may_pick(s, name):
        """מנהל/בעל המשרד — כל סוכן; מתאמת — רק סוכן מהצוות שלה; סוכן — אף אחד."""
        if is_admin(s):
            return True
        team = coord_team(s)
        return bool(team) and norm(name) in team

    def phone_of(name):
        try:
            for p in G["_phones_for_name"](name) or []:
                p9 = kc.phone9(p)
                if p9:
                    return p9
        except Exception:
            pass
        return ""

    def nb_row(key):
        if not key:
            return None
        try:
            for r in G["fetch_newborn"]() or []:
                if G["_nb_key"](r) == key:
                    return r
        except Exception as e:
            log.warning("kit nb lookup failed: %s", e)
        return None

    def log_act(s, action, detail=""):
        try:
            G["_log_activity"](real_name(s), s.get("role", ""), s.get("phone", ""), action, detail)
        except Exception:
            pass

    def fresh_tokens():
        return {"review_token": secrets.token_urlsafe(16), "view_token": secrets.token_urlsafe(16)}

    def dispatch_review(rec):
        base = _base()

        def run():
            try:
                send_review(G, rec, base)   # מוחלף בבדיקות דרך kit.send_review
            except Exception as e:
                log.warning("kit send_review failed: %s", e)
        _spawn(run)

    def can_touch(s, rec):
        """הסוכן של התיק, מי שיצר אותו, מתאמת על סוכן מהצוות שלה, או מנהל."""
        if not rec:
            return False
        me9 = kc.phone9(s.get("phone"))
        return bool(is_admin(s) or (me9 and me9 in (kc.phone9(rec.get("agent_phone")), kc.phone9(rec.get("created_by_phone"))))
                    or (rec.get("agent_name") and may_pick(s, rec.get("agent_name"))))

    # ── יצירה ────────────────────────────────────────────────────────────
    @app.route("/v2/api/kit/create", methods=["POST"])
    def kit_api_create():
        s, err = auth()
        if err:
            return err
        j = request.get_json(silent=True) or {}
        source = str(j.get("source") or "")
        me = real_name(s)
        agent_name, agent_phone = me, kc.phone9(s.get("phone"))
        if source == "nb":
            key = str(j.get("key") or "")
            r = nb_row(key)
            if not r:
                return jsonify({"ok": False, "reason": "not_found"})
            src = dict(_nb_src(r), meet_at=_s(j.get("meet_at")), listing_key=key)
            if not src["owner"]:
                return jsonify({"ok": False, "reason": "owner"})
            if not src["phone"]:
                return jsonify({"ok": False, "reason": "phone"})
        elif source == "meet":
            skey = str(j.get("skey") or "")
            rec = ((G["_load_config"]() or {}).get("nbStatus") or {}).get(skey)
            if not isinstance(rec, dict):
                return jsonify({"ok": False, "reason": "not_found"})
            ragent = norm(rec.get("agent"))
            if ragent:
                if canon(ragent) != canon(norm(me)):
                    if not may_pick(s, ragent):
                        return jsonify({"ok": False, "reason": "forbidden"})
                    agent_name, agent_phone = ragent, phone_of(ragent)
            elif not is_admin(s) and (not kc.phone9(s.get("phone")) or kc.phone9(rec.get("by_phone") or rec.get("created_by_phone")) != kc.phone9(s.get("phone"))):
                return jsonify({"ok": False, "reason": "forbidden"})   # פגישה בלי סוכן — רק מי שקבע אותה
            pkey = str(rec.get("pkey") or "")
            lr = _nb_src(nb_row(pkey)) if nb_row(pkey) else {}
            src = {"owner": _s(rec.get("owner")), "phone": kc.phone9(rec.get("ophone")),
                   "street": _s(rec.get("addr")) or lr.get("street", ""), "city": lr.get("city", ""),
                   "rooms": lr.get("rooms", ""), "price": _s(rec.get("price")) or lr.get("price", ""),
                   "sqm": lr.get("sqm", ""), "ptype": lr.get("ptype", ""),
                   "meet_at": _s(rec.get("date")), "listing_key": pkey}
            if not src["owner"]:
                return jsonify({"ok": False, "reason": "owner"})
            if not src["phone"]:
                return jsonify({"ok": False, "reason": "phone"})
        elif source == "manual":
            form = dict(j, addr=j.get("street") or j.get("addr"))
            why = kc.manual_validate(form)
            if why:
                return jsonify({"ok": False, "reason": why})
            src = {"owner": _s(j.get("owner")), "phone": kc.phone9(j.get("phone")), "street": _s(form["addr"]),
                   "city": _s(j.get("city")), "rooms": _s(j.get("rooms")), "price": _s(j.get("price")),
                   "sqm": _s(j.get("sqm")), "ptype": _s(j.get("ptype")) or "דירה",
                   "meet_at": _s(j.get("meet_at")), "listing_key": ""}
        else:
            return jsonify({"ok": False, "reason": "source"})
        want = _s(j.get("agent"))
        if want and canon(norm(want)) != canon(norm(agent_name)):
            if may_pick(s, want):
                ph = phone_of(norm(want))
                if not ph:
                    return jsonify({"ok": False, "reason": "agent"})   # סוכן לא מוכר — בלי תיק
                agent_name, agent_phone = norm(want), ph
            elif source != "meet":   # סוכן/מתאמת שבחרו סוכן מחוץ להרשאה — חוזרים לסוכן של הסשן
                agent_name, agent_phone = me, kc.phone9(s.get("phone"))
        src.update(agent_name=agent_name, agent_phone=agent_phone)
        try:
            snap = kc.build_snapshot(G, src)
        except Exception as e:
            log.warning("kit build_snapshot failed: %s", e)
            return jsonify({"ok": False, "reason": "build"})
        row = dict(status="pending", agent_name=agent_name, agent_phone=agent_phone, created_by=me,
                   created_by_phone=kc.phone9(s.get("phone")), source=source, listing_key=src["listing_key"],
                   owner_name=src["owner"], owner_phone=src["phone"], snapshot=snap,
                   sent_review_at=_now_iso(), **fresh_tokens())
        rec = sb().kit_insert(row)
        if not rec:
            return jsonify({"ok": False, "reason": "db"})
        dispatch_review(rec)
        log_act(s, "תיק פרזנטציה — נשלח לאישור", "%s · %s" % (src["owner"], snap.get("street") or ""))
        return jsonify({"ok": True, "id": rec["id"], "status": "pending"})

    # ── הרשימה של הסוכן ──────────────────────────────────────────────────
    @app.route("/v2/api/kit/mine")
    def kit_api_mine():
        s, err = auth()
        if err:
            return err
        wide = request.args.get("all") == "1"
        team = coord_team(s) if wide and not is_admin(s) else None
        allp = wide and (is_admin(s) or team is not None)
        me9 = kc.phone9(s.get("phone"))
        try:
            rows = sb().kit_list(None if allp else me9) or []
        except Exception as e:
            log.warning("kit_list failed: %s", e)
            rows = []
        if team is not None:   # מתאמת — הצוות שלה והתיקים שלה, לא כל המשרד
            rows = [r for r in rows if kc.phone9(r.get("agent_phone")) == me9 or norm(r.get("agent_name")) in team]
        now, base, out = _t.time(), _base(), []
        for r in rows:
            snap = r.get("snapshot") or {}
            v = r.get("views") or {}
            st = kc.eff_status(r, now)
            it = {"id": r.get("id"), "status": st, "owner": r.get("owner_name") or snap.get("owner") or "",
                  "street": snap.get("street") or "", "city": snap.get("city") or "",
                  "created_at": r.get("created_at"), "reject_reason": r.get("reject_reason") or "",
                  "views": {"opens": int(v.get("opens") or 0), "secs": int(v.get("secs") or 0), "last": v.get("last")}}
            if allp:
                it["agent"] = r.get("agent_name") or ""
            if st in _SHOW_LINK and r.get("view_token"):
                url = base + "/k/" + r["view_token"]
                it.update(wa=kc.wa972(r.get("owner_phone")), url=url, text=kc.owner_message(snap) + "\n" + url)
            out.append(it)
        return jsonify({"ok": True, "kits": out})

    # ── שליחה חוזרת לאישור (אחרי דחייה/פקיעה) ────────────────────────────
    def src_from_rec(rec):
        snap = rec.get("snapshot") or {}
        L = snap.get("listing") or {}
        street = snap.get("street") or ""
        if rec.get("source") in ("nb", "meet"):
            r = nb_row(rec.get("listing_key"))
            if r:
                street = _nb_src(r)["street"] or street
        return {"owner": rec.get("owner_name") or snap.get("owner") or "", "phone": kc.phone9(rec.get("owner_phone")),
                "street": street, "city": snap.get("city") or "", "rooms": snap.get("rooms") or "",
                "price": snap.get("price") or "", "sqm": L.get("sqm") or "", "ptype": L.get("ptype") or "",
                "meet_at": snap.get("meet_at") or "", "listing_key": rec.get("listing_key") or "",
                "agent_name": rec.get("agent_name") or "", "agent_phone": rec.get("agent_phone") or ""}

    @app.route("/v2/api/kit/resend", methods=["POST"])
    def kit_api_resend():
        s, err = auth()
        if err:
            return err
        kid = (request.get_json(silent=True) or {}).get("id")
        rec = sb().kit_get(kid) if kid else None
        if not can_touch(s, rec):
            return jsonify({"ok": False, "reason": "not_found"})
        st = kc.eff_status(rec, _t.time())
        if st not in ("rejected", "expired"):
            return jsonify({"ok": False, "reason": "status"})
        try:
            snap = kc.build_snapshot(G, src_from_rec(rec))
        except Exception as e:
            log.warning("kit rebuild failed: %s", e)
            return jsonify({"ok": False, "reason": "build"})
        fields = dict(snapshot=snap, reject_reason=None, decided_by=None, decided_at=None,
                      sent_review_at=_now_iso(), **fresh_tokens())
        if not sb().kit_claim(rec["id"], rec.get("status") or "", "pending", fields):
            return jsonify({"ok": False, "reason": "status"})
        rec = sb().kit_get(rec["id"]) or dict(rec, status="pending", **fields)
        dispatch_review(rec)
        log_act(s, "תיק פרזנטציה — נשלח שוב לאישור", "%s · %s" % (rec.get("owner_name") or "", snap.get("street") or ""))
        return jsonify({"ok": True, "id": rec["id"], "status": "pending"})

    # ── הסוכן שלח לבעל הנכס ───────────────────────────────────────────────
    @app.route("/v2/api/kit/sent", methods=["POST"])
    def kit_api_sent():
        s, err = auth()
        if err:
            return err
        kid = (request.get_json(silent=True) or {}).get("id")
        rec = sb().kit_get(kid) if kid else None
        if not can_touch(s, rec):
            return jsonify({"ok": False, "reason": "not_found"})
        if rec.get("status") != "approved":
            return jsonify({"ok": False, "reason": "status"})
        if not sb().kit_claim(rec["id"], "approved", "sent", {"sent_at": _now_iso()}):
            return jsonify({"ok": False, "reason": "status"})
        snap = rec.get("snapshot") or {}
        log_act(s, "תיק פרזנטציה — נשלח לבעל הנכס", "%s · %s" % (rec.get("owner_name") or "", snap.get("street") or ""))
        return jsonify({"ok": True, "id": rec["id"], "status": "sent"})

    # ── הגדרות (בעל המשרד בלבד) ───────────────────────────────────────────
    @app.route("/v2/api/kit/settings", methods=["GET", "POST"])
    def kit_api_settings():
        s, err = auth()
        if err:
            return err
        if not is_owner(s):
            return jsonify({"ok": False, "error": "forbidden"}), 403
        if request.method == "GET":
            cfg = G["_load_config"]() or {}
            return jsonify({"ok": True, "settings": kc.kit_settings(cfg), "saved": dict(cfg.get("v2_kit") or {}),
                            "defaults": dict(kc.KIT_DEFAULTS)})
        j = request.get_json(silent=True) or {}
        vals = {k: _s(j.get(k))[:300] for k in SETTINGS_KEYS if k in j}
        for k in ("g_url", "instagram", "facebook"):
            if vals.get(k) and not vals[k].startswith("https://"):
                return jsonify({"ok": False, "reason": k})

        def fn(cfg):
            cur = dict(cfg.get("v2_kit") or {})
            cur.update(vals)
            cfg["v2_kit"] = cur
            return cur
        ok = G["_config_mutate"](fn)
        if not ok or not ok[0]:
            return jsonify({"ok": False, "reason": "save"})
        log_act(s, "תיק פרזנטציה — הגדרות", ", ".join(sorted(vals)))
        return jsonify({"ok": True, "settings": kc.kit_settings(G["_load_config"]() or {})})

    # ── [Task 4] אישור התיק + דף הצפייה של בעל הנכס ───────────────────────
    # פרטיות: /k/* מחזיר רק תמונות, PDF, דף עם פס קישורים ו-204 — לעולם לא את הצילום (JSON) או שדה ממנו כנתון.
    from flask import Response
    import html as _html
    import io as _io
    from collections import OrderedDict
    from urllib.parse import quote

    imgs_cache, imgs_lock = OrderedDict(), threading.Lock()
    pings, pings_lock = {}, threading.Lock()
    thr = {"t": None, "pid": None}
    thr_lock = threading.Lock()

    @app.before_request
    def _kit_kick():
        if os.environ.get("KIT_TICK", "1") == "0":
            return
        t = thr["t"]
        if t is not None and t.is_alive() and thr["pid"] == os.getpid():
            return
        with thr_lock:
            t = thr["t"]
            if t is not None and t.is_alive() and thr["pid"] == os.getpid():
                return
            thr["t"] = threading.Thread(target=_kit_tick, args=(G,), daemon=True, name="kit-review-tick")
            thr["t"].start()
            thr["pid"] = os.getpid()

    def esc(v):
        return _html.escape(str(v or ""), quote=True)

    def office_name():
        try:
            return str(((G["_load_config"]() or {}).get("v2_office") or {}).get("name") or "").strip()
        except Exception:
            return ""

    def resp(body, code=200, ctype="text/html; charset=utf-8", extra=None):
        h = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Content-Type": ctype}
        h.update(extra or {})
        return Response(body, status=code, headers=h)

    def by_tok(col, tok):
        if not _TOK_RE.match(str(tok or "")):
            return None
        try:
            return sb().kit_by_token(col, tok)
        except Exception as e:
            log.warning("kit_by_token failed: %s", e)
            return None

    def jpegs(rec):
        """עמודי התיק כ-JPEG (q85), במטמון לפי (id, זמן הצילום) — עד 20 תיקים. ping לא מבטל את המטמון."""
        snap = rec.get("snapshot") or {}
        key = (rec.get("id"), str(snap.get("made_at") or rec.get("updated_at") or ""))
        with imgs_lock:
            if key in imgs_cache:
                imgs_cache.move_to_end(key)
                return imgs_cache[key]
            import kit_render as kr
            out = []
            for im in kr.render_pages(snap):
                b = _io.BytesIO()
                im.save(b, "JPEG", quality=85, optimize=True)
                out.append(b.getvalue())
            imgs_cache[key] = out
            while len(imgs_cache) > _IMG_CACHE_MAX:
                imgs_cache.popitem(last=False)
            return out

    def img_resp(rec, n):
        try:
            pages = jpegs(rec)
        except Exception as e:
            log.warning("kit render failed: %s", e)
            return resp("", 500, "text/plain; charset=utf-8")
        if not 1 <= n <= len(pages):
            return resp("", 404, "text/plain; charset=utf-8")
        return resp(pages[n - 1], 200, "image/jpeg")

    def shell(title, body, script=""):
        return ("<!doctype html><html lang=\"he\" dir=\"rtl\"><head><meta charset=\"utf-8\">"
                "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                "<meta name=\"robots\" content=\"noindex,nofollow\"><meta name=\"referrer\" content=\"no-referrer\"><title>%s</title>"
                "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">"
                "<link href=\"https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800&display=swap\" rel=\"stylesheet\">"
                "<style>%s</style></head><body>%s%s</body></html>") % (esc(title), _CSS, body,
                                                                     ("<script>%s</script>" % script) if script else "")

    def closed_page(code=410):
        off = office_name()
        body = ("<main class=\"closed\"><div class=\"card\"><div class=\"off\">%s</div>"
                "<h1>התיק אינו זמין</h1><p>הקישור כבר לא פעיל. לפרטים אפשר לפנות לסוכן.</p></div></main>") % esc(off)
        return resp(shell(off or "התיק אינו זמין", body), code)

    # ── אישור (לאייל בלבד — מי שמחזיק את הקישור) ─────────────────────────
    _STATUS_LINE = {"approved": "התיק אושר ומחכה לסוכן", "sent": "התיק אושר ונשלח לבעל הנכס",
                    "rejected": "התיק נדחה", "expired": "פג תוקף האישור (48 שעות). הסוכן יכול לשלוח שוב."}

    @app.route("/v2/kit/review/<tok>", methods=["GET"])
    def kit_review_page(tok):
        rec = by_tok("review_token", tok)
        if not rec:
            return resp(shell("לא נמצא", "<main class=\"closed\"><div class=\"card\"><h1>הקישור לא נמצא</h1></div></main>"), 404)
        snap = rec.get("snapshot") or {}
        st = kc.eff_status(rec, _t.time())
        try:
            npages = len(jpegs(rec))
        except Exception as e:
            log.warning("kit review render failed: %s", e)
            npages = 0
        place = ", ".join(x for x in (snap.get("street") or "", snap.get("city") or "") if x)
        imgs = "".join("<img src=\"/v2/kit/review/%s/p%d.jpg\" alt=\"עמוד %d\" loading=\"lazy\">" % (esc(tok), i, i)
                       for i in range(1, npages + 1))
        if st == "pending":
            act = ("<section id=\"act\" class=\"bar\"><label for=\"why\">סיבת דחייה (לא חובה)</label>"
                   "<textarea id=\"why\" maxlength=\"300\" rows=\"3\"></textarea>"
                   "<button class=\"btn pri\" onclick=\"go('approve')\">אשר ושלח לסוכן</button>"
                   "<button class=\"btn sec\" onclick=\"go('reject')\">דחה</button>"
                   "<div id=\"msg\" class=\"msg\" role=\"status\" aria-live=\"polite\"></div></section>")
            script = ("function go(a){var bs=document.querySelectorAll('#act button');for(var i=0;i<bs.length;i++)bs[i].disabled=true;"
                      "var m=document.getElementById('msg');m.textContent='שומר…';"
                      "fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},"
                      "body:JSON.stringify({action:a,reason:document.getElementById('why').value})})"
                      ".then(function(r){return r.text();}).then(function(t){m.textContent=t;setTimeout(function(){location.reload();},1200);})"
                      ".catch(function(){m.textContent='שגיאה — נסה שוב';for(var i=0;i<bs.length;i++)bs[i].disabled=false;});}")
        else:
            line = _STATUS_LINE.get(st, st)
            if st == "rejected" and rec.get("reject_reason"):
                line += " · " + str(rec.get("reject_reason"))
            act = "<section class=\"bar\"><div class=\"status\">%s</div></section>" % esc(line)
            script = ""
        body = ("<main class=\"wrap\"><header class=\"head\"><div class=\"off\">%s</div><h1>תיק פרזנטציה לאישור</h1>"
                "<p>%s · %s · %s</p></header>%s<div class=\"pages\">%s</div></main>") % (
            esc(office_name()), esc(rec.get("agent_name")), esc(rec.get("owner_name") or snap.get("owner")), esc(place),
            act, imgs)
        return resp(shell("תיק פרזנטציה לאישור", body, script))

    @app.route("/v2/kit/review/<tok>", methods=["POST"])
    def kit_review_decide(tok):
        rec = by_tok("review_token", tok)
        if not rec:
            return resp("לא נמצא", 404, "text/plain; charset=utf-8")
        j = request.get_json(silent=True) or {}
        action = str(j.get("action") or "")
        s = G["_web_auth"]() if G.get("_web_auth") else None
        if s:
            who = real_name(s)
            who9 = kc.phone9(s.get("phone"))
        else:
            who9 = _approver9(G)
            try:
                who = G["_display_name_for"]("", who9) or "מאשר"
            except Exception:
                who = "מאשר"
        now = _t.time()
        new, msg = kc.decide(rec, action, who, now)   # פג תוקף / כבר הוחלט — לפני כל כתיבה
        if not new:
            return resp(msg, 200, "text/plain; charset=utf-8")
        reason = _s(j.get("reason"))[:300] if new == "rejected" else ""
        fields = {"decided_by": who, "decided_at": _now_iso(), "reject_reason": reason or None}
        if not sb().kit_claim(rec["id"], "pending", new, fields):
            cur = sb().kit_get(rec["id"]) or {}
            _, msg2 = kc.decide(cur, action, who, now)
            if msg2 not in ("כבר אושר", "כבר נדחה", "פג תוקף"):
                msg2 = "לא נשמר — נסה שוב"
            return resp(msg2, 200, "text/plain; charset=utf-8")
        snap = rec.get("snapshot") or {}
        detail = "%s · %s · %s" % (rec.get("agent_name") or "", rec.get("owner_name") or "", snap.get("street") or "")
        if reason:
            detail += " · " + reason
        try:
            G["_log_activity"](who, "admin", who9, "תיק פרזנטציה — " + ("אושר" if new == "approved" else "נדחה"), detail)
        except Exception:
            pass
        return resp(msg, 200, "text/plain; charset=utf-8")

    @app.route("/v2/kit/review/<tok>/p<int:n>.jpg")
    def kit_review_img(tok, n):
        rec = by_tok("review_token", tok)
        if not rec:
            return resp("", 404, "text/plain; charset=utf-8")
        return img_resp(rec, n)

    # ── הצד של בעל הנכס ──────────────────────────────────────────────────
    def open_kit(vtok):
        rec = by_tok("view_token", vtok)
        if rec and kc.eff_status(rec, _t.time()) in _SHOW_LINK:
            return rec
        return None

    def json_str(v):
        import json as _json
        return _json.dumps(v)

    def site_root():
        return os.environ.get("SITE_PUBLIC_URL", "https://refamily.co.il").rstrip("/")

    @app.route("/k/<vtok>")
    def kit_view_page(vtok):
        rec = open_kit(vtok)
        if not rec:
            return closed_page()
        snap = rec.get("snapshot") or {}
        ag = snap.get("agent") or {}
        agent = rec.get("agent_name") or ag.get("name") or ""
        claims = snap.get("claims") or {}
        off = office_name()
        imgs = "".join("<img src=\"/k/%s/p%d.jpg\" alt=\"עמוד %d\"%s>" % (esc(vtok), i, i, "" if i == 1 else " loading=\"lazy\"")
                       for i in range(1, len(jpegs(rec)) + 1))
        links = ["<a class=\"btn pri\" href=\"/k/%s.pdf\">הורד כ-PDF</a>" % esc(vtok)]
        g = str(claims.get("g_url") or "")
        if g.startswith("https://"):
            links.append("<a class=\"btn sec\" href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%sהעסק שלנו בגוגל · ביקורות</a>" % (esc(g), _ICON["google"]))
        for k, lbl in (("instagram", "אינסטגרם"), ("facebook", "פייסבוק")):
            u = str(claims.get(k) or "")
            if u.startswith("https://"):
                links.append("<a class=\"btn sec\" href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%s%s</a>" % (esc(u), _ICON[k], lbl))
        links.append("<a class=\"btn sec\" href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">לאתר הנכסים שלנו</a>" % esc(site_root()))
        su = str(ag.get("site_url") or "")
        if su.startswith("https://") and agent:
            links.append("<a class=\"btn sec\" href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">לעמוד של %s באתר</a>" % (esc(su), esc(agent)))
        wa = kc.wa972(rec.get("agent_phone"))
        if wa:
            links.append("<a class=\"btn wa\" href=\"https://wa.me/%s\" target=\"_blank\" rel=\"noopener noreferrer\">וואטסאפ ל%s</a>" % (wa, esc(agent)))
        body = "<main class=\"view\"><div class=\"pages\">%s</div><nav class=\"links\">%s</nav></main>" % (imgs, "".join(links))
        ping = "/k/%s/ping" % vtok
        script = ("(function(){var u=%s;function p(){if(document.visibilityState==='hidden')return;"
                  "try{fetch(u,{method:'POST',keepalive:true});}catch(e){}}"
                  "setTimeout(p,2000);setInterval(p,15000);})();") % json_str(ping)
        return resp(shell("תיק אישי" + (" · " + off if off else ""), body, script))

    @app.route("/k/<vtok>/p<int:n>.jpg")
    def kit_view_img(vtok, n):
        rec = open_kit(vtok)
        if not rec:
            return resp("", 410, "text/plain; charset=utf-8")
        return img_resp(rec, n)

    @app.route("/k/<vtok>.pdf")
    def kit_view_pdf(vtok):
        rec = open_kit(vtok)
        if not rec:
            return closed_page()
        try:
            from PIL import Image
            import kit_render as kr
            pdf = kr.render_pdf([Image.open(_io.BytesIO(b)).convert("RGB") for b in jpegs(rec)])
        except Exception as e:
            log.warning("kit pdf failed: %s", e)
            return resp("", 500, "text/plain; charset=utf-8")
        fn = quote(kc.file_name(rec.get("snapshot") or {}))
        return resp(pdf, 200, "application/pdf", {"Content-Disposition": "attachment; filename*=UTF-8''" + fn})

    @app.route("/k/<vtok>/ping", methods=["POST"])
    def kit_view_ping(vtok):
        rec = open_kit(vtok)
        if not rec:
            return resp("", 410, "text/plain; charset=utf-8")
        now = _t.time()
        with pings_lock:
            if now - pings.get(vtok, 0) < _PING_GAP:
                return resp("", 204, "text/plain; charset=utf-8")
            pings[vtok] = now
            if len(pings) > 2000:
                for k in [k for k, v in pings.items() if now - v > 60]:
                    pings.pop(k, None)
        try:
            sb().kit_update(rec["id"], {"views": kc.view_add(rec.get("views"), now)})
        except Exception as e:
            log.warning("kit ping failed: %s", e)
        return resp("", 204, "text/plain; charset=utf-8")


_CSS = (
    ":root{--navy:#1E3A5F;--cream:#F2EFE7;--blue:#2E6BD6;--green:#157A43;--muted:#5B6472}"
    "*{box-sizing:border-box}"
    "body{margin:0;background:#F2EFE7;color:#1E3A5F;font-family:'Heebo',Arial,sans-serif;direction:rtl;"
    "-webkit-font-smoothing:antialiased}"
    ".pages img{display:block;width:100%;height:auto;margin:0 0 12px;border-radius:20px;"
    "box-shadow:0 6px 20px rgba(30,58,95,.06);background:#fff}"
    ".view,.wrap{max-width:560px;margin:0 auto;padding:16px 16px 40px}"
    ".links,.bar{display:flex;flex-direction:column;gap:10px;margin:8px 0 20px}"
    ".btn{display:flex;align-items:center;justify-content:center;min-height:48px;padding:10px 18px;border-radius:14px;"
    "font:700 17px 'Heebo',Arial,sans-serif;text-decoration:none;cursor:pointer;border:1.5px solid transparent}"
    ".btn .ic{flex:none;margin-inline-end:10px}"
    ".btn.pri{background:#2E6BD6;color:#fff}"
    ".btn.sec{background:#fff;color:#1E3A5F;border-color:#D5D9E0}"
    ".btn.wa{background:#157A43;color:#fff}"
    ".btn:disabled{opacity:.55}"
    "textarea{width:100%;font:400 16px 'Heebo',Arial,sans-serif;padding:12px;border-radius:14px;border:1.5px solid #D5D9E0;"
    "background:#fff;color:#1E3A5F;resize:vertical}"
    "label{font-weight:500;color:#5B6472;font-size:15px}"
    ".head{margin:8px 0 12px}.head h1{margin:2px 0;font-size:24px;font-weight:800}.head p{margin:0;color:#5B6472}"
    ".off{font-weight:800;color:#1E3A5F;font-size:16px}"
    ".status{background:#fff;border-radius:16px;padding:14px 16px;font-weight:700}"
    ".msg{min-height:22px;font-weight:700;text-align:center}"
    ".closed{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}"
    ".closed .card{background:#fff;border-radius:22px;padding:32px 24px;text-align:center;max-width:420px;width:100%;"
    "box-shadow:0 6px 20px rgba(30,58,95,.06)}"
    ".closed h1{margin:10px 0 6px;font-size:24px;font-weight:800}.closed p{margin:0;color:#5B6472}"
)
