# kit_core.py — ליבה טהורה של תיק הפרזנטציה (בלי רשת, בלי DB, בלי AI)
import re
import datetime as _dt

APPROVE_H = 48
MIN_BUYERS = 3
BUYER_MIN = 60
_VIEW_GAP = 1800
_VIEW_CAP = 4 * 3600
_DAYS = ["ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳", "א׳"]  # Monday=0 → ב׳ ... Sunday=6 → א׳


def phone9(v):
    d = re.sub(r"\D", "", str(v or ""))
    return d[-9:] if len(d) >= 9 else ""


def wa972(v):
    p = phone9(v)
    return "972" + p if p else ""


def street_only(street):
    """שם הרחוב בלי מספר בית (אותו כלל כמו social_publish.soc_scrub_house).
    גם '12 א' (רווח לפני האות), וכתובת עם ', עיר' — נשאר רק הרחוב (העיר מוצגת בנפרד)."""
    t = str(street or "").split(",")[0].strip()
    t = re.sub(r"^\d+\S*\s*", "", t)                      # מספר בתחילת הכתובת ('18 הנוטר')
    m = re.search(r"\d", t)
    if m:                                                    # הכל מהמספר הראשון והלאה (12 א׳ / 12-14 / דירה 4 / קומה 3)
        t = t[:m.start()]
    t = re.sub(r"(?:\s|^)מס['׳\.]?\s*$", "", t)              # 'מס'' שנשאר לפני המספר
    t = re.sub(r"[\s\-–/\\.,'׳\"״]+$", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _ts(v):
    try:
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace("Z", "+00:00")
        d = _dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=_dt.timezone.utc)
        return d.timestamp()
    except Exception:
        return None


def eff_status(rec, now):
    st = (rec or {}).get("status") or ""
    if st == "pending":
        t = _ts(rec.get("sent_review_at"))
        if t is not None and now - t > APPROVE_H * 3600:
            return "expired"
    return st


def decide(rec, action, who, now):
    st = eff_status(rec, now)
    if st == "expired":
        return None, "פג תוקף"
    if st in ("approved", "sent"):
        return None, "כבר אושר"
    if st == "rejected":
        return None, "כבר נדחה"
    if st != "pending":
        return None, "פג תוקף"
    if action == "approve":
        return "approved", "אושר"
    if action == "reject":
        return "rejected", "נדחה"
    return None, "פג תוקף"


def owner_message(snap):
    s = snap or {}
    ag, of = s.get("agent"), s.get("office")
    ag = (ag.get("name") or "") if isinstance(ag, dict) else (ag or "")   # בצילום האמיתי — agent_block / office_numbers
    of = (of.get("office") or "") if isinstance(of, dict) else (of or "")
    head = "שלום %s, כאן %s מ%s." % (s.get("owner_first") or "", ag, of)
    meet = ""
    m = str(s.get("meet_at") or "").strip()
    if m:
        try:
            d = _dt.datetime.fromisoformat(m)
            meet = " לקראת הפגישה שלנו ביום %s %s" % (_DAYS[d.weekday()], d.strftime("%d/%m"))
            if "T" in m or " " in m:   # שעה רק כשנקבעה
                meet += " בשעה %s" % d.strftime("%H:%M")
        except Exception:
            meet = ""
    body = "הכנתי לך תיק אישי על הנכס שלך ב%s." % (s.get("street") or "")
    if meet:
        return "%s%s %s אשמח שתעיף מבט לפני שנפגש." % (head, meet, body)
    return "%s %s אשמח שתעיף מבט לפני שנפגש." % (head, body)


def file_name(snap):
    return "תיק אישי - %s.pdf" % ((snap or {}).get("owner") or "").strip()


def view_add(views, now, step=15):
    v = dict(views or {})
    first = v.get("first") or now
    last = v.get("last")
    opens = int(v.get("opens") or 0)
    secs = int(v.get("secs") or 0)
    if last is None or now - last > _VIEW_GAP:
        opens += 1
    secs = min(secs + step, _VIEW_CAP)
    return {"first": first, "last": now, "opens": opens, "secs": secs}


