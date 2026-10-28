# tests/newborn/test_nb_feats.py — מאפייני נכס נולד (סורק v14.5): תגיות מעלית/ממ"ד/מרפסת, קומה מתוך,
# והטקסט של בעל הנכס — נשמרים בשורה, נכנסים לחיפוש ומוצגים בכרטיס. על הקוד האמיתי.
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("WARMUP_ON_BOOT", "0")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)
import app as A
import effie_v2 as E

n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1

row = {"_orderId": "57001", "deal_type": "למכירה", "property_type": "דירה", "rooms": "4", "sqm": "100",
       "floor": "3", "total_floors": "8", "price": "1900000", "city": "קרית ביאליק", "street": "הרצל 5",
       "link": "https://www.yad2.co.il/realestate/item/n1", "tags": 'מעלית;ממ"ד',
       "description": "דירה מוארת עם נוף פתוח"}
sk, rec = E.y2_norm_private(row)
raw = rec["raw"]
ck(raw.get("תגיות") == 'מעלית · ממ"ד', raw.get("תגיות"))
ck("קומה 3 מתוך 8" in raw["תיאור נכס"], raw["תיאור נכס"])
ck(raw["תיאור נכס"].endswith("דירה מוארת עם נוף פתוח"), raw["תיאור נכס"])
ck(raw.get("קומות בבניין") == "8", raw.get("קומות בבניין"))
ck(raw.get("קומה") == "3", raw.get("קומה"))

# שורה ישנה (בלי תגיות / בלי קומות בבניין) — כמו קודם
_, rec2 = E.y2_norm_private(dict(row, tags="", total_floors="", description=""))
ck("תגיות" not in rec2["raw"] or rec2["raw"]["תגיות"] == "", rec2["raw"].get("תגיות"))
ck(rec2["raw"]["תיאור נכס"] == "דירה · 4 חד' · 100 מ\"ר · קומה 3", rec2["raw"]["תיאור נכס"])

# קומה מתוך עדיין נקראת נכון בחיפוש ובזיהוי 'כבר בבלעדיות'
ck(A._row_floor({"תיאור": raw["תיאור נכס"]}) == 3, A._row_floor({"תיאור": raw["תיאור נכס"]}))
ck(A._famexcl_floor_txt(raw["תיאור נכס"]) == 3, A._famexcl_floor_txt(raw["תיאור נכס"]))

# החיפוש רואה את התגיות (שורה ממופה)
orow = A._nb_as_office_row(raw)
ck(orow.get("תגיות") == 'מעלית · ממ"ד', orow.get("תגיות"))
ck(A._row_feature_state(orow, "מעלית", "מעלית") is True, "elevator via tags")
ck(A._row_feature_state(orow, "מרפסת", "מרפסת") is None, "balcony unknown")

# הכרטיס
ctx = {"contacts": {}, "statuses": {}, "fam_list": {}, "pd_map": {}, "eff_name": "x", "phone9": "", "notes_admin": False}
A._nb_notes_for = lambda *a, **k: []
out = A._nb_row_out(raw, 0, "קרית ביאליק", "הרצל 5", "", "", False, ctx)
ck(out.get("feats") == ["מעלית", 'ממ"ד'], out.get("feats"))
old = {"תיאור נכס": "דירה · 4 חד' · ללא מעלית", "עיר": "קרית ביאליק"}
ck(A._nb_row_out(old, 0, "קרית ביאליק", "הרצל 5", "", "", False, ctx).get("feats") == [], "'ללא מעלית' not a feature")
print("ok", n)
