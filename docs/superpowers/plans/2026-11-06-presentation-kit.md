# תיק פרזנטציה לבעל נכס — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sales kit an agent requests from Effie for a property owner before a listing meeting. It is built in seconds from Effie data, approved by the office owner through a WhatsApp link, and sent by the agent from their own phone. The owner opens it on a tracked view page with a PDF download.

**Architecture:**
- Two pure modules:
  - `kit_core.py` builds the snapshot, the counts, the copy and the state machine.
  - `kit_render.py` draws 1080×1920 pages with Pillow and joins them into a PDF.
- A Flask module `kit.py` with `register(app, G)`, in the `prop_share` / `social_video` pattern. It holds the routes, the approval page, the public view page and the review-send tick.
- One Supabase table, `presentation_kits`, reached through new `kit_*` functions in `supabase_db.py`.
- Client entry points in `effie_v2.py`:
  - a button on the נכס נולד card
  - a button on the meetings screen
  - a new `/v2/kits` screen
  - a drawer item
  - an admin card

**Tech Stack:** Flask, Pillow 10.4 (with `fonts/Heebo-VF.ttf` via `set_variation_by_axes`), python-bidi, Supabase REST, and 360dialog through `G["send_text"]`.

**Spec:** `docs/superpowers/specs/2026-11-06-presentation-kit-design.md` (approved by Eyal on 06/11). Read it first: page contents are in section 4, and the builder decisions are in sections 8–9.

## Global Constraints
- **No AI calls anywhere in the kit.** Every number and every piece of copy comes from Effie data or fixed text.
- **White-label.**
  - The office name comes from `G["_load_config"]().get("v2_office",{}).get("name")`. Don't use `G["_office_name"]`, which is not in G.
  - The logo is `social_video._logo_path()`.
  - The word "אפי" never appears in the kit.
- **Palette** (closed, nothing else):
  - navy `#1E3A5F`
  - cream `#F2EFE7`
  - gold `#C29435` / `#E4C56B`
  - text on gold `#231700`
  - green `#157A43` (phone line only)
  - muted `#6B7280` / `#5B6472`
  - white cards with 32px radius at 1080 scale
  - Heebo, RTL, no emojis
- **Privacy.**
  - No house number anywhere in the kit. Street name and city only: strip the number with the same rule as `social_publish.soc_scrub_house`.
  - No buyer names or phones. Counts only.
- **Fixed claims**, editable in admin, with these defaults:
  - `"מעל 70% מהעסקאות שלנו נסגרות בשיתוף פעולה בין סוכני <office>"`
  - `"מקום 2 בעסקאות ברשת רימקס ישראל · מתחילת 2026, נכון ל-01/11/2026"`
  - Google `4.9`, reviews `118` (rendered "מעל 118 ביקורות בגוגל"), link = the Bialik profile URL, which Eyal pastes in admin. With an empty link, no link is shown.
- **The agent page never shows the agent's own deal count or tenure.**
- **Statuses:** `pending → approved | rejected | expired`; `approved → sent`. A pending kit older than `APPROVE_H = 48` hours is `expired`. Expiry is computed on read, with no job.
- **Nothing reaches the owner unless the status is `approved` or `sent`.**
- **Commits:** local only, and only your own files: `git add <paths>`. `git pull --ff-only` before starting. Other chats have uncommitted work in `app.py` / `effie_v2.py`, so check `git diff --cached` before every commit.
- **Tests:** plain-script `ck()` style for routes (copy `tests/social_video/test_routes.py`) and pytest for the pure functions. JS: `node --check` on the extracted script plus node on the real function. There's no `timeout` command on the Mac.

