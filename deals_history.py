# deals_history.py
"""[DEALS-HISTORY 12/10] היסטוריית עסקאות — נרמול שורות מקבצי 'מעקב עסקאות', תצוגות לפי הרשאה,
סטטיסטיקה, ראוטים ודף /v2/history. ספק: docs/superpowers/specs/2026-10-12-deals-history-design.md"""
import os
import re
import time
import hmac
import datetime as _dt

BRANCHES = {"bialik": "ביאליק", "motzkin": "מוצקין", "kiryat_yam": "קרית ים"}

# שדה → כותרות אפשריות (התאמה מדויקת קודם, אחר כך תחילית). הסדר חשוב: ספציפי לפני כללי.
HEADER_FIELDS = [
    ("serial", ['מס"ד', "מסד", "מס'"]),
    ("month", ["חודש"]),
    ("deal_date", ["תאריך עסקה", "תאריך"]),
    ("city", ["עיר"]),
    ("street", ["רחוב"]),
    ("address", ["כתובת"]),
    ("side", ["קונה / מוכר", "קונה/מוכר", "צד"]),
    ("other_broker", ["מתווך בצד השני"]),
    ("agent", ["סוכן", "מתווך"]),
    ("collection_status", ["סטאוס טיפול בגבייה", "סטטוס טיפול בגבייה"]),
    ("client", ["טל ושם לקוח", "שם לקוח", "לקוח"]),
    ("notes", ["הערה", "הערות"]),
    ("discount", ["הנחה לפני מעמ", 'הנחה לפני מע"מ', "הנחה"]),
    ("deal_amount", ["סכום העסקה", "סכום עסקה"]),
    ("commission_gross", ["עמלה כולל מעמ", 'עמלה כולל מע"מ']),
    ("commission_net", ["עמלה לפני מעמ", 'עמלה לפני מע"מ']),
    ("lead_source", ["מאיפה הגיע הלקוח"]),
    ("paid_amount", ["התקבל כסף"]),
    ("deposited", ["הופקד"]),
    ("invoice_no", ["חשבונית", "חשבונית מס קבלה"]),
    ("receipt_no", ["קבלה"]),
    ("reported_date", ["דווח במערכת"]),
    ("remax_approved", ["אישור לרימקס"]),
    ("lawyer_notes", ['עו"ד / הערות', 'עו"ד']),
]
_PREFIX_OK = {"lawyer_notes", "invoice_no"}   # כותרות שמגיעות עם המשך ('עו"ד ויסמן / ...', 'חשבונית מס קבלה')
CITIES = ["קרית מוצקין", "קרית ביאליק", "קרית ים", "קרית אתא", "קרית חיים", "חיפה", "עכו", "נשר"]


def normalize_header(v):
    t = re.sub(r"\s+", " ", str(v or "")).strip()
    return t.replace("״", '"').replace("׳", "'").replace("קריית", "קרית")


def find_header_row(rows, scan=10):
    """השורה הראשונה (מתוך scan) עם ≥4 כותרות מוכרות → (index, {field: col})."""
    for i, r in enumerate(rows[:scan]):
        fields = {}
        hdr = [normalize_header(c) for c in (r or ())]
        for field, names in HEADER_FIELDS:
            for col, h in enumerate(hdr):
                if not h or col in fields.values():
                    continue
                if h in names or (field in _PREFIX_OK and any(h.startswith(nm) for nm in names)):
                    fields[field] = col
                    break
        for col, h in enumerate(hdr):
            if h == "התחשבנות סוכן":
                fields["_settlement"] = col   # נשמר רק ב-raw — לא מוצג באפי
        if len([k for k in fields if not k.startswith("_")]) >= 4:
            return i, fields
    return None, {}


