# סרטוני סטורי + ריל לנכסי המשרד — תוכנית בנייה

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** אפי מייצרת לכל נכס משרד חדש (או בלחיצת מפתח) סרטון 9:16 של ~14ש' (קליפ Kling + מצגת + טקסט עברי + מוזיקה), שולחת לאייל ולסוכן לאישור בוואטסאפ, ובלחיצת "פרסם" מעלה סטורי+ריל לאינסטגרם ולעמוד הפייסבוק.

**Architecture:** מודול חדש `social_video.py` בדפוס `social_publish.py`: חלק טהור (טקסטים, חיתוך, תקרות, מכונת מצבים), רינדור (Pillow לשכבות PNG + ffmpeg להרכבה), לקוחות מוזרקים (fal, Claude vision), תזמור, וראוטים ב-`register(app, G)`. הרחבת `Graph` ב-`social_publish.py` לווידאו. שמירה בטבלאות חדשות `social_videos` ו-`social_links`. הוק בכפתורי וואטסאפ ב-`_d360_webhook` (app.py). ממשק בכרטיס הנכס וב-`/v2/dev` (effie_v2.py).

**Tech Stack:** Python 3 / Flask, requests, Pillow 10 + python-bidi 0.4.2, ffmpeg (`imageio-ffmpeg` בשרת), fal.ai queue REST, Anthropic Messages API (vision), Meta Graph API, WhatsApp Cloud API דרך 360dialog, Supabase REST.