## Review Focus
1. **Owner phone in any format.** `054-444 8065`, `+972544448065` and `544448065` should all give `wa=972544448065`. A manual phone with fewer than 9 digits is rejected with `{"ok":false,"reason":"phone"}`. Test in Task 1.
2. **Agent with no photo, bio, license or review.** Page 2 still renders, with no empty boxes: blocks are hidden and the cover shows the agent's initials. Test in Task 2.
3. **Long Hebrew names and addresses.** Examples: "רחוב שדרות ההסתדרות הציונית העולמית" and a 40-character owner name. They wrap or shrink inside the card and never cross the page edge. Test in Task 2, which measures text boxes against the 1080 width.
4. **`/k/<tok>` for a kit that is pending, rejected, expired or unknown.** It returns a friendly 410 page (cream, office name, "התיק אינו זמין"), never the PDF or the images. Test in Task 4.
5. **Double approve, or approve after reject.** Only the first decision applies, through a conditional PATCH on `status=eq.pending`. The second tap gets "כבר אושר" or "כבר נדחה". Test in Task 4.

---

### Task 1: Data layer and pure core

**Files:**
- Create: `/Users/eyal/Documents/remax-family/supabase/migrations/20261106_presentation_kits.sql` (in the remax-family repo; Eyal runs it)
- Modify: `supabase_db.py` (add a `kit_*` block after the `video_*` block, around line 1741)
- Create: `kit_core.py`
- Test: `tests/kit/test_core.py` (pytest)

**Interfaces:**
- Produces, in the SQL table `presentation_kits`:
  - `id uuid pk default gen_random_uuid()`
  - `office_id uuid not null references offices(id)`
  - `created_at timestamptz default now()`, `updated_at timestamptz`
  - `status text not null`
  - `agent_name text`, `agent_phone text` (last9), `created_by text`, `created_by_phone text`
  - `source text` (`nb` | `meet` | `manual`), `listing_key text`
  - `owner_name`, `owner_phone`, `snapshot jsonb`
  - `review_token text unique`, `view_token text unique`
  - `sent_review_at timestamptz`, `review_due bool default false`
  - `decided_by`, `decided_at`, `reject_reason`, `sent_at`
  - `views jsonb default '{}'`
  - Enable RLS with no policies, following the header style of `20261006_buyer_pages.sql`.
- Produces, in `supabase_db`, each one scoped to `office_id` like `video_*`:
  - `kit_insert(rec: dict) -> dict|None`
  - `kit_update(kid, fields) -> bool`
  - `kit_claim(kid, frm, to, fields) -> bool`
  - `kit_get(kid) -> dict|None`
  - `kit_by_token(col: str, tok: str) -> dict|None`, where `col` is `review_token` or `view_token`
  - `kit_list(agent_phone: str|None, days: int = 90) -> list`, where None means the whole office
- Produces, in `kit_core`:
  - `APPROVE_H = 48`, `MIN_BUYERS = 3`, `BUYER_MIN = 60`
  - `phone9(v) -> str`, which returns the last 9 digits, or '' if there are fewer than 9
  - `wa972(v) -> str`, which returns '972'+phone9, or ''
  - `street_only(street: str) -> str`, which removes the house number. Reuse `social_publish.soc_scrub_house(street, street)` semantics: strip trailing `\d+[א-ת]?(/\d+)?` and `מס'`.
  - `eff_status(rec, now: float) -> str`, which returns `'expired'` when `status=='pending'` and `sent_review_at` is older than `APPROVE_H`
  - `decide(rec, action: str, who: str, now: float) -> tuple[str|None, str]`. The action is `approve` or `reject`. It returns `(new, msg)`, where msg is one of `'אושר' | 'נדחה' | 'כבר אושר' | 'כבר נדחה' | 'פג תוקף'`.
  - `owner_message(snap: dict) -> str`. This is the exact copy from spec §3, without the meeting part when `meet_at` is empty.
  - `file_name(snap) -> str`, which returns `"תיק אישי - <owner>.pdf"`
  - `view_add(views: dict, now: float, step: int = 15) -> dict`. Its keys are `first`, `last`, `opens` and `secs`. A new open is counted when the gap since `last` is more than 1800 seconds. `secs` grows by `step` and is capped at 4 hours in total.
  - `manual_validate(form: dict) -> str|None`. It returns a reason: `'owner' | 'phone' | 'addr' | 'rooms' | 'price'`, or None.

