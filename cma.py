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


# ── משימה 2: העסקאות שלנו, הנכס של בעל הנכס, וחישוב הטווח ──
MAX_COMPS = 7               # עד 7 עסקאות דומות (4 נתנו טווח רחב מדי בבגין 12 — הדמיה 06/11)
MIN_COMPS = 4               # פחות — אין טווח, ואין עמוד בתיק
SIZE_TOL = 0.20             # שטח ±20%
OUTLIER = 0.30              # מחיר למ"ר רחוק 30%+ מהחציון — חריג
YEARS = 3
SHOW_COMPS = 12


def city_key(c):
    """'קרית מוצקין' / 'ק. מוצקין' / 'מוצקין' → 'מוצקין' (להשוואה בלבד)."""
    t = _norm(c)
    t = re.sub(r"^(?:קרית|ק\s*\.)\s*", "", t)
    return t.strip()


def ptype_key(p):
    t = _norm(p)
    if "גן" in t:
        return "גן"
    if "פנטהאוז" in t or "גג" in t:
        return "גג"
    if "דופלקס" in t or "טריפלקס" in t:
        return "דופלקס"
    if "קוטג" in t or "משפחתי" in t or "וילה" in t or "בית פרטי" in t:
        return "בית"
    return "דירה"


def _split_street_house(s):
    """'מנחם בגין 12' / 'בגין12 ק.מוצקין' / 'מנחם בגין, קרית מוצקין' → (רחוב, בית|None, עיר-מהטקסט)."""
    t = _norm(s)
    city = ""
    if "," in t:
        t, city = t.split(",", 1)
    m = re.search(r"\s(ק\s*\.\s*\S+|קרית\s+\S+)\s*$", " " + t)
    if m and not city:
        city = m.group(1)
        t = (" " + t)[:m.start()]
    t = re.sub(r"([א-ת])(\d)", r"\1 \2", t).strip()
    mm = re.match(r"^([^\d]+?)\s*(\d+)", t)
    if mm:
        return mm.group(1).strip(" -,"), int(mm.group(2)), _norm(city)
    return t.strip(" -,"), None, _norm(city)


def ours_rows(dh_rows, known):
    """שורות deal_history → שורות שוק (source='ours'). מכירה בלבד, בלי שורות שנעלמו ובלי עתידיות;
    שני הצדדים של אותה עסקה (רחוב, בית, מחיר, עד 14 יום) — שורה אחת. לא נוגעים בלקוח/עמלה."""
    today = _dt.date.today().isoformat()
    out = []
    for r in dh_rows or []:
        side = str(r.get("side") or "")
        if "שוכר" in side or "משכיר" in side or r.get("missing_since"):
            continue
        d = str(r.get("deal_date") or "")[:10]
        price = _int(r.get("deal_amount"))
        if not d or d > today or not price:
            continue
        st, house, tcity = _split_street_house(r.get("street"))
        if not st:
            continue
        row = {"source": "ours", "deal_date": d, "city": _norm(r.get("city")) or tcity,
               "street": canon_street(st, known), "house": house, "price": price, "ours": True}
        dup = next((o for o in out if o["street"] == row["street"] and o["house"] == row["house"]
                    and o["price"] == price and abs((_dt.date.fromisoformat(o["deal_date"])
                                                     - _dt.date.fromisoformat(d)).days) <= 14), None)
        if dup:
            dup["deal_date"] = min(dup["deal_date"], d)
            continue
        out.append(row)
    return out


def link_ours(market, ours):
    """שורת מדלן ועסקה שלנו (אותו רחוב ובית, מחיר ±1%, תאריך ±21 יום) → שורה אחת עם ours=True.
    עסקה שלנו בלי שורה במדלן — נשארת, בלי חדרים ומ"ר."""
    out = [dict(r, ours=bool(r.get("ours"))) for r in market or []]
    for o in ours or []:
        od = _dt.date.fromisoformat(o["deal_date"])
        hit = None
        for r in out:
            if (r.get("street") == o["street"] and r.get("house") == o.get("house") and r.get("price")
                    and abs(r["price"] - o["price"]) <= 0.01 * o["price"] and r.get("deal_date")
                    and abs((_dt.date.fromisoformat(r["deal_date"]) - od).days) <= 21):
                hit = r
                break
        if hit:
            hit["ours"] = True
        else:
            out.append({"source": "ours", "nb": "", "deal_date": o["deal_date"], "city": o.get("city") or "",
                        "street": o["street"], "house": o.get("house"), "project": "", "ptype": "", "rooms": None,
                        "sqm": None, "floor": "", "price": o["price"], "ppm": None, "bad": "", "ours": True,
                        "uploaded_at": ""})
    return out


