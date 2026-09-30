# חיפוש נכס — טאב נכס נולד · תוכנית ביצוע

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** חיפוש במסך הנכסים מחזיר גם נכסים מנכס נולד בטאב רביעי, עם כרטיס נכס נולד מלא.

**Architecture:** שרת: פירוק חיפוש משותף עם מטמון, ניקוד נכס נולד באותו `score_match` דרך מיפוי לשורת-משרד, ובונה-כרטיס משותף ל-`/api/newborn` ול-`/api/search/newborn`. קליינט: הכרטיס ופעולותיו עוברים לבלוק משותף `V2_NB_KIT` (CSS תחום ב-`.nbk` + JS) שמוזרק לשני הדפים; כל דף מגדיר `nbKitRows()`/`nbKitRefresh()`.

**Tech Stack:** Flask (app.py, effie_v2.py), vanilla JS בתבניות Python, בדיקות: python (חילוץ ast) + node (vm).

**ספק:** `docs/superpowers/specs/2026-09-30-props-search-newborn-design.md`

## Global Constraints

- אין השהיית נכס נולד בחיפוש (החלטת אייל 30/09).
- טאב "נכס נולד" רק כשיש טקסט בחיפוש; בלי חיפוש — קישור "לכל נכס נולד ←".
- כרטיס מלא (חיוג/וואטסאפ/סטטוס/הערות/מי פנה) — אותם endpoints של נכס נולד.
- מסך נכס נולד: פלט HTML של כרטיס **זהה** לפני/אחרי.
- `git pull --ff-only` לפני כל עריכה; קומיט רק של השינויים שלי (`git diff -w` לבדיקה); חתימת Co-Authored-By.
- אימות: `ast.parse` (לא py_compile); `node --check`/`vm.Script` לסקריפטים.
- טסטים בסקראצ'פד: `/private/tmp/claude-501/-Users-eyal-Documents-remax-family/ec981553-45f3-4419-b634-700a4a2efe5f/scratchpad/`.

---

### Task 1: פירוק חיפוש משותף עם מטמון

**Files:**
- Modify: `app.py` — לפני `@app.route("/api/search/properties")`; בתוך `api_search_properties`.
- Test: `scratchpad/test_parse_cache.py`

**Interfaces:**
- Produces: `_parse_props_query(q: str) -> dict` (עותק עמוק; `{}` בכשל).

- [ ] **Step 1: טסט (נכשל — הפונקציה לא קיימת)**

```python
# scratchpad/test_parse_cache.py
import ast, copy, threading, time
SRC = open('/Users/eyal/Documents/GitHub/remax-bot/app.py', encoding='utf-8').read(); t = ast.parse(SRC)
code = next(ast.get_source_segment(SRC, n) for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "_parse_props_query")
calls = []
def parse_search_query(text):
    calls.append(text); time.sleep(0.2); return {"city": "קרית ביאליק", "must_have": []}
C = {}; locks = {}
def _cache_get(k, ttl): return C.get(k)
def _cache_put(k, v): C[k] = v
class _L:
    def __init__(s, k): s.l = locks.setdefault(k, threading.Lock())
    def __enter__(s): s.l.acquire()
    def __exit__(s, *a): s.l.release()
ns = dict(parse_search_query=parse_search_query, _cache_get=_cache_get, _cache_put=_cache_put, _sf_lock=_L, copy=copy)
exec(code, ns); f = ns["_parse_props_query"]
out = []
ts = [threading.Thread(target=lambda: out.append(f("4 חדרים"))) for _ in range(3)]
[x.start() for x in ts]; [x.join() for x in ts]
assert calls == ["מחפש דירה 4 חדרים"], calls          # AI פעם אחת בלבד
assert all(o == {"city": "קרית ביאליק", "must_have": []} for o in out)
out[0]["must_have"].append("x"); assert f("4 חדרים")["must_have"] == []   # עותק — שינוי לא דולף
assert f("מחפש קוטג'") and calls[-1] == "מחפש קוטג'"   # "מחפש" בתחילה נשמר
print("OK")
```

- [ ] **Step 2:** `python3 scratchpad/test_parse_cache.py` → StopIteration (אין פונקציה).

- [ ] **Step 3: מימוש** — ב-app.py מיד לפני `@app.route("/api/search/properties", methods=["POST"])`:

```python
_PARSE_Q_TTL = 600
def _parse_props_query(q):
    """[NB-SEARCH 30/09] פירוק חיפוש נכסים (AI) משותף למשרד ולנכס נולד: מטמון 10 דק' לפי הטקסט +
    single-flight — שתי הבקשות שהמסך שולח במקביל עושות קריאת AI אחת. מחזיר עותק ({} בכשל)."""
    text = q if q.startswith("מחפש") else ("מחפש דירה " + q)
    key = "pq:" + text
    c = _cache_get(key, _PARSE_Q_TTL)
    if c is None:
        with _sf_lock(key):
            c = _cache_get(key, _PARSE_Q_TTL)
            if c is None:
                c = parse_search_query(text) or {}
                if c:
                    _cache_put(key, c)
    return copy.deepcopy(c)
```