- [ ] **Step 1: Write the failing tests** in `tests/kit/test_core.py`:
  - `phone9("054-444 8065")=="544448065"`, `wa972("+972544448065")=="972544448065"`, `phone9("12345")==""`.
  - `street_only("הנוטר 18")=="הנוטר"`, `street_only("שדרות ההסתדרות 12א")=="שדרות ההסתדרות"`, `street_only("עוזי חיטמן")=="עוזי חיטמן"`.
  - `eff_status({"status":"pending","sent_review_at":<now-49h ISO>}, now)=="expired"`; `approved` stays approved.
  - `decide` from pending/approve gives `("approved","אושר")`; from approved/approve gives `(None,"כבר אושר")`; from expired gives `(None,"פג תוקף")`.
  - `owner_message` with `{"owner_first":"משה","agent":"אוהד לוי","office":"רימקס פמילי","meet_at":"2026-11-11T17:00","street":"הנוטר"}` equals `"שלום משה, כאן אוהד לוי מרימקס פמילי. לקראת הפגישה שלנו ביום ג׳ 11/11 בשעה 17:00 הכנתי לך תיק אישי על הנכס שלך בהנוטר. אשמח שתעיף מבט לפני שנפגש."`. Without `meet_at` it equals `"שלום משה, כאן אוהד לוי מרימקס פמילי. הכנתי לך תיק אישי על הנכס שלך בהנוטר. אשמח שתעיף מבט לפני שנפגש."`.
  - `view_add({}, 1000)` gives `{"first":1000,"last":1000,"opens":1,"secs":15}`. A second call at 1010 gives `opens` 1 and `secs` 30. A call at 1000+1801 gives `opens` 2.
  - `manual_validate({"owner":"משה","phone":"0544448065","addr":"הנוטר 18","city":"קרית ביאליק","rooms":"5","price":"2,350,000"})` is None. Drop `price` and it returns `'price'`.
- [ ] **Step 2: Run** `python3 -m pytest tests/kit/test_core.py -q`. Expected: FAIL with `ModuleNotFoundError: kit_core`.
- [ ] **Step 3: Implement** `kit_core.py`, then the `kit_*` functions in `supabase_db.py` (copy the `_sv_post` / `video_update` / `video_claim` shapes with table `presentation_kits`), then the migration SQL.
- [ ] **Step 4: Run** `python3 -m pytest tests/kit/test_core.py -q` to get PASS, then `python3 -c "import ast;ast.parse(open('supabase_db.py').read())"`.
- [ ] **Step 5: Commit**: `git add kit_core.py supabase_db.py tests/kit/test_core.py`, then `git commit -m "תיק פרזנטציה: שכבת נתונים וליבה"`. In the remax-family repo, commit the migration separately.

### Task 2: Snapshot builder and renderer

