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

SETTINGS_KEYS = ("coop", "rank", "g_rating", "g_count", "g_url")
_SHOW_LINK = ("approved", "sent")


def send_review(G, rec, base) -> bool:
    """Implemented in Task 4."""
    return False


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
        return bool(s) and (s.get("role") == "admin" or is_owner(s))

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
        return bool(rec) and (is_admin(s) or kc.phone9(rec.get("agent_phone")) == kc.phone9(s.get("phone")))

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
            if rec.get("agent") and canon(rec.get("agent")) != canon(me):
                if not may_pick(s, rec["agent"]):
                    return jsonify({"ok": False, "reason": "forbidden"})
                agent_name, agent_phone = rec["agent"], phone_of(rec["agent"])
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
        if want and canon(want) != canon(agent_name):
            if may_pick(s, want):
                agent_name, agent_phone = norm(want), phone_of(norm(want))
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
        if vals.get("g_url") and not vals["g_url"].startswith("https://"):
            return jsonify({"ok": False, "reason": "g_url"})

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
