# tests/deals_history/test_area.py — מחירי השוואה לפי שכונה ("איזה עסקאות היו באפקה", אייל 12/10)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
IDX = {"city": {"קרית ביאליק": ["ביאליק", "קרית ביאליק"], "קרית מוצקין": ["מוצקין", "קרית מוצקין"]},
       "nb": {"אפק": {"city": "קרית ביאליק", "aliases": ["אפק", "אפקה", "הברושים", "נאות אפק"]},
              "נווה גנים": {"city": "קרית מוצקין", "aliases": ["נווה גנים"]},
              "ותיק": {"city": "קרית מוצקין", "aliases": ["ותיק", "ותיקה"]}},
       "ambiguous": {"ותיק", "ותיקה", "מרכז"}}
STREETS = [("נעמי שמר 12", "אפק", "קרית ביאליק"), ("נעמי שמר 4", "נאות אפק", "קרית ביאליק"),
           ("אהוד מנור 3", "אפק", "קרית ביאליק"), ("אהוד מנור 9", "אפק", "קריית ביאליק"),
           ("הגפן 4", "נווה גנים", "קרית מוצקין"), ("הגפן 8", "נווה גנים", "קרית מוצקין"),
           ("הרצל 1", "אפק", "קרית ביאליק")]   # עדות אחת בלבד — לא מספיק
SI = D.nb_street_index(STREETS, IDX)
ck(SI["sc"].get(("נעמי שמר", "קרית ביאליק")) == "אפק" and SI["sc"].get(("אהוד מנור", "קרית ביאליק")) == "אפק", SI)
ck(("הרצל", "קרית ביאליק") not in SI["sc"], "single evidence ignored")
ck(D.find_area("איזה עסקאות היו באפקה", IDX)["nb"] == "אפק", "באפקה → אפק")
ck(D.find_area("נאות אפק", IDX)["nb"] == "אפק" and D.find_area("נווה גנים", IDX)["city"] == "קרית מוצקין", "multiword alias")
ck(D.find_area("הגפן מוצקין", IDX) is None and D.find_area("ותיקה", IDX) is None, "street query / ambiguous → no area")
R = [dict(id="1", street="נעמי שמר 10", city="קרית ביאליק", side="מוכר", deal_amount=2000000, deal_date="2025-01-01", agent="א", branch="bialik"),
     dict(id="2", street="אהוד מנור 5", city="קריית ביאליק", side="קונה", deal_amount=1800000, deal_date="2024-01-01", agent="ב", branch="bialik"),
     dict(id="3", street="הגפן 4", city="קרית מוצקין", side="מוכר", deal_amount=1500000, deal_date="2025-02-01", agent="ג", branch="motzkin"),
     dict(id="4", street="נעמי שמר 3", city="קרית מוצקין", side="מוכר", deal_amount=9, deal_date="2025-03-01", agent="ד", branch="motzkin")]
ctx = {"idx": IDX, "streets": SI}
cs = D.comps_search(R, "איזה עסקאות היו באפקה", area_ctx=ctx)
ck([x["date"] for x in cs["results"]] == ["01/01/2025", "01/01/2024"] and cs["area"] == "אפק · קרית ביאליק", cs)
ck(cs["n_sale"] == 2 and cs["avg_sale"] == 1900000, "avg in area")
ck(D.comps_search(R, "הגפן מוצקין", area_ctx=ctx)["results"][0]["address"].startswith("הגפן"), "street search unchanged")
ck("area" not in D.comps_search(R, "הגפן", area_ctx=ctx), "no area label for street search")
ck(D.comps_search(R, "באפקה", area_ctx=None)["results"] == [], "no ctx → plain text (no street named אפקה)")
# [12/10 חי] בקבצי העסקאות העיר כתובה 'ביאליק' / 'ק. ביאליק' / ריקה — לא 'קרית ביאליק' כמו בנכסים
R2 = [dict(id="5", street="נעמי שמר 2", city="ביאליק", side="מוכר", deal_amount=2100000, deal_date="2026-09-28", agent="א", branch="bialik"),
      dict(id="6", street="אהוד מנור 15", city="ק. ביאליק", side="מוכר", deal_amount=2200000, deal_date="2026-09-19", agent="א", branch="bialik"),
      dict(id="7", street="נעמי שמר 8", city="", side="קונה", deal_amount=2000000, deal_date="2026-08-01", agent="א", branch="bialik"),
      dict(id="8", street="הגפן 4", city="מוצקין", side="מוכר", deal_amount=1500000, deal_date="2026-02-01", agent="ג", branch="motzkin")]
cs2 = D.comps_search(R2, "איזה עסקאות היו באפקה", area_ctx=ctx)
ck(sorted(x["date"] for x in cs2["results"]) == ["01/08/2026", "19/09/2026", "28/09/2026"], cs2["results"])
ck([x["address"] for x in D.comps_search(R2, "נווה גנים", area_ctx=ctx)["results"]] == ["הגפן 4, מוצקין"], "short city name, other area")
ck(D._city_canon("ק.ביאליק", IDX) == "קרית ביאליק" and D._city_canon("קריית ים", IDX) == "קרית ים", "canon city")
# [12/10] מיפוי OSM (מאושר) משלים רחובות שלא הופיעו בנכסים; עדויות הנכסים גוברות; שם שכונה של יד2 עם פסיקים
OSM = {"קרית ביאליק": {"ספי ריבלין": "נאות אפק, אפקה", "שדרות הבנים": "הפרפר", "נעמי שמר": "הפרפר"},
       "חיפה": {"אנה פרנק": "קרית חיים מערבית", "ביילינסון": "קרית חיים מזרחית"}}
