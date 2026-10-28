# tests/ai_digest/test_ai_digest.py — אייל 29/10: 'סריקת AI אוטומטית כל יום ב-11 ומייל של כל השינויים מיום לפני
# רק של המסך הזה (בלי שבתות וחגים)'. ai_digest.py = פונקציות טהורות; ההדבקה ב-app.py נבדקת סטטית.
import os, sys, datetime as dt
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
import ai_digest as A

n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1

d = lambda s: dt.datetime.strptime(s, "%Y-%m-%d %H:%M")
T0 = d("2026-10-29 11:00").timestamp()
recs = [
    {"key": "ps:1", "date": T0 - 3600 * 5, "type": "לקוח עבר מפרסם נכס", "name": "דנה", "phone": "0501111111", "agent": "אלי",
     "what": "מפרסם למכירה: הרצל 5", "past": "עסקה: קונה · הרצל 5", "status": "", "link": "https://yad2/x", "buyer_link": ""},
    {"key": "pb:2|7", "date": T0 - 86400 * 9, "type": "לקוח עבר נוסף כקונה", "name": "רון", "phone": "0502222222", "agent": "נדב",
     "what": "4 חד' בביאליק", "past": "", "status": "", "link": "", "buyer_link": "/v2/crm/buyers?q=0502222222"},
    {"key": "bs:3", "date": T0 - 86400 * 30, "type": "קונה שמפרסם נכס", "name": "גיל", "phone": "0503333333", "agent": "אוהד",
     "what": "מפרסם: בגין 2", "past": "", "status": "נשלח לסוכן", "link": "", "buyer_link": ""},
]

# 1. בלי צילום קודם (ריצה ראשונה): חדש = מה שקרה מאז since
new, changed, snap = A.digest_diff(recs, None, since_ts=T0 - 86400)
ck([r["key"] for r in new] == ["ps:1"] and changed == [], (new, changed))
ck(snap == {"ps:1": "", "pb:2|7": "", "bs:3": "נשלח לסוכן"}, snap)

# 2. עם צילום: חדש = מפתח שלא היה (גם אם התאריך ישן), שונה = מצב שהשתנה; מה שנעלם לא מדווח
prev = {"ps:1": "", "bs:3": "ממתין לשליחה", "gone:9": ""}
new, changed, snap = A.digest_diff(recs, prev, since_ts=T0 - 86400)
ck([r["key"] for r in new] == ["pb:2|7"], new)
ck([(r["key"], r["prev_status"]) for r in changed] == [("bs:3", "ממתין לשליחה")], changed)
ck("gone:9" not in snap, snap)

# 3. בלי שינויים
new, changed, _ = A.digest_diff(recs, snap, since_ts=T0 - 86400)
ck(new == [] and changed == [], (new, changed))

# 4. מתי שולחים: 11:00 ואילך, לא בשבת/חג, פעם ביום, ניסיון חוזר אחרי 15 דק' עד 8
ck(A.digest_due(d("2026-10-29 11:00"), {}, quiet=False, hour=11, now_ts=T0), "חמישי 11:00")
ck(not A.digest_due(d("2026-10-29 10:59"), {}, quiet=False, hour=11, now_ts=T0), "לפני 11")
ck(not A.digest_due(d("2026-10-31 11:00"), {}, quiet=False, hour=11, now_ts=T0), "שבת — לפי היום בשבוע")
ck(not A.digest_due(d("2026-10-29 11:00"), {}, quiet=True, hour=11, now_ts=T0), "חג (חלון השתקה)")
ck(not A.digest_due(d("2026-10-29 12:00"), {"ok": True, "ts": T0}, quiet=False, hour=11, now_ts=T0), "כבר נשלח היום")
ck(not A.digest_due(d("2026-10-29 11:05"), {"ok": False, "ts": T0 - 60, "tries": 1}, quiet=False, hour=11, now_ts=T0), "ניסיון חוזר רק אחרי 15 דק'")
ck(A.digest_due(d("2026-10-29 11:20"), {"ok": False, "ts": T0 - 1200, "tries": 1}, quiet=False, hour=11, now_ts=T0), "ניסיון חוזר")
ck(not A.digest_due(d("2026-10-29 13:00"), {"ok": False, "ts": T0 - 9999, "tries": 8}, quiet=False, hour=11, now_ts=T0), "עד 8")

