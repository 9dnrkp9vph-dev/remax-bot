# site_api — הממשק בין אפי לאתר refamily.co.il

מודול נפרד (`site_api.py`), נרשם מ-app.py אחרי effie_v2. כשל בו לא מפיל את אפי.

## env (Render של אפי)
| משתנה | |
|---|---|
| `SITE_KEY` | מחרוזת סודית — **אותו ערך** כמו ב-Render של האתר. ריק = הראוטים לאתר כבויים (403) |
| `SITE_PUBLIC_URL` | כתובת האתר לכפתור "צפה באתר" (ברירת מחדל `https://refamily-site.onrender.com`) |
| `SITE_SEARCH_PER_MIN` | תקרת חיפושים מהאתר לדקה (ברירת מחדל 60); בנוסף עד 2 במקביל |

## ראוטים
- `POST /site/api/search {key, q}` → `{ok, keys:[מספר מודעה...], summary}` — המוח של חיפוש הנכסים, נכסי המשרד בלבד, בלי מוסתרים, בלי פרטים אישיים.
- `POST /site/api/form {key, kind: value|contact|career, fields}` → `{ok}` — מייל לנמעני הדוח היומי.
- `GET /v2/api/site/state`, `POST /v2/api/site/prop` — הסתר/מומלץ מכרטיסי "שלי" (סוכן — נכס שלו; מנהל/מפתח — הכל; עד 6 מומלצים פעילים).
- `GET/POST /v2/api/site/settings`, `GET /v2/site` — מסך "האתר" (מנהל/מפתח בלבד; לא הנה"ח/מזכירה).

## טבלה
`website_settings` — `remax-family/supabase/migrations/20261013_website_settings.sql`. בלי הטבלה: המסכים מציגים הודעה, האתר עובד עם ברירות מחדל.

## בדיקות
`python -m pytest tests/siteweb -q` (דורש flask + pytest).
