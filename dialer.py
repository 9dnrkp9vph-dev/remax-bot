# dialer.py — [DIALER 03/11] חייגן חכם למתאמות (אייל: 'תבנה את זה באפי אבל רק למתאמות כרגע').
# תור של בעלי נכס נולד לפי סיכוי לפגישה, תסריט אישי, חיוג מהקו של המשרד (c2cDial), תיעוד תוצאה,
# קביעת פגישה ליומן של הסוכן דרך /api/newborn/status הקיים (נספרת ביעדים ובתחרות), פוש לסוכן,
# ואישור לבעל הנכס בוואטסאפ מהטלפון של המתאמת. הלוגיקה הטהורה למעלה (נבדקת), הראוטים ב-register.
import datetime as _dt
import re as _re
import threading as _threading
import time as _time

from goals import _IL

WINDOW_DAYS = 14          # רק מודעות מ-14 הימים האחרונים
CLAIM_SEC = 20 * 60       # מתאמת שחייגה 'תופסת' את הנכס ל-20 דק' — שלא יחייגו אליו פעמיים
BUYER_MIN = 60            # סף 'קונה מתאים' (bai_score)
GOAL_DEFAULT = 5          # יעד פגישות יומי במסך
HEB_DAYS = ["ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "שבת", "א׳"]   # weekday(): 0=שני


def _norm(t):
    return _re.sub(r"\s+", " ", str(t or "").replace("קריית", "קרית")).strip()


def area_eq(a, b):
    """שכונה/עיר זהות: אחרי נרמול — שוויון, או הכלה (≥3 תווים): 'נאות אפק' ⊂ 'נאות אפק, אפקה'."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    return (len(a) >= 3 and a in b) or (len(b) >= 3 and b in a)


def age_label(created, now):
    m = max(0, int((now - created) / 60))
    if m < 60:
        return "פורסם לפני %d דק׳" % max(1, m)
    h = m // 60
    if h < 24:
        return "פורסם לפני שעה" if h == 1 else "פורסם לפני %d שעות" % h
    d = h // 24
    return "פורסם אתמול" if d == 1 else "פורסם לפני %d ימים" % d


def lead_score(age_days, dropped, contacted, buyers_n, has_owner):
    """(ציון 3-97, סיבות[(סוג, טקסט)]) — סוג: g=זהב (קונים), gr=ירוק (מחיר), ''=אפור."""
    sc, why = 0, []
    sc += 34 if age_days <= 0 else 26 if age_days == 1 else 20 if age_days == 2 else 12 if age_days <= 5 else 5
    if buyers_n:
        sc += min(26, 6 + 4 * (buyers_n - 1))
        why.append(("g", "קונה מתאים במשרד" if buyers_n == 1 else "%d קונים מתאימים במשרד" % buyers_n))
    if dropped:
        sc += 14
        why.append(("gr", "ירידת מחיר"))
    if contacted:
        sc -= 8
        why.append(("", "כבר פנו: " + ", ".join(contacted[:2])))
    else:
        sc += 16
        why.append(("", "אף סוכן לא פנה"))
    if has_owner:
        sc += 3
    return max(3, min(97, sc)), why


def _at(day, hh, mm):
    return _dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=_IL)


def _day_word(d, today):
    if d == today:
        return "היום"
    if d == today + _dt.timedelta(days=1):
        return "מחר"
    return "יום " + HEB_DAYS[d.weekday()]


def free_slots(now_dt, busy, n=5):
    """מועדים פנויים לפגישה: 4 ימים קדימה, בלי שבת; שישי 10:00/12:00; שאר הימים 10:00/12:00/17:00/18:30.
    לפחות 90 דק' מעכשיו, ולא בתוך 75 דק' מפגישה קיימת של הסוכן (busy = datetimes עם אזור זמן)."""
    out = []
    today = now_dt.date()
    for k in range(5):
        d = today + _dt.timedelta(days=k)
        wd = d.weekday()
        if wd == 5:
            continue
        hours = [(10, 0), (12, 0)] if wd == 4 else [(10, 0), (12, 0), (17, 0), (18, 30)]
        for hh, mm in hours:
            t = _at(d, hh, mm)
            if t < now_dt + _dt.timedelta(minutes=90):
                continue
            if any(abs((t - b).total_seconds()) < 75 * 60 for b in busy or []):
                continue
            out.append({"iso": t.strftime("%Y-%m-%dT%H:%M"), "label": "%s %02d:%02d" % (_day_word(d, today), hh, mm)})
            if len(out) >= n:
                return out
    return out


def next_retry(now_dt, kind):
    """'לא ענה' — היום 17:30 (השעה שבה בעלי נכסים עונים), אחרת יום העבודה הבא 10:30.
    'לחזור אליו' בלי מועד — מחר 10:00. שישי אחרי 11:00 → ראשון."""
    if kind == "na" and now_dt.weekday() not in (4, 5) and now_dt < _at(now_dt.date(), 17, 0):
        return _at(now_dt.date(), 17, 30)
    if kind == "na" and now_dt.weekday() == 4 and now_dt < _at(now_dt.date(), 11, 0):
        return _at(now_dt.date(), 12, 0)
    d = now_dt.date() + _dt.timedelta(days=1)
    while d.weekday() == 5:
        d += _dt.timedelta(days=1)
    return _at(d, 10, 30 if kind == "na" else 0)


def agent_counts(rows, canon):
    """נכסי המשרד הפעילים לפי סוכן: (nb_rows[(שכונה, סוכן)], city[(עיר, סוכן)], תצוגה{canon: שם})."""
    nbc, cic, disp = {}, {}, {}
    for r in rows or []:
        if str(r.get("סטטוס", "") or "").strip() not in ("", "פעילה"):
            continue
        if str(r.get("ירד מפרסום", "") or r.get("delisted_at", "") or "").strip():
            continue
        nm = str(r.get("סוכן 1", "") or "").strip()
        k = canon(nm)
        if not k:
            continue
        disp.setdefault(k, nm)
        nb, city = _norm(r.get("שכונה", "")), _norm(r.get("עיר / ישוב", "") or r.get("עיר", ""))
        if nb:
            nbc[(nb, k)] = nbc.get((nb, k), 0) + 1
        if city:
            cic[(city, k)] = cic.get((city, k), 0) + 1
    return nbc, cic, disp


def rank_agents(city, nb, counts, team, roster, canon, top=3):
    """הסוכן שיגיע: 3 לכל נכס שלו באותה שכונה + 1 לכל נכס באותה עיר + 2 אם מהצוות של המתאמת.
    team/roster = שמות; מחזיר [{name, why, mine}] — המומלץ ראשון."""
    nbc, cic, disp = counts
    cands = {}
    for nm in list(team or []) + list(roster or []):
        k = canon(nm)
        if k and k not in cands:
            cands[k] = nm
    team_k = {canon(n) for n in team or []}
    scored = []
    for k, nm in cands.items():
        n_nb = sum(v for (a, kk), v in nbc.items() if kk == k and nb and area_eq(a, nb))
        n_ci = sum(v for (a, kk), v in cic.items() if kk == k and city and area_eq(a, city))
        sc = 3 * n_nb + n_ci + (2 if k in team_k else 0)
        if n_nb:
            why = "%d נכסים שלו ב%s" % (n_nb, _norm(nb).split(",")[0]) if n_nb > 1 else "נכס שלו ב%s" % _norm(nb).split(",")[0]
        elif n_ci:
            why = "%d נכסים שלו ב%s" % (n_ci, _norm(city)) if n_ci > 1 else "נכס שלו ב%s" % _norm(city)
        else:
            why = "מהצוות שלך" if k in team_k else ""
        scored.append((sc, k in team_k, nm, why))
    scored.sort(key=lambda x: (-x[0], not x[1], x[2]))
    return [{"name": nm, "why": why, "mine": mine} for sc, mine, nm, why in scored[:top] if sc > 0 or mine]


def build_state(st, now):
    """גיזום מצב המתאמת: לידים מעל 30 יום וימים מעל 14 נמחקים."""
    st = dict(st or {})
    leads = {k: v for k, v in (st.get("leads") or {}).items() if isinstance(v, dict) and now - (v.get("t") or 0) < 30 * 86400}
    cutoff = _dt.datetime.fromtimestamp(now - 14 * 86400, _IL).strftime("%Y-%m-%d")
    days = {k: v for k, v in (st.get("days") or {}).items() if k >= cutoff}
    return {"leads": leads, "days": days}


def queue_split(cands, my_leads, global_out, claims, me9, now):
    """cands = לידים מוכנים (עם key, score). מחזיר (ready, later): later = 'לא ענה'/'לחזור' שעוד לא הגיע זמנם.
    יוצאים מהתור: פגישה/לא מעוניין (של כל מתאמת), ולידים שמתאמת אחרת חייגה אליהם ב-20 הדק' האחרונות."""
    ready, later = [], []
    for c in cands:
        k = c["key"]
        if k in global_out:
            continue
        cl = claims.get(k)
        if cl and cl.get("by9") != me9 and now - (cl.get("t") or 0) < CLAIM_SEC:
            continue
        s = my_leads.get(k)
        if s and s.get("o") in ("meet", "no"):
            continue
        if s and s.get("o") in ("na", "back") and (s.get("r") or 0) > now:
            later.append(dict(c, retry=s.get("r"), outcome=s.get("o")))
            continue
        if s and s.get("o") == "na":
            c = dict(c, tries=s.get("n", 1))
        ready.append(c)
    ready.sort(key=lambda c: -c["score"])
    later.sort(key=lambda c: c["retry"])
    return ready, later


# ── שרת ────────────────────────────────────────────────────────────────────
_CACHE = {"t": 0, "v": None}
_CLOCK = _threading.Lock()


def register(app, G):
    from flask import jsonify, request
    import effie_v2 as _ev
    import goals as _goals

    log = G.get("log")

    def canon(n):
        n = str(n or "").strip()
        try:
            n = G["_canon_agent_name"](n) or n
        except Exception:
            pass
        return G["_canon_key"](n)

    def _real(s):   # מתאמות נכנסות בשם הגנרי 'מנהל' — השם האמיתי לפי הטלפון
        try:
            return G["_display_name_for"](s.get("name") or "", s.get("phone") or "") or s.get("name") or ""
        except Exception:
            return s.get("name") or ""

    def _coord_rec(s):
        try:
            return (G["_coordinators_all"]() or {}).get(G["_last9"](s.get("phone", "")))
        except Exception:
            return None

    def allowed(s):
        """רק מתאמות (ובעל המשרד — לבדיקה). מתאמות רשומות בניהול כמנהלות, ולכן מזוהות לפי הטלפון/השם."""
        if not s:
            return False
        if s.get("dev"):
            return True
        if s.get("role") == "coordinator" or s.get("drole") == "coordinator":
            return True
        if _coord_rec(s):
            return True
        k = canon(_real(s))
        try:
            for it in (G["_load_config"]().get("coordinators") or []):
                if isinstance(it, dict) and k and k in (canon(it.get("coordinator")), canon(it.get("name"))):
                    return True
        except Exception:
            pass
        return False

    def _team(s):
        rec = _coord_rec(s) or {}
        names = set()
        for ph in rec.get("agents") or set():
            nm = (G["web_phone_name_map"]() or {}).get(G["_last9"](ph)) or (G["web_contacts_phone_name"]() or {}).get(G["_last9"](ph))
            if nm:
                names.add(nm)
        return sorted(names)

    def _roster():
        try:
            r = [n for n in (_goals.g_roster(G) or []) if n]
        except Exception:
            r = []
        return r or list((G["fetch_agents_phones"]() or {}).keys())

    def _buyers_prep():
        try:
            stat = G["_bstat_current"]() if "_bstat_current" in G else {}
        except Exception:
            stat = {}
        out = []
        for r in (G["_fetch_manual_buyers"]() or []):
            try:
                st = _ev.bstat_of(r, stat, G["_bcanon"]) if "_bcanon" in G else None
            except Exception:
                st = None
            if st in ("closed", "frozen"):
                continue
            text = " ".join(str(r.get(k, "") or "") for k in ("search", "summary"))
            rb = _ev.bai_budget(r.get("budget", "")) or _ev.bai_budget(r.get("search", ""))
            out.append((text, rb))
        return out

    def _build():
        """המועמדים לתור — משותף לכל המתאמות, מטמון 3 דק'."""
        now = _time.time()
        rows = G["fetch_newborn"]() or []
        cfg = G["_load_config"]()
        taken = set()   # פגישה/לא מעוניין שכבר נרשמו על הנכס (של כל אחד)
        for v in (cfg.get("nbStatus") or {}).values():
            if isinstance(v, dict) and v.get("status") in ("meeting", "not_interested") and v.get("pkey"):
                taken.add(v.get("pkey"))
        pd_map = G["_price_dropped_map"]() or {}
        ctx = {"contacts": G["_fetch_newborn_contacts"]() or {}, "statuses": {}, "fam_list": G["_famexcl_addr_list"](),
               "pd_map": pd_map, "eff_name": "", "phone9": "", "notes_admin": False}
        try:
            idx = G["_nb_alias_idx"]()
        except Exception:
            idx = None
        buyers = _buyers_prep()
        out = []
        for r in rows:
            c = G["_newborn_created_epoch"](r)
            if not c or (now - c) / 86400 > WINDOW_DAYS:
                continue
            k = G["_nb_key"](r)
            if k in taken:
                continue
            if G["_nb_clean"](r.get("delisted_at", "")):
                continue
            office = G["_nb_as_office_row"](r)
            ad = int((now - c) / 86400)
            dropped = G["_nb_price_key"](r) in pd_map
            try:
                o = G["_nb_row_out"](r, ad, office["עיר / ישוב"], office["כתובת"],
                                     G["_nb_clean"](r.get("שם בעל הנכס", "")),
                                     G["_nb_clean"](r.get("משתמש", "") or r.get("סוכן 1", "")), dropped, ctx)
            except Exception as e:
                if log: log.warning(f"dialer: row skipped ({k}): {e}")
                continue
            tel = _re.sub(r"\D", "", str(o.get("phone") or ""))
            if not tel or o.get("famexcl") or o.get("rent"):
                continue
            price_n = _ev.bai_budget(office["מחיר"])
            rooms = None
            try:
                rooms = float(office["חדרים"]) if office["חדרים"] else None
            except Exception:
                rooms = None
            parsed = {"city": office["עיר / ישוב"], "neighborhood": office["שכונה"], "budget_max": price_n,
                      "rooms_min": rooms, "rooms_max": rooms, "property_type": office["סוג נכס"],
                      "_qtext": office["סוג נכס"]}
            try:
                area = _ev.bai_area_terms(parsed, idx) if idx else None
            except Exception:
                area = None
            nb_buy = 0
            for text, rb in buyers:
                try:
                    if _ev.bai_score(parsed, text, rb, False, area)[0] >= BUYER_MIN:
                        nb_buy += 1
                except Exception:
                    continue
            sc, why = lead_score(ad, dropped, o.get("contacted") or [], nb_buy, bool(o.get("owner")))
            feats = o.get("feats") or []
            if feats:
                why.append(("b", " · ".join(str(f) for f in feats[:3])))
            out.append({"key": k, "address": o.get("address") or "", "city": o.get("city") or "",
                        "nb": office["שכונה"], "rooms": office["חדרים"], "sqm": office['מ"ר'], "floor": office["קומה"],
                        "ptype": office["סוג נכס"], "price": o.get("price") or "", "priceOld": o.get("priceOld") or "",
                        "owner": o.get("owner") or "", "phone": o.get("phone") or "", "tel": tel, "wa": o.get("wa") or "",
                        "link": o.get("link") or "", "desc": (o.get("desc") or "")[:240],
                        "age": age_label(c, now), "ageDays": ad, "buyers": nb_buy, "contacted": o.get("contacted") or [],
                        "score": sc, "why": [{"k": a, "t": b} for a, b in why]})
        return out

    def _cands():
        now = _time.time()
        if _CACHE["v"] is not None and now - _CACHE["t"] < 180:
            return _CACHE["v"]
        with _CLOCK:
            if _CACHE["v"] is not None and _time.time() - _CACHE["t"] < 180:
                return _CACHE["v"]
            v = _build()
            if v:
                _CACHE.update(t=_time.time(), v=v)
            return v

    def _st_all(cfg):
        d = cfg.get("v2_dialer")
        return d if isinstance(d, dict) else {}

    def _today_key(now):
        return _dt.datetime.fromtimestamp(now, _IL).strftime("%Y-%m-%d")

    def _meetings_today(cfg, me9, now):
        s, e = _goals.day_bounds(_dt.datetime.fromtimestamp(now, _IL).date())
        n = 0
        for v in (cfg.get("nbStatus") or {}).values():
            if isinstance(v, dict) and v.get("status") == "meeting" and v.get("by_phone") == me9:
                ma = v.get("meeting_at")
                if isinstance(ma, (int, float)) and s <= ma < e:
                    n += 1
        return n

    def _busy(cfg, agent):
        k = canon(agent)
        out = []
        for v in (cfg.get("nbStatus") or {}).values():
            if not isinstance(v, dict) or v.get("status") != "meeting" or canon(v.get("agent")) != k:
                continue
            t = _goals.parse_ts(v.get("date"))
            if t:
                out.append(_dt.datetime.fromtimestamp(t, _IL))
        return out

    def _deny():
        return jsonify({"ok": True, "allowed": False})

    @app.route("/v2/api/dialer/access", methods=["GET"])
    def dialer_access():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        return jsonify({"ok": True, "allowed": allowed(s)})

    @app.route("/v2/api/dialer/queue", methods=["GET"])
    def dialer_queue():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        if not allowed(s):
            return _deny()
        try:
            now = _time.time()
            me9 = G["_last9"](s.get("phone", ""))
            cfg = G["_load_config"]()
            allst = _st_all(cfg)
            mine = build_state(allst.get(me9), now)
            gl = allst.get("_global") or {}
            ready, later = queue_split(_cands(), mine["leads"], gl.get("out") or {}, gl.get("claims") or {}, me9, now)
            team, roster = _team(s), _roster()
            counts = agent_counts(G["fetch_sheet_rows"]() or [], canon)
            for c in ready[:40]:
                c["agents"] = rank_agents(c["city"], c["nb"], counts, team, roster, canon)
            name = _real(s)
            day = mine["days"].get(_today_key(now)) or {}
            try:
                office = ((cfg.get("v2_office") or {}).get("name") or "").strip() or G["_office_name"]()
            except Exception:
                office = ((cfg.get("v2_office") or {}).get("name") or "").strip()
            agents_all = team + [n for n in sorted(roster) if canon(n) not in {canon(t) for t in team}]
            return jsonify({"ok": True, "allowed": True, "me": name, "office": office,
                            "stats": {"calls": int(day.get("calls") or 0), "meetings": _meetings_today(cfg, me9, now),
                                      "goal": GOAL_DEFAULT},
                            "items": ready[:40], "more": max(0, len(ready) - 40),
                            "later": [{"key": c["key"], "address": c["address"], "city": c["city"], "owner": c["owner"],
                                       "retry": c["retry"], "outcome": c["outcome"],
                                       "at": _dt.datetime.fromtimestamp(c["retry"], _IL).strftime("%d/%m %H:%M")}
                                      for c in later[:20]],
                            "agents": [{"name": n, "mine": canon(n) in {canon(t) for t in team}} for n in agents_all]})
        except Exception as e:
            if log: log.error(f"dialer queue error: {e}", exc_info=True)
            return jsonify({"ok": False, "reason": str(e)[:160]}), 500

    @app.route("/v2/api/dialer/slots", methods=["GET"])
    def dialer_slots():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        if not allowed(s):
            return _deny()
        agent = (request.args.get("agent") or "").strip()
        now_dt = _dt.datetime.fromtimestamp(_time.time(), _IL)
        return jsonify({"ok": True, "slots": free_slots(now_dt, _busy(G["_load_config"](), agent)) if agent else []})

    def _mutate(me9, fn):
        def m(cfg):
            allst = cfg.get("v2_dialer")
            if not isinstance(allst, dict):
                allst = {}
            now = _time.time()
            allst[me9] = build_state(allst.get(me9), now)
            gl = allst.get("_global")
            if not isinstance(gl, dict):
                gl = {}
            gl["out"] = {k: v for k, v in (gl.get("out") or {}).items() if now - (v.get("t") or 0) < 30 * 86400}
            gl["claims"] = {k: v for k, v in (gl.get("claims") or {}).items() if now - (v.get("t") or 0) < CLAIM_SEC}
            allst["_global"] = gl
            fn(allst[me9], gl, now)
            cfg["v2_dialer"] = allst
        return G["_config_mutate"](m)

    @app.route("/v2/api/dialer/dial", methods=["POST"])
    def dialer_dial():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        if not allowed(s):
            return _deny()
        d = request.get_json(silent=True) or {}
        key = str(d.get("key") or "").strip()[:200]
        if not key:
            return jsonify({"ok": False, "reason": "bad_input"}), 400
        me9, name = G["_last9"](s.get("phone", "")), _real(s)

        def fn(mine, gl, now):
            dk = _today_key(now)
            day = mine["days"].get(dk) or {}
            day["calls"] = int(day.get("calls") or 0) + 1
            mine["days"][dk] = day
            gl["claims"][key] = {"by9": me9, "by": name, "t": now}
        ok, _ = _mutate(me9, fn)
        try:
            G["_log_activity"](name, s.get("role", ""), s.get("phone", ""), "חייגן חכם — חיוג",
                               str(d.get("addr") or key)[:80])
        except Exception:
            pass
        return jsonify({"ok": bool(ok)})

    @app.route("/v2/api/dialer/outcome", methods=["POST"])
    def dialer_outcome():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        if not allowed(s):
            return _deny()
        d = request.get_json(silent=True) or {}
        key = str(d.get("key") or "").strip()[:200]
        o = str(d.get("outcome") or "").strip()
        if not key or o not in ("na", "back", "no", "meet"):
            return jsonify({"ok": False, "reason": "bad_input"}), 400
        me9, name = G["_last9"](s.get("phone", "")), _real(s)
        now_dt = _dt.datetime.fromtimestamp(_time.time(), _IL)
        retry = None
        if o in ("na", "back"):
            rt = _goals.parse_ts(d.get("retry")) if d.get("retry") else None
            retry = rt if rt and rt > _time.time() else next_retry(now_dt, o).timestamp()

        def fn(mine, gl, now):
            prev = mine["leads"].get(key) or {}
            rec = {"o": o, "t": now}
            if retry:
                rec["r"] = retry
            if o == "na":
                rec["n"] = int(prev.get("n") or 0) + 1
            mine["leads"][key] = rec
            if o in ("no", "meet"):
                gl["out"][key] = {"o": o, "by": name, "t": now}
            gl["claims"].pop(key, None)
        ok, _ = _mutate(me9, fn)
        addr = str(d.get("addr") or key)[:80]
        lbl = {"na": "לא ענה", "back": "לחזור אליו", "no": "לא מעוניין", "meet": "נקבעה פגישה"}[o]
        try:
            G["_log_activity"](name, s.get("role", ""), s.get("phone", ""), "חייגן חכם — " + lbl, addr)
        except Exception:
            pass
        pushed = False
        if o == "meet":   # פוש לסוכן שיגיע (הפגישה עצמה כבר נשמרה ב-/api/newborn/status)
            agent = str(d.get("agent") or "").strip()
            when = str(d.get("when") or "").strip()[:40]
            ids = [G["_last9"](p) for p in (G["_phones_for_name"](agent) or []) if G["_last9"](p)]
            if ids:
                body = "%s · %s%s" % (addr, when, (" · " + str(d.get("owner") or "")[:30]) if d.get("owner") else "")
                _threading.Thread(target=G["send_push"], args=("פגישה חדשה מ" + (name.split()[0] if name else "המתאמת"), body, ids),
                                  daemon=True).start()
                pushed = True
        _CACHE["t"] = 0 if o in ("no", "meet") else _CACHE["t"]
        return jsonify({"ok": bool(ok), "retry": retry, "pushed": pushed,
                        "retryAt": _dt.datetime.fromtimestamp(retry, _IL).strftime("%H:%M") if retry else ""})


V2_DIALER_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>חייגן חכם</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--cream:#F2EFE7;--navy:#1E3A5F;--navy0:#0E1D33;--navy2:#2C4C77;--blue:#2E6BD6;--gold:#C29435;--gold2:#E4C56B;--goldtxt:#7A5E1C;
  --green:#157A43;--ink:#14192B;--mut:#5B6472;--mut2:#6B7280;--line:#E6E1D6;--shadow:0 6px 20px rgba(30,58,95,.06)}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:'Heebo',sans-serif;background:var(--cream);color:var(--ink);min-height:100vh;min-height:100dvh}
button{font-family:inherit;cursor:pointer;border:0}
.wrap{max-width:1120px;margin:0 auto;padding:0 0 calc(env(safe-area-inset-bottom,0px) + 30px)}
.hero{background:linear-gradient(160deg,var(--navy0),var(--navy2));color:#fff;padding:calc(env(safe-area-inset-top,0px) + 12px) 16px 16px;border-radius:0 0 26px 26px}
.hero .top{display:flex;align-items:center;gap:10px}
.back{width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;flex:none}
.hero h1{font-size:21px;font-weight:800}
.hero .sub{font-size:12.5px;opacity:.78}
.ai{background:linear-gradient(135deg,var(--gold),var(--gold2));color:#231700;font-size:10.5px;font-weight:800;border-radius:99px;padding:2px 8px;margin-inline-start:6px;vertical-align:middle}
.kpis{display:flex;gap:8px;margin-top:12px}
.kpi{flex:1;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:8px 6px;text-align:center}
.kpi b{display:block;font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}
.kpi span{font-size:11px;opacity:.8}
.kpi.ring{display:flex;align-items:center;gap:8px;justify-content:center;flex:1.4}
.ringw{width:46px;height:46px;position:relative;flex:none}
.ringw svg{transform:rotate(-90deg)}
.ringw .n{position:absolute;inset:0;display:grid;place-items:center;font-weight:800;font-size:15px}
.grid{display:grid;grid-template-columns:320px 1fr;gap:14px;padding:14px 14px 0;align-items:start}
@media(max-width:880px){.grid{grid-template-columns:1fr}.side{order:2}}
.card{background:#fff;border-radius:22px;box-shadow:var(--shadow);padding:16px}
.h{font-size:14px;font-weight:800;color:var(--navy);margin-bottom:10px;display:flex;align-items:center;gap:8px}
.h .c{margin-inline-start:auto;font-size:12px;font-weight:600;color:var(--mut2)}
.qi{display:flex;gap:10px;align-items:center;padding:9px;border-radius:16px;border:1px solid var(--line);background:#FBFAF6;margin-bottom:7px;cursor:pointer;min-height:56px;width:100%;text-align:start}
.qi.cur{border-color:var(--blue);background:#EEF4FE}
.sc{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;font-weight:800;font-size:13px;flex:none}
.sc.hi{background:#FBF3DF;color:var(--goldtxt)}.sc.md{background:#EEF4FE;color:var(--blue)}.sc.lo{background:#F1F1EF;color:var(--mut)}
.qi .t{font-weight:700;font-size:14px;color:var(--ink)}
.qi .s{font-size:12px;color:var(--mut2)}
.qi .tag{margin-inline-start:auto;font-size:11px;font-weight:700;padding:3px 8px;border-radius:99px;background:#FBF3DF;color:var(--goldtxt);white-space:nowrap}
.sub2{font-size:12px;font-weight:800;color:var(--mut);margin:12px 2px 6px}
.insight{margin-top:12px;background:#FBF3DF;border-radius:16px;padding:11px 13px;font-size:12.5px;color:#4A3A12;line-height:1.55}
.insight b{color:var(--goldtxt)}
.lead{display:grid;grid-template-columns:1fr;gap:6px}
.fresh{display:inline-block;background:#EEF4FE;color:var(--blue);font-size:12px;font-weight:800;border-radius:99px;padding:3px 10px;margin-bottom:6px}
.addr{font-size:23px;font-weight:800;color:var(--navy)}
.meta{color:var(--mut);font-size:14px}
.price{font-size:21px;font-weight:800;margin-top:4px}
.price s{font-size:14px;color:var(--mut2);font-weight:500;margin-inline-start:6px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:12px;font-weight:700;padding:5px 10px;border-radius:99px;background:#F1F1EF;color:var(--mut)}
.chip.g{background:#FBF3DF;color:var(--goldtxt)}.chip.b{background:#EEF4FE;color:var(--blue)}.chip.gr{background:#E6F4EC;color:var(--green)}
.scorebar{display:flex;align-items:center;gap:10px;margin-top:10px;font-size:13px;color:var(--mut)}
.scorebar .bar{flex:1;height:8px;border-radius:9px;background:#EEE9DD;overflow:hidden}
.scorebar .bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--gold2),var(--gold));border-radius:9px;transition:width .6s}
.scorebar b{color:var(--goldtxt);font-size:15px}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
@media(max-width:560px){.duo{grid-template-columns:1fr}}
.mini{border:1px solid var(--line);border-radius:18px;padding:11px 13px}
.mini .l{font-size:11.5px;color:var(--mut2);font-weight:700;display:flex;align-items:center;gap:6px}
.mini .v{font-size:16px;font-weight:800;margin-top:2px}
.mini .w{font-size:12.5px;color:var(--mut);margin-top:2px}
.reco{font-size:10.5px;font-weight:800;color:#231700;background:linear-gradient(135deg,var(--gold),var(--gold2));border-radius:99px;padding:1px 8px}
.agsel{width:100%;margin-top:6px;min-height:40px;border-radius:12px;border:1.5px solid var(--line);background:#fff;font:600 16px 'Heebo',sans-serif;color:var(--navy);padding:0 8px}
.script{margin-top:14px;border-radius:18px;background:linear-gradient(180deg,#FFFBF0,#fff);border:1px solid #F0E3BF;padding:13px 15px}
.script .h{color:var(--goldtxt);margin-bottom:6px}
.say{font-size:16px;line-height:1.7}
.say mark{background:#FBF3DF;color:inherit;border-radius:6px;padding:0 4px;font-weight:700}
.obj{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.obj button{background:#fff;border:1px solid #E8D9AE;color:var(--goldtxt);font-weight:700;font-size:12.5px;border-radius:99px;padding:0 12px;min-height:38px}
.obj button.on{background:var(--gold);color:#231700;border-color:var(--gold)}
.ans{display:none;margin-top:10px;font-size:14px;line-height:1.6;background:#fff;border-radius:14px;padding:10px 12px;border-inline-start:4px solid var(--gold)}
.ans.on{display:block}
.act{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.btn{min-height:52px;border-radius:16px;font-weight:800;font-size:16px;padding:0 20px;display:inline-flex;align-items:center;gap:8px;justify-content:center}
.btn.dial{background:var(--green);color:#fff;flex:1;font-size:17px;box-shadow:0 8px 22px rgba(21,122,67,.25)}
.btn.sec{background:#fff;color:var(--navy);border:1.5px solid var(--line)}
.btn.pri{background:var(--blue);color:#fff}
.btn.wa{background:var(--green);color:#fff}
.btn:disabled{opacity:.6}
.hint{font-size:12.5px;color:var(--mut2);margin-top:8px}
.call{margin-top:14px;border-radius:20px;background:linear-gradient(135deg,var(--navy0),var(--navy2));color:#fff;padding:16px}
.call .st{font-size:13px;opacity:.8}
.call .who{font-size:20px;font-weight:800;margin:3px 0}
.call .tm{font-variant-numeric:tabular-nums;font-size:30px;font-weight:800}
.call .tip{background:rgba(255,255,255,.08);border-radius:14px;padding:10px 12px;font-size:13.5px;line-height:1.6;margin-top:10px}
.call .tip b{color:var(--gold2)}
.og{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}
@media(max-width:560px){.og{grid-template-columns:1fr 1fr}}
.og button{min-height:64px;border-radius:16px;background:#fff;border:1.5px solid var(--line);font-weight:800;font-size:14px;color:var(--navy);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px}
.og button.main{background:var(--blue);color:#fff;border-color:var(--blue)}
.og button small{font-weight:500;font-size:11px;opacity:.75}
.slots{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 10px}
.slot{min-height:44px;border-radius:14px;border:1.5px solid var(--line);background:#fff;padding:0 14px;font-weight:700;font-size:14px;color:var(--navy);position:relative}
.slot.on{border-color:var(--blue);background:#EEF4FE;color:var(--blue)}
.slot.best::after{content:"מומלץ";position:absolute;top:-8px;inset-inline-end:8px;background:var(--gold);color:#231700;font-size:9.5px;font-weight:800;border-radius:99px;padding:1px 6px}
.dt{min-height:44px;border-radius:14px;border:1.5px solid var(--line);padding:0 10px;font:600 16px 'Heebo',sans-serif;color:var(--navy);background:#fff}
.lbl{font-size:12.5px;font-weight:700;color:var(--mut);margin-top:8px}
textarea{width:100%;min-height:64px;border-radius:14px;border:1.5px solid var(--line);padding:10px;font:500 16px 'Heebo',sans-serif;margin-top:6px;resize:vertical}
.ok{text-align:center;padding:24px 14px;border-radius:22px;background:linear-gradient(180deg,#FFFBF0,#fff);border:1px solid #F0E3BF;position:relative;overflow:hidden;margin-top:14px}
.ok .big{width:62px;height:62px;border-radius:50%;margin:0 auto 10px;display:grid;place-items:center;background:linear-gradient(135deg,var(--gold),var(--gold2))}
.ok h3{font-size:21px;color:var(--navy)}
.ok ul{list-style:none;margin:12px auto 0;max-width:380px;text-align:start;font-size:14px}
.ok li{display:flex;gap:8px;align-items:center;padding:5px 0}
.ok li i{width:20px;height:20px;border-radius:50%;background:#E6F4EC;display:grid;place-items:center;flex:none}
.ok li.x i{background:#F1F1EF}
.next{margin-top:12px;font-size:13px;color:var(--mut)}
.spark{position:absolute;width:8px;height:8px;border-radius:2px;animation:fly 1.1s ease-out forwards}
@keyframes fly{to{transform:translate(var(--x),var(--y)) rotate(320deg);opacity:0}}
.empty{text-align:center;padding:30px 16px}
.empty .ic{width:64px;height:64px;border-radius:50%;background:#FBF3DF;border:1.5px solid var(--gold2);display:grid;place-items:center;margin:0 auto 12px}
.empty h3{font-size:18px;color:var(--navy)}
.empty p{font-size:14px;color:var(--mut);margin-top:6px;line-height:1.55}
.empty .btn{margin-top:14px}
#toast{position:fixed;bottom:40px;left:50%;transform:translateX(-50%);background:var(--navy);color:#fff;font-size:13.5px;font-weight:700;
  padding:11px 18px;border-radius:14px;opacity:0;transition:opacity .2s;pointer-events:none;z-index:95;max-width:calc(100% - 32px);text-align:center}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
<div class="wrap" id="app"><div style="text-align:center;color:#5B6472;font-size:14px;padding:60px 0">מכין את התור שלך…</div></div>
<div id="toast" role="status" aria-live="polite"></div>
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
function toast(m){ var t = el('toast'); t.textContent = m; t.style.opacity = '1'; clearTimeout(t._h); t._h = setTimeout(function(){ t.style.opacity = '0'; }, 2800); }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function fmtP(p){ var d = String(p || '').replace(/\D/g, ''); return d ? Number(d).toLocaleString('en-US') + ' ₪' : ''; }
function first(n){ return String(n || '').trim().split(/\s+/)[0] || ''; }
function street(a){ return String(a || '').replace(/\s*\d.*$/, '').trim() || String(a || ''); }

var D = null, CUR = 0, MODE = 'lead', SLOT = 0, SLOTS = [], AGENT = '', TIMER = null, SECS = 0, BOOKED = null;
var BACK = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>';
var PHONE = '<svg width="20" height="20" viewBox="0 0 24 24" fill="#fff"><path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z"/></svg>';
var CHECK = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#157A43" stroke-width="3.5"><path d="M5 12l5 5L20 7"/></svg>';
var OBJ = [
  ['כבר יש לי מתווך', 'מצוין, זה אומר שאתם רציניים. אני לא מבקשת להחליף אף אחד. [B]חבל שהם לא יראו את הדירה. נקבע ביקור קצר של 20 דקות?'],
  ['אני מוכר לבד', 'לגמרי מבינה. מי שמוכר לבד מקבל הרבה שיחות ומעט קונים רציניים. [B]נביא רק קונים עם תקציב. אפשר לפחות שתכירו?'],
  ['כמה עמלה?', 'זה תלוי בנכס ובמה שתבחרו, והסוכן יציג הכל בפגישה בלי שום התחייבות. בואו נקבע 20 דקות ותחליטו אחרי.'],
  ['תתקשרו עוד חודש', 'בשמחה. בינתיים, מה דעתכם שהסוכן יקפוץ להערכת שווי חינם? ככה תדעו בדיוק איפה אתם עומדים כשתחליטו.']
];

function cur(){ return D && D.items[CUR]; }
function hdr(){
  var s = D.stats, pct = Math.min(1, s.meetings / Math.max(1, s.goal)), off = 125.6 - 125.6 * pct;
  var conv = s.calls ? Math.round(s.meetings / s.calls * 100) + '%' : '—';
  return '<div class="hero"><div class="top"><button class="back" onclick="location.href=\'/v2/home\'" aria-label="חזרה">' + BACK + '</button>' +
    '<div><h1>חייגן חכם<span class="ai">AI</span></h1><div class="sub">' + esc(D.office || '') + ' · ' + esc(first(D.me)) + ', התור שלך מסודר לפי סיכוי לפגישה</div></div></div>' +
    '<div class="kpis"><div class="kpi ring"><div class="ringw"><svg width="46" height="46"><circle cx="23" cy="23" r="20" stroke="rgba(255,255,255,.15)" stroke-width="5" fill="none"/>' +
    '<circle cx="23" cy="23" r="20" stroke="#E4C56B" stroke-width="5" fill="none" stroke-linecap="round" stroke-dasharray="125.6" stroke-dashoffset="' + off + '" style="transition:stroke-dashoffset .8s"/></svg>' +
    '<div class="n">' + s.meetings + '</div></div><div style="text-align:start"><b style="font-size:14px">פגישות היום</b><span>יעד ' + s.goal + '</span></div></div>' +
    '<div class="kpi"><b>' + s.calls + '</b><span>שיחות</span></div><div class="kpi"><b>' + conv + '</b><span>שיחה לפגישה</span></div></div></div>';
}
function scls(v){ return v >= 70 ? 'hi' : v >= 45 ? 'md' : 'lo'; }
function queueHtml(){
  var h = '<div class="h">התור שלך <span class="c">' + D.items.length + (D.more ? '+' : '') + ' ממתינים</span></div>';
  D.items.slice(0, 12).forEach(function(l, k){
    h += '<button class="qi' + (k === CUR ? ' cur' : '') + '" onclick="pick(' + k + ')"><div class="sc ' + scls(l.score) + '">' + l.score + '%</div>' +
      '<div style="min-width:0"><div class="t">' + esc(l.address) + '</div><div class="s">' + esc(l.city) + (l.rooms ? ' · ' + esc(l.rooms) + ' חד׳' : '') + ' · ' + esc(l.age.replace('פורסם ', '')) + '</div></div>' +
      (l.tries ? '<span class="tag">ניסיון ' + (l.tries + 1) + '</span>' : '') + '</button>';
  });
  if (D.later.length){
    h += '<div class="sub2">לחזור אליהם בהמשך</div>';
    D.later.slice(0, 6).forEach(function(l){
      h += '<div class="qi" style="cursor:default;opacity:.7"><div class="sc lo"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#5B6472" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></div>' +
        '<div><div class="t">' + esc(l.address) + '</div><div class="s">' + (l.outcome === 'na' ? 'לא ענה' : 'ביקש שנחזור') + '</div></div><span class="tag">' + esc(l.at) + '</span></div>';
    });
  }
  h += '<div class="insight"><b>טיפ:</b> בעלי נכסים עונים הכי הרבה בין 17:00 ל-19:00. מי שלא ענה חוזר לתור לבד בשעה הזו.</div>';
  return h;
}
function leadHtml(l){
  var ag = (l.agents || [])[0] || null;
  if (!AGENT) AGENT = ag ? ag.name : ((D.agents[0] || {}).name || '');
  var agInfo = (l.agents || []).filter(function(a){ return a.name === AGENT; })[0];
  var meta = [l.nb, l.city].filter(Boolean).join(', ') + (l.rooms ? ' · ' + l.rooms + ' חדרים' : '') + (l.sqm ? ' · ' + l.sqm + ' מ״ר' : '') + (l.floor ? ' · קומה ' + l.floor : '');
  var opts = D.agents.map(function(a){ return '<option' + (a.name === AGENT ? ' selected' : '') + '>' + esc(a.name) + '</option>'; }).join('');
  return '<div class="lead"><div><span class="fresh">' + esc(l.age) + '</span></div>' +
    '<div class="addr">' + esc(l.address) + '</div><div class="meta">' + esc(meta) + '</div>' +
    '<div class="price">' + esc(fmtP(l.price)) + (l.priceOld ? '<s>' + esc(fmtP(l.priceOld)) + '</s>' : '') + '</div>' +
    '<div class="chips">' + l.why.map(function(w){ return '<span class="chip ' + w.k + '">' + esc(w.t) + '</span>'; }).join('') + '</div>' +
    '<div class="scorebar">סיכוי לפגישה <div class="bar"><i id="sbar"></i></div><b>' + l.score + '%</b></div></div>' +
    '<div class="duo"><div class="mini"><div class="l">בעל הנכס</div><div class="v">' + esc(l.owner || 'לא צוין שם') + '</div>' +
      '<div class="w" dir="ltr" style="text-align:right">' + esc(l.phone) + '</div>' + (l.link ? '<div class="w"><a href="' + esc(l.link) + '" target="_blank" style="color:var(--blue);font-weight:700">למודעה</a></div>' : '') + '</div>' +
    '<div class="mini"><div class="l">הסוכן שיגיע' + (ag && ag.name === AGENT ? ' <span class="reco">המלצה</span>' : '') + '</div>' +
      '<select class="agsel" onchange="setAgent(this.value)" aria-label="הסוכן שיגיע">' + opts + '</select>' +
      '<div class="w">' + esc(agInfo && agInfo.why ? agInfo.why : '') + '</div></div></div>';
}
function scriptHtml(l){
  var b = l.buyers ? '<mark>' + (l.buyers === 1 ? 'קונה פעיל' : l.buyers + ' קונים פעילים') + '</mark> שמחפשים בדיוק ' + (l.rooms ? esc(l.rooms) + ' חדרים ' : 'נכס כזה ') + 'ב' + esc(l.nb || l.city) + '. '
              : 'קונים פעילים שמחפשים ב' + esc(l.nb || l.city) + '. ';
  var say = 'היי' + (l.owner ? ' ' + esc(first(l.owner)) : '') + ', מדברת ' + esc(first(D.me)) + ' מ' + esc(D.office || 'המשרד') + '. ראיתי את הנכס שלך ב<mark>' + esc(street(l.address)) + '</mark>. ' +
            'יש לנו ' + b + 'אפשר שהסוכן שלנו ' + esc(first(AGENT)) + ' יקפוץ לביקור קצר?';
  return '<div class="script"><div class="h">מה להגיד <span class="c" style="color:var(--goldtxt)">נכתב לבעל הנכס הזה</span></div><p class="say">' + say + '</p>' +
    '<div class="obj">' + OBJ.map(function(o, k){ return '<button onclick="objection(' + k + ',this)">' + o[0] + '</button>'; }).join('') + '</div><div class="ans" id="ans"></div></div>';
}
function render(){
  if (!D) return;
  if (!D.allowed){
    el('app').innerHTML = '<div class="hero"><div class="top"><button class="back" onclick="location.href=\'/v2/home\'" aria-label="חזרה">' + BACK + '</button><h1>חייגן חכם</h1></div></div>' +
      '<div class="card" style="margin:14px"><div class="empty"><div class="ic">' + PHONE.replace('#fff', '#7A5E1C') + '</div><h3>החייגן פתוח כרגע למתאמות</h3><p>כשנפתח אותו לכל המשרד, הוא יופיע כאן.</p></div></div>';
    return;
  }
  var l = cur(), main = '';
  if (!l){
    main = '<div class="empty"><div class="ic">' + CHECK.replace(/12/g, '28') + '</div><h3>סיימת את התור</h3><p>אין כרגע בעלי נכסים לחייג אליהם. נכסים חדשים ייכנסו לתור ברגע שהסורק יביא אותם, ומי שביקש שנחזור יופיע בשעה שנקבעה.</p>' +
      '<button class="btn sec" onclick="load()">רענון התור</button></div>';
  } else if (MODE === 'lead'){
    main = leadHtml(l) + scriptHtml(l) + '<div class="act"><button class="btn dial" onclick="dial()">' + PHONE + 'חייג מהקו של המשרד</button><button class="btn sec" onclick="skip()">דלג</button></div>' +
      '<div class="hint">הטלפון שלך יצלצל ראשון, ואז בעל הנכס. השיחה מוקלטת ומסוכמת ביומן השיחות.</div>';
  } else if (MODE === 'call'){
    main = leadHtml(l) + scriptHtml(l) + '<div class="call"><div class="st">בשיחה</div><div class="who">' + esc(l.owner || 'בעל הנכס') + ' · ' + esc(l.address) + '</div><div class="tm" id="tm">00:00</div>' +
      '<div class="tip"><b>טיפ:</b> סיימי בהצעה של שני מועדים — "מתאים לך היום בערב או מחר בבוקר?" קל יותר לבחור מאשר להחליט.</div></div>' +
      '<div class="og"><button class="main" onclick="outcome(\'meet\')">נקבעה פגישה<small>לבחור מועד</small></button><button onclick="outcome(\'back\')">לחזור אליו<small>מחר 10:00</small></button>' +
      '<button onclick="outcome(\'na\')">לא ענה<small>חוזר לתור לבד</small></button><button onclick="outcome(\'no\')">לא מעוניין<small>יוצא מהתור</small></button></div>';
  } else if (MODE === 'book'){
    main = '<div class="h">פגישה ל' + esc(AGENT) + ' · ' + esc(l.address) + '</div>' +
      '<div class="lbl">מועדים פנויים ביומן שלו באפי</div><div class="slots" id="slots">' + slotsHtml() + '</div>' +
      '<div class="lbl">או מועד אחר</div><input type="datetime-local" class="dt" id="dtx" onchange="SLOT=-1;el(\'slots\').innerHTML=slotsHtml()">' +
      '<div class="lbl">הערה לסוכן (לא חובה)</div><textarea id="note" placeholder="למשל: מתלבט בין שני מתווכים, פנוי בערבים"></textarea>' +
      '<div class="act"><button class="btn pri" style="flex:1" id="bookBtn" onclick="book()">קבע פגישה</button><button class="btn sec" onclick="MODE=\'call\';render()">חזרה</button></div>';
  } else if (MODE === 'done'){
    var b = BOOKED;
    main = '<div class="ok" id="okc"><div class="big"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#231700" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg></div>' +
      '<h3>פגישה נקבעה ל' + esc(b.agent) + '</h3><ul>' +
      '<li><i>' + CHECK + '</i>' + esc(b.when) + ', נשמר ביומן הפגישות באפי</li>' +
      '<li class="' + (b.cal ? '' : 'x') + '"><i>' + (b.cal ? CHECK : '') + '</i>' + (b.cal ? 'נכנס ליומן Google' : 'לא נכנס ליומן Google — הסוכן לא מחובר לסנכרון') + '</li>' +
      (b.pushed ? '<li><i>' + CHECK + '</i>נשלחה התראה ל' + esc(first(b.agent)) + ' עם הפרטים</li>' : '') + '<li><i>' + CHECK + '</i>נספר לך ביעדים ובתחרות</li></ul>' +
      (b.wa ? '<div class="act" style="justify-content:center"><button class="btn wa" onclick="sendWa()">שלחי אישור לבעל הנכס בוואטסאפ</button></div>' : '') +
      '<div class="act" style="justify-content:center"><button class="btn sec" onclick="nextLead()">לבעל הנכס הבא</button></div></div>';
  }
  el('app').innerHTML = hdr() + '<div class="grid"><div class="side card">' + queueHtml() + '</div><div class="card">' + main + '</div></div>';
  if (MODE === 'lead' && el('sbar')) setTimeout(function(){ var b = el('sbar'); if (b && l) b.style.width = l.score + '%'; }, 60);
  else if (el('sbar') && l) el('sbar').style.width = l.score + '%';
  if (MODE === 'call') tick();
}
function slotsHtml(){
  if (!SLOTS.length) return '<span style="font-size:13px;color:var(--mut)">אין מועד פנוי ב-4 הימים הקרובים — בחרי מועד למטה</span>';
  return SLOTS.map(function(s, k){ return '<button class="slot' + (k === SLOT ? ' on' : '') + (k === 0 ? ' best' : '') + '" onclick="SLOT=' + k + ';el(\'dtx\').value=\'\';el(\'slots\').innerHTML=slotsHtml()">' + esc(s.label) + '</button>'; }).join('');
}
function pick(k){ if (MODE === 'call' && !confirm('לצאת מהשיחה בלי לתעד תוצאה?')) return; stopT(); CUR = k; MODE = 'lead'; AGENT = ''; render(); scrollTo(0, 0); }
function setAgent(n){ AGENT = n; render(); }
function objection(k, b){
  var bs = document.querySelectorAll('.obj button'); for (var i = 0; i < bs.length; i++) bs[i].classList.remove('on');
  b.classList.add('on'); var l = cur();
  var bt = l.buyers ? 'יש לנו ' + (l.buyers === 1 ? 'קונה פעיל' : l.buyers + ' קונים פעילים') + ' שמחפשים בדיוק כזה, ו' : '';
  el('ans').innerHTML = esc(OBJ[k][1].replace('[B]', bt)); el('ans').classList.add('on');
}
function dial(){
  var l = cur(); if (!l) return;
  POST('/v2/api/dialer/dial', {key: l.key, addr: l.address}).catch(function(){});
  POST('/api/newborn/contact', {key: l.key, addr: l.address}).catch(function(){});   // 'מי פנה' — סוכנים יראו שכבר פנו
  D.stats.calls++;
  if (typeof c2cDial === 'function') c2cDial(l.tel); else location.href = 'tel:' + l.tel;
  MODE = 'call'; SECS = 0; render();
}
function tick(){ stopT(); TIMER = setInterval(function(){ SECS++; var t = el('tm'); if (t) t.textContent = String(Math.floor(SECS / 60)).padStart(2, '0') + ':' + String(SECS % 60).padStart(2, '0'); }, 1000); }
function stopT(){ clearInterval(TIMER); TIMER = null; }
function outcome(o){
  var l = cur(); if (!l) return;
  if (o === 'meet'){ stopT(); MODE = 'book'; SLOT = 0; SLOTS = []; render(); loadSlots(); return; }
  stopT();
  POST('/v2/api/dialer/outcome', {key: l.key, outcome: o, addr: l.address}).then(function(j){
    if (!j || !j.ok){ toast('לא נשמר — נסי שוב'); return; }
    if (o === 'na') toast('לא ענה. חוזר לתור ב-' + j.retryAt);
    if (o === 'back') toast('נחזור אליו מחר ב-' + j.retryAt);
    if (o === 'no') toast('יצא מהתור, גם אצל שאר המתאמות');
    if (o !== 'no') D.later.unshift({key: l.key, address: l.address, outcome: o, at: j.retryAt});
    D.items.splice(CUR, 1); if (CUR >= D.items.length) CUR = 0; MODE = 'lead'; AGENT = ''; render();
  });
}
function loadSlots(){
  GET('/v2/api/dialer/slots?agent=' + encodeURIComponent(AGENT)).then(function(j){ SLOTS = (j && j.slots) || []; SLOT = SLOTS.length ? 0 : -1; if (MODE === 'book' && el('slots')) el('slots').innerHTML = slotsHtml(); });
}
function book(){
  var l = cur(), date = '', label = '';
  var dx = el('dtx') && el('dtx').value;
  if (dx){ date = dx.slice(0, 16); var d = new Date(dx); label = d.toLocaleDateString('he-IL', {weekday:'long', day:'numeric', month:'numeric'}) + ' ' + dx.slice(11, 16); }
  else if (SLOT >= 0 && SLOTS[SLOT]){ date = SLOTS[SLOT].iso; label = SLOTS[SLOT].label; }
  if (!date){ toast('בחרי מועד לפגישה'); return; }
  var bb = el('bookBtn'); bb.disabled = true; bb.textContent = 'קובע…';
  var note = (el('note').value || '').trim();
  POST('/api/newborn/status', {key: l.key, addr: l.address + (l.city ? ', ' + l.city : ''), price: l.price, phone: l.phone, owner: l.owner,
                               status: 'meeting', date: date, agent: AGENT, note: note}).then(function(j){
    if (!j || !j.ok){ bb.disabled = false; bb.textContent = 'קבע פגישה'; toast('הפגישה לא נשמרה — נסי שוב'); return; }
    D.stats.meetings++;
    BOOKED = {agent: AGENT, when: label, cal: !!j.calendar, wa: l.wa, owner: l.owner, addr: l.address, pushed: false};
    var fin = function(){ MODE = 'done'; render(); burst(); };
    POST('/v2/api/dialer/outcome', {key: l.key, outcome: 'meet', addr: l.address, agent: AGENT, when: label, owner: l.owner})
      .then(function(o){ BOOKED.pushed = !!(o && o.pushed); fin(); }).catch(fin);
  }).catch(function(){ bb.disabled = false; bb.textContent = 'קבע פגישה'; toast('אין חיבור — נסי שוב'); });
}
function sendWa(){
  var b = BOOKED;
  var t = 'היי' + (b.owner ? ' ' + first(b.owner) : '') + ', תודה על השיחה! כמו שסיכמנו, ' + b.agent + ' מ' + (D.office || 'המשרד') + ' יגיע אליך ל' + b.addr + ', ' + b.when + '. אם משהו משתנה, אפשר לכתוב לי כאן.';
  window.open('https://wa.me/' + b.wa + '?text=' + encodeURIComponent(t), '_blank');
}
function nextLead(){ D.items.splice(CUR, 1); if (CUR >= D.items.length) CUR = 0; MODE = 'lead'; AGENT = ''; BOOKED = null; render(); scrollTo(0, 0); }
function skip(){ if (!D.items.length) return; CUR = (CUR + 1) % D.items.length; AGENT = ''; render(); }
function burst(){
  var box = el('okc'); if (!box) return;
  for (var k = 0; k < 24; k++){
    var s = document.createElement('i'); s.className = 'spark'; s.style.left = '50%'; s.style.top = '56px';
    s.style.background = k % 3 ? '#C29435' : '#E4C56B';
    s.style.setProperty('--x', (Math.random() * 340 - 170) + 'px'); s.style.setProperty('--y', (Math.random() * 190 - 110) + 'px');
    box.appendChild(s); (function(x){ setTimeout(function(){ x.remove(); }, 1200); })(s);
  }
}
function load(){
  GET('/v2/api/dialer/queue').then(function(j){
    if (!j || !j.ok){ el('app').innerHTML = '<div style="text-align:center;color:#5B6472;padding:60px 16px">לא הצלחנו לטעון את התור. <button class="btn sec" onclick="load()">נסי שוב</button></div>'; return; }
    D = j; D.items = D.items || []; D.later = D.later || []; D.agents = D.agents || [];
    CUR = 0; MODE = 'lead'; AGENT = ''; render();
  }).catch(function(){ el('app').innerHTML = '<div style="text-align:center;color:#5B6472;padding:60px 16px">אין חיבור. <button class="btn sec" onclick="load()">נסי שוב</button></div>'; });
}
load();
</script></body></html>'''
