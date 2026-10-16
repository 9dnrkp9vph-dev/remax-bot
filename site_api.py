"""site_api.py — ממשק אפי לאתר refamily.co.il (שלב ג', 13/10/2026).

מודול נפרד מ-effie_v2: ראוטים לאתר (חיפוש AI + טפסים במייל) וניהול האתר (הסתר/מומלץ, מסך "האתר").
נרשם מ-app.py אחרי effie_v2.register:  site_api.register_site(app, globals())
env: SITE_KEY — אותו ערך באתר ובאפי (ריק = הראוטים לאתר כבויים); SITE_PUBLIC_URL — כתובת האתר לקישור "צפה באתר".
"""
from __future__ import annotations
import hmac
import html as _html
import os
import re
import threading
import time

FORM_KINDS = {"value": "הערכת שווי", "contact": "צור קשר", "career": "קריירה"}
FIELD_LABELS = {"name": "שם", "phone": "טלפון", "address": "כתובת הנכס", "city": "עיר", "when": "מתי מתכננים למכור",
                "experience": "ניסיון בנדל\"ן", "message": "הודעה", "page": "עמוד"}
MAX_FEATURED = 6


def key_ok(given, expected) -> bool:
    return bool(expected) and bool(given) and hmac.compare_digest(str(given), str(expected))


def search_result(parsed, matches, hidden) -> dict:
    """תוצאות החיפוש החכם לאתר: רק מספרי מודעה של נכסים פעילים ולא מוסתרים — בלי שום פרט אישי."""
    keys = []
    for m in matches or []:
        row = m[1] if isinstance(m, (tuple, list)) else m
        lid = str(row.get("מספר מודעה", "") or "").strip()
        if not lid or lid in hidden or str(row.get("ירד מפרסום", "") or "").strip():
            continue
        if lid not in keys:
            keys.append(lid)
    return {"ok": True, "keys": keys[:200], "summary": str((parsed or {}).get("summary_he") or "")[:200]}


def form_email(kind, fields, office_name):
    """פנייה מהאתר → (נושא, HTML מוגן, טקסט)."""
    title = FORM_KINDS[kind]
    name = re.sub(r"\s+", " ", str(fields.get("name", "") or "")).strip()[:80]
    subject = "פנייה מהאתר — " + title + (" — " + name if name else "")
    rows = [(FIELD_LABELS[k], str(v or "")[:1500]) for k, v in fields.items()
            if k in FIELD_LABELS and str(v or "").strip()]
    text = "\n".join("%s: %s" % (l, v) for l, v in rows)
    html = ('<div dir="rtl" style="font-family:Arial,sans-serif;font-size:15px;color:#1E3A5F">'
            '<h2 style="margin:0 0 12px">' + _html.escape(subject) + '</h2><table cellpadding="6">' +
            "".join('<tr><td style="color:#6B7280">%s</td><td><b>%s</b></td></tr>'
                    % (_html.escape(l), _html.escape(v).replace("\n", "<br>")) for l, v in rows) +
            '</table><p style="color:#6B7280;font-size:12px">נשלח מהאתר של ' + _html.escape(office_name or "") +
            '</p></div>')
    return subject, html, text


def prop_flags(rows):
    """שורות website_settings → (מוסתרים:set, מומלצים:list לפי סדר העדכון)."""
    hidden, featured = set(), []
    for r in rows or []:
        if r.get("kind") != "prop":
            continue
        d = r.get("data") or {}
        k = str(r.get("key") or "")
        if d.get("hidden"):
            hidden.add(k)
        if d.get("featured") and k not in featured:
            featured.append(k)
    return hidden, featured


SITE_EDITORS = ("secretary", "manager", "developer")


def can_edit_prop(sess, row, owns, is_dev) -> bool:
    """'הסתר מהאתר' — המזכירה (וגם מנהל ומפתח). סוכן לא משנה כלום באתר (אייל 13/10: 'הכל דרך המזכירה');
    'מומלץ באתר' = הנכס החם של הסטורי (אחד לסוכן) — לא כפתור נפרד."""
    return bool(sess) and (bool(is_dev) or sess.get("drole") in SITE_EDITORS)


PAGE_LIMITS = {"hero_sub": 220, "approach": 600}
CITY_MAX = 600   # תיאור עיר — כמו שהאתר מציג (היה 400 וקטע טיוטות באמצע משפט, 15/10)
SOCIAL_HOSTS = {"facebook": ("facebook.com",), "instagram": ("instagram.com",), "youtube": ("youtube.com", "youtu.be")}


BIO_MAX = 1500   # תיאור סוכן באתר — כולל שורות (ייבוא מהאתר הישן 14/10; היה 300 ושורה אחת)


def _plain(t, n):
    t = re.sub(r"<[^>]*>", "", str(t or ""))
    t = t.replace("<", "").replace(">", "")
    return re.sub(r"[ \t]+", " ", t).strip()[:n]


def _phone(v):
    d = re.sub(r"\D", "", str(v or ""))
    if d.startswith("972"):
        d = d[3:]
    if len(d) == 9 and not d.startswith("0"):
        d = "0" + d
    return d if (re.fullmatch(r"05\d{8}", d) or re.fullmatch(r"0[2-9]\d{7}", d)) else None


