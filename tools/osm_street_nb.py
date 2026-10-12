#!/usr/bin/env python3
"""מיפוי רחוב → שכונה לקריות ולקרית חיים (אייל 12/10: "תבנה את מיפוי הרחובות").

מקורות (קריאה בלבד, רץ מקומית, לא בשרת):
  * OpenStreetMap — כל הרחובות עם שם וגאומטריה, גבולות הערים, פסי הרכבת, נקודות שכונה.
  * נכסי המשרד מיד2 — נקודות עם קואורדינטות ושם שכונה (העוגנים).
שיוך: כל רחוב → העיר שבה רוב הנקודות שלו; השכונה = רוב משוקלל של העוגנים הקרובים (עד 600 מ') באותה עיר,
רק כשיש רוב ברור. קרית חיים: מערבית/מזרחית לפי הצד של פסי הרכבת (לא לפי העוגנים).

שימוש:
  python3 tools/osm_street_nb.py <תיקיית-osm> <props.json> [פלט.json]
  ברירת מחדל לפלט: tools/street_nb_osm.proposed.json — האפליקציה קוראת רק את tools/street_nb_osm.json (אחרי אישור אייל).
"""
import collections, json, math, os, re, sys

CITIES = {"קרית ביאליק": "קרית ביאליק", "קרית מוצקין": "קרית מוצקין", "קרית ים": "קרית ים",
          "קרית אתא": "קרית אתא", "חיפה": "חיפה"}
KH = ("קרית חיים מערבית", "קרית חיים מזרחית")
_PREFIX = re.compile(r"^(?:שדרות|שד['׳.]?|רחוב|רח['׳.]?|דרך|סמטת|סמ['׳.]?|כיכר)\s+")


def norm(s):
    s = str(s or "").replace("קריית", "קרית").replace("״", "").replace('"', "").replace("׳", "").replace("'", "")
    return re.sub(r"\s+", " ", s).strip()


def street_key(name):
    """'שדרות ירושלים 5' / 'ירושלים' → 'ירושלים'; גרשיים, קריית, מספר בית ותחיליות (שדרות/רח'/דרך) מוסרים."""
    s = str(name or "").replace("קריית", "קרית")
    s = _PREFIX.sub("", re.sub(r"\s+", " ", s).strip())
    s = re.sub(r"\s*\d.*$", "", s)
    return norm(s)


# ── גאומטריה ──
def _m(a, b):
    """מרחק במטרים (קירוב מקומי — מספיק לכמה ק"מ)."""
    dy = (a[0] - b[0]) * 111320.0
    dx = (a[1] - b[1]) * 111320.0 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def assemble_rings(segs):
    """מקטעים (רשימות נקודות) → טבעות סגורות. מקטע יכול להגיע הפוך."""
    left = [list(s) for s in segs if len(s) >= 2]
    rings = []
    while left:
        ring = left.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(left):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[-2::-1]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[:0:-1] + ring
                else:
                    continue
                left.pop(i)
                changed = True
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append(ring)
    return rings


def _in_ring(p, ring):
    y, x = p
    inside = False
    for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def in_rings(p, rings):
    return sum(1 for r in rings if _in_ring(p, r)) % 2 == 1   # טבעות פנימיות (חורים) מתקזזות


def city_of(points, cities):
    c = collections.Counter()
    for p in points:
        for name, rings in cities.items():
            if in_rings(p, rings):
                c[name] += 1
                break
    if not c:
        return None
    top, k = c.most_common(1)[0]
    return top if k * 2 > len(points) else None


def side_of_line(p, line):
    """-1/+1 — הצד של p ביחס למקטע הקרוב ביותר בקו."""
    best = None
    for a, b in zip(line, line[1:]):
        ay, ax, by_, bx = a[0], a[1], b[0], b[1]
        dy, dx = by_ - ay, bx - ax
        L = dy * dy + dx * dx or 1e-18
        t = max(0.0, min(1.0, ((p[0] - ay) * dy + (p[1] - ax) * dx) / L))
        d = _m(p, (ay + t * dy, ax + t * dx))
        if best is None or d < best[0]:
            cross = dx * (p[0] - ay) - dy * (p[1] - ax)
            best = (d, 1 if cross > 0 else -1)
    return best[1] if best else 0