ובתוך `api_search_properties` להחליף:

```python
        parsed = parse_search_query(q if q.startswith("מחפש") else ("מחפש דירה " + q))
```
ב-
```python
        parsed = _parse_props_query(q)   # [NB-SEARCH 30/09] משותף עם /api/search/newborn
```

ולוודא `import copy` ברמת המודול (אם חסר — להוסיף ליד שאר ה-imports).

- [ ] **Step 4:** הטסט עובר + `ast.parse(app.py)`.
- [ ] **Step 5:** לא לקמט עדיין (קומיט אחד לכל השרת בסוף Task 2).

---

### Task 2: חיפוש נכס נולד בשרת

**Files:**
- Modify: `app.py` — `search_listings_in_sheet` (פרמטרים), עוזרים חדשים אחרי `_famexcl_floor_txt`, `api_newborn` (הלולאה השנייה משתמשת בבונה המשותף), ראוט חדש אחרי `api_newborn`.
- Test: `scratchpad/test_nb_search.py`, רגרסיה `scratchpad/test_nb_limit.py`.

**Interfaces:**
- Consumes: `_parse_props_query` (Task 1).
- Produces: `search_listings_in_sheet(query, rows=None, cap=None)`; `_nb_clean(v)`; `_nb_as_office_row(r) -> dict`; `_nb_row_out(r, ad, city, addr, owner, lister, dropped, ctx) -> dict`; `POST /api/search/newborn {q}` → `{ok, results:[כרטיס + score], count, summary, rent}`.

- [ ] **Step 1: טסט**

```python
# scratchpad/test_nb_search.py — מיפוי + ניקוד על score_match האמיתי (חילוץ רקורסיבי של תלויות)
import ast, re, json
SRC = open('/Users/eyal/Documents/GitHub/remax-bot/app.py', encoding='utf-8').read(); T = ast.parse(SRC)
defs = {n.name: n for n in T.body if isinstance(n, ast.FunctionDef)}
assigns = {}
for n in T.body:
    if isinstance(n, ast.Assign):
        for tg in n.targets:
            if isinstance(tg, ast.Name): assigns[tg.id] = n
need, seen, order = ["_nb_as_office_row", "search_listings_in_sheet", "score_match", "_nb_clean"], set(), []
while need:
    nm = need.pop()
    if nm in seen: continue
    seen.add(nm)
    node = defs.get(nm) or assigns.get(nm)
    if node is None: continue
    order.append(node)
    for x in ast.walk(node):
        if isinstance(x, ast.Name) and (x.id in defs or x.id in assigns) and x.id not in seen: need.append(x.id)
order.sort(key=lambda n: n.lineno)
ns = {"re": re, "fetch_sheet_rows": lambda: [], "log": type("L", (), {"warning": lambda *a: None, "info": lambda *a: None})()}
skip = {"fetch_sheet_rows"}
exec("\n\n".join(ast.get_source_segment(SRC, n) for n in order if getattr(n, "name", "") not in skip), ns)
nb = [
  {"רחוב": "הנוטר 18", "עיר": "קרית ביאליק", "שכונה": "נאות אפק", "מחיר": "1950000", "תיאור נכס": "דירה · 4 חד' · 100 מ\"ר · קומה 2. מעלית"},
  {"רחוב": "הרצל 5", "עיר": "קרית מוצקין", "מחיר": "1800000", "תיאור נכס": "דירה · 4 חד' · 95 מ\"ר"},
  {"רחוב": "ירושלים 3", "עיר": "קרית ביאליק", "מחיר": "2900000", "תיאור נכס": "דירה · 5 חד'"},
  {"רחוב1": "שמר 12", "עיר": "קרית ביאליק", "מחיר": "1700000", "תיאור נכס": "דירת 4 חדרים משופצת, קומה 1"},
]
m = ns["_nb_as_office_row"](nb[0])
assert (m["עיר / ישוב"], m["שכונה"], m["כתובת"], m["חדרים"], m['מ"ר'], m["קומה"], m["סוג נכס"], m["סוג עסקה"]) == \
       ("קרית ביאליק", "נאות אפק", "הנוטר 18", "4", "100", "2", "דירה", "מכירה"), m
m3 = ns["_nb_as_office_row"](nb[3]); assert (m3["כתובת"], m3["חדרים"], m3["קומה"], m3["סוג נכס"]) == ("שמר 12", "4", "1", ""), m3
rows = [dict(ns["_nb_as_office_row"](r), _i=i) for i, r in enumerate(nb)]
q = {"city": "קרית ביאליק", "rooms_min": 4, "rooms_max": 4, "budget_max": 2000000, "deal_type": "מכירה", "must_have": []}
got = [r["_i"] for s, r, f in ns["search_listings_in_sheet"](q, rows=rows, cap=30)]
assert 0 in got and 3 in got and 1 not in got and 2 not in got, got   # עיר אחרת / מעל התקציב — בחוץ
assert ns["search_listings_in_sheet"](q) == []                        # בלי rows = נכסי המשרד (כאן ריק) — כמו היום
rent = dict(q, deal_type="השכרה"); assert ns["search_listings_in_sheet"](rent, rows=rows, cap=30) == []
print("OK")
```

