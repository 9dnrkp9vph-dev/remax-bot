# היעדים שלי להיום — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the auto-opening hot-properties story's first card with each person's daily goals (auto-counted), add a `/v2/goals` screen, per-agent targets editable by managers, a TV goals card and a CRM dashboard table.

**Architecture:** A new module `goals.py` (registered from `app.py` like `office_presence.py`) holds the pure counting/targets logic and all `/v2/api/goals/*` routes. `app.py` gets one new nbStatus field (`meeting_at`); `deals_history.py` logs the reminder button; `effie_v2.py` gets the UI (story first card, home mini card, own hot property, `/v2/goals` page, TV card, CRM card).

**Tech Stack:** Flask, vanilla JS in Python string templates, Supabase via `supabase_db`, tests as runnable scripts (`python3 tests/goals/test_x.py`, node for JS).

**Spec:** `docs/superpowers/specs/2026-10-28-daily-goals-design.md` (approved by Eyal 28/10). Read it first.

## Global Constraints

- Default daily targets: `{"meetings": 2, "buyers": 3, "past_clients": 5, "reviews": 2}`.
- "Today" = Israel time (`Asia/Jerusalem`), midnight to midnight.
- Palette: blue `#2E6BD6` action + progress bars; navy `#1E3A5F` completed bar + "הושלם"; green `#157A43` only for the past-clients button; gold only for the overall ring and empty-state icon; no red. No emojis. Touch targets ≥ 44px. Cards white, radius 20, shadow `0 6px 20px rgba(30,58,95,.06)`. Heebo, RTL.
- Office name always from config, never hard-coded.
- Only managers (drole `manager`/`developer`, i.e. `role == "admin"` but not accountant/secretary) may change targets. Agents and coordinators may not.
- Failure of one data source shows `—` for that goal, never `0`, and never breaks the rest.
- All user-facing text Hebrew. Commit only files you changed; other chats commit in this checkout.
- Do not push or deploy (Eyal does it).

## Review Focus

1. A meeting re-saved, edited, or switched meeting→followup→meeting the same day — expect it counted once, on the day it was first set. (Task 2 test `test_meeting_stamp_kept`.)
2. Agent name spelled differently between nbStatus/buyers/reviews and the login name ("בינימין"/"בנימין", double spaces) — expect it still counts, via `_canon_key` + aliases. (Task 1 test `test_name_variants_count`.)
3. A buyer whose `date` is DD/MM/YYYY without time, ISO, or empty — expect only today's dates counted, empty ignored. (Task 1 test `test_buyer_date_formats`.)
4. Around midnight/winter clock (UTC+2 vs +3): a reminder logged 23:30 IL counts for that day, 00:10 for the next. (Task 1 test `test_day_bounds_il`.)
5. Coordinator requesting `?agent=` of an agent not in her team, or an agent requesting another agent — expect 403 / own data only. (Task 4 test `test_scope_guard`.)

---

### Task 1: Pure counting and targets — `goals.py`

**Files:**
- Create: `goals.py`
- Test: `tests/goals/test_counts.py`

**Interfaces:**
- Produces (module-level, pure, no Flask):
  - `DEFAULTS = {"meetings": 2, "buyers": 3, "past_clients": 5, "reviews": 2}`
  - `ACT_REMIND = "תזכורת ללקוח עבר"`, `ACT_REVIEW_MANUAL = "בקשת ביקורת — ידני"`, `ACT_BPAGE = "דף קונה — שליחה"`
  - `day_bounds(day: datetime.date) -> (float, float)` — epoch start/end of that Israel day.
  - `parse_ts(s) -> float | None` — accepts epoch number/str, `DD/MM/YYYY`, `DD/MM/YYYY HH:MM`, ISO with/without zone (naive = Israel time).
  - `targets_for(cfg: dict, agent: str, canon) -> dict` — `cfg["v2_goals"]["default"]` over `DEFAULTS`, then `cfg["v2_goals"]["agents"][canon(agent)]`; values are ints 0–50.
  - `count_agent(agent: str, bounds, src: dict, canon) -> dict` returning `{"meetings": int|None, "buyers": int|None, "bpage": int|None, "past_clients": int|None, "reviews": int|None, "followups": {"due": int, "done": int}|None, "missed": int|None}`. `src` keys (each already fetched, or the exception it raised): `nb` (nbStatus dict), `buyers` (list of buyer dicts), `bpages` (list from `supabase_db.bpage_all()`), `activity` (list of activity rows for the day), `reviews` (list from `site_api.reviews_active`), `missed` (list of `{"agent", "phone", "ts"}`). A source whose value is an `Exception` → that goal `None`.
  - `rollup(per_agent: dict[str, dict], targets: dict[str, dict]) -> dict` — sums counts and targets per goal (None treated as missing: sum the known, flag `partial: True`).

