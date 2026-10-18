# CRM שלב 1 — זרמים ישירים, ייבוא היסטוריה וניתוק פיירברי — תוכנית בנייה

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** עד 31/10/2026 — שיחות וחשבוניות מגיעות לאפי ישירות (לא דרך פיירברי), כל ההיסטוריה של שלושת המודולים בתוך אפי, ופיירברי מנותק בלי לאבד אף רשומה.

**Architecture:** ראוט קליטה חדש לשיחות לפי המתכון של `/v2/api/invoices/ingest`. בתקופת המקבילות הזרמים הישירים נכתבים לטבלת צל (`ingest_shadow`), ודוח השוואה יומי מוכיח שאין פערים מול המסלול הישן. בניתוק מחליפים משתנה סביבה, והזרם הישיר מתחיל לכתוב לטבלאות האמיתיות. התמלול המלא נשמר בטבלה חדשה (`call_transcripts`), כי הסנכרון מהגיליון דורס את `calls.raw`. ייבוא ההיסטוריה הוא כלי שורת-פקודה עם ריצה יבשה, שמשתמש באותם מנרמלים.

**Tech Stack:** Flask (`effie_v2.py`, `app.py`), Supabase REST דרך `supabase_db.py`, Make (סנריו 2934615), Apps Script (`AppsScript_supabase_addition.gs`).

**Spec:** `docs/superpowers/specs/2026-10-19-crm-dashboard-design.md`. תוכניות נפרדות יבואו בהמשך: (2) מסכי CRM, (3) דשבורד.

## Global Constraints
- אסור לשנות טבלאות קיימות. מותר רק להוסיף טבלאות. המיגרציה נשמרת ב-`remax-family/supabase/migrations/`, ואייל מריץ אותה ב-SQL Editor.
- כל כתיבה דרך השרת (service_role). בטבלאות החדשות: RLS פעיל בלי policies.
- מולטי-טננט: כל שורה עם `office_id` (`supabase_db.SB_OFFICE_ID`).
- מחירים ותאריכים מהמקור נשמרים כטקסט גולמי ב-`raw`.
- מפתחות קליטה ב-env בלבד, נבדקים ב-`hmac.compare_digest`, וריק = כבוי (403).
- ניסיון חוזר לא מכפיל: upsert לפי `(office_id, …, source_key)`.
- הניתוק ב-31/10 בכל מקרה (החלטת אייל).
- בדיקות בסגנון הפרויקט: סקריפט python ב-`tests/crm/` שמחלץ פונקציות מהקוד האמיתי עם `ast` ובודק עם `ck(cond, msg)`. בנוסף `ast.parse` על כל קובץ ששונה.
- אייל עושה push, deploy ו-SQL בעצמו. בלי סודות בריפו או בצ'אט.

## Review Focus
1. **Make שולח את אותה שיחה פעמיים** (retry / הרצה חוזרת). מצופה: שורה אחת בצל ושורה אחת ב-`call_transcripts`. נבדק ב-Task 3.
2. **שיחה שלא נענתה או קצרה מאוד** (אין תמלול, סיכום ריק, "No Answer"). מצופה: השיחה נקלטת עם סטטוס, ובלי שורת תמלול ריקה. נבדק ב-Task 2.
3. **אחרי הניתוק הסנכרון הישן עדיין רץ** ודורס/מכפיל את `calls`. מצופה: ה-runbook מנטרל אותו לפני החלפת המשתנה, ובדיקת ה-runbook מאמתת שאין שתי שורות לאותה שיחה. Task 7.
4. **ייבוא היסטוריה של רשומה שכבר קיימת באפי** (בעיקר חשבוניות, שהממיר המקורי איחד בהן 6,426 שורות ל-5,184). מצופה: הריצה היבשה מסווגת אותה כ"קיימת" ולא כ"חדשה". נבדק ב-Task 6.
5. **תמלול ארוך מאוד** (שיחה של שעה, עשרות אלפי תווים). מצופה: נשמר במלואו בלי חיתוך ובלי 500. נבדק ב-Task 2.

---