def clean_settings(body, agent_names):
    """ולידציה להגדרות האתר. מחזיר (pages, branches, social, agents, errors) — הערכים הנקיים + שגיאות לפי שדה."""
    body = body if isinstance(body, dict) else {}
    errors = {}
    pages = {}
    for k, v in (body.get("pages") or {}).items():
        k = str(k)
        if k in PAGE_LIMITS:
            pages[k] = _plain(v, PAGE_LIMITS[k])
        elif k.startswith("city:") and len(k) <= 40:
            pages[k] = _plain(v, CITY_MAX)
    branches = []
    for b in (body.get("branches") or [])[:5]:
        if not isinstance(b, dict):
            continue
        nm, ph = _plain(b.get("name"), 30), _phone(b.get("phone"))
        if nm and ph:
            branches.append({"name": nm, "phone": ph})
        elif nm or str(b.get("phone") or "").strip():
            errors["branches"] = "שם סניף וטלפון תקין חובה בכל שורה"
    social = {}
    for k, v in (body.get("social") or {}).items():
        if k not in SOCIAL_HOSTS:
            continue
        v = str(v or "").strip()[:200]
        if not v:
            continue
        m = re.match(r"^https://(?:www\.|m\.)?([a-z0-9.-]+)(/[^\s<>\"']*)?$", v, re.I)
        if m and m.group(1).lower() in SOCIAL_HOSTS[k]:
            social[k] = v
        else:
            errors[k] = "קישור https לא תקין"
    known = set(agent_names)
    agents = {}
    for nm, d in (body.get("agents") or {}).items():
        if nm not in known or not isinstance(d, dict):
            continue
        try:
            order = max(0, min(999, int(d.get("order", 0))))
        except (TypeError, ValueError):
            order = 0
        agents[nm] = {"shown": bool(d.get("shown", True)), "order": order, "bio": _plain(d.get("bio"), BIO_MAX)}
    return pages, branches, social, agents, errors


def agents_directory(full, vphones, cfg, name_key, phones_for=None, roles_for=None):
    """מדריך הסוכנים לאתר (שרת-לשרת, במפתח): שם, כינויים, נייד אמיתי (לוואטסאפ בלבד — לא מוצג באתר),
    מספר וירטואלי ורישיון. מקורות: גיליון 'אנשי קשר' (fetch_agents_full), מספרים וירטואליים, וקונפיג אפי."""
    cfg = cfg or {}
    gone = {name_key(n) for n in (cfg.get("removedAgents") or []) + (cfg.get("purgedAgents") or [])}
    lic = cfg.get("v2_licenses") or {}
    vk = {name_key(k): v for k, v in (vphones or {}).items()}
    by = {}
    def slot(nm):
        nm = re.sub(r"\s+", " ", str(nm or "")).strip()
        if not nm or name_key(nm) in gone:
            return None
        return by.setdefault(name_key(nm), {"name": nm, "aliases": [], "phone": "", "vphone": "", "license": ""})
    for v in (full or {}).values():
        a = slot((v or {}).get("name"))
        if a:
            a["phone"] = a["phone"] or str(v.get("phone") or "").strip()
            a["license"] = a["license"] or str(v.get("license") or "").strip()
    for ag in cfg.get("agents") or []:
        a = slot((ag or {}).get("name"))
        if not a:
            continue
        a["aliases"] = [str(x) for x in (ag.get("aliases") or []) if str(x).strip()]
        a["phone"] = a["phone"] or str(ag.get("phone") or "").strip()
        a["vphone"] = a["vphone"] or str(ag.get("vphone") or "").strip()
    susp = {re.sub(r"\D", "", str(x or ""))[-9:] for x in (cfg.get("suspended") or [])} - {""}
    for k, a in by.items():
        a["vphone"] = a["vphone"] or str(vk.get(k, "") or "").strip()
        p9 = re.sub(r"\D", "", a["phone"])[-9:]
        a["license"] = str(lic.get(p9, "") or "").strip() or a["license"]
        mine = {p9} if p9 else set()
        if phones_for:   # לסוכן כמה טלפונים (גיליון/כניסה/קונפיג) — מושהה לפי כל אחד מהם
            try:
                mine |= {re.sub(r"\D", "", str(x or ""))[-9:] for x in (phones_for(a["name"]) or [])}
            except Exception:
                pass
        a["suspended"] = bool(mine & susp)   # 14/10: מושהה — האתר לא מציג אותו
        a["phones"] = sorted(x for x in mine if x)   # 15/10: תמונה באפי שמורה לפי טלפון הכניסה — האתר מנסה את כולם
        a["role"] = ""
        if roles_for:   # 15/10: תפקיד לפי כל הטלפונים של האדם — הנה"ח גוברת (חגית הופיעה באתר)
            rs = []
            for x in ([p9] if p9 else []) + sorted(mine - {p9}):
                try:
                    rs.append(str(roles_for(x) or ""))
                except Exception:
                    pass
            a["role"] = "accountant" if "accountant" in rs else next((r for r in rs if r and r != "agent"), rs[0] if rs else "")
    return list(by.values())


# ---- 'סוכן AI אישי' (14/10): גולש באתר → הודעה מוכנה לוואטסאפ הרשמי → דף קונה ----
LEAD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LEAD_RE = re.compile(r"^\s*היי,\s*אני\s*מחפש(?:/ת|ת)?:\s*(?P<q>.+?)\s*(?:\((?:קוד|חיפוש\s*מס[׳'\u0022]?)\s*(?P<code>[A-Z2-9]{4})\)\s*)?$", re.S)


def new_lead_code(rnd=None):
    import secrets
    pick = rnd or secrets.choice
    return "".join(pick(LEAD_ALPHABET) for _ in range(4))


def parse_lead_message(text):
    """הודעת 'סוכן AI אישי' → {'q', 'code'}; כל הודעה אחרת → None (רק הפורמט המדויק מפעיל)."""
    m = _LEAD_RE.match(str(text or ""))
    if not m:
        return None
    q = re.sub(r"\s+", " ", m.group("q")).strip()[:300]
    return {"q": q, "code": m.group("code") or ""} if q else None