def parse_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return _dt.date(1899, 12, 30) + _dt.timedelta(days=int(v))
    m = re.match(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", str(v))
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return _dt.date(y, mo, d)
        except ValueError:
            return None
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", str(v))
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_num(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[₪,\s]", "", str(v))
    try:
        return float(t)
    except ValueError:
        return None


def _num_out(v):
    x = parse_num(v)
    if x is None:
        return None
    return int(x) if float(x).is_integer() else round(x, 2)


_PHONE = re.compile(r"0[2-9]\d?[\s\-]?\d{3}[\s\-]?\d{4}")


def split_client(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if not s:
        return "", ""
    m = _PHONE.search(s)
    phone = re.sub(r"\D", "", m.group(0)) if m else ""
    name = (s[:m.start()] + " " + s[m.end():]) if m else s
    name = re.sub(r"\s+", " ", re.sub(r"[-–,/|]+", " ", name)).strip()
    return name, phone


def norm_side(s):
    t = re.sub(r"\s+", "", str(s or ""))
    parts = [w for w in ("קונה", "מוכר", "משכיר") if w in t]
    if "שוכר" in t.replace("משכיר", ""):
        parts.append("שוכר")
    return "+".join(parts) if parts else re.sub(r"\s+", " ", str(s or "")).strip()


def _cell(cells, fields, f):
    i = fields.get(f)
    if i is None or i >= len(cells):
        return None
    v = cells[i]
    return None if (isinstance(v, str) and not v.strip()) else v


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.strftime("%d/%m/%Y")
    return re.sub(r"\s+", " ", str(v)).strip()


def _split_address(addr):
    a = normalize_header(addr)
    for c in CITIES:
        if c in a:
            return c, re.sub(r"\s+", " ", a.replace(c, " ").strip(" ,"))
    return "", a


def normalize_row(cells, fields, ctx):
    """שורת אקסל → ('ok'|'skip'|'broken', row). row בעמודות הטבלה + src_key + raw (כל התאים כטקסט)."""
    cells = tuple(cells or ())
    if not any(c not in (None, "") and not (isinstance(c, str) and not c.strip()) for c in cells):
        return "skip", None
    agent = _txt(_cell(cells, fields, "agent"))
    if re.search(r'סה"כ|סה״כ|סיכום|total', agent, re.I):
        return "skip", None
    amount = _num_out(_cell(cells, fields, "deal_amount"))
    comm = _num_out(_cell(cells, fields, "commission_net"))
    city = _txt(_cell(cells, fields, "city"))
    street = _txt(_cell(cells, fields, "street"))
    if not street and "address" in fields:
        c2, street = _split_address(_txt(_cell(cells, fields, "address")))
        city = city or c2
    ddate = parse_date(_cell(cells, fields, "deal_date"))
    if not agent and ctx.get("default_agent") and (ddate or amount is not None or street):
        agent = ctx["default_agent"]   # קרית ים: עמודת הסוכן ריקה — כל העסקאות של קובי חמו (אייל 12/10)
    if not agent:
        return "skip", None   # שורות סיכום חודשיות / הערות — בלי סוכן אין עסקה
    if not ddate and amount is None and comm is None and not street:
        return "broken", {"agent": agent, "src_row": ctx["row_idx"], "sheet": ctx["sheet"]}
    name, phone = split_client(_cell(cells, fields, "client"))
    serial = _txt(_cell(cells, fields, "serial"))
    key_tail = serial if re.fullmatch(r"\d+", serial or "") else "r%d" % ctx["row_idx"]
    rep = parse_date(_cell(cells, fields, "reported_date"))
    hdr_names = ctx.get("headers") or []   # כל התאים המקוריים לפי כותרת (כשהכותרות ידועות)
    raw = {}
    for i, c in enumerate(cells):
        h = hdr_names[i] if i < len(hdr_names) else ""
        if c not in (None, "") and not (isinstance(c, str) and not c.strip()) and h:
            raw[h] = _txt(c)
    si = fields.get("_settlement")
    if si is not None and si < len(cells) and cells[si] not in (None, ""):
        raw["התחשבנות סוכן"] = _txt(cells[si])
    row = {
        "branch": ctx["branch"], "year": int(ctx["year"]), "src_sheet": ctx["sheet"], "src_row": ctx["row_idx"],
        "src_serial": serial, "src_key": "%s|%s|%s|%s" % (ctx["branch"], ctx["year"], ctx["sheet"], key_tail),
        "deal_date": ddate.isoformat() if ddate else None, "city": city, "street": street,
        "side": norm_side(_cell(cells, fields, "side")), "agent": agent,
        "client_name": name, "client_phone": phone,
        "other_broker": _txt(_cell(cells, fields, "other_broker")),
        "deal_amount": amount, "commission_gross": _num_out(_cell(cells, fields, "commission_gross")),
        "commission_net": comm, "discount": _num_out(_cell(cells, fields, "discount")),
        "lead_source": _txt(_cell(cells, fields, "lead_source")),
        "paid_amount": _num_out(_cell(cells, fields, "paid_amount")),
        "deposited": _txt(_cell(cells, fields, "deposited")),
        "invoice_no": _txt(_cell(cells, fields, "invoice_no")),
        "receipt_no": _txt(_cell(cells, fields, "receipt_no")),
        "reported_date": rep.isoformat() if rep else None,
        "remax_approved": _txt(_cell(cells, fields, "remax_approved")),
        "collection_status": _txt(_cell(cells, fields, "collection_status")),
        "notes": _txt(_cell(cells, fields, "notes")),
        "lawyer_notes": _txt(_cell(cells, fields, "lawyer_notes")),
        "raw": raw,
    }
    return "ok", row


_AGENT_SPLIT = re.compile(r"\s*[+/\\]\s*")   # לא מפצלים על "ו" — שמות כמו "אלעד ויזמן"; צמדי "ו" הומרו ל-"+" במיפוי


def split_agents(name):
    """'אלי שמול + יהודית שמול' / 'רון/דודו' → רשימת שמות (עסקה משותפת, אייל 12/10)."""
    return [x.strip() for x in _AGENT_SPLIT.split(str(name or "")) if x.strip()]


def canon_agent(raw_name, branch, amap, canon):
    """שם גולמי מהקובץ → שם קנוני. מיפוי לפי amap ('branch|raw' → שם; '-' = לא סוכן), ואז canon()
    לכל חבר בעסקה משותפת בנפרד. משותפת נשמרת כ-'א + ב'."""
    nm = re.sub(r"\s+", " ", str(raw_name or "")).strip()
    mapped = (amap or {}).get("%s|%s" % (branch, nm), "")
    if mapped == "-":
        return ""
    names = [canon(x) or x for x in split_agents(mapped or nm)]
    return " + ".join(x for x in names if x)


# ── תצוגות לפי הרשאה ─────────────────────────────────────────────────────────
EDITOR_DROLES = ("manager", "developer", "accountant")
_GENERIC = ("מנהל", "סוכן")
DETAIL_FROM_YEAR = 2026   # אייל 12/10: פירוט עמלה/גבייה/דיווח רק מקובץ 2026; ההיסטוריה — לקוח/כתובת/סכום


def is_editor(s):
    return (s or {}).get("drole") in EDITOR_DROLES


def _dmy(iso):
    return "%s/%s/%s" % (iso[8:10], iso[5:7], iso[:4]) if iso else ""


def _addr(r):
    return ", ".join(x for x in (r.get("street") or "", r.get("city") or "") if x)


def _kind(side):
    return "השכרה" if any(w in (side or "") for w in ("שוכר", "משכיר")) else "מכירה"


def view_agent(r):
    d = {"id": r["id"], "date": _dmy(r.get("deal_date") or ""), "address": _addr(r), "side": r.get("side") or "",
         "client": r.get("client_name") or "", "price": r.get("deal_amount"), "branch": r.get("branch"),
         "year": r.get("year")}
    if (r.get("year") or 0) >= DETAIL_FROM_YEAR:
        rep = r.get("reported_date") or ""
        d.update(commission_net=r.get("commission_net"), paid=r.get("paid_amount"),
                 reported=("%s/%s" % (rep[5:7], rep[:4])) if rep else "")
    return d


def view_comps(r):
    return {"date": _dmy(r.get("deal_date") or ""), "address": _addr(r), "kind": _kind(r.get("side")),
            "side": r.get("side") or "", "price": r.get("deal_amount"), "agent": r.get("agent") or "",
            "branch": r.get("branch")}


_FULL = ("id", "branch", "year", "src_sheet", "src_serial", "deal_date", "city", "street", "side", "agent",
         "client_name", "client_phone", "other_broker", "deal_amount", "commission_gross", "commission_net",
         "discount", "lead_source", "paid_amount", "deposited", "invoice_no", "receipt_no", "reported_date",
         "remax_approved", "collection_status", "notes", "lawyer_notes", "missing_since")


def view_full(r):
    d = {k: r.get(k) for k in _FULL}
    d["date"] = _dmy(r.get("deal_date") or "")
    return d


def scope_rows(rows, s, canon_key):
    """s["keys"] = מפתחות קנוניים מותרים (הסוכן + שותפי הצוות / הסוכנים של המתאמת).
    עסקה משותפת ('א + ב') גלויה לכל אחד מחבריה. שם כללי ('מנהל') לא רואה כלום כאן."""
    keys = set((s or {}).get("keys") or set()) - {canon_key(g) for g in _GENERIC} - {""}
    if not keys:
        return []
    return [r for r in rows if any(canon_key(a) in keys for a in split_agents(r.get("agent", "")))]


def _sort_desc(rows):
    return sorted(rows, key=lambda r: (r.get("deal_date") or "", r.get("id") or ""), reverse=True)


def _norm_q(t):
    return normalize_header(t).lower()


def comps_search(rows, q, cap=200):
    toks = [t for t in _norm_q(q).split() if t]
    if not toks:
        return {"results": [], "n_sale": 0, "avg_sale": None, "n_rent": 0, "avg_rent": None}
    hit = [r for r in rows if all(t in _norm_q(" ".join((r.get("street") or "", r.get("city") or ""))) for t in toks)]
    hit = _sort_desc(hit)
    out = {"results": [view_comps(r) for r in hit[:cap]]}
    for kind, k in (("מכירה", "sale"), ("השכרה", "rent")):
        sel = [r for r in hit if _kind(r.get("side")) == kind]
        ps = [float(r["deal_amount"]) for r in sel if r.get("deal_amount")]
        out["n_" + k] = len(sel)
        out["avg_" + k] = int(round(sum(ps) / len(ps))) if ps else None
    return out


def _agg(rows):
    return {"n": len(rows), "commission": int(round(sum(float(r.get("commission_net") or 0) for r in rows)))}


def stats(rows, year):
    """עסקאות ועמלות לשנה. עסקה משותפת — חצי לכל סוכן (אייל 12/10: 'א'); הסה"כ לא משתנה."""
    cur = [r for r in rows if r.get("year") == year]
    prev = [r for r in rows if r.get("year") == year - 1]
    ag = {}
    for r in cur:
        names = split_agents(r.get("agent", "")) or [""]
        share = 1.0 / len(names)
        for a in names:
            x = ag.setdefault(a, {"agent": a, "n": 0.0, "commission": 0.0})
            x["n"] += share
            x["commission"] += float(r.get("commission_net") or 0) * share
    by_agent = sorted(({"agent": x["agent"], "n": round(x["n"], 2), "commission": int(round(x["commission"]))}
                       for x in ag.values()), key=lambda x: -x["commission"])
    br, months = {}, {}
    for r in cur:
        br.setdefault(r.get("branch") or "", []).append(r)
        m = (r.get("deal_date") or "")[5:7]
        if m:
            months.setdefault(m, []).append(r)
    return {"year": year, "total": _agg(cur), "prev": _agg(prev),
            "byBranch": sorted(({"branch": k, **_agg(v)} for k, v in br.items()), key=lambda x: -x["commission"]),
            "byAgent": by_agent, "byMonth": [{"month": m, **_agg(months[m])} for m in sorted(months)]}


def _detail(rows):
    return [r for r in rows if (r.get("year") or 0) >= DETAIL_FROM_YEAR]


def unpaid(rows):
    return sorted((r for r in _detail(rows) if not r.get("paid_amount")), key=lambda r: (r.get("deal_date") or "9999", r.get("id") or ""))


def unreported(rows):
    return sorted((r for r in _detail(rows) if not r.get("reported_date")), key=lambda r: (r.get("deal_date") or "9999", r.get("id") or ""))


def _rows(sb):
    if time.time() - _HIST_CACHE["ts"] < 120:
        return _HIST_CACHE["rows"]
    rows = sb.deal_history_all() if (sb and sb.enabled()) else []
    _HIST_CACHE.update(ts=time.time(), rows=rows)
    return rows


_HIST_CACHE = {"ts": 0, "rows": []}


def register(app, G, page):
    """ראוטי היסטוריית העסקאות + דף /v2/history. page = _page של effie_v2 (מזריק V2_BOOST)."""
    from flask import request, jsonify
    sb = G.get("_sbdb")
    key = (os.environ.get("DEALS_IMPORT_KEY") or "").strip()

    @app.route("/v2/api/deals/history/import", methods=["POST"])
    def v2_deals_history_import():
        """ייבוא מסקריפט מקומי (tools/import_deal_history.py) — מוגן במפתח, לא בסשן."""
        k = (request.headers.get("X-Import-Key") or "").strip()
        if not key or not k or not hmac.compare_digest(k, key):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        if not (sb and sb.enabled()):
            return jsonify({"ok": False, "reason": "no_db"}), 503
        b = request.get_json(silent=True) or {}
        amap = b.get("amap") or {}
        out, skipped = [], 0
        for r in (b.get("rows") or [])[:2000]:
            raw_agent = str(r.get("agent", "") or "")
            ag = canon_agent(raw_agent, r.get("branch", ""), amap, G["_canon_agent_name"])
            if not ag:
                skipped += 1
                continue
            x = dict(r)
            x["agent_raw"], x["agent"] = raw_agent, ag
            out.append(x)
        saved = sb.deal_history_upsert(out) if out else 0
        _HIST_CACHE["ts"] = 0
        G["_log_activity"]("ייבוא", "system", "", "היסטוריית עסקאות — ייבוא", "%d שורות" % saved)
        return jsonify({"ok": True, "saved": saved, "skipped_no_agent": skipped})

    def _auth():
        s = G["_web_auth"]()
        if not s:
            return None, (jsonify({"ok": False, "auth": False}), 401)
        return s, None

    def _keys(s):
        """הסוכן + שותפי הצוות (אייל 12/10) / הסוכנים של המתאמת — דרך _scope_keys_phones הקיים."""
        nm = (s.get("name") or "").strip()
        if s.get("role") != "coordinator" and nm in _GENERIC:
            return set()
        keys, _p, _m = G["_scope_keys_phones"](s.get("role", "agent"), nm, set(), s.get("agents"), s.get("agent_names"))
        return set(keys or set())

    def _editor():
        s, err = _auth()
        if err:
            return None, err
        if not is_editor(s):
            return None, (jsonify({"ok": False, "reason": "forbidden"}), 403)
        return s, None

    @app.route("/v2/api/deals/history/mine", methods=["GET"])
    def v2_deals_history_mine():
        s, err = _auth()
        if err:
            return err
        rows = scope_rows(_rows(sb), {"keys": _keys(s)}, G["_canon_key"])
        years = sorted({r.get("year") for r in rows if r.get("year")}, reverse=True)
        y = request.args.get("year", "")
        if y.isdigit():
            rows = [r for r in rows if r.get("year") == int(y)]
        res = [dict(view_agent(r), agent=r.get("agent") or "") for r in _sort_desc(rows)]
        return G["_etag_wrap"]({"ok": True, "results": res, "years": years, "n": len(rows)})

    @app.route("/v2/api/deals/history/comps", methods=["GET"])
    def v2_deals_history_comps():
        s, err = _auth()
        if err:
            return err
        return jsonify(dict(comps_search(_rows(sb), request.args.get("q", "")), ok=True))

    @app.route("/v2/api/deals/history/stats", methods=["GET"])
    def v2_deals_history_stats():
        s, err = _editor()
        if err:
            return err
        rows = _rows(sb)
        years = sorted({r.get("year") for r in rows if r.get("year")}, reverse=True)
        y = request.args.get("year", "")
        year = int(y) if y.isdigit() else (years[0] if years else time.localtime().tm_year)
        return G["_etag_wrap"](dict(stats(rows, year), ok=True, years=years))

    @app.route("/v2/api/deals/history/open", methods=["GET"])
    def v2_deals_history_open():
        s, err = _editor()
        if err:
            return err
        fn = unreported if request.args.get("kind") == "unreported" else unpaid
        return G["_etag_wrap"]({"ok": True, "results": [view_full(r) for r in fn(_rows(sb))], "since": DETAIL_FROM_YEAR})

    @app.route("/v2/api/deals/history/search", methods=["GET"])
    def v2_deals_history_search():
        s, err = _editor()
        if err:
            return err
        toks = [t for t in _norm_q(request.args.get("q", "")).split() if t]
        if not toks:
            return jsonify({"ok": True, "results": []})
        hits = [r for r in _rows(sb) if all(t in _norm_q(" ".join(str(r.get(k) or "") for k in
                ("client_name", "client_phone", "street", "city", "agent", "invoice_no", "receipt_no"))) for t in toks)]
        return jsonify({"ok": True, "results": [view_full(r) for r in _sort_desc(hits)[:200]]})