# 5. התוכן: נושא, כל התראה עם שם/טלפון/סוכן/מה קרה, קישורים מלאים, שינוי מצב, וקישור לטאב
new, changed, _ = A.digest_diff(recs, {"bs:3": "ממתין לשליחה"}, since_ts=T0 - 86400)
subj, html, text = A.digest_render(new, changed, office="רימקס פמילי", base="https://remax-bot.onrender.com", day="29/10/2026")
ck("התראות AI" in subj and "29/10/2026" in subj and "2 חדשות" in subj and "1 עודכנה" in subj, subj)
for s in ("דנה", "0501111111", "אלי", "מפרסם למכירה: הרצל 5", "https://yad2/x", "רון",
          "https://remax-bot.onrender.com/v2/crm/buyers?q=0502222222", "https://remax-bot.onrender.com/v2/crm/ai",
          "ממתין לשליחה", "נשלח לסוכן", "לקוח עבר מפרסם נכס"):
    ck(s in html, "html: " + s)
ck("דנה" in text and "https://remax-bot.onrender.com/v2/crm/ai" in text, text)
ck('dir="rtl"' in html, "rtl")
ck("<script" not in html.lower() and "&lt;b&gt;" in A.digest_render([dict(recs[0], name="<b>")], [], "o", "https://x", "1")[1], "escape")

# 6. יום בלי שינויים — מייל קצר שאומר את זה (שיידע שהסריקה רצה)
subj, html, text = A.digest_render([], [], office="רימקס פמילי", base="https://x", day="29/10/2026")
ck("אין שינויים" in subj and "אין התראות חדשות" in html, subj)

# 6ב. [29/10] לקוחות חוזרים — הודעת וואטסאפ לאייל בלבד (לא לסוכנים); בלי לקוחות חוזרים אין הודעה
rcr = {"key": "rc:541|20261028", "date": T0 - 3600, "type": "לקוח חוזר", "name": "משה כהן", "phone": "0541111111",
       "agent": "דקלה ביבי", "what": "חתם שוב — מוכר + בלעדיות: שבזי 4", "past": "עסקה: קונה · הנוטר 18", "status": "נחתם חלקית"}
ck(A.digest_wa_text(new, changed, "https://x", "29/10/2026") == "", "בלי לקוחות חוזרים — בלי הודעה")
w = A.digest_wa_text([rcr, recs[0]], [], "https://remax-bot.onrender.com", "29/10/2026")
for s_ in ("לקוחות חוזרים", "29/10/2026", "משה כהן", "0541111111", "חתם שוב — מוכר + בלעדיות: שבזי 4", "דקלה ביבי", "הנוטר 18",
           "https://remax-bot.onrender.com/v2/crm/ai"):
    ck(s_ in w, "wa: " + s_)
ck("דנה" not in w, "רק לקוחות חוזרים")
ck("משה כהן" in A.digest_wa_text([], [dict(rcr, prev_status="ממתין לחתימה", status="נחתם")], "https://x", "1"), "גם כשנחתם")

# 7. ההדבקה ב-app.py: הלולאה של הדוח היומי מריצה את הסריקה, והשבת/חג נבדקים
SRC = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
loop = SRC.split("def _report_daily_loop_body")[1][:4000]
ck("_ai_digest_tick(now)" in loop, "tick בלולאה")
tick = SRC.split("def _ai_digest_tick")[1][:3000]
ck("_shabbat_quiet_now()" in tick and "AI_DIGEST" in tick and "v2_ai_digest" in tick and "_crm_ai_rows" in tick, "tick")
ck("CRM_OWNER_EMAILS" in tick or "_crm_owner_emails" in tick, "נשלח לבעל המשרד בלבד")
ck("digest_wa_text" in tick and "send_text(" in tick and "OWNER_PUSH_ID" in tick and "AI_DIGEST_WA" in tick, "וואטסאפ לאייל")
EV = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
ck('G["_crm_ai_rows"]' in EV, "effie_v2 חושף את רשומות ה-AI")
ck('"ai_digest"' in EV, "באוטומציות")
print("OK", n, "checks")
