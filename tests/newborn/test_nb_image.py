# tests/newborn/test_nb_image.py — 26/11 (אייל: 'גם תמונה אחת על כל נכס חדש למכירה' → 'כן תבנה'):
# סורק v15.9 שולח תמונה ראשית למודעות נכס נולד חדשות → נשמרת בשורה ומוצגת בכרטיס. דף הקונה — עדיין בלי תמונות.
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

IMG = "https://img.yad2.co.il/Pic/202611/n1.jpeg"
row = {"_orderId": "57001", "deal_type": "למכירה", "price": "1900000", "city": "קרית ביאליק", "street": "הרצל 5",
       "link": "https://www.yad2.co.il/realestate/item/n1", "image": IMG, "images": [IMG]}
_, rec = E.y2_norm_private(row)
ck(rec["raw"].get("תמונה") == IMG, rec["raw"].get("תמונה"))
_, rec2 = E.y2_norm_private(dict(row, image="", images=[]))
ck(not rec2["raw"].get("תמונה"), rec2["raw"].get("תמונה"))
_, rec3 = E.y2_norm_private(dict(row, image="javascript:alert(1)"))
ck(not rec3["raw"].get("תמונה"), "non-http dropped")

ctx = {"contacts": {}, "statuses": {}, "fam_list": {}, "pd_map": {}, "eff_name": "x", "phone9": "", "notes_admin": False}
A._nb_notes_for = lambda *a, **k: []
out = A._nb_row_out(rec["raw"], 0, "קרית ביאליק", "הרצל 5", "", "", False, ctx)
ck(out.get("image") == IMG, out.get("image"))
ck(A._nb_row_out(rec2["raw"], 0, "קרית ביאליק", "הרצל 5", "", "", False, ctx).get("image") == "", "no image")

# דף הקונה: נכס נולד נשאר בלי תמונות (החלטה 06/10)
orow = dict(A._nb_as_office_row(rec["raw"]))
ck(E.bpage_snapshot("newborn", orow)["images"] == [], "buyer page newborn without images")

# הכרטיס מציג את התמונה (V2_NB_KIT)
ck("r.image" in E.V2_NB_KIT and "referrerpolicy" in E.V2_NB_KIT, "card renders image")
print("ok", n)
