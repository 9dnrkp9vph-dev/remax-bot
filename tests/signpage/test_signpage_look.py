# tests/signpage/test_signpage_look.py — אייל 10/11: עמוד ההסכם בעיצוב חתימה טובה, "בלי סיכונים"
# (הלקח מ-24/08: כפתור 'המשך לחתימת הבלעדיות' שמת בשקט). מרנדר את /s/<token> האמיתי.
import os, sys, re; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _render import *
n = 0
def ck(c, m=""):
    global n; assert c, m; n += 1
HDR2 = HDR + "\nכתובת הלקוח: הנביאים 54 קרית אתא\nמייל הלקוח: karubis1509@gmail.com"
BODY = "בין הלקוח…\n1. סעיף ראשון\n   4.1 במכירה 1% ממחיר המכירה"
# 1) ממתין עם הסכם בלעדיות מחובר — ה-JS (כולל הכפתור) זהה לחלוטין למה שהיה לפני השינוי
DOCS["tokSELLER0000001"] = {"status": "pending", "header": HDR, "docs": json.dumps([{"deal_type": "OWNER_SALE", "title": "הזמנת שירותי תיווך למכירת נכס מקרקעין", "body": "1. סעיף\n\nהערות: סעיף 4.2 מבוטל", "next_token": "tokEXCL000000002", "next_title": "הזמנת שירותי תיווך בבלעדיות"}])}
DOCS["tokEXCL000000002"] = {"status": "pending", "header": HDR, "docs": "[]"}
st, h = page("tokSELLER0000001")
ck(st == 200)
# js_snapshot.txt = ה-JS לפני השינוי של 10/11. שינוי מכוון בחתימה → לעדכן את הצילום במודע
before = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "js_snapshot.txt"), encoding="utf-8").read()
ck(script_of(h) == before, "ה-JS של עמוד החתימה השתנה!")
ck("location.href=\\''+('/s/'+encodeURIComponent(NX))" in h, "כפתור ההמשך לבלעדיות")
ck('"tokEXCL000000002"' in h and "חתימה ממתינה" in h)
for i in ("id=step1", "id=step2", "id=contBar", "id=pad", "id=cid", "id=agree", "id=sbtn"):
    ck(i in h, i)
ck("<div class=doctitle>הזמנת שירותי תיווך למכירת נכס מקרקעין</div>" in h)
ck("<div class=docnum>מס׳ <span>" in h)
ck("<h4>הערות ותוספות להסכם:</h4><div class=nt>סעיף 4.2 מבוטל</div>" in h and "\n\nהערות:" not in h.split("<div class=notes>")[0].split("id=step1")[-1])
ck("מחיר מכירה מבוקש" in h)
# 2) נחתם — חתימה מעל קו, תאריך ושעה, אישור תנאים, שדות הלקוח החדשים
DOCS["tokSIGNED0000003"] = {"status": "signed", "header": HDR2, "signature": "data:image/jpeg;base64,AAAA", "signed_at": "2026-11-04T19:49:57+02:00",
    "docs": json.dumps([{"deal_type": "OWNER_EXCLUSIVE", "title": "הזמנת שירותי תיווך בבלעדיות · להסכם מס' 08018", "body": BODY}])}
st, h = page("tokSIGNED0000003")
ck(st == 200)
ck("<div class=doctitle>הזמנת שירותי תיווך בבלעדיות</div>" in h)
ck("מצורף להסכם הזמנת שירותי תיווך מס׳ 08018" in h)
ck("מכתובת: <u>הנביאים 54 קרית אתא</u></span>" in h and "מייל: <u>karubis1509@gmail.com</u></span>" in h)
ck("<div class='sv dt'>19:49 · 04/11/2026</div><div class=ln>תאריך ושעה</div>" in h)
ck("src='data:image/jpeg;base64,AAAA'" in h and "<div class=ln>חתימה</div>" in h)
ck("תנאי השימוש ומדיניות הפרטיות" in h and "window.print()" in h)
ck("<script>" not in h, "בעמוד חתום אין סקריפט חתימה")
# 3) הסכם ישן: בלי שורות חדשות, בלי signed_at, כמה מסמכים (זוג ישן משותף) — לא נופל
DOCS["tokOLD0000000004"] = {"status": "signed", "header": HDR, "signature": "data:image/png;base64,BB",
    "docs": json.dumps([{"title": "הזמנת שירותי תיווך לקניית נכס מקרקעין", "body": "1. א"}, {"title": "נספח", "body": "2. ב"}])}
