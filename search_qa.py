# search_qa.py — [SEARCH-QA 04/11 אייל] 'מנגנון שישפר את החיפושים ותוצאות החיפוש וישלח לי המלצות לתיקון'.
# כל יום ראשון: כל חיפושי הנכסים מהשבוע (אפי + האתר, מיומן הפעילות) רצים שוב דרך אותו מנוע, נבדקים אוטומטית
# (כמו הבדיקה הידנית של 46 החיפושים ב-22/10), ובעל המשרד מקבל מייל עם הבעיות מקובצות, דוגמאות והמלצה לכל קבוצה.
# שום דבר לא משתנה אוטומטית. פונקציות טהורות; ההרצה והשליחה ב-app.py (_search_qa_tick).
import html as _h
import re
import time as _t

ACT_EFFIE = "חיפוש נכסים"     # אפי — הטקסט כמו שהוקלד
ACT_SITE = "חיפוש AI באתר"    # האתר — 'טקסט · N נכסים'
REQUERY_SEC = 300              # חיפוש נוסף של אותו אדם תוך 5 דק' בניסוח אחר = התוצאות הראשונות לא עזרו
TOP = 10                       # בודקים את 10 התוצאות הראשונות (מה שרואים)

CATS = ("מנוע החיפוש", "נתונים", "הזדמנות עסקית")

# קוד → (כותרת, סוג, המלצה)
KINDS = {
    "zero": ("חיפושים בלי אף תוצאה", "מנוע החיפוש",
             "אם האזור שלנו והמשפט ברור — כנראה הפירוק החמיר מדי (תקציב, חדרים או סוג נכס). כדאי שהמנוע יציע "
             "אוטומטית את הקרוב ביותר במקום רשימה ריקה. אם האזור מחוץ לקריות — אין מה לתקן."),
    "parse_fail": ("ה-AI לא הבין את המשפט", "מנוע החיפוש",
                   "לרוב קיצור, שגיאת כתיב או משפט לא בעברית. אם הניסוח חוזר — ללמד את הפירוק את הצורה הזו."),
    "requery": ("חיפשו שוב בניסוח אחר תוך 5 דקות", "מנוע החיפוש",
                "הסימן הכי אמין שהתוצאות הראשונות לא עזרו. ההבדל בין הניסוח הראשון לשני מראה מה המנוע פספס."),
    "deal": ("השכרה ומכירה התבלבלו", "מנוע החיפוש",
             "בקשה להשכרה שהובנה כמכירה (או להפך). לקבוע את סוג העסקה לפי המילים בטקסט, בלי לסמוך על ה-AI."),
    "area": ("רוב התוצאות בעיר אחרת", "מנוע החיפוש",
             "העיר שנכתבה לא תואמת את רוב התוצאות. לבדוק את מיפוי הערים והשכונות (כמו 'חיים' = קרית חיים)."),
    "strict": ("'רק ב…' ובכל זאת שכונה אחרת", "מנוע החיפוש",
               "נכתב 'רק ב…' אבל נכנסו נכסים משכונה אחרת — הכלל מ-28/10 לא תפס כאן."),
    "rooms": ("מספר חדרים רחוק מהמבוקש", "מנוע החיפוש",
              "בין 10 הראשונות יש נכסים עם פחות חדרים מהמבוקש או יותר מ-2 חדרים מעליו."),
    "budget": ("מעל התקציב בין הראשונות", "מנוע החיפוש",
               "נכס יקר ביותר מ-10% מהתקציב בין 5 התוצאות הראשונות."),
    "budget_order": ("מעל התקציב לפני בתוך התקציב", "מנוע החיפוש",
                     "נכס מעל התקציב מדורג לפני נכס שבתוך התקציב — סותר את הכלל מ-28/10."),
    "type": ("סוג נכס אחר", "מנוע החיפוש",
             "ביקשו סוג מסוים (פנטהאוז, קוטג', דירת גן…) ורוב התוצאות מסוג אחר."),
    "must_not": ("'ללא X' ובכל זאת יש X", "מנוע החיפוש",
                 "תוצאה עם תכונה שהלקוח ביקש בלעדיה (למשל 'ללא מעלית')."),
    "must_have": ("'עם X' ובתוצאה כתוב שאין", "מנוע החיפוש",
                  "תוצאה שבתיאור שלה כתוב שאין את התכונה שביקשו."),
    "missed": ("מילה שנכתבה לא נכנסה לחיפוש", "מנוע החיפוש",
               "חדרים, תקציב או עיר שנכתבו במפורש והפירוק פספס. כלל טקסט קבוע יתפוס את זה בלי AI."),
    "few": ("רק 1–2 תוצאות", "הזדמנות עסקית",
            "ביקוש שיש לנו בו מעט מלאי — כדאי שהסוכנים ידעו שמחפשים את זה."),
    "no_inventory": ("רחוב או שכונה בלי אף נכס שלנו", "הזדמנות עסקית",
                     "מחפשים שם ואין לנו נכס — כיוון לגיוס מוכרים באזור."),
    "data_nb": ("נכסים בלי שם שכונה", "נתונים",
                "נכס בלי שכונה לא נתפס בחיפוש לפי שכונה. לבקש מהסוכן להשלים את השכונה במודעה ביד2."),
}

