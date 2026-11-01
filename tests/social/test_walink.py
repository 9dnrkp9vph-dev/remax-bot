# tests/social/test_walink.py — קישור הוואטסאפ בפוסט: הסוכן מקבל הודעה מוכנה עם פרטי הנכס ומאיפה הגיע הפונה
# (אייל 02/11: 'שבקישור הסוכן יידע על מה מדובר, פרטי הנכס ומאיפה הגיע')
import os, sys
from urllib.parse import urlparse, parse_qs
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..")); sys.path.insert(0, HERE)
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from flask import Flask
import social_publish as SP
from _fakes import ROW, make_G

clean = lambda d: str(d or "").strip()
noft = lambda row: []
AG = {"name": "אירנה אוברוב", "phone": "0546761233"}

# 1) בפוסט: קישור קצר של אפי (בלי עברית מקודדת), לא wa.me ישיר
b = SP.soc_build_post(ROW, "RE/MAX Family", clean, noft, agent=AG, wa_link="https://app.test/v2/social/wa/tok1")["body"]
ck("וואטסאפ: https://app.test/v2/social/wa/tok1" in b and "wa.me" not in b and "%D7" not in b, b)
# בלי wa_link — wa.me ישיר כמו קודם
ck("https://wa.me/972546761233" in SP.soc_build_post(ROW, "ר", clean, noft, agent=AG)["body"], "fallback direct")

# 2) הנוסח לסוכן
t = SP.soc_wa_text(ROW, "אירנה אוברוב", "RE/MAX Family", "fb")
ck(t.startswith("היי אירנה,") and "בעמוד הפייסבוק של RE/MAX Family" in t, t)
ck("4 חדרים" in t and "נאות אפק" in t and "קרית ביאליק" in t and "אהוד מנור" in t and "1,890,000" in t, t)
ck("13" not in t, ("no house number", t))
ck("tok1" in t, ("ad number so the agent can find it", t))
ck("באינסטגרם של" in SP.soc_wa_text(ROW, "אירנה", "RE/MAX Family", "ig"), "ig source")

# 3) הראוט הציבורי: מפנה לוואטסאפ של הסוכן עם ההודעה, ורושם ביומן
G, st, sb = make_G()
G["fetch_agents_phones"] = lambda: {"דנה לוי": "052-1112233"}
app = Flask(__name__); SP.register(app, G); c = app.test_client()
r = c.get("/v2/social/wa/tok1")
ck(r.status_code == 302, r.status_code)
loc = urlparse(r.headers["Location"])
ck(loc.netloc == "wa.me" and loc.path == "/972521112233", r.headers["Location"])
txt = parse_qs(loc.query)["text"][0]
ck(txt.startswith("היי דנה,") and "הפייסבוק" in txt and "1,890,000" in txt, txt)
ck(any("פנייה בוואטסאפ" in str(a) for a in st["acts"]), st["acts"])
ck(c.get("/v2/social/wa/tok1?s=ig").status_code == 302 and "באינסטגרם" in parse_qs(urlparse(
    c.get("/v2/social/wa/tok1?s=ig").headers["Location"]).query)["text"][0], "ig param")
# נכס שלא קיים / בלי טלפון לסוכן — דף קצר, לא שגיאה
ck(c.get("/v2/social/wa/nope").status_code == 404, "unknown")
G["fetch_agents_phones"] = lambda: {}
r2 = c.get("/v2/social/wa/tok1")
ck(r2.status_code == 404 and "לא זמינים" in r2.get_data(as_text=True), (r2.status_code, r2.get_data(as_text=True)[:200]))
# 4) באינסטגרם (קישור בטקסט לא לחיץ): המספר + בקשה לציין את מספר המודעה ושזה מאינסטגרם
ig = SP.soc_build_post(ROW, "RE/MAX Family", clean, noft, agent=AG, wa_link="https://app.test/v2/social/wa/tok1")["ig_caption"]
ck("לפרטים בוואטסאפ: אירנה אוברוב · 054-676-1233" in ig, ig)
ck("ציינו בהודעה: מודעה tok1 מאינסטגרם" in ig and "app.test" not in ig, ig)
print("ok", n)