- [ ] **Step 2:** להריץ → נכשל (אין `_nb_as_office_row`).

- [ ] **Step 3: `search_listings_in_sheet` מקבל rows/cap:**

```python
def search_listings_in_sheet(query: dict, rows=None, cap=None) -> list:
    # [NB-SEARCH 30/09] rows/cap אופציונליים — אותו סולם flex משמש גם לנכס נולד (rows=שורות ממופות)
    rows = fetch_sheet_rows() if rows is None else rows
    if not rows:
        return []
    _has_nb = bool((query.get("neighborhoods")) or (query.get("neighborhood") or "").strip())
    cap = cap or (40 if _has_nb else 25)   # תקרת תוצאות
```
(שאר הפונקציה ללא שינוי.)

- [ ] **Step 4: עוזרים** — אחרי `_famexcl_floor_txt`:

```python
def _nb_clean(v):
    """ערך שורת נכס נולד — '-'/'—'/ריק → ''."""
    v = str(v or "").strip()
    return "" if v in ("-", "—", "") else v

def _nb_as_office_row(r):
    """[NB-SEARCH 30/09] שורת נכס נולד → מבנה שורת משרד, כדי ש-score_match ינקד אותה כמו נכס משרד.
    חדרים/מ"ר/קומה: מהשדה אם יש, אחרת מהתיאור ('דירה · 4 חד' · 100 מ"ר · קומה 2')."""
    desc = _nb_clean(r.get("תיאור נכס", ""))
    rooms = _nb_clean(r.get("חדרים", "")) or ("%g" % _famexcl_rooms(desc) if _famexcl_rooms(desc) is not None else "")
    sqm = _nb_clean(r.get('מ"ר', "")) or (str(_famexcl_sqm(desc)) if _famexcl_sqm(desc) is not None else "")
    floor = _nb_clean(r.get("קומה", "")) or (str(_famexcl_floor_txt(desc)) if _famexcl_floor_txt(desc) is not None else "")
    ptype = desc.split(" · ", 1)[0].strip() if " · " in desc else ""
    return {"סוג עסקה": "מכירה",   # נכס נולד = מכירה בלבד (31/08)
            "עיר / ישוב": _nb_clean(r.get("עיר", "") or r.get("עיר / ישוב", "")),
            "שכונה": _nb_clean(r.get("שכונה", "")),
            "כתובת": _nb_clean(r.get("רחוב1", "") or r.get("רחוב", "")), "מספר בית": "",
            "חדרים": rooms, 'מ"ר': sqm, "קומה": floor, "מחיר": _nb_clean(r.get("מחיר", "")),
            "סוג נכס": ptype, "תיאור": desc}

def _nb_row_out(r, ad, city, addr, owner, lister, dropped, ctx):
    """[NB-SEARCH 30/09] כרטיס נכס נולד לקליינט — משותף ל-/api/newborn ול-/api/search/newborn.
    ctx: contacts, statuses, fam_list, pd_map, eff_name, phone9, notes_admin."""
    _k = _nb_key(r)
    _vstat = ctx["statuses"].get(_canon_key(ctx["eff_name"]) + "::" + _k)
    ophone = _nb_clean(r.get("טלפון בעל הנכס-", "") or r.get("טלפון בעל הנכס", ""))
    _fl = _famexcl_floor(r.get("קומה", ""))
    if _fl is None:   # שורות ישנות בלי שדה קומה — מהתיאור ("קומה N")
        _m_fl = re.search(r"קומה\s*(-?\d+)", str(r.get("תיאור נכס", "") or ""))
        _fl = int(_m_fl.group(1)) if _m_fl else None
    _dsc = str(r.get("תיאור נכס", "") or "")
    _famv = _is_famexcl(addr, city, ctx["fam_list"], _famexcl_price(r.get("מחיר", "")), _fl,
                        _famexcl_rooms(_dsc), _famexcl_sqm(_dsc))   # שם הסוכן שבבלעדיות / '' / None
    return {
        "key": _k,
        "contacted": ctx["contacts"].get(_k, []),
        "city": city,
        "address": addr,
        "desc": _nb_clean(r.get("תיאור נכס", "")),
        "price": _newborn_price(r.get("מחיר", "")),
        "notes": _nb_clean(r.get("הערות חדש", ""))[:160],
        "owner": owner,
        "phone": _fmt_vphone(ophone),
        "wa": _wa_phone(ophone),
        "agent": lister,
        "link": _nb_clean(r.get("קישור", "")),
        "date": _nb_clean(r.get("נראה לראשונה", "") or r.get("נוצר בתאריך", "") or r.get("תאריך יצירה", "")),
        "stat": _vstat or None,
        "unotes": _nb_notes_for(_k, ctx["phone9"], ctx["notes_admin"]),
        "ageDays": ad,
        "delisted": _nb_clean(r.get("delisted_at", "")),
        "famexcl": (_famv is not None),
        "famexclAgent": (_famv or ""),
        "priceDropped": dropped,
        "priceOld": ctx["pd_map"].get(_nb_price_key(r), "") if dropped else "",
    }
```

