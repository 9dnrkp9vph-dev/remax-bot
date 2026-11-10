# Voice Agent Lab (שלב 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** מסך מעבדה `/v2/voice` שבו בעל המשרד מדבר בקול (דפדפן) עם סוכן קולי בעברית שמשחק "העוזרת הדיגיטלית" ומנסה לתאם פגישה לנכס אמיתי מנכס נולד; כל שיחה נשמרת עם תמלול ותוצאה.

**Architecture:** מודול חדש `voice_agent.py` (`register(app, G)` כמו `dialer.py`). השרת בונה הנחיות + נתונים (קונים מתאימים, עסקאות ברחוב, 2 מועדים) ומנפיק מפתח זמני מ-OpenAI Realtime; הדפדפן מתחבר ב-WebRTC ישירות ל-OpenAI, עונה בעצמו על כלי הנתונים מתוך תשובת השרת, ושולח לשרת תמלול/תוצאה אחרי כל תור. שמירה בטבלת Supabase חדשה.

**Tech Stack:** Python/Flask, requests, OpenAI Realtime API (`POST /v1/realtime/client_secrets`, WebRTC `POST /v1/realtime/calls`), Supabase PostgREST, JS וניל בתוך מחרוזת HTML.

**Spec:** `docs/superpowers/specs/2026-11-10-voice-agent-design.md`

## Global Constraints

- הכל מוגש רק לבעל המשרד: `s.get("dev") or G["_is_dev"](s.get("phone",""))`; אחרת `{"ok":False,"allowed":False}` (401 בלי כניסה).
- env: `OPENAI_API_KEY` (ריק = "לא מוגדר", בלי קריאה החוצה), `VOICE_MODEL` (ברירת מחדל `gpt-realtime-2025-08-28` — הגרסה הראשונה, לא 1.5), `VOICE_VOICE` (ברירת מחדל `marin`).
- המפתח הקבוע לעולם לא נשלח לדפדפן — רק `client_secret.value` הזמני.
- שם המשרד מ-`v2_office.name` / `G["_office_name"]()` — לא hardcoded.
- פלטה סגורה של אפי, Heebo, RTL, כרטיסים לבנים radius 20–22, מגע 44px, אדום רק למחיקה, זהב = AI.
- אין כתיבה ליומן / nbStatus / פוש בשלב 1.
- כל שגיאה בהרשמת המודול לא מפילה את האפליקציה (try/except ב-app.py כמו dialer).
- בדיקות בסגנון הריפו: `python3 tests/voice/test_*.py` עם `check()` ו-exit code.

## Review Focus

1. **אין `OPENAI_API_KEY`** → המסך מציג מצב ריק מעוצב "הסוכן הקולי לא מוגדר" ולא שגיאת JS/500. (Task 3)
2. **OpenAI מחזיר שגיאה בהנפקת המפתח** (401/429/500) → `/session` מחזיר `{ok:false, reason:"openai", status}` והמסך מציג הודעה; לא נוצרת שורת שיחה יתומה. (Task 3)
3. **ליד בלי שם בעלים / 0 קונים / 0 עסקאות** → ההנחיות לא מזכירות שם, ולא אומרות "0 קונים"/"0 עסקאות" (הסוכן לא ממציא). (Task 2)
4. **מספר בית ברחוב** ("עוזי חיטמן 19") → בהנחיות הפתיחה הרחוב בלי המספר; המספר מופיע רק בשורת "לידיעתך בלבד". (Task 2)
5. **סגירת טאב באמצע** → מה שכבר נאמר שמור (הלוג נשלח אחרי כל תור, upsert לפי call_id, תורים מתמזגים ולא נדרסים). (Task 1 + Task 4)

---

### Task 1: טבלת השיחות + עזרי Supabase

**Files:**
- Create: `supabase/migrations/20261110_voice_lab_calls.sql`
- Modify: `supabase_db.py` (בסוף הקובץ)
- Test: `tests/voice/test_voicelab_db.py`

