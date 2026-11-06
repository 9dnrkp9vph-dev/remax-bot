"""cma.py — ניתוח שוק השוואתי (CMA) לעמוד "כמה שווה הנכס שלך" בתיק הפרזנטציה (אייל 06/11).

ספק: docs/superpowers/specs/2026-11-06-cma-design.md · תוכנית: docs/superpowers/plans/2026-11-06-cma.md
מקור הנתונים: טבלאות עסקאות שאייל מוריד ידנית ממדלן (proExpert) פעם בחודש, לכל שכונה, + העסקאות שסגרנו.
אין כאן משיכה אוטומטית מאף אתר ואין קריאה לבינה מלאכותית.
"""
from __future__ import annotations
import datetime as _dt
import re

MADLAN_HEADERS = ("יום מכירה", "כתובת", "מחיר (₪)", "סוג נכס", "חדרים", "שטח (מ״ר)", "קומה", "מחיר (₪) למ״ר", "שנת בנייה")
MIN_PRICE = 150000          # מתחת — לא עסקה מלאה (חלק מדירה וכד')
MIN_PPM = 7000              # מחיר למ"ר מתחת — חלק מדירה (596,666 על 103 מ"ר = 5,793); הנמוך האמיתי ב-5 שנים ~10,000
_QUOTES = "\"'״׳`"
_CITY_RE = re.compile(r"\s*(קרי+ת\s+\S+|חיפה|נשר|עכו)\s*$")


def _norm(s):
    t = str(s or "").replace("קריית", "קרית")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _cmp(s):
    """צורת השוואה: בלי גרשיים ובלי רווחים כפולים."""
    t = _norm(s)
    for q in _QUOTES:
        t = t.replace(q, "")
    return re.sub(r"\s+", " ", t).strip()


def canon_street(name, known):
    """שם רחוב ממדלן → השם כמו באפי (known). 'בגין מנחם'→'מנחם בגין', 'בן צבי'→'יצחק בן צבי', 'ערבה'→'הערבה'."""
    n = _norm(name)
    if not n:
        return ""
    km = {}
    for k in known or ():
        km.setdefault(_cmp(k), k)
    c = _cmp(n)
    toks = c.split(" ")
    cands = [" ".join(toks[i:] + toks[:i]) for i in range(len(toks))]
    for x in cands:
        for y in (x, "ה" + x, x[1:] if x.startswith("ה") else None):
            if y and y in km:
                return km[y]
    ends = [k for ck, k in km.items() if ck.endswith(" " + c)]
    if len(ends) == 1:
        return ends[0]
    return n


def parse_madlan_addr(s):
    """'בגין מנחם 12, קרית מוצקין' → {street:'בגין מנחם', house:12, city:'קרית מוצקין', project:''}.
    בלי מספר בית / שם בלועזית / 'ללא רחוב' → street '' ו-project = הטקסט."""
    t = _norm(s)
    if "," in t:
        left, city = t.split(",", 1)
        city = city.strip()
    else:
        m = _CITY_RE.search(t)
        city = m.group(1).strip() if m else ""
        left = t[:m.start()] if m else t
    left = left.strip()
    m = re.match(r"^([^\d]+?)\s+(\d+)", left)
    if m and re.search("[א-ת]", m.group(1)) and "ללא" not in m.group(1):
        return {"street": m.group(1).strip(" -"), "house": int(m.group(2)), "city": _norm(city), "project": ""}
    return {"street": "", "house": None, "city": _norm(city), "project": left}


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^\d.]", "", str(v).replace(",", ""))
    try:
        return float(t) if t else None
    except ValueError:
        return None


def _int(v):
    x = _num(v)
    return int(round(x)) if x is not None else None


def _rooms(v):
    x = _num(v)
    if x is None:
        return None
    return int(x) if x == int(x) else x


def _date(v):
    if isinstance(v, _dt.datetime):
        return v.date().isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    m = re.match(r"^\s*(\d{1,2})[./](\d{1,2})[./](\d{4})", str(v or ""))
    if m:
        try:
            return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return None
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    return m.group(0).strip() if m else None