def lead_reply(first, office, n, url, updated):
    hi = "שלום" + (" " + first if first else "") + ", כאן הסוכן האישי של " + office + ".\n"
    if updated:
        body = "עדכנתי לך את הדף האישי — %s:\n" % ("נכס אחד נוסף" if n == 1 else "%d נכסים נוספים" % n)
    else:
        body = ("מצאתי נכס אחד שמתאים" if n == 1 else "מצאתי %d נכסים שמתאימים" % n) + " למה שחיפשת — הכנתי לך דף אישי:\n"
    return hi + body + url + "\nבדף אפשר לסמן מה מתאים ומה לא, ונחזור אליכם."


def lead_ack(first, office):
    hi = ("שלום %s" % first) if first else "שלום"
    return ("%s, קיבלתי את הבקשה שלך.\n"
            "אני עובר עכשיו על כל הנכסים של %s ומדרג אותם לפי מה שכתבת — "
            "הדף האישי שלך עם הנכסים שהכי מתאימים יגיע כאן בעוד כמה שניות." % (hi, office))


def lead_no_match(first, office):
    return ("שלום" + (" " + first if first else "") + ", כאן הסוכן האישי של " + office + ".\n"
            "קיבלנו את הבקשה שלכם. כרגע אין נכס שמתאים בדיוק, ונחזור אליכם עם אפשרויות.")


def _leads_on():
    return (os.environ.get("SITE_LEADS") or "1").strip() != "0"