Counting rules (copy from spec, exactly):
- meetings: nb records with `meeting_at` in bounds, `not str(pkey).startswith("manual:")`, `canon(agent) == canon(target)`.
- buyers: buyer rows with `canon(agent)` match and `parse_ts(date)` in bounds.
- bpage: of today's buyers, those whose page (`bpages` row joined by `buyers.sheet_row == buyer.row`) has `last_sent_at` in bounds.
- past_clients: activity rows `action == ACT_REMIND` whose `canon(name)` (the clicker) == `canon(target)`, distinct `detail` (9-digit client phone) per day.
- reviews: reviews whose `at` is in bounds and `canon(agents[0]) == canon(target)`.
- followups: nb records `status == "followup"`, `date[:10]` == today (ISO `YYYY-MM-DD` or `DD/MM/YYYY`), agent match; `done` = those with `done` true.
- missed: count of `missed` rows for the agent.

- [ ] **Step 1: Write the failing tests** — in `tests/goals/test_counts.py` (script style, `sys.path` to repo root, `import goals as g`), with `canon = lambda n: " ".join(str(n).split())` plus an alias map `{"בינימין אביטן": "בנימין אביטן"}`:
  - `test_day_bounds_il`: `day_bounds(date(2026,10,28))` start == epoch of `2026-10-28T00:00+02:00` (winter); an activity at 23:30 IL counts, 00:10 next day does not.
  - `test_targets_override`: cfg default `{"meetings": 1}` + agent override `{"buyers": 5}` → `{"meetings":1,"buyers":5,"past_clients":5,"reviews":2}`; garbage value `"x"` ignored; 99 clipped to 50.
  - `test_meetings_rules`: 3 nb records — today meeting (counts), `manual:` pkey (no), yesterday `meeting_at` (no) → 1; record set by coordinator (`by` ≠ agent) for agent counts for agent.
  - `test_buyer_date_formats`: dates `"28/10/2026"`, `"2026-10-28T09:15:00+02:00"`, `""`, `"27/10/2026"` → 2.
  - `test_bpage_today`: of 2 buyers today, one page with `last_sent_at` today → `bpage == 1`; a resend today of an older page still counts if buyer is today's.
  - `test_past_clients_distinct`: 3 ACT_REMIND rows for agent, two with same detail → 2; ACT_REVIEW_MANUAL rows ignored; row by manager name ignored for agent.
  - `test_reviews_count`: review added today by manager for agent (`created_by` manager, `agents=[agent]`) counts for agent.
  - `test_name_variants_count`: buyer agent "בינימין  אביטן" counts for "בנימין אביטן".
  - `test_source_failure`: `src["buyers"] = RuntimeError()` → `buyers is None and bpage is None`, others computed.
  - `test_rollup`: two agents, one with `reviews None` → summed reviews from the other, `partial True`; targets summed.

- [ ] **Step 2: Run** `python3 tests/goals/test_counts.py` — Expected: FAIL `ModuleNotFoundError: goals`.
- [ ] **Step 3: Implement** the functions above in `goals.py` (module docstring in Hebrew like `office_presence.py`; `canon` is injected so tests need no app).
- [ ] **Step 4: Run** `python3 tests/goals/test_counts.py` — Expected: prints `ok N` and exits 0.
- [ ] **Step 5: Commit** `git add goals.py tests/goals/test_counts.py && git commit -m "יעדים: ספירה טהורה ויעדים לכל סוכן"`

### Task 2: `meeting_at` stamp on nbStatus