def subject_from_listing(listing):
    """פרטי הנכס מהתיק (שדות בעברית או באנגלית) → {street, house, city, rooms, sqm, ptype, price, key} או None."""
    g = lambda *ks: next((listing.get(k) for k in ks if listing.get(k) not in (None, "")), None)
    raw = g("רחוב", "רחוב1", "כתובת", "street")
    st, house, tcity = _split_street_house(raw) if raw else ("", None, "")
    hv = g("מספר בית", "house")
    if hv is not None and _int(hv) is not None:
        house = _int(hv)
    rooms = _rooms(g("חדרים", "rooms"))
    if not st or not rooms:
        return None
    return {"street": st, "house": house, "city": _norm(g("עיר / ישוב", "עיר", "city")) or tcity,
            "rooms": rooms, "sqm": _int(g("sqm", 'מ"ר')) or None, "ptype": _norm(g("ptype", "סוג נכס")) or "דירה",
            "price": _int(g("מחיר", "price")), "key": str(g("listing_key", "key") or "")}


def _same_street(r, subj):
    return r.get("street") == subj["street"] and (not r.get("city") or not subj.get("city")
                                                    or city_key(r["city"]) == city_key(subj["city"]))


def subject_nb(street, city, deals):
    cnt = {}
    for r in deals or []:
        if r.get("nb") and _same_street(r, {"street": street, "city": city}):
            cnt[r["nb"]] = cnt.get(r["nb"], 0) + 1
    return max(cnt, key=lambda k: (cnt[k], k)) if cnt else ""


def _round10k(x):
    return int(round(x / 10000.0)) * 10000


def _quart(vals):
    import statistics as _st
    v = sorted(vals)
    if len(v) == 1:
        return v[0], v[0]
    q = _st.quantiles(v, n=4, method="inclusive")
    return q[0], q[2]


def _median(vals):
    import statistics as _st
    return _st.median(vals)


def _rooms_ok(r, rooms, tol):
    return r.get("rooms") is not None and abs(float(r["rooms"]) - float(rooms)) <= tol + 1e-9