# בבדיקה הקבועה — מה לא נחשב כשל (מצב מלאי, לא מנוע)
REG_OK = {"few", "no_inventory", "data_nb"}

# בדיקה קבועה — חיפושים שתוקנו בעבר. רצים כל שבוע כדי שתיקון לא יישבר בשקט.
REGRESSION = [
    "דירה להשכרה בקרית ביאליק",
    "דו משפחתי בקרית מוצקין",
    "4 חדרים בביאליק או מוצקין או חיים",
    "עד 1.7M בקרית ביאליק",
    "רחוב הדקל קרית מוצקין",
    "רק במשכנות האומנים",
    "3-4 חדרים עם מעלית עד 1.4 מיליון",
    "עד קומה 2 ללא מעלית עם מרפסת",
    "5 חדרים באפקה",
    "דירת 4 חדרים בקרית ביאליק עד 2 מיליון",
    "פנטהאוז עד 5 מיליון",
    "דירת גן בקרית ים",
]

_CITY_WORDS = (("ביאליק", "ביאליק"), ("מוצקין", "מוצקין"), ("אתא", "אתא"), ("חיים", "חיים"),
               ("שמואל", "שמואל"), ("קרית ים", "ים"), ("חיפה", "חיפה"))
_RENT_RE = r"השכרה|להשכיר|שכירות|לשכור|שכ\"ד|שכ״ד"
_SALE_RE = r"למכירה|לקנות|קנייה|קניה"
_TYPE_GROUPS = ({"קוטג'", "קוטג", "בית פרטי", "דו משפחתי", "דו-משפחתי", "וילה", "מיני קוטג'"},
                {"דירת גן", "גן"},
                {"פנטהאוז", "דירת גג", "גג", "דופלקס גג"},
                {"דופלקס"})


def _norm_q(q):
    return re.sub(r"\s+", " ", str(q or "")).strip()


def _city(s):
    return re.sub(r"\s+", " ", str(s or "").replace("קריית", "קרית")).strip()