**Files:**
- Modify: `goals.py` (add helper), `app.py` (`/api/newborn/status` `_mut` ~line 9782; `/api/newborn/status/edit` ~9937)
- Test: `tests/goals/test_meeting_stamp.py`

**Interfaces:**
- Produces: `goals.meeting_stamp(prev: dict, new_status: str, now: float) -> float | None` — `prev.get("meeting_at")` if present; else `now` if `new_status == "meeting"`; else `None`.

- [ ] **Step 1: Failing tests:** `test_meeting_stamp_kept` — new meeting → now; prev has stamp, status followup → prev stamp kept; prev has stamp, re-save meeting with later now → prev stamp; no stamp, followup → None. Plus a static check (ast/regex over `app.py`) that both the status `_mut` and the edit handler call `meeting_stamp(` and that `/status/done` does not drop `meeting_at` (it copies the existing record).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** helper; in `app.py` import `goals as _goals` near the other module imports, in `_mut` set `ms = _goals.meeting_stamp(_prev, status, time.time())` and `rec["meeting_at"] = ms` when not None; in edit, when `new_status == "meeting"` and the record has no `meeting_at`, set it.
- [ ] **Step 4: Run** test + `python3 -c "import ast;ast.parse(open('app.py').read())"` — PASS.
- [ ] **Step 5: Commit** `app.py goals.py tests/goals/test_meeting_stamp.py` — "יעדים: חותמת meeting_at לפגישה מנכס נולד".

### Task 3: Log the past-client buttons

**Files:**
- Modify: `goals.py` (route), `deals_history.py` (`waBtn`, ~line 893), `app.py` (register goals after office_presence, same try/except pattern)
- Test: `tests/goals/test_remind_route.py`, `tests/goals/test_waBtn.js`

**Interfaces:**
- Produces: `goals.register(app, G)`; route `POST /v2/api/goals/remind` body `{"phone": str, "kind": "remind"|"review"}` → `G["_log_activity"](name, role, phone, ACT_REMIND|ACT_REVIEW_MANUAL, last9(client))`, returns `{"ok": True}`; 403 without `G["_web_auth"]()`; 400 when client phone has < 9 digits.
- Consumes: `G["_web_auth"]`, `G["_log_activity"]`, `G["_last9"]`.

- [ ] **Step 1: Failing tests:** Python with Flask + `AutoG` (copy the pattern from `tests/presence/test_crm_ping.py`): logs remind with detail `"501234567"`, review kind logs ACT_REVIEW_MANUAL, 403 unauthenticated, 400 bad phone. Node: extract `waBtn` and `remindText` from `deals_history.py`, render, assert both anchors carry `onclick` that calls a beacon with `kind` `remind`/`review` and the client phone, and that `href` is unchanged (WhatsApp still opens).
- [ ] **Step 2: Run** both — FAIL.
- [ ] **Step 3: Implement** route; in `waBtn` add `onclick="goalBeacon('<p9>','remind')"` / `'review'`, and a small `goalBeacon(p, k)` that does `fetch('/v2/api/goals/remind', {method:'POST', keepalive:true, headers:{'Content-Type':'application/json','X-Auth-Token':TOK}, body:...}).catch(function(){})` (never blocks navigation). Register `goals` in `app.py`.
- [ ] **Step 4: Run** both + ast on the three files — PASS.
- [ ] **Step 5: Commit** — "יעדים: רישום תזכורת ללקוח עבר ובקשת ביקורת ידנית".

### Task 4: Goals API

**Files:**
- Modify: `goals.py`; `site_api.py` (expose `review_rows()` at module level — same rows `_rv_rows` reads, without the seeding side effect); `effie_v2.py` (`crm_todo` gains `limit=30` param, default unchanged)
- Test: `tests/goals/test_goals_api.py`

