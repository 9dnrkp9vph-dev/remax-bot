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
_TOTAL = re.compile(r'^(סה"כ|סה״כ|סיכום|total)\b', re.I)
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
    """העיר רק בסוף הכתובת — 'דרך עכו 119' / 'דרך חיפה 12' נשארים רחוב (ביקורת 12/10)."""
    a = normalize_header(addr)
    for c in CITIES:
        m = re.search(r"(?:^|[\s,])" + re.escape(c) + r"\s*$", a)
        if m:
            return c, re.sub(r"\s+", " ", a[:m.start()]).strip(" ,")
    return "", a


def normalize_row(cells, fields, ctx):
    """שורת אקסל → ('ok'|'skip'|'broken', row). row בעמודות הטבלה + src_key + raw (כל התאים כטקסט)."""
    cells = tuple(cells or ())
    if not any(c not in (None, "") and not (isinstance(c, str) and not c.strip()) for c in cells):
        return "skip", None
    agent = _txt(_cell(cells, fields, "agent"))
    if re.search(r'סה"כ|סה״כ|סיכום|total', agent, re.I):
        return "skip", None
    # שורת סה"כ/סיכום גם כשהמילה בעמודה אחרת (קרית ים: עמודת הסוכן ריקה — ביקורת 12/10)
    if any(isinstance(c, str) and len(c.strip()) <= 15 and _TOTAL.match(c.strip()) for c in cells):
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
        if ddate or amount is not None or street:   # נראית כמו עסקה בלי סוכן — לדוח, לא להיעלם בשקט
            return "broken", {"agent": "", "src_row": ctx["row_idx"], "sheet": ctx["sheet"]}
        return "skip", None   # שורות סיכום חודשיות / הערות — בלי סוכן ובלי פרטי עסקה
    if not ddate and amount is None and comm is None and not street:
        return "broken", {"agent": agent, "src_row": ctx["row_idx"], "sheet": ctx["sheet"]}
    name, phone = split_client(_cell(cells, fields, "client"))
    serial = _txt(_cell(cells, fields, "serial"))
    key_tail = serial if re.fullmatch(r"\d+", serial or "") else "r%d" % ctx["row_idx"]
    if ctx.get("key_mode") == "sync":
        # [ביקורת 2א] סנכרון 2026: בלי שם הגיליון (שינוי שם טאב לא משכפל), ובלי מס"ד — לפי תוכן (לא מיקום)
        if not re.fullmatch(r"\d+", serial or ""):
            sig = "|".join([ddate.isoformat() if ddate else "", street, norm_side(_cell(cells, fields, "side")), agent])
            key_tail = "h" + _hashlib.sha1(sig.encode()).hexdigest()[:10]
        src_key = "%s|%s|%s" % (ctx["branch"], ctx["year"], key_tail)
    else:
        src_key = "%s|%s|%s|%s" % (ctx["branch"], ctx["year"], ctx["sheet"], key_tail)
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
        "src_serial": serial, "src_key": src_key,
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


def open_workbook(data, pw):
    """bytes של xlsx/xlsm (מוצפן או לא) → Workbook read_only. סיסמה שגויה → חריגה."""
    import io, msoffcrypto, openpyxl
    bio = io.BytesIO(data)
    of = msoffcrypto.OfficeFile(io.BytesIO(data))
    if of.is_encrypted():
        out = io.BytesIO()
        of.load_key(password=pw or "")
        of.decrypt(out)
        bio = out
    bio.seek(0)
    return openpyxl.load_workbook(bio, read_only=True, data_only=True)


def pick_main_sheet(wb):
    for ws in wb.worksheets:
        hi, fields = find_header_row(list(ws.iter_rows(values_only=True, max_row=12)))
        if hi is not None and "agent" in fields and len([k for k in fields if not k.startswith("_")]) >= 6:
            return ws.title
    return None