**Files:**
- Modify: `kit_core.py` (add the builders)
- Create: `kit_render.py`
- Test: `tests/kit/test_snapshot.py`, `tests/kit/test_render.py` (pytest)

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `office_numbers(G) -> {"years":int,"deals":int,"agents":int,"office":str}`
    - years = current year − 2016
    - deals = the `deal_history_all()` rows that are not `missing_since`, dated from 2016-01-01 up to today, with a side that has no שוכר or משכיר. This is the refamily-site `deals.side_counts` "sale" rule.
    - agents = names in `effie_v2.crm_roster(G)` whose `G["_resolve_roles"]` drole is `agent` for some phone in `G["_phones_for_name"](name)`, and who are not in `G["_coordinators_all"]()`
    - The result is cached with `G["_swr"]("kit:office", 1800, …)`.
  - `buyers_block(G, listing: dict) -> {"mode":"match"|"city","n":int,"lines":[[label,int],…],"city":str}`
    - `listing` is office-shaped: `עיר / ישוב, שכונה, חדרים, מחיר, סוג נכס`.
    - Match with the same parsed/area/threshold as `dialer.py:284-360`: `effie_v2.bai_score`, `BUYER_MIN = 60`, skipping closed and frozen buyers via `effie_v2.bstat_of`.
    - Lines, each dropped when 0: `"תקציב של <price rounded down to 100K> ומעלה"`, `"מחפשים <rooms> חדרים ומעלה"`, `"מחפשים ב<city>"`.
    - With fewer than `MIN_BUYERS` matches, return `mode:"city"`. `n` is then the number of active buyers whose search and summary text contains the city (normalise קריית→קרית), and `lines` is empty.
  - `agent_block(G, name, phone9) -> {"name","first","license","bio","review":{"text","by"}|None,"photo":path|None,"site_url":str}`
    - License: `cfg["v2_licenses"]`, falling back to `fetch_agents_full`.
    - Bio: `site_api.SettingsStore(G["_sbdb"]).all()`, kind=`agent`.
    - Review: `site_api.reviews_active(rows)`, first the agent's own, otherwise the office's newest, otherwise None.
    - Photo: `social_video._agent_photo`-style lookup.
    - `site_url`: `os.environ.get("SITE_PUBLIC_URL","https://refamily.co.il") + "/צוות/" + site_slug(name)`, with `site_slug` copied verbatim from `refamily-site/refsite/textutil.py:18-20`. It is empty when the agent's `website_settings` agent row has `shown == False`.
  - `kit_settings(cfg) -> dict`, which reads `cfg.get("v2_kit")` merged over `KIT_DEFAULTS`. `KIT_DEFAULTS` holds the exact strings from Global Constraints, under the keys `coop`, `rank`, `g_rating`, `g_count`, `g_url`.
  - `build_snapshot(G, src: dict) -> dict`
    - `src` keys: `owner, phone, street, city, rooms, price, meet_at, agent_name, agent_phone`.
    - It returns everything the renderer needs: `owner, owner_first, street` (via `street_only`), `city, rooms, price` (formatted with commas), `meet_at, agent:{…agent_block}, office:{…office_numbers}, buyers:{…}, claims:{…kit_settings}, made_at`.
    - The kit is rendered from this snapshot only, so what Eyal approved is what the owner sees.
- In `kit_render`:
  - `render_pages(snap: dict) -> list[PIL.Image]`: 6 RGB images at 1080×1920, in the order cover, agent, power, plan, buyers, next step, with content as in spec §4. The CMA page is left out until the CMA exists.
  - `render_pdf(imgs) -> bytes`, with `imgs[0].save(buf,"PDF",save_all=True,append_images=imgs[1:],resolution=150)`.
  - `wrap_rtl(draw, text, font, width) -> list[str]`, which splits on words, measures with `textlength`, and runs `_rtl` on each line.
  - Fonts and helpers are adapted from `report_story.py` (`_font`, `_bidi`, `_rr`).

- [ ] **Step 1: Write the failing tests.**
  - `test_snapshot.py`, with a fake G (in-memory buyers, `deal_history_all`, cfg, `_swr=lambda k,t,f: f()`):
    - `office_numbers` counts 3 sale sides and skips a rent side, a pre-2016 row, a future row and a `missing_since` row.
    - `buyers_block` gives `mode=="match"` and n 4 for 4 matching buyers. With 2 matching buyers it gives `mode=="city"` and n equal to the active buyers in that city (a frozen buyer is excluded).
    - `agent_block` with no bio, license or review gives `bio==""`, `review is None` and `photo is None`.
    - `build_snapshot(...)["street"]=="הנוטר"` from `"הנוטר 18"`.
    - The claims defaults equal the Global Constraints strings.
  - `test_render.py`:
    - `render_pages(sample)` gives 6 images, each `(1080,1920)`.
    - `render_pdf(...)[:4]==b"%PDF"`.
    - In `wrap_rtl` on the 40-character owner name and the long street, every line's `textlength` is at most the card width (1080 − 2×72).
    - A snapshot with an empty agent block still renders 6 pages without exceptions.
    - Save `/tmp/kit_p*.png` for a visual check.
