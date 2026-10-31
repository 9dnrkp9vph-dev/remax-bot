# פרסום נכסים בעמוד ובאינסטגרם מאפי (Meta) — תוכנית בנייה

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** אפי מפרסמת נכסי משרד בעמוד הפייסבוק ובאינסטגרם של המשרד דרך Meta Graph API — ידנית (כפתור למפתח) ואוטומטית (עד 5 ביום), עם מצב תצוגה מקדימה שלא כותב כלום ל-Meta.

**Architecture:** מודול חדש `social_publish.py` (פונקציות טהורות + לקוח Graph + ראוטים ולולאה ב-`register(app, G)`, בדפוס של `goals.py`). שמירה בטבלה חדשה `social_posts`. התמונות מוגשות מאפי כ-JPEG זמני כדי ש-Meta תמשוך אותן. ממשק: כרטיס ב-`/v2/dev`, כפתור ושורת מצב ב-`propCard`, וריבוע בלוח הבקרה.

**Tech Stack:** Python 3 / Flask, requests, Pillow, Supabase REST, Meta Graph API, JS בתוך מחרוזות HTML ב-`effie_v2.py`.

**Spec:** `docs/superpowers/specs/2026-10-31-social-publish-meta-design.md` (remax-bot `785d365`).

## Global Constraints

- עבודה בענף `social` בתיקייה נפרדת (`git worktree add ../remax-bot-social -b social`). **לא דוחפים ולא ממזגים ל-main** בלי אישור אייל ("לא רוצה לדחוף כל פעם לרנדר עד שזה לא מוכן").
- commit מקומי בלבד. SQL ומשתני סביבה — אצל אייל.
- `META_TOKEN` רק ב-env. אסור שיופיע בלוג, בהודעת שגיאה, בתשובת API או בקונפיג. כל הודעת שגיאה עוברת `_scrub(msg, token)`.
- `SOCIAL_MODE`: רק הערך `publish` (אחרי `strip().lower()`) מתיר כתיבה ל-Meta. כל ערך אחר, ריק או חסר = `preview`. `off` = כבוי.
- `SOCIAL_AUTO`: `1` = פעיל; ברירת מחדל `0`. `SOCIAL_CHANNELS`: ברירת מחדל `fb,ig`.
- קבועים: `DAILY_CAP=5`, `ROUND_CAP=3`, `FLOOD=40`, `GAP_MIN=20`, `REPEAT_DAYS=14`, `WAIT_DAYS=3`, `RETRY_DAYS=3`, `ONE_IMG_HOURS=72`, `MAX_IMAGES=10`, `DESC_MAX=600`, `NIGHT=(22, 8)`, `KNOWN_TTL_DAYS=60`, `IMG_TTL_H=24`, `IMG_MAX_PX=1440`, `LOOP_SEC=600`.
- שם המשרד רק מ-`v2_office.name` בקונפיג. מסחרי (`סוג עסקה` = מסחרי) לא מתפרסם.
- בטקסט: אין מספר בית, טלפון, שם סוכן או קישור. ביטוי הטלפון (כמו באתר): `(?:\+?972[-\s]?|\b0)(?:5\d|[2-9])(?:[-\s]?\d){7}\b`.
- בממשק אפי: פלטה סגורה (זהב לכפתור "פרסם ברשתות"), אין אימוג'ים ב-UI, שטח מגע 44px. אימוג'ים מותרים רק בטקסט הפוסט עצמו.
- בדיקות: סקריפטים רגילים `python3 tests/social/test_X.py`, חילוץ פונקציות דרך import של המודול (המודול טהור) או `ast` לקוד ב-app.py/effie_v2.py; JS דרך `node --check` ו-node על הקוד האמיתי. `timeout` לא קיים על המק.
- בלי שום קריאה אמיתית ל-Meta בבדיקות — `http` מוזרק ומזויף.

## Review Focus

