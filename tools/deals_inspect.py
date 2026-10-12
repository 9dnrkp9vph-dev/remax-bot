#!/usr/bin/env python3
"""בדיקת קובץ מעקב עסקאות — איך מסומנים 'התקבל כסף' / 'הופקד' / 'דווח' ואם יש טלפון לקוח (אייל 12/10).

קריאה בלבד. הסיסמה: getpass (לא מודפסת, לא נשמרת). הפלט בלי שמות ובלי טלפונים של לקוחות —
רק מספר שורה, סוג הערך (מספר/טקסט/ריק), צבע הרקע של התא, והאם יש טלפון בעמודת הלקוח (כן/לא).

  python3 tools/deals_inspect.py "<נתיב לקובץ>" [מספר שורות, ברירת מחדל 25]
"""
import collections, getpass, io, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import deals_history as D

WATCH = ("paid_amount", "deposited", "reported_date", "remax_approved", "collection_status", "invoice_no")
STATUS_TEXT = ("collection_status",)   # טקסט סטטוס בלבד מודפס (אין בו פרטי לקוח)


def fill_of(cell):
    f = getattr(cell, "fill", None)
    if not f or f.fill_type in (None, "none"):
        return "-"
    c = f.fgColor
    if c is None:
        return "?"
    if c.type == "rgb" and c.rgb not in (None, "00000000"):
        return "rgb:" + str(c.rgb)[-6:]
    if c.type == "theme":
        return "theme:%s%s" % (c.theme, ("/%+.2f" % c.tint) if c.tint else "")
    if c.type == "indexed":
        return "idx:%s" % c.indexed
    return "?"


def kind_of(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return "ריק"
    if isinstance(v, (int, float)):
        return "מספר"
    if hasattr(v, "year"):
        return "תאריך"
    return "טקסט"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path, n = argv[1], int(argv[2]) if len(argv) > 2 else 25
    data = open(path, "rb").read()
    import msoffcrypto, openpyxl
    bio = io.BytesIO(data)
    of = msoffcrypto.OfficeFile(io.BytesIO(data))
    if of.is_encrypted():
        out = io.BytesIO()
        of.load_key(password=getpass.getpass("סיסמת הקובץ: "))
        of.decrypt(out)
        bio = out
    bio.seek(0)
    wb = openpyxl.load_workbook(bio, data_only=True)   # לא read_only — צריך צבעים
    sh = D.pick_main_sheet(wb)
    ws = wb[sh]
    rows = list(ws.iter_rows(max_row=12))
    hi, F = D.find_header_row([[c.value for c in r] for r in rows])
    print("גיליון:", sh, "· שורת כותרת:", hi + 1)
    print("עמודות:", {f: openpyxl.utils.get_column_letter(F[f] + 1) for f in WATCH + ("client", "agent") if f in F})
    stats = collections.defaultdict(collections.Counter)
    shown = 0
    for r in ws.iter_rows(min_row=hi + 2):
        vals = [c.value for c in r]
        st, row = D.normalize_row(vals, F, {"branch": "x", "year": 2026, "sheet": sh, "row_idx": r[0].row})
        if st != "ok":
            continue
        parts = ["שורה %d" % r[0].row]
        for f in WATCH:
            if f not in F or F[f] >= len(r):
                continue
            c = r[F[f]]
            k, fl = kind_of(c.value), fill_of(c)
            stats[f][(k, fl)] += 1
            txt = (" '%s'" % str(c.value).strip()[:20]) if (f in STATUS_TEXT and k == "טקסט") else ""
            parts.append("%s=%s/%s%s" % (f, k, fl, txt))
        if "client" in F and F["client"] < len(r):
            has_ph = bool(re.search(r"0\d[\d\-\s]{7,}", str(r[F["client"]].value or "")))
            stats["client_phone"]["כן" if has_ph else "לא"] += 1
        if shown < n:
            print(" · ".join(parts))
            shown += 1
    print("\nסיכום (סוג ערך, צבע) לכל עמודה:")
    for f, c in stats.items():
        print(" ", f, dict(c.most_common(8)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