- [ ] **Step 2: Run** `python3 -m pytest tests/kit -q`. Expected: FAIL (missing functions).
- [ ] **Step 3: Implement** the builders in `kit_core.py` and all of `kit_render.py`.
- [ ] **Step 4: Run** `python3 -m pytest tests/kit -q`. Expected: PASS. Open the 6 PNGs and compare them with the approved mockup (v2, "שיווקית"): dark cover, agent page, power page, plan, buyers, next step.
- [ ] **Step 5: Commit**: `git add kit_core.py kit_render.py tests/kit/test_snapshot.py tests/kit/test_render.py`, then `git commit -m "תיק פרזנטציה: צילום נתונים ורינדור עמודים"`.

### Task 3: Agent routes (create, list, resend, sent) and settings

**Files:**
- Create: `kit.py`
- Modify: `app.py` (add a register block after `social_video`, around line 14087: `try: import kit as _kit; _kit.register(app, globals()) except Exception as e: log.warning(...)`)
- Test: `tests/kit/test_routes.py` (plain-script `ck()`; fakes copied from `tests/social_video/_fakes.py`, plus an in-memory `SBK` with the `kit_*` functions)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces routes. All of them use `s = G["_web_auth"]()` and return 401 if it is empty.
  - `POST /v2/api/kit/create` takes JSON `{"source":"nb"|"meet"|"manual","key"?:str,"skey"?:str,"owner"?,"phone"?,"street"?,"city"?,"rooms"?,"price"?,"meet_at"?,"agent"?:str}` and returns `{"ok":true,"id","status":"pending"}` or `{"ok":false,"reason"}`.
    - `nb`: the row comes from `G["fetch_newborn"]()` where `G["_nb_key"](r)==key`. Fields come from the raw keys `שם בעל הנכס`, `טלפון בעל הנכס-`/`טלפון בעל הנכס`, `רחוב1`/`רחוב`, `עיר`, `חדרים`, `מחיר`. A missing owner or phone gives `reason:"owner"`/`"phone"`.
    - `meet`: the record is `cfg["nbStatus"][skey]`, using its `pkey` / `owner` / `ophone` / `addr` / `price`, with `meet_at=date`. Look up the listing by `pkey` for rooms and city.
    - `manual`: `manual_validate`.
    - `agent`: only when `s["role"]` is `admin` or `coordinator` may it name another agent. Otherwise it is the session agent.
    - The route inserts a `pending` row with fresh `review_token` / `view_token` from `secrets.token_urlsafe(16)`, then calls `send_review(G, rec, base)` from Task 4 in a thread, then `_log_activity(..., "תיק פרזנטציה — נשלח לאישור", "<owner> · <street>")`.
  - `GET /v2/api/kit/mine` returns `{"ok":true,"kits":[{"id","status"` (via `eff_status`)`,"owner","street","city","created_at","reject_reason","views":{opens,secs,last},"wa","text","url"}]}`.
    - The list holds the session agent's kits; an admin gets the whole office with `?all=1`.
    - `wa`, `text` and `url` are present only when the status is `approved` or `sent`. `url = <base>/k/<view_token>`, and `text = owner_message(snap) + "\n" + url`.
  - `POST /v2/api/kit/resend {id}` is allowed for the owning agent or an admin, only on `rejected` or `expired`. It rebuilds the snapshot, sets `pending`, clears `reject_reason`, sets new tokens, and sends for review again.
  - `POST /v2/api/kit/sent {id}`: approved becomes sent, with `sent_at`, and logs `"תיק פרזנטציה — נשלח לבעל הנכס"`.
  - `GET` and `POST /v2/api/kit/settings` are for the owner only (`s.dev or G["_is_dev"](phone)`, as in `dialer.py`). The body holds `coop, rank, g_rating, g_count, g_url`. Values are trimmed, `g_url` must start with `https://`, and saving goes through `G["_config_mutate"]` into `cfg["v2_kit"]`, checking `ok[0]`. The change is logged.
  - `base` = `os.environ.get("APP_BASE_URL","https://remax-bot.onrender.com")`.