def register_site(app, G, store=None):
    from flask import request, jsonify
    log = G.get("log")
    _store = {"s": store}

    def st():
        if _store["s"] is None:
            _store["s"] = SettingsStore(G.get("_sbdb"))
        return _store["s"]

    # הגנה על אפי מעומס חיפושי האתר (כל חיפוש חדש = פענוח AI): עד 2 במקביל, ותקרה לדקה לכל האתר
    sem = threading.BoundedSemaphore(2)
    app.site_search_sem = sem
    _minute = {"t": [], "lock": threading.Lock()}

    def _minute_ok():
        cap = int((os.environ.get("SITE_SEARCH_PER_MIN") or "60").strip() or 60)
        now = time.time()
        with _minute["lock"]:
            _minute["t"] = [t for t in _minute["t"] if now - t < 60]
            if len(_minute["t"]) >= cap:
                return False
            _minute["t"].append(now)
            return True

    def _active_ids():
        return {str(r.get("מספר מודעה", "") or "").strip() for r in (G["fetch_sheet_rows"]() or [])
                if not str(r.get("ירד מפרסום", "") or "").strip()} - {""}

    def _site_key_ok(body):
        return key_ok((body or {}).get("key", ""), (os.environ.get("SITE_KEY") or "").strip())

    @app.route("/site/api/search", methods=["POST"])
    def site_api_search():
        b = request.get_json(silent=True) or {}
        if not _site_key_ok(b):
            return jsonify({"ok": False}), 403
        q = re.sub(r"\s+", " ", str(b.get("q", "") or "")).strip()[:120]
        if not q:
            return jsonify({"ok": True, "keys": [], "summary": ""})
        if not sem.acquire(blocking=False):
            return jsonify({"ok": False, "reason": "busy"})
        try:
            if not _minute_ok():
                return jsonify({"ok": False, "reason": "busy"})
            parsed = G["_parse_props_query"](q) or {}
            matches = G["search_listings_in_sheet"](parsed) if parsed else []
            hidden, _ = prop_flags(st().all())
            return jsonify(search_result(parsed, matches, hidden))
        except Exception as e:
            if log: log.warning(f"site search: {e}")
            return jsonify({"ok": False})
        finally:
            sem.release()

    @app.route("/site/api/agents", methods=["POST"])
    def site_api_agents():
        b = request.get_json(silent=True) or {}
        if not _site_key_ok(b):
            return jsonify({"ok": False}), 403
        try:
            return jsonify({"ok": True, "agents": agents_directory(G["fetch_agents_full"](), G["fetch_agent_virtual_phones"](),
                                                                   G["_load_config"]() or {}, G["_name_key"],
                                                                   phones_for=G["_phones_for_name"],
                                                                   roles_for=lambda p9: (G["_resolve_roles"](p9) or ("", ""))[1])})
        except Exception as e:
            if log: log.warning(f"site agents: {e}")
            return jsonify({"ok": False})

    @app.route("/site/api/lead", methods=["POST"])
    def site_api_lead():
        """האתר שומר את הבקשה ומקבל קוד שנכנס להודעת הוואטסאפ (תוקף 24 שעות)."""
        b = request.get_json(silent=True) or {}
        if not _site_key_ok(b):
            return jsonify({"ok": False}), 403
        q = re.sub(r"\s+", " ", str(b.get("q", "") or "")).strip()[:300]
        if len(q.split()) < 2 or not _leads_on():
            return jsonify({"ok": False})
        src = re.sub(r"[^a-z]", "", str(b.get("src", "") or ""))[:12]
        code = new_lead_code()

        def _put(cfg):
            now = time.time()
            leads = {k: v for k, v in (cfg.get("v2_site_leads") or {}).items() if now - (v.get("ts") or 0) < 86400}
            leads[code] = {"q": q, "src": src, "ts": now}
            cfg["v2_site_leads"] = dict(sorted(leads.items(), key=lambda kv: -kv[1]["ts"])[:500])
        try:
            G["_config_mutate"](_put)
            return jsonify({"ok": True, "code": code})
        except Exception as e:
            if log: log.warning(f"site lead: {e}")
            return jsonify({"ok": False})

    # ---- 'סוכן AI אישי': הודעה נכנסת בוואטסאפ הרשמי (נקרא מה-webhook של 360 ב-app.py) ----
    _lead_day = {}   # טלפון → חותמות זמן (עד 3 דפים ביום)
    _lead_lock = threading.Lock()
    _lead_work = threading.Lock()     # קונה+דף לליד אחד בכל רגע — שתי הודעות מהירות לא יוצרות שני קונים
    _lead_seen = {}                   # מזהה הודעה מ-360 → זמן (ניסיון חוזר של ה-webhook)
    _lead_nocode = []                 # הודעות בלי קוד תקף היום (תקרה כללית — הגנה מהודעות מזויפות)
    _lead_limit_pushed = {}           # טלפון → יום שבו כבר נשלח פוש 'הגבלה יומית'

    def _push(title, body, push_to):
        G["send_push"](title, body, *([push_to] if push_to else []))

    def _use_code(code):
        """קוד תקף (פחות מ-24 שעות) — מוחזר ונמחק (שימוש אחד); אחרת None."""
        got = {}
        def _take(cfg):
            leads = cfg.get("v2_site_leads") or {}
            v = leads.get(code)
            if v and time.time() - (v.get("ts") or 0) <= 86400:
                got["v"] = v
            leads.pop(code, None)
            cfg["v2_site_leads"] = leads
        try:
            G["_config_mutate"](_take)
        except Exception as e:
            if log: log.warning(f"site lead code: {e}")
        return got.get("v")

    def _lead_handle(wa_from, name, text, mid=""):
        if not _leads_on():
            return "ignored"
        m = parse_lead_message(text)
        if not m:
            return "ignored"
        now = time.time()
        with _lead_lock:
            if mid:
                for k in [k for k, t in _lead_seen.items() if now - t > 3600]:
                    _lead_seen.pop(k, None)
                if mid in _lead_seen:
                    return "duplicate"
                _lead_seen[mid] = now
        with _lead_work:
            return _lead_work_one(wa_from, name, m, now)

    def _lead_work_one(wa_from, name, m, now):
        cfg = G["_load_config"]() or {}
        stored = _use_code(m["code"]) if m["code"] else None   # קוד שפג/משומש — לפי טקסט ההודעה
        q, src = (stored["q"], stored.get("src", "")) if stored else (m["q"], "")
        if not stored:
            cap = int(os.environ.get("SITE_LEAD_NOCODE_DAY", "10") or 10)
            with _lead_lock:
                _lead_nocode[:] = [t for t in _lead_nocode if now - t < 86400]
                if len(_lead_nocode) >= cap:
                    if log: log.warning("site lead: daily cap for codeless messages reached")
                    return "nocode_cap"
                _lead_nocode.append(now)
        digits = re.sub(r"\D", "", str(wa_from or ""))
        phone = "0" + digits[-9:]
        agent = (os.environ.get("SITE_LEAD_AGENT") or "אייל שמול").strip()
        aph = str((G["fetch_agents_phones"]() or {}).get(agent, "") or "")
        to9 = G["_last9"](aph)
        push_to = [to9] if to9 else None   # בלי טלפון לסוכן — send_push בלי יעד (ברירת המחדל: הבעלים)
        office = str((cfg.get("v2_office") or {}).get("name", "") or "").strip() or "המשרד"
        nm = re.sub(r"\s+", " ", str(name or "")).strip()[:60]
        first = nm.split()[0] if nm else ""
        with _lead_lock:
            day = [t for t in _lead_day.get(phone, []) if time.time() - t < 86400]
            for k in [k for k, d in _lead_limit_pushed.items() if now - d > 86400]:
                _lead_limit_pushed.pop(k, None)
            for k in [k for k, v in _lead_day.items() if not any(now - t < 86400 for t in v)]:
                _lead_day.pop(k, None)
            if len(day) >= 3:
                if phone not in _lead_limit_pushed:      # פוש אחד ביום לכל טלפון
                    _lead_limit_pushed[phone] = now
                    _push("ליד מהאתר — הגבלה יומית", "%s (%s) ביקש שוב: %s" % (nm or "ליד", phone, q[:60]), push_to)
                return "limit"
            _lead_day[phone] = day + [now]
        try:   # 15/10 (אייל): תשובה מיידית — שהלקוח יחכה בשיחה עד שהדף מגיע
            G["_d360_send_text"](wa_from, lead_ack(first, office))
        except Exception as e:
            if log: log.warning(f"site lead ack: {e}")
        p9 = phone[-9:]
        same = [b for b in (G["_fetch_manual_buyers"]() or []) if re.sub(r"\D", "", str(b.get("phone", "") or ""))[-9:] == p9]
        # קודם ליד קודם מהאתר (גם אם הועבר לסוכן אחר — אותו קונה, אותו דף), אחר כך קונה של סוכן הלידים
        buyer = next((b for b in same if str(b.get("summary", "") or "").startswith("ליד מהאתר")), None) \
            or next((b for b in same if str(b.get("agent", "") or "").strip() == agent), None)
        if buyer and str(buyer.get("agent", "") or "").strip() not in ("", agent):
            agent = str(buyer["agent"]).strip()           # הועבר — ההתראות לסוכן הנוכחי
            aph = str(buyer.get("agent_phone", "") or "") or str((G["fetch_agents_phones"]() or {}).get(agent, "") or "")
            to9 = G["_last9"](aph)
            push_to = [to9] if to9 else None
        if buyer:
            G["_buyers_write"]("updatebuyer", {"row": buyer["row"], "search": q})
            buyer = dict(buyer, search=q)
        else:
            import datetime as _dt
            payload = {"date": _dt.datetime.now().strftime("%d/%m/%Y %H:%M"), "name": nm or "ליד מהאתר", "phone": phone,
                       "budget": "", "summary": "ליד מהאתר" + (" · " + src if src else ""), "agent": agent,
                       "agent_phone": aph, "search": q}
            j = G["_buyers_write"]("addbuyer", payload) or {}
            buyer = dict(payload, row=j.get("row"))
        try:
            G["_cache_clear"]("buyers")
        except Exception:
            pass
        res, keys = None, []
        if buyer.get("row"):
            try:
                keys = app.bpage_lead_pick(q) or []
                res = app.bpage_lead_send(buyer, keys, q) if keys else None
            except Exception as e:
                if log: log.warning(f"site lead page: {e}")
                _push("ליד מהאתר — לא נוצר דף", "%s %s · %s" % (nm, phone, q[:60]), push_to)
                res, keys = None, []
        if res and res.get("n"):
            msg, status = lead_reply(first, office, res["n"], res["url"], not res.get("first")), "sent"
        else:
            msg, status = lead_no_match(first, office), "no_match"
        ok = G["_d360_send_text"](wa_from, msg)
        try:
            G["_log_activity"](agent, "site", "", "ליד מהאתר — סוכן AI אישי", ((nm or phone) + " · " + q)[:60])
        except Exception:
            pass
        if not ok:
            _push("ליד מהאתר — לא נשלח אוטומטית", "%s %s · %s" % (nm, phone, q[:60]), push_to)
            return "send_failed"
        _push("ליד חדש מהאתר", "%s · %s · %s" % (nm or phone, q[:50],
                       ("נשלחו %d נכסים" % res["n"]) if status == "sent" else "אין התאמה — לחזור ללקוח"), push_to)
        return status

    def site_lead_inbound(wa_from, name, text, sync=False, mid=""):
        """נקרא לכל הודעת טקסט נכנסת; רק הפורמט של 'סוכן AI אישי' מטופל (ב-thread — ה-webhook עונה מיד)."""
        if not _leads_on() or parse_lead_message(text) is None:
            return "ignored"
        if sync:
            return _lead_handle(wa_from, name, text, mid)

        def _run():
            try:
                _lead_handle(wa_from, name, text, mid)
            except Exception as e:
                if log: log.error(f"site lead inbound: {e}", exc_info=True)
        threading.Thread(target=_run, daemon=True, name="site-lead").start()
        return "queued"
    app.site_lead_inbound = site_lead_inbound
    try:
        G["_site_lead_inbound"] = site_lead_inbound
    except Exception:
        pass

    @app.route("/site/api/form", methods=["POST"])
    def site_api_form():
        b = request.get_json(silent=True) or {}
        if not _site_key_ok(b):
            return jsonify({"ok": False}), 403
        kind = str(b.get("kind", "") or "")
        if kind not in FORM_KINDS:
            return jsonify({"ok": False, "reason": "kind"}), 400
        raw = b.get("fields") if isinstance(b.get("fields"), dict) else {}
        fields = {str(k)[:20]: str(v or "")[:1500] for k, v in list(raw.items())[:15]}
        try:
            office = ""
            try:
                office = str(((G["_load_config"]() or {}).get("v2_office") or {}).get("name", "") or "")
            except Exception:
                office = ""
            subject, html, text = form_email(kind, fields, office or "המשרד")
            res = G["_report_send_email"](subject, html, text)
            ok = bool(res[0]) if isinstance(res, (tuple, list)) else bool(res)
            G["_log_activity"]("אתר", "site", "", "פנייה מהאתר — " + FORM_KINDS[kind],
                               (fields.get("name", "") + " · " + fields.get("page", "")).strip(" ·"))
            return jsonify({"ok": ok})
        except Exception as e:
            if log: log.warning(f"site form: {e}")
            return jsonify({"ok": False})

    # ---- הסתר / מומלץ באתר (כרטיסי הנכסים באפי) ----
    @app.route("/v2/api/site/state", methods=["GET"])
    def site_state():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        rows = st().all()
        hidden, _ = prop_flags(rows)
        dev = False
        try:
            dev = bool(G["_is_dev"](s.get("phone", ""))) or s.get("drole") == "developer"
        except Exception:
            pass
        return jsonify({"ok": True, "hidden": sorted(hidden), "can_edit": can_edit_prop(s, {}, None, dev),
                        "available": bool(getattr(st(), "available", True))})

    @app.route("/v2/api/site/prop", methods=["POST"])
    def site_prop():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        b = request.get_json(silent=True) or {}
        if "hidden" not in b or "featured" in b:
            return jsonify({"ok": False, "reason": "bad_field"}), 400
        key = str(b.get("key", "") or "").strip()[:80]
        row = next((r for r in (G["fetch_sheet_rows"]() or []) if str(r.get("מספר מודעה", "") or "").strip() == key), None) if key else None
        if not row:
            return jsonify({"ok": False, "reason": "not_found"}), 404
        sess = dict(s)
        try:
            sess["_phones"] = [s.get("phone", "")] + list(G["_phones_for_name"](s.get("name", "")) or [])
        except Exception:
            sess["_phones"] = [s.get("phone", "")]
        is_dev = False
        try:
            is_dev = bool(G["_is_dev"](s.get("phone", ""))) or s.get("drole") == "developer"
        except Exception:
            pass
        if not can_edit_prop(sess, row, G["_agent_owns_row"], is_dev):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        rows = st().all()
        if not getattr(st(), "available", True):
            return jsonify({"ok": False, "reason": "no_table"})
        hidden, _ = prop_flags(rows)
        new_hidden = bool(b.get("hidden"))
        if new_hidden == (key in hidden):
            return jsonify({"ok": True, "hidden": new_hidden})
        if not st().put("prop", key, {"hidden": new_hidden}, s.get("name", "")):
            return jsonify({"ok": False, "reason": "save_failed"})
        where = " ".join(str(row.get(k, "") or "") for k in ("כתובת", "עיר / ישוב")).strip()
        G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                           "אתר — הסתרת נכס" if new_hidden else "אתר — הצגת נכס", (where + " · " + key).strip(" ·"))
        return jsonify({"ok": True, "hidden": new_hidden})

    # ---- מסך "האתר" (מנהל/מפתח) ----
    def _admin():
        s = G["_web_auth"]()
        if not s:
            return None
        dev = False
        try:
            dev = bool(G["_is_dev"](s.get("phone", ""))) or s.get("drole") == "developer"
        except Exception:
            pass
        return s if (dev or s.get("drole") in ("manager", "developer")) else None

    def _agent_names():
        cfg = G["_load_config"]() or {}
        nk = G["_name_key"]
        gone = {nk(n) for n in (cfg.get("removedAgents") or []) + (cfg.get("purgedAgents") or [])}
        out = []
        for a in cfg.get("agents") or []:
            nm = re.sub(r"\s+", " ", str((a or {}).get("name", "") or "")).strip()
            if nm and nk(nm) not in gone and nm not in out:
                out.append(nm)
        return out

    @app.route("/v2/api/site/settings", methods=["GET"])
    def site_settings_get():
        s = _admin()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        rows = st().all()
        page = {r.get("key"): r.get("data") for r in rows if r.get("kind") == "page"}
        agd = {r.get("key"): (r.get("data") or {}) for r in rows if r.get("kind") == "agent"}
        agk = {G["_name_key"](k): v for k, v in agd.items()}
        props = G["fetch_sheet_rows"]() or []
        nk = G["_name_key"]
        cnt = {}
        cities = []
        for r in props:
            if str(r.get("ירד מפרסום", "") or "").strip():
                continue
            k = nk(str(r.get("סוכן 1", "") or ""))
            cnt[k] = cnt.get(k, 0) + 1
            c = re.sub(r"\s+", " ", str(r.get("עיר / ישוב", "") or "")).strip().replace("קריית", "קרית")
            if c == "חיפה" and re.search(r"קרי?ית\s*חיים", str(r.get("שכונה", "") or "")):
                c = "קרית חיים"   # ביד2 קרית חיים היא שכונה של חיפה; באתר יש לה עמוד עיר משלה
            if c and c not in cities:
                cities.append(c)
        names = _agent_names()
        agents = []
        for i, nm in enumerate(names):
            d = agd.get(nm) or agk.get(nk(nm), {})   # רשומה שנשמרה באיות אחר של השם (ייבוא)
            agents.append({"name": nm, "shown": bool(d.get("shown", True)), "order": int(d.get("order", i) or 0),
                           "bio": str(d.get("bio", "") or ""), "count": cnt.get(nk(nm), 0)})
        hidden, _ = prop_flags(rows)
        return jsonify({"ok": True, "pages": page.get("pages") or {}, "branches": page.get("branches") or [],
                        "social": page.get("social") or {}, "agents": agents, "cities": cities,
                        "counts": {"shown": max(0, sum(1 for r in props if not str(r.get("ירד מפרסום", "") or "").strip()) - len(hidden)),
                                   "hidden": len(hidden)},
                        "available": bool(getattr(st(), "available", True)),
                        "site_url": (os.environ.get("SITE_PUBLIC_URL") or "https://refamily.co.il").strip()})

    @app.route("/v2/api/site/settings", methods=["POST"])
    def site_settings_post():
        s = _admin()
        if not s:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        pages, branches, social, agents, errors = clean_settings(b, _agent_names())
        if errors:
            return jsonify({"ok": False, "errors": errors})
        by = s.get("name", "")
        ok = True
        if "pages" in b:
            ok &= st().put("page", "pages", pages, by)
        if "branches" in b:
            ok &= st().put("page", "branches", branches, by)
        if "social" in b:
            ok &= st().put("page", "social", social, by)
        for nm, d in agents.items():
            ok &= st().put("agent", nm, d, by)
        G["_log_activity"](by, s.get("role", ""), s.get("phone", ""), "אתר — עדכון הגדרות",
                           ", ".join(k for k in ("pages", "branches", "social", "agents") if k in b))
        return jsonify({"ok": bool(ok), "errors": {}})

    @app.route("/v2/site", methods=["GET"])
    def v2_site_page():
        from flask import Response
        r = Response(V2_SITE_HTML, mimetype="text/html")
        r.headers["Cache-Control"] = "no-store"
        return r


