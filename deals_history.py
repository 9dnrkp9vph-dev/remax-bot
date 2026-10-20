# deals_history.py
"""[DEALS-HISTORY 12/10] היסטוריית עסקאות — נרמול שורות מקבצי 'מעקב עסקאות', תצוגות לפי הרשאה,
סטטיסטיקה, ראוטים ודף /v2/history. ספק: docs/superpowers/specs/2026-10-12-deals-history-design.md"""
import os
import re
import time
import hmac
import datetime as _dt
try:
    from tools.osm_street_nb import street_key as _osm_street_key, norm as _osm_norm
except Exception:   # בלי tools/ (סביבה חלקית) — מפתח רחוב בסיסי
    def _osm_norm(s):
        return re.sub(r"\s+", " ", str(s or "").replace("קריית", "קרית")).strip()

    def _osm_street_key(st):
        return re.sub(r"\s*\d.*$", "", _osm_norm(st)).strip()

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
    ("client_phone", ["נייד לקוח", "טלפון לקוח", "טל לקוח", "נייד", "טלפון"]),   # עמודה נפרדת (ביאליק 2026 — אייל 12/10)
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


_STATUS_FIELDS = ("paid_amount", "deposited", "reported_date")


def fill_class_rgb(rgb):
    """צבע רקע → 'green'/'red'/'yellow'/''. בקבצים: ירוק C6EFCE = בוצע, ורוד FFC7CE = לא, צהוב FFEB9C = בטיפול (אייל 12/10)."""
    h = re.sub(r"[^0-9A-Fa-f]", "", str(rgb or ""))[-6:]
    if len(h) != 6 or h.upper() in ("000000", "FFFFFF"):
        return ""
    r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)
    if g > r + 15 and g >= b:
        return "green"
    if r > 200 and g > 200 and b < 190:
        return "yellow"
    if r > g + 15 and r > b:
        return "red"
    return ""


def cell_fill_class(cell):
    try:
        f = cell.fill
        if not f or f.fill_type in (None, "none"):
            return ""
        c = f.fgColor
        return fill_class_rgb(c.rgb) if c is not None and c.type == "rgb" else ""
    except Exception:
        return ""


def phone_cell(v):
    """תא טלפון → '05XXXXXXXX'. אקסל שומר נייד כמספר בלי 0 (546334989 / 546334989.0); +972 → 0."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    d = re.sub(r"\D", "", str(v or ""))
    if d.startswith("972"):
        d = d[3:]
    if len(d) == 9 and d[0] in "23456789":
        d = "0" + d
    return d if 9 <= len(d) <= 10 else ""


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
    if not agent and ctx.get("default_agent") and (ddate or street):
        # רק שורה עם תאריך/רחוב. שורת סכום בלי תווית (רק מספרים) נספרה כעסקה של קובי (אייל 12/10)
        agent = ctx["default_agent"]   # קרית ים: עמודת הסוכן ריקה — כל העסקאות של קובי חמו (אייל 12/10)
    if not agent and ctx.get("default_agent") and not (ddate or street):
        return "skip", None   # קרית ים: שורת סכום/סיכום — מספרים בלי תאריך ובלי כתובת
    if not agent:
        if ddate or amount is not None or street:   # נראית כמו עסקה בלי סוכן — לדוח, לא להיעלם בשקט
            return "broken", {"agent": "", "src_row": ctx["row_idx"], "sheet": ctx["sheet"]}
        return "skip", None   # שורות סיכום חודשיות / הערות — בלי סוכן ובלי פרטי עסקה
    if not ddate and amount is None and comm is None and not street:
        return "broken", {"agent": agent, "src_row": ctx["row_idx"], "sheet": ctx["sheet"]}
    name, phone = split_client(_cell(cells, fields, "client"))
    phone = phone_cell(_cell(cells, fields, "client_phone")) or phone
    # [אייל 12/10] תשלום/הפקדה/דיווח מסומנים בצבע התא: ירוק = בוצע (גם כשהתא ריק); מספר בתא גובר
    fills = {k: v for k, v in (ctx.get("fills") or {}).items() if v}
    paid = _num_out(_cell(cells, fields, "paid_amount"))
    if paid is None and fills.get("paid_amount") == "green":
        paid = _num_out(_cell(cells, fields, "commission_gross")) or comm
    dep = _txt(_cell(cells, fields, "deposited")) or ("כן" if fills.get("deposited") == "green" else "")
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
        "paid_amount": paid,
        "deposited": dep,
        "invoice_no": _txt(_cell(cells, fields, "invoice_no")),
        "receipt_no": _txt(_cell(cells, fields, "receipt_no")),
        "reported_date": rep.isoformat() if rep else None,
        "remax_approved": _txt(_cell(cells, fields, "remax_approved")),
        "collection_status": _txt(_cell(cells, fields, "collection_status")),
        "notes": _txt(_cell(cells, fields, "notes")),
        "lawyer_notes": _txt(_cell(cells, fields, "lawyer_notes")),
        "raw": dict(raw, _status=fills) if fills else raw,
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
        it = wb[sh].iter_rows()
        head, head_cells = [], []
        for r in it:
            head_cells.append(r)
            head.append(tuple(getattr(c, "value", None) for c in r))
            if len(head) >= 12:
                break
        hi, fields = find_header_row(head)
        if hi is None:
            rep["missing_sheets"].append(sh)
            continue
        headers = [normalize_header(c) for c in head[hi]]
        def rows_iter():
            for k, r in enumerate(head_cells[hi + 1:], start=hi + 2):
                yield k, r
            k = len(head) + 1
            for r in it:
                yield k, r
                k += 1
        empty = 0
        for i, rcells in rows_iter():
            cells = tuple(getattr(c, "value", None) for c in rcells)
            fills = {f: cell_fill_class(rcells[fields[f]]) for f in _STATUS_FIELDS
                     if f in fields and fields[f] < len(rcells)}
            if not any(c not in (None, "") and not (isinstance(c, str) and not c.strip()) for c in (cells or ())):
                empty += 1
                if empty >= stop_after_empty:
                    rep["stopped_at"] = i   # קבצים עם מיליון שורות ריקות בסוף — לא קוראים את כולן
                    break
                continue
            empty = 0
            st, row = normalize_row(cells, fields, {"branch": branch, "year": year, "sheet": sh, "row_idx": i,
                                                    "headers": headers, "default_agent": default_agent,
                                                    "key_mode": key_mode, "fills": fills})
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
    st = ((row or {}).get("raw") or {}).get("_status")
    if st:
        core["_status"] = st   # שינוי צבע בלבד (למשל 'התקבל כסף' הפך ירוק) — חייב לעדכן
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
         "year": r.get("year"), "phone": re.sub(r"\D", "", str(r.get("client_phone") or ""))}   # וואטסאפ ללקוח (אייל 12/10)
    if (r.get("year") or 0) >= DETAIL_FROM_YEAR:
        rep = r.get("reported_date") or ""
        d.update(commission_net=r.get("commission_net"), paid=r.get("paid_amount"),
                 reported=("%s/%s" % (rep[5:7], rep[:4])) if rep else ("כן" if is_reported(r) else ""))
    return d


def view_comps(r):
    return {"date": _dmy(r.get("deal_date") or ""), "address": _addr(r), "kind": _kind(r.get("side")),
            "side": r.get("side") or "", "price": r.get("deal_amount"), "agent": r.get("agent") or "",
            "branch": r.get("branch")}


_FULL = ("id", "branch", "year", "src_sheet", "src_serial", "deal_date", "city", "street", "side", "agent",
         "client_name", "client_phone", "other_broker", "deal_amount", "commission_gross", "commission_net",
         "discount", "lead_source", "paid_amount", "deposited", "invoice_no", "receipt_no", "reported_date",
         "remax_approved", "collection_status", "notes", "lawyer_notes", "missing_since", "status")


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
    """מפתח רחוב: בלי מספר בית, גרשיים ותחיליות (שדרות/שד'/רח'/דרך) — כמו במיפוי OSM."""
    return _osm_street_key(st)


def _label_has(label, aliases):
    """שם שכונה (גם של יד2 עם פסיקים: 'נאות אפק, אפקה') מכיל אחד הכינויים כמילים שלמות."""
    norm = _osm_norm
    parts = [norm(p) for p in str(label or "").split(",") if norm(p)]
    for a in {norm(x) for x in aliases or () if norm(x)}:
        for p in parts:
            if p == a or re.search(r"(^| )" + re.escape(a) + r"($| )", p):
                return True
    return False


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


def load_osm_streets(path=None):
    """המיפוי המאושר (tools/street_nb_osm.json). אין קובץ (טרם אושר) → {} — החיפוש לפי עדויות הנכסים בלבד."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "street_nb_osm.json")
    try:
        return (_json.load(open(path, encoding="utf-8")) or {}).get("streets") or {}
    except Exception:
        return {}