- [ ] **Step 1: Write the failing tests** in `test_routes.py`:
  - Unauthenticated requests get 401.
  - `create` with `source=nb` and a fake row gives pending, one inserted row, the review sent once (patch `kit.send_review`), and one activity entry.
  - `create` with a manual body that has no price gives `reason=="price"`.
  - An agent cannot set `agent` to someone else: the row's `agent_name` stays the session's. A coordinator can.
  - `mine` for a pending kit has no `wa` or `url`. After the fake status is set to approved, `wa=="972544448065"` and `url` ends with `/k/<view_token>`.
  - `resend` on approved gives `ok false`; on rejected it gives pending, with a new `review_token` different from the old one.
  - `settings` POST by an agent gives 403. By the owner it persists into `cfg["v2_kit"]`, and a `g_url` of `http://x` gives `ok false`.
- [ ] **Step 2: Run** `python3 tests/kit/test_routes.py`. Expected: FAIL (no `kit` module).
- [ ] **Step 3: Implement** `kit.py` with `register(app, G)` and the app.py register block.
- [ ] **Step 4: Run** `python3 tests/kit/test_routes.py` and `python3 -m pytest tests/kit -q`, both PASS. Then `python3 -c "import ast;[ast.parse(open(f).read()) for f in ('app.py','kit.py')]"`. Check route binding the way the 16f7d7f lesson requires: with `app.view_functions`, each new route maps to the intended function name.
- [ ] **Step 5: Commit**: `git add kit.py tests/kit/test_routes.py` and `git add -p app.py` (only your register hunk), then `git commit -m "תיק פרזנטציה: ראוטים לסוכן והגדרות"`.

### Task 4: Approval and the public view page

**Files:**
- Modify: `kit.py`
- Test: `tests/kit/test_review_view.py` (plain-script)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `send_review(G, rec, base) -> bool`.
    - Approver: `os.environ.get("KIT_APPROVER")` or the first of `sorted(G["DEV_PHONES"])`, as last9, sent to "972…".
    - If `G["_quiet_hours"]()` or `G["_shabbat_quiet_now"]()`: `kit_update(id, {"review_due": True})` and return False.
    - Otherwise: `G["send_text"](to, "תיק פרזנטציה חדש לאישור\n<agent> · <owner> · <street>, <city>\nלצפייה ולאישור: <base>/v2/kit/review/<review_token>")`, then on success `kit_update(id, {"sent_review_at": now_iso, "review_due": False})`.
    - Note that `send_text` switches to the family_update template on its own outside the 24-hour window.
  - `_kit_tick(G)`, started once from `@app.before_request` (the 15/09 lesson): a daemon thread that every 600 seconds sends `review_due` kits that are still pending.
  - `GET /v2/kit/review/<tok>`. The token must match `[A-Za-z0-9_-]{2,64}` and be found by `kit_by_token("review_token", tok)`. It returns an HTML page with:
    - the 6 page images
    - "אשר ושלח לסוכן" (blue), "דחה" (white with a border), and a reason textarea, optional, up to 300 characters
    - the status line when the kit is already decided
  - `POST /v2/kit/review/<tok>` takes `{"action":"approve"|"reject","reason"?}`. It runs `decide`, then `kit_claim(id,"pending",new,{decided_by,decided_at,reject_reason})`, and returns the msg as text/plain. A lost claim reloads and returns "כבר אושר" or "כבר נדחה". The decision is logged: `"תיק פרזנטציה — אושר"` / `"— נדחה"`.
  - `GET /v2/kit/review/<tok>/p<n>.jpg` and `GET /k/<vtok>/p<n>.jpg` return JPEG q85, n from 1 to 6.
    - They are rendered from the snapshot and cached in memory, keyed `(id, updated_at)`, holding at most 20 kits.
    - The `/k/` variant requires `eff_status` to be approved or sent.
  - `GET /k/<vtok>` is the owner view page.
    - For approved or sent: cream background, the 6 images stacked full width, then a link bar:
      - "הורד כ-PDF" (`/k/<vtok>.pdf`)
      - "לביקורות בגוגל" (only if `g_url`)
      - "לאתר המשרד"
      - "לעמוד של <agent> באתר" (only if `site_url`)
      - "וואטסאפ ל<agent>" (green)
    - The images carry no links, which is why the bar exists.
    - The heartbeat script is `setInterval(p,15000)` plus one after 2 seconds. It is skipped when `document.visibilityState==='hidden'`, and it posts to `/k/<vtok>/ping`.
    - Otherwise: 410, with a cream page showing the office name and "התיק אינו זמין".
    - Headers: `Cache-Control: no-store`, `X-Robots-Tag: noindex`, as in `_bp_resp`.
  - `POST /k/<vtok>/ping`: only for approved or sent. It runs `kit_update(id, {"views": view_add(rec["views"], now)})`, rate-limited to one per 10 seconds per token in memory, and returns 204.
  - `GET /k/<vtok>.pdf` returns `render_pdf(...)` with `Content-Disposition: attachment; filename*=UTF-8''<quoted file_name>`.