### Task 0: סקירת 53 האוטומציות עם אייל (בלי קוד)

**Files:**
- Create: `docs/handoff/2026-10-fireberry-automations.md`

- [ ] **Step 1:** לבקש מאייל ייצוא או צילומים של רשימת "תהליכי עבודה" בפיירברי (53), וגם את גוף ה"אז" של כל אוטומציה **פעילה**.
- [ ] **Step 2:** טבלה במסמך: שם · טריגר · מה עושה · **החלטה** (לבנות באפי / כבר קיים באפי — איפה / לוותר) · הערה. ההחלטה בעמודה הזו היא של אייל.
- [ ] **Step 3:** כל שורה שסומנה "לבנות" הופכת למשימה בתוכנית המשך נפרדת, ונבנית **לפני** הניתוק.
- [ ] **Step 4:** Commit: `git add docs/handoff/2026-10-fireberry-automations.md && git commit -m "CRM: סקירת אוטומציות פיירברי"`

### Task 1: מיגרציה — טבלאות צל ותמלול

**Files:**
- Create: `/Users/eyal/Documents/remax-family/supabase/migrations/20261019_crm_phase1.sql`

**Interfaces:**
- Produces:
  - `ingest_shadow(id uuid pk default gen_random_uuid(), office_id uuid not null, stream text not null check (stream in ('calls','invoices')), source_key text not null, received_at timestamptz, raw jsonb not null, created_at timestamptz default now(), unique(office_id, stream, source_key))`
  - `call_transcripts(id uuid pk default gen_random_uuid(), office_id uuid not null, source_key text not null, event_id text, transcript text, recording_url text, created_at timestamptz default now(), updated_at timestamptz default now(), unique(office_id, source_key))`
  - אינדקס `(office_id, stream, received_at desc)` על הצל.

- [ ] **Step 1:** לכתוב את הקובץ: `create table if not exists`, `alter table … enable row level security` לשתיהן, בלי policies, ובלי שום `alter` על טבלה קיימת.
- [ ] **Step 2:** בדיקה: `grep -iE "alter table (calls|signatures|invoices)|drop " supabase/migrations/20261019_crm_phase1.sql` → בלי פלט.
- [ ] **Step 3:** Commit בריפו remax-family. אייל מריץ ב-SQL Editor.

### Task 2: מנרמל שיחה טהור

**Files:**
- Modify: `effie_v2.py` (פונקציה ברמת המודול, ליד `sig_ingest_norm`)
- Test: `tests/crm/test_call_norm.py`

**Interfaces:**
- Produces: `call_ingest_norm(body: dict) -> tuple[str, str, dict, str, str] | None`, שמחזיר `(source_key, received_date_iso, raw, transcript, recording_url)`.
  - `source_key = "mk:" + call_uuid`. `call_uuid` נלקח מ-`call_uuid` / `uuid` / `callid`. אם אין uuid, מחזירים `None`.
  - `raw` במפתחות של טאב השיחות כדי שהקוראים הקיימים יעבדו: `event_id`(=source_key), `status`, `agent`, `agent_phone`, `caller_phone`, `duration_sec`, `transcript_summary`, `received_at` (מחרוזת המקור כמו שהיא), `recording_url`.
  - `received_date_iso` = התאריך בלבד בשעון ישראל (`YYYY-MM-DD`), לפי `inv_parse_dt`. אם התאריך לא פריס — היום.
  - `transcript` = טקסט מלא בלי חיתוך. ריק אם הגיע ריק או "No Answer".

