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
print("OK", n, "checks")
