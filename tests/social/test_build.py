# tests/social/test_build.py — soc_build_post / soc_scrub_phones / soc_addr_key / soc_floor
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP

clean = lambda d: str(d or "").strip()
feats_on = lambda row: ["מעלית", 'ממ"ד']
feats_off = lambda row: []
ROW = {"מספר מודעה": "tok1", "סוג עסקה": "מכירה", "סוג נכס": "דירה", "חדרים": "4", "שכונה": "נאות אפק",
       "עיר / ישוב": "קרית ביאליק", "כתובת": "אהוד מנור", "מספר בית": "13", "מחיר": "1890000",
       'מ"ר': "110", "קומה": "3", "_desc_ae": "דירה מוארת ומשופצת. התקשרו 054-1234567 עכשיו",
       "תמונות": ["https://img.yad2.co.il/a.jpg", "https://img.yad2.co.il/b.jpg"]}

p = SP.soc_build_post(ROW, "רימקס פמילי", clean, feats_on)
b = p["body"]
ck("למכירה · 4 חדרים בנאות אפק, קרית ביאליק" in b, b)
ck("📍 אהוד מנור" in b and "אהוד מנור 13" not in b, b)
ck("1,890,000 ₪" in b and '110 מ"ר' in b and "קומה 3" in b, b)
ck("054" not in b and "1234567" not in b, b)
ck(b.rstrip().endswith("לפרטים — הודעה לעמוד") and "רימקס פמילי" in b, b)
ck('✔ מעלית · ממ"ד' in b, b)
ck("✔" not in SP.soc_build_post(ROW, "רימקס פמילי", clean, feats_off)["body"], "no feats line")
ck(p["ig_caption"].startswith(b) and "#דירותלמכירה" in p["ig_caption"] and "#קריתביאליק" in p["ig_caption"]
   and "#נדלן" in p["ig_caption"] and "#רימקספמילי" in p["ig_caption"], p["ig_caption"])
ck("#" not in b, "no hashtags in fb body")
ck(p["images"] == ROW["תמונות"], p["images"])

# phones
for t in ("054-1234567", "+972 54 123 4567", "04 8123456", "0541234567"):
    ck(SP.soc_scrub_phones("טל " + t + " בערב").strip() in ("טל  בערב", "טל בערב") or t not in SP.soc_scrub_phones("טל " + t), t)
    ck(not any(ch.isdigit() for ch in SP.soc_scrub_phones("טל " + t)), (t, SP.soc_scrub_phones("טל " + t)))
ck("1,890,000" in SP.soc_scrub_phones("מחיר 1,890,000 ו-110 מ\"ר") and "110" in SP.soc_scrub_phones("110 מ\"ר"), "keeps prices")

# long desc
long = dict(ROW, _desc_ae=("מילה " * 300).strip())
lb = SP.soc_build_post(long, "רימקס פמילי", clean, feats_off)["body"]
seg = [s for s in lb.split("\n\n") if s.startswith("מילה")][0]
ck(len(seg) <= SP.DESC_MAX and seg.endswith("…") and not seg[:-1].endswith(" "), (len(seg), seg[-10:]))

# rent
rent = SP.soc_build_post(dict(ROW, **{"סוג עסקה": "השכרה", "מחיר": "5200"}), "רימקס פמילי", clean, feats_off)
ck("להשכרה" in rent["body"] and "5,200 ₪ לחודש" in rent["body"] and "#דירותלהשכרה" in rent["ig_caption"], rent["body"])

# images
many = SP.soc_build_post(dict(ROW, **{"תמונות": ["https://x/%d.jpg" % i for i in range(12)] + ["https://x/1.jpg"]}),
                         "ר", clean, feats_off)["images"]
ck(len(many) == 10 and len(set(many)) == 10, many)
one = SP.soc_build_post(dict(ROW, **{"תמונות": [], "תמונה": "https://x/only.jpg"}), "ר", clean, feats_off)["images"]
ck(one == ["https://x/only.jpg"], one)
js = SP.soc_build_post(dict(ROW, **{"תמונות": '["https://x/1.jpg","https://x/2.jpg"]'}), "ר", clean, feats_off)["images"]
ck(js == ["https://x/1.jpg", "https://x/2.jpg"], js)

# addr key / floor
ck(SP.soc_addr_key(ROW) == SP.soc_addr_key(dict(ROW, **{"עיר / ישוב": "קריית ביאליק"})), "kiryat normalize")
ck(SP.soc_addr_key(ROW) != SP.soc_addr_key(dict(ROW, חדרים="5")), "rooms differ")
ck(SP.soc_addr_key(dict(ROW, חדרים="4.0")) == SP.soc_addr_key(ROW), "4.0 == 4")
ck(SP.soc_floor(ROW) == "3" and SP.soc_floor(dict(ROW, קומה="", _desc_ae="קומה 7 מתוך 9")) == "7"
   and SP.soc_floor(dict(ROW, קומה="", _desc_ae="")) == "", "floor")
print("social_build OK", n)