def cma_compute(subject, deals, listings, today):
    """הנכס + עסקאות (link_ours) + מודעות פעילות → נתוני העמוד והתצוגה לסוכן, או None כשאין מספיק."""
    since = today.replace(year=today.year - YEARS) if not (today.month == 2 and today.day == 29) \
        else today.replace(year=today.year - YEARS, day=28)
    since_s = since.isoformat()
    pk = ptype_key(subject.get("ptype"))
    nb = subject_nb(subject["street"], subject.get("city"), deals)
    ok = [r for r in deals or [] if not r.get("bad") and r.get("deal_date") and r["deal_date"] >= since_s
          and r.get("rooms") is not None and r.get("ptype") and ptype_key(r["ptype"]) == pk and r.get("price")]
    street = [r for r in ok if _same_street(r, subject)]
    nbrs = [r for r in ok if nb and r.get("nb") == nb and not _same_street(r, subject)]
    h = subject.get("house")
    street.sort(key=lambda r: (abs(r["house"] - h) if (h is not None and r.get("house") is not None) else 9999,
                               -_dt.date.fromisoformat(r["deal_date"]).toordinal()))
    nbrs.sort(key=lambda r: r["deal_date"], reverse=True)
    sqm = subject.get("sqm")

    def pick(tol):
        cands = [r for r in street + nbrs if _rooms_ok(r, subject["rooms"], tol)]
        rows = []
        for r in cands:
            c = {"street": r.get("street") or r.get("project") or "", "house": r.get("house"), "date": r["deal_date"],
                 "rooms": r.get("rooms"), "sqm": r.get("sqm"), "floor": r.get("floor") or "", "price": r["price"],
                 "ppm": r.get("ppm"), "ours": bool(r.get("ours")), "used": False, "reason": ""}
            if sqm and (not r.get("sqm") or abs(r["sqm"] - sqm) > SIZE_TOL * sqm):
                c["reason"] = "גדולה/קטנה מדי"
            rows.append(c)
        val = (lambda c: c["ppm"]) if sqm else (lambda c: c["price"])
        while True:
            chosen = [c for c in rows if not c["reason"] and val(c)][:MAX_COMPS]
            if len(chosen) < MIN_COMPS:
                return rows, chosen
            med = _median([val(c) for c in chosen])
            far = [c for c in chosen if abs(val(c) - med) > OUTLIER * med]
            if not far:
                return rows, chosen
            for c in far:
                c["reason"] = "חריג"

    rows, chosen = pick(0.5)
    if len(chosen) < MIN_COMPS:
        rows, chosen = pick(1.5)
    if len(chosen) < MIN_COMPS:
        return None
    for c in chosen:
        c["used"] = True
    for c in rows:   # מעבר ל-7 הקרובות — לא נפסלו, פשוט לא נדרשו
        c["extra"] = (not c["used"] and not c["reason"])
    if sqm:
        q1, q3 = _quart([c["ppm"] for c in chosen])
        rng, prng, basis = [_round10k(q1 * sqm), _round10k(q3 * sqm)], [int(round(q1)), int(round(q3))], "sqm"
    else:
        q1, q3 = _quart([c["price"] for c in chosen])
        rng, prng, basis = [_round10k(q1), _round10k(q3)], [], "price"
    # המספרים לבעל הנכס: כל העסקאות ברחוב באותו סוג ומספר חדרים בדיוק; פחות מ-3 → השכונה
    exact = lambda rs: [r for r in rs if _rooms_ok(r, subject["rooms"], 0.0)]
    s_cnt = exact(street)
    level = "street"
    if len(s_cnt) < 3:
        s_cnt, level = exact(street + nbrs), "neighborhood"
    pp = [r["ppm"] for r in s_cnt if r.get("ppm")]
    comp_l, seen = [], set()
    for x in listings or []:
        if x.get("delisted") or "שכ" in str(x.get("deal") or "") or str(x.get("key") or "") == subject.get("key"):
            continue
        st, hs, _c = _split_street_house(x.get("address"))
        if not _same_street({"street": canon_street(st, {subject["street"]}), "city": x.get("city")}, subject):
            continue
        if ptype_key(x.get("type")) != pk or not _rooms_ok({"rooms": _rooms(x.get("rooms"))}, subject["rooms"], 1.0):
            continue
        sig = (hs, _rooms(x.get("rooms")), _int(x.get("sqm")), _int(x.get("price")))
        if sig in seen:
            continue
        seen.add(sig)
        comp_l.append({"source": x.get("source") or "", "street": subject["street"], "house": hs,
                       "rooms": _rooms(x.get("rooms")), "sqm": _int(x.get("sqm")), "price": _int(x.get("price"))})
    up = sorted(str(r.get("uploaded_at") or "")[:10] for r in deals or []
                if r.get("uploaded_at") and (r.get("nb") == nb or _same_street(r, subject)))
    return {"title": "כמה שווה הנכס שלך",
            "subject": {k: subject.get(k) for k in ("street", "house", "city", "rooms", "sqm", "ptype")},
            "level": level, "street_count": len(s_cnt), "since_year": since.year,
            "ppm_median": int(round(_median(pp) / 100.0)) * 100 if pp else 0,
            "competing": len(comp_l), "range": rng, "ppm_range": prng, "basis": basis, "n_used": len(chosen),
            "comps": rows[:SHOW_COMPS], "listings": comp_l, "data_as_of": up[-1] if up else ""}


