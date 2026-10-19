# CRM שלב 3 — דשבורד חי — תוכנית בנייה

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (אייל בחר Native). Steps use checkbox (`- [ ]`) syntax.

**Goal:** עמוד `/v2/crm/dashboard` למחשב, לאייל בלבד. בראש העמוד שורת בריאות (ירוק/צהוב/אדום לכל זרם), מתחתיה מדדים לפי תקופה, גרפים יומיים ל-30 יום, ומונה חיפושי AI באתר ובאפי.

**Architecture:** API אחד, `GET /v2/api/crm/dashboard`, למפתח בלבד. הוא נבנה דרך `_swr` (ttl של 15 דק', כך שאחרי הבנייה הראשונה התשובה מיידית) ומרכיב את התשובה ממקורות קיימים. הסיכומים לפי תקופה באים מ-`build_office_report(today)["data"]`. הסדרות היומיות, מצב הבריאות וספירות ה-AI באפי מחושבים בפונקציות טהורות חדשות ב-effie_v2. עמוד ה-HTML קורא ל-API עם `fbTok`, באותו דפוס של `/v2/crm/parallel`. הגרפים ב-Chart.js 4.4.1 מ-cdnjs.

**Spec:** `docs/superpowers/specs/2026-10-19-crm-dashboard-design.md` §6.4.

## Global Constraints
- גישה רק דרך `_is_dev` (אייל). אחרים מקבלים 403.
- מחשב ומסך רחב. בטלפון רק שלא יישבר (העמודות נערמות).
- פלטת אפי בלבד: קרם `#F2EFE7`, נייבי `#1E3A5F`, זהב `#C29435` ל-AI, ירוק `#157A43`, אדום `#C24040` רק למצב "תקלה". פונט Heebo, RTL, כרטיסים לבנים עם radius 20 וצל `0 6px 20px rgba(30,58,95,.06)`. בלי אימוג'ים.
- שום שינוי בטבלאות. העמוד קורא בלבד.
- רענון: בטעינה, בכפתור "רענן", ואוטומטית כל 15 דק'.
- בדיקות: `tests/crm/` עם `_load.py` / ראוט אמיתי עם מקורות מזויפים.

## Review Focus
1. **שבת וחג:** אין שיחות ואין חתימות, וזה לא תקלה. מצב "שקט" אפור, לא אדום. נבדק ב-Task 1.
2. **מקור שנופל** (Supabase / הגיליון): הדשבורד מציג את שאר המקורות ומסמן את המקור שנפל כ"אין נתון", בלי 500. נבדק ב-Task 3.
3. **בנייה ראשונה איטית** (הדוח היומי לא שמור במטמון, 5–8 ש'): מוצג "טוען…", והבנייה לא מתבצעת פעמיים במקביל (`_swr`). נבדק ב-Task 3.
4. **תאריכים בפורמטים שונים** (ISO-Z, DD/MM/YYYY HH:MM, YYYY-MM-DD) בסדרות היומיות: כל אחד נספר ביום הישראלי הנכון. נבדק ב-Task 2.
5. **אין נתון לזרם** (למשל עדיין אין חשבוניות ישירות): צהוב "אין נתון", לא אדום ולא קריסה. נבדק ב-Task 1.

---

### Task 1: מצב בריאות לכל זרם (פונקציה טהורה)

**Files:** Modify `effie_v2.py` (רמת מודול, ליד `crm_ts`) · Test `tests/crm/test_dash_health.py`

**Interfaces — Produces:**
- `CRM_STREAMS`: רשימת `(key, label, max_gap_hours, work_hours_only)`:
  - `calls` "שיחות": 3 שעות, רק בשעות עבודה
  - `signatures` "חתימות": 30 שעות
  - `invoices` "חשבוניות": 30 שעות
  - `newborn` "נכס נולד (סורק פרטי)": 3 שעות, רק בשעות עבודה
  - `office` "נכסי המשרד (סורק)": 8 שעות
  - `shtaf` "שת"פ (סורק)": 30 שעות
  - `site_leads` "לידים מהאתר": 72 שעות
  - `app_usage` "שימוש באפי": 3 שעות, רק בשעות עבודה
- `crm_health(last_ts: float|None, now: float, max_gap_h: float, work_only: bool, quiet: bool) -> str`, שמחזיר אחד מ-`"ok" | "warn" | "bad" | "quiet" | "none"`:
  - `quiet=True` (שבת/חג) מחזיר `quiet`. `last_ts=None` מחזיר `none`.
  - פער קטן מ-`max_gap_h` → `ok`. פער עד פי 2 → `warn`. מעבר לזה → `bad`.
  - כש-`work_only` מחושבות רק שעות עבודה: א'–ה' 08:00–20:00 וו' 08:00–13:00, בשעון ישראל. מחוץ לשעות העבודה ספירת הפער נעצרת.
- שעות העבודה מחושבות בפונקציה `_work_hours_between(a, b) -> float` (שעון ישראל).

- [ ] **Step 1: failing test**
```python
H=3600; mon10=ts("2026-10-19 10:00")
ck(health(mon10-1*H, mon10, 3, True, False)=="ok")
ck(health(mon10-5*H, mon10, 3, True, False)=="warn")
ck(health(mon10-7*H, mon10, 3, True, False)=="bad")
# הפסקת לילה לא נספרת: שיחה אחרונה ב-19:30 אתמול, עכשיו 08:30 → חצי שעה עבודה + חצי שעה = ok
ck(health(ts("2026-10-18 19:30"), ts("2026-10-19 08:30"), 3, True, False)=="ok")
ck(health(mon10-5*H, mon10, 3, True, True)=="quiet")
ck(health(None, mon10, 3, True, False)=="none")
ck(health(mon10-40*H, mon10, 30, False, False)=="warn")
```
- [ ] **Step 2:** הבדיקה נכשלת. **Step 3:** מימוש. **Step 4:** הבדיקה עוברת + ast. **Step 5:** Commit.

### Task 2: סדרות יומיות ל-30 יום (פונקציה טהורה)

**Files:** Modify `effie_v2.py` · Test `tests/crm/test_dash_series.py`

**Interfaces — Produces:**
`crm_daily_series(rows: list, get_when, days: int, today_iso: str) -> list[int]`. מחזיר רשימה באורך `days`: הערך האחרון הוא היום, והראשון הוא לפני `days-1` ימים. היום של כל שורה הוא `get_when(row)`, ממופה ליום ישראלי דרך `crm_ts`. שורה בלי תאריך או מחוץ לטווח לא נספרת.

- [ ] **Step 1: failing test**
```python
rows=[{"t":"2026-10-19T06:00:00Z"},{"t":"18/10/2026 23:30"},{"t":"2026-10-18T22:30:00Z"},{"t":""},{"t":"2026-09-01"}]
s=series(rows, lambda r:r["t"], 3, "2026-10-19")
ck(s==[0,1,2], s)   # 22:30Z = 00:30 בישראל ב-19/10 (שעון חורף +2)
```
- [ ] **Steps 2–5** כמו ב-Task 1.

### Task 3: API `/v2/api/crm/dashboard`

**Files:** Modify `effie_v2.py` (ראוט בתוך `register`) · Test `tests/crm/test_dash_route.py`

**Interfaces — Consumes:** `crm_health`, `CRM_STREAMS`, `crm_daily_series`, `crm_ts`; `G["build_office_report"]`, `G["web_fetch_raw"]`, `G["get_signings"]`, `G["_fetch_manual_buyers"]`, `G["fetch_newborn"]`, `G["_activity_fetch"]`, `G["_usage_rows"]`, `G.get("site_ai_usage")`, `sb.fetch_invoices_rows`, `G["_swr"]`, `G["_is_dev"]`, `G["_web_auth"]`.

**Produces:** JSON
```
{ok, built_at, health:[{key,label,status,last}], periods:{calls,calls_answered,signings,signings_by_label,buyers,newborn,shtaf,deals_opened,deals_closed,office_active,open_now,lawyer_now},
  series:{days:[iso…30], calls:[…], signings:[…], buyers:[…], newborn:[…]},
  ai:{site:{today,cap,blocked,cache,hours:{HH:n}}, site_7d:[…7], effie_today:{props,newborn,buyers_ai,ask}, effie_7d:[…7]},
  usage_today:[{name,min}…10], insights:[…], scans:{…}}
```
- כל מקור עטוף ב-try. מקור שנופל מחזיר את ברירת המחדל שלו (0 / רשימה ריקה / `none`), ונרשמת שורת לוג.
- `quiet` נקבע לפי חלון השבת/חג הקיים (`_shabbat_window` או מה שמשמש את `SHABBAT_AUTO`; הבונה מאתר את הפונקציה).
- הבנייה עוברת דרך `G["_swr"]("crmdash", 900, build)`. `?fresh=1` עוקף את המטמון.
- `last` של כל זרם:
  - שיחות / חתימות: הכי חדש מ-`received_at`
  - חשבוניות: `fetch_invoices_rows("",limit=1)`
  - נכס נולד / משרד / שת"פ: מ-`data["scans"]`
  - לידים מהאתר: הפעולה האחרונה ב-activity שמתחילה ב"ליד מהאתר" או "פנייה מהאתר"
  - שימוש באפי: הפינג האחרון
- ספירות ה-AI באפי לפי פעולות ב-activity: "חיפוש נכסים", "חיפוש נכס נולד", "חיפוש קונה AI", "שאל את אפי".

- [ ] **Step 1: failing test** — הראוט האמיתי עם מקורות מזויפים: 403 בלי מפתח · מבנה המפתחות · מקור אחד שזורק → שאר השדות מלאים והמצב שלו `none` · `site_ai_usage` חסר → `ai.site.today==0` · `_swr` נקרא עם `"crmdash"`.
- [ ] **Steps 2–5.**

### Task 4: העמוד `/v2/crm/dashboard`

**Files:** Modify `effie_v2.py` (קבוע `_CRM_DASH_HTML` + ראוט) · Test `tests/crm/test_dash_page.py`

**Layout (החלטה שלי, מבנה פיירברי):**
- כותרת "לוח בקרה" + "עודכן HH:MM" + כפתור "רענן".
- **שורת בריאות:** כרטיס קטן לכל זרם, עם נקודה צבעונית, שם הזרם ו"לפני X דק'/שעות".
- **מדדים:** 6 כרטיסים: שיחות (נענו %) · חתימות (בלעדיות) · קונים חדשים · נכס נולד · עסקאות (נפתחו/נסגרו, פתוחים, אצל עו"ד) · נכסי המשרד בפרסום. בכל כרטיס בורר היום / השבוע / החודש / השנה, משותף לכל הכרטיסים.
- **גרפים:** קווים ל-30 יום (שיחות, חתימות, קונים, נכס נולד), עמודות לשעות היום של חיפושי AI באתר, ועמודות ל-7 ימים של AI באתר מול AI באפי.
- **כרטיס AI:** "היום X מתוך תקרה Y" באתר, וחסימות + מטמון. הצבע זהב (AI), ואדום רק כשהשימוש ≥ 90% מהתקרה.
- **תחתית:** תובנות מהדוח היומי + 10 המשתמשים הפעילים היום באפי + קישור ל"דוח מקבילות".
- Chart.js `https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js`. אם הסקריפט לא נטען, הגרפים מוחלפים בטבלת מספרים.
- [ ] **Step 1: failing test:** 200 + `fbTok` + `/v2/api/crm/dashboard` + `dir="rtl"` + `Heebo` + `chart.umd.min.js`. ה-JS עובר `node --check`.
- [ ] **Steps 2–5.** + **בדיקה ויזואלית:** הרצה מקומית עם API מזויף וצילום מסך ב-1440px וב-390px.

### Task 5: קישורים + יומן
- [ ] קישור "לוח בקרה" במסך הניהול (`/v2/admin`) למפתח בלבד, וקישור בעמוד דוח המקבילות.
- [ ] שורה ביומן ההחלטות ב-remax-family. Commit.

**לא בתוכנית הזו:** פוש כשזרם עובר לאדום. לפי הספק זה חלק מהדשבורד, אבל זה דורש לולאת רקע, ולכן ייבנה בתוכנית המשך קטנה אחרי שאייל יראה את הספים בפועל.