def _num(v):
    s = re.sub(r"[^\d.]", "", str(v or ""))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def collect(acts):
    """יומן הפעילות → [{q, n, src:set, ts, requery}] — חיפוש ייחודי (רווחים מנורמלים) עם מונה ומקור.
    requery = הניסוח הבא של אותו אדם אם חיפש שוב תוך 5 דק' (באפי בלבד — באתר אין זהות)."""
    out, by_phone = {}, {}
    for a in acts or []:
        act = str(a.get("action") or "")
        det = str(a.get("detail") or "")
        if act == ACT_EFFIE:
            src, q = "אפי", _norm_q(det)
        elif act == ACT_SITE:
            src, q = "אתר", _norm_q(re.sub(r"\s*·\s*\d+\s*נכסים\s*$", "", det))
        else:
            continue
        if not q or q.startswith("("):
            continue
        it = out.setdefault(q, {"q": q, "n": 0, "src": set(), "ts": 0.0})
        it["n"] += 1
        it["src"].add(src)
        it["ts"] = max(it["ts"], float(a.get("ts") or 0))
        if src == "אפי" and a.get("phone"):
            by_phone.setdefault(str(a["phone"]), []).append((float(a.get("ts") or 0), q))
    for seq in by_phone.values():
        seq.sort()
        for (t1, q1), (t2, q2) in zip(seq, seq[1:]):
            if q1 != q2 and 0 < t2 - t1 <= REQUERY_SEC and not out[q1].get("requery"):
                out[q1]["requery"] = q2
    return sorted(out.values(), key=lambda x: (-x["n"], -x["ts"]))


def _area_txt(parsed):
    p = parsed or {}
    parts = [p.get("street") or "", p.get("neighborhood") or "", ", ".join(p.get("neighborhoods") or []),
             p.get("city") or "", ", ".join(p.get("cities") or [])]
    return " · ".join(x for x in (str(y).strip() for y in parts) if x)


def _row_in_area(r, cities):
    rc, rn = _city(r.get("עיר / ישוב")), _city(r.get("שכונה"))
    for c in cities:
        if not c:
            continue
        if rc and (c in rc or rc in c):
            return True
        if rn and c in rn:            # 'קרית חיים' רשומה ביד2 כשכונה של חיפה
            return True
        if not rc:
            return True               # בלי עיר — לא נפסל
    return False


def _type_ok(want, have):
    want, have = str(want or "").strip(), str(have or "").strip()
    if not have or want in have or have in want:
        return True
    return any(want in g and any(x in have for x in g) for g in _TYPE_GROUPS)