- [ ] **Step 5: `api_newborn` משתמש בבונה** — לפני לולאת `for (r, ad, city, ...) in (_cand[:_lim] ...)`:

```python
        _ctx = {"contacts": contacts, "statuses": nbstatuses, "fam_list": fam_list, "pd_map": _pd_map,
                "eff_name": eff_name, "phone9": _last9(s.get("phone", "")),
                "notes_admin": (s["role"] == "admin" or _is_dev(s.get("phone", "")))}
```
וגוף הלולאה כולו (מ-`_k = _nb_key(r)` עד סוף `out.append({...})`) מוחלף ב:
```python
            out.append(_nb_row_out(r, ad, city, _addr, _owner, lister, _dropped, _ctx))
```

- [ ] **Step 6: הראוט** — מיד אחרי `api_newborn` (לפני `@app.route("/api/newborn/contact"`):

```python
@app.route("/api/search/newborn", methods=["POST"])
def api_search_newborn():
    """[NB-SEARCH 30/09] חיפוש נכס — טאב נכס נולד: אותה הבנה של חיפוש המשרד (_parse_props_query),
    אותו ניקוד (score_match דרך _nb_as_office_row), בלי השהיה (החלטת אייל 30/09), עד 30 תוצאות."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    q = ((request.get_json(silent=True) or {}).get("q", "") or "").strip()
    if not q:
        return jsonify({"ok": True, "results": [], "count": 0, "summary": "", "rent": False})
    try:
        _log_activity(s["name"], s["role"], s["phone"], "חיפוש נכס נולד", q)
        parsed = _parse_props_query(q)
        if not parsed:
            return jsonify({"ok": True, "results": [], "count": 0, "summary": "", "rent": False})
        now = time.time()
        pseudo = []
        for r in fetch_newborn():
            c = _newborn_created_epoch(r)
            if not c or (now - c) / 86400 > NEWBORN_WINDOW_DAYS:
                continue
            pr = _nb_as_office_row(r)
            pr["_nb"] = r; pr["_age"] = int((now - c) / 86400)
            pseudo.append(pr)
        matches = search_listings_in_sheet(parsed, rows=pseudo, cap=30)
        _scan_price_changes()
        _pd = _price_dropped_map()
        _ctx = {"contacts": _fetch_newborn_contacts(), "statuses": _nb_statuses(), "fam_list": _famexcl_addr_list(),
                "pd_map": _pd, "eff_name": s.get("name", ""), "phone9": _last9(s.get("phone", "")),
                "notes_admin": (s["role"] == "admin" or _is_dev(s.get("phone", "")))}
        out = []
        for sc, pr, _fx in matches:
            r = pr["_nb"]
            try:
                o = _nb_row_out(r, pr["_age"], pr["עיר / ישוב"], pr["כתובת"], _nb_clean(r.get("שם בעל הנכס", "")),
                                _nb_clean(r.get("משתמש", "") or r.get("סוכן 1", "")), _nb_price_key(r) in _pd, _ctx)
            except Exception:
                continue
            o["score"] = min(100, int(sc))
            out.append(o)
        return jsonify({"ok": True, "results": out, "count": len(out),
                        "summary": parsed.get("summary_he", ""), "rent": parsed.get("deal_type") == "השכרה"})
    except Exception as e:
        log.error(f"newborn search error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500
```

- [ ] **Step 7:** `test_nb_search.py` עובר; `test_nb_limit.py` (פלט `/api/newborn` מול HEAD) עובר — לעדכן את המילון שלו עם `_nb_clean` ו-`_nb_row_out` (מחולצים מהקובץ) כי `api_newborn` קורא להם עכשיו; `ast` + בדיקת קשירת ראוטים.

- [ ] **Step 8: קומיט** (`git add app.py` אחרי `git diff -w` שמראה רק את השינויים שלי).

---

### Task 3: רכיב כרטיס משותף `V2_NB_KIT` + מסך נכס נולד

**Files:**
- Modify: `effie_v2.py` — קבוע חדש `V2_NB_KIT` לפני `V2_NB_HTML`; ב-`V2_NB_HTML`: הסרת כללי ה-CSS `.nb … .notes`, `class="nbk"` ל-`#list`, סימון `<!--NB_KIT-->` לפני `<script>` הראשי, הסרת הפונקציות שעוברות, דבק `nbKitRows/nbKitRefresh`, קריאה ל-`nbKitInit()`; הראוט `/v2/newborn` מזריק.
- Test: `scratchpad/test_nb_kit.js`