**Interfaces:**
- Produces: `voicelab_save(call: dict) -> bool` (upsert לפי `call_id`), `voicelab_list(limit: int = 20) -> list[dict]` (החדש ראשון).

- [ ] **Step 1: מיגרציה** — טבלה `voice_lab_calls`: `id uuid pk default gen_random_uuid()`, `office_id uuid not null`, `call_id text unique not null`, `created_at timestamptz default now()`, `updated_at timestamptz default now()`, `lead_key text`, `address text`, `owner text`, `agent text`, `model text`, `turns jsonb default '[]'`, `outcome text`, `outcome_when text`, `note text`, `seconds int`. `enable row level security` בלי policies (שרת בלבד, כמו invoices). אינדקס `(office_id, created_at desc)`.
- [ ] **Step 2: בדיקה נכשלת** — עם `requests` מזויף (דפוס tests/props): `voicelab_save({"call_id":"c1","turns":[...]})` שולח POST ל-`/rest/v1/voice_lab_calls` עם `on_conflict=call_id` ו-`Prefer: resolution=merge-duplicates`, `office_id`=SB_OFFICE_ID, ו-`updated_at` מוגדר; בלי `call_id` → False בלי רשת; `enabled()` False → False; שגיאת HTTP → False (לא זורק). `voicelab_list(5)` שולח `order=created_at.desc&limit=5` ומחזיר את הרשימה; כשל → `[]`.
- [ ] **Step 3: הרצה — FAIL** `python3 tests/voice/test_voicelab_db.py`
- [ ] **Step 4: מימוש** בדפוס `signdoc_save`; מפתחות שלא ברשימת העמודות נזרקים.
- [ ] **Step 5: הרצה — PASS**, ‏`python3 -c "import ast;ast.parse(open('supabase_db.py').read())"`
- [ ] **Step 6: Commit** `feat(voice): טבלת שיחות המעבדה + עזרי Supabase`

### Task 2: לוגיקה טהורה — עובדות, הנחיות, כלים

**Files:**
- Create: `voice_agent.py` (פונקציות מודול בלבד בשלב זה)
- Test: `tests/voice/test_voice_logic.py`

**Interfaces:**
- Produces:
  - `street_name(addr: str) -> str` — רחוב בלי מספר בית ("עוזי חיטמן 19" → "עוזי חיטמן"; "הרצל 5א" → "הרצל").
  - `street_deals(rows: list[dict], street: str, city: str, now: float, days: int = 730) -> int` — שורות `active_rows` (מ-deals_history) שבהן `street_name(r["street"])` == `street_name(street)` (נרמול רווחים/גרשיים/"רח'"), עיר תואמת (`קריית`→`קרית`, ריק בשורה = תואם), ו-`deal_date` (ISO) בתוך `days` אחרונים. מחזיר מספר עסקאות ייחודיות לפי `(deal_date, street)` (קונה+מוכר באותה עסקה = 1).
  - `build_instructions(lead: dict, agent: str, office: str, facts: dict, slots: list[dict]) -> str`
  - `TOOLS: list[dict]` — הגדרות function לסשן Realtime.
  - `session_payload(instr: str, model: str, voice: str) -> dict` — גוף ל-`client_secrets`.