def rows_from_workbook(wb, branch, year, sheets, default_agent="", stop_after_empty=300, key_mode=""):
    import collections
    rep = {"ok": 0, "skip": 0, "broken": 0, "agents": collections.Counter(), "commission": 0,
           "missing_sheets": [], "broken_rows": [], "dup_keys": [], "stopped_at": None}
    out, seen = [], set()
    names = [ws.title for ws in wb.worksheets]
    for sh in sheets:
        if sh not in names:
            rep["missing_sheets"].append(sh)
            continue
        it = wb[sh].iter_rows(values_only=True)
        head = []
        for r in it:
            head.append(r)
            if len(head) >= 12:
                break
        hi, fields = find_header_row(head)
        if hi is None:
            rep["missing_sheets"].append(sh)
            continue
        headers = [normalize_header(c) for c in head[hi]]
        def rows_iter():
            for k, r in enumerate(head[hi + 1:], start=hi + 2):
                yield k, r
            k = len(head) + 1
            for r in it:
                yield k, r
                k += 1
        empty = 0
        for i, cells in rows_iter():
            if not any(c not in (None, "") and not (isinstance(c, str) and not c.strip()) for c in (cells or ())):
                empty += 1
                if empty >= stop_after_empty:
                    rep["stopped_at"] = i   # קבצים עם מיליון שורות ריקות בסוף — לא קוראים את כולן
                    break
                continue
            empty = 0
            st, row = normalize_row(cells, fields, {"branch": branch, "year": year, "sheet": sh, "row_idx": i,
                                                    "headers": headers, "default_agent": default_agent,
                                                    "key_mode": key_mode})
            rep[st] += 1
            if st == "ok":
                if row["src_key"] in seen:
                    if row["src_key"] not in rep["dup_keys"]:
                        rep["dup_keys"].append(row["src_key"])
                    row["src_key"] = "%s|r%d" % (row["src_key"], i)
                seen.add(row["src_key"])
                out.append(row)
                rep["agents"][row["agent"]] += 1
                rep["commission"] += float(row.get("commission_net") or 0)
            elif st == "broken":
                rep["broken_rows"].append("%s שורה %d" % (sh, i))
    rep["agents"] = dict(rep["agents"])
    return out, rep


import hashlib as _hashlib, json as _json

_TRACK_NAME = re.compile(r"מעקב|עסקאות")


def pick_latest(entries):
    """אייל 12/10: בכל תיקייה — קובץ המעקב שנשמר אחרון (גם עותק כפול). קובץ בלי 'מעקב/עסקאות' בשם
    (קרית ים: '2026 קרית ים.xlsx') — רק כשאין בתיקייה קובץ מעקב בשם מפורש. 'גיבוי…' לא נבחר אם יש אחר."""
    xl = [e for e in (entries or []) if re.search(r"\.xls[xmb]?$", e.get("name", ""), re.I)
          and not e["name"].startswith("~$")]
    pool = [e for e in xl if _TRACK_NAME.search(e["name"]) and "גיבוי" not in e["name"]] \
        or [e for e in xl if "גיבוי" not in e["name"]] or xl
    return max(pool, key=lambda e: (e.get("server_modified") or "", e["name"])) if pool else None


