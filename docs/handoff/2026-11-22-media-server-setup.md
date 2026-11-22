# שרת המדיה — הקמה (22/11/2026)

שירות קטן שמרכיב את סרטוני השיווק במקום אפי. אותו ריפו (`remax-bot`), קובץ כניסה אחר (`media_app.py`).
אין בו מסד נתונים, וואטסאפ, Meta או תהליכי רקע.

## 1. יצירת השירות ב-Render
New → Web Service → הריפו `remax-bot`, ענף `main`.

| שדה | ערך |
|---|---|
| Name | `effie-media` |
| Region | Oregon (כמו אפי) |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn media_app:app` |
| Instance Type | Standard (2GB) — אפשר להקטין אחרי שרואים את גרף הזיכרון |
| Health Check Path | `/health` |
| Auto-Deploy | Yes |

משתנה סביבה אחד: `MEDIA_KEY` = מחרוזת אקראית ארוכה (לא בצ'אט, לא בגיט). `PYTHON_VERSION` — כמו באפי, אם מוגדר שם.

בדיקה: `https://effie-media.onrender.com/health` → `{"ok": true, "ffmpeg": true, "key": true}`.

## 2. חיבור אפי
ב-Render של `remax-bot`, שני משתנים:
- `MEDIA_URL` = `https://effie-media.onrender.com`
- `MEDIA_KEY` = אותו ערך בדיוק

השמירה מפעילה מחדש את אפי — לעשות בשעה שקטה.

## 3. בדיקה
'סרטון לרשתות' על נכס אחד. בלוג של `effie-media` אמורות להופיע `POST /render` ו-`GET /job/...`.

## חזרה אחורה
למחוק את `MEDIA_URL` באפי → הרינדור חוזר להיות מקומי, עם הגנת הזיכרון (לא מתחיל בלי 600MB פנויים).

## מה קורה כששרת המדיה לא זמין
הסרטון נכשל עם 'שרת הסרטונים לא זמין כרגע — נסו שוב בעוד כמה דקות'. אפי, הפוסטים וכל השאר ממשיכים לעבוד.