- [ ] **Step 1: Write the failing test**
```python
ck(norm({"call_uuid":"u1","callstatus":"ANSWER","agent":"אלי שמול","agent_phone":"0505235330",
         "caller_phone":"546631493","created":"18/10/2026 17:08","summary":"סיכום","transcript":"שלום…"})[0]=="mk:u1", "key")
r = norm({"call_uuid":"u1","callstatus":"ANSWER","created":"18/10/2026 17:08","summary":"s","transcript":"t"})
ck(r[1]=="2026-10-18" and r[2]["status"]=="ANSWER" and r[2]["transcript_summary"]=="s" and r[3]=="t", r)
ck(norm({"callstatus":"ANSWER"}) is None, "no uuid")
ck(norm({"call_uuid":"u2","callstatus":"NOANSWER","transcript":"No Answer"})[3]=="", "no answer → empty transcript")
big = "א"*60000
ck(len(norm({"call_uuid":"u3","transcript":big})[3])==60000, "no truncation")
ck(norm({"call_uuid":"u4","callstatus":"call2call"})[2]["status"]=="call2call", "status kept raw")
```
- [ ] **Step 2:** `python3 tests/crm/test_call_norm.py` → נכשל (`call_ingest_norm` לא מוגדר).
- [ ] **Step 3:** לממש. שמות השדות בגוף: לקבל גם עברית וגם אנגלית, כמו `f(*names)` ב-invoices ingest. מיפוי סטטוס: `callstatus` / `status`.
- [ ] **Step 4:** הבדיקה עוברת + `python3 -c "import ast;ast.parse(open('effie_v2.py').read())"`.
- [ ] **Step 5:** Commit.

### Task 3: גישה ל-DB + ראוט `/v2/api/calls/ingest`

**Files:**
- Modify: `supabase_db.py`, `effie_v2.py`
- Test: `tests/crm/test_calls_ingest.py` (requests מזויף, בסגנון בדיקות `merge_office_props`)

**Interfaces:**
- Consumes: `call_ingest_norm` (Task 2).
- Produces (ב-`supabase_db`):
  - `shadow_upsert(stream: str, source_key: str, received_iso: str, raw: dict) -> bool` — POST ל-`ingest_shadow`, `on_conflict=office_id,stream,source_key`, merge-duplicates.
  - `transcript_upsert(source_key: str, event_id: str, transcript: str, recording_url: str) -> bool` — לא כותב כשהתמלול וגם הקישור ריקים.
  - `call_upsert_direct(source_key: str, received_iso: str, raw: dict) -> bool` — upsert ל-`calls` עם אותן עמודות ש-`_sbCallRecord_` כותב (event_id, status, agent, agent_phone, caller_phone, duration_sec, transcript_summary, received_at, raw, updated_at).
  - `fetch_shadow(stream: str, since_iso: str) -> list[dict]`.
- Produces (ב-effie_v2): `POST /v2/api/calls/ingest`.
  - מפתח `X-Ingest-Key` מול env `CALLS_INGEST_KEY`.
  - מצב לפי env `CALLS_DIRECT`: `shadow` (ברירת מחדל) → `shadow_upsert("calls", …)`; `live` → `call_upsert_direct` + `_cache_clear("raw:שיחות:01/01/2020:31/12/2099")`.
  - בשני המצבים: `transcript_upsert`.
  - התשובה: `{"ok":True,"mode":…,"source_key":…}`. גוף ריק או בלי uuid → `{"ok":False,"reason":"empty"}` (200). מפתח שגוי → 403.
  - שורה ב-`activity_log` רק במצב live (בצל — שקט).

- [ ] **Step 1: Write the failing test** — לרשום את הקריאות ל-requests המזויף ולבדוק:
```python
ck(post(body, key="bad").status==403, "key")
ck(calls_to("ingest_shadow")==1 and calls_to("calls")==0, "shadow by default")
post(body); ck(rows("ingest_shadow")==1, "retry doesn't duplicate (same on_conflict key)")
ck(calls_to("call_transcripts")==1, "transcript saved")
os.environ["CALLS_DIRECT"]="live"; post(body)
ck(calls_to("calls")==1 and calls_to("ingest_shadow")==1, "live writes calls")
ck(post({"callstatus":"x"}).json["reason"]=="empty", "no uuid")
ck(calls_to("call_transcripts", body_of={"call_uuid":"n","transcript":""}) == 0, "no empty transcript row")
```
- [ ] **Step 2:** הבדיקה נכשלת.
- [ ] **Step 3:** לממש. המשתנים נקראים בכל בקשה (לא בעליית המודול), כדי שהחלפת המשתנה ב-Render ונגיעה ב-deploy יספיקו. בדיקת קשירת ראוטים: `/v2/api/calls/ingest` קשור לפונקציה הנכונה (הלקח מ-16f7d7f).
- [ ] **Step 4:** הבדיקות עוברות + ast על שני הקבצים.
- [ ] **Step 5:** Commit.