- [ ] **Step 1: Write the failing tests** in `test_review_view.py`:
  - In quiet hours, `send_review` sets `review_due` and does not call `send_text`. Otherwise the text contains `/v2/kit/review/<tok>`.
  - Review GET with a bad token gives 404; with a good token, 200 and 6 `<img`.
  - POST approve gives "אושר" and the status approved; a second approve gives "כבר אושר"; reject after approve gives "כבר אושר".
  - Reject with a reason stores `reject_reason`.
  - An expired kit (`sent_review_at` 49 hours ago): approve gives "פג תוקף".
  - `/k/<vtok>` for pending, rejected, expired and an unknown token: each is 410, has no `<img`, and has the header `X-Robots-Tag: noindex`.
  - For approved it is 200 with 6 images and a PDF link. The Google link is absent when `g_url` is empty.
  - `/k/<vtok>.pdf` starts with `%PDF` when approved and is 410 when pending.
  - Ping twice at the same instant leaves `views.opens==1`; the second call is rate-limited.
  - Extract the view page's inline script and run `node --check` on it.
- [ ] **Step 2: Run** `python3 tests/kit/test_review_view.py`. Expected: FAIL.
- [ ] **Step 3: Implement** in `kit.py`.
- [ ] **Step 4: Run** `python3 tests/kit/test_review_view.py`, `python3 tests/kit/test_routes.py` and `python3 -m pytest tests/kit -q`. All PASS.
- [ ] **Step 5: Commit**: `git add kit.py tests/kit/test_review_view.py`, then `git commit -m "תיק פרזנטציה: אישור, דף צפייה ומעקב"`.

### Task 5: Client — entry points, `/v2/kits` screen, drawer, admin card

**Files:**
- Modify: `effie_v2.py`:
  - `V2_NB_KIT` `stActs` row, around line 6191
  - `V2_MEETS_HTML` `itemRow`, around line 10595
  - new `V2_KITS_HTML` and its route `/v2/kits` (served through `_page` like `/v2/meets`)
  - `V2_HOME_HTML` drawer, around line 1686
  - `/v2/admin` card next to `dlrCard`, around line 2791, with its JS around line 3112
- Test: `tests/kit/test_client.js` (node), plus `tests/test_home_menu.py` (existing) must stay green