- [ ] **Step 1: בדיקות נכשלות** (`lead` לדוגמה: `{"address":"עוזי חיטמן 19","city":"קרית ביאליק","nb":"נאות אפק","rooms":"5","price":"2,290,000","owner":"דני כהן","desc":"דירה מרווחת..."}`, `facts={"buyers":7,"deals":4}`, `slots=[{"label":"מחר 10:00"},{"label":"חמישי 17:00"}]`):
  - `street_name("עוזי חיטמן 19") == "עוזי חיטמן"`, `street_name("רח' הרצל 5א") == "הרצל"`.
  - `street_deals`: 2 שורות של אותה עסקה (אותו תאריך, מוכר+קונה) + שורה מלפני 3 שנים + שורה בעיר אחרת + שורה עם `missing_since` → `1`.
  - ההנחיות מכילות: `"העוזרת הדיגיטלית של רועי לוי"`, שם המשרד, `"עוזי חיטמן"`, `"7 קונים"`, `"4 עסקאות"`, `"מחר 10:00"`, `"חמישי 17:00"`, `"דני"`.
  - שורת הפתיחה בהנחיות (הקטע שמסומן `פתיחה:`) **לא** מכילה `"19"`.
  - עם `facts={"buyers":0,"deals":0}` ו-`owner=""`: אין `"0 קונים"`, אין `"0 עסקאות"`, אין `"דני"`; כן יש הוראה לא להמציא מספרים.
  - שמות הכלים ב-`TOOLS`: `{"get_slots","get_area_facts","record_outcome","end_call"}`; ל-`record_outcome` פרמטר `outcome` עם enum `["meet","back","no"]` ו-`when`,`note` אופציונליים.
  - `session_payload(...)["session"]`: `type=="realtime"`, `model` כפי שהועבר, `audio.output.voice` כפי שהועבר, `audio.input.transcription == {"model":"gpt-4o-transcribe","language":"he"}`, `tools == TOOLS`, `instructions` כפי שהועבר.
- [ ] **Step 2: הרצה — FAIL**
- [ ] **Step 3: מימוש.** תוכן ההנחיות (עברית, מחרוזת אחת) — חייב לכסות את 6 שלבי התסריט מהספק, את כללי האנטי-מטרות (גלוי שדיגיטלית; לא לחץ מעבר לסירוב שני; לא להמציא נתונים; לא הערכת שווי בטלפון; עמלה — "<סוכן> יפרט בפגישה"; מספר בית לא נאמר; מחיר רק אם שואלים), את פירוט ההתנגדויות הידועות (מטפל לבד/מתווך, רק השכרה, גר רחוק, כבר היו מהמשרד, מה העמלה), את כללי המגדר (גוף ראשון נקבה; לשון רבים לבעלים אלא אם השם חד-משמעי), "משפטים קצרים, שאלה אחת בכל פעם", ובסוף שיחה — לקרוא `record_outcome` ואז `end_call`. משפט פתיחה מילולי: `שלום, כאן העוזרת הדיגיטלית של {agent} מ{office}. ראינו את הדירה שפרסמתם ב{street}. יש לכם דקה?` נתונים שאינם חיוביים (0/None) לא נכנסים כלל.
- [ ] **Step 4: הרצה — PASS** + ast.
- [ ] **Step 5: Commit** `feat(voice): הנחיות התסריט ועובדות הנכס`

### Task 3: ראוטים בשרת + חשיפת הלידים מהחייגן

**Files:**
- Modify: `dialer.py` (בתוך `register`, אחרי `_cands`): `G["_dialer_lab_leads"] = _lab_leads`
- Modify: `voice_agent.py` — `register(app, G)`
- Modify: `app.py:14208-14211` — אחרי הרשמת dialer, אותו דפוס try/except ל-`voice_agent.register(app, globals())`
- Test: `tests/voice/test_voice_routes.py`