### Task 4: חשבוניות ישירות למצב צל

**Files:**
- Modify: `effie_v2.py` (`v2_api_invoices_ingest`)
- Test: `tests/crm/test_invoices_direct.py`

**Interfaces:**
- Consumes: `shadow_upsert` (Task 3).
- Produces: התנהגות חדשה ב-`/v2/api/invoices/ingest`. כשהבקשה מגיעה עם `?via=direct` (מהתוכנה החיצונית) ו-env `INVOICES_DIRECT` הוא `shadow` (ברירת מחדל), השורה המנורמלת נכתבת ל-`shadow_upsert("invoices", row_hash, created_at, row)`, **בלי** הכנסה ל-`invoices` ובלי וואטסאפ ללקוח. `INVOICES_DIRECT=live` → בדיוק המסלול הקיים. בלי `via` → המסלול הקיים (פיירברי), בלי שום שינוי.

- [ ] **Step 1: Write the failing test:** `via=direct` במצב shadow → הצל קיבל שורה, `insert_invoice_row` לא נקרא, `_inv_wa_send_async` לא נקרא. בלי `via` → כמו היום. `live` → כמו היום.
- [ ] **Step 2:** נכשל.
- [ ] **Step 3:** לממש. הנרמול הקיים לא משתנה. אם התוכנה החיצונית שולחת שמות שדות אחרים, מוסיפים אותם ל-`f(...)` כשיגיעו (אייל מעביר דוגמת גוף).
- [ ] **Step 4:** עובר + ast.
- [ ] **Step 5:** Commit.

### Task 5: דוח מקבילות יומי

**Files:**
- Modify: `effie_v2.py` (פונקציות טהורות ברמת המודול + ראוט)
- Test: `tests/crm/test_parallel.py`

**Interfaces:**
- Consumes: `fetch_shadow` (Task 3), `G["web_fetch_raw"]("שיחות", …)`, `G["get_signings"]()`, `fetch_invoices_rows`.
- Produces:
  - `parallel_match_calls(legacy: list[dict], direct: list[dict]) -> dict` — התאמה לפי `inv_phone9(caller_phone)` + `inv_phone9(agent_phone)` + זמן ±120ש'. כל רשומה מותאמת פעם אחת לכל היותר. מחזיר `{"matched":n, "only_legacy":[…], "only_direct":[…]}`, והרשימות מכילות זמן + סוכן + 4 ספרות אחרונות של הטלפון בלבד.
  - `parallel_match_invoices(legacy, direct) -> dict` — לפי `doc_num` אם יש בשני הצדדים, אחרת לפי `phone9` + סכום + יום.
  - `sig_nonapp_by_agent(sigs: list[dict], since_iso: str) -> list[tuple[str,int]]` — חתימות מאז `since` שאינן מאפי (source_key לא מתחיל ב-`app:` וגם אין שורת `app:` תואמת בדדופ התצוגה), לפי סוכן. אלה הסוכנים שעוד מחתימים בחתימה טובה.
  - `GET /v2/api/crm/parallel?days=3` — `_dev_guard`. לכל יום ולכל זרם: הספירות וההתאמות. ובנוסף `sig_nonapp`.