def _city_from_text(text, idx):
    """עיר מתוך שדה רחוב שמכיל כתובת מלאה ('בגין12 ק.מוצקין') — שם עיר/כינוי כמילה שלמה. אין → ''."""
    t = " " + _city_n(re.sub(r"ק\s*\.\s*", "קרית ", str(text or ""))) + " "
    best = ""
    for canon, aliases in ((idx or {}).get("city") or {}).items():
        for a in [canon] + list(aliases or ()):
            a = _city_n(a)
            if len(a) >= 3 and (" " + a + " ") in t and len(a) > len(best):
                best, out = a, _city_n(canon)
    return out if best else ""


def nb_street_index(street_rows, idx, osm=None):
    """[(רחוב, שכונה, עיר)] → {"sc": {(רחוב, עיר): שכונה}, "s": {רחוב: שכונה}} — רק עם 2+ עדויות.
    "s" = רחוב שכל העדויות שלו בשכונה אחת (לעסקה בלי עיר).
    osm = {עיר: {רחוב: שכונה}} (tools/street_nb_osm.json, מאושר) — משלים רחובות בלי עדויות; העדויות גוברות."""
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
    for city, m in (osm or {}).items():
        for st, lab in (m or {}).items():
            k = (_sk(st), _city_canon(city, idx))
            if len(k[0]) >= 2 and lab and k not in sc:
                sc[k] = _city_n(lab)
    for k, v in sc.items():
        by_st[k[0]].add(v)
    return {"sc": sc, "s": {st: list(v)[0] for st, v in by_st.items() if len(v) == 1}}


# שכונות שהשם שלהן קיים ביותר מעיר אחת — החלטת אייל לאיזו עיר הכוונה (12/10: 'גבעת הרקפות' = ביאליק, לא אתא)
AREA_FIXED = {"גבעת הרקפות": "קרית ביאליק"}


def find_area(q, idx):
    """מילים בחיפוש → שכונה (כינוי חד-משמעי, 3+ תווים; תחילית ב/ה/ל/מ מותרת). אחרת None."""
    am = _alias_map(idx)
    amb = {_city_n(a) for a in ((idx or {}).get("ambiguous") or ())}
    toks = _city_n(q).split()
    for size in (3, 2, 1):
        for i in range(len(toks) - size + 1):
            ph = " ".join(toks[i:i + size])
            for cand in (ph, ph[1:] if ph[:1] in "בהלמ" else None):
                if cand in AREA_FIXED:
                    city = AREA_FIXED[cand]
                    return {"nb": cand, "city": city, "label": cand + " · " + city, "aliases": [cand], "only_city": True}
    for size in (3, 2, 1):
        for i in range(len(toks) - size + 1):
            ph = " ".join(toks[i:i + size])
            for cand in (ph, ph[1:] if ph[:1] in "בהלמ" else None):
                if cand and len(cand) >= 3 and cand in am and cand not in amb:
                    cn = am[cand]
                    city = ((idx.get("nb") or {}).get(cn) or {}).get("city", "")
                    al = [cn] + list(((idx.get("nb") or {}).get(cn) or {}).get("aliases") or [])
                    return {"nb": cn, "city": city, "label": cn + (" · " + city if city else ""), "aliases": al}
    return None