def deal_key(r):
    return "|".join(str(x) for x in (r.get("deal_date") or "", r.get("street") or r.get("project") or "",
                                       r.get("house") if r.get("house") is not None else "", r.get("price") or "",
                                       r.get("rooms") if r.get("rooms") is not None else "",
                                       r.get("sqm") or "", r.get("floor") or ""))


def mark_dup_projects(rows):
    """אותה עסקה (תאריך ±3 ימים, מחיר, חדרים, מ"ר, קומה) תחת כמה כתובות — נשמרת רק שורה יחידה עם רחוב ומספר בית;
    אם יש כמה כאלה — כולן מסומנות bad='dup_project' (לא ידוע מה הכתובת האמיתית)."""
    groups = {}
    for r in rows:
        if r.get("price") is None:
            continue
        groups.setdefault((r["price"], r.get("rooms"), r.get("sqm"), r.get("floor")), []).append(r)
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda r: r.get("deal_date") or "")
        clusters, cur = [], [g[0]]
        for r in g[1:]:
            a = _dt.date.fromisoformat(cur[-1]["deal_date"]) if cur[-1].get("deal_date") else None
            b = _dt.date.fromisoformat(r["deal_date"]) if r.get("deal_date") else None
            if a and b and (b - a).days <= 3:
                cur.append(r)
            else:
                clusters.append(cur)
                cur = [r]
        clusters.append(cur)
        for c in clusters:
            addrs = {(r.get("street"), r.get("house"), r.get("project")) for r in c}
            if len(addrs) < 2:
                continue
            real = [r for r in c if r.get("street") and r.get("house") is not None]
            keep = real[0] if len(real) == 1 else None
            for r in c:
                if r is not keep:
                    r["bad"] = "dup_project"
    return rows


def madlan_rows(table, nb, file_name, known):
    """טבלת מדלן ([{כותרת: ערך}], מ-ibs_parse_table) → (שורות ל-market_upsert, סטטיסטיקה).
    כותרת חסרה → ValueError('headers'). העמודות לפי הכותרת, לא לפי המיקום."""
    heads = set()
    for t in table or []:
        heads |= {str(k).strip() for k in t.keys()}
    if not table or any(h not in heads for h in MADLAN_HEADERS):
        raise ValueError("headers")
    rows, seen, dups = [], set(), 0
    for t in table:
        t = {str(k).strip(): v for k, v in t.items()}
        a = parse_madlan_addr(t.get("כתובת"))
        price = _int(t.get("מחיר (₪)"))
        sqm = _int(t.get("שטח (מ״ר)")) or None
        r = {"source": "madlan", "nb": _norm(nb), "file_name": str(file_name or ""),
             "deal_date": _date(t.get("יום מכירה")), "city": a["city"],
             "street": canon_street(a["street"], known) if a["street"] else "", "house": a["house"],
             "project": a["project"], "ptype": _norm(t.get("סוג נכס")), "rooms": _rooms(t.get("חדרים")),
             "sqm": sqm, "floor": _norm(t.get("קומה")), "price": price,
             "ppm": int(round(price / sqm)) if price and sqm else None,
             "year_built": _int(t.get("שנת בנייה")), "bad": ""}
        if not r["deal_date"] or not price:
            continue
        if price < MIN_PRICE:
            r["bad"] = "price"
        elif r["ppm"] is not None and r["ppm"] < MIN_PPM:
            r["bad"] = "ppm"
        r["deal_key"] = deal_key(r)
        if r["deal_key"] in seen:
            dups += 1
            continue
        seen.add(r["deal_key"])
        rows.append(r)
    mark_dup_projects(rows)
    dates = sorted(r["deal_date"] for r in rows)
    st = {"n": len(rows), "dups": dups, "bad": sum(1 for r in rows if r["bad"]),
          "min_date": dates[0] if dates else None, "max_date": dates[-1] if dates else None,
          "streets": len({r["street"] for r in rows if r["street"]})}
    return rows, st
