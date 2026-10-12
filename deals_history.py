# deals_history.py
"""[DEALS-HISTORY 12/10] היסטוריית עסקאות — נרמול שורות מקבצי 'מעקב עסקאות', תצוגות לפי הרשאה,
סטטיסטיקה, ראוטים ודף /v2/history. ספק: docs/superpowers/specs/2026-10-12-deals-history-design.md"""
import re
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
    if not agent:
        return "skip", None   # שורות סיכום חודשיות / הערות — בלי סוכן אין עסקה
    ddate = parse_date(_cell(cells, fields, "deal_date"))
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
