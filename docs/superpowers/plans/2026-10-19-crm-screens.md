# CRM שלב 2 — מסכי CRM במבנה פיירברי (מתחיל מלוג שיחות) — תוכנית בנייה

> **For agentic workers:** superpowers:executing-plans (Native, כמו בשלבים הקודמים).

**Goal:** עמוד `/v2/crm/calls` לפי דוגמת המסך שאייל אישר (`remax-family/docs/handoff/mockups/crm-calls-mockup.html`):
- מודולים למעלה
- תצוגות שמורות בצד
- טבלה עם חיפוש, מיון, עמודות, סינון, דפדוף, ייצוא לאקסל ו"+ חדש"
- כרטיס רשומה במגירה משמאל: סיכום, ביקורת, תמלול מלא, עריכה, מחיקה, "הוסף כקונה" ווואטסאפ

המנוע גנרי, כך ששאר המודולים (מתעניינים, מקבלי מסמכים וכו') יתווספו בהמשך כהגדרה בלבד.

**Architecture:**
- **השרת:** `crm_query(records, q, filters, sort, page, size)` טהור על רשומות מנורמלות. הרשומות נבנות מהמקור הקיים (`web_fetch_raw("שיחות")`, כבר במטמון) ובתוספת שכבת עריכות.
- **שכבת העריכות:** טבלה חדשה `crm_overrides`. עד הניתוק הסנכרון מהגיליון דורס את `calls`, ולכן עריכה לא נכתבת ישירות לטבלה.
- **מחיקה:** דרך `hidden_calls` הקיים (הסתרה הפיכה, ומסך השיחות באפי מכבד אותה).
- **רשומה חדשה:** נכתבת ל-`calls` עם `source_key="crm:<uuid>"`, שהסנכרון לא נוגע בו.
- **תמלול מלא:** מ-`call_transcripts`. קיים רק לשיחות שהגיעו מ-Make הישיר, מ-19/10 והלאה.
- **תצוגות שמורות:** בקונפיג `v2_crm_views` דרך `_config_mutate`.
- **העמוד:** HTML אחד, שמקבל מה-API את הגדרת העמודות של המודול.

**Spec:** `docs/superpowers/specs/2026-10-19-crm-dashboard-design.md` §6.3 + דוגמת המסך.

## Global Constraints
- מפתח בלבד (`_is_dev`), מחשב. פלטת אפי, Heebo, RTL. אייקונים ב-SVG ולא באימוג'ים. אדום רק למחיקה (ריבוע `#FBEDED`).
- אין שינוי בטבלאות קיימות. מותר רק להוסיף את `crm_overrides`.
- כל כתיבה נרשמת ב-`activity_log`.
- טלפונים מוצגים מלאים, כי המסך הוא של אייל בלבד. בייצוא לאקסל הטלפון מלא.

## Review Focus
1. **עריכה שנדרסת** ע"י הסנכרון מהגיליון: נשמרת בשכבה ומוצגת אחרי הסנכרון. (Task 2)
2. **חיפוש בעברית** (גרש וגרשיים, טלפון עם או בלי מקפים, 972): מוצא. (Task 2)
3. **5,000+ שורות:** דפדוף בשרת של 50 לעמוד, ותשובה מהירה מהמטמון. (Task 3)
4. **מחיקה בטעות:** הסתרה הפיכה, ובמגירה כפתור "שחזר". (Task 3)
5. **ייצוא עם עברית** נפתח באקסל תקין (CSV עם BOM). (Task 3)

---
### Task 1: מיגרציה + גישה ל-DB
`remax-family/supabase/migrations/20261019_crm_overrides.sql`: `crm_overrides(id uuid pk, office_id uuid, module text, record_key text, fields jsonb, updated_at timestamptz, updated_by text, unique(office_id,module,record_key))`, RLS בלי policies.
ב-`supabase_db`:
- `crm_overrides_fetch(module) -> dict[key, fields]`
- `crm_override_upsert(module, key, fields, by)` (מיזוג עם הקיים)
- `transcript_get(source_key) -> dict|None`

### Task 2: מודול השיחות + מנוע השאילתות (טהור)
- `CRM_MODULES["calls"]`: עמודות `[(key, label, type)]`: agent, caller_phone, date, status, duration, summary, score. בנוסף: שדות לעריכה, ותצוגות מובנות:
  - הכל
  - היום
  - לא נענו
  - יוצאות (call2call)
  - ביקורת 1–2
- `crm_calls_records(rows, overrides, hidden) -> list[dict]`: `key`=event_id; `date` כ-epoch; `status_label` (נענתה/לא נענתה/יוצאת/תפוס/בוטלה); `score` מתוך "ציון: N/5" ב-`call_review`; עריכות מהשכבה מעל המקור; מוסתרות מסומנות ב-`hidden=True`.
- `crm_query(records, q, filters, sort, page, size) -> {rows,total}`:
  - חיפוש: כל המילים בכל העמודות, טלפון לפי 9 ספרות אחרונות, נרמול גרש/גרשיים.
  - filters: `{field: value}`, `date_from`/`date_to` (ISO), `view`.
  - מיון לפי עמודה ⇅. מוסתרות מוחרגות, חוץ מ-`view=hidden`.
- `crm_csv(records, columns) -> bytes`: עם BOM.

### Task 3: API
מפתח בלבד:
- `GET /v2/api/crm/<module>/meta`: עמודות, תצוגות ומונים.
- `GET /v2/api/crm/<module>/list?q&view&sort&dir&page&f_<field>`.
- `GET /v2/api/crm/<module>/record?key=`: הרשומה עם `transcript`, `recording`, `review`.
- `POST /v2/api/crm/<module>/record`: עם `{key, fields}` → עריכה. עם `{fields}` בלי key → חדש. עם `{key, delete:true}` → הסתרה. עם `{key, restore:true}` → שחזור.
- `GET /v2/api/crm/<module>/export?...`: CSV של הסינון הנוכחי.
- `GET/POST /v2/api/crm/views?module=`: תצוגות שמורות של אייל.

### Task 4: העמוד `/v2/crm/<module>`
- המבנה של דוגמת המסך.
- מודולים שעוד לא בנויים מוצגים מעומעמים, עם "בקרוב".
- "לוח בקרה" מוביל ל-`/v2/crm/dashboard`.
- המגירה: עריכה inline של שדות העריכה, שמירה, ופח (אישור + שחזור).
- "הוסף כקונה" פותח את `/v2/buyers` עם prefill (שם וטלפון).
- וואטסאפ דרך wa.me (נספר אוטומטית).
- בחירת עמודות נשמרת ב-localStorage.
- בדיקה ויזואלית: 1440 + 390, בלי גלילה הצידה.

### Task 5: קישורים, יומן, ביקורת עצמאית בסוף.