**Interfaces:**
- Produces (JS גלובלי): `nbCard(r,i)`, `nbDial(i)`, `markContact(i)`, `waOwner(i)`, `stDate(i,status)`, `stSave(i,status)`, `stToggleNI(i)`, `stSet(i,status,date)`, `noteSheet(i)`, `noteSave(i)`, `agOpts`, `agOther`, `dt15Opts`, `dtNextQ`, `dtJoin`, `nbFmtPrice(p)`, `nbKitInit()`; משתנים `MGR, MYNAME, AG_OPTS, IS_COORD, OFFICE_AG, NB_WA_T, ST_LABEL`.
- Consumes (מהדף המארח): `el, esc, GET, POST, toast, openSheet, closeSheet, c2cDial`, `nbKitRows()`, `nbKitRefresh()`.

- [ ] **Step 1: טסט השוואה** — `nbCard` הישן מ-HEAD מול החדש מהרכיב על 6 שורות מגוונות (בעלים+טלפון, בלי בעלים עם קישור, contacted עם MGR=true/false, stat פגישה/לא מעוניין, unotes, famexcl+agent, delisted, priceDropped+priceOld, ageDays 0/45/200) → מחרוזות זהות. ופעולות: `nbKitRows` מחזיר מערך מדומה — `stSet(1,'not_interested','')` שולח POST עם `key` של שורה 1 וקורא ל-`nbKitRefresh`; `waOwner(0)` פותח `wa.me/<wa>?text=` עם הכתובת; `noteSave` בלי טקסט → toast.

```js
// scratchpad/test_nb_kit.js
const fs = require('fs'), vm = require('vm'), cp = require('child_process');
const NEW = fs.readFileSync('/Users/eyal/Documents/GitHub/remax-bot/effie_v2.py', 'utf8');
const OLD = cp.execSync('git -C /Users/eyal/Documents/GitHub/remax-bot show HEAD:effie_v2.py').toString();
const kitS = NEW.indexOf('V2_NB_KIT = r"""'), kitJ = NEW.indexOf('<script>', kitS), kitE = NEW.indexOf('</script>', kitJ);
const kitJs = NEW.slice(kitJ + 8, kitE); new vm.Script(kitJs);
const oS = OLD.indexOf('function nbCard(r, i){'), oE = OLD.indexOf('var NB_SHOWN = 40;', oS);
const oldCard = OLD.slice(oS, oE) + "\nfunction fmtPrice(p){ p = String(p || '').trim(); if (!p) return ''; return (/^[\\d,.]+$/.test(p) ? '₪' : '') + p; }\nvar ST_LABEL = {meeting:'פגישה', followup:'פולו-אפ', not_interested:'לא מעוניין'};";
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rows = [
  {address:'הנוטר 18', city:'קרית ביאליק', desc:'דירה · 4 חד׳', price:'1,950,000', owner:'דנה', phone:'050-1234567', wa:'972501234567', link:'https://yad2/x', date:'30/09', ageDays:0, contacted:['אלי','רפי'], stat:{status:'meeting', date:'2026-10-01T10:00', agent:'אלי'}, unotes:[{name:'אלי', text:'לחזור'}]},
  {address:'הרצל 5', city:'', desc:'', price:'1800000', ageDays:45, link:'https://yad2/y', stat:{status:'not_interested'}},
  {address:'שמר 12', city:'קרית ביאליק', price:'1700000', ageDays:200, famexcl:true, famexclAgent:'בנימין', delisted:'29/09'},
  {address:'ירושלים 3', city:'קרית ים', price:'2,000,000', priceOld:'2,100,000', priceDropped:true, ageDays:10, owner:'', phone:'0521112222', wa:'972521112222'},
];
let n = 0; const eq = (a, b, m) => { n++; if (a !== b) { console.error('FAIL', m, '\nOLD:', a, '\nNEW:', b); process.exit(1); } };
for (const MGR of [true, false]) {
  const o = {esc, MGR}; vm.runInNewContext(oldCard, o);
  const k = {esc}; vm.runInNewContext(kitJs, k); k.MGR = MGR;
  rows.forEach((r, i) => eq(o.nbCard(r, i), k.nbCard(r, i), 'card ' + i + ' MGR=' + MGR));
}
const posts = [], opened = []; let refreshed = 0, toasts = [];
const ctx = {esc, el: () => ({value: ''}), toast: t => toasts.push(t), closeSheet(){}, openSheet(){},
  POST: (u, d) => { posts.push([u, d]); return Promise.resolve({ok: true}); }, GET: () => Promise.resolve({ok: true, text: ''}),
  window: {open: (u) => opened.push(u)}, encodeURIComponent, c2cDial: () => {},
  nbKitRows: () => rows, nbKitRefresh: () => { refreshed++; }};
vm.runInNewContext(kitJs, ctx);
ctx.stSet(1, 'not_interested', '');
ctx.waOwner(0);
ctx.noteSave(0);
setTimeout(() => {
  eq(posts[0][0], '/api/newborn/status', 'status endpoint'); eq(posts[0][1].key, rows[1].key, 'row index → key');
  eq(refreshed, 1, 'refresh after save');
  eq(opened[0].indexOf('https://wa.me/972501234567?text=') === 0, true, 'wa link');
  eq(posts.some(p => p[0] === '/api/newborn/contact'), true, 'wa marks contact');
  eq(toasts.indexOf('כתוב הערה') >= 0, true, 'empty note blocked');
  console.log('OK', n, 'checks');
}, 20);
```