class SettingsStore:
    """website_settings ב-Supabase (שורה לכל kind+key). טבלה חסרה/כשל → available=False, all()=[]."""

    def __init__(self, sb):
        self.sb = sb
        self.available = True

    def all(self):
        sb = self.sb
        if not (sb and sb.enabled()):
            self.available = False
            return []
        try:
            import requests
            r = requests.get(sb.SUPABASE_URL + "/rest/v1/website_settings", headers=sb._headers(),
                             params={"office_id": "eq." + sb.SB_OFFICE_ID, "select": "kind,key,data"}, timeout=10)
            r.raise_for_status()
            self.available = True
            return r.json() or []
        except Exception:
            self.available = False
            return []

    def put(self, kind, key, data, by):
        sb = self.sb
        if not (sb and sb.enabled()):
            return False
        try:
            import requests
            from datetime import datetime, timezone
            r = requests.post(sb.SUPABASE_URL + "/rest/v1/website_settings?on_conflict=office_id,kind,key",
                              headers={**sb._headers(), "Content-Type": "application/json",
                                       "Prefer": "resolution=merge-duplicates,return=minimal"},
                              json={"office_id": sb.SB_OFFICE_ID, "kind": kind, "key": key, "data": data,
                                    "updated_by": str(by or "")[:80],
                                    "updated_at": datetime.now(timezone.utc).isoformat()}, timeout=10)
            return r.status_code < 300
        except Exception:
            return False