# ── משימה 3: cma_block (הוק התיק), ראוטים ומסך "ניתוח שוק" ──
STALE_DAYS = 45


def _today_il():
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    except Exception:
        return _dt.date.today()


def _known_streets(G, dh):
    known = set()
    for r in dh or []:
        st = _split_street_house(r.get("street"))[0]
        if st:
            known.add(st)
    try:
        rows, _l = G["_office_rows_for"]("")
        for r in rows or []:
            st = _split_street_house(r.get("כתובת"))[0]
            if st:
                known.add(st)
    except Exception:
        pass
    try:
        for r in G["fetch_newborn"]() or []:
            st = _split_street_house(r.get("רחוב1") or r.get("רחוב"))[0]
            if st:
                known.add(st)
    except Exception:
        pass
    return known


def _listings(G):
    """מודעות פעילות (משרד/שת"פ/נכס נולד) באותו מבנה של מודול הנכסים ב-CRM."""
    import effie_v2
    office = []
    try:
        rows, lbl = G["_office_rows_for"]("")
        office = [dict(r, **{"סוג עסקה": lbl}) if lbl and not r.get("סוג עסקה") else r for r in rows or []]
    except Exception:
        pass
    f = lambda k, d=None: G.get(k) or d
    h = {"nb_ep": f("_newborn_created_epoch", lambda r: 0), "nb_pkey": f("_nb_price_key", lambda r: ""),
         "nb_office": f("_nb_as_office_row", lambda r: {}),
         "excl_ep": lambda r: (f("_excl_epoch", lambda x: 0))(r.get("first_seen") or r.get("received_at") or ""),
         "excl_pkey": f("_excl_price_key", lambda r: ""), "prop_ep": f("_prop_epoch", lambda r: 0),
         "prop_pkey": f("_prop_price_key", lambda r: ""), "agent_name": lambda n: n or ""}
    recs = effie_v2.crm_props_records(G["fetch_newborn"]() or [], G["fetch_external_exclusives"]() or [], office,
                                      {}, 0, h)
    return [r for r in recs if not r.get("delisted") and "שכ" not in str(r.get("deal") or "")
            and "מסחר" not in str(r.get("deal") or "")]


def _inputs(G):
    today = _today_il()
    since = today.replace(year=today.year - YEARS - 1).isoformat()
    sb = G["_sbdb"]
    market = sb.market_all(since) or []
    dh = []
    try:
        dh = G["_deal_history_linked"]() or []
    except Exception:
        dh = []
    known = _known_streets(G, dh) | {r.get("street") for r in market if r.get("street")}
    deals = link_ours(market, ours_rows(dh, known))
    try:
        listings = _listings(G)
    except Exception:
        listings = []
    return deals, listings, known


def _cached_inputs(G):
    swr = G.get("_swr")
    return swr("cma:in", 600, lambda: _inputs(G)) if swr else _inputs(G)


def strip_addresses(res):
    """הגרסה שנשמרת בצילום התיק (ב-DB): בלי שם רחוב ובלי מספרי בית — לא של הנכס ולא של העסקאות
    (בקשת צ'אט התיק 08/11). נשארים הטווח, המספרים והשורות בלי כתובת."""
    if not res:
        return res
    out = {k: v for k, v in res.items() if k not in ("subject", "comps", "listings")}
    out["subject"] = {k: v for k, v in (res.get("subject") or {}).items() if k not in ("street", "house")}
    out["comps"] = [{k: v for k, v in c.items() if k not in ("street", "house")} for c in res.get("comps") or []]
    out["listings"] = [{k: v for k, v in x.items() if k not in ("street", "house")} for x in res.get("listings") or []]
    return out


def cma_block(G, listing):
    """הוק תיק הפרזנטציה: פרטי הנכס → נתוני עמוד ה-CMA בלי כתובות (strip_addresses), או None."""
    return strip_addresses(cma_full(G, listing))