st, h = page("tokOLD0000000004")
ck(st == 200 and "<h2>נספח</h2>" in h and "מכתובת" not in h and "מייל:" not in h)
ck("<div class='sv dt'></div>" in h)
ck("מחיר קניה מבוקש" in h)
# 4) כותרת עם מחיר ריק ושורת נכס חסרה
DOCS["tokEMPTY00000005"] = {"status": "signed", "header": "", "signature": "", "docs": "[]"}
st, h = page("tokEMPTY00000005")
ck(st == 200 and "פרטי הנכס" not in h)
# 5) עזרים
ck(A._sign_price_label([{"deal_type": "CLIENT_RENT", "title": "הזמנת שירותי תיווך לשכירות נכס מקרקעין"}]) == "מחיר שכירות מבוקש")
ck(A._sign_price_label([{"deal_type": "CLIENT_SALE", "title": "הזמנת שירותי תיווך לקניה/שכירות נכס מקרקעין"}]) == "מחיר מבוקש")
ck(A._sign_price_label([{"deal_type": "OWNER_SALE", "title": "הזמנת שירותי תיווך למכירת ו/או השכרת נכס מקרקעין"}]) == "מחיר מבוקש")
ck(A._sign_price_label([]) == "מחיר מבוקש")
ck(A._sign_split_notes("x\n\nהערות: a\nb") == ("x", "a\nb"))
ck(A._sign_split_notes("x") == ("x", ""))
p = A._parse_sign_header(HDR2)
ck(p["caddr"] == "הנביאים 54 קרית אתא" and p["email"] == "karubis1509@gmail.com" and len(p["props"]) == 1 and p["props"][0]["price"] == "2,100,000", p)
ck(A._sign_header_prices(HDR2) == [2100000])
print("OK", n)
# 6) [10/11 אייל] תקופת הבלעדיות מודגשת; בהסכם שאינו בלעדיות — לא
DOCS["tokXDATES0000006"] = {"status": "signed", "header": HDR, "signature": "",
    "docs": json.dumps([{"deal_type": "OWNER_EXCLUSIVE", "title": "הזמנת שירותי תיווך בבלעדיות", "body": "3. הלקוח מזמין… לתקופה מיום 08/11/2026 ועד יום 08/05/2027 (להלן)"}])}
st, h = page("tokXDATES0000006")
ck("מיום <mark class=xd>08/11/2026</mark> ועד יום <mark class=xd>08/05/2027</mark>" in h, h[h.find("לתקופה"):h.find("לתקופה")+200])
DOCS["tokXDATES0000007"] = {"status": "signed", "header": HDR, "signature": "",
    "docs": json.dumps([{"deal_type": "OWNER_SALE", "title": "הזמנת שירותי תיווך למכירת נכס מקרקעין", "body": "מיום 08/11/2026 ועד יום 08/05/2027"}])}
st, h = page("tokXDATES0000007")
ck("<mark" not in h)
ck(A._sign_mark_excl("מיום ____ ועד יום ____") == "מיום ____ ועד יום ____")
ck(A._sign_mark_excl("מספר 18701 מיום 08/11/2026.") == "מספר 18701 מיום 08/11/2026.", "תאריך הסכם המוכר לא מודגש")
print("OK2", n)