def check_search(q, parsed, matches, note="", feature_state=None):
    """חיפוש אחד שרץ שוב → רשימת בעיות [{code, info, rows?}]. matches = [(score, row, flex)]."""
    iss = []
    add = lambda code, info="", **kw: iss.append(dict(code=code, info=str(info), **kw))
    t = str(q or "")
    if not parsed:
        add("parse_fail")
        return iss
    rows = [m[1] if isinstance(m, (tuple, list)) else m for m in (matches or [])]
    top = rows[:TOP]
    if not rows:
        add("zero", _area_txt(parsed), area=_area_txt(parsed))
    elif len(rows) <= 2:
        add("few", "%d תוצאות" % len(rows), area=_area_txt(parsed))

    deal = str(parsed.get("deal_type") or "")
    if re.search(_RENT_RE, t) and "שכר" not in deal:
        add("deal", "נכתב השכרה, הובן " + (deal or "מכירה"))
    elif "שכר" in deal and not re.search(_RENT_RE, t) and re.search(_SALE_RE, t):
        add("deal", "נכתב מכירה, הובן השכרה")

    cities = [_city(c) for c in ([parsed.get("city")] + list(parsed.get("cities") or [])) if c]
    if cities and top:
        bad = [r for r in top if not _row_in_area(r, cities)]
        if len(bad) * 2 > len(top):
            add("area", "%d מתוך %d ב%s" % (len(bad), len(top), _city(bad[0].get("עיר / ישוב")) or "עיר אחרת"))
    nbs = [str(n).strip() for n in ([parsed.get("neighborhood")] + list(parsed.get("neighborhoods") or [])) if n and str(n).strip()]
    if parsed.get("_strict_area") and nbs and top:
        bad = [r for r in top if (r.get("שכונה") or "").strip() and not any(n in r.get("שכונה", "") for n in nbs)]
        if bad:
            add("strict", "%s ב%s" % (bad[0].get("כתובת", ""), bad[0].get("שכונה", "")))
    if nbs and top:
        miss = [r for r in top if not str(r.get("שכונה") or "").strip() and (not cities or _row_in_area(r, cities))]
        if miss:
            add("data_nb", "%d נכסים בלי שכונה" % len(miss),
                rows=[{"addr": ("%s %s, %s" % (r.get("כתובת", ""), r.get("מספר בית", "") or "", r.get("עיר / ישוב", ""))).replace(" ,", ",").strip(),
                       "agent": str(r.get("סוכן 1") or "").strip() or "—"} for r in miss])

    rmin, rmax = _num(parsed.get("rooms_min")), _num(parsed.get("rooms_max"))
    if (rmin or rmax) and top:
        lo, hi = (rmin or 0) - 0.5, (rmax or rmin) + 2
        bad = [r for r in top if _num(r.get("חדרים")) is not None and not (lo <= _num(r.get("חדרים")) <= hi)]
        if len(bad) * 3 > len(top):
            add("rooms", "%d מתוך %d (למשל %s חד')" % (len(bad), len(top), r"%g" % _num(bad[0].get("חדרים"))))

    bmax = _num(parsed.get("budget_max"))
    if bmax and top:
        prices = [_num(r.get("מחיר")) for r in top]
        over = [p for p in prices[:5] if p and p > bmax * 1.10]
        if over:
            add("budget", "%s מול תקציב %s" % (_money(max(over)), _money(bmax)))
        first_over = next((i for i, p in enumerate(prices) if p and p > bmax), None)
        last_in = max((i for i, p in enumerate(prices) if p and p <= bmax), default=None)
        if first_over is not None and last_in is not None and first_over < last_in:
            add("budget_order", "%s במקום %d, ו-%s במקום %d" % (_money(prices[first_over]), first_over + 1,
                                                                 _money(prices[last_in]), last_in + 1))

    want = str(parsed.get("property_type") or "").strip()
    if want and want != "דירה" and top:
        bad = [r for r in top if not _type_ok(want, r.get("סוג נכס"))]
        if len(bad) * 2 > len(top):
            add("type", "ביקשו %s, %d מתוך %d %s" % (want, len(bad), len(top), bad[0].get("סוג נכס") or "אחר"))

    if feature_state and top:
        for f in parsed.get("must_not") or []:
            hit = [r for r in top if _safe(feature_state, r, f) is True]
            if hit:
                add("must_not", "ללא %s — %s" % (f, hit[0].get("כתובת", "")))
        for f in parsed.get("must_have") or []:
            if str(f).strip() in ("גינה",):
                continue
            hit = [r for r in top if _safe(feature_state, r, f) is False]
            if hit:
                add("must_have", "עם %s — %s" % (f, hit[0].get("כתובת", "")))

    missed = []
    if re.search(r"\d(?:\.5)?\s*(?:-\s*\d(?:\.5)?\s*)?חד", t) and not (rmin or rmax):
        missed.append("חדרים")
    if re.search(r"\d(?:[.,]\d+)?\s*(?:מיליון|מליון|מ'|M\b|m\b|אלף)|עד\s*\d", t) and not bmax and not parsed.get("floor_max"):
        missed.append("תקציב")
    known = " ".join(str(x) for x in (parsed.get("city"), parsed.get("cities"), parsed.get("neighborhood"),
                                      parsed.get("neighborhoods"), parsed.get("street")) if x)
    for word, key in _CITY_WORDS:
        if re.search(r"(?:^|[\s,])(?:[בולה]|מ)?" + re.escape(word) + r"(?=$|[\s,.])", t) and key not in known:
            if key == "חיים" and "חיים" in known:
                continue
            missed.append(word)
            break
    if missed:
        add("missed", " · ".join(missed))

    if note:
        m = re.match(r"אין לנו כרגע נכס (?:ברחוב |ב)(.+?)(?:\s*·|$)", str(note))
        area = (m.group(1).strip() if m else str(note)[:60])
        if "ברחוב" in str(note)[:20]:
            area = "רחוב " + area
        city = parsed.get("city") or ", ".join(parsed.get("cities") or [])
        add("no_inventory", area, area=(area + (", " + city if city and city not in area else "")))
    return iss