def cma_full(G, listing):
    """פרטי הנכס → cma_compute המלא (עם כתובות — לתצוגה לסוכן בלבד), או None. כשל → None + אזהרה בלוג."""
    try:
        subj = subject_from_listing(listing or {})
        if not subj:
            return None
        deals, listings, known = _cached_inputs(G)
        subj["street"] = canon_street(subj["street"], known)
        return cma_compute(subj, deals, listings, _today_il())
    except Exception as e:
        lg = G.get("log")
        if lg:
            lg.warning(f"cma_block: {e}")
        return None


def register(app, G):
    from flask import jsonify, request

    def _owner(s):
        return bool(s) and (s.get("dev") or bool(G["_is_dev"](s.get("phone", ""))))

    def _act(s, action, detail):
        try:
            G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), action, detail)
        except Exception:
            pass

    @app.route("/v2/api/cma/upload", methods=["POST"])
    def cma_upload():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "reason": "auth"}), 401
        if not _owner(s):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        import base64
        b = request.get_json(silent=True) or {}
        nb = _norm(b.get("nb"))[:60]
        if not nb:
            return jsonify({"ok": False, "reason": "nb"})
        try:
            raw = base64.b64decode(str(b.get("data") or "").split(",")[-1] or b"")
        except Exception:
            raw = b""
        if not raw:
            return jsonify({"ok": False, "reason": "no_file"})
        try:
            import effie_v2
            table = effie_v2.ibs_parse_table(str(b.get("name") or "t.xlsx"), raw)
        except Exception:
            return jsonify({"ok": False, "reason": "headers"})
        try:
            dh = G["_deal_history_linked"]() or []
        except Exception:
            dh = []
        try:
            rows, st = madlan_rows(table, nb, str(b.get("name") or ""), _known_streets(G, dh))
        except ValueError:
            return jsonify({"ok": False, "reason": "headers"})
        G["_sbdb"].market_upsert(rows)
        _act(s, "עסקאות ממדלן — העלאה", "%s · %d עסקאות" % (nb, st["n"]))
        return jsonify({"ok": True, "stats": st})

    @app.route("/v2/api/cma/files", methods=["GET"])
    def cma_files():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "reason": "auth"}), 401
        if not _owner(s):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        files = G["_sbdb"].market_files() or []
        lim = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=STALE_DAYS)).isoformat()
        return jsonify({"ok": True, "files": files,
                        "stale": [f["nb"] for f in files if str(f.get("last_upload") or "") < lim]})

    @app.route("/v2/api/cma/view", methods=["GET"])
    def cma_view():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "reason": "auth"}), 401
        a = request.args
        res = cma_full(G, {"street": a.get("street", ""), "house": a.get("house", ""), "city": a.get("city", ""),
                            "rooms": a.get("rooms", ""), "sqm": a.get("sqm", ""), "ptype": a.get("ptype", "")})
        return jsonify({"ok": True, "cma": res, "reason": "" if res else "few"})


V2_CMA_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>ניתוח שוק</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--cream:#F2EFE7;--navy:#1E3A5F;--navy0:#0E1D33;--navy2:#2C4C77;--blue:#2E6BD6;--gold:#C29435;--gold2:#E4C56B;
  --goldtxt:#7A5E1C;--ink:#14192B;--mut:#5B6472;--mut2:#6B7280;--line:#E6E1D6;--shadow:0 6px 20px rgba(30,58,95,.06)}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:'Heebo',sans-serif;background:var(--cream);color:var(--ink);min-height:100dvh}
