# 🏠 RE/MAX WhatsApp Bot — הוראות התקנה

## מה זה עושה
סוכן שולח "מצגת" + טקסט + תמונות → מקבל PDF מוכן בחזרה תוך ~30 שניות.

---

## שלב 1 — הכן את הקבצים

1. העתק את כל הקבצים לתיקייה: `app.py`, `requirements.txt`, `Procfile`, `railway.toml`
2. שים את קובץ הלוגו בתיקייה ושנה שמו ל: `logo.png`

---

## שלב 2 — Railway (שרת חינמי)

1. היכנס ל: https://railway.app
2. לחץ **"New Project" → "Deploy from GitHub"**
3. חבר את GitHub ודחוף את הקבצים לריפו חדש
4. Railway יזהה אוטומטית ויתקין הכל

### משתני סביבה ב-Railway (Variables):
```
MAYTAPI_TOKEN      = ה-API Key מ-maytapi.com
MAYTAPI_PHONE_ID   = ה-Phone ID מ-maytapi.com  
MAYTAPI_PRODUCT_ID = ה-Product ID מ-maytapi.com
CLAUDE_API_KEY     = ה-API Key מ-console.anthropic.com
TRIGGER_WORD       = מצגת
```

לחץ **Deploy** — Railway יתן לך URL כגון:
`https://remax-bot-production.up.railway.app`

---

## שלב 3 — Maytapi Webhook

1. היכנס ל: https://console.maytapi.com
2. לחץ על הטלפון שלך → **Webhook**
3. הכנס את ה-URL:
   `https://remax-bot-production.up.railway.app/webhook`
4. שמור

---

## שלב 4 — בדיקה

שלח בוואטסאפ למספר שלך:
```
מצגת
רחוב הרצל 10, חיפה
דירת 4 חדרים, 100 מ"ר
קומה 3/8, מחיר 1,500,000 ₪
חניה ומחסן
ישראל ישראלי - 050-1234567
```
ואז שלח 1-4 תמונות.

אחרי ~30 שניות — PDF חוזר אוטומטית! ✅

---

## זרימת השימוש

```
סוכן שולח: "מצגת" + טקסט הנכס
    ↓
בוט: "קיבלתי! שלח תמונות"
    ↓
סוכן שולח: 1-4 תמונות
    ↓ (45 שניות המתנה)
בוט: שולח PDF מוכן 🎉
```

**טיפ:** אם שלחת 4 תמונות — העיבוד מתחיל מיד ולא ממתין.

---

## מחירים משוערים
- **Railway**: חינם עד 500 שעות/חודש (מספיק לשימוש יומי)
- **Maytapi**: $29/חודש לסים אחד
- **Claude API**: ~$0.01 לבקשה (זניח)
- **סה"כ**: ~$30/חודש

---

## תמיכה
אם השרת לא עולה — בדוק את Logs ב-Railway.