def area_filter(rows, q, area_ctx=None):
    """חיפוש לפי שכונה (אם זוהתה) או רחוב/עיר → (שורות, שכונה|None). משותף למחירי השוואה ול'העסקאות שלי'."""
    toks = [t for t in _norm_q(q).split() if t]
    if not toks:
        return [], None
    area = find_area(q, area_ctx.get("idx")) if area_ctx else None
    if area:
        si = area_ctx.get("streets") or {}

        def _row_city(r):
            return _city_canon(r.get("city"), idx) or _city_from_text(r.get("street"), idx)
        sc, s1, idx = si.get("sc") or {}, si.get("s") or {}, area_ctx.get("idx")

        def _nb_of(r):
            sk, city = _sk(r.get("street")), _row_city(r)
            return sc.get((sk, city)) if city else s1.get(sk)
        def _in_city(r):   # שכונה עם עיר קבועה (AREA_FIXED) — רק עסקאות באותה עיר (או בלי עיר)
            c = _row_city(r)
            return not area.get("only_city") or not c or c == _city_n(area["city"])
        def _city_is_area(r):
            # אייל 12/10: בקובץ כתוב 'חיים'/'קרית חיים' בעמודת העיר — שייך לשכונה גם כשהרחוב לא במפה
            c = _city_n(re.sub(r"^ק\s*\.\s*", "קרית ", str(r.get("city") or "").strip()))
            return bool(c) and (_label_has(c, area.get("aliases")) or _label_has("קרית " + c, area.get("aliases")))
        hit = [r for r in rows if _in_city(r) and (_city_is_area(r) or
               (lambda v: v and (v == area["nb"] or _label_has(v, area.get("aliases"))))(_nb_of(r)))]
    else:
        hit = [r for r in rows if all(t in _norm_q(" ".join((r.get("street") or "", r.get("city") or ""))) for t in toks)]
    return _sort_desc(hit), area


def comps_search(rows, q, cap=200, area_ctx=None):
    hit, area = area_filter(rows, q, area_ctx)
    if not [t for t in _norm_q(q).split() if t]:
        return {"results": [], "n_sale": 0, "avg_sale": None, "n_rent": 0, "avg_rent": None}
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
            "byAgent": by_agent, "byMonth": [{"month": m, **_agg(months[m])} for m in sorted(months)],
            "bySide": side_split(rows, year)}


def active_rows(rows):
    """[ביקורת 2א] שורות שנעלמו מהאקסל (missing_since) לא נספרות בדוחות/רשימות/השוואה — רק ב'לבדיקה' ובחיפוש.
    [אייל 12/10] גם שורה בלי תאריך, בלי רחוב ובלי לקוח (שורת סכום שנכנסה בטעות) — לא עסקה."""
    return [r for r in rows if not r.get("missing_since")
            and (r.get("deal_date") or r.get("street") or r.get("client_name"))]


def _detail(rows):
    return [r for r in rows if (r.get("year") or 0) >= DETAIL_FROM_YEAR]


def unpaid(rows):
    """החדש למעלה (אייל 12/10: 'תמיד העסקאות עם התאריך הכי חדש בראש הרשימה')."""
    return _sort_desc(r for r in _detail(rows) if not r.get("paid_amount"))


def is_reported(r):
    """תאריך דיווח — או תא 'דווח במערכת' ירוק בלי תאריך (אייל 12/10)."""
    return bool(r.get("reported_date")) or ((r.get("status") or {}).get("reported_date") == "green")


def unreported(rows):
    return _sort_desc(r for r in _detail(rows) if not is_reported(r))


_BRANCH_KEYS = ("bialik", "motzkin", "kiryat_yam")


def by_kind(rows, deal):
    """אייל 12/10: הפרדה בין מכירה/קנייה לשכירות. 'sale' / 'rent'; ריק = הכל. צד לא ידוע נחשב מכירה (כמו _kind)."""
    want = {"sale": "מכירה", "rent": "השכרה"}.get(deal)
    return [r for r in rows if _kind(r.get("side")) == want] if want else rows


def side_split(rows, year):
    cur = [r for r in rows if r.get("year") == year]
    return {"sale": _agg(by_kind(cur, "sale")), "rent": _agg(by_kind(cur, "rent"))}


def by_branch(rows, branch):
    """בורר הסניף של המנהלים (אייל 12/10). ריק/לא מוכר = כל הסניפים."""
    return [r for r in rows if r.get("branch") == branch] if branch in _BRANCH_KEYS else rows


def link_names(deal_names, app_names, key):
    """שם בקבצים → שם הסוכן באפליקציה (אייל 12/10: 'לחי אלבז לא מופיעות עסקאות').
    זהה (אחרי נרמול כתיב) → אותו סוכן; אחרת שם פרטי + שם משפחה זהים ('חי אלבז' ↔ 'חי חיים אלבז') — רק כשיש מועמד יחיד.
    שם של מילה אחת / בלי התאמה — לא מחברים."""
    exact, loose = {}, {}
    for a in app_names or ():
        a = str(a or "").strip()
        if not a:
            continue
        exact.setdefault(key(a), a)
        t = a.split()
        if len(t) >= 2:
            loose.setdefault((key(t[0]), key(t[-1])), set()).add(a)
    out = {}
    for dn in deal_names or ():
        dn = str(dn or "").strip()
        if not dn:
            continue
        if key(dn) in exact:
            out[dn] = exact[key(dn)]
            continue
        t = dn.split()
        cand = loose.get((key(t[0]), key(t[-1]))) if len(t) >= 2 else None
        if cand and len(cand) == 1:
            out[dn] = next(iter(cand))
    return out


def apply_links(rows, links):
    """עותק של השורות עם שמות הסוכנים באפליקציה (גם בעסקה משותפת, לכל חבר); השם מהקובץ נשמר ב-agent_file."""
    out = []
    for r in rows:
        mem = split_agents(r.get("agent", ""))
        new = [links.get(a, a) for a in mem]
        if new != mem:
            r = dict(r, agent=" + ".join(new), agent_file=r.get("agent", ""))
        out.append(r)
    return out