V2_SITE_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>האתר</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;min-height:100vh;color:#1E3A5F;padding-bottom:96px}
  header{padding:calc(env(safe-area-inset-top,0px) + 10px) 18px 6px;display:flex;align-items:center;justify-content:space-between}
  .backBtn{width:44px;height:44px;border-radius:14px;background:#fff;box-shadow:0 2px 8px rgba(30,58,95,.08);display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
  .t{font-size:17px;font-weight:800}
  main{padding:4px 16px 20px;display:flex;flex-direction:column;gap:12px;max-width:680px;margin:0 auto}
  .cc{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:16px;display:flex;flex-direction:column;gap:10px}
  .h{font-size:15px;font-weight:800}.s{font-size:12.5px;color:#5B6472;line-height:1.6}
  .stats{display:flex;gap:8px}.stat{flex:1;background:#F6F4EE;border-radius:14px;padding:10px;text-align:center}
  .stat b{display:block;font-size:20px}.stat span{font-size:11.5px;color:#5B6472;font-weight:600}
  label{font-size:12.5px;font-weight:700;display:block;margin-bottom:4px}
  input,textarea{width:100%;font:400 16px Heebo;border:1.5px solid #DCD6C8;border-radius:12px;padding:10px 12px;color:#1E3A5F;background:#fff;min-height:44px}
  textarea{min-height:84px;resize:vertical}
  .err{color:#A32F2F;font-size:12px;font-weight:600;margin-top:3px}
  .row{display:flex;gap:8px;align-items:center}.row input{flex:1}
  .btn2{min-height:44px;padding:0 14px;border-radius:12px;border:1.5px solid #DCD6C8;background:#fff;color:#1E3A5F;font:700 13px Heebo;cursor:pointer}
  .del{width:44px;height:44px;border-radius:12px;background:#FBEDED;border:0;cursor:pointer;display:flex;align-items:center;justify-content:center;flex:0 0 44px}
  .ag{border-top:1px solid #F0EDE3;padding-top:10px;display:flex;flex-direction:column;gap:8px}
  .ag:first-of-type{border-top:0;padding-top:0}
  .agh{display:flex;align-items:center;gap:8px}.agh .nm{flex:1;font-weight:800;font-size:14px}.agh .nm i{font-style:normal;font-weight:600;color:#5B6472;font-size:12px}
  .mv{width:40px;height:40px;border-radius:10px;border:1.5px solid #DCD6C8;background:#fff;cursor:pointer;font-size:15px;color:#1E3A5F}
  .sw{position:relative;width:52px;height:30px;border-radius:999px;background:#DCD6C8;border:0;cursor:pointer;flex:0 0 52px}
  .sw::after{content:"";position:absolute;top:3px;right:3px;width:24px;height:24px;border-radius:50%;background:#fff;transition:right .2s}
  .sw.on{background:#2E6BD6}.sw.on::after{right:25px}
  .save{position:fixed;left:0;right:0;bottom:0;padding:12px 16px calc(env(safe-area-inset-bottom,0px) + 12px);background:rgba(242,239,231,.96)}
  .save button{width:100%;max-width:680px;display:block;margin:0 auto;min-height:52px;border-radius:16px;border:0;background:#2E6BD6;color:#fff;font:800 16px Heebo;cursor:pointer}
  .link{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:12px;background:#1E3A5F;color:#fff;text-decoration:none;font-weight:700;font-size:14px;align-self:flex-start}
  .empty{text-align:center;padding:30px 16px}
  #toast{position:fixed;bottom:92px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;font-size:13px;font-weight:700;padding:10px 18px;border-radius:999px;opacity:0;transition:opacity .2s;pointer-events:none;z-index:80;white-space:nowrap}
</style></head><body>
<header>
  <button class="backBtn" onclick="location.href='/v2/home'" aria-label="חזרה"><svg width="15" height="15" viewBox="0 0 14 14"><path d="M5 2L10 7l-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
  <div class="t">האתר</div><div style="width:44px"></div>
</header>
<main id="m"><div class="cc empty"><div class="s">טוען…</div></div></main>
<div class="save" id="saveBar" style="display:none"><button onclick="save()">שמירה</button></div>
<div id="toast" role="status" aria-live="polite"></div>
<script>
var TOK = null; try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
if (!TOK) location.replace('/v2');
function el(id){ return document.getElementById(id); }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function toast(m){ var t = el('toast'); t.textContent = m; t.style.opacity = '1'; clearTimeout(t._h); t._h = setTimeout(function(){ t.style.opacity = '0'; }, 2000); }
function api(u, d){ return fetch(u, d ? {method:'POST', headers:{'X-Auth-Token': TOK, 'Content-Type':'application/json'}, body: JSON.stringify(d)} : {headers:{'X-Auth-Token': TOK}})
  .then(function(r){ if (r.status === 403) return {forbidden: true}; return r.json(); }); }
var D = null, ERR = {};
function load(){
  api('/v2/api/site/settings').then(function(j){
    if (j.forbidden){ el('m').innerHTML = '<div class="cc empty"><div class="h">המסך זמין למנהלי המשרד בלבד</div><button class="btn2" style="margin-top:12px" onclick="location.href=\'/v2/home\'">חזרה לבית</button></div>'; return; }
    if (!j.ok){ el('m').innerHTML = '<div class="cc empty"><div class="s">לא נטען — נסה שוב</div></div>'; return; }
    D = j; D.agents.sort(function(a, b){ return a.order - b.order; }); render();
  }).catch(function(){ el('m').innerHTML = '<div class="cc empty"><div class="s">אין חיבור — נסה שוב</div></div>'; });
}
function fld(id, label, val, ta, max){
  return '<div><label for="' + id + '">' + esc(label) + '</label>' + (ta ? '<textarea id="' + id + '" maxlength="' + max + '">' + esc(val) + '</textarea>'
    : '<input id="' + id + '" value="' + esc(val) + '" maxlength="' + max + '">') + (ERR[id] ? '<div class="err">' + esc(ERR[id]) + '</div>' : '') + '</div>';
}
function render(){
  var h = '';
  if (!D.available) h += '<div class="cc"><div class="h">ההגדרות עוד לא פעילות</div><div class="s">צריך להריץ את קובץ ה-SQL של website_settings ב-Supabase. עד אז האתר עובד עם ברירות המחדל.</div></div>';
  h += '<div class="cc"><div class="h">האתר</div><div class="stats">' +
    '<div class="stat"><b>' + D.counts.shown + '</b><span>נכסים מוצגים</span></div>' +
    '<div class="stat"><b>' + D.counts.hidden + '</b><span>מוסתרים</span></div>' +
    '</div><div class="s">הסתרה מהאתר — מכרטיס הנכס במסך הנכסים (מזכירה). המומלצים באתר = הנכסים החמים מהסטורי.</div>' +
    '<a class="link" href="' + esc(D.site_url) + '" target="_blank" rel="noopener">צפה באתר</a></div>';
  var P = D.pages || {};
  h += '<div class="cc"><div class="h">טקסטים</div>' + fld('p_hero', 'תת-כותרת בפתיחה', P.hero_sub || '', true, 220) +
    fld('p_appr', 'הגישה שלנו', P.approach || '', true, 600);
  (D.cities || []).forEach(function(c, i){ h += fld('p_city' + i, 'תיאור ' + c, P['city:' + c] || '', true, 600); });
  h += '</div>';
  h += '<div class="cc"><div class="h">סניפים</div><div class="s">מופיעים בפתיחה ובתחתית האתר.</div><div id="brs">';
  (D.branches.length ? D.branches : [{name:'', phone:''}]).forEach(function(b, i){
    h += '<div class="row"><input aria-label="שם הסניף" class="bn" value="' + esc(b.name) + '" placeholder="שם הסניף" maxlength="30">' +
      '<input aria-label="טלפון" class="bp" value="' + esc(b.phone) + '" placeholder="טלפון" inputmode="tel" maxlength="20">' +
      '<button class="del" aria-label="הסרת סניף" onclick="rmBranch(' + i + ')"><svg width="15" height="15" viewBox="0 0 16 16"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.6a1 1 0 0 0 1 .9h3.6a1 1 0 0 0 1-.9l.7-8.6" fill="none" stroke="#C24040" stroke-width="1.4" stroke-linecap="round"/></svg></button></div>';
  });
  h += '</div>' + (ERR.branches ? '<div class="err">' + esc(ERR.branches) + '</div>' : '') + '<button class="btn2" onclick="addBranch()">+ הוספת סניף</button></div>';
  var S = D.social || {};
  h += '<div class="cc"><div class="h">רשתות חברתיות</div>' + fld('facebook', 'פייסבוק', S.facebook || '', false, 200) +
    fld('instagram', 'אינסטגרם', S.instagram || '', false, 200) + fld('youtube', 'יוטיוב', S.youtube || '', false, 200) + '</div>';
  h += '<div class="cc"><div class="h">הצוות באתר</div><div class="s">מי מופיע בעמוד הצוות ובדף הבית, באיזה סדר, ותיאור הסוכן לעמוד שלו באתר.</div>';
  D.agents.forEach(function(a, i){
    h += '<div class="ag"><div class="agh"><div class="nm">' + esc(a.name) + ' <i>' + (a.count ? a.count + ' נכסים' : 'בלי נכסים') + '</i></div>' +
      '<button class="mv" aria-label="למעלה" onclick="mv(' + i + ',-1)">▲</button><button class="mv" aria-label="למטה" onclick="mv(' + i + ',1)">▼</button>' +
      '<button class="sw' + (a.shown ? ' on' : '') + '" role="switch" aria-checked="' + a.shown + '" aria-label="מופיע באתר" onclick="tg(' + i + ')"></button></div>' +
      '<textarea aria-label="תיאור הסוכן" class="bio" data-i="' + i + '" rows="3" placeholder="תיאור הסוכן (רשות) — מופיע בעמוד הסוכן באתר" maxlength="1500">' + esc(a.bio) + '</textarea></div>';
  });
  h += '</div>';
  el('m').innerHTML = h; el('saveBar').style.display = 'block';
}
function grab(){
  var P = {}; P.hero_sub = el('p_hero').value; P.approach = el('p_appr').value;
  (D.cities || []).forEach(function(c, i){ P['city:' + c] = el('p_city' + i).value; });
  D.pages = P;
  var bn = document.querySelectorAll('.bn'), bp = document.querySelectorAll('.bp'), br = [];
  for (var i = 0; i < bn.length; i++) if (bn[i].value.trim() || bp[i].value.trim()) br.push({name: bn[i].value, phone: bp[i].value});
  D.branches = br;
  D.social = {facebook: el('facebook').value.trim(), instagram: el('instagram').value.trim(), youtube: el('youtube').value.trim()};
  document.querySelectorAll('.bio').forEach(function(x){ D.agents[+x.getAttribute('data-i')].bio = x.value; });
}
function addBranch(){ grab(); if (D.branches.length >= 5){ toast('עד 5 סניפים'); return; } D.branches.push({name:'', phone:''}); render(); }
function rmBranch(i){ grab(); D.branches.splice(i, 1); render(); }
function mv(i, d){ grab(); var j = i + d; if (j < 0 || j >= D.agents.length) return; var t = D.agents[i]; D.agents[i] = D.agents[j]; D.agents[j] = t; render(); }
function tg(i){ grab(); D.agents[i].shown = !D.agents[i].shown; render(); }
function save(){
  grab(); var ag = {};
  D.agents.forEach(function(a, i){ ag[a.name] = {shown: a.shown, order: i, bio: a.bio}; });
  api('/v2/api/site/settings', {pages: D.pages, branches: D.branches, social: D.social, agents: ag}).then(function(j){
    if (j.forbidden){ toast('אין הרשאה'); return; }
    ERR = {};
    if (j.errors){ for (var k in j.errors) ERR[k === 'branches' ? 'branches' : k] = j.errors[k]; }
    if (j.ok){ toast('נשמר — באתר תוך דקה'); render(); } else { render(); toast('יש שדות לתקן'); }
  }).catch(function(){ toast('לא נשמר — נסה שוב'); });
}
load();
</script></body></html>'''
