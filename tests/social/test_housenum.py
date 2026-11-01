# tests/social/test_housenum.py — מספר בית לא יוצא גם מתוך התיאור של בעל הנכס (תצוגה מקדימה 01/11: 'רחוב אנרי מאטיס 14')
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP

clean = lambda d: str(d or "").strip()
noft = lambda row: []
ROW = {"מספר מודעה": "syobc4d1", "סוג עסקה": "מכירה", "סוג נכס": "בית פרטי/קוטג'", "חדרים": "7",
       "שכונה": "גבעת טל", "עיר / ישוב": "קרית אתא", "כתובת": "אנרי מאטיס", "מספר בית": "14",
       "מחיר": "4900000", 'מ"ר': "516"}

def body(desc, **kw):
    return SP.soc_build_post(dict(ROW, _desc_ae=desc, **kw), "רימקס פמילי", clean, noft)["body"]

b = body("רחוב אנרי מאטיס 14 בשכונת גבעת טל המבוקשת")
ck("14" not in b and "רחוב אנרי מאטיס בשכונת גבעת טל" in b, b)
ck("14" not in body("וילה במאטיס 14, ליד בית ספר"), "last word of street + number")
ck("14" not in body("אנרי מאטיס מס' 14 קומת קרקע"), "מס' form")
ck("14" not in body("אנרי מאטיס 14א, כניסה פרטית"), "letter suffix")
# כתובת שכבר כוללת את המספר
b2 = body("ברחוב אהוד מנור 13 בנאות אפק", **{"כתובת": "אהוד מנור 13", "מספר בית": ""})
ck("13" not in b2 and "ברחוב אהוד מנור בנאות אפק" in b2, b2)
# מה שלא אמור להיפגע
keep = body("אנרי מאטיס 14. 7 חדרים, קומה 3, 516 מ\"ר, מחיר 4,900,000")
ck("7 חדרים" in keep and "קומה 3" in keep and "4,900,000" in keep and keep.count("516") >= 1, keep)
ck("הרצל 5" in body("קרוב להרצל 5 ולפארק"), "other street untouched")
print("ok", n)