button,input,select{font-family:inherit;font-size:16px}
.hero{background:linear-gradient(160deg,var(--navy0),var(--navy2));color:#fff;padding:calc(env(safe-area-inset-top,0px) + 12px) 16px 18px;border-radius:0 0 26px 26px}
.top{display:flex;align-items:center;gap:10px}
.back{width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;color:#fff;text-decoration:none;font-size:20px}
h1{font-size:21px;font-weight:800}.sub{font-size:12.5px;opacity:.8}
.wrap{max-width:720px;margin:0 auto;padding:14px 16px 40px}
.card{background:#fff;border-radius:22px;box-shadow:var(--shadow);padding:16px;margin-bottom:12px}
.f{display:grid;grid-template-columns:2fr 1fr;gap:8px}.f3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:8px}
label{font-size:12px;color:var(--mut);display:block;margin-bottom:3px}
input,select{width:100%;min-height:44px;border:1.5px solid var(--line);border-radius:12px;padding:0 10px;background:#fff}
.go{margin-top:12px;width:100%;min-height:48px;border:0;border-radius:14px;background:var(--blue);color:#fff;font-weight:800}
.kick{font-size:12px;color:var(--goldtxt);font-weight:700}
.big{font-size:30px;font-weight:800;color:var(--navy)}.lbl{font-size:12.5px;color:var(--mut)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.rng{background:linear-gradient(135deg,var(--gold),var(--gold2));color:#231700;border-radius:20px;padding:16px;text-align:center;margin-bottom:12px}
.rng .big{color:#231700;font-size:clamp(20px,6.4vw,30px);white-space:nowrap}
.cr{display:grid;grid-template-columns:1fr auto;gap:2px 8px;padding:9px 0;border-bottom:1px solid #F1EDE3;font-size:13.5px}
.cr:last-child{border:0}.cr b{font-variant-numeric:tabular-nums}.cr .m{grid-column:1/-1;font-size:12px;color:var(--mut2)}
.cr.ex{color:#6B7280}.cr.out{color:#A7ADB7}.cr.out .a,.cr.out b{text-decoration:line-through}
.chip{font-size:11px;font-weight:700;border-radius:8px;padding:1px 7px;margin-inline-start:5px}
.ours{background:#FBF4E2;color:var(--goldtxt)}.why{background:#F1F1F1;color:var(--mut2)}
.empty{text-align:center;padding:26px 10px}.dot{width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,var(--gold),var(--gold2));margin:0 auto 10px;display:grid;place-items:center;color:#231700;font-size:24px;font-weight:800}
.h{font-size:14px;font-weight:800;color:var(--navy);margin-bottom:4px}
</style></head><body>
<div class="hero"><div class="top"><a class="back" href="/v2/home" aria-label="חזרה">&#8250;</a>
<div><h1>ניתוח שוק</h1><div class="sub">טווח מחיר מעסקאות אמיתיות ב-3 השנים האחרונות</div></div></div></div>
<div class="wrap">
<div class="card" id="form">
 <div class="f"><div><label for="st">רחוב</label><input id="st" autocomplete="off"></div>
  <div><label for="hs">מספר בית</label><input id="hs" inputmode="numeric"></div></div>
 <div style="margin-top:8px"><label for="ct">עיר</label><input id="ct" value="קרית מוצקין"></div>
 <div class="f3"><div><label for="rm">חדרים</label><input id="rm" inputmode="decimal"></div>
  <div><label for="sq">מ"ר (רשות)</label><input id="sq" inputmode="numeric"></div>
  <div><label for="pt">סוג</label><select id="pt"><option>דירה</option><option>דירת גן</option><option>פנטהאוז</option><option>דופלקס</option><option>קוטג'</option></select></div></div>
 <button class="go" onclick="run()">חשב</button>
</div>
<div id="res"></div>
</div>
<script>
var TOK = null; try{ TOK = localStorage.getItem('fbTok'); }catch(e){}
function el(i){ return document.getElementById(i); }
// CMA-FN-START
function cmaEsc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function cmaFmt(n){ if (n == null || n === '') return ''; return String(Math.round(Number(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function cmaDate(iso){ var p = String(iso || '').split('-'); return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : ''; }
function cmaRow(c){
  var addr = cmaEsc(c.street) + (c.house != null ? ' ' + cmaEsc(c.house) : '');
  var meta = [cmaDate(c.date), c.rooms != null ? cmaEsc(c.rooms) + ' חד׳' : '', c.sqm ? cmaEsc(c.sqm) + ' מ"ר' : '',
              c.floor !== '' && c.floor != null ? 'קומה ' + cmaEsc(c.floor) : '', c.ppm ? cmaFmt(c.ppm) + ' ₪ למ"ר' : ''].filter(Boolean).join(' · ');
  return '<div class="cr' + (c.used ? '' : (c.extra ? ' ex' : ' out')) + '"><span class="a">' + addr +
    (c.ours ? '<span class="chip ours">עסקה שלנו</span>' : '') +
    (!c.used && c.reason ? '<span class="chip why">' + cmaEsc(c.reason) + '</span>' : '') +
    '</span><b>' + cmaFmt(c.price) + '</b><span class="m">' + meta + '</span></div>';
}
function cmaResult(j){
  var m = j && j.cma;
  if (!m) return '<div class="card empty"><div class="dot">?</div><div class="h">אין מספיק עסקאות דומות</div>' +
    '<div class="lbl">נסה בלי מ"ר, או בדוק שהשכונה הועלתה בכרטיס "עסקאות ממדלן" בניהול.</div></div>';
  var where = m.level === 'street' ? 'ב' + cmaEsc(m.subject.street) : 'בשכונה';
  var h = '<div class="rng"><div class="lbl" style="color:#231700">טווח מומלץ</div><div class="big">' +
    cmaFmt(m.range[0]) + ' – ' + cmaFmt(m.range[1]) + ' ₪</div><div class="lbl" style="color:#231700">' +
    (m.basis === 'sqm' ? cmaFmt(m.ppm_range[0]) + '–' + cmaFmt(m.ppm_range[1]) + ' ₪ למ"ר · ' : 'בלי שטח — לפי מחיר עסקאות בלבד · ') +
    'מבוסס על ' + m.n_used + ' עסקאות</div></div>';
  h += '<div class="card"><div class="kick">מה בעל הנכס רואה בתיק</div><div class="grid2" style="margin-top:8px">' +
    '<div><div class="big">' + m.street_count + '</div><div class="lbl">דירות ' + cmaEsc(m.subject.rooms) + ' חדרים נמכרו ' + where + ' מאז ' + m.since_year + '</div></div>' +
    '<div><div class="big">' + cmaFmt(m.ppm_median) + '</div><div class="lbl">מחיר ממוצע למ"ר</div></div>' +
    '<div><div class="big">' + m.competing + '</div><div class="lbl">דירות דומות מתחרות עכשיו</div></div></div></div>';
  h += '<div class="card"><div class="h">העסקאות — לפי הקרבה לבית</div>' + (m.comps || []).map(cmaRow).join('') + '</div>';
  if ((m.listings || []).length) h += '<div class="card"><div class="h">מתחרות עכשיו</div>' + m.listings.map(function(x){
    return '<div class="cr"><span class="a">' + cmaEsc(x.street) + (x.house != null ? ' ' + cmaEsc(x.house) : '') + ' · ' + cmaEsc(x.source) +
      '</span><b>' + cmaFmt(x.price) + '</b><span class="m">' + [x.rooms != null ? cmaEsc(x.rooms) + ' חד׳' : '', x.sqm ? cmaEsc(x.sqm) + ' מ"ר' : ''].filter(Boolean).join(' · ') + '</span></div>';
  }).join('') + '</div>';
  if (m.data_as_of) h += '<div class="lbl" style="text-align:center">נתוני עסקאות מעודכנים ל-' + cmaDate(m.data_as_of) + '</div>';
  return h;
}
// CMA-FN-END
function run(){
  var q = ['street=' + encodeURIComponent(el('st').value.trim()), 'house=' + encodeURIComponent(el('hs').value.trim()),
           'city=' + encodeURIComponent(el('ct').value.trim()), 'rooms=' + encodeURIComponent(el('rm').value.trim()),
           'sqm=' + encodeURIComponent(el('sq').value.trim()), 'ptype=' + encodeURIComponent(el('pt').value)].join('&');
  el('res').innerHTML = '<div class="card lbl">מחשב…</div>';
  fetch('/v2/api/cma/view?' + q, {headers: {'X-Auth-Token': TOK}}).then(function(r){
    if (r.status === 401){ location.replace('/v2'); return null; } return r.json();
  }).then(function(j){ if (j) el('res').innerHTML = cmaResult(j); })
    .catch(function(){ el('res').innerHTML = '<div class="card lbl">שגיאת רשת — נסה שוב</div>'; });
}
</script></body></html>'''