- [ ] **Step 1: Write the failing test:**
```python
L=[dict(caller_phone="0546631493",agent_phone="0505235330",received_at="2026-10-18T17:08:10+03:00")]
D=[dict(caller_phone="546631493",agent_phone="505235330",received_at="2026-10-18T17:09:30+03:00")]
ck(match_calls(L,D)["matched"]==1, "±120s, phone formats")
D2=[dict(caller_phone="546631493",agent_phone="505235330",received_at="2026-10-18T17:12:00+03:00")]
ck(len(match_calls(L,D2)["only_legacy"])==1, "outside window")
ck(match_calls(L+L, D)["matched"]==1, "one-to-one")
ck(match_inv([dict(doc_num="25134",phone9="504422040",amount="1",created_at="2026-10-16")],
             [dict(doc_num="25134",phone9="",amount="",created_at="")])["matched"]==1, "doc_num wins")
ck(sig_nonapp([dict(source_key="fb:1:BUYER",agent="דידי לוי",received_at="2026-10-20T10:00:00+03:00"),
               dict(source_key="app:x:BUYER",agent="יובל כהן",received_at="2026-10-20T10:00:00+03:00")],
              "2026-10-19")==[("דידי לוי",1)], "non-app by agent")
```
- [ ] **Step 2:** נכשל. **Step 3:** לממש. **Step 4:** עובר + ast. **Step 5:** Commit.

### Task 6: כלי ייבוא היסטוריה מ-CSV של פיירברי

**Files:**
- Create: `tools/import_fireberry.py`
- Test: `tests/crm/test_import_fireberry.py`

**Interfaces:**
- Consumes: `call_ingest_norm`, `sig_ingest_norm`, ונרמול החשבוניות (`inv_*`). מייבאים אותם מ-effie_v2 עם `ast` כמו בבדיקות, לא מעתיקים.
- Produces: `python3 tools/import_fireberry.py <calls|signatures|invoices> <file.csv> [--save]`. ה-URL והמפתח של Supabase נלקחים מ-env, או מ-`getpass` אם חסרים.
  - פונקציה טהורה `fb_plan(module: str, rows: list[dict], existing: dict) -> list[dict]`. כל פריט: `{"action": "new"|"exists"|"enrich"|"reject", "source_key":…, "reason":…}`.
  - **שיחות:** מפתח קיים = `event_id` (מזהה הרשומה בפיירברי, עמודת "מזהה" בייצוא). הייבוא כותב ל-`calls` ב-`source_key = "fb:" + event_id` רק כשאין שורה עם אותו `event_id`.
  - **חתימות:** `fb:<event_id>:<deal_type>`, כמו ב-ingest.
  - **חשבוניות:** `row_hash` כמו ב-ingest. כשה-hash לא קיים אבל `doc_num` לא ריק וקיים — `exists`. בלי `doc_num` — `phone9` + סכום + יום → `exists`.
  - פריטי `enrich` = רשומה קיימת שחסרים בה שדות (טלפון / סיכום). רק מוסיפים שדות, לא דורסים.
  - דוח בריצה יבשה: מונים לכל פעולה + 10 דוגמאות לכל פעולה (בלי טלפון מלא) + שמות העמודות שזוהו ושלא זוהו.
  - `--save` כותב במנות של 100 דרך `_upsert_bulk`.
- [ ] **Step 1: Write the failing test** — טבלאות קטנות בזיכרון:
```python
ck(plan("invoices",[row_same_hash],{"hashes":{H},"docnums":set()})[0]["action"]=="exists", "hash")
ck(plan("invoices",[row_diff_date_same_doc],{"hashes":set(),"docnums":{"25134"}})[0]["action"]=="exists", "doc_num dedupe")
ck(plan("calls",[dict(**{"מזהה":"e1"})],{"event_ids":{"e1"}})[0]["action"]=="exists", "call by event_id")
ck(plan("signatures",[dict(**{"מזהה":"e2","סוג הסכם":"BUYER_VIEW"})],{"keys":set()})[0]["source_key"]=="fb:e2:BUYER_VIEW", "sig key")
ck(plan("calls",[{}],{"event_ids":set()})[0]["action"]=="reject", "no id")
```
- [ ] **Step 2:** נכשל. **Step 3:** לממש. **Step 4:** עובר.
- [ ] **Step 5:** ריצה יבשה אמיתית אצל אייל על שלושת הקבצים. **שער:** אם בחשבוניות `new` עולה בהרבה על (השורות בקובץ פחות מה שכבר בטבלה), עוצרים ובודקים את ה-dedupe לפני `--save`.
- [ ] **Step 6:** Commit (הכלי והבדיקה בלבד. קובצי ה-CSV לעולם לא נכנסים לגיט).