1. **תיאור עם טלפון בפורמט חריג** (`054-1234567`, `+972 54 123 4567`, `04 8123456`) → נמחק מהטקסט. בדיקה: Task 2.
2. **תמונה מיד2 שלא יורדת / לא תמונה / פגומה** → מדולגת בלי חריגה; כולן נכשלות → "אין תמונות" ולא נוצר פוסט. בדיקה: Task 5 + Task 7.
3. **timeout בבקשת הכתיבה הסופית ל-Meta** (feed / media_publish) → הערוץ נרשם `unknown`, אין ניסיון חוזר אוטומטי, ולחיצה חוזרת באותו יום חסומה. בדיקה: Task 6 + Task 7.
4. **הזרמה חוזרת של הסורק או שחזור גיבוי** (כל מספרי המודעה כבר ב-`known`, גם כש-`_y2_first_seen` חדש) → אפס פרסומים. בדיקה: Task 4.
5. **`SOCIAL_MODE` עם ערך שגוי** (`"true"`, `"1"`, `"yes"`, `"publsh"`, ריק) → מתנהג כ-preview ושום בקשת כתיבה לא נשלחת. (`" Publish "` כן נחשב `publish` — strip+lower.) בדיקה: Task 6 + Task 7.

---

### Task 1: טבלת `social_posts` ועזרי Supabase

**Files:**
- Create: `/Users/eyal/Documents/remax-family/supabase/migrations/20261031_social_posts.sql` (ריפו remax-family, commit שם)
- Modify: `supabase_db.py` (אחרי פונקציות `bpage_*`, בערך שורה 1513)
- Test: `tests/social/test_db.py`

**Interfaces:**
- Produces:
  - `social_insert(rec: dict) -> dict | None` — מוסיף `office_id=SB_OFFICE_ID`, מחזיר את השורה (Prefer `return=representation`).
  - `social_update(row_id: str, fields: dict) -> bool`
  - `social_recent(days: int) -> list[dict]` — כל השורות של המשרד מ-`days` הימים האחרונים, החדש קודם (`order=created_at.desc`).

- [ ] **Step 1: SQL** — `create table if not exists social_posts` עם העמודות מהספק (סעיף 7): `id uuid pk default gen_random_uuid()`, `office_id uuid not null`, `property_key text not null`, `addr_key text`, `trigger text`, `mode text`, `by_phone text`, `fb_post_id text`, `fb_permalink text`, `fb_status text`, `ig_media_id text`, `ig_permalink text`, `ig_status text`, `error text`, `body text`, `images jsonb default '[]'`, `created_at timestamptz default now()`, `updated_at timestamptz default now()`; אינדקס `(office_id, created_at desc)` ו-`(office_id, property_key)`; `alter table … enable row level security;` בלי policies.
- [ ] **Step 2: Write failing test** `test_db.py` עם `requests` מזויף:
  - `social_insert({"property_key":"abc"})` שולח POST ל-`/rest/v1/social_posts` עם `office_id` ו-`Prefer` שמכיל `return=representation`, ומחזיר את השורה הראשונה.
  - `social_update("u1", {"fb_status":"ok"})` שולח PATCH עם `id=eq.u1` ו-`office_id=eq.<SB_OFFICE_ID>`, ומוסיף `updated_at`.
  - `social_recent(14)` שולח `created_at=gte.<ISO>` ו-`order=created_at.desc`.
  - כשל HTTP ב-insert → `None`, לא חריגה.
- [ ] **Step 3: Run** `python3 tests/social/test_db.py` — Expected: FAIL (`AttributeError: social_insert`).
- [ ] **Step 4: Implement** את שלוש הפונקציות בסגנון `bpage_create` (`_headers()`, `_TIMEOUT`).
- [ ] **Step 5: Run** — Expected: PASS.
- [ ] **Step 6: Commit** — `git add supabase_db.py tests/social/test_db.py && git commit -m "social: טבלת social_posts ועזרי Supabase"`; ב-remax-family: commit לקובץ ה-SQL.

### Task 2: בניית הפוסט — `soc_build_post`

**Files:**
- Create: `social_publish.py`
- Test: `tests/social/test_build.py`

**Interfaces:**
- Consumes: מוזרקים מבחוץ (לא import): `clean_desc` (= `y2_clean_desc`), `feats` (= `_row_feats`, מחזיר רשימת שמות תכונות), `office_name: str`.
- Produces:
  - `soc_scrub_phones(text: str) -> str`
  - `soc_addr_key(row: dict) -> str` — `"<עיר>|<רחוב>|<מספר בית>|<חדרים>"` מנורמל (רווחים, "קריית"→"קרית", חדרים כמספר `"4"`/`"4.5"`); קומה לא בתוך המפתח.
  - `soc_floor(row: dict) -> str` — הקומה מהעמודה או מהתיאור ("קומה 3 מתוך 8" → `"3"`), אחרת `""`.
  - `soc_build_post(row: dict, office_name: str, clean_desc, feats) -> dict` → `{"body": str, "ig_caption": str, "images": [str]}`; `images` = עד `MAX_IMAGES` כתובות מקור מ-`תמונות` (רשימה או JSON או מופרד בפסיקים), ובלעדיה `[תמונה]`, ללא כפילויות.