def manual_validate(form):
    f = form or {}
    if not str(f.get("owner") or "").strip():
        return "owner"
    if not phone9(f.get("phone")):
        return "phone"
    if not str(f.get("addr") or "").strip():
        return "addr"
    if not str(f.get("rooms") or "").strip():
        return "rooms"
    if not str(f.get("price") or "").strip():
        return "price"
    return None


# ── צילום הנתונים (Task 2): כל מה שהעמודים מציגים נקבע כאן, פעם אחת, ונשמר עם התיק ──────────
import logging as _logging
import os as _os

_log = _logging.getLogger(__name__)

KIT_DEFAULTS = {
    "coop": "מעל 70% מהעסקאות שלנו נסגרות בשיתוף פעולה בין סוכני <office>",
    "rank": "מקום 2 בעסקאות ברשת רימקס ישראל · מתחילת 2026, נכון ל-01/11/2026",
    "g_rating": "4.9",
    "g_count": "118",
    "g_url": "",
    "instagram": "",
    "facebook": "",
}


def kit_settings(cfg):
    """הטענות הקבועות (ניתנות לעריכה בניהול) — v2_kit מעל ברירות המחדל. ערך ריק לא דורס."""
    out = dict(KIT_DEFAULTS)
    for k, v in ((cfg or {}).get("v2_kit") or {}).items():
        if k in out and str(v or "").strip():
            out[k] = str(v).strip()
    v2o = (cfg or {}).get("v2_office") or {}
    for k in ("instagram", "facebook"):     # בלי ערך בכרטיס התיק — הקישור שהוגדר בפרטי המשרד
        if not out[k] and str(v2o.get(k) or "").strip().startswith("https://"):
            out[k] = str(v2o[k]).strip()
    return out


def site_slug(s) -> str:
    # מועתק כמו שהוא מ-refamily-site/refsite/textutil.py:18-20
    t = re.sub(r"[^\w֐-׿]+", "-", str(s or ""))
    return re.sub(r"-+", "-", t).strip("-")


def _norm_city(s):
    return re.sub(r"\s+", " ", str(s or "").replace("קריית", "קרית")).strip()


def _office_name(G):
    try:
        return str(((G["_load_config"]() or {}).get("v2_office") or {}).get("name") or "").strip()
    except Exception:
        return ""


def _date(v):
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


OFFICE_SINCE = 2005      # 21 שנות ניסיון בקריות ב-2026 (אייל, 08/11)


def office_numbers(G):
    """שנות ניסיון · עסקאות (צדדים, מכירה/קנייה, מאז 2016 — כלל side_counts של האתר) · סוכנים."""
    def build():
        today = _dt.date.today()
        since, lim = _dt.date(2016, 1, 1), today
        deals = 0
        try:
            sb = G.get("_sbdb")
            rows = sb.deal_history_all() if (sb and sb.enabled()) else []
        except Exception as e:
            _log.warning("kit office_numbers: deals failed: %s", e)
            rows = []
        for r in rows or []:
            if not isinstance(r, dict) or r.get("missing_since"):
                continue
            d = _date(r.get("deal_date"))
            if not d or d < since or d > lim:
                continue
            side = str(r.get("side") or "")
            if "שוכר" in side or "משכיר" in side:
                continue
            deals += 1
        agents = 0
        try:
            import effie_v2 as _ev
            coords = G["_coordinators_all"]() or {}
            cph = set(coords.keys())
            cnames = {G["_name_key"](v.get("name") or "") for v in coords.values() if isinstance(v, dict)}
            for nm in _ev.crm_roster(G) or []:
                phones = [G["_last9"](p) for p in (G["_phones_for_name"](nm) or [])]
                if G["_name_key"](nm) in cnames or any(p in cph for p in phones):
                    continue
                if any(p and G["_resolve_roles"](p)[1] == "agent" for p in phones):
                    agents += 1
        except Exception as e:
            _log.warning("kit office_numbers: agents failed: %s", e)
        return {"years": today.year - OFFICE_SINCE, "deals": deals, "agents": agents, "office": _office_name(G)}
    return G["_swr"]("kit:office", 1800, build)