**Spec:** `docs/superpowers/specs/2026-11-02-social-video-stories-reels-design.md` (commit `20f571f`). טיוטת הסרטון שאייל אישר: `scratchpad/mock/full_spike.py` + `mock.py` (גרסה א', לוגו גדול על מלבן לבן) — מקור לפריסה ולגדלים.

## Global Constraints

- עבודה בענף `claude/social-reels-stories-69efc1` (worktree). **בלי push ובלי merge ל-main** בלי OK מפורש של אייל. SQL ו-env — אצל אייל.
- סודות: `FAL_KEY`, `META_TOKEN`, `CLAUDE_API_KEY`, `D360_API_KEY` רק מ-env. אף פעם בלוג, בשגיאה, בתשובת API, בקונפיג או בבדיקה. כל שגיאה עוברת `social_publish._scrub(msg, [secrets])`.
- רק `SOCIAL_MODE=publish` (`soc_mode`) שולח וואטסאפ אישור, כותב ל-Meta, או מריץ את המסלול האוטומטי. ב-preview: רק כפתור ידני, סרטון בכרטיס `/v2/dev`.
- קבועים (social_video.py): `DAILY_CAP=3`, `MONTH_AI_CAP=100`, `APPROVE_H=48`, `RETRY_DAYS=3`, `KEEP_FINAL_DAYS=3`, `KEEP_MAX_DAYS=10`, `DIR_MAX_BYTES=1_000_000_000`, `FAL_TIMEOUT_S=480`, `RENDER_TIMEOUT_S=180`, `W,H=1080,1920`, `SAFE=(65,290,1015,1240)` (x0,y0,x1,y1), `XFADE=0.4`, `LOOP_SEC=600`.
- מודל ברירת מחדל: `FAL_VIDEO_MODEL=fal-ai/kling-video/v2.5-turbo/pro/image-to-video`, `duration "5"`, `negative_prompt "people, person, text, logo, watermark, new furniture, distortion, blur"`.
- פרומפט: `"Slow cinematic dolly-in through the {room}, natural daylight, smooth stable camera, realistic, keep the room exactly as in the photo, do not invent details, no people, no text, no logos, vertical 9:16"`; לחזית: `"Slow cinematic push-in on the building facade, natural daylight, smooth stable camera, realistic, keep the building exactly as in the photo, do not invent details, no people, no text, no logos, vertical 9:16"`.
- תזמון: AI 0–5 · תמונה 5–9 · תמונה 9–11.5 · סיום 11.5–14 (xfade 0.4).
- טקסט על המסך: אין מספר בית, טלפון בעלים, שם לקוח. רחוב מותר. טלפון בסרטון = **וירטואלי** (`_vphone_for_name`); קישור וואטסאפ = **אישי** (`_phones_for_name` פחות `_agent_vphones9`).
- עיצוב: גרסה א' — הצללה כהה למעלה/למטה, לבן `#FFFFFF`, זהב `#E4C56B`, נייבי `#0E1D33`, Heebo 500–800, לוגו `family-logo.png` על מלבן לבן (פינות ישרות) בגובה 150px, ממורכז ב-y=290. כל הטקסט בתוך `SAFE`. "הדמיית תנועה" רק על קטע AI אמיתי.
- ממשק אפי: פלטה סגורה (זהב לכפתור "צור סרטון"), אין אימוג'י ב-UI, מגע 44px, מפתח בלבד (`drole == developer`).
- בדיקות: סקריפטים `python3 tests/social_video/test_X.py` בסגנון `ck()` של `tests/social/`; Flask דרך `register()` האמיתי עם G מזויף; JS דרך `node --check`. בלי קריאה אמיתית ל-fal/Meta/Claude/WhatsApp — `http` מוזרק.
- אימות קבצים קנוניים אחרי שינוי: `python3 -c "import ast; ast.parse(open('<path>').read())"` ל-app.py/effie_v2.py/social_*.py.

## Review Focus

1. **לחיצה כפולה/מקבילה על "פרסם"** (אייל והסוכן כמעט יחד, או webhook שחוזר פעמיים) → פרסום אחד בלבד; השני מקבל "כבר פורסם ע"י X". בדיקה: Task 3 (מכונת מצבים) + Task 10 (webhook ×2).
2. **נכס שאין לו מחיר / חדרים / שכונה / קומה** → השורה הרלוונטית נשמטת, אין "None"/"0 חדרים"/"קומה " ריק על המסך. בדיקה: Task 2.
3. **fal מחזיר 402/401 או timeout** → הסרטון נוצר בלי AI (Ken Burns), אין ניסיון חוזר אחרי timeout, פוש קרדיט פעם ביום. בדיקה: Task 6 + Task 9.
4. **הסרטון נמחק מהדיסק לפני "פרסם"** (ניקוי/דפלוי) → "הסרטון לא זמין — צור מחדש", שום קריאה ל-Meta. בדיקה: Task 9.
5. **payload זר/מזויף בכפתור וואטסאפ או טוקן דף אישור לא קיים/פג** → מתעלמים / 404, אין שינוי מצב. בדיקה: Task 10.

---

### Task 1: טבלאות + עזרי Supabase + fakes

**Files:**
- Create: `docs/superpowers/plans/sql/2026-11-02_social_videos.sql`
- Modify: `supabase_db.py` (אחרי `social_recent`)
- Create: `tests/social_video/_fakes.py`, `tests/social_video/test_db.py`

**Interfaces:**
- Produces (supabase_db): `video_insert(rec) -> dict|None`, `video_update(vid, fields) -> bool`, `video_get(vid) -> dict|None`, `video_claim(vid, frm, to, fields) -> bool` (PATCH עם `status=eq.<frm>` ו-`Prefer: return=representation`; True רק אם שורה אחת חזרה), `video_recent(days) -> list` (חדש קודם), `link_insert(rec) -> dict|None`, `link_get(code) -> dict|None`, `link_click(code) -> None` (clicks+1, last_click_at).
- Produces (fakes): `SBV` (אותם מתודות בזיכרון, `video_claim` אטומי עם lock), `make_G(rows=None, cfg=None)` מורחב מ-`tests/social/_fakes.make_G` עם `_vphone_for_name`, `_phones_for_name`, `_agent_vphones9`, `send_text`, `_d360_on`, `_wa_window_open`, `_d360_post_message` (מקליטים), `ROW` עם 4 תמונות.

- [ ] **Step 1:** SQL: `social_videos` (עמודות לפי הספק §7, `status text not null default 'rendering'`, `ai boolean default false`, `ai_cost_usd numeric`, timestamps `default now()`), `social_links` (`code text primary key`, `clicks int default 0`), שתיהן `office_id uuid not null`, RLS enable בלי policies, אינדקס `(office_id, created_at desc)`.
- [ ] **Step 2: Failing test** `test_db.py`: מול `requests` מזויף — `video_claim` שולח `params` עם `status=eq.pending` ומחזיר False כשהתשובה `[]`; `video_insert` מוסיף `office_id`; `link_click` עושה GET+PATCH עם clicks+1.
- [ ] **Step 3:** run → FAIL. **Step 4:** implement (אותו סגנון של `social_insert` — try/except → None/False). **Step 5:** run → PASS.
- [ ] **Step 6: Commit** `סרטונים: טבלאות social_videos/social_links + עזרי supabase`

### Task 2: חלק טהור — טקסטים ותזמון

**Files:** Create `social_video.py` (header + קבועים + פונקציות טהורות), `tests/social_video/test_texts.py`

**Interfaces:**
- Consumes: `social_publish._price`, `_num`, `soc_floor`, `soc_scrub_house`, `soc_scrub_phones`.
- Produces: `vid_texts(row, feats: list[str], highlight: str, agent: str, vphone: str, office_phone: str) -> dict` עם מפתחות `open` (`chip`, `title`, `place`, `price`), `s2` (`main`, `sub`), `s3` (`main`, `sub`), `end` (`recap`, `agent`, `phone`, `cta`). `vid_timeline(n_slides: int, ai: bool) -> list[tuple[str, float]]` (שם קטע, אורך).

- [ ] **Step 1: Failing tests:**
  - `ROW` מכירה → `open.title == "4 חדרים למכירה"`, `open.place == "נאות אפק, קרית ביאליק"`, `open.price == "1,890,000 ₪"`, `open.chip == "חדש בשוק"`.
  - השכרה, מחיר 5500 → `price == "5,500 ₪ לחודש"`, title "… להשכרה".
  - `s2.main == '110 מ"ר · קומה 3'`; בלי קומה → `'110 מ"ר'`; בלי מ"ר ובלי קומה → `s2` ריק (`main == ""`).
  - `s3.main == highlight` כש-highlight לא ריק; אחרת `" · ".join(feats[:3])`; `s3.sub` = feats כשה-main הוא highlight.
  - `end.agent == agent`, `end.phone == vphone`; vphone ריק → `office_phone`; שניהם ריקים → `phone == ""`. `end.cta == "שלחו הודעה ונחזור אליכם"`. `end.recap == "4 חדרים · 1,890,000 ₪"`.
  - אין שום ערך המכיל `"13"` (מספר הבית) או `"None"`; highlight עם טלפון → נמחק.
  - `vid_timeline(2, True) == [("ai",5),("s2",4),("s3",2.5),("end",2.5)]`; `vid_timeline(1, True)` → `[("ai",5),("s2",4.5),("end",4.5)]`; `ai=False` → הקטע הראשון נקרא `"kb"` באותו אורך.
- [ ] **Step 2–5:** run FAIL → implement → PASS.
- [ ] **Step 6: Commit** `סרטונים: טקסטים ותזמון (טהור)`

### Task 3: חלק טהור — חיתוך, תקרות, מכונת מצבים, ניקוי

**Files:** Modify `social_video.py`; Create `tests/social_video/test_logic.py`

**Interfaces:**
- Produces:
  - `vid_crop_box(w: int, h: int, wm: tuple|None, aspect=9/16, bias=0.5) -> tuple[int,int,int,int]|None` — חלון ברוחב `h*aspect` לכל הגובה; `wm`=(x0,y0,x1,y1) בשברים; בוחר את המיקום הקרוב ל-`bias` שלא חותך את wm; None אם אין.
  - `vid_pan_range(w, h, wm) -> tuple[float,float]` — טווח x (שברים 0–1 של `iw-ow`) למסלול pan שלא נכנס ל-wm; ברירת מחדל (0.25, 0.75).
  - `vid_can_create(row, history_videos, now, hidden, trigger) -> (bool, reason)` — אותם תנאים כמו `soc_can_publish(row, "ig", …)` לגבי משרד/פעיל/הסתרה/מסחרי + ≥2 תמונות + לא נוצר סרטון ל"אותה דירה" ב-14 יום (סטטוס ≠ failed/skipped/expired) + אין סרטון `pending/rendering` לאותו נכס.
  - `vid_caps(history_videos, now, trigger) -> (bool, reason)` — יומי: `trigger=="auto"` ושורות auto מהיום ≥3 → False; חודשי: שורות `ai=True` מתחילת החודש ≥100 → False ("תקרה חודשית").
  - `vid_decide(rec, action: "pub"|"skip", who: str, now) -> (new_status|None, msg)` — רק מ-`pending`; פג אם `now - sent_at > 48h` → (`"expired"`, "הסרטון כבר לא בתוקף"); אחרת `approved`/`skipped`. מצב אחר → (None, "כבר {פורסם/דולג/פג} ע"י {decided_by}").
  - `vid_publish_when(now, blocked: bool) -> float` — now אם לא חסום, אחרת 08:00 הבא (שבת → מוצ"ש 20:00 דרך הקורא).
  - `vid_gc(files: list[(token, size, mtime)], recs_by_token: dict, now) -> list[token]` — למחיקה לפי הספק (סופי+3 ימים, קשיח 10 ימים, תקרת 1GB מהישן לחדש).
- [ ] **Step 1: Failing tests:** חיתוך 1440×960 עם wm שמאל-עליון (0.03,0.03,0.17,0.13) → x0 ≥ 0.17*1440; wm באמצע-למטה (0.45,0.88,0.6,0.97) בגובה מלא → None כשאין מקום ו-bias; תקרה יומית 3 auto → False, ידני → True; חודשית 100 ai → False גם לידני; decide: pending→approved; שני decide → None + "כבר פורסם ע"י אייל"; 49 שעות → expired; gc: published+4 ימים נמחק, pending+4 ימים לא, כל דבר+11 יום נמחק.
- [ ] **Step 2–5:** FAIL → implement → PASS.
- [ ] **Step 6: Commit** `סרטונים: חיתוך, תקרות, מכונת מצבים, ניקוי (טהור)`

### Task 4: שכבות טקסט (Pillow)

**Files:** Modify `social_video.py`; Copy `fonts/Heebo-VF.ttf`, `fonts/OFL-Heebo.txt` (מ-`git show ig-story:fonts/...`); Create `tests/social_video/test_layers.py`

**Interfaces:**
- Produces: `vid_layers(texts: dict, timeline, logo_path: str, ai: bool, out_dir: str) -> dict[str, str]` — PNG שקוף 1080×1920 לכל קטע (`ai`/`kb`, `s2`, `s3`, `end`), כולל ההצללה (פתיחה/אמצע: רצועה כהה מאחורי טקסט אמצעי; סיום: כיסוי `(8,16,30,165)` + הצללה). פריסה, גדלים ומשקלים — כמו `full_spike.py` (s1–s4). `_font(size, weight)` עם `set_variation_by_axes([weight])`; `_rtl(s)` = `bidi.get_display`.
- [ ] **Step 1: Failing tests:** כל PNG בגודל 1080×1920 RGBA; תיבת הפיקסלים הלבנים/זהובים האטומים (alpha>200, לא ההצללה) כולה בתוך `SAFE`; "הדמיית תנועה" (בדיקה: פיקסלים ב-y≈1210 x>900) קיימים ב-`ai` ולא ב-`kb`; טקסט ריק → אין קריסה.
- [ ] **Step 2–5:** FAIL → implement → PASS.
- [ ] **Step 6: Commit** `סרטונים: שכבות טקסט עבריות (Pillow+bidi+Heebo)`

### Task 5: הרכבה ב-ffmpeg + מוזיקה

**Files:** Modify `social_video.py`, `requirements.txt` (+`imageio-ffmpeg==0.5.1`); Create `assets/music/` (+`SOURCES.md`), `tests/social_video/test_compose.py`

**Interfaces:**
- Produces: `vid_ffmpeg() -> str|None` (נתיב: `imageio_ffmpeg.get_ffmpeg_exe()` ואם אין `shutil.which("ffmpeg")`); `vid_compose(clip_path: str|None, slides: list[(jpeg_bytes, wm)], layers: dict, timeline, music_path: str|None, out_path: str, run=subprocess.run) -> dict` → `{"ok", "duration", "cover"}` (cover = `<out>-cover.jpg` מפריים 0.5ש').
- קטע AI: `scale=1080:1920,fps=30,setsar=1` + overlay, `-t` לפי timeline. בלי clip: Ken Burns על תמונת ה-AI (zoom 1.0→1.08 מרכזי). שקפים: תמונה מוגדלת לגובה 2000, `crop=1125:2000:x=<pan לפי vid_pan_range>`, `scale=1080:1920`. חיבור xfade 0.4. אודיו: מוזיקה `afade in 0.5 / out 1.0`, `volume=0.35`; בלי מוזיקה — `anullsrc` שקט (תמיד יש ערוץ AAC 48k). פלט: `-c:v libx264 -preset veryfast -crf 21 -pix_fmt yuv420p -r 30 -g 60 -movflags +faststart -c:a aac -ar 48000 -threads 1`. כל קטע נכתב לקובץ ואז concat (חוסך זיכרון). `run(..., timeout=RENDER_TIMEOUT_S)`.
- מוזיקה: `vid_music(key) -> str|None` — בחירה דטרמיניסטית (`hashlib.md5(key)`) מ-`assets/music/*.mp3`. הורדה: 5 קטעים שקטים מ-Pixabay Music (רישיון Pixabay Content License) אם אפשר להוריד בלי התחברות; אחרת התיקייה ריקה + שורה ב-`SOURCES.md` "לאייל להוסיף" והסרטונים שקטים.
- [ ] **Step 1: Failing test** (מדולג עם הודעה אם `vid_ffmpeg()` None): 3 JPEG צבעוניים 1440×960 + שכבות מ-Task 4 + קליפ דמה (ffmpeg `testsrc` 768×1364 5ש') → MP4 1080×1920, משך 14±0.6, יש stream אודיו aac, `moov` לפני `mdat` (קריאת 64KB ראשונים), cover קיים; בלי clip → עדיין 14±0.6; `run` מזויף שזורק TimeoutExpired → `ok False`.
- [ ] **Step 2–5:** FAIL → implement → PASS. מדידת זיכרון: הרץ פעם אחת `/usr/bin/time -l python3 tests/social_video/test_compose.py` ורשום את maximum resident set ב-commit message (יעד <600MB).
- [ ] **Step 6: Commit** `סרטונים: הרכבה ב-ffmpeg + מוזיקה`

### Task 6: לקוח fal

**Files:** Modify `social_video.py`; Create `tests/social_video/test_fal.py`

**Interfaces:**
- Produces: `class FalError(Exception)` עם `.code` ו-`.unknown`; `class Fal: __init__(http, key, model=None, sleep=time.sleep, clock=time.time)`; `clip(jpeg_bytes: bytes, prompt: str) -> bytes` (MP4); `MODEL_ARGS = {"kling": {"duration": "5", "negative_prompt": …}, "hailuo": {"duration": "6", "prompt_optimizer": False}}` נבחר לפי מחרוזת במזהה; `vid_prompt(room: str) -> str`; `FAL_COST = {"kling": 0.35, "hailuo": 0.19}`.
- זרימה: POST `https://queue.fal.run/<model>` עם `Authorization: Key <key>` ו-`image_url` כ-data URI → `status_url`/`response_url` → polling כל 8ש' עד `FAL_TIMEOUT_S` → GET response → `video.url` → הורדה. סטטוס שאינו IN_QUEUE/IN_PROGRESS/COMPLETED → `FalError` ודאי. 401/402/403 בהגשה → `FalError(code)`. timeout → `FalError(unknown=True)`.
- `vid_ai_clip(fal, jpeg, room) -> (bytes|None, err_code|None, cost)` — ניסיון חוזר אחד רק לכשל ודאי שאינו 401/402/403; unknown → בלי חזרה.
- [ ] **Step 1: Failing tests** (http מזויף): הצלחה → bytes והמפתח לא בשום URL/גוף שנרשם מלבד הכותרת; FAILED → ניסיון שני מצליח → נקרא submit פעמיים; timeout (clock מזויף) → unknown, submit פעם אחת; 402 → `(None, 402, 0)` ובלי ניסיון שני; הודעת השגיאה לא מכילה את המפתח.
- [ ] **Step 2–5:** FAIL → implement → PASS.
- [ ] **Step 6: Commit** `סרטונים: לקוח fal (Kling) עם ניסיון חוזר זהיר`

### Task 7: בחירת תמונות (Claude vision)

**Files:** Modify `social_video.py`; Create `tests/social_video/test_pick.py`

**Interfaces:**
- Produces: `vid_pick(http, api_key, images: list[bytes], desc: str, feats: list[str]) -> dict` → `{"ai": idx, "room": str, "slides": [idx…≤3], "highlight": str, "wm": {idx: (x0,y0,x1,y1)|None}, "skip": [idx]}`. קריאה אחת ל-`https://api.anthropic.com/v1/messages` (model `claude-sonnet-4-5`, כמו `parse_listing_text`), עד 8 תמונות מוקטנות ל-512px base64, הוראה להחזיר JSON בלבד. ולידציה: אינדקסים בטווח, ai∉slides, ai∉skip, highlight ≤4 מילים ו**כל מילה שלו מופיעה בתיאור** (אחרת ""), טלפונים נמחקים. כל כשל/JSON שבור → fallback: ai=0, slides=[1,2,3]∩טווח, highlight="", wm=פינה שמאלית-עליונה (0.02,0.02,0.18,0.14) לכל תמונה.
- [ ] **Step 1: Failing tests:** תשובה תקינה → מועתקת; highlight "נוף לים" כשאין "ים" בתיאור → ""; JSON שבור → fallback; ai מחוץ לטווח → fallback; http זורק → fallback; המפתח לא בהודעת שגיאה.
- [ ] **Step 2–5:** FAIL → implement → PASS.
- [ ] **Step 6: Commit** `סרטונים: בחירת תמונות וזיהוי סימן מים (Claude vision) עם נפילה בטוחה`

### Task 8: Graph — וידאו לאינסטגרם ולעמוד

**Files:** Modify `social_publish.py` (מחלקת `Graph`); Create `tests/social_video/test_graph_video.py`

**Interfaces:**
- Produces (מתודות `Graph`, כולן קוראות `_guard()` ראשון):
  - `ig_video(ig_id, kind: "STORIES"|"REELS", video_url, caption="", cover_url="") -> (media_id, permalink)` — container עם `media_type`, `video_url`, `is_ai_generated="true"`; ל-REELS גם `caption`, `share_to_feed="true"`, `cover_url`; `_wait(cid, poll_max=60)`; `media_publish` final; permalink רק לריל.
  - `fb_video_story(page_id, file_url) -> story_id` — `video_stories` start → POST ל-`upload_url` עם header `file_url` (דרך `self.http.post(upload_url, headers={"Authorization": "OAuth <ptoken>", "file_url": file_url})`) → finish (final).
  - `fb_reel(page_id, file_url, description) -> (video_id, permalink)` — `video_reels` start → `https://rupload.facebook.com/video-upload/<ver>/<video_id>` עם אותם headers → finish עם `video_state=PUBLISHED`, `description` (final) → GET `permalink_url`.
- [ ] **Step 1: Failing tests** (http מקליט): STORIES בלי caption/share_to_feed; REELS עם share_to_feed+cover+is_ai_generated; fb story שלושה שלבים בסדר; reel עם `video_state=PUBLISHED`; כש-`SOCIAL_MODE=preview` → RuntimeError לפני כל http; טוקן העמוד לא מופיע בהודעת `MetaError`.
- [ ] **Step 2–5:** FAIL → implement → PASS. הרץ גם `for f in tests/social/test_*.py; do python3 $f || break; done` — כל הבדיקות הקיימות עדיין עוברות.
- [ ] **Step 6: Commit** `פרסום ברשתות: Graph לווידאו (סטורי+ריל, IG+FB)`

### Task 9: תזמור — יצירה ופרסום

**Files:** Modify `social_video.py`; Create `tests/social_video/test_run.py`

**Interfaces:**
- Consumes: Tasks 1–8; `social_publish.soc_office_rows`, `soc_hidden`, `soc_build_post`, `soc_images`, `soc_big_url`, `soc_fetch_jpeg`, `_clean_desc`, `_cfg_social`, `soc_daily_alert`, `PAGE_ID_DEFAULT`, `_key`, `soc_addr_key`.
- Produces:
  - `VidStore` (תיקייה `MAP_CACHE_DIR/social_videos` או tmp): `path(token)`, `cover(token)`, `exists(token)`, `new_token()` (`secrets.token_urlsafe(12)`).
  - `vid_create_one(G, key, trigger, by_phone, http=None, now=None, env=None, store=None) -> dict` `{"ok","id","status","reason","ai"}` — inflight lock לנכס; בדיקות (`vid_can_create`, `vid_caps`); שורה `rendering`; הורדת עד 8 תמונות; `vid_pick`; קליפ (רק אם `FAL_KEY` ומודל; 401/402 → `soc_daily_alert(G,"fal",…,"חשבון fal — צריך לטעון קרדיט")`); שכבות; הרכבה; עדכון `status` ל-`preview` (preview) או `pending` + `sent_at` + שליחת אישורים (Task 10, `vid_send_review`) ב-publish; כשל → `failed` + error מנוקה. activity log "סרטון לרשתות — נוצר/נכשל".
  - `vid_publish(G, vid, http=None, now=None, env=None, store=None, channels=None) -> dict` — דורש `status in (approved, partial)`; קובץ חסר → "הסרטון לא זמין — צור מחדש" בלי Meta; לכל ערוץ (`ig_story`,`ig_reel`,`fb_story`,`fb_reel`) שאינו `ok`: Graph; caption לריל IG = `soc_build_post(...)["ig_caption"]` + שורה "שלחו לנו הודעה"; תיאור ריל FB = body + `"לוואטסאפ ישיר: <base>/w/<code>"` (code חדש ב-`social_links` עם channel `fb_reel`); 190/102/קצב כמו `social_publish`; סטטוס סופי `published` (4/4) או `partial`; activity log.
- [ ] **Step 1: Failing tests** (G מזויף, Fal/Graph/pick מזויפים, `vid_compose` אמיתי אם יש ffmpeg — אחרת מזויף):
  - preview: שורה `preview`, אין `send_text`/Graph; publish: `pending` + שתי הודעות אישור (אייל + סוכן אישי, לא וירטואלי).
  - בלי `FAL_KEY` → `ai False`, הודעת האישור מכילה "ללא AI".
  - fal 402 → ממשיך בלי AI + פוש "fal" פעם אחת ביום.
  - `vid_publish` על `approved`: 4 קריאות Graph בסדר, תיאור ריל FB מכיל `/w/`, caption IG לא מכיל `/w/` ולא מספר בית; ig_reel נכשל → `partial`, הרצה חוזרת עם `channels` שולחת רק אותו.
  - קובץ נמחק → reason "הסרטון לא זמין — צור מחדש", אפס קריאות Graph.
  - preview mode + `vid_publish` → RuntimeError לא דולף; reason "מצב בדיקה".
- [ ] **Step 2–5:** FAIL → implement → PASS.
- [ ] **Step 6: Commit** `סרטונים: יצירה ופרסום (תזמור)`

### Task 10: אישור בוואטסאפ + דף אישור + קישור /w/

**Files:** Modify `social_video.py`, `app.py` (`_d360_webhook`, ~שורה 704); Create `tests/social_video/test_review.py`

**Interfaces:**
- Produces:
  - `vid_send_review(G, rec, base, env) -> list[str]` — נמענים: `SOCIAL_VIDEO_APPROVER` או `DEV_PHONES` + הסוכן (אישי, מסונן מול `_agent_vphones9`, בלי כפילות). לכל נמען בחלון 24ש' (`G["_wa_window_open"]`): הודעת `video` (`link` לסרטון, caption) ואז `interactive` `button` עם `reply` ids `vid:<id>:pub` / `vid:<id>:skip` (כותרות "פרסם" / "דלג") דרך `G["_d360_post_message"]`. מחוץ לחלון: אם `WA_TPL_VIDEO` מוגדר — template עם header video ו-quick replies (payloads זהים); אחרת `G["send_text"](to, "סרטון לנכס … מוכן — לצפייה ולאישור: <base>/v2/social/review/<review_token>")`. שעות: אם `_quiet_hours()`/שבת — לא שולחים, מסמנים `review_due` (הלולאה שולחת).
  - `vid_on_button(G, from_phone, payload) -> str|None` — מפענח `vid:<id>:(pub|skip)`; רק אם `from_phone` (last9) ברשימת הנמענים של הרשומה; `video_claim(pending→approved|skipped)`; approved → `vid_publish` ב-thread (או מתוזמן לפי `vid_publish_when`); מחזיר טקסט תשובה ונשלח ל-from.
  - app.py `_d360_webhook`: לכל `m` עם `type in ("interactive","button")` → `payload = m["interactive"]["button_reply"]["id"]` או `m["button"]["payload"]`; אם מתחיל ב-`vid:` → `globals()["_social_video"].vid_on_button(globals(), m["from"], payload)` ב-try/except (לוג אזהרה).
  - ראוטים (ב-register של Task 11): `GET /v2/social/review/<tok>` (HTML נגן + שני כפתורים, RTL, פלטת אפי, 44px), `POST /v2/social/review/<tok>` `{action}` → אותו `vid_decide`/claim; `GET /w/<code>` → `link_click` + 302 ל-`https://wa.me/972<9 ספרות>?text=<urlencoded>` (הודעה: "היי, ראיתי ב{ריל בפייסבוק|…} את הדירה — {title}, {place}, {price} (מודעה {key}). אשמח לפרטים"); הסוכן לפי `סוכן 1` הנוכחי של הנכס; אין טלפון אישי → טלפון המשרד מ-`v2_office.phone`; קוד לא קיים → 404.
- [ ] **Step 1: Failing tests:** בחלון → 2 קריאות `_d360_post_message` לכל נמען (video, interactive) עם ids נכונים; מחוץ לחלון בלי תבנית → `send_text` עם `/v2/social/review/`; וירטואלי של הסוכן לא בנמענים; `vid_on_button` פעמיים → publish נקרא פעם אחת, תשובה שנייה "כבר פורסם ע"י"; payload זר / טלפון זר → None ואין שינוי; webhook ב-app.py (חילוץ `_d360_webhook` דרך ast + G מזויף) מנתב `button_reply` ו-`button.payload`; `/w/<code>` → 302 עם `wa.me/972` ו-clicks+1, קוד זר → 404; דף אישור פג → "לא בתוקף".
- [ ] **Step 2–5:** FAIL → implement → PASS. `ast.parse` על app.py.
- [ ] **Step 6: Commit** `סרטונים: אישור בוואטסאפ (כפתורים/דף), webhook, קישור וואטסאפ לסוכן`

### Task 11: ראוטים, לולאה אוטומטית, ניקוי, רישום

**Files:** Modify `social_video.py` (`register(app, G)`), `app.py` (import ליד `import social_publish as _social` + `_social_video.register(app, globals())` ליד שורה 13384); Create `tests/social_video/test_routes.py`

**Interfaces:**
- Produces ראוטים: `POST /v2/api/social/video {key}` (מפתח; spawn `vid_create_one(..., "manual")`); `GET /v2/api/social/videos?keys=` (מפתח; לכל נכס: הסרטון האחרון, סטטוס ערוצים, `can`); `POST /v2/api/social/video/retry {id, channels}` (מפתח; רק `partial` ובתוך 3 ימים); `GET /v2/api/social/video/health` (מפתח; `fal` מצב מפתח, עלות AI החודש, מונה מול תקרה, אחרונים); `GET /v2/social/vid/<tok>.mp4` ו-`<tok>-cover.jpg` (ציבורי, 404 לזר, `Cache-Control: no-store`, תמיכה ב-Range); + ראוטי Task 10.
- `vid_auto_tick(G, now, env)`: רק `SOCIAL_VIDEO_AUTO=1` + publish + `META_TOKEN`; זריעת `v2_social.vid_known` בפעם הראשונה (כמו `soc_auto_tick`); מועמדים חדשים → עד 3 ביום, השאר `vid_waiting` עד 3 ימים; לא בלילה/שבת/השתקה; גם: שליחת `review_due`, סימון expired (48ש'), פרסומים מתוזמנים שהגיע זמנם, `vid_gc`.
- לולאה ב-`before_request` (דפוס `social_publish.register`), thread `social-video`, `LOOP_SEC`.
- [ ] **Step 1: Failing tests:** 401/403 ללא-מפתח בכל `/v2/api/social/video*`; POST מפעיל `vid_create_one` עם trigger manual; mp4 ציבורי 200 לטוקן קיים / 404 לזר; tick: לא רץ ב-preview; זריעה ראשונה בלי יצירה; 5 חדשים → 3 נוצרים, 2 ממתינים; לילה → 0; expired מסומן; ast על app.py.
- [ ] **Step 2–5:** FAIL → implement → PASS. ייבוא מודול אמיתי: `MAYTAPI_TOKEN=x MAYTAPI_PHONE_ID=x MAYTAPI_PRODUCT_ID=x CLAUDE_API_KEY=x python3 -c "import app"` ובדיקה שהראוטים קיימים ב-`app.url_map`.
- [ ] **Step 6: Commit** `סרטונים: ראוטים, לולאה אוטומטית, ניקוי, רישום באפליקציה`

### Task 12: ממשק — כפתור בכרטיס, כרטיס /v2/dev, ריבוע בקרה

**Files:** Modify `effie_v2.py` (ליד בלוק `[SOCIAL 31/10]` ~7140 ו-~7357, כרטיס dev ~11466, `social_health_tile` / ריבוע ~15296), `social_video.py` (`video_health_line(G, now, env) -> dict`); Create `tests/social_video/test_ui.js` (node על ה-JS המחולץ)

**Interfaces:**
- JS: `VID = {items:{}, busy:{}}`; `vidRow(p)` — מתחת ל-`socRow(p)`: כפתור זהב "צור סרטון" (או "צור סרטון (מצב בדיקה)"), ושורה "סרטון: ממתין לאישור / פורסם 02/11 · 4/4 / חלקי — נסה שוב"; `vidLoad(list)` דרך `/v2/api/social/videos`; `vidCreate(k)` עם busy guard.
- dev card: אזור "סרטונים" — `<video controls playsinline>` ל-5 האחרונים (cover כ-poster), מצב לכל ערוץ, מי החליט, עלות החודש ומונה, מצב fal.
- ריבוע בקרה: שורת סרטונים בתוך הריבוע הקיים; `bad` כש-fal 401/402 היום.
- [ ] **Step 1: Failing test:** `test_ui.js` — `vidRow` לא מחזיר כלום ללא מפתח / שת"פ / נכס נולד; עם `items[k].last.status=="pending"` מציג "ממתין לאישור"; busy → כפתור disabled; אין אימוג'י במחרוזות.
- [ ] **Step 2–5:** FAIL → implement → PASS; `node --check` על כל בלוק JS שהשתנה; `ast.parse` על effie_v2.py.
- [ ] **Step 6: Commit** `סרטונים: כפתור בכרטיס הנכס, כרטיס /v2/dev, ריבוע בקרה`

### Task 13: אימות מקצה לקצה מקומי + הוראות הפעלה

**Files:** Create `docs/handoff/social-video-activation.md` (SQL, env, צעדי אייל, נוסח תבנית `video_review` להגשה ב-360dialog)

- [ ] **Step 1:** הרצה מקומית אחת של `vid_create_one` במצב preview על נכס הלוטם (התמונות מ-`scratchpad/mock/src`, G מזויף, fal אמיתי עם `~/.fal_key`, Graph מזויף) → MP4 נשלח לאייל לצפייה. עלות ≤0.35$.
- [ ] **Step 2:** כל הבדיקות: `for f in tests/social/test_*.py tests/social_video/test_*.py; do python3 $f || exit 1; done; node tests/social_video/test_ui.js`.
- [ ] **Step 3:** ביקורת ענף מלאה (subagent, המודל החזק).
- [ ] **Step 4: Commit** `סרטונים: הוראות הפעלה`