IDX3 = dict(IDX, nb=dict(IDX["nb"], **{"הפרפר": {"city": "קרית ביאליק", "aliases": []}, "קרית חיים": {"city": "חיפה", "aliases": ["קרית חיים"]},
                                       "מערבית": {"city": "חיפה", "aliases": ["קרית חיים מערבית"]}}),
            city=dict(IDX["city"], **{"חיפה": ["חיים", "חיפה", "קרית חיים"]}))
SI3 = D.nb_street_index(STREETS, IDX3, osm=OSM)
ctx3 = {"idx": IDX3, "streets": SI3}
R3 = R2 + [dict(id="9", street="ספי ריבלין 3", city="ביאליק", side="מוכר", deal_amount=1, deal_date="2026-07-01", agent="א", branch="bialik"),
           dict(id="10", street="שד' הבנים 4", city="ביאליק", side="מוכר", deal_amount=1, deal_date="2026-06-01", agent="א", branch="bialik"),
           dict(id="11", street="אנה פרנק 7", city="חיים", side="מוכר", deal_amount=1, deal_date="2026-05-01", agent="ד", branch="motzkin"),
           dict(id="12", street="ביילינסון 2", city="קריית חיים", side="מוכר", deal_amount=1, deal_date="2026-04-01", agent="ד", branch="motzkin")]
afek = sorted(x["date"] for x in D.comps_search(R3, "באפקה", area_ctx=ctx3)["results"])
ck(afek == ["01/07/2026", "01/08/2026", "19/09/2026", "28/09/2026"], ("osm street joins; listing votes win for נעמי שמר", afek))
ck([x["date"] for x in D.comps_search(R3, "הפרפר", area_ctx=ctx3)["results"]] == ["01/06/2026"], "שד' prefix + osm")
kh = sorted(x["date"] for x in D.comps_search(R3, "עסקאות בקרית חיים", area_ctx=ctx3)["results"])
ck(kh == ["01/04/2026", "01/05/2026"], ("קרית חיים = מערבית+מזרחית", kh))
ck([x["date"] for x in D.comps_search(R3, "קרית חיים מערבית", area_ctx=ctx3)["results"]] == ["01/05/2026"], "west only")
IDX2 = dict(IDX, city=dict(IDX["city"], **{"קרית ים": ["קרית ים"]}))
ck(D._city_canon("ים", IDX2) == "קרית ים", D._city_canon("ים", IDX2))
# אייל 12/10: 'גבעת הרקפות' = השכונה בקרית ביאליק בלבד (לא קרית אתא), גם כשהכינוי עמום במפה
IDX4 = dict(IDX, city=dict(IDX["city"], **{"קרית אתא": ["אתא", "קרית אתא"]}),
            nb=dict(IDX["nb"], **{"גבעת הרקפות": {"city": "קרית ביאליק", "aliases": ["גבעת הרקפות באתא", "גבעת הרקפות בביאליק"]}}),
            ambiguous={"ותיק", "ותיקה", "מרכז", "גבעת הרקפות"})
OSM4 = {"קרית ביאליק": {"מנחם בגין": "גבעת הרקפות", "בגין": "גבעת הרקפות", "חיננית": "גבעת הרקפות"}, "קרית אתא": {"הרב מינץ": "גבעת הרקפות"}}
ctx4 = {"idx": IDX4, "streets": D.nb_street_index([], IDX4, osm=OSM4)}
R4 = [dict(id="a", street="מנחם בגין 3", city="ביאליק", side="מוכר", deal_amount=1, deal_date="2026-03-01", agent="א", branch="bialik"),
      dict(id="b", street="חיננית 5", city="קרית ביאליק", side="קונה", deal_amount=1, deal_date="2026-04-01", agent="א", branch="bialik"),
      dict(id="c", street="הרב מינץ 2", city="אתא", side="מוכר", deal_amount=1, deal_date="2026-05-01", agent="ב", branch="motzkin")]
for q in ("עסקאות בגבעת הרקפות", "גבעת הרקפות"):
    cs4 = D.comps_search(R4, q, area_ctx=ctx4)
    ck([x["date"] for x in cs4["results"]] == ["01/04/2026", "01/03/2026"] and cs4["area"] == "גבעת הרקפות · קרית ביאליק", (q, cs4))
# כתובת מלאה בשדה הרחוב בלי עיר ('בגין12 ק.מוצקין') — העיר מהטקסט, לא שיוך לבגין של ביאליק
R5 = R4 + [dict(id="d", street="בגין12 ק.מוצקין", city="", side="מוכר", deal_amount=1, deal_date="2026-06-01", agent="ג", branch="motzkin"),
           dict(id="e", street="חיננית 9 ק.ביאליק", city="", side="מוכר", deal_amount=1, deal_date="2026-07-01", agent="ג", branch="bialik")]
cs5 = D.comps_search(R5, "גבעת הרקפות", area_ctx=ctx4)
ck([x["date"] for x in cs5["results"]] == ["01/07/2026", "01/04/2026", "01/03/2026"], cs5["results"])
ck(D._city_from_text("בגין12 ק.מוצקין", IDX4) == "קרית מוצקין" and D._city_from_text("הרצל 5", IDX4) == "", "city from text")
print("OK", n, "checks")
