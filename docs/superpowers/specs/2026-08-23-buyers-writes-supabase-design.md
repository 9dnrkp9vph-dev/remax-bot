# כתיבות הקונים → Supabase ישירות (23/08/2026)

## רקע
הקריאות של הקונים כבר על Supabase (`BUYERS_SOURCE=supabase`, `fetch_buyers_rows`: `sheet_row`+`raw`
עם 8 מפתחות: date,name,phone,budget,summary,agent,agent_phone,search). הכתיבות עדיין דרך Apps Script
(`addbuyer`/`updatebuyer`/`deletebuyer`) לגיליון, שמשכפל ל-Supabase ב-hook. אייל (13/08): קונים
מוזנים **רק מהאפליקציה** → הגיליון מיותר לקונים.

**הדורס (אותר 13/08, נוטרל 23/08):** טריגר `sbReconcileAll` (כל 30 דק') קרא ל-`sbBackfillBuyers`
שמוחק את טבלת buyers וממלא מהגיליון. אייל הוסיף `//` לשורה ושמר (23/08). `sbSyncRecent` (כל דקה)
נוגע רק בשיחות/חתימות (upsert) — לא רלוונטי.

## העיצוב
1. **supabase_db.py — שלוש פונקציות כתיבה:**
   - `buyers_insert(raw)` — `sheet_row` = max+1 (GET order=sheet_row.desc limit=1), POST; על 409
     (התנגשות ייחודיות) ניסיון חוזר עד 3 פעמים. מחזיר את מספר השורה.
   - `buyers_update(row, fields)` — GET raw של השורה, מיזוג השדות (search/phone/budget…), PATCH
     `raw`+`updated_at`. שורה לא קיימת → False.
   - `buyers_delete(row)` — RPC `buyers_delete_row` הקיים (מוחק ומזיז — אותה סמנטיקה כמו היום).
2. **app.py — מפזר `_buyers_write(action, payload)`:** חתימת תשובה זהה ל-`_buyers_apps_post`
   (`{"ok": True}` / `{"ok": False, "error": ...}`). `BUYERS_WRITE=supabase` (ברירת מחדל) → הפונקציות
   החדשות; `BUYERS_WRITE=sheets` → המסלול הישן 1:1 (rollback במשתנה סביבה אחד).
   אם Supabase לא מוגדר → נופל למסלול הישן.
3. **חמש נקודות הכתיבה עוברות למפזר** (`/api/buyers/add`, `/api/buyers/update`, `/api/buyers/delete`,
   `_add_buyer_from_signing`, `_merge_buyer_search`). שאר הלוגיקה (דדופ, הרשאות `as`, push, activity,
   `_cache_clear("buyers")`) ללא שינוי. מבנה הנתונים ללא שינוי — הקריאות/המסכים/הבריף לא נוגעים.
4. **גיליון "קונים" קופא** כגיבוי היסטורי. סטטוסי קונים נשארים בקובץ הדיסק (עובד).
5. **בדיקות (TDD, חילוץ ast):** insert max+1 ו-retry על 409; update ממזג ו-PATCH עם הפילטר הנכון;
   delete קורא ל-RPC; המפזר מנתב לפי הדגל ומחזיר את אותה חתימה; אין יותר `_buyers_apps_post("addbuyer"…)`
   ב-app.py. ast.
6. **אימות אחרי deploy (אייל):** קונה-בדיקה — הוספה → עריכת "מה מחפש" → מחיקה; החתמת מתעניין →
   קונה אוטומטי; המתנה של שעה (שני סבבי reconcile) לוודא שהכל נשאר.
