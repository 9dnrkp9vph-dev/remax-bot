"""נכס נולד → תיק: חדרים ומ"ר מהתיאור (בשורות יד2 אין שדות כאלה) — אחרת ניתוח השוק לא נבנה (10/11)."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import kit


def test_rooms_sqm_from_description():
    r = kit._nb_src({"רחוב": "גרושקביץ' 38", "עיר": "קרית מוצקין",
                     "תיאור נכס": "דירה · 2 חד' · 53 מ\"ר · קומה 1 מתוך 2. דירה פינתית"})
    assert r["rooms"] == "2" and r["sqm"] == "53"


def test_field_wins_and_fallbacks():
    assert kit._nb_src({"חדרים": "3.5", "תיאור נכס": "5 חד' 120 מ\"ר"})["rooms"] == "3.5"
    assert kit._nb_src({"תיאור נכס": "דירת 4.5 חדרים, 98 מ״ר"})["sqm"] == "98"
    assert kit._nb_src({"תיאור נכס": "קומה 13"})["rooms"] == ""
    assert kit._nb_src({})["rooms"] == "" and kit._nb_src({})["sqm"] == ""