- [ ] **Step 2:** להריץ → נכשל (אין `V2_NB_KIT`).

- [ ] **Step 3: הרכיב** — `V2_NB_KIT = r"""<style>…</style><script>…</script>"""` לפני `V2_NB_HTML`:
  - **CSS:** כל כללי `.nb`, `.nb .top/.ad/.dt/.pr`, `.chip`, `.chip.new`, `.chip.age`, `.owner…`, `.oActs…`, `.contacted`, `.stActs…`, `.stLine…`, `.notes` מ-`V2_NB_HTML` (שורות 4388-4417 כרגע) — **אותן הצהרות בדיוק**, כל סלקטור בקידומת `.nbk ` (למשל `.nbk .nb{…}`, `.nbk .chip.new{…}`); ובנוסף לגיליון (שאינו בתוך `.nbk`): `#sheet .notes{…}` (אותה הצהרה של `.notes`), `#sheet .fld`, `#sheet .fld span`, `#sheet .fld input,#sheet .fld textarea`, `#sheet .btn-gold`, `#sheet .btn-blue` — ההצהרות מ-`V2_NB_HTML` שורות 4439-4446.
  - **JS:** `var MGR = false; var ST_LABEL = {…};` + `function nbFmtPrice(p){ p = String(p || '').trim(); if (!p) return ''; return (/^[\d,.]+$/.test(p) ? '₪' : '') + p; }` + הפונקציות `nbCard, nbDial, markContact, NB_WA_T, waOwner, MYNAME, AG_OPTS, IS_COORD, OFFICE_AG, agOpts, agOther, dt15Opts, dtNextQ, dtJoin, stDate, stSave, stToggleNI, stSet, noteSheet, noteSave` מועתקות כמו שהן משורות 4667-4861, עם שלושה שינויים מכניים בלבד:
    1. כל `el('list')._src[i]` → `nbKitRows()[i]`;
    2. כל `load();` בתוך `stToggleNI/stSet/noteSave` → `nbKitRefresh();`;
    3. בתוך `nbCard`: `fmtPrice(` → `nbFmtPrice(`.
  - שורת `GET('/v2/api/me/nbtext')…` הופכת לפונקציה: `function nbKitInit(){ GET('/v2/api/me/nbtext').then(function(j){ if (j && j.ok) NB_WA_T = j.text || ''; }).catch(function(){}); }` (הרכיב נטען לפני העוזרים של הדף — אין קוד שרץ בטעינה).

- [ ] **Step 4: מסך נכס נולד**
  - ב-CSS של `V2_NB_HTML`: למחוק את השורות של `.nb … .notes` (שעברו לרכיב). **להשאיר** `.fld`, `.btn…`, `#sheet…`, `.mRow…`, `.more`, `.empty`.
  - `<div id="list"></div>` → `<div id="list" class="nbk"></div>`.
  - לפני `<script>` הראשי: `<!--NB_KIT-->`.
  - `var ROWS = [], BUCKETS = [], TOTAL = 0, AGE = -1, MGR = false, MEETS = [];` → בלי `MGR = false,`; למחוק את שורת `var ST_LABEL…`.
  - למחוק את הפונקציות שעברו (nbCard, nbDial, markContact, NB_WA_T+GET, waOwner, MYNAME/AG_OPTS/IS_COORD/OFFICE_AG, agOpts…noteSave). להשאיר `NB_SHOWN, nbMore, setAge, openMeetings, fmtPrice`.
  - להוסיף במקומן:
    ```js
    function nbKitRows(){ return el('list')._src || []; }   // [NB-KIT 30/09] הכרטיסים מצביעים לרשימה המוצגת
    function nbKitRefresh(){ load(); }
    ```
  - באתחול (בתחילת ה-IIFE האחרון, לפני `GET('/api/auth/whoami')`): `nbKitInit();`.
  - הראוט: `return _page(V2_NB_HTML)` → `return _page(V2_NB_HTML.replace("<!--NB_KIT-->", V2_NB_KIT, 1))`.

- [ ] **Step 5:** `test_nb_kit.js` עובר; `vm.Script` על הסקריפט הראשי של מסך נכס נולד; `test_nb_client.js` (רצף טעינה) עובר; `ast`.
- [ ] **Step 6: קומיט.**

---

### Task 4: טאב "נכס נולד" במסך הנכסים

**Files:**
- Modify: `effie_v2.py` — `V2_PROPS_HTML` (CSS קטן, סגמנט, קישור, סימון רכיב, JS), הראוט `/v2/props`.
- Test: `scratchpad/test_props_nb.js`