**Interfaces:**
- Consumes: Task 1 `voicelab_save`, `voicelab_list` (דרך `G["supabase_db"]` או import ישיר של `supabase_db`); Task 2 הכל.
- Produces (dialer): `_lab_leads(n: int = 10) -> list[dict]` — `_cands()` ממוין לפי `score` יורד, `n` ראשונים, לכל אחד `agents = rank_agents(c["city"], c["nb"], counts, [], _roster(), canon)`; עותקים (לא משנה את המטמון).
- Produces (routes, כולם בודקים dev):
  - `GET /v2/voice` → `V2_VOICE_HTML` (Task 4; בשלב זה מחרוזת placeholder).
  - `GET /v2/api/voice/leads` → `{ok, allowed:true, configured: bool(OPENAI_API_KEY), office, leads:[{key,address,city,nb,rooms,price,owner,buyers,agents:[{name,why}]}], agents:[שמות roster]}`.
  - `POST /v2/api/voice/session {key, agent}` → מאתר את הליד, `facts={"buyers":lead.buyers, "deals":street_deals(G["_deal_history_linked"](), ...)}`, `slots = free_slots(now_il, G["_dialer_busy"](agent))[:2]` (חשיפה נוספת מ-dialer: `G["_dialer_busy"]=_busy`), בונה הנחיות, `POST https://api.openai.com/v1/realtime/client_secrets` עם `Authorization: Bearer OPENAI_API_KEY`, timeout 15. הצלחה → `call_id = uuid4().hex`, `voicelab_save({call_id, lead_key, address, owner, agent, model})`, תשובה `{ok, call_id, secret: <value>, model, facts, slots}`. בלי מפתח → `{ok:false, reason:"not_configured"}`; ליד לא נמצא → 404 `reason:"lead"`; OpenAI לא 200 → `{ok:false, reason:"openai", status}` בלי שמירה.
  - `POST /v2/api/voice/log {call_id, turns, outcome?, when?, note?, seconds?}` → `voicelab_save` (turns עד 200, כל טקסט עד 2000 תווים; outcome רק מ-`meet/back/no`).
  - `GET /v2/api/voice/calls` → `{ok, calls: voicelab_list(20)}`.
- [ ] **Step 1: בדיקות נכשלות** — Flask עם G מזויף (דפוס `tests/dialer/test_dialer.py` AutoG) ו-`requests.post` מזויף ל-OpenAI:
  - סוכן רגיל → `allowed:false` בכל הראוטים; בלי כניסה → 401.
  - בלי `OPENAI_API_KEY` → `/leads` מחזיר `configured:false`; `/session` מחזיר `reason:"not_configured"` ולא קורא ל-requests.
  - עם מפתח: `/session` שולח ל-`.../v1/realtime/client_secrets` עם ה-Bearer, הגוף `session.model == VOICE_MODEL`, התשובה מכילה `secret` מה-mock ולא מכילה את המפתח הקבוע בשום שדה; `voicelab_save` נקרא פעם אחת.
  - OpenAI מחזיר 429 → `reason:"openai"`, `status:429`, `voicelab_save` לא נקרא.
  - `/log` עם `outcome:"hack"` → נשמר בלי outcome.
  - `_lab_leads(2)` מחזיר 2 ממוינים לפי ציון ולא משנה את `_CACHE`.
- [ ] **Step 2: הרצה — FAIL**
- [ ] **Step 3: מימוש**
- [ ] **Step 4: הרצה — PASS**, + `python3 tests/dialer/test_dialer.py` עדיין ירוק, + ast על app.py/dialer.py/voice_agent.py.
- [ ] **Step 5: Commit** `feat(voice): ראוטי המעבדה + חשיפת לידים מהחייגן`

### Task 4: מסך המעבדה (`V2_VOICE_HTML`)