def _num(v):
    try:
        return float(str(v or "").replace(",", "").strip())
    except ValueError:
        return None


def _rooms_txt(r):
    return ("%g" % r) if r is not None else ""


def buyers_block(G, listing):
    """קונים שמתאימים לנכס — אותו ציון כמו בחייגן (bai_score ≥ BUYER_MIN), בלי סגרו/בהקפאה. מספרים בלבד.
    פחות מ-MIN_BUYERS — מצב עיר: כמה קונים פעילים מחפשים בעיר."""
    import effie_v2 as _ev
    L = listing or {}
    city = _norm_city(L.get("עיר / ישוב"))
    price_n = _ev.bai_budget(L.get("מחיר"))
    rooms = _num(L.get("חדרים"))
    parsed = {"city": city, "neighborhood": L.get("שכונה") or "", "budget_max": price_n,
              "rooms_min": rooms, "rooms_max": rooms, "property_type": L.get("סוג נכס") or "",
              "_qtext": L.get("סוג נכס") or ""}
    try:
        idx = G["_nb_alias_idx"]()
    except Exception:
        idx = None
    try:
        area = _ev.bai_area_terms(parsed, idx) if idx else None
    except Exception:
        area = None
    try:
        stat = G["_bstat_current"]() if "_bstat_current" in G else {}
    except Exception:
        stat = {}
    active = []
    for r in (G["_fetch_manual_buyers"]() or []):
        try:
            st = _ev.bstat_of(r, stat, G["_bcanon"]) if "_bcanon" in G else None
        except Exception:
            st = None
        if st in ("closed", "frozen"):
            continue
        text = " ".join(str(r.get(k, "") or "") for k in ("search", "summary"))
        rb = _ev.bai_budget(r.get("budget", "")) or _ev.bai_budget(r.get("search", ""))
        active.append((text, rb))
    matched = []
    for text, rb in active:
        try:
            if _ev.bai_score(parsed, text, rb, False, area)[0] >= BUYER_MIN:
                matched.append((text, rb))
        except Exception:
            continue
    if len(matched) < MIN_BUYERS:
        n = sum(1 for text, _ in active if city and city in _norm_city(text))
        return {"mode": "city", "n": n, "lines": [], "city": city}
    lines = []
    floor = int(price_n // 100000 * 100000) if price_n else 0
    if floor:
        lines.append(["תקציב של {:,} ומעלה".format(floor), sum(1 for _, rb in matched if rb and rb >= floor)])
    if rooms:
        def _ok(text):
            br = _ev.bai_rooms(text)
            return bool(br) and br[1] >= rooms
        lines.append(["מחפשים %s חדרים ומעלה" % _rooms_txt(rooms), sum(1 for t, _ in matched if _ok(t))])
    if city:
        lines.append(["מחפשים ב" + city, sum(1 for t, _ in matched if city in _norm_city(t))])
    return {"mode": "match", "n": len(matched), "lines": [l for l in lines if l[1] > 0], "city": city}


def _settings_rows(G):
    try:
        import site_api
        return site_api.SettingsStore(G.get("_sbdb")).all() or []
    except Exception as e:
        _log.warning("kit agent_block: website_settings failed: %s", e)
        return []


def agent_block(G, name, phone9_, settings_rows=None):
    """עמוד הסוכן: שם, רישיון, הטקסט מהאתר, המלצה אחת, תמונה וקישור לעמוד באתר (רק כשהוא ציבורי)."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    p9 = phone9(phone9_)
    nk = G.get("_name_key") or (lambda s: re.sub(r"\s+", "", str(s or "")))
    try:
        cfg = G["_load_config"]() or {}
    except Exception:
        cfg = {}
    lic = str((cfg.get("v2_licenses") or {}).get(p9, "") or "").strip() if p9 else ""
    if not lic and name:
        try:
            for v in (G["fetch_agents_full"]() or {}).values():
                if nk(v.get("name") or "") == nk(name):
                    lic = str(v.get("license") or "").strip()
                    break
        except Exception:
            pass
    rows = _settings_rows(G) if settings_rows is None else settings_rows
    arow = next((r for r in rows if r.get("kind") == "agent" and name and nk(r.get("key")) == nk(name)), None)
    ad = (arow or {}).get("data") or {}
    bio = re.sub(r"[ \t]+", " ", re.sub(r"<[^>]*>", "", str(ad.get("bio") or ""))).strip()
    review = None
    try:
        import site_api
        revs = site_api.reviews_active(rows)
    except Exception:
        revs = []
    own = next((r for r in revs if any(nk(a) == nk(name) for a in r.get("agents") or [])), None) if name else None
    pick = own or (revs[0] if revs else None)
    if pick:
        review = {"text": str(pick.get("text") or "").strip(), "by": str(pick.get("by") or "").strip()}
    photo = None
    if name:
        try:
            import social_video
            photo = social_video._agent_photo(G, {"סוכן 1": name})
        except Exception:
            photo = None
    site_url = ""
    if name and not (arow is not None and ad.get("shown", True) is False):
        site_url = _os.environ.get("SITE_PUBLIC_URL", "https://refamily.co.il").rstrip("/") + "/צוות/" + site_slug(name)
    return {"name": name, "first": name.split(" ")[0] if name else "", "license": lic, "bio": bio,
            "review": review, "photo": photo, "site_url": site_url}


def _cma_block(G, listing):
    """מקום שמור לעמוד ניתוח שוק — cma.py עוד לא קיים (אז None)."""
    try:
        import cma
    except ImportError:
        return None
    try:
        return cma.cma_block(G, listing)
    except Exception as e:
        _log.warning("kit cma_block failed: %s", e)
        return None


def _fmt_price(v):
    d = re.sub(r"\D", "", str(v or ""))
    return "{:,}".format(int(d)) if d else ""


def _fmt_phone(v):
    p = phone9(v)
    return ("0%s-%s" % (p[:2], p[2:])) if p else ""


def build_snapshot(G, src):
    """src (owner, phone, street, city, rooms, price, meet_at, agent_name, agent_phone [, sqm, ptype]) →
    הצילום שממנו התיק מצויר. מה שאייל אישר = מה שבעל הנכס רואה."""
    s = src or {}
    owner = re.sub(r"\s+", " ", str(s.get("owner") or "")).strip()
    city = _norm_city(s.get("city"))
    rooms = str(s.get("rooms") or "").strip()
    price = _fmt_price(s.get("price"))
    listing = {"עיר / ישוב": city, "שכונה": "", "חדרים": rooms, "מחיר": price,
               "סוג נכס": str(s.get("ptype") or "").strip() or "דירה",
               "sqm": str(s.get("sqm") or "").strip(), "ptype": str(s.get("ptype") or "").strip() or "דירה"}
    # לניתוח השוק בלבד: הכתובת המלאה ומפתח המודעה — לא נשמרים בצילום (בלי מספר בית בתיק)
    cma_in = dict(listing, **{"רחוב": str(s.get("street") or "").strip(),
                              "listing_key": str(s.get("listing_key") or s.get("nb_key") or s.get("pkey") or "")})
    agent = agent_block(G, s.get("agent_name"), s.get("agent_phone"))
    agent["phone"] = _fmt_phone(s.get("agent_phone"))
    try:
        cfg = G["_load_config"]() or {}
    except Exception:
        cfg = {}
    try:
        buyers = buyers_block(G, listing)
    except Exception as e:
        _log.warning("kit buyers_block failed: %s", e)
        buyers = {"mode": "city", "n": 0, "lines": [], "city": city}
    return {
        "owner": owner, "owner_first": owner.split(" ")[0] if owner else "",
        "street": street_only(s.get("street")), "city": city, "rooms": rooms, "price": price,
        "meet_at": str(s.get("meet_at") or "").strip(),
        "agent": agent, "office": office_numbers(G), "buyers": buyers, "claims": kit_settings(cfg),
        "listing": listing, "cma": _cma_block(G, cma_in),
        "made_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