**Interfaces:**
- Consumes: `V2_NB_KIT` (Task 3), `POST /api/search/newborn` (Task 2).
- Produces: `NBRES`, `NB_SUM`, `NB_RENT`, `_applyNb(j)`, `nbKitRows()`, `nbKitRefresh()`.

- [ ] **Step 1: טסט**

```js
// scratchpad/test_props_nb.js — load/render של מסך הנכסים עם טאב נכס נולד (קוד אמיתי, DOM מדומה)
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync('/Users/eyal/Documents/GitHub/remax-bot/effie_v2.py', 'utf8');
const ps = src.indexOf('V2_PROPS_HTML'), s1 = src.indexOf('<script>', src.indexOf('<!--NB_KIT-->', ps)), s2 = src.indexOf("</script></body></html>'''", s1);
const pageJs = src.slice(s1 + 8, s2); new vm.Script(pageJs);
const ks = src.indexOf('V2_NB_KIT = r"""'), kj = src.indexOf('<script>', ks), ke = src.indexOf('</script>', kj);
const kitJs = src.slice(kj + 8, ke);
// הרצה חלקית: רק הפונקציות שנבדקות (load/render/setMode + _applyNb) בסביבה מדומה
let n = 0; const eq = (a, b, m) => { n++; if (JSON.stringify(a) !== JSON.stringify(b)) { console.error('FAIL', m, a, b); process.exit(1); } };
const els = {};
const mk = id => (els[id] = els[id] || {id, textContent: '', innerHTML: '', value: '', style: {}, classList: {t: {}, toggle(c, v){ this.t[c] = v; }}, getAttribute(){ return ''; }, parentNode: {children: []}});
const reqs = [];
const ctx = {console, JSON, Math, Date, Promise, setTimeout, clearTimeout, encodeURIComponent,
  localStorage: {getItem: () => null, setItem(){}},
  document: {querySelector: () => null, addEventListener(){}, getElementById: mk, body: {style: {}}},
  window: {addEventListener(){}, open(){}}, location: {search: '', replace(){}, href: ''},
  fetch: () => Promise.resolve({json: () => ({ok: true})}),
};
ctx.el = mk;
vm.runInNewContext(kitJs + '\n' + pageJs.replace(/\(function\(\)\{\n  GET\('\/api\/auth\/whoami'\)[\s\S]*$/, ''), ctx);
ctx.GET = u => { reqs.push(['GET', u]); return Promise.resolve({ok: true, results: []}); };
ctx.POST = (u, d) => { reqs.push(['POST', u, d && d.q]); return Promise.resolve(u.indexOf('newborn') >= 0
  ? {ok: true, results: [{key: 'k1', address: 'הנוטר 18', city: 'קרית ביאליק', price: '1,950,000', ageDays: 3}], summary: 'דירה בקרית ביאליק', rent: false}
  : {ok: true, results: []}); };
ctx.loadHot = () => {};
(async () => {
  mk('q').value = '4 חדרים קרית ביאליק';
  await ctx.load('4 חדרים קרית ביאליק');
  eq(reqs.some(r => r[1] === '/api/search/newborn' && r[2] === '4 חדרים קרית ביאליק'), true, 'newborn search sent with q');
  eq(ctx.NBRES.length, 1, 'results applied');
  eq(mk('cNb').textContent, 1, 'count shown');
  eq(mk('sgNb').style.display, '', 'tab visible with q');
  ctx.MODE = 'nb'; ctx.render();
  eq(mk('list').innerHTML.indexOf('class="nbk"') >= 0 && mk('list').innerHTML.indexOf('הנוטר 18') >= 0, true, 'nb cards rendered inside .nbk');
  eq(ctx.nbKitRows()[0].key, 'k1', 'kit rows = NBRES');
  reqs.length = 0; mk('q').value = '';
  await ctx.load('');
  eq(reqs.some(r => r[1] === '/api/search/newborn'), false, 'no newborn request without q');
  eq(ctx.NBRES.length, 0, 'cleared'); eq(mk('sgNb').style.display, 'none', 'tab hidden without q');
  eq(ctx.MODE, 'office', 'nb mode falls back to office when q cleared');
  eq(mk('nbAll').style.display, '', 'link to newborn shown without q');
  console.log('OK', n, 'checks');
})();
```

- [ ] **Step 2:** להריץ → נכשל.

- [ ] **Step 3: markup + CSS** ב-`V2_PROPS_HTML`:
  - ב-`.segs`: `overflow-x:auto` (4 סגמנטים ב-375px); `.segs .sg{…;white-space:nowrap;padding:9px 8px}`.
  - סגמנט רביעי אחרי "שלי":
    ```html
    <div class="sg" data-m="nb" id="sgNb" onclick="setMode(this)" style="display:none">נכס נולד <b id="cNb"></b></div>
    ```
  - מיד אחרי `</div>` של `.segs`:
    ```html
    <a id="nbAll" href="/v2/newborn" style="align-self:flex-start;font-size:12px;font-weight:700;color:#2E6BD6;text-decoration:none">לכל נכס נולד ←</a>
    ```
  - `<!--NB_KIT-->` לפני `<script>` הראשי.