def _safe(fn, r, f):
    try:
        return fn(r, f, f)
    except Exception:
        return None


def _money(v):
    v = float(v or 0)
    if v >= 1e6:
        return ("%.2f" % (v / 1e6)).rstrip("0").rstrip(".") + "M"
    return "{:,.0f}".format(v)


def build_report(results, regression=None):
    """results = [{q, n, src, count, issues, requery?}] → דוח מקובץ.
    count של קבוצה = כמה פעמים חיפשו את החיפושים שבה (לא רק כמה ניסוחים)."""
    groups, demand, nbrows = {}, {}, {}
    total = sum(int(r.get("n") or 1) for r in results or [])
    clean = 0
    for r in results or []:
        n = int(r.get("n") or 1)
        src = "/".join(sorted(r.get("src") or []))
        iss = list(r.get("issues") or [])
        if r.get("requery"):
            iss.append({"code": "requery", "info": "אחר כך: " + str(r["requery"])})
        if not [i for i in iss if i["code"] not in ("few", "no_inventory", "data_nb")]:
            clean += n
        seen = set()
        for i in iss:
            c = i["code"]
            if c in seen or c not in KINDS:
                continue
            seen.add(c)
            g = groups.setdefault(c, {"code": c, "title": KINDS[c][0], "cat": KINDS[c][1], "rec": KINDS[c][2],
                                      "count": 0, "queries": 0, "examples": []})
            g["count"] += n
            g["queries"] += 1
            if len(g["examples"]) < 3:
                g["examples"].append({"q": r["q"], "src": src, "info": i.get("info", ""), "n": n})
            if c in ("zero", "no_inventory") and i.get("area"):
                d = demand.setdefault(i["area"], {"area": i["area"], "count": 0, "examples": []})
                d["count"] += n
                if len(d["examples"]) < 2:
                    d["examples"].append(r["q"])
            if c == "data_nb":
                for x in i.get("rows") or []:
                    k = (x["addr"], x["agent"])
                    nbrows[k] = nbrows.get(k, 0) + n
    order = {c: i for i, c in enumerate(CATS)}
    gl = sorted(groups.values(), key=lambda g: (-g["count"], order.get(g["cat"], 9)))
    reg = None
    if regression is not None:
        reg = {"total": len(regression), "ok": sum(1 for x in regression if x.get("ok")),
               "fails": [x for x in regression if not x.get("ok")]}
    return {"total": total, "unique": len(results or []), "clean": clean,
            "by_src": {s: sum(int(r.get("n") or 1) for r in results or [] if s in (r.get("src") or ())) for s in ("אפי", "אתר")},
            "groups": gl,
            "demand": sorted(demand.values(), key=lambda d: -d["count"])[:12],
            "data_nb": [{"addr": a, "agent": g, "count": c} for (a, g), c in sorted(nbrows.items(), key=lambda kv: -kv[1])][:15],
            "regression": reg}


def regression_result(q, issues):
    bad = [i for i in issues or [] if i["code"] not in REG_OK]
    return {"q": q, "ok": not bad, "why": " · ".join(KINDS.get(i["code"], (i["code"],))[0] + (" (" + i["info"] + ")" if i.get("info") else "")
                                                    for i in bad)}


def due(now, rec, hour, now_ts=None):
    """יום ראשון מ-hour ואילך, פעם אחת; כשל → ניסיון חוזר כל 15 דק', עד 8."""
    now_ts = _t.time() if now_ts is None else now_ts
    rec = rec or {}
    if now.weekday() != 6 or now.hour < hour or rec.get("ok"):
        return False
    return int(rec.get("tries") or 0) < 8 and (now_ts - float(rec.get("ts") or 0)) >= 900