**Interfaces:**
- Produces routes:
  - `GET /v2/api/goals/today[?agent=<name>]` → `{"ok": True, "view": "agent"|"team"|"office", "day": "YYYY-MM-DD", "me": {counts, targets} | None, "total": {rollup} | None, "agents": [{"name", "counts", "targets", "seen_today": bool}] (team/office only), "can_edit": bool}`. Agent → own only (`agent` param ignored). Coordinator → her agents (`G["_coordinators_all"]()` by her phone) as `team`; `?agent=` outside team → 403. Manager → whole office as `office`; `?agent=` any.
  - `GET /v2/api/goals/office?k=<TV_KEY>` → `{"ok": True, "total": rollup}` only (no names). Same key check as `/v2/api/brief` (`_TV_KEY` compare_digest; expose it via `G` or re-read env). 403 otherwise.
  - `POST /v2/api/goals/targets` body `{"agent": name|"" , "targets": {goal: int}}` → manager only (403 otherwise); `""` = office default; writes `cfg["v2_goals"]` through `G["_config_mutate"]`; logs `"יעדים — עדכון"` with agent + values; returns new targets.
- Builds through `G["_swr"]("goals:" + scope_key, 60, build)`; sources from `G`: `_load_config()["nbStatus"]`, `_fetch_manual_buyers()`, `_sbdb.bpage_all()`, `_activity_fetch(day_start, today=True)`, `site_api.review_rows()`→`reviews_active`, `web_fetch_raw("שיחות", <3 days ago DD/MM/YYYY>, "31/12/2099")`→`effie_v2.crm_todo(calls, [], [], [], {}, now, h, limit=None)["missed"]`. Each source fetched once per build, wrapped so an exception becomes the `src` value.
- Office roster = login-capable agents: contacts minus suspended/removed/accountant/test accounts — reuse whatever `crm_dashboard_data`'s agent table uses (`agent_act` roster in `effie_v2.py` ~18240).

- [ ] **Step 1: Failing tests** (Flask + AutoG with fake sources): `test_agent_own_only`; `test_scope_guard` (coordinator `?agent=` outside team → 403; agent `?agent=` → own data); `test_team_rollup`; `test_office_kiosk` (bad key 403, good key returns totals and no `agents`/names anywhere in JSON); `test_targets_manager_only` (agent/coordinator 403, manager writes default + per-agent and `_config_mutate` called, activity logged); `test_source_failure_dash` (buyers raises → `counts.buyers is None`, 200).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** + existing `python3 tests/crm/test_dash_agents_todo.py` (crm_todo unchanged by default) — PASS.
- [ ] **Step 5: Commit** — "יעדים: API — היום, משרד לטלוויזיה, עדכון יעדים".

### Task 5: App UI — `/v2/goals`, story first card, home

**Files:**
- Modify: `effie_v2.py` (home template ~line 1220 and story JS ~1751; new `V2_GOALS_HTML` + route `/v2/goals` served through `_page()` like other screens)
- Test: `tests/goals/test_goals_ui.js`

**Interfaces:**
- Consumes: `GET /v2/api/goals/today`, `POST /v2/api/goals/targets`, `GET /v2/api/hot` (existing; own hot property).
- Produces JS: `goalsCardHtml(j)` (shared by story card and `/v2/goals`), `goalsChipsHtml(j)` (home mini card).

