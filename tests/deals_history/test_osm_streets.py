# tests/deals_history/test_osm_streets.py — מיפוי רחוב→שכונה מ-OpenStreetMap (אייל 12/10: "תבנה את מיפוי הרחובות")
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools import osm_street_nb as O
n = 0
def ck(c, m):
    global n; assert c, m; n += 1

# הרכבת טבעת מקטעים (כמו members של relation) + נקודה בתוך פוליגון
segs = [[(0, 0), (0, 1)], [(1, 1), (0, 1)], [(1, 1), (1, 0)], [(1, 0), (0, 0)]]   # כיוון הפוך במקטע 2
rings = O.assemble_rings(segs)
ck(len(rings) == 1 and rings[0][0] == rings[0][-1], rings)
ck(O.in_rings((0.5, 0.5), rings) and not O.in_rings((1.5, 0.5), rings), "point in polygon")

# שם רחוב: שדרות/רח'/גרשיים — אותו מפתח
ck(O.street_key("שדרות ירושלים") == O.street_key("ירושלים 5") == "ירושלים", O.street_key("שדרות ירושלים"))
ck(O.street_key("רח' ש\"י עגנון 12") == O.street_key("ש״י עגנון") == "שי עגנון", O.street_key("ש״י עגנון"))
ck(O.street_key("קריית חיים") == "קרית חיים", "קריית→קרית")

# שיוך: רחוב ליד עוגנים של שכונה אחת → השכונה; באמצע בין שתיים / רחוק → בלי שיוך
A = [{"lat": 32.850, "lon": 35.100, "nb": "נאות אפק, אפקה", "city": "קרית ביאליק"}] * 4 + \
    [{"lat": 32.830, "lon": 35.100, "nb": "גבעת הרקפות", "city": "קרית ביאליק"}] * 4
near_afek = [(32.8505, 35.1002), (32.8508, 35.1004)]
ck(O.assign_street(near_afek, "קרית ביאליק", A) == "נאות אפק, אפקה", O.assign_street(near_afek, "קרית ביאליק", A))
ck(O.assign_street([(32.840, 35.100)], "קרית ביאליק", A) is None, "midway → none (no clear majority)")
ck(O.assign_street([(32.900, 35.100)], "קרית ביאליק", A) is None, "far → none")
ck(O.assign_street(near_afek, "קרית מוצקין", A) is None, "other city's anchors ignored")

# צד של קו (פסי הרכבת) — לחלוקת קרית חיים
line = [(32.80, 35.06), (32.84, 35.07)]   # קו שעולה צפונה, בערך
ck(O.side_of_line((32.82, 35.05), line) != O.side_of_line((32.82, 35.08), line), "opposite sides")

# עיר לרחוב לפי רוב הנקודות
cities = {"א": [[(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]], "ב": [[(0, 1), (0, 2), (1, 2), (1, 1), (0, 1)]]}
ck(O.city_of([(0.5, 0.2), (0.5, 0.4), (0.5, 1.2)], cities) == "א", "majority city")
print("OK", n, "checks")