**Files:**
- Modify: `voice_agent.py` — `V2_VOICE_HTML`
- Modify: `effie_v2.py` — פריט "מעבדת קול" בתפריט הצד בבית, רק כש-`whoami.dev`
- Test: `tests/voice/test_voice_page.js` (node + jsdom/vm על הסקריפט המחולץ, דפוס tests/dialer/*.js)

**Interfaces:**
- Consumes: הראוטים של Task 3.
- Produces: פונקציות JS גלובליות לבדיקה: `voiceStart(key, agent)`, `onEvent(ev)`, `toolReply(name, args)`, `flushLog()`.

מבנה: hero נייבי "מעבדת קול" + תג זהב "בטא"; רשימת 10 לידים (כרטיס: כתובת, עיר, חדרים, מחיר, בעלים, "N קונים מתאימים", בורר סוכן — ברירת מחדל המומלץ); כפתור זהב "התחל שיחה"; בזמן שיחה — מצב (מתחבר / מדברת / מקשיבה), תמלול חי (בועות: העוזרת / אתה), כפתור משני "סיים שיחה"; "שיחות קודמות" (תוצאה, משך, פתיחת תמלול). מצבי ריק מעוצבים: לא מוגדר, אין לידים, מיקרופון נדחה ("צריך לאשר מיקרופון בדפדפן"), בתוך אפליקציית אפי (`window.Capacitor`) → "פתח בדפדפן" עם הקישור.

זרימת WebRTC (סדר מחייב): `getUserMedia({audio:true})` → POST `/v2/api/voice/session` → `RTCPeerConnection`, track מקומי, `<audio autoplay>` לרמוט, data channel `oai-events` → `createOffer` → `fetch("https://api.openai.com/v1/realtime/calls?model="+model, {method:"POST", body: offer.sdp, headers:{Authorization:"Bearer "+secret,"Content-Type":"application/sdp"}})` → `setRemoteDescription({type:"answer", sdp})` → בפתיחת הערוץ: `response.create` כדי שהעוזרת תפתח ראשונה.

אירועים: `conversation.item.input_audio_transcription.completed` → תור "אתה"; `response.output_audio_transcript.done` → תור "העוזרת"; `response.function_call_arguments.done` → `toolReply`: `get_slots` → `{slots}` מתשובת `/session`; `get_area_facts` → `{facts}`; `record_outcome` → שומר מקומית + `flushLog()` + `{ok:true}`; `end_call` → סגירה אחרי 1.5ש'. תשובה לכלי: `conversation.item.create {item:{type:"function_call_output", call_id, output: JSON}}` ואז `response.create` (חוץ מ-end_call). `flushLog()` נקרא אחרי כל תור ובסיום (עם `seconds`); ב-`pagehide` — `navigator.sendBeacon`.

- [ ] **Step 1: בדיקות נכשלות** (node, `fetch`/`RTCPeerConnection` מזויפים):
  - `onEvent` עם אירוע תמלול משתמש + אירוע תמלול עוזרת → שני תורים בסדר, ו-`flushLog` שלח POST ל-`/v2/api/voice/log` עם שניהם.
  - `toolReply("get_slots")` מחזיר את ה-slots מהסשן; `toolReply("record_outcome",{outcome:"meet",when:"מחר 10:00"})` שולח log עם `outcome:"meet"`.
  - תשובת `/session` עם `reason:"not_configured"` → מוצג מצב "לא מוגדר", `RTCPeerConnection` לא נוצר.
  - `window.Capacitor` קיים → מוצג "פתח בדפדפן", `getUserMedia` לא נקרא.
  - ה-SDP נשלח ל-`api.openai.com/v1/realtime/calls?model=` עם ה-Bearer הזמני מהסשן.
- [ ] **Step 2: הרצה — FAIL**
- [ ] **Step 3: מימוש** + פריט התפריט ב-effie_v2.
- [ ] **Step 4: PASS** + `node --check` על הסקריפט המחולץ + ast על effie_v2.py + צילום מסך מקומי בגודל טלפון (נתוני דוגמה).
- [ ] **Step 5: Commit** `feat(voice): מסך מעבדת הקול`

### Task 5: אימות וסגירה

- [ ] כל `tests/voice/*` + `tests/dialer/*` ירוקים; האפליקציה עולה (`import app`) וספירת ראוטים עלתה ב-5.
- [ ] רשומה ביומן ההחלטות ב-`remax-family/CLAUDE.md`.
- [ ] צעדי אייל: SQL של Task 1 ב-SQL Editor → push+deploy → `/v2/voice` ב-Safari בטלפון.