def assign_street(points, city, anchors, k=7, radius=600.0, min_share=0.65, min_anchors=3):
    """רוב משוקלל של העוגנים הקרובים באותה עיר. אין רוב ברור / מעט עוגנים / רחוק → None."""
    pool = [a for a in anchors if a.get("city") == city and a.get("nb")]
    votes, used = collections.Counter(), set()
    for p in points:
        near = sorted(((_m(p, (a["lat"], a["lon"])), i, a) for i, a in enumerate(pool)), key=lambda x: x[0])[:k]
        for d, i, a in near:
            if d <= radius:
                votes[a["nb"]] += a.get("w", 1) / (d + 50.0)
                used.add(i)
    if len(used) < min_anchors or not votes:
        return None
    top, w = votes.most_common(1)[0]
    return top if w / sum(votes.values()) >= min_share else None


# ── הרצה ──
def _geom(e):
    return [(g["lat"], g["lon"]) for g in e.get("geometry") or [] if g]


def build(osm_dir, props_path):
    J = lambda f: json.load(open(os.path.join(osm_dir, f), encoding="utf-8"))["elements"]
    cities = {}
    for rel in J("admin.json"):
        nm = norm((rel.get("tags") or {}).get("name:he") or (rel.get("tags") or {}).get("name"))
        if nm in CITIES:
            segs = [[(g["lat"], g["lon"]) for g in m.get("geometry") or []] for m in rel.get("members") or []
                    if m.get("type") == "way" and m.get("role") in ("outer", "")]
            cities[CITIES[nm]] = assemble_rings(segs)
    anchors = []
    for r in json.load(open(props_path, encoding="utf-8")).get("results") or []:
        if r.get("lat") and r.get("lng") and norm(r.get("neighborhood")):
            anchors.append({"lat": float(r["lat"]), "lon": float(r["lng"]), "nb": norm(r["neighborhood"]),
                            "city": norm(r.get("city"))})
    for e in J("places.json"):
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        nm = norm((e.get("tags") or {}).get("name:he") or (e.get("tags") or {}).get("name"))
        city = city_of([(c["lat"], c["lon"])], cities)
        if nm and city and nm != "קרית חיים":
            anchors.append({"lat": c["lat"], "lon": c["lon"], "nb": nm, "city": city, "w": 2})
    rails = [_geom(e) for e in J("rail.json")]
    rail = max(rails, key=lambda g: sum(1 for p in g if 32.81 < p[0] < 32.85 and 35.04 < p[1] < 35.09)) if rails else []
    west_ref = (32.8315, 35.0567)                       # נקודת 'קרית חיים מערבית' ב-OSM
    west_side = side_of_line(west_ref, rail) if rail else 0
    streets = collections.defaultdict(list)
    for e in J("streets.json"):
        nm = (e.get("tags") or {}).get("name:he") or (e.get("tags") or {}).get("name")
        if nm and re.search(r"[א-ת]", nm):
            streets[nm.strip()] += _geom(e)
    out, unassigned, kh_flip = collections.defaultdict(dict), collections.defaultdict(list), 0
    for nm, pts in sorted(streets.items()):
        if not pts:
            continue
        city = city_of(pts, cities)
        if not city:
            continue
        lab = assign_street(pts, city, anchors)
        if city == "חיפה" and lab and "קרית חיים" in lab and rail:
            sides = collections.Counter(side_of_line(p, rail) for p in pts)
            by_rail = KH[0] if sides.most_common(1)[0][0] == west_side else KH[1]
            kh_flip += by_rail != lab
            lab = by_rail
        if city == "חיפה" and not lab:
            continue                                      # שאר חיפה — לא בתחום
        if lab:
            out[city][nm] = lab
        else:
            unassigned[city].append(nm)
    return {"streets": out, "unassigned": unassigned, "anchors": len(anchors), "kh_rail_flips": kh_flip,
            "cities": sorted(cities)}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    res = build(argv[1], argv[2])
    dst = argv[3] if len(argv) > 3 else os.path.join(os.path.dirname(__file__), "street_nb_osm.proposed.json")
    json.dump({"source": "OpenStreetMap (ODbL) + נכסי המשרד", "streets": res["streets"]},
              open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    for c in sorted(res["streets"]):
        print(c, "משויכים:", len(res["streets"][c]), "בלי שיוך:", len(res["unassigned"].get(c, [])))
    print("עוגנים:", res["anchors"], "· ערים:", res["cities"], "· קרית חיים — תיקוני רכבת:", res["kh_rail_flips"])
    print("נכתב:", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
