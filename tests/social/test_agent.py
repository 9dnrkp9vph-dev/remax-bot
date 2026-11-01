# tests/social/test_agent.py — שם הסוכן ווואטסאפ לנייד האישי שלו בפוסט (אייל 01/11: 'בפוסט עצמו')
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..")); sys.path.insert(0, HERE)
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from _fakes import ROW, make_G, ImgHttp

clean = lambda d: str(d or "").strip()
noft = lambda row: []
AG = {"name": "קובי חמו", "phone": "0541234567"}

p = SP.soc_build_post(ROW, "רימקס פמילי", clean, noft, agent=AG)
b, ig = p["body"], p["ig_caption"]
ck("לפרטים: קובי חמו" in b and "https://wa.me/972541234567" in b, b)
ck("הודעה לעמוד" not in b, b)
ck("לפרטים: קובי חמו · 054-123-4567" in ig and "wa.me" not in ig, ig)        # באינסטגרם קישור לא לחיץ — המספר
ck(ig.rstrip().endswith("#רימקספמילי") and "#נדלן" in ig and "#" not in b, ig)
ck("רימקס פמילי" in b, "office name stays")

# בלי טלפון — שם + הודעה לעמוד; בלי שם / שם ממלא-מקום — כמו קודם
b2 = SP.soc_build_post(ROW, "ר", clean, noft, agent={"name": "קובי חמו", "phone": ""})["body"]
ck("לפרטים: קובי חמו · הודעה לעמוד" in b2 and "wa.me" not in b2, b2)
for bad in ({}, None, {"name": "סוכן 8719", "phone": "0541234567"}, {"name": "משרד", "phone": "0541234567"},
            {"name": "(לא משויך)", "phone": "0541234567"}):
    bb = SP.soc_build_post(ROW, "ר", clean, noft, agent=bad)["body"]
    ck("לפרטים — הודעה לעמוד" in bb and "wa.me" not in bb, (bad, bb))
# בלי הפרמטר — בדיוק כמו קודם (תאימות)
ck(SP.soc_build_post(ROW, "ר", clean, noft)["body"].rstrip().endswith("לפרטים — הודעה לעמוד"), "default unchanged")
# טלפון בתיאור עדיין נמחק — רק הטלפון של הסוכן מופיע
b3 = SP.soc_build_post(dict(ROW, _desc_ae="התקשרו 052-9998887"), "ר", clean, noft, agent=AG)["body"]
ck("9998887" not in b3 and "972541234567" in b3, b3)

# soc_agent_for: הסוכן של הנכס + הנייד האישי מאנשי הקשר (גם באיות/רווחים שונים)
G, st, sb = make_G()
G["fetch_agents_phones"] = lambda: {"קובי  חמו": "054-1234567", "אחר": "0500000000"}
G["_canon_key"] = lambda s: " ".join(str(s).split())
a = SP.soc_agent_for(G, dict(ROW, **{"סוכן 1": "קובי חמו", "טלפון 1": "0559999999"}))
ck(a == {"name": "קובי חמו", "phone": "054-1234567"}, ("personal phone, not the listing phone", a))
ck(SP.soc_agent_for(G, dict(ROW, **{"סוכן 1": "לא קיים"})) == {"name": "לא קיים", "phone": ""}, "unknown agent")
G["fetch_agents_phones"] = lambda: (_ for _ in ()).throw(RuntimeError("down"))
ck(SP.soc_agent_for(G, dict(ROW, **{"סוכן 1": "קובי חמו"}))["phone"] == "", "contacts down -> no phone")
print("ok", n)