**Interfaces:**
- Consumes: the Task 3 routes.
- Produces:
  - **NB card:** a button `class="s"` labeled "תיק לפני פגישה", calling `kitFromNb(i)`. It POSTs `{source:"nb",key:nbKitRows()[i].key}`, then shows the toast "התיק בהכנה · ממתין לאישור". On `reason` it shows a toast: `owner`/`phone` gives "חסרים שם או טלפון של בעל הנכס — פתח תיק ידני".
  - **Meetings screen:** a `.sq` button placed before delete, calling `kitFromMeet(i)` with `{source:"meet",skey:MEETS[i].skey}`. It is shown only when the skey does not start with `manual:`.
  - **`/v2/kits` screen**, with the header "תיקי פרזנטציה":
    - The list from `/v2/api/kit/mine`. Each card shows owner · street, city, and a status chip:
      - "בהכנה" (gold-text chip)
      - "מוכן לשליחה" (blue)
      - "נדחה · <reason>"
      - "פג תוקף"
      - "נשלח"
    - A views line on approved and sent cards: "נפתח N פעמים · M דק' · לאחרונה DD/MM HH:MM", or "עוד לא נפתח".
    - "שלח לבעל הנכס" (green), which runs `window.open('https://wa.me/'+k.wa+'?text='+encodeURIComponent(k.text),'_blank')` and then POSTs `/v2/api/kit/sent`. V2_BOOST already routes desktop users to WhatsApp Web.
    - "שלח שוב לאישור" on rejected and expired cards.
    - "תיק חדש (ידני)" opens a sheet with all fields at 16px and required: owner, phone (`type=tel`), street + number, city, rooms, price (format commas while typing, as `fmtPrice` does in /v2/sign), plus an optional meeting date and time. An admin or coordinator also gets an agent picker.
    - Inline errors sit next to the field, mapped from `reason`.
    - Empty state: a gold circle icon, "עוד אין תיקים", "פתח תיק מכרטיס בנכס נולד או ידנית", and a CTA.
  - **Drawer item:** `menuKits` → `/v2/kits` ("תיקי פרזנטציה"), shown for every role.
  - **Admin card** `kitCard`, "תיק פרזנטציה — נתונים קבועים". It has five fields (coop, rank, Google rating, review count, Google link). `kitLoad()` is added to `boot()` and `kitSave()` POSTs `/v2/api/kit/settings` and shows the toast "נשמר".

- [ ] **Step 1: Write the failing test** `tests/kit/test_client.js`. Extract the real functions from `effie_v2.py` the same way `tests/propshare` / `tests/newborn` JS tests do, then check:
  - `kitStatusChip({status:"pending"})` contains "בהכנה". "rejected" with reason "מחיר לא נכון" contains both "נדחה" and the reason.
  - `kitViews({opens:2,secs:150,last:<ts>})` gives "נפתח 2 פעמים · 3 דק' · …". For `{}` it gives "עוד לא נפתח".
  - `kitSendBtn` shows only for approved and sent.
  - `kitManualErr("price")` maps to the price field.
- [ ] **Step 2: Run** `node tests/kit/test_client.js`. Expected: FAIL.
- [ ] **Step 3: Implement** the client pieces in `effie_v2.py`.
- [ ] **Step 4: Run** the checks, which must all PASS:
  - `node tests/kit/test_client.js`
  - `node --check` on each modified inline script: NB kit, meets, kits, home, admin
  - `python3 -m pytest tests/test_home_menu.py -q`
  - `python3 -c "import ast;ast.parse(open('effie_v2.py').read())"`
  - Then start the app locally with fake data and screenshot `/v2/kits` at phone width (375).
- [ ] **Step 5: Commit**: `git add -p effie_v2.py` (only your hunks) and `git add tests/kit/test_client.js`, then `git commit -m "תיק פרזנטציה: כפתורים, מסך תיקים, תפריט וכרטיס ניהול"`.

### Task 6: Whole-branch check and handoff note
- [ ] Run `python3 -m pytest tests/kit -q`, `python3 tests/kit/test_routes.py`, `python3 tests/kit/test_review_view.py`, `node tests/kit/test_client.js` and the existing `tests/newborn`, `tests/social_video` and `tests/test_home_menu.py`. All green.
- [ ] Add a decision-log entry at the top of "יומן החלטות" in `/Users/eyal/Documents/remax-family/CLAUDE.md`, with the remax-bot commits and "ממתין ל-SQL+push+deploy". Eyal's steps go in it:
  1. Run `20261106_presentation_kits.sql`.
  2. Push and deploy.
  3. In admin, paste the Google link.
  4. Test: a kit from a נכס נולד card, approve it from WhatsApp, send it, open the link on a phone, and see "נפתח 1 פעמים".
- [ ] Commit in remax-family: `git add CLAUDE.md`, then `git commit -m "יומן: תיק פרזנטציה נבנה"`.