def render(rep, office, rng):
    """→ (נושא, html, טקסט). מייל בעברית מימין לשמאל, טבלאות עם עיצוב מוטמע (כמו הסיכום השבועי)."""
    e = lambda x: _h.escape(str(x if x is not None else ""))
    F = "font-family:Heebo,Arial,sans-serif"
    subject = "בקרת חיפושים · %s · %s" % (office or "המשרד", rng)
    pct = round(100 * rep["clean"] / rep["total"]) if rep["total"] else 100
    td = f"padding:7px 6px;{F};font-size:13px;color:#1E3A5F;border-bottom:1px solid #F0EDE3;vertical-align:top"
    th = f"padding:6px;{F};font-size:11.5px;color:#6B7280;font-weight:700;border-bottom:1px solid #E9E4D8;text-align:right"
    catc = {"מנוע החיפוש": "#2E6BD6", "נתונים": "#7A5E1C", "הזדמנות עסקית": "#157A43"}

    def card(title, small, body):
        return (f"<tr><td style='padding:6px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#fff;border-radius:18px'>"
                f"<tr><td style='padding:14px 16px'><div style='{F};font-size:16px;font-weight:800;color:#1E3A5F;margin-bottom:6px'>{e(title)} "
                f"<span style='font-size:11.5px;color:#6B7280;font-weight:500'>{e(small)}</span></div>{body}</td></tr></table></td></tr>")

    tiles = "".join(
        f"<td width='25%' valign='top' style='padding:4px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#fff;border-radius:16px'>"
        f"<tr><td style='padding:10px 12px;{F}'><div style='font-size:12px;color:#7A5E1C;font-weight:700'>{e(k)}</div>"
        f"<div style='font-size:26px;font-weight:800;color:#1E3A5F'>{e(v)}</div></td></tr></table></td>"
        for k, v in (("חיפושים", rep["total"]), ("ניסוחים שונים", rep["unique"]),
                     ("אפי / אתר", "%d / %d" % (rep["by_src"].get("אפי", 0), rep["by_src"].get("אתר", 0))), ("בלי בעיה", "%d%%" % pct)))
    rows = [f"<tr><td style='padding:2px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>{tiles}</tr></table></td></tr>"]
    L = [subject, "", "חיפושים: %d · ניסוחים שונים: %d · אפי %d / אתר %d · בלי בעיה %d%%" % (
        rep["total"], rep["unique"], rep["by_src"].get("אפי", 0), rep["by_src"].get("אתר", 0), pct)]

    reg = rep.get("regression")
    if reg:
        body = (f"<div style='{F};font-size:13px;color:#1E3A5F'>{reg['ok']} מתוך {reg['total']} עברו.</div>"
                + "".join(f"<div style='{F};font-size:13px;color:#C24040;margin-top:4px'>• {e(x['q'])} — {e(x.get('why'))}</div>" for x in reg["fails"]))
        rows.append(card("בדיקה קבועה", "חיפושים שתוקנו בעבר — שלא יישברו", body))
        L += ["", "בדיקה קבועה: %d/%d" % (reg["ok"], reg["total"])] + ["  ✗ %s — %s" % (x["q"], x.get("why", "")) for x in reg["fails"]]

    if rep["groups"]:
        for g in rep["groups"]:
            ex = "".join(f"<tr><td style='{td}'>{e(x['q'])}</td><td style='{td};white-space:nowrap;color:#6B7280'>{e(x['src'])}{(' ×' + str(x['n'])) if x['n'] > 1 else ''}</td>"
                         f"<td style='{td};color:#5B6472'>{e(x['info'])}</td></tr>" for x in g["examples"])
            body = (f"<div style='{F};font-size:11.5px;font-weight:700;color:{catc.get(g['cat'], '#1E3A5F')};margin-bottom:4px'>{e(g['cat'])}</div>"
                    f"<div style='{F};font-size:13.5px;color:#1E3A5F;background:#F7F4EC;border-radius:12px;padding:8px 10px;margin-bottom:8px'><b>המלצה:</b> {e(g['rec'])}</div>"
                    f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' dir='rtl' style='border-collapse:collapse'>"
                    f"<tr><th style='{th}'>החיפוש</th><th style='{th}'>מקור</th><th style='{th}'>מה נמצא</th></tr>{ex}</table>")
            rows.append(card(g["title"], "%d פעמים · %d ניסוחים" % (g["count"], g["queries"]), body))
            L += ["", "■ %s (%d) — %s" % (g["title"], g["count"], g["cat"]), "  המלצה: " + g["rec"]]
            L += ["  • %s [%s] %s" % (x["q"], x["src"], x["info"]) for x in g["examples"]]
    else:
        rows.append(card("לא נמצאה בעיה השבוע", "", f"<div style='{F};font-size:13px;color:#5B6472'>כל החיפושים שרצו שוב נראים תקינים.</div>"))
        L += ["", "לא נמצאה בעיה השבוע."]

    if rep["demand"]:
        body = "".join(f"<tr><td style='{td};font-weight:700'>{e(d['area'])}</td><td style='{td};text-align:center'>{d['count']}</td>"
                       f"<td style='{td};color:#5B6472'>{e(' / '.join(d['examples']))}</td></tr>" for d in rep["demand"])
        rows.append(card("ביקוש בלי היצע", "לגיוס מוכרים",
                         f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' dir='rtl' style='border-collapse:collapse'>"
                         f"<tr><th style='{th}'>אזור</th><th style='{th};text-align:center'>פעמים</th><th style='{th}'>דוגמה</th></tr>{body}</table>"))
        L += ["", "— ביקוש בלי היצע —"] + ["%s: %d (%s)" % (d["area"], d["count"], " / ".join(d["examples"])) for d in rep["demand"]]

    if rep["data_nb"]:
        body = "".join(f"<tr><td style='{td}'>{e(x['addr'])}</td><td style='{td};white-space:nowrap'>{e(x['agent'])}</td></tr>" for x in rep["data_nb"])
        rows.append(card("להשלמה ביד2: נכסים בלי שכונה", "לפי סוכן",
                         f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' dir='rtl' style='border-collapse:collapse'>"
                         f"<tr><th style='{th}'>נכס</th><th style='{th}'>סוכן</th></tr>{body}</table>"))
        L += ["", "— נכסים בלי שכונה —"] + ["%s · %s" % (x["addr"], x["agent"]) for x in rep["data_nb"]]

    html = (f"<div dir='rtl' style='background:#F2EFE7;padding:12px 0'><table role='presentation' width='640' align='center' cellpadding='0' cellspacing='0' style='max-width:640px;margin:0 auto'>"
            f"<tr><td style='padding:6px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#1E3A5F;border-radius:22px'><tr><td style='padding:18px 20px;{F}'>"
            f"<div style='font-size:22px;font-weight:800;color:#fff'>בקרת חיפושים · {e(office)}</div>"
            f"<div style='font-size:12.5px;color:#D9DEE8;margin-top:3px'>{e(rng)} · כל החיפושים רצו שוב על הנכסים של היום</div></td></tr></table></td></tr>"
            + "".join(rows)
            + f"<tr><td style='padding:10px;{F};font-size:11.5px;color:#6B7280;text-align:center'>שום דבר לא משתנה אוטומטית — כל תיקון מחכה לאישורך · הופק על ידי אפי</td></tr></table></div>")
    L += ["", "שום דבר לא משתנה אוטומטית — כל תיקון מחכה לאישורך."]
    return subject, html, "\n".join(L)
