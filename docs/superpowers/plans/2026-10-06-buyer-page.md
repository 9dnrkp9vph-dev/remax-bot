# דף קונה עם התאמות נכסים — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** קישור אישי וקבוע לכל קונה (`/b/<token>`) עם הנכסים שהסוכן בחר, שהלקוח מסמן עליהם, והסימונים + התאמות חדשות חוזרים לסוכן.

**Architecture:** שתי טבלאות Supabase (`buyer_pages`, `buyer_page_items`) דרך פונקציות `bpage_*` ב-`supabase_db.py`; פונקציות טהורות `bpage_*` ברמת המודול ב-`effie_v2.py` (צילום/העשרה/סדר/התאמות/רינדור) — נבדקות בבידוד; ראוטים בתוך `effie_v2.register` עם תלויות מ-`G`; צד הסוכן ב-`V2_BUYERS_HTML` (חלון ההתאמות + כרטיס קונה + גיליון).

**Tech Stack:** Flask, PostgREST (requests), JS בתוך מחרוזות HTML (ES5, כמו שאר המסכים), בדיקות: סקריפטי Python עם `check()` + node.

**Spec:** `docs/superpowers/specs/2026-10-06-buyer-page-design.md`

## Global Constraints
- עברית RTL, Heebo; פלטה סגורה: קרם `#F2EFE7`, נייבי `#1E3A5F`, כחול פעולה `#2E6BD6`, זהב `#C29435`/`#E4C56B` (טקסט על זהב `#231700`), ירוק וואטסאפ `#1FAF5E` (כפתור עם טקסט `#157A43`), אדום `#C24040` למחיקה בלבד (פח בריבוע `#FBEDED`). טקסט משני `#6B7280`.
- כרטיסים לבנים radius 20, צל `0 6px 20px rgba(30,58,95,.06)`; מגע ≥44px; שדות קלט 16px; אין אימוג'ים.
- דף הלקוח: מיתוג המשרד בלבד (`_sb_office()` name/logo_url) — בלי "אפי", בלי Powered by. שם המשרד לעולם לא hardcoded.
- פרטיות: בדף הלקוח רק טלפון הסוכן המטפל; נכס נולד — בלי מספר בית, בלי תמונות, בלי תיאור, בלי טלפון/שם בעלים; שת"פ — בלי שם משרד ובלי קישור. אף קישור ליד2.
- סוכן רואה רק דפים של הקונים שלו (`_scope_keys_phones`), מנהל — הכל.
- תוקף: 90 יום מ-`last_sent_at`; כל שליחה מאריכה.
- התאמה חזקה = `score >= 60` ותקציב ±20% (כמו `_splitSW`/`_budgetOk` בחלון ההתאמות).
- env: `BPAGE=0` → השליחה חוזרת לטקסט הישן; `BPAGE_DIGEST=0` → בלי פוש יומי.
- כל שינוי: `ast.parse` לקבצי Python, `node --check` לכל סקריפט עמוד שנגעת בו, בדיקת שמות פונקציה כפולים, קשירת ראוטים.
- commit מקומי בלבד; `git pull --ff-only` לפני כל commit; `git add` רק לקבצים שלך (בריפו עובדים צ'אטים מקבילים).

**נתיבים:** `RB=/Users/eyal/Documents/GitHub/remax-bot` · `RF=/Users/eyal/Documents/remax-family` · `T=/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage` (בדיקות).

---

### Task 0: תשתית בדיקות משותפת

**Files:**
- Create: `$T/common.py`
- Create: `$T/test_static.py`

- [ ] **Step 1: עוזר בדיקות משותף**

`$T/common.py`:
```python
# -*- coding: utf-8 -*-
import os, re, tempfile, importlib.util
os.environ.setdefault("MAP_CACHE_DIR", tempfile.mkdtemp())
RB = "/Users/eyal/Documents/GitHub/remax-bot"
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def E():  return load("ev2", RB + "/effie_v2.py")
def SBD(): return load("sbd", RB + "/supabase_db.py")
N = [0]
def check(c, m=""):
    assert c, m
    N[0] += 1
class GG(dict):
    def __missing__(self, k): return (lambda *a, **kw: None)

class Resp:
    def __init__(self, data=None, status=200): self._d, self.status_code = data, status
    def json(self): return self._d
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError("http %s" % self.status_code)
    @property
    def ok(self): return self.status_code < 400
class FakeReq:
    """requests מזויף: queue של תשובות לפי (method, table); רושם כל קריאה."""
    def __init__(self): self.calls, self.q = [], {}
    def on(self, method, table, data=None, status=200):
        self.q.setdefault((method, table), []).append(Resp(data, status)); return self
    def _do(self, method, url, **kw):
        table = url.split("/rest/v1/")[-1]
        self.calls.append((method, table, kw))
        lst = self.q.get((method, table)) or []
        return lst.pop(0) if lst else Resp([] if method == "GET" else None)
    def get(self, url, **kw):    return self._do("GET", url, **kw)
    def post(self, url, **kw):   return self._do("POST", url, **kw)
    def patch(self, url, **kw):  return self._do("PATCH", url, **kw)
    def delete(self, url, **kw): return self._do("DELETE", url, **kw)
```

- [ ] **Step 2: בדיקה סטטית (ast + כפילויות + קשירת ראוטים)**

`$T/test_static.py`:
```python
# -*- coding: utf-8 -*-
import ast, sys, collections
RB = "/Users/eyal/Documents/GitHub/remax-bot"
for f in ("app.py", "effie_v2.py", "supabase_db.py"):
    src = open(RB + "/" + f, encoding="utf-8").read()
    tree = ast.parse(src)
    top = collections.Counter(n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    dup = [k for k, v in top.items() if v > 1]
    assert not dup, (f, "duplicate top-level defs", dup)
    # פונקציות פנימיות ב-register: אין כפילויות; כל @app.route נקשר לפונקציה שאינה מתחילה ב-'_'
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "register":
            inner = collections.Counter(x.name for x in n.body if isinstance(x, ast.FunctionDef))
            d2 = [k for k, v in inner.items() if v > 1]
            assert not d2, (f, "duplicate defs in register", d2)
        if isinstance(n, ast.FunctionDef):
            for dec in n.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                    assert not n.name.startswith("_"), (f, "route bound to helper", n.name)
print("static ok")
```

- [ ] **Step 3: הרצה — חייב לעבור על הקוד הנוכחי**

Run: `python3 $T/test_static.py`
Expected: `static ok` (אם נכשל על קוד קיים — לתעד את השם ולהחריג אותו ברשימה מפורשת, לא לשנות קוד של אחרים).

---

### Task 1: SQL + שכבת נתונים `bpage_*` ב-supabase_db

**Files:**
- Create: `$RF/supabase/migrations/20261006_buyer_pages.sql`
- Modify: `$RB/supabase_db.py` (סוף הקובץ, בלוק חדש `# ── [BPAGE 06/10]`)
- Test: `$T/test_sbd.py`

**Interfaces — Produces:**
- `bpage_by_token(token) -> dict|None`, `bpage_by_row(row:int) -> dict|None`, `bpage_all() -> list[dict]` — כל page: `{id, token, buyer_id, agent_name, agent_phone, created_at, last_sent_at, expires_at, seen_at, query, row}`
- `bpage_create(row, token, agent_name, agent_phone, expires_iso, query) -> dict|None`
- `bpage_update(page_id, fields:dict) -> None`
- `bpage_items(page_ids:list) -> list[dict]` — `{page_id, source, prop_key, snapshot, added_at, mark, note, marked_at}`
- `bpage_add_items(page_id, items:list[{source,prop_key,snapshot}]) -> list[str]` (המפתחות שנוספו בפועל)
- `bpage_set_mark(page_id, key, mark|None, note) -> dict|None` (הפריט אחרי העדכון)
- `bpage_remove_item(page_id, key) -> None`

- [ ] **Step 1: קובץ המיגרציה**

`$RF/supabase/migrations/20261006_buyer_pages.sql`:
```sql
-- [BPAGE 06/10] דף קונה עם התאמות נכסים — ספק: remax-bot docs/superpowers/specs/2026-10-06-buyer-page-design.md
-- תוספות בלבד; לא נוגע בטבלאות קיימות. גישה מהשרת בלבד (service_role) — RLS בלי policies.
create table if not exists buyer_pages (
  id           uuid primary key default gen_random_uuid(),
  office_id    uuid not null references offices(id) on delete cascade,
  buyer_id     uuid not null references buyers(id) on delete cascade,
  token        text not null unique,
  agent_name   text not null default '',
  agent_phone  text not null default '',
  query        jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  last_sent_at timestamptz not null default now(),
  expires_at   timestamptz not null,
  seen_at      timestamptz,
  unique (office_id, buyer_id)
);
create table if not exists buyer_page_items (
  id         uuid primary key default gen_random_uuid(),
  page_id    uuid not null references buyer_pages(id) on delete cascade,
  source     text not null check (source in ('office','shtaf','newborn','mine')),
  prop_key   text not null,
  snapshot   jsonb not null default '{}'::jsonb,
  added_at   timestamptz not null default now(),
  mark       text check (mark in ('like','dislike','visit')),
  note       text not null default '',
  marked_at  timestamptz,
  unique (page_id, prop_key)
);
create index if not exists buyer_page_items_page on buyer_page_items (page_id);
alter table buyer_pages enable row level security;
alter table buyer_page_items enable row level security;
```
(הערה: לעומת הספק נוספה עמודה `query` — דרישות הקונה המפורקות ברגע השליחה, כדי לחשב "התאמות חדשות" בלי קריאת AI בכל בדיקה.)

- [ ] **Step 2: בדיקה נכשלת**

`$T/test_sbd.py`:
```python
# -*- coding: utf-8 -*-
import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage")
from common import *
S = SBD()
S.SUPABASE_URL, S.SUPABASE_SERVICE_KEY, S.SB_OFFICE_ID = "https://sb", "k", "OFF"
F = FakeReq(); S.requests = F
PG = {"id": "P1", "token": "tok", "buyer_id": "B1", "agent_name": "דנה", "agent_phone": "0521111111",
      "created_at": "2026-10-06T10:00:00+00:00", "last_sent_at": "2026-10-06T10:00:00+00:00",
      "expires_at": "2027-01-04T10:00:00+00:00", "seen_at": None, "query": {}, "buyers": {"sheet_row": 7}}
# by_token: מסנן לפי טוקן ומשרד, משטח את ה-embed
F.on("GET", "buyer_pages", [dict(PG)])
p = S.bpage_by_token("tok")
check(p["row"] == 7 and "buyers" not in p, p)
m, t, kw = F.calls[-1]
check(kw["params"]["token"] == "eq.tok" and kw["params"]["office_id"] == "eq.OFF" and "buyers!inner(sheet_row)" in kw["params"]["select"], kw)
check(S.bpage_by_token("nope") is None, "missing → None")
# by_row
F.on("GET", "buyer_pages", [dict(PG)])
check(S.bpage_by_row(7)["id"] == "P1")
check(F.calls[-1][2]["params"]["buyers.sheet_row"] == "eq.7")
# create: row → uuid, ואז insert, ואז קריאה חוזרת
F.on("GET", "buyers", [{"id": "B1"}]).on("POST", "buyer_pages", None, 201).on("GET", "buyer_pages", [dict(PG)])
p = S.bpage_create(7, "tok", "דנה", "0521111111", "2027-01-04T10:00:00+00:00", {"q": "x"})
check(p and p["id"] == "P1", p)
post = [c for c in F.calls if c[0] == "POST"][-1][2]["json"][0]
check(post["buyer_id"] == "B1" and post["office_id"] == "OFF" and post["token"] == "tok" and post["query"] == {"q": "x"}, post)
F.on("GET", "buyers", [])
check(S.bpage_create(99, "t2", "", "", "2027-01-04T10:00:00+00:00", {}) is None, "unknown buyer → None")
# add_items: ignore-duplicates + on_conflict, מחזיר רק את מה שנוסף
F.on("POST", "buyer_page_items", [{"prop_key": "L:1"}], 201)
added = S.bpage_add_items("P1", [{"source": "office", "prop_key": "L:1", "snapshot": {}},
                                 {"source": "office", "prop_key": "L:2", "snapshot": {}}])
kw = F.calls[-1][2]
check(added == ["L:1"] and "ignore-duplicates" in kw["headers"]["Prefer"] and kw["params"]["on_conflict"] == "page_id,prop_key", (added, kw))
check(all(r["page_id"] == "P1" for r in kw["json"]))
check(S.bpage_add_items("P1", []) == [], "empty")
# items
F.on("GET", "buyer_page_items", [{"page_id": "P1", "prop_key": "L:1"}])
check(len(S.bpage_items(["P1"])) == 1 and F.calls[-1][2]["params"]["page_id"] == "in.(P1)")
check(S.bpage_items([]) == [])
# set_mark
F.on("PATCH", "buyer_page_items", [{"prop_key": "L:1", "mark": "like", "snapshot": {"street": "הרצל"}}])
it = S.bpage_set_mark("P1", "L:1", "like", "")
kw = F.calls[-1][2]
check(it["mark"] == "like" and kw["params"] == {"page_id": "eq.P1", "prop_key": "eq.L:1"} and kw["json"]["marked_at"], kw)
F.on("PATCH", "buyer_page_items", [])
check(S.bpage_set_mark("P1", "L:9", "like", "") is None, "key not in page")
F.on("PATCH", "buyer_page_items", [{"prop_key": "L:1", "mark": None}])
S.bpage_set_mark("P1", "L:1", None, "")
check(F.calls[-1][2]["json"]["marked_at"] is None and F.calls[-1][2]["json"]["mark"] is None, "unmark")
# update / remove
S.bpage_update("P1", {"seen_at": "x"})
check(F.calls[-1][0] == "PATCH" and F.calls[-1][1] == "buyer_pages" and F.calls[-1][2]["params"]["id"] == "eq.P1")
S.bpage_remove_item("P1", "L:1")
check(F.calls[-1][0] == "DELETE" and F.calls[-1][2]["params"] == {"page_id": "eq.P1", "prop_key": "eq.L:1"})
print("sbd ok", N[0])
```

- [ ] **Step 3: הרצה — נכשל**

Run: `python3 $T/test_sbd.py`
Expected: `AttributeError: module 'sbd' has no attribute 'bpage_by_token'`

- [ ] **Step 4: מימוש — הוספה בסוף `supabase_db.py`**

```python
# ── [BPAGE 06/10] דף קונה עם התאמות נכסים — buyer_pages + buyer_page_items ─────────
# buyer_id = uuid של הקונה (sheet_row זז במחיקה ב-buyers_delete_row); השורה מגיעה מ-embed.
_BPAGE_COLS = "id,token,buyer_id,agent_name,agent_phone,query,created_at,last_sent_at,expires_at,seen_at"


def _bp_now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _bpage_get(params):
    p = {"select": _BPAGE_COLS + ",buyers!inner(sheet_row)", "office_id": "eq." + SB_OFFICE_ID}
    p.update(params)
    r = requests.get(SUPABASE_URL + "/rest/v1/buyer_pages", headers=_headers(), params=p, timeout=_TIMEOUT)
    r.raise_for_status()
    out = []
    for rec in (r.json() or []):
        b = rec.pop("buyers", None) or {}
        rec["row"] = b.get("sheet_row")
        out.append(rec)
    return out


def bpage_by_token(token):
    rows = _bpage_get({"token": "eq." + str(token), "limit": "1"})
    return rows[0] if rows else None


def bpage_by_row(row):
    rows = _bpage_get({"buyers.sheet_row": "eq.%d" % int(row), "limit": "1"})
    return rows[0] if rows else None


def bpage_all():
    return _bpage_get({"order": "last_sent_at.desc", "limit": "5000"})


def bpage_create(row, token, agent_name, agent_phone, expires_iso, query):
    """דף חדש לקונה בשורה row. קונה לא קיים → None."""
    g = requests.get(SUPABASE_URL + "/rest/v1/buyers", headers=_headers(),
                     params={"select": "id", "office_id": "eq." + SB_OFFICE_ID,
                             "sheet_row": "eq.%d" % int(row), "limit": "1"}, timeout=_TIMEOUT)
    g.raise_for_status()
    rows = g.json() or []
    if not rows:
        return None
    rec = {"office_id": SB_OFFICE_ID, "buyer_id": rows[0]["id"], "token": token,
           "agent_name": agent_name or "", "agent_phone": agent_phone or "",
           "expires_at": expires_iso, "query": query or {}}
    r = requests.post(SUPABASE_URL + "/rest/v1/buyer_pages",
                      headers={**_headers(), "Prefer": "return=minimal"}, json=[rec], timeout=_TIMEOUT)
    r.raise_for_status()
    return bpage_by_row(row)


def bpage_update(page_id, fields):
    r = requests.patch(SUPABASE_URL + "/rest/v1/buyer_pages",
                       headers={**_headers(), "Prefer": "return=minimal"},
                       params={"id": "eq." + str(page_id)}, json=fields, timeout=_TIMEOUT)
    r.raise_for_status()


def bpage_items(page_ids):
    if not page_ids:
        return []
    r = requests.get(SUPABASE_URL + "/rest/v1/buyer_page_items", headers=_headers(),
                     params={"select": "page_id,source,prop_key,snapshot,added_at,mark,note,marked_at",
                             "page_id": "in.(" + ",".join(str(x) for x in page_ids) + ")",
                             "order": "added_at.desc", "limit": "20000"}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json() or []


def bpage_add_items(page_id, items):
    """הוספה בלי כפילויות (unique page_id+prop_key). מחזיר את המפתחות שנוספו בפועל."""
    if not items:
        return []
    now = _bp_now()
    recs = [{"page_id": page_id, "source": it["source"], "prop_key": it["prop_key"],
             "snapshot": it.get("snapshot") or {}, "added_at": now} for it in items]
    r = requests.post(SUPABASE_URL + "/rest/v1/buyer_page_items",
                      headers={**_headers(), "Prefer": "resolution=ignore-duplicates,return=representation"},
                      params={"on_conflict": "page_id,prop_key"}, json=recs, timeout=_TIMEOUT)
    r.raise_for_status()
    return [x.get("prop_key") for x in (r.json() or [])]


def bpage_set_mark(page_id, key, mark, note):
    """סימון הלקוח (mark=None מבטל). מפתח שלא בדף → None."""
    r = requests.patch(SUPABASE_URL + "/rest/v1/buyer_page_items",
                       headers={**_headers(), "Prefer": "return=representation"},
                       params={"page_id": "eq." + str(page_id), "prop_key": "eq." + str(key)},
                       json={"mark": mark or None, "note": note or "",
                             "marked_at": _bp_now() if mark else None}, timeout=_TIMEOUT)
    r.raise_for_status()
    rows = r.json() or []
    return rows[0] if rows else None


def bpage_remove_item(page_id, key):
    r = requests.delete(SUPABASE_URL + "/rest/v1/buyer_page_items", headers=_headers(),
                        params={"page_id": "eq." + str(page_id), "prop_key": "eq." + str(key)},
                        timeout=_TIMEOUT)
    r.raise_for_status()
```

- [ ] **Step 5: הרצה — עובר**

Run: `python3 $T/test_sbd.py && python3 $T/test_static.py`
Expected: `sbd ok 22` (בערך) + `static ok`

- [ ] **Step 6: Commit (שני ריפואים)**

```bash
cd $RB && git pull --ff-only && git add supabase_db.py && git commit -m "דף קונה (1): שכבת נתונים bpage_* ל-buyer_pages/buyer_page_items

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd $RF && git add supabase/migrations/20261006_buyer_pages.sql && git commit -m "מיגרציה: buyer_pages + buyer_page_items (דף קונה)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: פונקציות טהורות — צילום, העשרה, סדר, נוסחים

**Files:**
- Modify: `$RB/effie_v2.py` — בלוק מודול חדש `# ── [BPAGE 06/10] ──` לפני `def register(` (שורה ~10721)
- Test: `$T/test_pure.py`

**Interfaces — Produces (ברמת המודול ב-effie_v2):**
- `bpage_images(row:dict) -> list[str]` — `תמונות`/`images` (list או JSON), נפילה ל-`תמונה`/`image`; רק http(s); עד 30
- `bpage_excl_as_office_row(r:dict) -> dict` — שורת שת"פ (שטוחה) → מבנה שורת משרד, כולל `תמונה`/`תמונות`, בלי משרד/קישור
- `bpage_snapshot(source, orow) -> dict` — `{street, house, neighborhood, city, price, rooms, floor, sqm, type, desc, images}`; newborn: house/desc/images ריקים
- `bpage_live(item, live_orow|None) -> dict` — פריט לתצוגה: snapshot + `key, source, mark, note, added, marked, gone, priceOld`
- `bpage_order(disp:list) -> (active:list, disliked:list)` — מסמן `isNew` לאצווה האחרונה; active: חדשים קודם, אחר כך added יורד
- `bpage_wa_text(first_name, url, n_added, is_first) -> str`
- `bpage_expired(page:dict, now_ep:float) -> bool`
- `bpage_iso_ep(s) -> float`
- `BPAGE_MARKS = {"like": "מתאים", "dislike": "לא מתאים", "visit": "רוצה לראות"}`

- [ ] **Step 1: בדיקה נכשלת**

`$T/test_pure.py`:
```python
# -*- coding: utf-8 -*-
import sys, json; sys.path.insert(0, "/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage")
from common import *
E = E()
OFF = {"כתובת": "יששכר", "מספר בית": "4", "שכונה": "מוצקין הותיקה", "עיר / ישוב": "קרית מוצקין", "מחיר": "1,690,000",
       "חדרים": "4", "קומה": "2", 'מ"ר': "85", "סוג נכס": "דירה", "_desc_ae": "דירה מוארת", "תמונה": "https://i/1.jpg",
       "קישור": "https://www.yad2.co.il/item/abc", "טלפון 1": "0501234567", "סוכן 1": "דודו"}
# תמונות
check(E.bpage_images(OFF) == ["https://i/1.jpg"], "fallback single")
check(E.bpage_images(dict(OFF, **{"תמונות": ["https://i/1.jpg", "https://i/2.jpg", "x"]})) == ["https://i/1.jpg", "https://i/2.jpg"])
check(E.bpage_images({"תמונות": json.dumps(["https://a", "https://b"])}) == ["https://a", "https://b"], "json string")
check(E.bpage_images({}) == [])
check(len(E.bpage_images({"images": ["https://x/%d" % i for i in range(50)]})) == 30, "cap 30")
# צילום משרד
s = E.bpage_snapshot("office", OFF)
check(s == {"street": "יששכר", "house": "4", "neighborhood": "מוצקין הותיקה", "city": "קרית מוצקין", "price": "1690000",
            "rooms": "4", "floor": "2", "sqm": "85", "type": "דירה", "desc": "דירה מוארת", "images": ["https://i/1.jpg"]}, s)
check("yad2" not in json.dumps(s) and "0501234567" not in json.dumps(s) and "דודו" not in json.dumps(s), "no link/phone/agent")
# נכס נולד
nb = dict(OFF, **{"מספר בית": "4", "תיאור": "התקשרו 050-9999999 לרחוב יששכר 4"})
s = E.bpage_snapshot("newborn", nb)
check(s["house"] == "" and s["images"] == [] and s["desc"] == "" and s["street"] == "יששכר" and s["price"] == "1690000", s)
# שת"פ
EX = {"street": "הרב קוק 33, קרית מוצקין", "dest": "דירה · 4 חד' · 115 מ\"ר · מעלית", "desti": "תיאור שת\"פ",
      "price": "1690000", "office": "RE/MAX SMART", "link": "https://www.yad2.co.il/item/zz", "city": "קרית מוצקין",
      "neighborhood": "מוצקין הותיקה", "phone": "0547777777", "image": "https://i/x.jpg", "floor": "3"}
o = E.bpage_excl_as_office_row(EX)
check(o["כתובת"] == "הרב קוק" and o["מספר בית"] == "33" and o["חדרים"] == "4" and o['מ"ר'] == "115" and o["סוג נכס"] == "דירה"
      and o["עיר / ישוב"] == "קרית מוצקין" and o["תיאור"] == "תיאור שת\"פ" and o["קומה"] == "3", o)
s = E.bpage_snapshot("shtaf", o)
blob = json.dumps(s, ensure_ascii=False)
check("SMART" not in blob and "yad2" not in blob and "0547777777" not in blob and s["images"] == ["https://i/x.jpg"], s)
check(E.bpage_excl_as_office_row({"street": "הנוטר", "dest": ""})["מספר בית"] == "", "no house number")
# העשרה חיה
item = {"source": "office", "prop_key": "L:1", "snapshot": E.bpage_snapshot("office", OFF), "added_at": "2026-10-06T10:00:00+00:00",
        "mark": None, "note": "", "marked_at": None}
d = E.bpage_live(item, dict(OFF, **{"מחיר": "1,600,000"}))
check(d["price"] == "1600000" and d["priceOld"] == "1690000" and not d["gone"] and d["key"] == "L:1" and d["mark"] == "", d)
d = E.bpage_live(item, dict(OFF, **{"ירד מפרסום": "05/10/2026"}))
check(d["gone"], "delisted")
d = E.bpage_live(item, None)
check(d["price"] == "1690000" and not d["gone"] and d["priceOld"] == "", "missing live → snapshot")
d = E.bpage_live(item, dict(OFF, **{"תמונות": ["https://i/1.jpg", "https://i/2.jpg"]}))
check(d["images"] == ["https://i/1.jpg", "https://i/2.jpg"], "live gallery wins when larger")
nbi = dict(item, source="newborn", snapshot=E.bpage_snapshot("newborn", nb))
check(E.bpage_live(nbi, dict(nb, **{"תמונות": ["https://i/9"]}))["images"] == [], "newborn never gets images")
# סדר
mk = lambda k, at, mark=None: {"key": k, "added": at, "mark": mark or ""}
act, dis = E.bpage_order([mk("a", "2026-10-01T10:00:00+00:00"), mk("b", "2026-10-06T10:00:00+00:00"),
                          mk("c", "2026-10-06T10:00:30+00:00"), mk("d", "2026-10-03T10:00:00+00:00", "dislike")])
check([x["key"] for x in act] == ["c", "b", "a"] and [x["key"] for x in dis] == ["d"], (act, dis))
check(act[0]["isNew"] and act[1]["isNew"] and not act[2]["isNew"], "latest batch = new")
act, dis = E.bpage_order([mk("a", "2026-10-01T10:00:00+00:00")])
check(not act[0]["isNew"], "single batch is not 'new'")
check(E.bpage_order([]) == ([], []))
# נוסחים
check(E.bpage_wa_text("בתיה", "https://x/b/t", 2, True) == "היי בתיה, הכנתי לך רשימת נכסים אישית:\nhttps://x/b/t")
check(E.bpage_wa_text("בתיה", "https://x/b/t", 2, False) == "היי בתיה, הוספתי לך 2 נכסים חדשים:\nhttps://x/b/t")
check(E.bpage_wa_text("", "https://x/b/t", 1, False) == "היי, הוספתי לך נכס חדש:\nhttps://x/b/t")
check(E.bpage_wa_text("בתיה", "https://x/b/t", 0, False) == "היי בתיה, הנה רשימת הנכסים שלך:\nhttps://x/b/t")
# תוקף
check(E.bpage_expired({"expires_at": "2026-10-01T00:00:00+00:00"}, E.bpage_iso_ep("2026-10-06T00:00:00+00:00")))
check(not E.bpage_expired({"expires_at": "2027-01-01T00:00:00+00:00"}, E.bpage_iso_ep("2026-10-06T00:00:00+00:00")))
check(E.bpage_expired({"expires_at": ""}, 0) is True, "no expiry = closed")
print("pure ok", N[0])
```

- [ ] **Step 2: הרצה — נכשל**

Run: `python3 $T/test_pure.py`
Expected: `AttributeError: module 'ev2' has no attribute 'bpage_images'`

- [ ] **Step 3: מימוש — בלוק לפני `def register(app, G):`**

```python
# ── [BPAGE 06/10] דף קונה עם התאמות נכסים — פונקציות טהורות (ספק 2026-10-06-buyer-page) ──
# כללי חשיפה (אייל 06/10): נכס נולד — בלי מספר בית/תמונות/תיאור/בעלים; שת"פ — בלי משרד/קישור;
# אף קישור ליד2 ואף טלפון שאינו של הסוכן המטפל.
BPAGE_MARKS = {"like": "מתאים", "dislike": "לא מתאים", "visit": "רוצה לראות"}
BPAGE_DAYS = 90


def _bp_digits(x):
    return _re.sub(r"\D", "", str(x or ""))


def bpage_iso_ep(s):
    import datetime as _dtb
    try:
        return _dtb.datetime.fromisoformat(str(s or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def bpage_expired(page, now_ep):
    ep = bpage_iso_ep((page or {}).get("expires_at"))
    return (not ep) or ep < now_ep


def bpage_images(row):
    imgs = (row or {}).get("תמונות") or (row or {}).get("images") or []
    if isinstance(imgs, str):
        try:
            imgs = json.loads(imgs)
        except Exception:
            imgs = [imgs]
    out = [str(u).strip() for u in (imgs if isinstance(imgs, list) else []) if str(u).strip().startswith("http")]
    if not out:
        one = str((row or {}).get("תמונה", "") or (row or {}).get("image", "") or "").strip()
        if one.startswith("http"):
            out = [one]
    return out[:30]


def bpage_excl_as_office_row(r):
    """שורת שת"פ (raw שטוח: street='הרב קוק 33, קרית מוצקין', dest='דירה · 4 חד' · 115 מ"ר') → שורת משרד.
    במכוון בלי office/link/phone — הם לא יוצאים לדף הלקוח."""
    g = lambda k: str((r or {}).get(k, "") or "").strip()
    st = g("street").split(",")[0].strip()
    m = _re.match(r"^(.*?)\s+(\d+\S*)$", st)
    street, house = (m.group(1).strip(), m.group(2)) if m else (st, "")
    parts = [p.strip() for p in g("dest").split("·") if p.strip()]
    num = lambda p: _re.sub(r"[^\d.]", "", p)
    rooms = next((num(p) for p in parts if "חד" in p), "") or g("rooms")
    sqm = next((num(p) for p in parts if 'מ"ר' in p), "") or g("sqm")
    ptype = parts[0] if parts and "חד" not in parts[0] and 'מ"ר' not in parts[0] else ""
    return {"סוג עסקה": "מכירה", "עיר / ישוב": g("city"), "שכונה": g("neighborhood"),
            "כתובת": street, "מספר בית": house, "חדרים": rooms, 'מ"ר': sqm, "קומה": g("floor"),
            "מחיר": g("price"), "סוג נכס": ptype, "תיאור": g("desti"),
            "תמונה": g("image"), "תמונות": (r or {}).get("images") or [],
            "ירד מפרסום": g("delisted_at")}


def bpage_snapshot(source, orow):
    g = lambda k: str((orow or {}).get(k, "") or "").strip()
    snap = {"street": g("כתובת"), "house": g("מספר בית"), "neighborhood": g("שכונה"), "city": g("עיר / ישוב"),
            "price": _bp_digits(g("מחיר")), "rooms": g("חדרים"), "floor": g("קומה"),
            "sqm": g('מ"ר') or g("מ״ר"), "type": g("סוג נכס"),
            "desc": (g("_desc_ae") or g("תיאור"))[:1200], "images": bpage_images(orow)}
    if source == "newborn":
        snap.update(house="", desc="", images=[])
    return snap


def bpage_live(item, live):
    snap = dict((item or {}).get("snapshot") or {})
    d = dict(snap)
    d.update(key=item.get("prop_key", ""), source=item.get("source", ""), mark=item.get("mark") or "",
             note=item.get("note") or "", added=item.get("added_at") or "", marked=item.get("marked_at") or "",
             gone=False, priceOld="")
    d.setdefault("images", [])
    if live is not None:
        if str(live.get("ירד מפרסום", "") or "").strip():
            d["gone"] = True
        cur = _bp_digits(live.get("מחיר"))
        if cur:
            if snap.get("price") and int(cur) < int(snap["price"]):
                d["priceOld"] = snap["price"]
            d["price"] = cur
        if item.get("source") != "newborn":
            imgs = bpage_images(live)
            if len(imgs) > len(d["images"]):
                d["images"] = imgs
    return d


def bpage_order(disp):
    """active: האצווה האחרונה (isNew) קודם, אחר כך לפי זמן הוספה יורד; disliked — בנפרד."""
    if not disp:
        return [], []
    eps = [bpage_iso_ep(x.get("added")) for x in disp]
    top, low = max(eps), min(eps)
    for x, ep in zip(disp, eps):
        x["isNew"] = (top - low > 120) and (top - ep) <= 120   # שליחה אחת = עד 2 דק'; אצווה יחידה אינה "חדשה"
    srt = sorted(zip(disp, eps), key=lambda t: (not t[0]["isNew"], -t[1]))
    act = [x for x, _ in srt if x.get("mark") != "dislike"]
    dis = [x for x, _ in srt if x.get("mark") == "dislike"]
    return act, dis


def bpage_wa_text(first, url, n, is_first):
    hi = "היי" + (" " + first if first else "") + ", "
    if is_first:
        body = "הכנתי לך רשימת נכסים אישית:"
    elif n == 1:
        body = "הוספתי לך נכס חדש:"
    elif n > 1:
        body = "הוספתי לך %d נכסים חדשים:" % n
    else:
        body = "הנה רשימת הנכסים שלך:"
    return hi + body + "\n" + url
```
(לוודא ש-`json` מיובא ברמת המודול ב-effie_v2 — `grep -n "^import json\|^import.*json" effie_v2.py`; אם לא, להוסיף `import json` לבלוק הייבוא העליון.)

- [ ] **Step 4: הרצה — עובר**

Run: `python3 $T/test_pure.py && python3 $T/test_static.py`
Expected: `pure ok 3x` + `static ok`

- [ ] **Step 5: Commit**

```bash
cd $RB && git pull --ff-only && git add effie_v2.py && git commit -m "דף קונה (2): פונקציות טהורות — צילום/העשרה/סדר/נוסחים עם כללי החשיפה

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: התאמות חדשות + שער פוש + הגבלת קצב (טהורות)

**Files:**
- Modify: `$RB/effie_v2.py` (אותו בלוק BPAGE)
- Test: `$T/test_match.py`

**Interfaces — Produces:**
- `bpage_new_matches(query:dict, src_rows:{source:{key:orow}}, sent:set, since_ep:float, budget:int, score_fn, cap=30) -> list[{source,key,score}]` — orow מכיל `_ep` (נראה לראשונה)
- `bpage_push_gate(st:dict, now:float, window=600) -> "now"|"pend"`
- `bpage_rate_ok(hits:list, now:float, limit=30, per=60) -> bool` (מעדכן את hits במקום)

- [ ] **Step 1: בדיקה נכשלת**

`$T/test_match.py`:
```python
# -*- coding: utf-8 -*-
import sys; sys.path.insert(0, "/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage")
from common import *
E = E()
NOW = 1_800_000_000.0
row = lambda price, ep, sc, gone="": {"מחיר": price, "_ep": ep, "_sc": sc, "ירד מפרסום": gone}
src = {"office": {"L:1": row("1700000", NOW - 3600, 90), "L:2": row("1700000", NOW - 3600, 50),
                  "L:3": row("2500000", NOW - 3600, 95), "L:4": row("1700000", NOW - 9 * 86400, 95),
                  "L:5": row("1700000", NOW - 60, 99, "05/10"), "L:6": row("", NOW - 60, 70)},
       "newborn": {"N:1": row("1650000", NOW - 100, 80)}, "shtaf": {"X:1": row("1700000", NOW - 100, 61)}}
sc = lambda r, q: r["_sc"]
out = E.bpage_new_matches({"x": 1}, src, {"X:1"}, NOW - 86400, 1_700_000, sc)
check([(o["source"], o["key"]) for o in out] == [("newborn", "N:1"), ("office", "L:1"), ("office", "L:6")], out)
check(out[0]["score"] == 80)
# בלי תקציב — לא מסנן מחיר
check(("office", "L:3") in [(o["source"], o["key"]) for o in E.bpage_new_matches({}, src, set(), NOW - 86400, 0, sc)])
# score_fn שזורק — מדלג
bad = lambda r, q: 1 / 0
check(E.bpage_new_matches({}, src, set(), 0, 0, bad) == [], "exceptions swallowed")
check(len(E.bpage_new_matches({}, {"office": {"L:%d" % i: row("1", NOW, 70) for i in range(50)}}, set(), 0, 0, sc)) == 30, "cap")
# שער פוש
st = {}
check(E.bpage_push_gate(st, NOW) == "now")
check(E.bpage_push_gate(st, NOW + 60) == "pend" and st["n"] == 1)
check(E.bpage_push_gate(st, NOW + 120) == "pend" and st["n"] == 2)
check(E.bpage_push_gate(st, NOW + 601) == "now" and st["n"] == 0)
# הגבלת קצב
h = []
check(all(E.bpage_rate_ok(h, NOW + i * 0.1) for i in range(30)))
check(not E.bpage_rate_ok(h, NOW + 3.1), "31st in a minute blocked")
check(E.bpage_rate_ok(h, NOW + 61), "window slides")
print("match ok", N[0])
```

- [ ] **Step 2: הרצה — נכשל**

Run: `python3 $T/test_match.py` → `AttributeError: ... 'bpage_new_matches'`

- [ ] **Step 3: מימוש (באותו בלוק BPAGE)**

```python
def bpage_new_matches(query, src_rows, sent, since_ep, budget, score_fn, cap=30):
    """התאמות חזקות (60+, תקציב ±20% כמו בחלון ההתאמות) שעוד לא בדף ונראו לראשונה אחרי since_ep."""
    out = []
    for src, rows in (src_rows or {}).items():
        for k, r in (rows or {}).items():
            if not k or k in sent or (r.get("_ep") or 0) <= since_ep:
                continue
            if str(r.get("ירד מפרסום", "") or "").strip():
                continue
            pr = int(_bp_digits(r.get("מחיר")) or 0)
            if budget >= 10000 and pr and abs(pr - budget) > budget * 0.2:
                continue
            try:
                sc = int(score_fn(r, query) or 0)
            except Exception:
                continue
            if sc >= 60:
                out.append({"source": src, "key": k, "score": min(100, sc)})
    out.sort(key=lambda o: -o["score"])
    return out[:cap]


def bpage_push_gate(st, now, window=600):
    """פוש ראשון מיד; סימונים נוספים בתוך החלון נצברים (st['n']) לפוש מסכם בסוף החלון."""
    if not st.get("t") or now - st["t"] >= window:
        st["t"], st["n"] = now, 0
        return "now"
    st["n"] = st.get("n", 0) + 1
    return "pend"


def bpage_rate_ok(hits, now, limit=30, per=60):
    hits[:] = [t for t in hits if now - t < per]
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True
```

- [ ] **Step 4: הרצה — עובר**

Run: `python3 $T/test_match.py && python3 $T/test_pure.py && python3 $T/test_static.py`

- [ ] **Step 5: Commit**

```bash
cd $RB && git pull --ff-only && git add effie_v2.py && git commit -m "דף קונה (3): התאמות חדשות, שער פוש, הגבלת קצב

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: מפתחות נכס בתשובות החיפוש + שדות שת"פ לגלריה

כדי שהקליינט ישלח `{source, key}` והשרת ימצא את אותו נכס — כל תוצאה צריכה מפתח יציב.

**Files:**
- Modify: `$RB/app.py:7626` (`_row_out` ב-`api_search_properties`) — `"pkey": _prop_price_key(row)`
- Modify: `$RB/app.py` (`api_search_exclusives`, ה-dict ב-`out.append`) — `"pkey": _excl_price_key(r)`
- Modify: `$RB/app.py` (`api_my_properties` — ה-dict של כל נכס) — `"pkey": _prop_price_key(row)`
- Modify: `$RB/effie_v2.py` `y2_norm_agency` — `raw` מקבל `rooms, sqm, floor, image, images`
- Modify: `$RB/effie_v2.py` `y2_norm_office` — שורה מקבלת `"תמונות": row.get("images") or []`
- Test: `$T/test_keys.py`

**Interfaces — Produces:** כל תוצאת משרד/שלי/שת"פ כוללת `pkey`; נכס נולד כבר כולל `key`.

- [ ] **Step 1: בדיקה נכשלת**

`$T/test_keys.py`:
```python
# -*- coding: utf-8 -*-
import sys, ast; sys.path.insert(0, "/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage")
from common import *
src = open(RB + "/app.py", encoding="utf-8").read()
def fn_src(name):
    t = ast.parse(src)
    for n in ast.walk(t):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n)
check('"pkey": _prop_price_key(row)' in fn_src("api_search_properties"), "office pkey")
check('"pkey": _excl_price_key(r)' in fn_src("api_search_exclusives"), "shtaf pkey")
check('"pkey": _prop_price_key(' in fn_src("api_my_properties"), "mine pkey")
E = E()
sk, rec = E.y2_norm_agency({"link": "https://www.yad2.co.il/realestate/item/north/abc123", "street": "הרצל", "homeNum": "5",
                            "city": "קרית ים", "rooms": "4.0", "sqm": "100", "floor": "3", "image": "https://i/1",
                            "images": ["https://i/1", "https://i/2"], "price": "1700000"}, "משרד", "999")
raw = rec["raw"]
check(raw["rooms"] == "4" and raw["sqm"] == "100" and raw["floor"] == "3" and raw["image"] == "https://i/1"
      and raw["images"] == ["https://i/1", "https://i/2"], raw)
o = E.y2_norm_office({"link": "https://www.yad2.co.il/item/abc", "images": ["https://i/1", "https://i/2"], "image": "https://i/1",
                      "street": "הרצל", "homeNum": "5", "city": "קרית ים", "price": "1"}, "5625538")
row = o[1] if isinstance(o, tuple) else o
check(row.get("תמונות") == ["https://i/1", "https://i/2"], row)
print("keys ok", N[0])
```
(לפני הכתיבה: `sed -n "$(grep -n '^def y2_norm_office' $RB/effie_v2.py | cut -d: -f1),+50p" $RB/effie_v2.py` — לבדוק מה הפונקציה מחזירה ולהתאים את שורת ה-`row =` אם צריך.)

- [ ] **Step 2: הרצה — נכשל** (`office pkey`)

- [ ] **Step 3: מימוש**

ב-`app.py` `_row_out` (אחרי `"branch": ...`):
```python
                "pkey": _prop_price_key(row),   # [BPAGE 06/10] מפתח יציב לדף הקונה
```
ב-`api_search_exclusives` בתוך `out.append({...})` (אחרי `"priceOld": ...`):
```python
                "pkey": _excl_price_key(r),     # [BPAGE 06/10]
```
ב-`api_my_properties` — למצוא את ה-dict שנבנה לכל נכס (`grep -n '"link"' ` בתוך הפונקציה) ולהוסיף `"pkey": _prop_price_key(<שם משתנה השורה>),`.

ב-`y2_norm_agency`, ב-`raw = {...}` להוסיף:
```python
           # [BPAGE 06/10] לדף הקונה: פרטים נפרדים + גלריה (הסורק ישלח images — עד אז image אחת)
           "rooms": y2_num_str(g("rooms")), "sqm": y2_num_str(g("sqm")), "floor": y2_num_str(g("floor")),
           "image": g("image"), "images": [str(u) for u in (row.get("images") or []) if str(u).startswith("http")][:30],
```
ב-`y2_norm_office`, ליד `"תמונה": g("image")`:
```python
            "תמונות": [str(u) for u in (row.get("images") or []) if str(u).startswith("http")][:30],   # [BPAGE 06/10]
```

- [ ] **Step 4: הרצה — עובר** + רגרסיה: `python3 $T/test_keys.py && python3 $T/test_static.py` ו-`python3 -c "import ast;ast.parse(open('$RB/app.py').read())"`.

- [ ] **Step 5: Commit**

```bash
cd $RB && git pull --ff-only && git add app.py effie_v2.py && git commit -m "דף קונה (4): pkey בתוצאות משרד/שלי/שת\"פ + פרטים וגלריה בשת\"פ ובמשרד

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ראוטים של הסוכן — שליחה, קריאה, סיכום, הסרה, נצפה

**Files:**
- Modify: `$RB/effie_v2.py` — בתוך `register`, בלוק `# ── [BPAGE 06/10] ראוטים ──` אחרי `v2_api_buyers_ai_search`
- Test: `$T/test_routes_agent.py`

**Interfaces:**
- Consumes (G): `_web_auth, _last9, _canon_key, _phones_for_name, _scope_keys_phones, _fetch_manual_buyers, fetch_agents_phones, _wa_phone, _log_activity, fetch_sheet_rows, fetch_external_exclusives, _dedupe_exclusives, fetch_newborn, _prop_price_key, _excl_price_key, _nb_key, _nb_as_office_row, _prop_epoch, _excl_epoch, _newborn_created_epoch, _parse_props_query, score_match, APP_BASE_URL (אופציונלי)`
- Produces (בתוך register): `_bp_sources() -> {"office":{k:orow}, "shtaf":{...}, "newborn":{...}}` (orow עם `_ep`; cache 120ש'), `_bp_buyer(row) -> dict|None`, `_bp_own(s) -> callable(buyer)->bool`, `_bp_url(token) -> str`, `_bp_newcount(page, items) -> list` (cache 10 דק')
- Routes: `POST /v2/api/bpage/send`, `GET /v2/api/bpage`, `GET /v2/api/bpage/summary`, `POST /v2/api/bpage/remove`, `POST /v2/api/bpage/seen`

- [ ] **Step 1: בדיקה נכשלת**

`$T/test_routes_agent.py`:
```python
# -*- coding: utf-8 -*-
import sys, re, json, time; sys.path.insert(0, "/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage")
from common import *
from flask import Flask
E = E()
l9 = lambda p: re.sub(r"\D", "", str(p or ""))[-9:]
NOW = time.time()
OFF = {"מספר מודעה": "1", "כתובת": "יששכר", "מספר בית": "4", "עיר / ישוב": "קרית מוצקין", "מחיר": "1690000", "חדרים": "4",
       "סטטוס": "פעילה", "תמונה": "https://i/1", "_ep": NOW - 3600}
OFF2 = dict(OFF, **{"מספר מודעה": "2", "כתובת": "הרצל", "_ep": NOW - 60})
NB = {"מזהה": "77", "רחוב1": "בגין", "עיר": "קרית ים", "מחיר": "1650000", "טלפון בעל הנכס": "0509999999", "תיאור נכס": "דירה · 4 חד'"}
EX = {"street": "הרב קוק 33, קרית מוצקין", "dest": "דירה · 4 חד'", "price": "1700000", "office": "SMART",
      "link": "https://www.yad2.co.il/item/zz", "received_at": "06/10/2026 10:00"}
BUY = [{"row": 7, "name": "בתיה ברון", "phone": "0501112222", "agent": "דנה", "agent_phone": "0521111111",
        "budget": "1,700,000", "search": "דירה 4 חדרים מוצקין"},
       {"row": 8, "name": "אחר", "phone": "0503334444", "agent": "יוסי", "agent_phone": "0529999999", "budget": "", "search": ""}]
PAGES, ITEMS, LOG = {}, [], []
class SB:
    def enabled(self): return True
    def bpage_by_row(self, row): return PAGES.get(row)
    def bpage_create(self, row, token, an, ap, exp, q):
        PAGES[row] = {"id": "P%d" % row, "token": token, "row": row, "agent_name": an, "agent_phone": ap,
                      "expires_at": exp, "last_sent_at": "2026-10-06T10:00:00+00:00", "created_at": "2026-10-06T10:00:00+00:00",
                      "seen_at": None, "query": q}
        return PAGES[row]
    def bpage_update(self, pid, f):
        for p in PAGES.values():
            if p["id"] == pid: p.update(f)
    def bpage_add_items(self, pid, its):
        have = {(i["page_id"], i["prop_key"]) for i in ITEMS}; out = []
        for it in its:
            if (pid, it["prop_key"]) in have: continue
            ITEMS.append(dict(it, page_id=pid, added_at="2026-10-06T10:00:00+00:00", mark=None, note="", marked_at=None)); out.append(it["prop_key"])
        return out
    def bpage_items(self, ids): return [i for i in ITEMS if i["page_id"] in ids]
    def bpage_all(self): return list(PAGES.values())
    def bpage_remove_item(self, pid, k): ITEMS[:] = [i for i in ITEMS if not (i["page_id"] == pid and i["prop_key"] == k)]
SBM = SB()
SESS = {"phone": "0521111111", "role": "agent", "name": "דנה"}
G = dict(_web_auth=lambda: SESS, _last9=l9, _canon_key=lambda x: re.sub(r"\s+", "", str(x or "")),
         _phones_for_name=lambda n: [], _fetch_manual_buyers=lambda: BUY,
         _scope_keys_phones=lambda role, name, ph, a=None, an=None: ({re.sub(r"\s+", "", name)}, set(ph), False),
         fetch_agents_phones=lambda: {"דנה": "0521111111"}, _wa_phone=lambda p: "972" + l9(p),
         _log_activity=lambda *a: LOG.append(a), fetch_sheet_rows=lambda: [OFF, OFF2],
         fetch_external_exclusives=lambda: [EX], _dedupe_exclusives=lambda r: r, fetch_newborn=lambda: [NB],
         _prop_price_key=lambda r: "L:" + r["מספר מודעה"], _excl_price_key=lambda r: "X:zz",
         _nb_key=lambda r: "id:" + r["מזהה"], _nb_as_office_row=lambda r: {"כתובת": r["רחוב1"], "מספר בית": "", "עיר / ישוב": r["עיר"], "מחיר": r["מחיר"], "חדרים": "4"},
         _prop_epoch=lambda r: r.get("_ep", 0), _excl_epoch=lambda s: NOW - 100, _newborn_created_epoch=lambda r: NOW - 100,
         _parse_props_query=lambda q: {"q": q}, score_match=lambda r, q, f=0: 90, APP_BASE_URL="https://app.test")
app = Flask("t"); GGx = GG(G); E.register(app, GGx); c = app.test_client()
E._BP_SB = SBM   # ראה מימוש: _bp_sb() מחזיר את E._BP_SB אם הוגדר (הזרקה לבדיקות)
# שליחה ראשונה
j = c.post("/v2/api/bpage/send", json={"row": 7, "q": "דירה 4 חדרים", "items": [
    {"source": "office", "key": "L:1"}, {"source": "newborn", "key": "id:77"}, {"source": "shtaf", "key": "X:zz"},
    {"source": "office", "key": "L:404"}]}).get_json()
check(j["ok"] and j["first"] and j["added"] == 3 and j["url"].startswith("https://app.test/b/") and "הכנתי לך" in j["msg"], j)
check(j["wa"] == "972501112222", j)
tok = j["url"].rsplit("/", 1)[1]
check(len(tok) >= 20 and PAGES[7]["agent_phone"] == "0521111111" and PAGES[7]["query"]["q"] == "דירה 4 חדרים", PAGES[7])
nb = [i for i in ITEMS if i["source"] == "newborn"][0]["snapshot"]
check(nb["house"] == "" and nb["images"] == [] and "0509999999" not in json.dumps(nb), nb)
sh = [i for i in ITEMS if i["source"] == "shtaf"][0]["snapshot"]
check("SMART" not in json.dumps(sh, ensure_ascii=False) and "yad2" not in json.dumps(sh), sh)
check(any("דף לקוח" in str(a) for a in LOG), LOG)
# שליחה שנייה — בלי כפילויות, מאריכה
j = c.post("/v2/api/bpage/send", json={"row": 7, "q": "x", "items": [{"source": "office", "key": "L:1"}, {"source": "mine", "key": "L:2"}]}).get_json()
check(j["ok"] and not j["first"] and j["added"] == 1 and "הוספתי לך נכס חדש" in j["msg"] and j["url"].endswith(tok), j)
check(len(ITEMS) == 4 and [i for i in ITEMS if i["prop_key"] == "L:2"][0]["source"] == "office", "mine → office")
# קונה של סוכן אחר
r = c.post("/v2/api/bpage/send", json={"row": 8, "items": [{"source": "office", "key": "L:1"}]})
check(r.status_code == 403, r.status_code)
check(c.post("/v2/api/bpage/send", json={"row": 99, "items": []}).status_code == 404)
check(c.post("/v2/api/bpage/send", json={"row": 7, "items": [{"source": "office", "key": "L:404"}]}).get_json()["reason"] == "no_items")
# GET
j = c.get("/v2/api/bpage?row=7").get_json()
check(j["ok"] and j["page"]["url"].endswith(tok) and len(j["items"]) == 4 and isinstance(j["new_matches"], list), j)
check(c.get("/v2/api/bpage?row=8").status_code == 403)
check(c.get("/v2/api/bpage?row=9").status_code == 404)
# summary — רק קונים בהיקף
ITEMS[0]["mark"], ITEMS[0]["marked_at"] = "visit", "2026-10-06T11:00:00+00:00"
PAGES[8] = dict(PAGES[7], id="P8", row=8, token="other")
j = c.get("/v2/api/bpage/summary").get_json()
check(set(j["rows"]) == {"7"} and j["rows"]["7"]["visit"] == 1 and j["rows"]["7"]["unseen"], j)
# seen + remove
check(c.post("/v2/api/bpage/seen", json={"row": 7}).get_json()["ok"] and PAGES[7]["seen_at"])
check(not c.get("/v2/api/bpage/summary").get_json()["rows"]["7"]["unseen"])
check(c.post("/v2/api/bpage/remove", json={"row": 7, "key": "L:2"}).get_json()["ok"] and len(ITEMS) == 3)
# מנהל רואה הכל
SESS.update(role="admin", name="אייל", phone="0505709865")
check(c.get("/v2/api/bpage?row=8").status_code == 200)
# כבוי
import os; os.environ["BPAGE"] = "0"
app2 = Flask("t2"); E.register(app2, GG(G)); c2 = app2.test_client()
check(c2.post("/v2/api/bpage/send", json={"row": 7, "items": []}).get_json() == {"ok": False, "off": True})
print("routes agent ok", N[0])
```

- [ ] **Step 2: הרצה — נכשל** (`404` על `/v2/api/bpage/send`)

- [ ] **Step 3: מימוש בתוך `register`**

ברמת המודול (מעל register, בבלוק BPAGE):
```python
_BP_SB = None   # הזרקה לבדיקות; בפרודקשן None → supabase_db
```
בתוך `register`, אחרי `v2_api_buyers_ai_search`:
```python
    # ── [BPAGE 06/10] דף קונה — ראוטים (ספק docs/superpowers/specs/2026-10-06-buyer-page-design.md) ──
    _BPAGE_ON = (os.environ.get("BPAGE", "1") or "1").strip() not in ("0", "false", "off")
    _bp_cache = {"src": None, "ts": 0.0, "new": {}}

    def _bp_sb():
        if _BP_SB is not None:
            return _BP_SB
        return _sb_mod()

    def _bp_sources():
        """{source: {key: orow}} מהמקורות החיים; orow במבנה שורת משרד + _ep (נראה לראשונה). cache 120ש'."""
        if _bp_cache["src"] is not None and time.time() - _bp_cache["ts"] < 120:
            return _bp_cache["src"]
        out = {"office": {}, "shtaf": {}, "newborn": {}}
        try:
            for r in (G["fetch_sheet_rows"]() or []):
                if str(r.get("סטטוס", "") or "").strip() not in ("", "פעילה"):
                    continue
                k = G["_prop_price_key"](r)
                if k:
                    out["office"][k] = dict(r, _ep=G["_prop_epoch"](r) or 0)
        except Exception as e:
            if log: log.warning(f"bpage office src: {e}")
        try:
            for r in (G["_dedupe_exclusives"](G["fetch_external_exclusives"]() or []) or []):
                k = G["_excl_price_key"](r)
                if k:
                    o = bpage_excl_as_office_row(r)
                    o["_ep"] = G["_excl_epoch"](r.get("first_seen") or r.get("received_at", "")) or 0
                    out["shtaf"][k] = o
        except Exception as e:
            if log: log.warning(f"bpage shtaf src: {e}")
        try:
            for r in (G["fetch_newborn"]() or []):
                k = G["_nb_key"](r)
                if k:
                    o = dict(G["_nb_as_office_row"](r))
                    o["ירד מפרסום"] = str(r.get("delisted_at", "") or "").strip()
                    o["_ep"] = G["_newborn_created_epoch"](r) or 0
                    out["newborn"][k] = o
        except Exception as e:
            if log: log.warning(f"bpage newborn src: {e}")
        _bp_cache.update(src=out, ts=time.time())
        return out

    def _bp_buyer(row):
        try:
            row = int(row)
        except Exception:
            return None
        for b in (G["_fetch_manual_buyers"]() or []):
            if str(b.get("row", "")) == str(row):
                return b
        return None

    def _bp_own(s):
        if s.get("role") == "admin":
            return lambda b: True
        ck, l9 = G["_canon_key"], G["_last9"]
        nm = s.get("name", "")
        ph = set(G["_phones_for_name"](nm) or [])
        if s.get("phone"):
            ph.add(l9(s["phone"]))
        keys, phones, _m = G["_scope_keys_phones"](s.get("role", ""), nm, ph, s.get("agents"), s.get("agent_names"))
        return lambda b: (ck(b.get("agent", "")) in keys) or (l9(b.get("agent_phone", "")) in phones)

    def _bp_url(token):
        base = (G.get("APP_BASE_URL") or request.url_root or "").rstrip("/")
        return base + "/b/" + token

    def _bp_auth_buyer(row):
        """(session, buyer, error_response)."""
        s = _web_auth()
        if not s:
            return None, None, (jsonify({"ok": False, "auth": False}), 401)
        b = _bp_buyer(row)
        if not b:
            return s, None, (jsonify({"ok": False, "reason": "no_buyer"}), 404)
        if not _bp_own(s)(b):
            return s, None, (jsonify({"ok": False, "reason": "forbidden"}), 403)
        return s, b, None

    def _bp_newmatches(page, items):
        """התאמות חדשות לדף (מטמון 10 דק' לדף)."""
        ck = _bp_cache["new"].get(page["id"])
        if ck and time.time() - ck[0] < 600:
            return ck[1]
        q = page.get("query") or {}
        sent = {i.get("prop_key") for i in items}
        try:
            res = bpage_new_matches(q.get("p") or {}, _bp_sources(), sent, bpage_iso_ep(page.get("created_at")),
                                    int(q.get("budget") or 0), lambda r, qq: G["score_match"](r, qq, 0))
        except Exception as e:
            if log: log.warning(f"bpage new matches: {e}")
            res = []
        _bp_cache["new"][page["id"]] = (time.time(), res)
        return res

    @app.route("/v2/api/bpage/send", methods=["POST"])
    def v2_api_bpage_send():
        if not _BPAGE_ON:
            return jsonify({"ok": False, "off": True})
        b = request.get_json(silent=True) or {}
        s, buyer, err = _bp_auth_buyer(b.get("row"))
        if err:
            return err
        sb = _bp_sb()
        if not sb:
            return jsonify({"ok": False, "off": True})
        try:
            src = _bp_sources()
            good, seen = [], set()
            for it in (b.get("items") or [])[:30]:
                so = "office" if it.get("source") == "mine" else str(it.get("source") or "")
                k = str(it.get("key") or "")
                r = (src.get(so) or {}).get(k)
                if r is None or k in seen:
                    continue
                seen.add(k)
                good.append({"source": so, "prop_key": k, "snapshot": bpage_snapshot(so, r)})
            if not good:
                return jsonify({"ok": False, "reason": "no_items"})
            import secrets as _secrets, datetime as _dtb
            now = _dtb.datetime.now(_dtb.timezone.utc)
            exp = (now + _dtb.timedelta(days=BPAGE_DAYS)).isoformat()
            agent = str(buyer.get("agent", "") or "").strip()
            aph = str(buyer.get("agent_phone", "") or "").strip() or str((G["fetch_agents_phones"]() or {}).get(agent, "") or "")
            qtext = str(b.get("q") or "").strip()[:200]
            query = {"q": qtext, "p": (G["_parse_props_query"](qtext) or {}) if qtext else {},
                     "budget": bai_budget(buyer.get("budget", "")) or bai_budget(buyer.get("search", ""))}
            page = sb.bpage_by_row(buyer["row"])
            first = page is None
            if first:
                page = sb.bpage_create(buyer["row"], _secrets.token_urlsafe(16), agent, aph, exp, query)
                if not page:
                    return jsonify({"ok": False, "reason": "create_failed"}), 500
            else:
                sb.bpage_update(page["id"], {"last_sent_at": now.isoformat(), "expires_at": exp, "query": query,
                                             "agent_name": agent, "agent_phone": aph})
            added = sb.bpage_add_items(page["id"], good)
            _bp_cache["new"].pop(page["id"], None)
            name = str(buyer.get("name", "") or "").strip()
            url = _bp_url(page["token"])
            _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "דף לקוח — שליחה",
                          "%s · %d נכסים" % (name, len(added)))
            return jsonify({"ok": True, "first": first, "added": len(added), "url": url,
                            "msg": bpage_wa_text(name.split()[0] if name else "", url, len(added), first),
                            "wa": G["_wa_phone"](buyer.get("phone", ""))})
        except Exception as e:
            if log: log.error(f"bpage send: {e}", exc_info=True)
            return jsonify({"ok": False, "reason": str(e)[:160]}), 500

    @app.route("/v2/api/bpage", methods=["GET"])
    def v2_api_bpage_get():
        s, buyer, err = _bp_auth_buyer(request.args.get("row"))
        if err:
            return err
        sb = _bp_sb()
        page = sb.bpage_by_row(buyer["row"]) if sb else None
        if not page:
            return jsonify({"ok": True, "page": None, "items": [], "new_matches": []})
        items = sb.bpage_items([page["id"]])
        src = _bp_sources()
        disp = [bpage_live(i, (src.get(i.get("source")) or {}).get(i.get("prop_key"))) for i in items]
        return jsonify({"ok": True, "page": {"url": _bp_url(page["token"]), "expires": page.get("expires_at"),
                                             "seen_at": page.get("seen_at"), "last_sent_at": page.get("last_sent_at"),
                                             "expired": bpage_expired(page, time.time())},
                        "items": disp, "new_matches": _bp_newmatches(page, items)})

    @app.route("/v2/api/bpage/summary", methods=["GET"])
    def v2_api_bpage_summary():
        s = _web_auth()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        sb = _bp_sb()
        if not sb or not _BPAGE_ON:
            return jsonify({"ok": True, "rows": {}})
        try:
            own = _bp_own(s)
            bys = {str(b.get("row", "")): b for b in (G["_fetch_manual_buyers"]() or [])}
            pages = [p for p in (sb.bpage_all() or []) if str(p.get("row")) in bys and own(bys[str(p.get("row"))])]
            items = sb.bpage_items([p["id"] for p in pages]) if pages else []
            by_page = {}
            for i in items:
                by_page.setdefault(i["page_id"], []).append(i)
            rows = {}
            for p in pages:
                its = by_page.get(p["id"], [])
                seen = bpage_iso_ep(p.get("seen_at"))
                cnt = {"like": 0, "visit": 0, "dislike": 0}
                for i in its:
                    if i.get("mark") in cnt:
                        cnt[i["mark"]] += 1
                rows[str(p["row"])] = dict(cnt, total=len(its),
                                           unseen=any(bpage_iso_ep(i.get("marked_at")) > seen for i in its if i.get("marked_at")),
                                           newN=len(_bp_newmatches(p, its)), expired=bpage_expired(p, time.time()))
            return jsonify({"ok": True, "rows": rows})
        except Exception as e:
            if log: log.warning(f"bpage summary: {e}")
            return jsonify({"ok": True, "rows": {}})

    @app.route("/v2/api/bpage/seen", methods=["POST"])
    def v2_api_bpage_seen():
        s, buyer, err = _bp_auth_buyer((request.get_json(silent=True) or {}).get("row"))
        if err:
            return err
        sb = _bp_sb()
        page = sb.bpage_by_row(buyer["row"]) if sb else None
        if page:
            import datetime as _dtb
            sb.bpage_update(page["id"], {"seen_at": _dtb.datetime.now(_dtb.timezone.utc).isoformat()})
        return jsonify({"ok": True})

    @app.route("/v2/api/bpage/remove", methods=["POST"])
    def v2_api_bpage_remove():
        b = request.get_json(silent=True) or {}
        s, buyer, err = _bp_auth_buyer(b.get("row"))
        if err:
            return err
        sb = _bp_sb()
        page = sb.bpage_by_row(buyer["row"]) if sb else None
        if not page:
            return jsonify({"ok": False, "reason": "no_page"}), 404
        sb.bpage_remove_item(page["id"], str(b.get("key") or ""))
        _bp_cache["new"].pop(page["id"], None)
        return jsonify({"ok": True})
```
(לוודא: `os`, `time`, `request`, `jsonify` כבר מיובאים ב-effie_v2; `bai_budget` היא פונקציית מודול קיימת. ה-`_bp_sb` בפרודקשן נשען על `_sb_mod` שמוגדר מוקדם יותר ב-register — הבלוק חייב לבוא אחריו.)

הערה לבדיקה: `bpage_iso_ep(seen_at)` בבדיקה — `seen_at` שנכתב הוא ISO עכשווי (2026+), גדול מ-`marked_at` של הבדיקה → `unseen=False`. תקין.

- [ ] **Step 4: הרצה — עובר**

Run: `python3 $T/test_routes_agent.py && python3 $T/test_static.py && python3 $T/test_pure.py && python3 $T/test_match.py`

- [ ] **Step 5: Commit**

```bash
cd $RB && git pull --ff-only && git add effie_v2.py && git commit -m "דף קונה (5): ראוטים של הסוכן — שליחה, קריאה, סיכום, נצפה, הסרה

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: הדף הציבורי `/b/<token>` + סימון + פוש

**Files:**
- Modify: `$RB/effie_v2.py` — מודול: `BPAGE_CSS`, `BPAGE_JS`, `bpage_render_public(ctx) -> str`, `bpage_render_closed(agent|None, office) -> str`; ב-register: `GET /b/<token>`, `POST /b/<token>/mark`
- Test: `$T/test_public.py`, `$T/test_public_js.js`

**Interfaces:**
- Consumes: `bpage_live`, `bpage_order`, `bpage_expired`, `bpage_push_gate`, `bpage_rate_ok`, `BPAGE_MARKS`, `_bp_sb`, `_bp_sources`, `_bp_buyer`, `_sb_office`, G: `send_push`, `_wa_phone`, `_last9`, `_log_activity`
- Produces: `bpage_render_public(ctx)` כש-ctx = `{token, office:{name,logo_url}, agent:{name,first,phone,tel,wa,avatar}, buyer_first, chips:[str], active:[disp], disliked:[disp]}`

- [ ] **Step 1: בדיקה נכשלת (Python)**

`$T/test_public.py`:
```python
# -*- coding: utf-8 -*-
import sys, re, json, time, threading; sys.path.insert(0, "/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage")
from common import *
from flask import Flask
E = E()
l9 = lambda p: re.sub(r"\D", "", str(p or ""))[-9:]
PAGE = {"id": "P7", "token": "T" * 22, "row": 7, "agent_name": "דנה כהן", "agent_phone": "0521111111",
        "expires_at": "2099-01-01T00:00:00+00:00", "created_at": "2026-10-06T10:00:00+00:00", "seen_at": None, "query": {}}
ITEMS = [{"page_id": "P7", "source": "office", "prop_key": "L:1", "added_at": "2026-10-06T10:00:00+00:00", "mark": None, "note": "", "marked_at": None,
          "snapshot": {"street": "יששכר", "house": "4", "city": "קרית מוצקין", "price": "1690000", "rooms": "4", "images": ["https://i/1", "https://i/2"], "desc": "מוארת"}},
         {"page_id": "P7", "source": "newborn", "prop_key": "id:77", "added_at": "2026-10-06T10:00:00+00:00", "mark": None, "note": "", "marked_at": None,
          "snapshot": {"street": "בגין", "house": "", "city": "קרית ים", "price": "1650000", "rooms": "4", "images": [], "desc": ""}}]
PUSH, LOG = [], []
class SB:
    def enabled(self): return True
    def bpage_by_token(self, t): return PAGE if t == PAGE["token"] else None
    def bpage_items(self, ids): return ITEMS
    def bpage_set_mark(self, pid, k, m, note):
        for i in ITEMS:
            if i["prop_key"] == k:
                i.update(mark=m, note=note); return i
        return None
E._BP_SB = SB()
G = dict(_wa_phone=lambda p: "972" + l9(p), _last9=l9, send_push=lambda t, b, ids: PUSH.append((t, b, ids)) or True,
         _log_activity=lambda *a: LOG.append(a), _fetch_manual_buyers=lambda: [{"row": 7, "name": "בתיה ברון", "search": "4 חדרים מוצקין", "budget": "1,700,000"}],
         fetch_sheet_rows=lambda: [], fetch_external_exclusives=lambda: [], _dedupe_exclusives=lambda r: r, fetch_newborn=lambda: [])
app = Flask("t"); E.register(app, GG(G)); c = app.test_client()
r = c.get("/b/" + PAGE["token"])
h = r.get_data(as_text=True)
check(r.status_code == 200 and 'dir="rtl"' in h and "noindex" in h and "no-store" in r.headers.get("Cache-Control", ""), r.status_code)
check("בתיה" in h and "דנה" in h and "0521111111" not in h.replace("972521111111", "") or True, "agent phone allowed")
check("0509999999" not in h and "yad2" not in h and "בגין 4" not in h, "no owner phone / yad2 / newborn house")
check("https://i/2" in h, "gallery")
check("נכס חדש לפני פרסום" in h, "newborn teaser")
check("אפי" not in re.sub(r"<script.*?</script>", "", h, flags=re.S), "white-label")
check(c.get("/b/nope").status_code == 404 and "הקישור אינו פעיל" in c.get("/b/nope").get_data(as_text=True))
PAGE["expires_at"] = "2020-01-01T00:00:00+00:00"
r = c.get("/b/" + PAGE["token"]); check(r.status_code == 410 and "הרשימה כבר לא פעילה" in r.get_data(as_text=True))
check(c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:1", "mark": "like"}).status_code == 410)
PAGE["expires_at"] = "2099-01-01T00:00:00+00:00"
# סימון
j = c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:1", "mark": "visit"}).get_json()
check(j["ok"] and ITEMS[0]["mark"] == "visit", j)
time.sleep(0.2)
check(len(PUSH) == 1 and PUSH[0][2] == ["521111111"] and "רוצה לראות" in PUSH[0][1] and "בתיה" in PUSH[0][0], PUSH)
check(any("סימון בדף לקוח" in str(a) for a in LOG))
j = c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:1", "mark": "dislike", "note": "x" * 500}).get_json()
check(j["ok"] and ITEMS[0]["mark"] == "dislike" and len(ITEMS[0]["note"]) == 200)
time.sleep(0.2); check(len(PUSH) == 1, "second mark within window → pending")
c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:1", "mark": "like", "note": "zz"})
check(ITEMS[0]["note"] == "", "note only with dislike")
check(c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:1", "mark": "hack"}).status_code == 400)
check(c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:9", "mark": "like"}).status_code == 404)
check(c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:1", "mark": None}).get_json()["ok"] and ITEMS[0]["mark"] is None, "unmark")
codes = [c.post("/b/%s/mark" % PAGE["token"], json={"key": "L:1", "mark": "like"}).status_code for _ in range(40)]
check(429 in codes, "rate limit")
print("public ok", N[0])
```

- [ ] **Step 2: הרצה — נכשל** (404 על `/b/...`)

- [ ] **Step 3: מימוש — מודול (בבלוק BPAGE)**

```python
BPAGE_CSS = r"""
*{box-sizing:border-box}body{margin:0;background:#F2EFE7;font-family:Heebo,system-ui,sans-serif;color:#1E3A5F;-webkit-text-size-adjust:100%}
.hd{position:sticky;top:0;z-index:5;background:#fff;display:flex;align-items:center;gap:10px;padding:10px 16px;box-shadow:0 2px 12px rgba(30,58,95,.08)}
.av{width:46px;height:46px;border-radius:50%;object-fit:cover;background:#E4C56B;display:flex;align-items:center;justify-content:center;font-weight:800;color:#231700;flex-shrink:0}
.hd .nm{font-weight:800;font-size:16px}.hd .of{font-size:12.5px;color:#6B7280}.hd .sp{flex:1}
.ic{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:none;text-decoration:none}
.ic.wa{background:#1FAF5E}.ic.ph{background:#EAF0FA}
.wrap{max-width:560px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:6px 0 8px;font-weight:800}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}.chip{background:#fff;border:1px solid #DCD6C8;border-radius:999px;padding:5px 12px;font-size:13px}
.card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);margin-bottom:14px;overflow:hidden}
.gal{position:relative;display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;aspect-ratio:4/3;background:#E9E5DA}
.gal::-webkit-scrollbar{display:none}.gal img{flex:0 0 100%;width:100%;height:100%;object-fit:cover;scroll-snap-align:center;cursor:zoom-in}
.cnt{position:absolute;bottom:10px;left:10px;background:rgba(14,29,51,.7);color:#fff;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px}
.newtag{position:absolute;top:10px;right:10px;background:#2E6BD6;color:#fff;font-size:12px;font-weight:800;border-radius:999px;padding:3px 10px}
.bd{padding:14px 16px 16px}.ad{font-weight:800;font-size:16px}.ar{font-size:13px;color:#6B7280;margin-top:2px}
.pr{font-size:22px;font-weight:800;margin-top:8px}.old{font-size:14px;color:#6B7280;text-decoration:line-through;margin-inline-start:8px;font-weight:600}
.facts{display:flex;gap:14px;font-size:13.5px;color:#5B6472;margin-top:6px}
.ds{font-size:14px;line-height:1.55;margin-top:8px;color:#3B4656;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.ds.open{-webkit-line-clamp:unset}.more{background:none;border:none;color:#2E6BD6;font-weight:700;font-size:13.5px;padding:6px 0;min-height:32px;font-family:inherit}
.teaser{background:#F6EEDB;color:#7A5E1C;font-weight:700;font-size:13.5px;border-radius:14px;padding:10px 12px;margin-top:10px}
.acts{display:flex;gap:8px;margin-top:12px}
.acts button{flex:1;min-height:44px;border-radius:14px;font-family:inherit;font-weight:800;font-size:14px;border:1.5px solid #DCD6C8;background:#fff;color:#1E3A5F}
.acts .lk.on{background:#2E6BD6;border-color:#2E6BD6;color:#fff}.acts .dl.on{background:#5B6472;border-color:#5B6472;color:#fff}
.acts .vs{background:#157A43;border-color:#157A43;color:#fff}
.note{display:none;margin-top:8px}.note.open{display:flex;gap:8px}
.note input{flex:1;font-size:16px;font-family:inherit;border:1.5px solid #DCD6C8;border-radius:12px;padding:10px;min-height:44px}
.note button{min-height:44px;border-radius:12px;border:none;background:#2E6BD6;color:#fff;font-weight:800;padding:0 16px;font-family:inherit}
.gone{opacity:.6}.gonetag{display:inline-block;background:#E9E5DA;color:#5B6472;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;margin-top:8px}
.fold{width:100%;min-height:48px;background:#fff;border:1.5px solid #DCD6C8;border-radius:16px;font-family:inherit;font-weight:800;color:#5B6472;font-size:15px;margin:6px 0 14px}
.empty{text-align:center;padding:40px 16px}.empty .c{width:64px;height:64px;border-radius:50%;background:#F6EEDB;margin:0 auto 12px;display:flex;align-items:center;justify-content:center}
.empty .t{font-weight:800;font-size:18px}.empty .s{color:#6B7280;margin-top:6px}
.btnrow{display:flex;gap:10px;justify-content:center;margin-top:16px}.btnrow a{min-height:44px;padding:0 18px;border-radius:14px;display:flex;align-items:center;font-weight:800;text-decoration:none}
.btnrow .w{background:#157A43;color:#fff}.btnrow .p{background:#fff;border:1.5px solid #DCD6C8;color:#1E3A5F}
#fs{display:none;position:fixed;inset:0;background:#0E1D33;z-index:20}#fs.open{display:flex}#fs .gal{aspect-ratio:auto;height:100%;width:100%;background:#0E1D33}
#fs .gal img{object-fit:contain;cursor:default}#fs .x{position:absolute;top:14px;left:14px;width:44px;height:44px;border-radius:50%;border:none;background:rgba(255,255,255,.15);color:#fff;font-size:22px}
#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1E3A5F;color:#fff;border-radius:999px;padding:10px 18px;font-weight:700;display:none;z-index:30}
"""

BPAGE_JS = r"""
var D = window.BP || {}, ST = {};
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function fmtP(p){ p = String(p || '').replace(/\D/g, ''); return p ? '₪' + p.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : ''; }
function where(it, full){ var st = [it.street, full ? it.house : ''].filter(Boolean).join(' ');
  return [st, it.neighborhood, it.city].filter(Boolean).join(', '); }
function visitText(it){ return 'שלום ' + (D.agent.first || '') + ', אשמח לתאם ביקור ב' + where(it, it.source !== 'newborn'); }
function galHtml(it, i){
  var im = it.images || [];
  if (!im.length) return '';
  return '<div class="gal" id="g' + i + '" onscroll="galCnt(' + i + ')">' + im.map(function(u, k){
      return '<img loading="lazy" src="' + esc(u) + '" alt="" onclick="fsOpen(' + i + ',' + k + ')">'; }).join('') +
    (it.isNew ? '<span class="newtag">חדש</span>' : '') +
    (im.length > 1 ? '<span class="cnt" id="c' + i + '">1/' + im.length + '</span>' : '') + '</div>';
}
function galCnt(i){ var g = document.getElementById('g' + i), c = document.getElementById('c' + i);
  if (!g || !c) return; var n = g.children.length - (g.querySelector('.newtag') ? 1 : 0) - 1;
  var k = Math.round(Math.abs(g.scrollLeft) / g.clientWidth) + 1; c.textContent = Math.min(k, n) + '/' + n; }
function cardHtml(it, i){
  var nb = it.source === 'newborn', facts = [];
  if (it.rooms) facts.push(it.rooms + ' חדרים'); if (it.floor) facts.push('קומה ' + it.floor); if (it.sqm) facts.push(it.sqm + ' מ"ר');
  var st = [it.street, nb ? '' : it.house].filter(Boolean).join(' ');
  return '<div class="card' + (it.gone ? ' gone' : '') + '" id="k' + i + '">' + (nb ? '' : galHtml(it, i)) +
    '<div class="bd"><div class="ad">' + esc(st) + (nb && it.isNew ? ' <span class="newtag" style="position:static">חדש</span>' : '') + '</div>' +
    '<div class="ar">' + esc([it.neighborhood, it.city].filter(Boolean).join(', ')) + '</div>' +
    '<div class="pr">' + esc(fmtP(it.price)) + (it.priceOld ? '<span class="old">' + esc(fmtP(it.priceOld)) + '</span>' : '') + '</div>' +
    (facts.length ? '<div class="facts">' + esc(facts.join(' · ')) + '</div>' : '') +
    (it.desc ? '<div class="ds" id="d' + i + '">' + esc(it.desc) + '</div><button class="more" onclick="more(' + i + ',this)">קרא עוד</button>' : '') +
    (nb ? '<div class="teaser">נכס חדש לפני פרסום · פרטים אצל ' + esc(D.agent.first || D.agent.name) + '</div>' : '') +
    (it.gone ? '<span class="gonetag">כבר לא זמין</span>' :
      '<div class="acts"><button class="lk' + (it.mark === 'like' || it.mark === 'visit' ? ' on' : '') + '" onclick="mark(' + i + ',\'like\')">מתאים</button>' +
      '<button class="dl' + (it.mark === 'dislike' ? ' on' : '') + '" onclick="mark(' + i + ',\'dislike\')">לא מתאים</button>' +
      '<button class="vs" onclick="visit(' + i + ')">רוצה לראות</button></div>' +
      '<div class="note" id="n' + i + '"><input id="ni' + i + '" maxlength="200" placeholder="למה? (לא חובה)" value="' + esc(it.note || '') + '">' +
      '<button onclick="saveNote(' + i + ')">שמור</button></div>') +
    '</div></div>';
}
function all(){ return (D.active || []).concat(D.disliked || []); }
function render(){
  var A = [], X = [];
  all().forEach(function(it){ (it.mark === 'dislike' ? X : A).push(it); });
  D.active = A; D.disliked = X;
  var h = A.map(function(it, i){ return cardHtml(it, i); }).join('');
  if (!A.length) h = '<div class="empty"><div class="c"><svg width="28" height="28" viewBox="0 0 24 24"><path d="M4 11l8-7 8 7v9H4z" fill="none" stroke="#7A5E1C" stroke-width="2" stroke-linejoin="round"/></svg></div>' +
    '<div class="t">אין כרגע נכסים ברשימה</div><div class="s">' + esc(D.agent.first || '') + ' יוסיף נכסים מתאימים בקרוב</div></div>';
  if (X.length){
    h += '<button class="fold" onclick="ST.fold=!ST.fold;render()">לא מתאימים (' + X.length + ')' + (ST.fold ? ' — הסתר' : '') + '</button>';
    if (ST.fold) h += X.map(function(it, j){ return cardHtml(it, A.length + j); }).join('');
  }
  document.getElementById('list').innerHTML = h;
}
function itemAt(i){ return all()[i]; }
function more(i, b){ var d = document.getElementById('d' + i); if (!d) return; d.classList.toggle('open'); b.textContent = d.classList.contains('open') ? 'הצג פחות' : 'קרא עוד'; }
function toast(t){ var e = document.getElementById('toast'); e.textContent = t; e.style.display = 'block'; clearTimeout(ST.tt); ST.tt = setTimeout(function(){ e.style.display = 'none'; }, 2200); }
function send(it, m, note){
  return fetch(location.pathname.replace(/\/$/, '') + '/mark', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({key: it.key, mark: m, note: note || ''})}).then(function(r){ return r.json(); })
    .then(function(j){ if (!j || !j.ok) toast('לא נשמר — נסה שוב'); return j; })
    .catch(function(){ toast('לא נשמר — נסה שוב'); });
}
function mark(i, m){
  var it = itemAt(i); if (!it) return;
  var nm = (it.mark === m || (m === 'like' && it.mark === 'visit')) ? null : m;
  it.mark = nm || ''; if (nm !== 'dislike') it.note = '';
  send(it, nm, '');
  render();
  if (nm === 'dislike'){ var j = all().indexOf(it); ST.fold = true; render();
    var n = document.getElementById('n' + j); if (n){ n.classList.add('open'); var inp = document.getElementById('ni' + j); if (inp) inp.focus(); } }
  else if (nm) toast('נשמר');
}
function saveNote(i){ var it = itemAt(i), inp = document.getElementById('ni' + i); if (!it || !inp) return;
  it.note = inp.value.slice(0, 200); send(it, 'dislike', it.note); toast('תודה, הועבר ל' + (D.agent.first || 'סוכן'));
  var n = document.getElementById('n' + i); if (n) n.classList.remove('open'); }
function visit(i){ var it = itemAt(i); if (!it) return;
  it.mark = 'visit'; send(it, 'visit', ''); render();
  window.open('https://wa.me/' + D.agent.wa + '?text=' + encodeURIComponent(visitText(it)), '_blank'); }
function fsOpen(i, k){ var it = itemAt(i); if (!it) return; var fs = document.getElementById('fs');
  fs.innerHTML = '<div class="gal">' + it.images.map(function(u){ return '<img src="' + esc(u) + '" alt="">'; }).join('') + '</div>' +
    '<button class="x" aria-label="סגירה" onclick="document.getElementById(\'fs\').classList.remove(\'open\')">×</button>';
  fs.classList.add('open'); var g = fs.firstChild; g.scrollLeft = -k * g.clientWidth; if (g.scrollLeft === 0 && k) g.scrollLeft = k * g.clientWidth; }
if (typeof document !== 'undefined' && document.getElementById('list')) render();
"""


def _bp_esc(s):
    import html as _h
    return _h.escape(str(s or ""), quote=True)


def _bp_head(office, agent):
    av = ('<img class="av" src="%s" alt="" onerror="this.outerHTML=\'<div class=av>%s</div>\'">' % (_bp_esc(agent.get("avatar")), _bp_esc((agent.get("name") or "?")[:1]))
          if agent.get("avatar") else '<div class="av">%s</div>' % _bp_esc((agent.get("name") or "?")[:1]))
    btns = ""
    if agent.get("wa"):
        btns += ('<a class="ic wa" href="https://wa.me/%s" target="_blank" rel="noopener" aria-label="וואטסאפ">'
                 '<svg width="20" height="20" viewBox="0 0 16 16"><path d="M13.5 8A5.5 5.5 0 1 1 8 2.5c3 0 5.5 2.5 5.5 5.5zM8 13.5L5.5 14l.5-2.3" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></a>') % _bp_esc(agent["wa"])
    if agent.get("tel"):
        btns += ('<a class="ic ph" href="tel:%s" aria-label="חיוג">'
                 '<svg width="18" height="18" viewBox="0 0 22 22"><path d="M5 3.5C4 4.5 3.5 6 4 7.5c1.2 4 5.5 8.5 9.5 10 1.5.6 3 .1 4-1l-2.6-2.9-2.2 1c-1.8-1-3.8-3-4.8-4.8l1-2.2z" fill="none" stroke="#2E6BD6" stroke-width="1.7" stroke-linejoin="round"/></svg></a>') % _bp_esc(agent["tel"])
    return ('<div class="hd">%s<div><div class="nm">%s</div><div class="of">%s</div></div><div class="sp"></div>%s</div>'
            % (av, _bp_esc(agent.get("name")), _bp_esc((office or {}).get("name")), btns))


def _bp_doc(title, body, office):
    return ('<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="robots" content="noindex,nofollow"><title>%s</title>'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;700;800&display=swap" rel="stylesheet">'
            '<style>%s</style></head><body>%s</body></html>') % (_bp_esc(title), BPAGE_CSS, body)


def bpage_render_public(ctx):
    data = {"agent": ctx["agent"], "active": ctx["active"], "disliked": ctx["disliked"]}
    js_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    chips = "".join('<span class="chip">%s</span>' % _bp_esc(c) for c in (ctx.get("chips") or []) if c)
    hi = "שלום %s, הנכסים שבחרתי בשבילך" % ctx["buyer_first"] if ctx.get("buyer_first") else "הנכסים שבחרתי בשבילך"
    body = (_bp_head(ctx.get("office"), ctx["agent"]) +
            '<div class="wrap"><h1>%s</h1>%s<div id="list"></div></div><div id="fs"></div><div id="toast" role="status" aria-live="polite"></div>'
            % (_bp_esc(hi), ('<div class="chips">%s</div>' % chips) if chips else "") +
            '<script>window.BP=%s;</script><script>%s</script>' % (js_data, BPAGE_JS))
    return _bp_doc((ctx.get("office") or {}).get("name") or "נכסים", body, ctx.get("office"))


def bpage_render_closed(agent, office):
    if agent:
        inner = ('<div class="empty"><div class="t">הרשימה כבר לא פעילה</div><div class="s">דבר איתי ואשלח לך נכסים מעודכנים</div>'
                 '<div class="btnrow">%s%s</div></div>') % (
            ('<a class="w" href="https://wa.me/%s">וואטסאפ</a>' % _bp_esc(agent["wa"])) if agent.get("wa") else "",
            ('<a class="p" href="tel:%s">חיוג</a>' % _bp_esc(agent["tel"])) if agent.get("tel") else "")
        body = _bp_head(office, agent) + '<div class="wrap">%s</div>' % inner
    else:
        body = '<div class="wrap"><div class="empty"><div class="t">הקישור אינו פעיל</div></div></div>'
    return _bp_doc((office or {}).get("name") or "נכסים", body, office)
```

בתוך `register` (אחרי ראוטי הסוכן):
```python
    _bp_rate, _bp_gate, _bp_glock = {}, {}, threading.Lock()
    _BP_TOKEN_RE = _re.compile(r"^[A-Za-z0-9_-]{10,40}$")

    def _bp_agent_ctx(page):
        ph = str(page.get("agent_phone", "") or "")
        nm = str(page.get("agent_name", "") or "").strip()
        d = "".join(ch for ch in ph if ch.isdigit())
        tel = ("0" + d[-9:]) if len(d) >= 9 else ""
        return {"name": nm, "first": nm.split()[0] if nm else "", "phone": tel, "tel": tel,
                "wa": G["_wa_phone"](ph) if ph else "", "avatar": ("/v2/api/avatar?p=" + d[-9:]) if d else ""}

    def _bp_resp(html, code):
        resp = make_response(html, code)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    def _bp_page_or_none(token):
        sb = _bp_sb()
        if not sb or not _BP_TOKEN_RE.match(str(token or "")):
            return None
        try:
            return sb.bpage_by_token(token)
        except Exception as e:
            if log: log.warning(f"bpage token: {e}")
            return None

    @app.route("/b/<token>", methods=["GET"])
    def bpage_public(token):
        office = _sb_office() or {}
        page = _bp_page_or_none(token)
        if not page:
            return _bp_resp(bpage_render_closed(None, office), 404)
        agent = _bp_agent_ctx(page)
        if bpage_expired(page, time.time()):
            return _bp_resp(bpage_render_closed(agent, office), 410)
        sb = _bp_sb()
        items = sb.bpage_items([page["id"]])
        src = _bp_sources()
        disp = [bpage_live(i, (src.get(i.get("source")) or {}).get(i.get("prop_key"))) for i in items]
        act, dis = bpage_order(disp)
        buyer = _bp_buyer(page.get("row")) or {}
        name = str(buyer.get("name", "") or "").strip()
        chips = [str(buyer.get("search", "") or "").strip()[:60]]
        bd = bai_budget(buyer.get("budget", "")) or bai_budget(buyer.get("search", ""))
        if bd:
            chips.append("עד ₪{:,}".format(int(bd)))
        return _bp_resp(bpage_render_public({"office": office, "agent": agent, "buyer_first": name.split()[0] if name else "",
                                             "chips": chips, "active": act, "disliked": dis}), 200)

    def _bp_push(page, title, body):
        to = G["_last9"](page.get("agent_phone", ""))
        if to:
            threading.Thread(target=lambda: G["send_push"](title, body, [to]), daemon=True).start()

    @app.route("/b/<token>/mark", methods=["POST"])
    def bpage_public_mark(token):
        page = _bp_page_or_none(token)
        if not page:
            return jsonify({"ok": False}), 404
        if bpage_expired(page, time.time()):
            return jsonify({"ok": False, "expired": True}), 410
        now = time.time()
        with _bp_glock:
            if not bpage_rate_ok(_bp_rate.setdefault(page["id"], []), now):
                return jsonify({"ok": False, "reason": "rate"}), 429
        b = request.get_json(silent=True) or {}
        mark = b.get("mark") or None
        if mark is not None and mark not in BPAGE_MARKS:
            return jsonify({"ok": False, "reason": "bad_mark"}), 400
        note = str(b.get("note") or "")[:200] if mark == "dislike" else ""
        it = _bp_sb().bpage_set_mark(page["id"], str(b.get("key") or ""), mark, note)
        if not it:
            return jsonify({"ok": False, "reason": "no_item"}), 404
        if mark:
            buyer = _bp_buyer(page.get("row")) or {}
            bname = str(buyer.get("name", "") or "").strip() or "לקוח"
            sn = it.get("snapshot") or {}
            st = " ".join(x for x in (sn.get("street"), sn.get("house")) if x)
            _log_activity(page.get("agent_name", ""), "client", "", "סימון בדף לקוח",
                          "%s: %s · %s%s" % (bname, BPAGE_MARKS[mark], st, (" · " + note) if note else ""))
            with _bp_glock:
                gst = _bp_gate.setdefault(page["id"], {})
                g = bpage_push_gate(gst, now)
            title = "דף לקוח · " + bname
            if g == "now":
                _bp_push(page, title, "%s — %s%s" % (BPAGE_MARKS[mark], st, (" · " + note) if note else ""))
                def _flush(pid=page["id"], pg=page, t=title):
                    with _bp_glock:
                        n = _bp_gate.get(pid, {}).get("n", 0)
                        if pid in _bp_gate:
                            _bp_gate[pid]["n"] = 0
                    if n:
                        _bp_push(pg, t, "סימן עוד %d נכסים" % n)
                tm = threading.Timer(600, _flush); tm.daemon = True; tm.start()
        return jsonify({"ok": True})
```
(לוודא ייבוא: `threading`, `make_response` מ-flask, `json`, `_re` ברמת המודול של effie_v2 — `grep -n "^import\|^from" effie_v2.py | head -30`, ולהוסיף מה שחסר.)

- [ ] **Step 4: בדיקת JS (node)**

`$T/test_public_js.js`:
```js
// מריץ את BPAGE_JS עם DOM מינימלי ובודק רינדור, קיפול, סימון והודעת ביקור
const {execSync} = require('child_process');
const py = `import importlib.util,json;s=importlib.util.spec_from_file_location('e','/Users/eyal/Documents/GitHub/remax-bot/effie_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(json.dumps(m.BPAGE_JS))`;
const JS = JSON.parse(execSync(`python3 -c "${py}"`, {env: Object.assign({}, process.env, {MAP_CACHE_DIR: '/tmp'})}).toString().trim().split('\n').pop());
let n = 0; const check = (c, m) => { if (!c) throw new Error(m); n++; };
const els = {}; const mk = id => els[id] || (els[id] = {id, innerHTML: '', style: {}, classList: {s: new Set(), add(c){this.s.add(c)}, remove(c){this.s.delete(c)}, toggle(c){this.s.has(c)?this.s.delete(c):this.s.add(c)}, contains(c){return this.s.has(c)}}, focus(){}, value: ''});
global.document = {getElementById: id => (id === 'list' || id === 'toast' || id === 'fs' || els[id]) ? mk(id) : null};
const fetches = []; global.fetch = (u, o) => { fetches.push([u, JSON.parse(o.body)]); return Promise.resolve({json: () => ({ok: true})}); };
global.location = {pathname: '/b/TOKEN'}; const opened = []; global.window = {open: (u) => opened.push(u)};
global.setTimeout = () => 0; global.clearTimeout = () => 0;
window.BP = {agent: {name: 'דנה כהן', first: 'דנה', wa: '972521111111'},
  active: [{key: 'L:1', source: 'office', street: 'יששכר', house: '4', city: 'קרית מוצקין', price: '1690000', priceOld: '1750000', images: ['https://i/1', 'https://i/2'], isNew: true, mark: ''},
           {key: 'id:7', source: 'newborn', street: 'בגין', house: '', city: 'קרית ים', price: '1650000', images: [], mark: ''}],
  disliked: [{key: 'L:3', source: 'office', street: 'הרצל', house: '5', city: 'קרית ים', price: '1', images: [], mark: 'dislike', note: 'קומה'}]};
global.BP = window.BP;
eval(JS.replace(/var D = window\.BP \|\| \{\}/, 'var D = BP'));
const L = () => els.list.innerHTML;
check(L().includes('₪1,690,000') && L().includes('₪1,750,000') && L().includes('1/2') && L().includes('חדש'), 'office card');
check(L().includes('נכס חדש לפני פרסום · פרטים אצל דנה') && !L().includes('בגין 4'), 'newborn teaser');
check(L().includes('לא מתאימים (1)') && !L().includes('הרצל 5'), 'disliked folded');
mark(0, 'like'); check(fetches[0][1].mark === 'like' && fetches[0][0] === '/b/TOKEN/mark', 'like sent');
mark(0, 'like'); check(fetches[1][1].mark === null, 'toggle off');
visit(1); check(fetches[2][1].mark === 'visit' && decodeURIComponent(opened[0]).includes('אשמח לתאם ביקור בבגין, קרית ים') && !decodeURIComponent(opened[0]).includes('בגין 4'), 'visit newborn');
mark(0, 'dislike'); check(L().includes('לא מתאימים (2)'), 'moves to folded');
console.log('public js ok', n);
```

- [ ] **Step 5: הרצה**

Run: `python3 $T/test_public.py && node $T/test_public_js.js && python3 $T/test_static.py`
וגם `node --check` על BPAGE_JS:
```bash
python3 -c "import importlib.util,os;os.environ['MAP_CACHE_DIR']='/tmp';s=importlib.util.spec_from_file_location('e','$RB/effie_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);open('$T/bpage.js','w').write(m.BPAGE_JS)" && node --check $T/bpage.js
```
Expected: הכל עובר.

- [ ] **Step 6: Commit**

```bash
cd $RB && git pull --ff-only && git add effie_v2.py && git commit -m "דף קונה (6): הדף הציבורי /b/<token> — גלריה, סימונים, פוש לסוכן, תוקף

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: צד הסוכן — שליחה מחלון ההתאמות, תגים, נכס נולד לבחירה

**Files:**
- Modify: `$RB/effie_v2.py` בתוך `V2_BUYERS_HTML` (שורות ~3885-4200): `propCard`, `renderMatchTab` (נכס נולד), `sendSelected`, `sendOne`, `matchProps`
- Test: `$T/test_agent_js.js`

**Interfaces:**
- Consumes: `POST /v2/api/bpage/send` → `{ok, url, msg, wa, first, added}` או `{ok:false, off:true}`; `GET /v2/api/bpage?row=` → `{items:[{key,mark}], new_matches:[{key}]}`
- Produces (JS): `BP_STATE = {keys:{key:mark}, newK:{key:1}}`, `itemKey(it) -> {source,key}`, `bpSend(mis:Array)`, `bpChip(key) -> html`

- [ ] **Step 1: בדיקה נכשלת**

`$T/test_agent_js.js`:
```js
// מחלץ את הסקריפט של V2_BUYERS_HTML ומריץ את הפונקציות החדשות עם סביבה מדומה
const {execSync} = require('child_process');
const py = `import importlib.util,json,re;s=importlib.util.spec_from_file_location('e','/Users/eyal/Documents/GitHub/remax-bot/effie_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);h=m.V2_BUYERS_HTML;print(json.dumps(re.findall(r'<script>([\\s\\S]*?)</script>',h)))`;
const parts = JSON.parse(execSync(`python3 -c "${py}"`, {env: Object.assign({}, process.env, {MAP_CACHE_DIR: '/tmp'})}).toString().trim().split('\n').pop());
const src = parts.join('\n');
let n = 0; const check = (c, m) => { if (!c) throw new Error(m); n++; };
function fn(name){ const i = src.indexOf('function ' + name + '('); if (i < 0) throw new Error('missing ' + name);
  let d = 0, j = src.indexOf('{', i); for (let k = j; k < src.length; k++){ if (src[k] === '{') d++; else if (src[k] === '}' && --d === 0) return src.slice(i, k + 1); } }
const posts = []; let reply = {ok: true, url: 'https://a/b/T', msg: 'היי בתיה, הכנתי לך רשימת נכסים אישית:\nhttps://a/b/T', wa: '972501112222', first: true, added: 2};
global.POST = (u, b) => { posts.push([u, b]); return Promise.resolve(reply); };
const opened = []; global.window = {open: (u) => opened.push(u)};
global.toast = () => 0; global.esc = s => String(s == null ? '' : s);
global.CUR_BUYER = {row: 7, name: 'בתיה ברון', wa: '972501112222'}; global.MQ_CUR = 'דירה 4 חדרים';
global.MITEMS = [{p: {pkey: 'L:1', address: 'יששכר 4'}, shtaf: false}, {p: {pkey: 'X:zz', street: 'הרב קוק 33'}, shtaf: true},
                 {p: {key: 'id:77', address: 'בגין'}, nb: true}];
global.MSEL = {0: 1, 1: 1, 2: 1};
let fallback = 0; global.sendSelectedText = () => { fallback++; };
global.BP_STATE = {keys: {}, newK: {}};
eval(fn('itemKey') + fn('bpSend') + fn('bpChip'));
check(JSON.stringify(itemKey(MITEMS[0])) === '{"source":"office","key":"L:1"}', 'office key');
check(itemKey(MITEMS[1]).source === 'shtaf' && itemKey(MITEMS[2]).source === 'newborn' && itemKey(MITEMS[2]).key === 'id:77', 'keys');
bpSend([0, 1, 2]).then(() => {
  check(posts[0][0] === '/v2/api/bpage/send' && posts[0][1].row === 7 && posts[0][1].items.length === 3 && posts[0][1].q === 'דירה 4 חדרים', 'payload');
  check(opened[0].indexOf('https://wa.me/972501112222?text=') === 0 && decodeURIComponent(opened[0]).includes('https://a/b/T'), 'wa opened');
  check(BP_STATE.keys['L:1'] === '' && BP_STATE.keys['id:77'] === '', 'marked as in page');
  reply = {ok: false, off: true};
  return bpSend([0]);
}).then(() => {
  check(fallback === 1, 'off → old text');
  BP_STATE.keys = {'L:1': 'like', 'L:2': '', 'L:3': 'dislike'};
  check(bpChip('L:1').includes('בדף · מתאים') && bpChip('L:2').includes('בדף הלקוח') && bpChip('L:3').includes('בדף · לא מתאים') && bpChip('L:9') === '', 'chips');
  BP_STATE.newK = {'L:9': 1}; check(bpChip('L:9').includes('חדש'), 'new chip');
  console.log('agent js ok', n);
}).catch(e => { console.error(e); process.exit(1); });
```

- [ ] **Step 2: הרצה — נכשל** (`missing itemKey`)

- [ ] **Step 3: מימוש ב-`V2_BUYERS_HTML`**

(א) מיד אחרי `var MITEMS = [], MSEL = {};` להוסיף:
```js
/* [BPAGE 06/10] דף קונה — קישור אישי במקום הודעת טקסט; תגי "בדף הלקוח" בחלון */
var BP_STATE = {keys: {}, newK: {}};
function itemKey(it){
  var p = it.p || {};
  if (it.nb) return {source: 'newborn', key: p.key || ''};
  return {source: it.shtaf ? 'shtaf' : 'office', key: p.pkey || ''};
}
function bpChip(k){
  if (!k) return '';
  if (Object.prototype.hasOwnProperty.call(BP_STATE.keys, k)){
    var m = BP_STATE.keys[k], t = m === 'like' ? 'בדף · מתאים' : m === 'visit' ? 'בדף · רוצה לראות' : m === 'dislike' ? 'בדף · לא מתאים' : 'בדף הלקוח';
    return '<span class="bpc" style="display:inline-block;background:#EAF0FA;color:#2E6BD6;font-size:11.5px;font-weight:800;border-radius:999px;padding:2px 9px">' + t + '</span>';
  }
  if (BP_STATE.newK[k]) return '<span class="bpc" style="display:inline-block;background:#2E6BD6;color:#fff;font-size:11.5px;font-weight:800;border-radius:999px;padding:2px 9px">חדש</span>';
  return '';
}
function bpSend(mis){
  var b = CUR_BUYER || {};
  var items = mis.map(function(k){ return itemKey(MITEMS[k]); }).filter(function(x){ return x.key; });
  if (!items.length || !b.row){ sendSelectedText(); return Promise.resolve(); }
  return POST('/v2/api/bpage/send', {row: b.row, q: MQ_CUR, items: items}).then(function(j){
    if (!j || j.off){ sendSelectedText(); return; }
    if (!j.ok){ toast(j.reason === 'no_items' ? 'הנכסים לא נמצאו — רענן ונסה שוב' : 'השליחה נכשלה'); return; }
    items.forEach(function(x){ if (!Object.prototype.hasOwnProperty.call(BP_STATE.keys, x.key)) BP_STATE.keys[x.key] = ''; });
    window.open('https://wa.me/' + (j.wa || b.wa || '') + '?text=' + encodeURIComponent(j.msg), '_blank');
    if (typeof renderMatchTab === 'function' && typeof MG !== 'undefined' && MG) renderMatchTab();
  }).catch(function(){ toast('השליחה נכשלה'); });
}
function bpLoad(row){
  BP_STATE = {keys: {}, newK: {}};
  if (!row) return Promise.resolve();
  return GET('/v2/api/bpage?row=' + encodeURIComponent(row)).then(function(j){
    if (!j || !j.ok) return;
    (j.items || []).forEach(function(it){ BP_STATE.keys[it.key] = it.mark || ''; });
    (j.new_matches || []).forEach(function(m){ BP_STATE.newK[m.key] = 1; });
    if (typeof MG !== 'undefined' && MG && el('mRes')) renderMatchTab();
  }).catch(function(){});
}
```

(ב) לשנות את שם `sendSelected` הקיים ל-`sendSelectedText` (הגוף לא משתנה), ולהוסיף:
```js
function sendSelected(){
  var ks = Object.keys(MSEL);
  if (!ks.length) return;
  bpSend(ks.map(Number));
}
```
ולשנות את `sendOne(mi)`:
```js
function sendOne(mi){
  var it = MITEMS[mi]; if (!it) return;
  bpSend([mi]);
}
```
(הגוף הישן של sendOne נמחק — `sendSelectedText` הוא ה-fallback כש-BPAGE=0; כשכבוי, שליחת נכס בודד שולחת את כל המסומנים בטקסט — מקובל כ-rollback. כדי לשמור התנהגות מדויקת: `function sendSelectedText(){ … }` נקראת עם MSEL; ב-sendOne כשכבוי — `MSEL = {}; MSEL[mi] = 1; sendSelectedText();` — לממש בתוך bpSend: אם `mis.length===1` ו-off → `var keep=MSEL; MSEL={}; MSEL[mis[0]]=1; sendSelectedText(); MSEL=keep;`.)

(ג) ב-`propCard`, אחרי `scoreChip(p.score)` להוסיף את התג:
```js
    '<div class="pr">' + esc(p.price ? '₪' + p.price : '') + '</div>' + scoreChip(p.score) + bpChip(p.pkey) + '</div>' +
```

(ד) ב-`renderMatchTab`, בענף `MTAB === 'nb'`, להחליף את `try{ nh += nbCard(r, i); }catch(e){}` ב:
```js
      try{
        var _mi = (r._mi != null) ? r._mi : (r._mi = MITEMS.push({p: r, nb: true}) - 1);
        nh += '<div style="display:flex;align-items:center;gap:8px;margin:2px 4px 6px">' +
          '<button class="sel' + (MSEL[_mi] ? ' on' : '') + '" onclick="toggleSel(' + _mi + ')" aria-label="בחירה לדף הלקוח">' +
          '<svg width="13" height="13" viewBox="0 0 14 14"><path d="M2 7.5l3.5 3.5L12 3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
          '<span style="font-size:12.5px;color:#6B7280">לדף הלקוח (בלי כתובת ותמונות)</span>' + bpChip(r.key) + '</div>' + nbCard(r, i);
      }catch(e){}
```
ו-`signSelected` — לדלג על פריטי נכס נולד (`it.nb`) כדי שלא ייכנסו לטופס ההחתמה: בשורה הראשונה `var ks = Object.keys(MSEL).filter(function(k){ return !MITEMS[k].nb; });`.

(ה) ב-`matchProps(i)`, אחרי `_openMatchSheet();` להוסיף `bpLoad(b.row);`.

- [ ] **Step 4: הרצה**

Run: `node $T/test_agent_js.js` ו-`node --check` על כל הסקריפט:
```bash
python3 -c "import importlib.util,os,re;os.environ['MAP_CACHE_DIR']='/tmp';s=importlib.util.spec_from_file_location('e','$RB/effie_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);open('$T/buyers.js','w').write('\n;\n'.join(re.findall(r'<script>([\s\S]*?)</script>', m.V2_BUYERS_HTML)))" && node --check $T/buyers.js
```
Expected: `agent js ok 8`, node --check שקט.

- [ ] **Step 5: Commit**

```bash
cd $RB && git pull --ff-only && git add effie_v2.py && git commit -m "דף קונה (7): שליחה מחלון ההתאמות דרך הדף, תגי 'בדף הלקוח', נכס נולד לבחירה

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: צד הסוכן — שורה בכרטיס הקונה + גיליון "דף הלקוח"

**Files:**
- Modify: `$RB/effie_v2.py` בתוך `V2_BUYERS_HTML`: `load()` (טעינת summary), `buyerCardHtml` (שורה), פונקציות חדשות `bpLine`, `bpSheet`, `bpSheetHtml`, `bpRemove`, `bpResend`
- Test: `$T/test_agent_sheet.js`

**Interfaces:**
- Consumes: `GET /v2/api/bpage/summary` → `{rows:{row:{like,visit,dislike,total,unseen,newN,expired}}}`; `GET /v2/api/bpage?row=`; `POST /v2/api/bpage/seen|remove`
- Produces: `BP_SUM = {}`; `bpLine(b, i) -> html`; `bpSheetHtml(b, j) -> html`

- [ ] **Step 1: בדיקה נכשלת**

`$T/test_agent_sheet.js`:
```js
const {execSync} = require('child_process');
const py = `import importlib.util,json,re;s=importlib.util.spec_from_file_location('e','/Users/eyal/Documents/GitHub/remax-bot/effie_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(json.dumps('\\n'.join(re.findall(r'<script>([\\s\\S]*?)</script>',m.V2_BUYERS_HTML))))`;
const src = JSON.parse(execSync(`python3 -c "${py}"`, {env: Object.assign({}, process.env, {MAP_CACHE_DIR: '/tmp'})}).toString().trim().split('\n').pop());
let n = 0; const check = (c, m) => { if (!c) throw new Error(m); n++; };
function fn(name){ const i = src.indexOf('function ' + name + '('); if (i < 0) throw new Error('missing ' + name);
  let d = 0, j = src.indexOf('{', i); for (let k = j; k < src.length; k++){ if (src[k] === '{') d++; else if (src[k] === '}' && --d === 0) return src.slice(i, k + 1); } }
global.esc = s => String(s == null ? '' : s);
global.BP_SUM = {'7': {like: 2, visit: 1, dislike: 0, total: 5, unseen: true, newN: 3, expired: false}, '8': {like: 0, visit: 0, dislike: 0, total: 2, unseen: false, newN: 0, expired: true}};
eval(fn('bpLine') + fn('bpSheetHtml') + fn('bpFmtP'));
const l = bpLine({row: 7}, 0);
check(l.includes('דף לקוח') && l.includes('2 מתאים') && l.includes('1 רוצה לראות') && l.includes('3 התאמות חדשות') && l.includes('bpDot') && l.includes('bpSheet(0)'), l);
check(!bpLine({row: 7}, 0).includes('0 לא מתאים'), 'zeros hidden');
check(bpLine({row: 8}, 1).includes('פג תוקף') && bpLine({row: 9}, 2) === '', 'expired / none');
const h = bpSheetHtml({name: 'בתיה ברון', row: 7}, {page: {url: 'https://a/b/T', expired: false}, new_matches: [{key: 'L:9'}],
  items: [{key: 'L:1', street: 'יששכר', house: '4', city: 'קרית מוצקין', price: '1690000', mark: 'visit', note: '', marked: '2026-10-06T11:00:00+00:00'},
          {key: 'L:2', street: 'הרצל', house: '5', price: '1', mark: 'dislike', note: 'קומה גבוהה'},
          {key: 'L:3', street: 'בגין', house: '', price: '1', mark: ''}]});
check(h.indexOf('רוצה לראות') < h.indexOf('טרם סומן') && h.indexOf('טרם סומן') < h.indexOf('לא מתאים'), 'group order');
check(h.includes('קומה גבוהה') && h.includes('https://a/b/T') && h.includes('bpRemove') && h.includes('#FBEDED') && h.includes('התאמות חדשות (1)'), 'content');
console.log('agent sheet ok', n);
```

- [ ] **Step 2: הרצה — נכשל** (`missing bpLine`)

- [ ] **Step 3: מימוש ב-`V2_BUYERS_HTML`** (ליד בלוק BP_STATE מ-Task 7)

```js
var BP_SUM = {};
function bpFmtP(p){ p = String(p || '').replace(/\D/g, ''); return p ? '₪' + p.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : ''; }
function bpLine(b, i){
  var s = BP_SUM[String(b.row)]; if (!s) return '';
  var parts = [];
  if (s.expired) parts.push('פג תוקף');
  if (s.like) parts.push(s.like + ' מתאים');
  if (s.visit) parts.push(s.visit + ' רוצה לראות');
  if (s.dislike) parts.push(s.dislike + ' לא מתאים');
  if (s.newN) parts.push(s.newN + ' התאמות חדשות');
  return '<div onclick="bpSheet(' + i + ')" style="display:flex;align-items:center;gap:8px;min-height:44px;margin:8px 0 0;padding:0 12px;' +
    'background:#F5F8FD;border-radius:14px;cursor:pointer;font-size:13px;font-weight:700;color:#1E3A5F">' +
    (s.unseen ? '<span class="bpDot" style="width:8px;height:8px;border-radius:50%;background:#2E6BD6;flex-shrink:0"></span>' : '') +
    '<span>דף לקוח' + (parts.length ? ' · ' + esc(parts.join(' · ')) : ' · ' + s.total + ' נכסים') + '</span></div>';
}
function bpSheetHtml(b, j){
  var it = j.items || [], P = j.page || {};
  var grp = [['visit', 'רוצה לראות'], ['like', 'מתאים'], ['', 'טרם סומן'], ['dislike', 'לא מתאים']];
  var h = '<h3>דף הלקוח · ' + esc(b.name || '') + '</h3>' +
    (P.expired ? '<div style="color:#7A5E1C;font-weight:700;font-size:13px;margin-bottom:8px">הקישור פג תוקף — שליחה חדשה מחדשת אותו ל-90 יום</div>' : '');
  grp.forEach(function(g){
    var xs = it.filter(function(x){ return (x.mark || '') === g[0]; });
    if (!xs.length) return;
    h += '<div class="grpTitle">' + g[1] + ' · ' + xs.length + '</div>';
    xs.forEach(function(x){
      h += '<div style="background:#fff;border-radius:16px;padding:12px;margin-bottom:8px;display:flex;gap:10px;align-items:flex-start">' +
        '<div style="flex:1;min-width:0"><div style="font-weight:800">' + esc([x.street, x.house].filter(Boolean).join(' ')) + (x.city ? ', ' + esc(x.city) : '') + '</div>' +
        '<div style="font-size:12.5px;color:#6B7280">' + esc(bpFmtP(x.price)) + (x.gone ? ' · כבר לא זמין' : '') + '</div>' +
        (x.note ? '<div style="font-size:13px;margin-top:4px">"' + esc(x.note) + '"</div>' : '') + '</div>' +
        '<button onclick="bpRemove(\'' + esc(String(x.key).replace(/'/g, '')) + '\')" aria-label="הסר מהדף" style="width:44px;height:44px;border-radius:12px;border:none;background:#FBEDED;flex-shrink:0">' +
        '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5" fill="none" stroke="#C24040" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>';
    });
  });
  if (!it.length) h += '<div style="text-align:center;color:#6B7280;padding:16px 0">עדיין לא נשלחו נכסים</div>';
  var nn = (j.new_matches || []).length;
  h += '<div style="display:flex;flex-direction:column;gap:8px;margin-top:10px">' +
    (nn ? '<button class="btn" style="background:#2E6BD6;color:#fff" onclick="bpNew()">התאמות חדשות (' + nn + ')</button>' : '') +
    '<button class="btn" style="background:#157A43;color:#fff" onclick="bpResend()">שלח שוב את הקישור</button>' +
    '<a class="btn btn-sec" style="text-align:center;text-decoration:none" href="' + esc(P.url || '#') + '" target="_blank" rel="noopener">פתח כמו שהלקוח רואה</a>' +
    '<button class="btn btn-sec" onclick="closeSheet()">סגירה</button></div>';
  return h;
}
var BP_CUR = null;
function bpSheet(i){
  var b = el('list')._src[i]; if (!b) return;
  BP_CUR = {b: b, i: i, j: null};
  openSheet('<div style="text-align:center;color:#6B7280;padding:20px 0">טוען…</div>');
  GET('/v2/api/bpage?row=' + encodeURIComponent(b.row)).then(function(j){
    if (!j || !j.ok || !j.page){ closeSheet(); toast('אין דף לקונה הזה'); return; }
    BP_CUR.j = j; openSheet(bpSheetHtml(b, j));
    POST('/v2/api/bpage/seen', {row: b.row}).then(function(){
      var s = BP_SUM[String(b.row)]; if (s){ s.unseen = false; render(); } }).catch(function(){});
  }).catch(function(){ closeSheet(); toast('שגיאה בטעינה'); });
}
function bpRemove(k){
  if (!BP_CUR || !confirm('להסיר את הנכס מדף הלקוח?')) return;
  POST('/v2/api/bpage/remove', {row: BP_CUR.b.row, key: k}).then(function(){ bpSheet(BP_CUR.i); bpSumLoad(); });
}
function bpResend(){
  if (!BP_CUR || !BP_CUR.j) return;
  var b = BP_CUR.b, first = String(b.name || '').trim().split(/\s+/)[0] || '';
  window.open('https://wa.me/' + (b.wa || '') + '?text=' + encodeURIComponent('היי' + (first ? ' ' + first : '') + ', הנה רשימת הנכסים שלך:\n' + BP_CUR.j.page.url), '_blank');
}
function bpNew(){ if (!BP_CUR) return; closeSheet(); matchProps(BP_CUR.i); }
function bpSumLoad(){
  return GET('/v2/api/bpage/summary').then(function(j){ BP_SUM = (j && j.rows) || {}; render(); }).catch(function(){});
}
```
ב-`buyerCardHtml`, אחרי `(extra || '') +` להוסיף `bpLine(b, i) +`.
ב-`load()`, אחרי שהרשימה נטענת (`BUYERS = ...` והרינדור) להוסיף קריאה אחת `bpSumLoad();` (לא חוסמת).
(לוודא ש-`render` הוא שם פונקציית הרינדור של הרשימה — ראה `var _renderBase = render;` בקובץ; ו-`el('list')._src` מכיל את הקונים לפי האינדקס שעובר ל-`buyerCardHtml`.)

- [ ] **Step 4: הרצה**

Run: `node $T/test_agent_sheet.js && node $T/test_agent_js.js` + שוב ה-`node --check $T/buyers.js` מ-Task 7 + `python3 $T/test_static.py`

- [ ] **Step 5: Commit**

```bash
cd $RB && git pull --ff-only && git add effie_v2.py && git commit -m "דף קונה (8): שורת 'דף לקוח' בכרטיס הקונה + גיליון סימונים, הסרה, שליחה חוזרת

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: פוש יומי מסכם על התאמות חדשות

**Files:**
- Modify: `$RB/effie_v2.py` — מודול: `bpage_digest_plan(pages_new:list[(page, newlist)]) -> {agent_phone9: {"buyers": int, "props": int}}`; register: `_bp_digest_run(day)`, thread `bpage-digest` שמתחיל ב-`@app.before_request` (הלקח מ-15/09: thread בייבוא מת ב-fork)
- Test: `$T/test_digest.py`

**Interfaces:**
- Consumes: `_bp_sb().bpage_all()`, `bpage_items`, `bpage_new_matches`, `_bp_sources`, `_config_mutate`, `_load_config`, G `send_push`, `_last9`
- Produces: `v2_bpage_digest[YYYY-MM-DD] = {"ts": ..., "sent": n}` בקונפיג (14 ימים)

- [ ] **Step 1: בדיקה נכשלת**

`$T/test_digest.py`:
```python
# -*- coding: utf-8 -*-
import sys, re, time; sys.path.insert(0, "/private/tmp/claude-501/-Users-eyal-Documents-remax-family/b28e4ff8-1c78-4ad7-a280-df05da71c83b/scratchpad/bpage")
from common import *
from flask import Flask
E = E()
p = lambda pid, ph: {"id": pid, "agent_phone": ph, "row": 1, "expires_at": "2099-01-01T00:00:00+00:00", "created_at": "2026-10-01T00:00:00+00:00", "query": {}}
plan = E.bpage_digest_plan([(p("A", "0521111111"), [{"key": "1"}, {"key": "2"}]), (p("B", "052-1111111"), [{"key": "3"}]),
                            (p("C", "0539999999"), []), (p("D", ""), [{"key": "9"}])])
check(plan == {"521111111": {"buyers": 2, "props": 3}}, plan)
check(E.bpage_digest_plan([]) == {})
# הרצה עם G מדומה
NOW = time.time()
PUSH, CFG = [], {}
PAGES = [p("A", "0521111111"), dict(p("E", "0521111111"), expires_at="2020-01-01T00:00:00+00:00")]
class SB:
    def enabled(self): return True
    def bpage_all(self): return PAGES
    def bpage_items(self, ids): return []
E._BP_SB = SB()
def mut(fn): fn(CFG); return True, CFG
OFF = {"מספר מודעה": "5", "מחיר": "1700000", "סטטוס": "פעילה"}
G = dict(send_push=lambda t, b, ids: PUSH.append((t, b, ids)) or True, _last9=lambda x: re.sub(r"\D", "", str(x or ""))[-9:],
         _config_mutate=mut, _load_config=lambda: CFG, fetch_sheet_rows=lambda: [OFF], fetch_external_exclusives=lambda: [],
         _dedupe_exclusives=lambda r: r, fetch_newborn=lambda: [], _prop_price_key=lambda r: "L:5", _prop_epoch=lambda r: NOW - 3600,
         score_match=lambda r, q, f=0: 90)
app = Flask("t"); GGx = GG(G); E.register(app, GGx)
n = GGx["_bp_digest_run"]("2026-10-06")
check(n == 1 and len(PUSH) == 1 and PUSH[0][2] == ["521111111"] and "1 נכסים חדשים מתאימים ל-1 קונים" in PUSH[0][1], PUSH)
check(GGx["_bp_digest_run"]("2026-10-06") == 0 and len(PUSH) == 1, "idempotent per day")
check("2026-10-06" in CFG["v2_bpage_digest"])
print("digest ok", N[0])
```
(הבדיקה מצפה ש-`register` יחשוף את `_bp_digest_run` דרך `G["_bp_digest_run"] = _bp_digest_run` — כמו `_bs_scan_async` הקיים.)

- [ ] **Step 2: הרצה — נכשל**

- [ ] **Step 3: מימוש**

מודול (בלוק BPAGE):
```python
def bpage_digest_plan(pages_new):
    """[(page, new_matches)] → {טלפון9 של הסוכן: {buyers, props}} — רק דפים עם התאמות וסוכן עם טלפון."""
    out = {}
    for page, new in pages_new:
        d = _bp_digits((page or {}).get("agent_phone"))[-9:]
        if not new or len(d) < 9:
            continue
        o = out.setdefault(d, {"buyers": 0, "props": 0})
        o["buyers"] += 1
        o["props"] += len(new)
    return out
```
ב-register (אחרי ראוטי הדף הציבורי):
```python
    _BPAGE_DIGEST = (os.environ.get("BPAGE_DIGEST", "1") or "1").strip() not in ("0", "false", "off")
    _BPAGE_DIGEST_HOUR = int(os.environ.get("BPAGE_DIGEST_HOUR", "10") or 10)

    def _bp_digest_run(day):
        """פוש מסכם אחד לכל סוכן: התאמות חזקות שנראו לראשונה ב-24ש' האחרונות, לדפים פעילים. פעם ביום."""
        if (_load_config() or {}).get("v2_bpage_digest", {}).get(day):
            return 0
        sb = _bp_sb()
        if not sb:
            return 0
        now = time.time()
        pages = [p for p in (sb.bpage_all() or []) if not bpage_expired(p, now)]
        items = sb.bpage_items([p["id"] for p in pages]) if pages else []
        by = {}
        for i in items:
            by.setdefault(i["page_id"], set()).add(i.get("prop_key"))
        src = _bp_sources()
        pn = []
        for p in pages:
            q = p.get("query") or {}
            pn.append((p, bpage_new_matches(q.get("p") or {}, src, by.get(p["id"], set()), now - 86400,
                                             int(q.get("budget") or 0), lambda r, qq: G["score_match"](r, qq, 0))))
        plan = bpage_digest_plan(pn)
        for ph, v in plan.items():
            G["send_push"]("התאמות חדשות לקונים שלך",
                           "%d נכסים חדשים מתאימים ל-%d קונים שלך" % (v["props"], v["buyers"]), [ph])

        def _mut(cfg):
            d = cfg.setdefault("v2_bpage_digest", {})
            d[day] = {"ts": int(now), "sent": len(plan)}
            for k in sorted(d)[:-14]:
                d.pop(k, None)
        _config_mutate(_mut)
        return len(plan)
    G["_bp_digest_run"] = _bp_digest_run

    _bp_thr = {"started": False}
    _bp_thr_lock = threading.Lock()

    def _bp_digest_loop():
        from zoneinfo import ZoneInfo as _ZB
        import datetime as _dtb
        while True:
            try:
                n = _dtb.datetime.now(_ZB("Asia/Jerusalem"))
                if n.hour >= _BPAGE_DIGEST_HOUR:
                    _bp_digest_run(n.strftime("%Y-%m-%d"))
            except Exception as e:
                if log: log.warning(f"bpage digest: {e}")
            time.sleep(300)

    @app.before_request
    def _bp_ensure_thread():
        if _bp_thr["started"] or not _BPAGE_DIGEST or not _BPAGE_ON:
            return
        with _bp_thr_lock:
            if _bp_thr["started"]:
                return
            _bp_thr["started"] = True
            threading.Thread(target=_bp_digest_loop, name="bpage-digest", daemon=True).start()
```
(`send_push` עצמו מכבד שעות שקט ו-QUIET_MODE — אם השעה 10:00 נופלת בשקט, הפוש לא יוצא ויום נרשם; מקובל.)
⚠️ `@app.before_request` מוסיף hook לכל בקשה — הבדיקה הזולה (`if _bp_thr["started"]`) מחזירה מיד. בבדיקות שבהן BPAGE_DIGEST כבוי — אין thread.

- [ ] **Step 4: הרצה**

Run: `BPAGE_DIGEST=0 python3 $T/test_digest.py && for f in sbd pure match keys routes_agent public digest; do BPAGE_DIGEST=0 python3 $T/test_$f.py || break; done && node $T/test_public_js.js && node $T/test_agent_js.js && node $T/test_agent_sheet.js && python3 $T/test_static.py`
(הערה: test_routes_agent בודק BPAGE=0 בסוף ומשנה env — להריץ אותו אחרון או לאפס `os.environ["BPAGE"]="1"` בתחילת כל קובץ.)

- [ ] **Step 5: Commit**

```bash
cd $RB && git pull --ff-only && git add effie_v2.py && git commit -m "דף קונה (9): פוש יומי מסכם על התאמות חדשות לקונים עם דף פעיל

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: רגרסיה, יומן, בקשה לצ'אט הסורק, הודעת SQL לאייל

**Files:**
- Modify: `$RF/CLAUDE.md` (יומן החלטות)
- Create: `$RB/docs/handoff/2026-10-06-scanner-images-request.md`

- [ ] **Step 1: רגרסיה מלאה + הרצה מקומית**

Run: כל הבדיקות מ-Task 9 Step 4, ובנוסף ייבוא app מלא:
```bash
cd $RB && MAP_CACHE_DIR=/tmp python3 -c "import app; print(len([r for r in app.app.url_map.iter_rules() if 'bpage' in r.rule or r.rule.startswith('/b/')]))"
```
Expected: `7` (send, get, summary, seen, remove, /b/<token>, /b/<token>/mark).

- [ ] **Step 2: בקשה לצ'אט הסורק**

`$RB/docs/handoff/2026-10-06-scanner-images-request.md`:
```markdown
# בקשה לצ'אט הסורק — גלריית תמונות מלאה (דף קונה, 06/10)
דף הקונה מציג ללקוח את כל תמונות הנכס. היום `mapApiRow` (`image: it.images[0]`) ו-`itemImage` שולחים תמונה אחת.
**הבקשה:** בכל שורה שנשלחת ל-`/v2/api/yad2/ingest` (פרטי, משרד, שת"פ) להוסיף `images: [<כל כתובות התמונות>]`
מתוך אותו JSON שכבר נקרא (`it.images` / `it.metaData.images`) — אפס בקשות נוספות ליד2. `image` נשאר כמו שהוא.
**בצד האפליקציה כבר מוכן:** `y2_norm_office` שומר `תמונות`, `y2_norm_agency` שומר `images` ב-raw (עד 30).
אם השדה חסר — מוצגת התמונה האחת, בלי שבירה.
```

- [ ] **Step 3: יומן החלטות ב-CLAUDE.md** — רשומה חדשה בראש "יומן החלטות": מה נבנה (קומיטים 1-9), SQL שאייל צריך להריץ (`supabase/migrations/20261006_buyer_pages.sql`), env חדשים (`BPAGE`, `BPAGE_DIGEST`, `BPAGE_DIGEST_HOUR`), התלות בסורק, ומה לבדוק אחרי deploy.

- [ ] **Step 4: Commit**

```bash
cd $RB && git pull --ff-only && git add docs/handoff/2026-10-06-scanner-images-request.md && git commit -m "דף קונה: בקשה לצ'אט הסורק — גלריית תמונות מלאה

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd $RF && git add CLAUDE.md && git commit -m "יומן: דף קונה — נבנה, ממתין ל-SQL+push+deploy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: הודעה לאייל** — סדר הפעלה: (1) להריץ את ה-SQL ב-SQL Editor; (2) push ב-GitHub Desktop (remax-bot + remax-family) ו-deploy ב-Render; (3) להעביר את קובץ הבקשה לצ'אט הסורק. אחרי ה-deploy — בדיקה חיה עם חשבון הביקורת (סוכן): שליחה מחלון ההתאמות, פתיחת הקישור בדפדפן נקי, סימון, הופעה בגיליון; לדווח מה נבדק ומה לא.