def row_hash(row):
    core = {k: v for k, v in (row or {}).items() if k != "raw" and not k.startswith("_") and k != "src_hash"}
    return _hashlib.sha1(_json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def sync_plan(existing, incoming, switched):
    ex = {r["src_key"]: r for r in existing or []}
    seen = set()
    up = []
    for r in incoming or []:
        h = row_hash(r)
        seen.add(r["src_key"])
        old = ex.get(r["src_key"])
        if not old or old.get("src_hash") != h or old.get("missing_since"):
            up.append(dict(r, src_hash=h))
    missing = [k for k, r in ex.items() if k not in seen and not r.get("missing_since")]
    back = [k for k, r in ex.items() if k in seen and r.get("missing_since")]
    # [ביקורת 2א] ההגנה לא תלויה בזיכרון (אחרי אתחול/מעבר קובץ): קובץ שמכיל פחות מ-60% מהשורות הפעילות
    # שכבר בטבלה — לא מסמנים חסרים (עותק כפול חלקי / גיליון שהוחלף). סניף קטן (<5) — בלי הגנה.
    act = {k for k, r in ex.items() if not r.get("missing_since")}
    guarded = False
    if (switched or len(act) >= 5) and act and len(seen & act) < 0.6 * len(act):
        missing, guarded = [], True
    return {"upsert": up, "missing": sorted(missing), "back": sorted(back), "guarded": guarded}


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


# ── [DEALS-AREA 12/10] חיפוש לפי שכונה ("איזה עסקאות היו באפקה", אייל) — "המוח" של חיפוש הנכסים:
# כינויי שכונות מ-_nb_alias_index(_CITY_NB_MAP_HE), ורחוב → שכונה לפי נכסי המשרד ונכס נולד (2+ עדויות) ──
def _city_n(c):
    return re.sub(r"\s+", " ", str(c or "").replace("קריית", "קרית")).strip()


def _sk(st):
    return re.sub(r"\s*\d.*$", "", _city_n(st)).strip()


def _alias_map(idx):
    m = {}
    for cn, e in ((idx or {}).get("nb") or {}).items():
        for a in list(e.get("aliases") or []) + [cn]:
            m[_city_n(a)] = cn
    return m


def _city_canon(c, idx):
    """'ביאליק' / 'ק. ביאליק' / 'קריית ביאליק' → 'קרית ביאליק' (לפי מפת הערים של חיפוש הנכסים).
    [12/10 חי] בקבצי העסקאות העיר כתובה בקיצור — בלי זה אף עסקה לא נמצאה לפי שכונה."""
    n = _city_n(re.sub(r"^ק\s*\.\s*", "קרית ", str(c or "").strip()))
    for cand in (n, "קרית " + n):   # 'ים' → 'קרית ים'
        for canon, aliases in ((idx or {}).get("city") or {}).items():
            if cand == _city_n(canon) or cand in {_city_n(a) for a in aliases or ()}:
                return _city_n(canon)
    return n


def nb_street_index(street_rows, idx):
    """[(רחוב, שכונה, עיר)] → {"sc": {(רחוב, עיר): שכונה}, "s": {רחוב: שכונה}} — רק עם 2+ עדויות.
    "s" = רחוב שכל העדויות שלו בשכונה אחת (לעסקה בלי עיר)."""
    import collections
    am = _alias_map(idx)
    votes = collections.defaultdict(collections.Counter)
    for st, nb, city in street_rows or []:
        sk, nbn = _sk(st), _city_n(nb)
        if len(sk) >= 2 and nbn:
            votes[(sk, _city_canon(city, idx))][am.get(nbn, nbn)] += 1
    sc, by_st = {}, collections.defaultdict(set)
    for k, cnt in votes.items():
        top, c = cnt.most_common(1)[0]
        if c >= 2:
            sc[k] = top
            by_st[k[0]].add(top)
    return {"sc": sc, "s": {st: list(v)[0] for st, v in by_st.items() if len(v) == 1}}


def find_area(q, idx):
    """מילים בחיפוש → שכונה (כינוי חד-משמעי, 3+ תווים; תחילית ב/ה/ל/מ מותרת). אחרת None."""
    am = _alias_map(idx)
    amb = {_city_n(a) for a in ((idx or {}).get("ambiguous") or ())}
    toks = _city_n(q).split()
    for size in (3, 2, 1):
        for i in range(len(toks) - size + 1):
            ph = " ".join(toks[i:i + size])
            for cand in (ph, ph[1:] if ph[:1] in "בהלמ" else None):
                if cand and len(cand) >= 3 and cand in am and cand not in amb:
                    cn = am[cand]
                    city = ((idx.get("nb") or {}).get(cn) or {}).get("city", "")
                    return {"nb": cn, "city": city, "label": cn + (" · " + city if city else "")}
    return None


def comps_search(rows, q, cap=200, area_ctx=None):
    toks = [t for t in _norm_q(q).split() if t]
    if not toks:
        return {"results": [], "n_sale": 0, "avg_sale": None, "n_rent": 0, "avg_rent": None}
    area = find_area(q, area_ctx.get("idx")) if area_ctx else None
    if area:
        si = area_ctx.get("streets") or {}
        sc, s1, idx = si.get("sc") or {}, si.get("s") or {}, area_ctx.get("idx")

        def _nb_of(r):
            sk, city = _sk(r.get("street")), _city_canon(r.get("city"), idx)
            return sc.get((sk, city)) if city else s1.get(sk)
        hit = [r for r in rows if _nb_of(r) == area["nb"]]
    else:
        hit = [r for r in rows if all(t in _norm_q(" ".join((r.get("street") or "", r.get("city") or ""))) for t in toks)]
    hit = _sort_desc(hit)
    out = {"results": [view_comps(r) for r in hit[:cap]]}
    if area:
        out["area"] = area["label"]
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


def active_rows(rows):
    """[ביקורת 2א] שורות שנעלמו מהאקסל (missing_since) לא נספרות בדוחות/רשימות/השוואה — רק ב'לבדיקה' ובחיפוש."""
    return [r for r in rows if not r.get("missing_since")]


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


V2_HISTORY_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>היסטוריית עסקאות</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;color:#1E3A5F;min-height:100vh}
  header{display:flex;align-items:center;gap:10px;padding:calc(env(safe-area-inset-top,0px) + 10px) 16px 6px}
  header .bk{width:44px;height:44px;border-radius:14px;background:#fff;border:1px solid #E9E4D8;display:flex;align-items:center;justify-content:center;cursor:pointer}
  header h1{font-size:19px;font-weight:800;flex:1}
  main{max-width:640px;margin:0 auto;padding:4px 16px 40px;display:flex;flex-direction:column;gap:12px}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px;overflow-x:auto;scrollbar-width:none}
  .segs::-webkit-scrollbar{display:none}
  .segs .sg{flex:1 0 auto;text-align:center;padding:9px 12px;min-height:40px;font-size:12.5px;font-weight:700;color:#5B6472;border-radius:10px;cursor:pointer;white-space:nowrap}
  .segs .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  #list{display:flex;flex-direction:column;gap:10px}
  .card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:14px 16px}
  .row1{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
  .ad{font-weight:800;font-size:15px}.sb{font-size:12.5px;color:#6B7280;margin-top:2px}
  .pr{font-weight:800;font-size:15px;white-space:nowrap}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .chip{font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;background:#F2EFE7;color:#5B6472}
  .chip.ok{background:#EAF5EE;color:#157A43}.chip.wait{background:#F6EEDB;color:#7A5E1C}
  .sum{display:flex;gap:10px}.sum .card{flex:1;text-align:center}.sum b{display:block;font-size:20px;font-weight:800}
  .sum span{font-size:12px;color:#6B7280}
  input.q{width:100%;font-size:16px;font-family:inherit;padding:12px 14px;border:1.5px solid #DCD6C8;border-radius:14px;background:#fff;color:#1E3A5F;outline:none}
  select.yr{font-size:16px;font-family:inherit;padding:10px 12px;border:1.5px solid #DCD6C8;border-radius:13px;background:#fff;color:#1E3A5F;min-height:44px}
  table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:7px 4px;border-bottom:1px solid #F0EDE3;text-align:right}
  th{color:#6B7280;font-weight:700}
  .empty{text-align:center;padding:36px 16px}.empty .c{width:62px;height:62px;border-radius:50%;background:#F6EEDB;margin:0 auto 12px;display:flex;align-items:center;justify-content:center}
  .empty .t{font-weight:800;font-size:17px}.empty .s{color:#6B7280;margin-top:6px;font-size:13.5px}
</style></head><body>
<header>
  <div class="bk" onclick="history.length > 1 ? history.back() : location.href='/v2/home'" aria-label="חזרה">
    <svg width="16" height="16" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
  <h1>היסטוריית עסקאות</h1>
</header>
<main>
  <div class="segs" id="tabs"></div>
  <div id="tools"></div>
  <div id="list"><div class="sb" style="text-align:center;padding:20px 0">טוען…</div></div>
</main>
<div id="toast"></div>
<script>
var TOK = '', ED = false, TAB = '', YEAR = '', Q = '', ME = '';
var BR = {bialik: 'ביאליק', motzkin: 'מוצקין', kiryat_yam: 'קרית ים'};
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function fmtP(p){ if (p == null || p === '') return ''; var n = Math.round(Number(p)); if (isNaN(n)) return ''; return '₪' + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function emptyHtml(t, s){ return '<div class="empty"><div class="c"><svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 11l8-7 8 7v9H4z" fill="none" stroke="#C29435" stroke-width="2" stroke-linejoin="round"/></svg></div><div class="t">' + esc(t) + '</div><div class="s">' + esc(s) + '</div></div>'; }
function agentCard(x, me){
  // היסטוריה (עד 2025): תאריך/כתובת/לקוח/סכום. 2026: גם עמלה/שולם/דווח (אייל 12/10)
  var ag = String(x.agent || ''), joint = ag.indexOf(' + ') >= 0;
  var others = joint ? ag.split(' + ').filter(function(a){ return a.trim() !== String(me || '').trim(); }) : [];
  var det = Object.prototype.hasOwnProperty.call(x, 'commission_net');
  return '<div class="card"><div class="row1"><div><div class="ad">' + esc(x.address || '—') + '</div>' +
    '<div class="sb">' + esc([x.date, x.side, x.client].filter(Boolean).join(' · ')) + '</div>' +
    (joint ? '<div class="sb">עסקה משותפת' + (others.length ? ' עם ' + esc(others.join(', ')) : '') + '</div>' :
      (me && ag && ag !== me ? '<div class="sb">' + esc(ag) + '</div>' : '')) + '</div>' +
    '<div class="pr">' + esc(fmtP(x.price)) + '</div></div>' +
    (det ? '<div class="chips"><span class="chip">עמלה ' + esc(fmtP(x.commission_net) || '—') + '</span>' +
      (x.paid ? '<span class="chip ok">שולם ' + esc(fmtP(x.paid)) + '</span>' : '<span class="chip wait">טרם שולם</span>') +
      (x.reported ? '<span class="chip ok">דווח ' + esc(x.reported) + '</span>' : '<span class="chip wait">לא דווח</span>') + '</div>' : '') +
    '</div>';
}
function compCard(x){
  return '<div class="card"><div class="row1"><div><div class="ad">' + esc(x.address || '—') + '</div>' +
    '<div class="sb">' + esc([x.date, x.kind, x.agent].filter(Boolean).join(' · ')) + '</div></div>' +
    '<div class="pr">' + esc(fmtP(x.price)) + '</div></div></div>';
}
function openCard(x){
  var addr = [x.street, x.city].filter(Boolean).join(', ');
  return '<div class="card"><div class="row1"><div><div class="ad">' + esc(addr || '—') + '</div>' +
    '<div class="sb">' + esc([x.date, x.side, x.agent, BR[x.branch]].filter(Boolean).join(' · ')) + '</div>' +
    '<div class="sb">' + esc([x.client_name, x.client_phone].filter(Boolean).join(' · ')) + '</div></div>' +
    '<div class="pr">' + esc(fmtP(x.commission_net)) + '</div></div>' +
    '<div class="chips">' + ((x.year || 0) < 2026 ? '' :
    (x.paid_amount ? '<span class="chip ok">שולם ' + esc(fmtP(x.paid_amount)) + '</span>' : '<span class="chip wait">טרם שולם</span>') +
    (x.reported_date ? '<span class="chip ok">דווח ' + esc(x.reported_date.slice(5, 7) + '/' + x.reported_date.slice(0, 4)) + '</span>' : '<span class="chip wait">לא דווח</span>')) +
    (x.collection_status ? '<span class="chip">' + esc(x.collection_status) + '</span>' : '') +
    (x.invoice_no ? '<span class="chip">חשבונית ' + esc(x.invoice_no) + '</span>' : '') +
    (x.receipt_no ? '<span class="chip">קבלה ' + esc(x.receipt_no) + '</span>' : '') + '</div></div>';
}
function statsHtml(j){
  var t = j.total || {}, p = j.prev || {};
  var tbl = function(title, rows, key, lbl){
    if (!rows || !rows.length) return '';
    return '<div class="card"><div class="ad" style="margin-bottom:6px">' + title + '</div><table><tr><th>' + lbl + '</th><th>עסקאות</th><th>עמלה</th></tr>' +
      rows.map(function(r){ return '<tr><td>' + esc(key(r)) + '</td><td>' + r.n + '</td><td>' + esc(fmtP(r.commission)) + '</td></tr>'; }).join('') + '</table></div>';
  };
  return '<div class="sum"><div class="card"><b>' + (t.n || 0) + '</b><span>עסקאות ' + j.year + '</span></div>' +
    '<div class="card"><b>' + esc(fmtP(t.commission || 0)) + '</b><span>עמלה לפני מע"מ</span></div></div>' +
    '<div class="sb" style="text-align:center">' + (j.year - 1) + ': ' + (p.n || 0) + ' עסקאות · ' + esc(fmtP(p.commission || 0)) + '</div>' +
    tbl('לפי משרד', j.byBranch, function(r){ return BR[r.branch] || r.branch; }, 'משרד') +
    tbl('לפי סוכן', j.byAgent, function(r){ return r.agent; }, 'סוכן') +
    tbl('לפי חודש', j.byMonth, function(r){ return r.month; }, 'חודש');
}
function agoTx(iso){ var m = Math.round((Date.now() - Date.parse(iso || 0)) / 60000); return isNaN(m) ? '' : (m < 1 ? 'עכשיו' : 'לפני ' + m + ' דק\''); }
function syncLine(j){
  if (!j || !j.enabled) return '<div class="sb">סנכרון קבצי השנה כבוי</div>';
  if (!j.configured) return '<div class="sb" style="color:#C24040">סנכרון: חסרים מפתחות Dropbox</div>';
  var b = j.branches || {};
  return '<div class="sb">' + ['bialik', 'motzkin', 'kiryat_yam'].filter(function(k){ return b[k]; }).map(function(k){
    var s = b[k];
    return esc(BR[k]) + ': ' + (s.error ? '<span style="color:#C24040">' + esc(s.error) + '</span>' : 'עודכן ' + esc(agoTx(s.ts)));
  }).join(' · ') + '</div>';
}
function reviewHtml(j){
  var m = (j && j.missing) || [], u = (j && j.unmapped) || [];
  if (!m.length && !u.length) return emptyHtml('אין מה לבדוק', 'שורות שנעלמו מקבצי השנה ושמות סוכנים חדשים יופיעו כאן');
  var h = '';
  if (m.length) h += '<div class="ad">נעלמו מהאקסל · ' + m.length + '</div>' + m.map(openCard).join('');
  if (u.length) h += '<div class="card"><div class="ad">שמות סוכנים בלי מיפוי</div><div class="sb">שלח את השמות למיפוי — עד אז הם לא מקושרים לסוכן באפליקציה</div>' +
    u.map(function(x){ return '<div class="sb">' + esc(BR[x.branch] || x.branch) + ' · ' + esc(x.name) + '</div>'; }).join('') + '</div>';
  return h;
}
function GET(u){ return fetch(u, {headers: {'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function setTab(t){ TAB = t; try{ localStorage.setItem('v2st:hist', t); }catch(e){} draw(); }
function tabsFor(){
  return ED ? [['stats', 'דוחות'], ['unpaid', 'לא שולם'], ['unrep', 'לא דווח'], ['review', 'לבדיקה'], ['search', 'חיפוש'], ['comps', 'מחירי השוואה']]
            : [['mine', 'העסקאות שלי'], ['comps', 'מחירי השוואה']];
}
function draw(){
  var tb = tabsFor();
  if (!tb.some(function(x){ return x[0] === TAB; })) TAB = tb[0][0];
  document.getElementById('tabs').innerHTML = tb.map(function(x){
    return '<div class="sg' + (x[0] === TAB ? ' on' : '') + '" onclick="setTab(\'' + x[0] + '\')">' + x[1] + '</div>'; }).join('');
  var tools = document.getElementById('tools'), list = document.getElementById('list');
  list.innerHTML = '<div class="sb" style="text-align:center;padding:20px 0">טוען…</div>';
  if (TAB === 'comps' || TAB === 'search'){
    tools.innerHTML = '<input class="q" id="q" type="search" enterkeyhint="search" placeholder="' +
      (TAB === 'comps' ? 'רחוב או שכונה — למשל "אפקה" או "הגפן מוצקין"' : 'שם לקוח, טלפון, כתובת, סוכן או מספר חשבונית') + '" value="' + esc(Q) + '">';
    var q = document.getElementById('q');
    q.onkeydown = function(e){ if (e.key === 'Enter'){ Q = q.value.trim(); runQ(); } };
    q.onchange = function(){ Q = q.value.trim(); runQ(); };
    runQ(); return;
  }
  tools.innerHTML = '';
  if (TAB === 'mine'){
    GET('/v2/api/deals/history/mine' + (YEAR ? '?year=' + YEAR : '')).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'נסה שוב בעוד רגע'); return; }
      tools.innerHTML = '<div style="display:flex;gap:8px;align-items:center"><select class="yr" onchange="YEAR=this.value;draw()"><option value="">כל השנים</option>' +
        (j.years || []).map(function(y){ return '<option' + (String(y) === String(YEAR) ? ' selected' : '') + '>' + y + '</option>'; }).join('') +
        '</select><div class="sb">' + j.n + ' עסקאות</div></div>';
      list.innerHTML = j.results.length ? j.results.map(function(x){ return agentCard(x, ME); }).join('') :
        emptyHtml('עוד אין עסקאות כאן', 'העסקאות שסגרת במשרד יופיעו כאן');
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else if (TAB === 'stats'){
    GET('/v2/api/deals/history/stats' + (YEAR ? '?year=' + YEAR : '')).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'הדוחות זמינים למנהלים ולהנהלת חשבונות'); return; }
      tools.innerHTML = '<select class="yr" onchange="YEAR=this.value;draw()">' + (j.years || []).map(function(y){
        return '<option' + (String(y) === String(j.year) ? ' selected' : '') + '>' + y + '</option>'; }).join('') + '</select>';
      list.innerHTML = statsHtml(j);
      GET('/v2/api/deals/history/sync').then(function(sy){ tools.insertAdjacentHTML('beforeend', syncLine(sy)); }).catch(function(){});
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else if (TAB === 'review'){
    GET('/v2/api/deals/history/review').then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'זמין למנהלים ולהנהלת חשבונות'); return; }
      list.innerHTML = reviewHtml(j);
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else {
    var kind = TAB === 'unpaid' ? 'unpaid' : 'unreported';
    GET('/v2/api/deals/history/open?kind=' + kind).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'זמין למנהלים ולהנהלת חשבונות'); return; }
      tools.innerHTML = j.results.length ? '<div class="sb">' + j.results.length + ' צדדים ב-' + j.since + ' והלאה, מהישן לחדש</div>' : '';
      list.innerHTML = j.results.length ? j.results.map(openCard).join('') :
        emptyHtml(kind === 'unpaid' ? 'אין כרגע מה לגבות' : 'אין כרגע מה לדווח', 'הרשימה מתמלאת מקבצי המעקב של ' + j.since + ' — אחרי חיבור הקבצים לאפי');
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  }
}
function runQ(){
  var list = document.getElementById('list');
  if (!Q){ list.innerHTML = emptyHtml(TAB === 'comps' ? 'מחירי השוואה' : 'חיפוש עסקה', TAB === 'comps' ? 'הקלד רחוב או שכונה (למשל אפקה) וראה מה נמכר שם ובכמה' : 'הקלד שם, טלפון או כתובת'); return; }
  var u = TAB === 'comps' ? '/v2/api/deals/history/comps?q=' : '/v2/api/deals/history/search?q=';
  GET(u + encodeURIComponent(Q)).then(function(j){
    if (!j || !j.ok){ list.innerHTML = emptyHtml('לא ניתן לחפש', 'נסה שוב'); return; }
    var head = TAB === 'comps' ? (j.area ? '<div class="sb">שכונת ' + esc(j.area) + '</div>' : '') + '<div class="sum"><div class="card"><b>' + j.n_sale + '</b><span>מכירות · ממוצע ' + esc(fmtP(j.avg_sale) || '—') + '</span></div>' +
      '<div class="card"><b>' + j.n_rent + '</b><span>השכרות · ממוצע ' + esc(fmtP(j.avg_rent) || '—') + '</span></div></div>' : '';
    list.innerHTML = j.results.length ? head + j.results.map(TAB === 'comps' ? compCard : openCard).join('') :
      emptyHtml('לא נמצא', 'אין עסקאות עבור "' + Q + '" — נסה מילה אחרת');
  }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לחפש', 'בדוק חיבור ונסה שוב'); });
}
(function(){
  try{ TOK = localStorage.getItem('fbTok') || ''; TAB = localStorage.getItem('v2st:hist') || ''; }catch(e){}
  if (!TOK){ location.href = '/v2'; return; }
  GET('/api/auth/whoami').then(function(j){
    if (!j || !j.ok){ location.replace('/v2'); return; }
    ED = ['manager', 'developer', 'accountant'].indexOf(j.drole) >= 0; ME = j.name || '';
    draw();
  }).catch(function(){ location.replace('/v2'); });
})();
</script></body></html>'''


_HIST_CACHE = {"ts": 0, "rows": []}


import threading as _threading

BRANCH_PW = {"bialik": "DEALS_PW_BIALIK", "motzkin": "DEALS_PW_MOTZKIN_YAM", "kiryat_yam": "DEALS_PW_MOTZKIN_YAM"}
DEFAULT_AGENT = {"kiryat_yam": "קובי חמו"}
_DIRS = {"bialik": "/הפרלמנט/אייל/מעקב עסקאות/{y}", "motzkin": "/הפרלמנט/אוהד/מעקב עסקאות מוצקין/{y}",
         "kiryat_yam": "/הפרלמנט/מעקב עסקאות קרית ים/{y}"}
_AGENT_MAP_CACHE = {}
SYNC_STATE = {}
_SYNC_THREAD = [None]
_SYNC_LOCK = _threading.Lock()


def SYNC_DIRS(year):
    return {b: (os.environ.get("DEALS_DIR_" + b.upper()) or p).format(y=year) for b, p in _DIRS.items()}


def load_agent_map():
    if _AGENT_MAP_CACHE.get("ts", 0) > time.time() - 600 and "m" in _AGENT_MAP_CACHE:
        return _AGENT_MAP_CACHE["m"]
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "deals_agent_map.json")
        m = _json.load(open(p, encoding="utf-8"))
    except Exception:
        m = {}
    _AGENT_MAP_CACHE.update(m=m, ts=time.time())
    return m


def sync_branch(branch, year, sb, dbx, canon, now_iso, folder=None, pw=None, last=None, push=None):
    """קובץ אחד → הטבלה. כל כשל = מצב עם שגיאה, בלי לגעת בטבלה (מקור האמת לא נפגע)."""
    st = {"file": "", "rev": "", "rows": 0, "upserted": 0, "missing": 0, "back": 0, "guarded": False,
          "unmapped": [], "error": "", "ts": now_iso, "switched": False}
    last = last or {}
    try:
        folder = folder or SYNC_DIRS(year)[branch]
        e = pick_latest(dbx.list_folder(folder))
        if not e:
            st["error"] = "אין קובץ מעקב בתיקייה"
            return st
        st.update(file=e["name"], rev=e["rev"], path=e["path"])
        st["switched"] = bool(last.get("path")) and last.get("path") != e["path"]
        if not st["switched"] and last.get("rev") == e["rev"] and not last.get("error"):
            st.update(skipped=True, rows=last.get("rows", 0), unmapped=last.get("unmapped", []))
            return st
        data, _rev = dbx.download(e["path"])
        wb = open_workbook(data, pw if pw is not None else os.environ.get(BRANCH_PW[branch], ""))
        sh = pick_main_sheet(wb)
        if not sh:
            st["error"] = "לא נמצא גיליון עסקאות בקובץ"
            return st
        rows, rep = rows_from_workbook(wb, branch, year, [sh], DEFAULT_AGENT.get(branch, ""), key_mode="sync")
        amap = load_agent_map()
        unm = set()
        for r in rows:
            raw = r["agent"]
            r["agent_raw"] = raw
            r["agent"] = canon_agent(raw, branch, amap, canon) or raw
            r["src_path"] = e["path"]
            if "%s|%s" % (branch, raw) not in amap and raw != DEFAULT_AGENT.get(branch):
                unm.add(raw)
        existing = [x for x in sb.deal_history_all() if x.get("branch") == branch and x.get("year") == year]
        plan = sync_plan(existing, rows, st["switched"])
        if plan["upsert"]:
            sb.deal_history_upsert(plan["upsert"])
        if plan["missing"]:
            sb.deal_history_set_missing(plan["missing"], now_iso)
        if plan["back"]:
            sb.deal_history_set_missing(plan["back"], None)
        st.update(rows=len(rows), upserted=len(plan["upsert"]), missing=len(plan["missing"]),
                  back=len(plan["back"]), guarded=plan["guarded"], unmapped=sorted(unm), sheet=sh)
        if st["switched"] and push:
            push("מעקב עסקאות — הקובץ הפעיל התחלף", "%s: עכשיו נקרא %s" % (BRANCHES[branch], e["name"]))
        _HIST_CACHE["ts"] = 0
    except Exception as ex:
        st["error"] = "%s: %s" % (type(ex).__name__, str(ex)[:160])
    return st


def sync_tick(sb, dbx, canon, push=None, log=None):
    year = int(os.environ.get("DEALS_SYNC_YEAR") or _dt.date.today().year)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    for b in BRANCHES:
        prev = SYNC_STATE.get(b)
        st = sync_branch(b, year, sb, dbx, canon, now, last=prev, push=push)
        SYNC_STATE[b] = st
        if st["error"] and log and (not prev or prev.get("error") != st["error"]):
            log.warning("deals sync %s: %s" % (b, st["error"]))


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
        rows = scope_rows(active_rows(_rows(sb)), {"keys": _keys(s)}, G["_canon_key"])
        years = sorted({r.get("year") for r in rows if r.get("year")}, reverse=True)
        y = request.args.get("year", "")
        if y.isdigit():
            rows = [r for r in rows if r.get("year") == int(y)]
        res = [dict(view_agent(r), agent=r.get("agent") or "") for r in _sort_desc(rows)]
        return G["_etag_wrap"]({"ok": True, "results": res, "years": years, "n": len(rows)})

    _AREA = {"ts": 0, "v": None}

    def _area_ctx():
        """מפת הכינויים + רחוב→שכונה (מטמון שעה). כשל → חיפוש רחוב רגיל."""
        if _AREA["v"] is not None and time.time() - _AREA["ts"] < 3600:
            return _AREA["v"]
        try:
            idx = G["_nb_alias_idx"]()
            v = {"idx": idx, "streets": nb_street_index(G["_street_nb_rows"](), idx)}
        except Exception:
            v = None
        _AREA.update(ts=time.time(), v=v)
        return v

    @app.route("/v2/api/deals/history/comps", methods=["GET"])
    def v2_deals_history_comps():
        s, err = _auth()
        if err:
            return err
        return jsonify(dict(comps_search(active_rows(_rows(sb)), request.args.get("q", ""), area_ctx=_area_ctx()), ok=True))

    @app.route("/v2/api/deals/history/stats", methods=["GET"])
    def v2_deals_history_stats():
        s, err = _editor()
        if err:
            return err
        rows = active_rows(_rows(sb))
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
        return G["_etag_wrap"]({"ok": True, "results": [view_full(r) for r in fn(active_rows(_rows(sb)))], "since": DETAIL_FROM_YEAR})

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

    @app.route("/v2/history", methods=["GET"])
    def v2_history_page():
        return page(V2_HISTORY_HTML)
    import dropbox_api as _dbx

    def _sync_loop():
        while True:
            try:
                sync_tick(sb, _dbx, G["_canon_agent_name"], push=G.get("send_push"), log=G.get("log"))
            except Exception as e:
                SYNC_STATE["_loop"] = {"error": str(e)[:160]}
            time.sleep(300)

    @app.before_request
    def _deals_sync_ensure():
        if (os.environ.get("DEALS_SYNC") or "") != "1" or not _dbx.configured():
            return None
        with _SYNC_LOCK:
            th = _SYNC_THREAD[0]
            if th is None or not th.is_alive():
                _SYNC_THREAD[0] = _threading.Thread(target=_sync_loop, daemon=True, name="deals-sync")
                _SYNC_THREAD[0].start()
        return None

    @app.route("/v2/api/deals/history/sync", methods=["GET"])
    def v2_deals_history_sync():
        s, err = _editor()
        if err:
            return err
        th = _SYNC_THREAD[0]
        return jsonify({"ok": True, "enabled": (os.environ.get("DEALS_SYNC") or "") == "1",
                        "configured": _dbx.configured(), "alive": bool(th and th.is_alive()),
                        "year": int(os.environ.get("DEALS_SYNC_YEAR") or _dt.date.today().year),
                        "branches": {k: v for k, v in SYNC_STATE.items()}})

    @app.route("/v2/api/deals/history/review", methods=["GET"])
    def v2_deals_history_review():
        s, err = _editor()
        if err:
            return err
        miss = [view_full(r) for r in _rows(sb) if r.get("missing_since")]
        unm = [{"branch": b, "name": nm} for b, st in SYNC_STATE.items() if isinstance(st, dict)
               for nm in (st.get("unmapped") or [])]
        return jsonify({"ok": True, "missing": miss, "unmapped": unm})