- [ ] **Step 1: Write failing tests:**
  - שורת דוגמה (מכירה, 4 חדרים, נאות אפק, קרית ביאליק, רחוב "אהוד מנור", מספר בית "13", מחיר "1890000", 110 מ"ר, קומה "3", תיאור עם "התקשרו 054-1234567") → `body` מכיל `"למכירה · 4 חדרים בנאות אפק, קרית ביאליק"`, `"📍 אהוד מנור"`, `"1,890,000 ₪"`, `"110 מ\"ר"`, `"קומה 3"`, ומסתיים בשם המשרד ו-`"לפרטים — הודעה לעמוד"`; **לא** מכיל `"13"` כמספר בית צמוד לרחוב, ולא `"054"`.
  - `feats` מחזיר `["מעלית","ממ\"ד"]` → שורה `"✔ מעלית · ממ\"ד"`; בלי תכונות → אין שורת ✔.
  - `soc_scrub_phones` מוחק `"054-1234567"`, `"+972 54 123 4567"`, `"04 8123456"`, ולא נוגע ב-`"1,890,000"` או `"110"`.
  - תיאור ארוך → עד `DESC_MAX` תווים, נחתך בגבול מילה עם `"…"`.
  - השכרה → `"להשכרה"` ו-`"לחודש"` ליד המחיר; `ig_caption` = `body` + שורת `"#נדלן #דירותלהשכרה #קריתביאליק #רימקספמילי"`; במכירה `#דירותלמכירה`.
  - `images`: 12 תמונות → 10; כפילויות מוסרות; רק `תמונה` → רשימה של אחת.
  - `soc_addr_key` זהה ל-`"קריית ביאליק"` ול-`"קרית ביאליק"`, ושונה כשמספר החדרים שונה.
- [ ] **Step 2: Run** `python3 tests/social/test_build.py` — Expected: FAIL (`ModuleNotFoundError: social_publish`).
- [ ] **Step 3: Implement** — המודול טהור (בלי Flask ברמת המודול), כמו `goals.py`. הקבועים מ-Global Constraints בראש הקובץ.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "social: בניית טקסט הפוסט והתמונות"`.

### Task 3: מתי מותר לפרסם — `soc_can_publish`

**Files:**
- Modify: `social_publish.py`
- Test: `tests/social/test_can.py`

**Interfaces:**
- Consumes: `soc_addr_key`, `soc_floor`, `parse_ts` (להעתיק את הגרסה מ-`goals.parse_ts` או לייבא `goals.parse_ts`).
- Produces: `soc_can_publish(row: dict, channel: str, history: list[dict], now: float, hidden: set[str]) -> tuple[bool, str]`. `channel` ∈ `"fb"`,`"ig"`. `history` = שורות `social_posts`. הסיבות (מחרוזות קבועות בעברית): `"ירד מפרסום"`, `"מוסתר מהאתר"`, `"מסחרי"`, `"אין תמונות"`, `"מחכה לתמונות"`, `"פורסם DD/MM · אפשר שוב מ-DD/MM"`, `"כבר נשלח היום"`.

- [ ] **Step 1: Write failing tests:**
  - נכס עם 2 תמונות, לא מוסתר, מכירה, היסטוריה ריקה → `(True, "")`.
  - `ירד מפרסום` מלא / `delisted_at` ב-raw → `(False, "ירד מפרסום")`.
  - מספר מודעה ב-`hidden` → `"מוסתר מהאתר"`. מסחרי → `"מסחרי"`.
  - תמונה אחת ו-`_y2_first_seen` לפני 10 שעות → `"מחכה לתמונות"`; לפני 73 שעות → `True`. אפס תמונות → `"אין תמונות"`.
  - היסטוריה: `fb_status="ok"`, `mode="publish"` לפני 5 ימים לאותו `property_key` → ל-`fb`: `False` עם `"פורסם"` ו-`"אפשר שוב מ-"`; ל-`ig` (ig_status `"failed"`) → `True`.
  - **אותה דירה, מספר מודעה אחר:** היסטוריה עם אותו `addr_key` לפני 3 ימים → `False`; אותו `addr_key` אבל קומה שונה בשני הצדדים → `True`.
  - היסטוריה של `mode="preview"` לא חוסמת. פרסום לפני 15 ימים לא חוסם.
  - `ig_status="unknown"` מהיום לאותו נכס → `(False, "כבר נשלח היום")` ל-`ig` (Review Focus 3).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** בעמודה `social_posts.addr_key` נשמר `soc_addr_key(row) + "#" + soc_floor(row)` (קומה ריקה = `"#"`). `soc_can_publish` מפרקת לפי `#`: החלק הראשון חייב להיות זהה, והקומה פוסלת התאמה רק כשהיא קיימת בשני הצדדים ושונה.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "social: כללי מתי מותר לפרסם"`.

### Task 4: תכנון הסבב האוטומטי — `soc_plan_round`

**Files:**
- Modify: `social_publish.py`
- Test: `tests/social/test_plan.py`

**Interfaces:**
- Consumes: `soc_can_publish`.
- Produces: `soc_plan_round(rows: list[dict], state: dict, history: list[dict], now: float, hidden: set, blocked: bool) -> dict` →
  `{"publish": [property_key], "state": dict, "flood": bool, "reason": str}`.
  `state` = `v2_social` בקונפיג: `{"known": {key: last_seen_epoch}, "waiting": {key: first_epoch}, "enabled_at": epoch}`. `blocked` = שבת/חג/השתקה (מחושב בחוץ). הלילה (`NIGHT`) נבדק בפנים לפי שעון ישראל.
  `soc_seed_known(rows, now) -> dict` — מצב התחלתי: כל המפתחות הקיימים ב-`known`.

- [ ] **Step 1: Write failing tests:**
  - `soc_seed_known` עם 480 שורות → `known` עם 480 מפתחות; ואז `soc_plan_round` על אותן שורות → `publish == []`, גם אם לכולן `_y2_first_seen` של עכשיו (Review Focus 4).
  - שורה אחת חדשה (מפתח לא ב-`known`, 2 תמונות) בשעה 12:00 → `publish == [key]`; ב-`state` המפתח נכנס ל-`known`.
  - 41 מפתחות חדשים → `publish == []`, `flood=True`, וכולם **נכנסים** ל-`known` (לא יפורסמו בסבב הבא).
  - היסטוריה עם 5 פרסומים `trigger="auto"` היום → `publish == []`, המועמד נכנס ל-`waiting`; פרסומים `trigger="manual"` לא נספרים בתקרה.
  - 4 מועמדים → לכל היותר 3 (`ROUND_CAP`); פרסום אוטומטי אחרון לפני 10 דקות → `publish == []` (`GAP_MIN`).
  - מפתח ב-`waiting` מלפני 4 ימים → נמחק מ-`waiting` ולא מתפרסם.
  - 23:30 או `blocked=True` → `publish == []` אבל `known` מתעדכן.
  - מפתח שלא נראה 61 ימים → נמחק מ-`known`.
  - מועמד שנכשל ב-`soc_can_publish` ל-fb ול-ig ("מחכה לתמונות") → נשאר ב-`waiting`, לא ב-`publish`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** סדר המועמדים: החדשים קודם (לפי `waiting[key]` יורד).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "social: תכנון הסבב האוטומטי"`.

### Task 5: תמונות — המרה ל-JPEG ומאגר זמני

**Files:**
- Modify: `social_publish.py`
- Test: `tests/social/test_img.py`

**Interfaces:**
- Produces:
  - `soc_jpeg(raw: bytes, square: bool) -> bytes | None` — Pillow; `None` אם לא תמונה. בלי `square`: הקטנה לצד ארוך `IMG_MAX_PX`. עם `square`: ריבוע `IMG_MAX_PX`×`IMG_MAX_PX`, התמונה כולה במרכז, הרקע = אותה תמונה מוגדלת ל-cover עם `GaussianBlur`.
  - `class ImgStore` (בזיכרון, נעילה): `put(src_url: str, now: float) -> str` (טוקן `secrets.token_urlsafe(16)`), `get(token: str, now: float) -> str | None` (פג אחרי `IMG_TTL_H`), `purge(now)`.
  - `soc_fetch_jpeg(http, src_url: str, square: bool) -> bytes | None` — הורדה עם timeout 20 ש', `None` בכל כשל.

- [ ] **Step 1: Write failing tests:**
  - תמונה 2000×1000 (נוצרת ב-Pillow) → `soc_jpeg(..., False)` מחזיר JPEG שמתחיל ב-`b"\xff\xd8"` ברוחב 1440 וגובה 720.
  - אותה תמונה עם `square=True` → 1440×1440; הפיקסל במרכז זהה בערך לפיקסל המרכזי של המקור (התמונה לא נחתכה); פיקסל בפינה שונה מלבן טהור (רקע מטושטש).
  - WebP כקלט → JPEG. `b"not an image"` → `None`.
  - `ImgStore`: `get` מחזיר את ה-URL; אחרי 25 שעות → `None`; טוקן לא קיים → `None`; שני `put` → טוקנים שונים.
  - `soc_fetch_jpeg` עם http מזויף שזורק `Timeout` / מחזיר 404 / מחזיר HTML → `None` (Review Focus 2).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** (אפשר להתבסס על `ig_jpeg` / `ig_load_image` מ-`git show ig-story:ig_story.py`).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "social: המרת תמונות ל-JPEG ומאגר זמני"`.

### Task 6: לקוח Meta Graph

**Files:**
- Modify: `social_publish.py`
- Test: `tests/social/test_graph.py`

**Interfaces:**
- Produces:
  - `GRAPH_VER` (הגרסה העדכנית של Graph API — לבדוק בתיעוד, לא פחות מ-v21.0).
  - `class MetaError(Exception)` עם `.code: int | None`, `.unknown: bool` (True כש-timeout/חיבור נפל בבקשת כתיבה סופית).
  - `soc_mode(env: dict) -> str` → `"off" | "preview" | "publish"` לפי Global Constraints.
  - `class Graph(http, token: str, env: dict, sleep=time.sleep)`:
    - `me() -> dict`, `page_ig_id(page_id) -> str | None`, `page_token(page_id) -> str` (`GET /{page_id}?fields=access_token`, נשמר במופע; `invalidate_page_token()`), `ig_quota(ig_id) -> int | None` (כמה נשארו).
    - `fb_post(page_id, message, image_urls) -> tuple[str, str]` → `(post_id, permalink_url)`.
    - `ig_post(ig_id, caption, image_urls) -> tuple[str, str]` → `(media_id, permalink)`; תמונה אחת = container יחיד; יותר = ילדים + CAROUSEL; polling `status_code` עד `FINISHED` (מקסימום 40 × 3 ש'), `ERROR`/`EXPIRED` → `MetaError`.
    - כל בקשת כתיבה עוברת `_guard()` שזורקת `RuntimeError("SOCIAL_MODE is not publish")` אם `soc_mode(env) != "publish"`.
  - `_scrub(msg: str, token: str) -> str` (מוחק את הטוקן ואת טוקן העמוד מכל הודעה).

- [ ] **Step 1: Write failing tests** עם `http` מזויף שמקליט קריאות:
  - **Review Focus 5:** `soc_mode` מחזיר `"publish"` ל-`"publish"` ול-`" Publish "`; `"off"` ל-`"off"`; `"preview"` ל-`""`, לחסר, ל-`"true"`, `"1"`, `"yes"`, `"publsh"`. במצב preview `fb_post`/`ig_post` זורקים `RuntimeError` ו**אין אף POST ב-http**.
  - `fb_post` עם 3 תמונות: 3 קריאות `POST /{page}/photos` עם `published=false` ו-`url`, ואז `POST /{page}/feed` עם `attached_media` של שלושת ה-id ו-`message`; כל הקריאות לעמוד עם **טוקן העמוד**, לא עם `token`; ואז GET `permalink_url`.
  - `page_token` נקרא פעם אחת בלבד לשני פוסטים; שגיאה 190 → `invalidate_page_token()` וניסיון אחד חוזר עם טוקן חדש.
  - `ig_post` עם תמונה אחת: `POST /{ig}/media` עם `image_url`+`caption`, polling (`IN_PROGRESS` ואז `FINISHED`), `POST /{ig}/media_publish` עם `creation_id`, GET `permalink`. עם 3 תמונות: 3 ילדים עם `is_carousel_item=true`, container עם `media_type=CAROUSEL` ו-`children` מופרד בפסיקים.
  - `status_code=ERROR` → `MetaError`. שגיאת Meta `{"error":{"code":4,…}}` → `MetaError(code=4)`.
  - **Review Focus 3:** `Timeout` ב-`POST /feed` או ב-`media_publish` → `MetaError(unknown=True)` ו**אין** קריאה חוזרת לאותו endpoint.
  - הודעת שגיאה שמכילה את הטוקן → אחרי `_scrub` הטוקן לא מופיע; `str(MetaError)` לא מכיל אותו.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** בסיס: `ig_publish` / `_meta_err` / `_scrub` מ-`git show ig-story:ig_story.py`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "social: לקוח Meta Graph לעמוד ולאינסטגרם"`.

### Task 7: הרצה, ראוטים ולולאה — `register(app, G)`

**Files:**
- Modify: `social_publish.py`
- Modify: `app.py` — `import social_publish as _social` ליד `import goals as _goals` (שורה ~7955); `_social.register(app, globals())` מיד אחרי `_goals.register(app, globals())` (שורה ~13170), בתוך try/except עם `log.error` כמו השאר.
- Test: `tests/social/test_run.py`, `tests/social/test_routes.py`

**Interfaces:**
- Consumes מ-G: `_web_auth`, `_load_config`, `_config_mutate`, `fetch_sheet_rows` (נכסי המשרד במכירה) ו-`fetch_sheet_rows_deal("השכרה")`, `y2_clean_desc` (דרך `G["_effie_v2"]` אם לא ב-G — לבדוק איך goals מגיע לפונקציות של effie_v2; אחרת import `effie_v2.y2_clean_desc`), `_row_feats`, `_shabbat_quiet_now`, `_quiet_mode`, `_log_activity(name, role, phone, action, detail)`, `send_push(title, body)`, `_sbdb` (המודול `supabase_db`), `log`. רשימת המוסתרים: `site_api.prop_flags(<שורות website_settings>)[0]` — לבדוק בקוד איך site_api קורא את `website_settings` ולהשתמש באותה פונקציה.
- Produces:
  - `soc_run_one(G, key: str, trigger: str, by_phone: str, channels: list[str] | None = None, http=None, now=None) -> dict` → `{"ok": bool, "mode": str, "fb": status, "ig": status, "reason": str, "row_id": str}`. statuses: `"ok" | "failed" | "unknown" | "skipped" | "preview"`.
  - ראוטים:
    - `POST /v2/api/social/publish` `{key, channels?}` — מפתח בלבד (`drole == "developer"`, אחרת 403). מחזיר מיד `{"ok": true, "queued": true}`; העבודה ב-thread.
    - `GET /v2/api/social/preview?key=` — מפתח בלבד; מחזיר `body`, `ig_caption`, כתובות תמונה (מקור), ו-`can` לכל ערוץ.
    - `GET /v2/api/social/status?keys=a,b` — מפתח בלבד; לכל מפתח: הפרסום האחרון (תאריך, סטטוס לכל ערוץ, קישורים) + `can` לכל ערוץ.
    - `GET /v2/api/social/health` — מפתח בלבד; מצב טוקן (`me()`), מזהי עמוד/אינסטגרם (נשמרים ל-`v2_social`), מכסת אינסטגרם, מצב, 10 פוסטים אחרונים.
    - `GET /v2/social/img/<token>.jpg` ו-`/v2/social/img/<token>-sq.jpg` — בלי כניסה; 404 לטוקן לא קיים/פג; `Content-Type: image/jpeg`; `Cache-Control: no-store`.
  - לולאה: thread `social-auto` שמתחיל ב-`@app.before_request` (בדיוק כמו `register_weekly` ב-goals), כל `LOOP_SEC`; רק כש-`SOCIAL_AUTO=1` ו-`soc_mode=="publish"` ויש טוקן. בהפעלה הראשונה (`enabled_at` חסר) → `soc_seed_known` ושמירה, בלי פרסום. `flood` → `send_push` לאייל פעם אחת לסבב.
  - `soc_daily_alert(G, kind, now)` — פוש אחד ביום לכל סוג (`token`, `flood`), זיכרון ב-`v2_social.alerts`.

- [ ] **Step 1: Write failing tests** (`test_run.py`, עם G מזויף כמו `AutoG` ב-`tests/goals/test_goals_api.py`, Graph מזויף ו-SB מזויף בזיכרון):
  - preview: `soc_run_one` → שורה ב-`social_posts` עם `mode="preview"`, `fb_status="preview"`, `ig_status="preview"`, ושום קריאה ל-Graph.
  - publish: fb ok + ig ok → שורה עם שני ה-id והקישורים; שורת יומן `"פרסום ברשתות — פורסם"`.
  - fb ok + ig `MetaError` → `fb_status="ok"`, `ig_status="failed"`, `error` בלי הטוקן; יומן `"פרסום ברשתות — נכשל"`.
  - **Review Focus 3:** fb `MetaError(unknown=True)` → `fb_status="unknown"`; קריאה שנייה לאותו נכס באותו יום → `fb` מקבל `"skipped"` עם `"כבר נשלח היום"`.
  - **Review Focus 2:** כל התמונות נכשלות בהמרה → `ok=False`, `reason="אין תמונות"`, אין קריאה ל-Graph.
  - `MetaError(code=190)` → `soc_daily_alert(..., "token")` → `send_push` פעם אחת; קריאה נוספת באותו יום — לא שולח שוב.
  - קוד 4/17/32/613 → `v2_social.paused_until` = חצות; סבב אוטומטי לפני כן לא מפרסם.
  - `channels=["ig"]` מפרסם רק באינסטגרם. `SOCIAL_CHANNELS=fb` → ig `"skipped"`.
  - מכסת אינסטגרם 0 → ig `"skipped"` עם הסיבה.
  - **Review Focus 5:** `SOCIAL_MODE="true"` → מתנהג כ-preview.
- [ ] **Step 2: Write failing route tests** (`test_routes.py`, `Flask()` אמיתי + `social_publish.register(app, G)`):
  - סוכן / מנהל שאינו מפתח → 403 בכל `/v2/api/social/*`; בלי כניסה → 401.
  - מפתח, `POST /publish` → 200 `queued:true`, ו-`soc_run_one` נקרא עם `trigger="manual"` וה-`by_phone` של המחובר.
  - `/v2/social/img/<טוקן לא קיים>.jpg` → 404; טוקן קיים (http מזויף מחזיר תמונה) → 200, `image/jpeg`, מתחיל ב-`\xff\xd8`; `-sq` מחזיר ריבוע.
  - `/health` כשאין `META_TOKEN` → `{"ok": true, "connected": false}` בלי קריאה ל-Graph; התשובה לא מכילה את הטוקן (בדיקה עם טוקן `"SECRET123"` ב-env).
- [ ] **Step 3: Run** `python3 tests/social/test_run.py && python3 tests/social/test_routes.py` — Expected: FAIL.
- [ ] **Step 4: Implement** + חיבור ב-app.py.
- [ ] **Step 5: Run** — Expected: PASS. ואז `python3 -c "import ast,sys;ast.parse(open('app.py').read());ast.parse(open('social_publish.py').read())"`.
- [ ] **Step 6: Commit** — `git commit -m "social: הרצה, ראוטים ולולאה אוטומטית"`.

### Task 8: ממשק — כרטיס ב-/v2/dev, כפתור בכרטיס הנכס, ריבוע בלוח הבקרה

**Files:**
- Modify: `effie_v2.py` — `V2_DEV_HTML` (שורה ~11254: כרטיס חדש אחרי כרטיס "נוסחי הסכמים", באותו מבנה `<div class="card"><h2>…`); `propCard` במסך הנכסים (שורה ~7306, ליד `hotRow` בשורה ~7354); לוח הבקרה: מקור `"social"` ב-`src` (ליד `"goals_weekly"`, שורה ~19081) ושורה ב-`health` (ליד שורה ~15106) — באותו פורמט של `weekly_health_tile`.
- Modify: `social_publish.py` — `social_health_tile(G, now) -> dict` (`{"key":"social","label":"פרסום ברשתות","status":..., "last":...}`; `none` כשכבוי, אדום כש-`token_bad`).
- Test: `tests/social/test_ui.js`, `tests/social/test_tile.py`

**Interfaces:**
- Consumes: `/v2/api/social/health`, `/v2/api/social/preview`, `/v2/api/social/status`, `/v2/api/social/publish`; ב-`propCard` המפתח הוא `p.pkey`; המשתנה הגלובלי שמסמן מפתח בדף הנכסים — לבדוק מה קיים (`WHO.drole` או דומה) ולהשתמש בו.
- Produces (JS):
  - `socRow(p) -> string` — HTML של שורת המצב/הכפתור; ריק אם לא מפתח.
  - `socPublish(key)` ו-`socPreview(key)`.
  - טעינת מצב אחת לכל הרשימה המוצגת (`/status?keys=` עם המפתחות של הכרטיסים שעל המסך), לא קריאה לכל כרטיס.

- [ ] **Step 1: Write failing tests:**
  - `test_ui.js` (חילוץ הפונקציות מ-`effie_v2.py` כמו ב-`tests/goals/test_goals_ui.js`): לא-מפתח → `socRow` מחזיר `""`; `can.fb=true` → כפתור זהב `"פרסם ברשתות"` עם `onclick="socPublish(...)"` וגובה 44px לפחות; `can.fb=false` עם סיבה → כפתור `disabled` והסיבה בטקסט; פרסום קודם → `"פורסם 31/10 · פייסבוק ✓ · אינסטגרם ✓"` עם קישורים `target="_blank"`; `ig_status="failed"` מלפני פחות מ-`RETRY_DAYS` → כפתור `"נסה שוב לאינסטגרם"` שקורא ל-`socPublish(key, ['ig'])`, ומלפני יותר → בלי הכפתור הזה; אין אימוג'ים ב-HTML של הממשק.
  - `node --check` על הסקריפטים של דף הנכסים ושל `/v2/dev` אחרי החילוץ.
  - `test_tile.py`: כבוי → `status="none"`; טוקן תקין ופרסום היום → `"ok"`; `token_bad` → אדום (`"bad"` או הערך המקביל ב-`crm_health`).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** כרטיס `/v2/dev`: מצב חיבור, מכסה, שדה "מספר מודעה" + "תצוגה מקדימה" (טקסט + תמונות ממוזערות), רשימת 10 אחרונים.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "social: כרטיס בכלי המפתח, כפתור בכרטיס הנכס וריבוע בלוח הבקרה"`.

### Task 9: אימות כולל

**Files:** אין קבצים חדשים.

- [ ] **Step 1:** כל בדיקות `tests/social/*` + `tests/goals/*` + `tests/crm/*` + `tests/siteweb/*` + שאר הסקריפטים ב-`tests/` — Expected: הכל עובר (אותו בסיס כמו לפני הענף).
- [ ] **Step 2:** `ast.parse` על `app.py`, `effie_v2.py`, `social_publish.py`, `supabase_db.py`.
- [ ] **Step 3:** ייבוא האפליקציה עם env מדומה וספירת ראוטים — Expected: 5 ראוטים חדשים (`/v2/api/social/publish|preview|status|health`, `/v2/social/img/<...>`) נרשמים, ומספר הראוטים הכולל גדל בדיוק בהם.
- [ ] **Step 4:** בדיקה ידנית מקומית של `/v2/dev` ושל דף הנכסים בגודל טלפון (צילום מסך) במצב preview בלי טוקן.
- [ ] **Step 5:** ביקורת סופית של כל הענף (סוקר עצמאי), תיקונים, commit.
- [ ] **Step 6:** **לא לדחוף.** לדווח לאייל ולחכות לאישור מיזוג.

## הפעלה אחרי המיזוג (אייל, עם הדרכה בצ'אט)

1. SQL `20261031_social_posts.sql` ב-SQL Editor.
2. push+deploy (בלי `META_TOKEN` אין שום השפעה).
3. Meta: אפליקציה Business בתיק "רימקס פמילי" ← System User ← שיוך העמוד והאינסטגרם בשליטה מלאה ← טוקן עם ההרשאות מהספק ← Render `META_TOKEN`.
4. `/v2/dev` ← "פרסום ברשתות": חיבור תקין, תצוגה מקדימה לכמה נכסים.
5. `SOCIAL_MODE=publish` ← לחיצה על נכס אחד ← בדיקה בעמוד ובאינסטגרם.
6. `SOCIAL_AUTO=1`.