### Task 7: Make — שליחה ישירה לאפי (בלי קוד בריפו)

**Files:**
- Backup: `~/Downloads/make-backups/2934615-before-crm-2026-10-XX.json`

- [ ] **Step 1:** לגבות את ה-blueprint של 2934615 דרך ה-MCP של Make לקובץ הגיבוי.
- [ ] **Step 2:** להוסיף מודול HTTP POST אחרי הסיכום (34), במקביל לכתיבה לפיירברי ולא במקומה. Error handler: Resume. URL: `https://remax-bot.onrender.com/v2/api/calls/ingest`, כותרת `X-Ingest-Key` (אייל מזין את הערך ב-Make). גוף: `call_uuid`, `callstatus`, `agent`, `agent_phone`, `caller_phone`, `duration_sec`, `created`, `summary` (הסיכום כפי שנכנס לפיירברי, כולל הביקורת), `transcript` (פלט מודול 33), `recording_url`.
- [ ] **Step 3:** לאמת שהשינוי היחיד ב-blueprint הוא המודול החדש: diff מול הגיבוי.
- [ ] **Step 4:** אחרי שיחה אמיתית — שורה ב-`ingest_shadow` ושורה ב-`call_transcripts` (SQL של אייל, או `GET /v2/api/crm/parallel?days=1`).
- [ ] **Step 5:** לרשום ביומן ההחלטות.

### Task 8: Runbook הניתוק + הודעה לסוכנים

**Files:**
- Create: `docs/handoff/2026-10-31-fireberry-cutover.md`

- [ ] **Step 1: הודעה לסוכנים** (וואטסאפ, אייל שולח). נוסח: מ-<תאריך> מחתימים רק מאפי (מסך "חתימות" → בעל נכס / מתעניין), וחתימה טובה נסגרת. מהיום ועד הניתוק, `sig_nonapp_by_agent` מראה מי עדיין מחתים בחוץ.
- [ ] **Step 2: Runbook** — רשימת צעדים לפי הסדר, ולכל צעד "איך יודעים שהצליח":
  1. 3 ימי עבודה של `/v2/api/crm/parallel` בלי `only_legacy` (ופערי `only_direct` מוסברים).
  2. ייצוא גיבוי מלא מפיירברי של **כל** המודולים לתיקייה של אייל (לא לגיט).
  3. ייבוא היסטוריה סופי (`--save`) על ייצוא טרי.
  4. ב-Apps Script: לנטרל ב-`//` את בלוק השיחות ב-`sbSyncRecent` ואת `sbBackfillCalls()` ב-`sbReconcileAll`.
  5. Render: `CALLS_DIRECT=live`, `INVOICES_DIRECT=live`, ולוודא `CALLS_SOURCE=supabase` + `SIGNATURES_SOURCE=supabase`.
  6. שיחת בדיקה → מופיעה במסך השיחות פעם אחת, עם סיכום.
  7. Make: להסיר את מודולי הכתיבה לפיירברי (2/82/114), אחרי גיבוי blueprint.
  8. פיירברי: לכבות את האוטומציות. לבטל את `SIGN_INGEST_KEY` ואת `INVOICES_INGEST_KEY` הישן (נחשפו בצילום). לא לחדש את המנוי.
  9. **Rollback** לכל צעד: `CALLS_DIRECT=shadow` + החזרת שורות ה-`//` ב-Apps Script + הדלקת האוטומציות (עד שהמנוי פג).
- [ ] **Step 3:** Commit. ביומן ההחלטות ב-remax-family: שורה על סיום שלב 1.

---

**סדר ביצוע (לוח זמנים מוצע):** Tasks 1–3 עד 21/10 (כדי ש-Make יתחיל להזרים) → Task 7 → Tasks 4–5 → Task 6 (ריצה יבשה ברגע שה-CSV אצל אייל) → Task 0 במקביל לאורך כל הדרך → Task 8 עד 28/10, וניתוק ב-31/10.