- [ ] **Step 4: JS** ב-`V2_PROPS_HTML`:
  - משתנים + דבק (אחרי `var MODE = …`):
    ```js
    var NBRES = [], NB_SUM = '', NB_RENT = false;   // [NB-SEARCH 30/09] טאב נכס נולד (רק כשיש חיפוש)
    function _applyNb(j){ NBRES = (j && j.results) || []; NB_SUM = (j && j.summary) || ''; NB_RENT = !!(j && j.rent); }
    function nbKitRows(){ return NBRES; }
    function nbKitRefresh(){
      var q = el('q').value.trim();
      if (!q) return;
      POST('/api/search/newborn', {q: q}).then(function(j){ if (j && j.ok){ _applyNb(j); render(); } }).catch(function(){});
    }
    ```
  - ב-`load(q)` — לפני `return Promise.all([`: `if (!q){ NBRES = []; NB_SUM = ''; NB_RENT = false; }`; ובתוך המערך, כפריט רביעי:
    ```js
    q ? step(POST('/api/search/newborn', {q: q}), 'props:nb', _applyNb) : Promise.resolve()
    ```
  - ב-`render()` — מיד אחרי `el('cMine').textContent = MINE.length;`:
    ```js
    var _hasQ = !!el('q').value.trim();
    if (el('cNb')) el('cNb').textContent = NBRES.length;
    if (el('sgNb')) el('sgNb').style.display = _hasQ ? '' : 'none';
    if (el('nbAll')) el('nbAll').style.display = _hasQ ? 'none' : '';
    if (MODE === 'nb' && !_hasQ){   // נמחק החיפוש בטאב נכס נולד → חזרה ל"המשרד שלנו"
      MODE = 'office';
      var _sgO = document.querySelector('#modes .sg[data-m="office"]');
      if (_sgO){ var _cs = _sgO.parentNode.children; for (var _i = 0; _i < _cs.length; _i++) _cs[_i].classList.toggle('on', _cs[_i] === _sgO); }
    }
    if (MODE === 'nb'){
      if (el('qSpin')) el('qSpin').style.display = 'none';
      el('sumLine').style.color = ''; el('sumLine').style.fontWeight = '';
      el('sumLine').textContent = NB_SUM ? NB_SUM + ' · נכס נולד' : 'נכס נולד';
      var _nh = '';
      NBRES.slice(0, 30).forEach(function(r, i){ try{ _nh += nbCard(r, i); }catch(e){} });
      el('list').innerHTML = _nh ? '<div class="nbk">' + _nh + '</div>' :
        '<div class="card empty"><div class="ic"><svg width="30" height="27" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg></div>' +
        '<div class="t">לא נמצאו נכסים בנכס נולד</div>' +
        '<div class="s">' + (NB_RENT ? 'נכס נולד מציג נכסים למכירה בלבד' : 'נסה ניסוח אחר — החיפוש מבין תקציב, חדרים ואזור') + '</div></div>';
      el('list')._src = NBRES;
      return;
    }
    ```
  - `qChanged`: בלי שינוי (במצב 'nb' — `load` כמו משרד/שת"פ).
  - באתחול, בתוך `.then` של whoami אחרי `el('avatarTx')…`:
    ```js
    MYNAME = j.name || '';
    MGR = (j.role === 'admin' || j.role === 'coordinator');
    if (MGR){
      IS_COORD = j.role === 'coordinator';
      GET('/api/my/agents').then(function(d){
        AG_OPTS = ((d && d.agents) || []).map(function(a){ return a.name; }).filter(function(a){ return a && a !== j.name; });
      }).catch(function(){});
    }
    ```
    ולפני `GET('/api/auth/whoami')`: `nbKitInit();`.
  - הראוט `/v2/props`: `return _page(V2_PROPS_HTML.replace("<!--NB_KIT-->", V2_NB_KIT, 1))`.

- [ ] **Step 5:** `test_props_nb.js` עובר; `vm.Script` על הסקריפט המלא; `ast`; הרגרסיות (`test_nb_kit.js`, `test_nb_client.js`, `test_home_swr.js`, `test_nb_limit.py`, `test_nb_search.py`, `test_parse_cache.py`).
- [ ] **Step 6: הרצה מקומית:** preview `effie-v2`, כניסה בחשבון הבדיקה, `/v2/props`: בלי חיפוש — אין טאב, יש קישור; חיפוש — טאב מופיע, מצב ריק מעוצב (אין נתונים מקומית); `/v2/newborn` נטען בלי שגיאות קונסול; הזרקת שורת דמה ל-`ROWS` + `render()` → כרטיס עם `getComputedStyle` זהה (radius 22px, padding) לכרטיס לפני השינוי.
- [ ] **Step 7: קומיט + יומן** ב-`remax-family/CLAUDE.md`.
