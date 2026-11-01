# tests/social_video/test_texts.py — vid_texts / vid_timeline (טהור)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_video as V
from _fakes import ROW

FE = ["מעלית", "ממ\"ד", "מרפסת", "חניה"]
t = V.vid_texts(ROW, FE, "", "דנה כהן", "072-555-0101", "04-6000800")
ck(t["open"]["title"] == "4 חדרים למכירה", t["open"])
ck(t["open"]["place"] == "נאות אפק, קרית ביאליק", t["open"])
ck(t["open"]["price"] == "1,890,000 ₪", t["open"])
ck(t["open"]["chip"] == "חדש בשוק", t["open"])
ck(t["s2"]["main"] == '110 מ"ר · קומה 3', t["s2"])
ck(t["s3"]["main"] == "מעלית · ממ\"ד · מרפסת", t["s3"])
ck(t["end"]["agent"] == "דנה כהן" and t["end"]["phone"] == "072-555-0101", t["end"])
ck(t["end"]["cta"] == "שלחו הודעה ונחזור אליכם", t["end"])
ck(t["end"]["recap"] == "4 חדרים · 1,890,000 ₪", t["end"])

t2 = V.vid_texts(ROW, FE, "משופצת מהיסוד", "דנה כהן", "", "04-6000800")
ck(t2["s3"]["main"] == "משופצת מהיסוד" and t2["s3"]["sub"] == "מעלית · ממ\"ד · מרפסת", t2["s3"])
ck(t2["end"]["phone"] == "04-6000800", t2["end"])
ck(V.vid_texts(ROW, FE, "", "דנה", "", "")["end"]["phone"] == "", "no phone")

rent = dict(ROW, **{"סוג עסקה": "השכרה", "מחיר": "5500"})
tr = V.vid_texts(rent, [], "", "", "", "")
ck(tr["open"]["price"] == "5,500 ₪ לחודש" and tr["open"]["title"] == "4 חדרים להשכרה", tr["open"])

nofl = dict(ROW, **{"קומה": "", "_desc_ae": "דירה"})
ck(V.vid_texts(nofl, [], "", "", "", "")["s2"]["main"] == '110 מ"ר', "no floor")
bare = dict(nofl, **{'מ"ר': "", "מחיר": "", "חדרים": "", "שכונה": ""})
tb = V.vid_texts(bare, [], "", "", "", "")
ck(tb["s2"]["main"] == "" and tb["open"]["price"] == "" and tb["open"]["place"] == "קרית ביאליק", tb)
ck(tb["open"]["title"] == "דירה למכירה", tb["open"])

hl = V.vid_texts(ROW, FE, "חייגו 054-1234567", "", "", "")
ck("054" not in hl["s3"]["main"], hl["s3"])
def allvals(d):
    for v in d.values():
        if isinstance(v, dict): yield from allvals(v)
        else: yield str(v)
for tt in (t, t2, tr, tb):
    vals = list(allvals(tt))
    ck(not any("None" in v for v in vals), vals)
    ck(not any("13" in v for v in vals), vals)   # מספר הבית

ck(V.vid_timeline(2, True) == [("ai", 5), ("s2", 4), ("s3", 2.5), ("end", 2.5)], V.vid_timeline(2, True))
ck(V.vid_timeline(1, True) == [("ai", 5), ("s2", 4.5), ("end", 4.5)], V.vid_timeline(1, True))
ck(V.vid_timeline(2, False)[0] == ("kb", 5), V.vid_timeline(2, False))
print("video_texts OK", n)