def apply_agent_map(rows, amap):
    """מיפוי שמות הקבצים (tools/deals_agent_map.json) גם לשורות שכבר נשמרו — 'ליקה' → 'ליקה אוברוב',
    'בן ובן' → 'בנימין אביטן + בן קדוש' (אייל 13/10). ערך ריק = בלי מיפוי; '-' = לא סוכן (נשאר כמו שהוא)."""
    out = []
    for r in rows:
        mem, new = split_agents(r.get("agent", "")), []
        for a in mem:
            v = (amap or {}).get("%s|%s" % (r.get("branch") or "", a), "")
            for x in (split_agents(v) if v and v != "-" else [a]):
                if x not in new:
                    new.append(x)
        out.append(dict(r, agent=" + ".join(new)) if new != mem else r)
    return out


_LINK_CACHE = {"ts": 0, "src": None, "rows": [], "links": {}, "names": []}


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
  .brs{display:flex;gap:6px;flex-wrap:wrap}
  .brs .bc{padding:10px 14px;min-height:44px;display:flex;align-items:center;font-size:13px;font-weight:700;border-radius:12px;background:#fff;border:1.5px solid #DCD6C8;color:#5B6472;cursor:pointer}
  .brs .bc.on{background:#1E3A5F;border-color:#1E3A5F;color:#fff}
  a.wa.rv{background:#fff;color:#7A5E1C;border:1.5px solid #E4C56B}
  a.wa{display:flex;align-items:center;justify-content:center;gap:8px;min-height:44px;margin-top:10px;border-radius:12px;background:#157A43;color:#fff;font-weight:700;font-size:14px;text-decoration:none}
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
var TOK = '', ED = false, TAB = '', YEAR = '', Q = '', ME = '', BRF = '', MQ = '', KF = '', OFFICE = '', REVIEW = '';
var BR = {bialik: 'ביאליק', motzkin: 'מוצקין', kiryat_yam: 'קרית ים'};
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function fmtP(p){ if (p == null || p === '') return ''; var n = Math.round(Number(p)); if (isNaN(n)) return ''; return '₪' + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function emptyHtml(t, s){ return '<div class="empty"><div class="c"><svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 11l8-7 8 7v9H4z" fill="none" stroke="#C29435" stroke-width="2" stroke-linejoin="round"/></svg></div><div class="t">' + esc(t) + '</div><div class="s">' + esc(s) + '</div></div>'; }
// אייל 12/10: וואטסאפ ללקוח עם הודעה מובנית שמזכירה שהסוכן קיים — רק כשיש טלפון
function waPhone(p){
  var d = String(p || '').replace(/\D/g, '');
  if (d.indexOf('972') === 0) d = d.slice(3);
  if (d.charAt(0) === '0') d = d.slice(1);
  return d.length >= 8 && d.length <= 9 ? '972' + d : '';
}
function remindText(x, agent){
  var first = String(x.client || '').trim().split(/\s+/)[0] || '';
  var acts = {'מוכר': 'במכירת הנכס', 'קונה': 'בקניית הנכס', 'משכיר': 'בהשכרת הנכס', 'שוכר': 'בשכירת הדירה'};
  var act = acts[String(x.side || '').trim()] || 'בעסקת הנדל"ן';
  var addr = x.address || [x.street, x.city].filter(Boolean).join(', ');
  var yr = /\d{4}$/.test(x.date || '') ? String(x.date).slice(-4) : '';
  return 'שלום' + (first ? ' ' + first : '') + ', כאן ' + agent + (OFFICE ? ' מ' + OFFICE : '') + '. ליוויתי אתכם ' + act +
    (addr ? ' ב' + addr : '') + (yr ? ' ב-' + yr : '') + ', ורציתי להזכיר שאני כאן בשבילכם. ' +
    'אם אתם או מישהו שאתם מכירים חושבים לקנות, למכור או להשכיר נכס, אשמח לעזור.\n' + agent;
}
// אייל 20/10 (GEO): בקשת ביקורת בגוגל — רק כשהוגדר קישור בניהול, ורק לעסקאות מהשנה האחרונה
function reviewText(x, agent){
  var first = String(x.client || '').trim().split(/\s+/)[0] || '';
  var acts = {'מוכר': 'במכירת הנכס', 'קונה': 'בקניית הנכס', 'משכיר': 'בהשכרת הנכס', 'שוכר': 'בשכירת הדירה'};
  var act = acts[String(x.side || '').trim()] || 'בעסקת הנדל"ן';
  return 'שלום' + (first ? ' ' + first : '') + ', כאן ' + agent + (OFFICE ? ' מ' + OFFICE : '') + '. היה לי תענוג ללוות אתכם ' + act + '. ' +
    'אם הייתם מרוצים, אשמח מאוד אם תכתבו עלינו ביקורת קצרה בגוגל — זה עוזר לנו מאוד:\n' + REVIEW + '\nתודה רבה!\n' + agent;
}
function recentDeal(x){
  var m = /(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})$/.exec(String(x.date || ''));
  if (!m) return false;
  return (Date.now() - new Date(+m[3], +m[2] - 1, +m[1]).getTime()) < 365 * 86400000;
}
function waBtn(x, agent){
  var ph = waPhone(x.phone || x.client_phone);
  if (!ph) return '';
  var rv = (REVIEW && recentDeal(x)) ? '<a class="wa rv" target="_blank" rel="noopener" href="https://wa.me/' + ph + '?text=' + encodeURIComponent(reviewText(x, agent || '')) + '">' +
    '<svg width="18" height="18" viewBox="0 0 24 24"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z" fill="none" stroke="#7A5E1C" stroke-width="1.8" stroke-linejoin="round"/></svg>' +
    'בקשת ביקורת בגוגל</a>' : '';
  return '<a class="wa" target="_blank" rel="noopener" href="https://wa.me/' + ph + '?text=' + encodeURIComponent(remindText(x, agent || '')) + '">' +
    '<svg width="18" height="18" viewBox="0 0 24 24"><path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.6-1.2A9 9 0 1 0 12 3z" fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg>' +
    'תזכורת ללקוח בוואטסאפ</a>' + rv;
}
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
      (x.reported ? '<span class="chip ok">דווח' + (x.reported === 'כן' ? '' : ' ' + esc(x.reported)) + '</span>' : '<span class="chip wait">לא דווח</span>') + '</div>' : '') +
    waBtn(x, me || (ag.split(' + ')[0] || '')) + '</div>';
}
function compCard(x){
  return '<div class="card"><div class="row1"><div><div class="ad">' + esc(x.address || '—') + '</div>' +
    '<div class="sb">' + esc([x.date, x.kind, x.agent, ED ? BR[x.branch] : ''].filter(Boolean).join(' · ')) + '</div></div>' +
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
    (x.reported_date ? '<span class="chip ok">דווח ' + esc(x.reported_date.slice(5, 7) + '/' + x.reported_date.slice(0, 4)) + '</span>' :
      (x.status && x.status.reported_date === 'green' ? '<span class="chip ok">דווח</span>' : '<span class="chip wait">לא דווח</span>'))) +
    (x.collection_status ? '<span class="chip">' + esc(x.collection_status) + '</span>' : '') +
    (x.invoice_no ? '<span class="chip">חשבונית ' + esc(x.invoice_no) + '</span>' : '') +
    (x.receipt_no ? '<span class="chip">קבלה ' + esc(x.receipt_no) + '</span>' : '') + '</div>' +
    waBtn({client: x.client_name, client_phone: x.client_phone, side: x.side, street: x.street, city: x.city, date: x.date},
          String(x.agent || '').split(' + ')[0]) + '</div>';
}
function statsHtml(j){
  var t = j.total || {}, p = j.prev || {};
  var tbl = function(title, rows, key, lbl){
    if (!rows || !rows.length) return '';
    return '<div class="card"><div class="ad" style="margin-bottom:6px">' + title + '</div><table><tr><th>' + lbl + '</th><th>עסקאות</th><th>עמלה</th></tr>' +
      rows.map(function(r){ return '<tr><td>' + esc(key(r)) + '</td><td>' + r.n + '</td><td>' + esc(fmtP(r.commission)) + '</td></tr>'; }).join('') + '</table></div>';
  };
  var lbl = j.deal === 'rent' ? 'שכירויות ' : (j.deal === 'sale' ? 'מכירות וקניות ' : 'עסקאות ');
  return '<div class="sum"><div class="card"><b>' + (t.n || 0) + '</b><span>' + lbl + j.year + '</span></div>' +
    '<div class="card"><b>' + esc(fmtP(t.commission || 0)) + '</b><span>עמלה לפני מע"מ</span></div></div>' +
    '<div class="sb" style="text-align:center">' + (j.year - 1) + ': ' + (p.n || 0) + ' עסקאות · ' + esc(fmtP(p.commission || 0)) + '</div>' +
    (j.bySide ? '<div class="sum">' + [['sale', 'מכירה וקנייה'], ['rent', 'שכירות']].map(function(k){
      var v = j.bySide[k[0]] || {};
      return '<div class="card"' + (j.deal && j.deal !== k[0] ? ' style="opacity:.55"' : '') + '><b>' + (v.n || 0) + '</b><span>' + k[1] + ' · ' + esc(fmtP(v.commission || 0)) + '</span></div>'; }).join('') + '</div>' : '') +
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
function brBar(){
  // בורר סניף למנהלים בכל הטאבים (אייל 12/10)
  if (!ED) return '';
  return '<div class="brs">' + [['', 'כל הסניפים'], ['bialik', 'ביאליק'], ['motzkin', 'מוצקין'], ['kiryat_yam', 'קרית ים']].map(function(b){
    return '<div class="bc' + (b[0] === BRF ? ' on' : '') + '" onclick="setBr(\'' + b[0] + '\')">' + b[1] + '</div>'; }).join('') + '</div>';
}
function kindBar(){
  // אייל 12/10: הפרדה בין מכירה/קנייה לשכירות — לכולם, בכל הטאבים
  return '<div class="brs" style="margin-top:8px">' + [['', 'הכל'], ['sale', 'מכירה וקנייה'], ['rent', 'שכירות']].map(function(b){
    return '<div class="bc' + (b[0] === KF ? ' on' : '') + '" onclick="setKind(\'' + b[0] + '\')">' + b[1] + '</div>'; }).join('') + '</div>';
}
function setKind(k){ KF = k; try{ localStorage.setItem('v2st:histkind', k); }catch(e){} draw(); }
function kQ(){ return KF ? 'deal=' + KF : ''; }
function bars(){ return brBar() + kindBar(); }
function setBr(b){ BRF = b; try{ localStorage.setItem('v2st:histbr', b); }catch(e){} draw(); }
function brQ(){ return ED && BRF ? 'branch=' + BRF : ''; }
function withQ(u){ var parts = [].slice.call(arguments, 1).filter(Boolean); return parts.length ? u + (u.indexOf('?') >= 0 ? '&' : '?') + parts.join('&') : u; }
function agentsHtml(j){
  // טבלת כל הסוכנים (אייל 12/10)
  var a = (j && j.agents) || [], u = (j && j.unlinked) || [];
  if (!a.length && !u.length) return emptyHtml('אין סוכנים להצגה', 'רשימת הסוכנים נטענת מאנשי הקשר של המשרד');
  var h = '<div class="card"><div class="ad" style="margin-bottom:6px">סוכנים באפליקציה · ' + a.length + '</div>' +
    '<table><tr><th>סוכן</th><th>עסקאות</th><th>' + (j.since || 2026) + '</th><th>אחרונה</th></tr>' +
    a.map(function(x){
      return '<tr><td>' + esc(x.name) + (x.file_names && x.file_names.length ? '<div class="sb">בקבצים: ' + esc(x.file_names.join(', ')) + '</div>' : '') + '</td>' +
        '<td>' + (x.n ? x.n : '<span class="chip wait">אין</span>') + '</td><td>' + (x.n_cur || '') + '</td><td>' + esc(x.last || '') + '</td></tr>';
    }).join('') + '</table></div>';
  if (u.length) h += '<div class="card"><div class="ad">שמות בקבצים בלי סוכן באפליקציה · ' + u.length + '</div>' +
    '<div class="sb" style="margin-bottom:6px">סוכנים לשעבר, שותפים חיצוניים או שם שכתוב אחרת — שלח לי אם מישהו מהם הוא סוכן פעיל</div>' +
    '<table><tr><th>שם בקובץ</th><th>עסקאות</th><th>סניף</th><th>אחרונה</th></tr>' +
    u.map(function(x){ return '<tr><td>' + esc(x.name) + '</td><td>' + x.n + '</td><td>' + esc((x.branches || []).map(function(b){ return BR[b] || b; }).join(', ')) + '</td><td>' + esc(x.last || '') + '</td></tr>'; }).join('') +
    '</table></div>';
  return h;
}
function GET(u){ return fetch(u, {headers: {'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function setTab(t){ TAB = t; try{ localStorage.setItem('v2st:hist', t); }catch(e){} draw(); }
function tabsFor(){
  return ED ? [['stats', 'דוחות'], ['unpaid', 'לא שולם'], ['unrep', 'לא דווח'], ['agents', 'סוכנים'], ['review', 'לבדיקה'], ['search', 'חיפוש'], ['comps', 'מחירי השוואה']]
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
    tools.innerHTML = bars() + '<input class="q" id="q" type="search" enterkeyhint="search" placeholder="' +
      (TAB === 'comps' ? 'רחוב או שכונה — למשל "אפקה" או "הגפן מוצקין"' : 'שם לקוח, טלפון, כתובת, סוכן או מספר חשבונית') + '" value="' + esc(Q) + '">';
    var q = document.getElementById('q');
    q.onkeydown = function(e){ if (e.key === 'Enter'){ Q = q.value.trim(); runQ(); } };
    q.onchange = function(){ Q = q.value.trim(); runQ(); };
    runQ(); return;
  }
  tools.innerHTML = bars();
  if (TAB === 'mine'){
    GET(withQ('/v2/api/deals/history/mine', YEAR ? 'year=' + YEAR : '', MQ ? 'q=' + encodeURIComponent(MQ) : '', kQ())).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'נסה שוב בעוד רגע'); return; }
      OFFICE = j.office || OFFICE; REVIEW = j.review || REVIEW;
      // אייל 12/10: הסוכן מחפש שכונה/רחוב רק בעסקאות שלו
      tools.innerHTML = kindBar() + '<input class="q" id="mq" style="margin-top:10px" type="search" enterkeyhint="search" placeholder="שכונה או רחוב — למשל אפקה" value="' + esc(MQ) + '">' +
        '<div style="display:flex;gap:8px;align-items:center;margin-top:10px"><select class="yr" onchange="YEAR=this.value;draw()"><option value="">כל השנים</option>' +
        (j.years || []).map(function(y){ return '<option' + (String(y) === String(YEAR) ? ' selected' : '') + '>' + y + '</option>'; }).join('') +
        '</select><div class="sb">' + j.n + ' עסקאות' + (j.area ? ' · שכונת ' + esc(j.area) : '') + '</div></div>';
      var mq = document.getElementById('mq');
      mq.onkeydown = function(e){ if (e.key === 'Enter'){ MQ = mq.value.trim(); draw(); } };
      mq.onchange = function(){ if (mq.value.trim() !== MQ){ MQ = mq.value.trim(); draw(); } };
      list.innerHTML = j.results.length ? j.results.map(function(x){ return agentCard(x, ME); }).join('') :
        (MQ ? emptyHtml('לא נמצאו עסקאות שלך כאן', 'אין לך עסקאות ב"' + MQ + '" — נסה שכונה או רחוב אחר') :
        emptyHtml('עוד אין עסקאות כאן', 'העסקאות שסגרת במשרד יופיעו כאן'));
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else if (TAB === 'stats'){
    GET(withQ('/v2/api/deals/history/stats', YEAR ? 'year=' + YEAR : '', brQ(), kQ())).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'הדוחות זמינים למנהלים ולהנהלת חשבונות'); return; }
      tools.innerHTML = bars() + '<select class="yr" style="margin-top:10px" onchange="YEAR=this.value;draw()">' + (j.years || []).map(function(y){
        return '<option' + (String(y) === String(j.year) ? ' selected' : '') + '>' + y + '</option>'; }).join('') + '</select>';
      list.innerHTML = statsHtml(j);
      GET('/v2/api/deals/history/sync').then(function(sy){ tools.insertAdjacentHTML('beforeend', syncLine(sy)); }).catch(function(){});
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else if (TAB === 'agents'){
    tools.innerHTML = '';
    GET('/v2/api/deals/history/agents').then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'זמין למנהלים ולהנהלת חשבונות'); return; }
      list.innerHTML = agentsHtml(j);
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else if (TAB === 'review'){
    GET(withQ('/v2/api/deals/history/review', brQ(), kQ())).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'זמין למנהלים ולהנהלת חשבונות'); return; }
      list.innerHTML = reviewHtml(j);
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else {
    var kind = TAB === 'unpaid' ? 'unpaid' : 'unreported';
    GET(withQ('/v2/api/deals/history/open?kind=' + kind, brQ(), kQ())).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'זמין למנהלים ולהנהלת חשבונות'); return; }
      OFFICE = j.office || OFFICE; REVIEW = j.review || REVIEW;
      tools.innerHTML = bars() + (j.results.length ? '<div class="sb" style="margin-top:8px">' + j.results.length + ' צדדים ב-' + j.since + ' והלאה, מהחדש לישן</div>' : '');
      list.innerHTML = j.results.length ? j.results.map(openCard).join('') :
        emptyHtml(kind === 'unpaid' ? 'אין כרגע מה לגבות' : 'אין כרגע מה לדווח', 'הרשימה מתמלאת מקבצי המעקב של ' + j.since + ' — אחרי חיבור הקבצים לאפי');
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  }
}
function searchMore(off){
  // אייל 12/10: חיפוש בלי טקסט = כל העסקאות של שלושת המשרדים, החדש למעלה, 100 בכל פעם
  var list = document.getElementById('list');
  var more = document.getElementById('more'); if (more) more.remove();
  if (!off) list.innerHTML = '<div class="sb" style="text-align:center;padding:20px 0">טוען…</div>';
  GET(withQ('/v2/api/deals/history/search?q=' + encodeURIComponent(Q || ''), brQ(), kQ(), off ? 'offset=' + off : '')).then(function(j){
    if (!j || !j.ok){ list.innerHTML = emptyHtml('לא ניתן לחפש', 'נסה שוב'); return; }
    OFFICE = j.office || OFFICE; REVIEW = j.review || REVIEW;
    var cards = j.results.map(openCard).join('');
    var btn = j.more ? '<div id="more" class="bc" style="justify-content:center;background:#fff;border:1.5px solid #DCD6C8;border-radius:12px;min-height:44px;display:flex;align-items:center;font-weight:700;cursor:pointer" onclick="searchMore(' + (j.offset + j.results.length) + ')">הצג עוד</div>' : '';
    if (!off){
      list.innerHTML = j.results.length ? '<div class="sb">' + (Q ? j.total + ' תוצאות' : 'כל העסקאות · ' + j.total + ' · החדשות למעלה') + '</div>' + cards + btn :
        emptyHtml('לא נמצא', Q ? 'אין עסקאות עבור "' + Q + '" — נסה מילה אחרת' : 'אין עסקאות להצגה');
    } else list.insertAdjacentHTML('beforeend', cards + btn);
  }).catch(function(){ if (!off) list.innerHTML = emptyHtml('לא ניתן לחפש', 'בדוק חיבור ונסה שוב'); });
}
function runQ(){
  var list = document.getElementById('list');
  if (TAB === 'search'){ searchMore(0); return; }
  if (!Q){ list.innerHTML = emptyHtml('מחירי השוואה', 'הקלד רחוב או שכונה (למשל אפקה) וראה מה נמכר שם ובכמה'); return; }
  GET(withQ('/v2/api/deals/history/comps?q=' + encodeURIComponent(Q), brQ(), kQ())).then(function(j){
    if (!j || !j.ok){ list.innerHTML = emptyHtml('לא ניתן לחפש', 'נסה שוב'); return; }
    OFFICE = j.office || OFFICE; REVIEW = j.review || REVIEW;
    var head = (j.area ? '<div class="sb">שכונת ' + esc(j.area) + '</div>' : '') + '<div class="sum"><div class="card"><b>' + j.n_sale + '</b><span>מכירות · ממוצע ' + esc(fmtP(j.avg_sale) || '—') + '</span></div>' +
      '<div class="card"><b>' + j.n_rent + '</b><span>השכרות · ממוצע ' + esc(fmtP(j.avg_rent) || '—') + '</span></div></div>';
    list.innerHTML = j.results.length ? head + j.results.map(compCard).join('') :
      emptyHtml('לא נמצא', 'אין עסקאות עבור "' + Q + '" — נסה מילה אחרת');
  }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לחפש', 'בדוק חיבור ונסה שוב'); });
}
(function(){
  try{ TOK = localStorage.getItem('fbTok') || ''; TAB = localStorage.getItem('v2st:hist') || ''; BRF = localStorage.getItem('v2st:histbr') || ''; KF = localStorage.getItem('v2st:histkind') || ''; }catch(e){}
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

    def _app_names():
        """שמות הסוכנים באפליקציה — אנשי הקשר (מקור הכניסה) + ספריית הצוות בקונפיג."""
        names = []
        try:
            names += [v for v in (G["web_contacts_phone_name"]() or {}).values() if v]
        except Exception:
            pass
        try:
            names += [(a.get("name") or "") for a in (G["_load_config"]().get("agents") or [])]
        except Exception:
            pass
        out, seen = [], set()
        for nm in names:
            nm = str(nm or "").strip()
            k = G["_canon_key"](nm)
            if nm and k and k not in seen and nm not in _GENERIC:
                seen.add(k)
                out.append(nm)
        return out

    def _lrows(sb):
        """השורות עם שמות הסוכנים כפי שהם באפליקציה (מטמון 10 דק' לכל טעינה של הטבלה)."""
        rows = _rows(sb)
        if _LINK_CACHE["src"] is rows and time.time() - _LINK_CACHE["ts"] < 600:
            return _LINK_CACHE["rows"]
        names = _app_names()
        rows_m = apply_agent_map(rows, load_agent_map())
        mem = {a for r in rows_m for a in split_agents(r.get("agent", ""))}
        links = link_names(mem, names, G["_canon_key"]) if names else {}
        _LINK_CACHE.update(ts=time.time(), src=rows, rows=apply_links(rows_m, links), links=links, names=names)
        return _LINK_CACHE["rows"]

    # [CRM 21/10] מודול 'עסקאות' ב-CRM קורא את אותן שורות (עם שמות הסוכנים כמו באפי)
    G["_deal_history_linked"] = lambda: _lrows(sb)

    def _office():
        try:
            return ((G["_load_config"]() or {}).get("v2_office") or {}).get("name") or ""
        except Exception:
            return ""

    def _review():
        """קישור 'כתבו ביקורת בגוגל' של המשרד (ניהול ← פרטי המשרד) — לכפתור בקשת ביקורת (GEO 20/10)."""
        try:
            u = str(((G["_load_config"]() or {}).get("v2_office") or {}).get("review", "") or "").strip()
            return u if u.startswith("https://") else ""
        except Exception:
            return ""

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
        rows = scope_rows(active_rows(_lrows(sb)), {"keys": _keys(s)}, G["_canon_key"])
        years = sorted({r.get("year") for r in rows if r.get("year")}, reverse=True)
        rows = by_kind(rows, request.args.get("deal", ""))
        q, area = (request.args.get("q") or "").strip(), None
        if q:   # אייל 12/10: הסוכן רואה באיזו שכונה/רחוב הוא עצמו מכר
            rows, area = area_filter(rows, q, _area_ctx())
        y = request.args.get("year", "")
        if y.isdigit():
            rows = [r for r in rows if r.get("year") == int(y)]
        res = [dict(view_agent(r), agent=r.get("agent") or "") for r in _sort_desc(rows)]
        out = {"ok": True, "results": res, "years": years, "n": len(rows), "office": _office(), "review": _review()}
        if area:
            out["area"] = area["label"]
        return G["_etag_wrap"](out)

    _AREA = {"ts": 0, "v": None}

    def _area_ctx():
        """מפת הכינויים + רחוב→שכונה (מטמון שעה). כשל → חיפוש רחוב רגיל."""
        if _AREA["v"] is not None and time.time() - _AREA["ts"] < 3600:
            return _AREA["v"]
        try:
            idx = G["_nb_alias_idx"]()
            v = {"idx": idx, "streets": nb_street_index(G["_street_nb_rows"](), idx, osm=load_osm_streets())}
        except Exception:
            v = None
        _AREA.update(ts=time.time(), v=v)
        return v

    @app.route("/v2/api/deals/history/comps", methods=["GET"])
    def v2_deals_history_comps():
        s, err = _auth()
        if err:
            return err
        rows = active_rows(_lrows(sb))
        if is_editor(s):
            rows = by_branch(rows, request.args.get("branch", ""))
        rows = by_kind(rows, request.args.get("deal", ""))
        return jsonify(dict(comps_search(rows, request.args.get("q", ""), area_ctx=_area_ctx()), ok=True))

    @app.route("/v2/api/deals/history/stats", methods=["GET"])
    def v2_deals_history_stats():
        s, err = _editor()
        if err:
            return err
        br, dl = request.args.get("branch", ""), request.args.get("deal", "")
        full = by_branch(active_rows(_lrows(sb)), br)
        years = sorted({r.get("year") for r in full if r.get("year")}, reverse=True)
        y = request.args.get("year", "")
        year = int(y) if y.isdigit() else (years[0] if years else time.localtime().tm_year)
        out = dict(stats(by_kind(full, dl), year), ok=True, years=years, branch=br if br in _BRANCH_KEYS else "",
                   deal=dl if dl in ("sale", "rent") else "")
        out["bySide"] = side_split(full, year)      # תמיד שני הסיכומים, גם כשמסונן
        return G["_etag_wrap"](out)

    @app.route("/v2/api/deals/history/open", methods=["GET"])
    def v2_deals_history_open():
        s, err = _editor()
        if err:
            return err
        fn = unreported if request.args.get("kind") == "unreported" else unpaid
        rows = by_kind(by_branch(active_rows(_lrows(sb)), request.args.get("branch", "")), request.args.get("deal", ""))
        return G["_etag_wrap"]({"ok": True, "results": [view_full(r) for r in fn(rows)], "since": DETAIL_FROM_YEAR, "office": _office(), "review": _review()})

    @app.route("/v2/api/deals/history/search", methods=["GET"])
    def v2_deals_history_search():
        s, err = _editor()
        if err:
            return err
        toks = [t for t in _norm_q(request.args.get("q", "")).split() if t]
        rows = [r for r in by_kind(by_branch(_lrows(sb), request.args.get("branch", "")), request.args.get("deal", ""))
                if r.get("deal_date") or r.get("street") or r.get("client_name")]
        if toks:
            rows = [r for r in rows if all(t in _norm_q(" ".join(str(r.get(k) or "") for k in
                    ("client_name", "client_phone", "street", "city", "agent", "invoice_no", "receipt_no"))) for t in toks)]
        # אייל 12/10: בלי טקסט — כל העסקאות של שלושת המשרדים, החדש למעלה, בדפים
        try:
            lim = max(1, min(int(request.args.get("limit") or 100), 300))
            off = max(0, int(request.args.get("offset") or 0))
        except ValueError:
            lim, off = 100, 0
        hits = _sort_desc(rows)
        return jsonify({"ok": True, "results": [view_full(r) for r in hits[off:off + lim]], "total": len(hits),
                        "more": off + lim < len(hits), "offset": off, "office": _office(), "review": _review()})

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

    @app.route("/v2/api/deals/history/agents", methods=["GET"])
    def v2_deals_history_agents():
        """טבלת כל הסוכנים (אייל 12/10): כמה עסקאות מחוברות לכל סוכן באפליקציה, ושמות מהקבצים שלא מחוברים לאף סוכן."""
        s, err = _editor()
        if err:
            return err
        rows = active_rows(_lrows(sb))
        names = _LINK_CACHE.get("names") or []
        back = {}
        for dn, an in (_LINK_CACHE.get("links") or {}).items():
            if dn != an:
                back.setdefault(an, set()).add(dn)
        agg = {}
        for r in rows:
            for a in split_agents(r.get("agent", "")):
                x = agg.setdefault(a, {"n": 0, "n_cur": 0, "last": "", "branches": set()})
                x["n"] += 1
                x["n_cur"] += (r.get("year") or 0) >= DETAIL_FROM_YEAR
                x["last"] = max(x["last"], r.get("deal_date") or "")
                x["branches"].add(r.get("branch") or "")
        app_set = set(names)
        agents = [{"name": nm, "n": agg.get(nm, {}).get("n", 0), "n_cur": agg.get(nm, {}).get("n_cur", 0),
                   "last": _dmy(agg.get(nm, {}).get("last", "")), "file_names": sorted(back.get(nm, ()))} for nm in names]
        agents.sort(key=lambda a: (-a["n"], a["name"]))
        unl = [{"name": a, "n": x["n"], "last": _dmy(x["last"]), "branches": sorted(b for b in x["branches"] if b)}
               for a, x in agg.items() if a not in app_set]
        unl.sort(key=lambda a: (-a["n"], a["name"]))
        return jsonify({"ok": True, "agents": agents, "unlinked": unl, "since": DETAIL_FROM_YEAR})

    @app.route("/v2/api/deals/history/review", methods=["GET"])
    def v2_deals_history_review():
        s, err = _editor()
        if err:
            return err
        br = request.args.get("branch", "")
        miss = [view_full(r) for r in _sort_desc(r for r in by_kind(by_branch(_lrows(sb), br), request.args.get("deal", ""))
                                                 if r.get("missing_since") and (r.get("deal_date") or r.get("street") or r.get("client_name")))]
        unm = [{"branch": b, "name": nm} for b, st in SYNC_STATE.items() if isinstance(st, dict)
               and (br not in _BRANCH_KEYS or b == br) for nm in (st.get("unmapped") or [])]
        return jsonify({"ok": True, "missing": miss, "unmapped": unm})