Behaviour (spec "הזרימה באפליקציה"):
- Story: `total()` becomes `2 + hotProps.length`; card 0 = goals (`goalsCardHtml`), card 1 = existing summary, then hot properties. `storyLog` unchanged (seen counts include the goals card). Buttons inside the goals card navigate to `/v2/newborn`, `/v2/buyers`, `/v2/history` (green), `/v2/reviews`, `/v2/meets`, `/v2/calls` after `closeStory()`.
- Coordinator/manager goals card shows `total` with a "פירוט לפי סוכן" link to `/v2/goals`.
- `/v2/goals`: agent — own card; coordinator/manager — total + list of agents (bar per goal, grey "לא נכנס היום"); manager — "עריכת יעד" per agent and "יעד ברירת מחדל" opening a sheet with four number inputs (16px, `inputmode=numeric`).
- Home: below the stats, mini card "היעדים שלי להיום · X/4" with chips, tap → `/v2/goals`; replace nothing else. Add card "הנכס החם שלי" from `/v2/api/hot` (agent's active one); none → designed empty state (gold-circle icon, "עוד לא סימנת נכס חם", "לסימון בנכסים שלי" → `/v2/props?tab=mine`). For coordinator/manager without one — hide the card.
- Client cache `v2c:goals` keyed by token + day; draw instantly, refresh from API.
- Overall ring = completed goals / 4 (a goal is complete when count ≥ target; target 0 counts as complete).
- Missing value (`null`) renders `—`.
- A 'בקרוב' row: '2 נכסים בפייסבוק ובאינסטגרם · יופעל בקרוב', no bar.
- Target editing lives on `/v2/goals` (manager view), not in `/v2/admin` — `/v2/admin` is owner-only and managers must be able to edit (deviation from the spec's own-call line; tell Eyal).

- [ ] **Step 1: Failing node tests:** extract the functions from `effie_v2.py` (pattern of existing node tests under `tests/buyers`), assert: `goalsCardHtml` renders 4 bars + followups + missed lines with the exact numbers; completed goal uses navy + "הושלם"; `null` → "—"; past-clients button has class/colour `#157A43`; no emoji code points; story `total()` with 3 hot props == 5; home empty state text; manager view includes "עריכת יעד", agent view does not.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** test + `node --check` on the extracted `<script>` of home and `/v2/goals` + ast on `effie_v2.py` — PASS.
- [ ] **Step 5: Commit** — "יעדים: מסך היעדים, כרטיס ראשון בסטורי, כרטיס בבית והנכס החם שלי".

### Task 6: TV goals card

**Files:**
- Modify: `effie_v2.py` (`V2_TV_HTML`, `playlist()` / `durFor` ~10454)
- Test: `tests/goals/test_tv.js`

**Interfaces:**
- Consumes: `GET /v2/api/goals/office?k=` (kiosk) or with token when logged in.
- Produces: playlist item `{t: 'goals'}` first in every loop; `durFor` treats `'goals'` with the summary weight `SUM_W`.

- [ ] **Step 1: Failing node test:** `playlist()` with 3 hot props starts with `goals`, then `sum`, then props; `durFor` gives `goals` the same duration as `sum`; goals card HTML shows office totals and contains no agent names (feed a payload with a name and assert it is absent); fetch failure → card skipped (playlist without `goals`).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** + `node --check` on the TV script — PASS.
- [ ] **Step 5: Commit** — "יעדים: כרטיס יעדים בטלוויזיה".

### Task 7: CRM dashboard table + story tile caption

**Files:**
- Modify: `effie_v2.py` (`crm_dashboard_data` src gets `"goals": lambda: <office build from goals.py>`; dashboard HTML gets card "יעדי היום"; story tile caption)
- Test: `tests/crm/test_dash_goals.py`

**Interfaces:**
- Consumes: `goals.count_agent`, `goals.rollup`, `goals.targets_for` (via a `goals.build_office(src, day, canon)` helper you add to `goals.py` and reuse in Task 4's office path).
- Produces: dashboard JSON key `"goals": {"day": ..., "rows": [{"name", "counts", "targets", "met": int, "trend": {"goal": delta_vs_last_week}, "seen_today": bool}], "total": {...}}` for periods `today`, `yesterday`, `week`.

Week rule: counts summed Sunday→today; target = daily target × workdays elapsed (Sun–Thu = 1, Fri = 0.5, Sat = 0). Trend = this period vs the same period a week earlier.

- [ ] **Step 1: Failing test** (`_load.load` pattern + fake goals src): rows sorted by `met` desc, office row first, week target on Wednesday = 4 × daily (Sun–Wed), Friday adds 0.5, `seen_today` false → row still present; story tile caption text mentions that card 1 is goals ("ראה 1 = רק היעדים").
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** (table columns per spec: סוכן · פגישות נכס נולד · קונים · דף קונה · לקוחות עבר · המלצות · פולו-אפ · שיחות פתוחות · עמידה).
- [ ] **Step 4: Run** + full `for f in tests/crm/test_*.py tests/goals/test_*.py; do python3 $f || echo FAIL $f; done` — PASS.
- [ ] **Step 5: Commit** — "יעדים: טבלת יעדי היום בלוח הבקרה".

### Task 8: Decision log

- [ ] Add an entry to `/Users/eyal/Documents/remax-family/CLAUDE.md` (decision log, top) summarising what was built, commits, test counts, and Eyal's steps (push+deploy; nothing else — no SQL, no env). Commit only `CLAUDE.md` in that repo.
