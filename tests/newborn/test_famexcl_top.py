# tests/newborn/test_famexcl_top.py — 'כבר בבלעדיות': קומות בבניין שונות = דירה אחרת (בגין 12, 28/10).
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("WARMUP_ON_BOOT", "0")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, ROOT)
import app as A

n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1

ck(A._famexcl_top_txt("דירת 5 חדרים כ - 100 מ\"ר מרפסת קומה 5/10 סלון") == 10, "5/10")
ck(A._famexcl_top_txt("דירה · 5 חד' · 107 מ\"ר · קומה 5 מתוך 8") == 8, "מתוך")
ck(A._famexcl_top_txt("קומה 5") is None, "no top")

OFFICE = [{"סטטוס": "פעילה", "כתובת": "מנחם בגין 12", "עיר / ישוב": "קרית מוצקין", "סוכן 1": "אירנה אוברוב",
           "מחיר": "1590000", "חדרים": "5", 'מ"ר': "100",
           "תיאור": "רחוב מנחם בגין 12 קריית מוצקין דירת 5 חדרים כ - 100 מ\"ר מרפסת מערבית קומה 5/10 סלון"}]
A.fetch_sheet_rows = lambda: OFFICE
A._cache_clear("famexcl_index")
idx = A._famexcl_addr_list()
ck(idx["12"][0]["top"] == 10 and idx["12"][0]["floor"] == 5, idx)

ctx = {"contacts": {}, "statuses": {}, "pd_map": {}, "eff_name": "x", "phone9": "", "notes_admin": False, "fam_list": idx}
A._nb_notes_for = lambda *a, **k: []
bruria = {"תיאור נכס": "דירה · 5 חד' · 107 מ\"ר · קומה 5 מתוך 8", "קומה": "5", "קומות בבניין": "8", "מחיר": "1620000"}
out = A._nb_row_out(bruria, 0, "קרית מוצקין", "מנחם בגין 12", "", "", False, ctx)
ck(out["famexcl"] is False, "different building height → not Irena's")
same = dict(bruria, **{"קומות בבניין": "10", "תיאור נכס": "דירה · 5 חד' · 100 מ\"ר · קומה 5 מתוך 10"})
ck(A._nb_row_out(same, 0, "קרית מוצקין", "מנחם בגין 12", "", "", False, ctx)["famexcl"] is True, "same apartment still matched")
old = {"תיאור נכס": "דירה · 5 חד' · 100 מ\"ר · קומה 5", "קומה": "5", "מחיר": "1600000"}
ck(A._nb_row_out(old, 0, "קרית מוצקין", "מנחם בגין 12", "", "", False, ctx)["famexcl"] is True, "unknown top → as before")
off1 = dict(bruria, **{"קומות בבניין": "9"})
ck(A._nb_row_out(off1, 0, "קרית מוצקין", "מנחם בגין 12", "", "", False, ctx)["famexcl"] is True, "1-floor difference tolerated")
print("ok", n)
