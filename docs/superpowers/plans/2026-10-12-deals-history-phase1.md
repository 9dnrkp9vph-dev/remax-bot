# היסטוריית עסקאות — שלב 1: תוכנית מימוש

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** לייבא את היסטוריית העסקאות של שלושת המשרדים (2015–2025) לטבלה `deal_history` ולבנות מסכי קריאה:
- "העסקאות שלי" לכל סוכן.
- "מחירי השוואה" לכולם.
- "ניהול": דוחות, לא שולם, לא דווח וחיפוש, למנהלים ולהנהלת חשבונות.

**Architecture:**
- **מודול חדש `deals_history.py`:** פונקציות טהורות לזיהוי כותרות, נרמול שורה, תצוגות לפי הרשאה וסטטיסטיקה. בנוסף פונקציה `register(app, G, page)` שמגדירה את הראוטים ואת דף `/v2/history`.
- **הייבוא רץ על המחשב של אייל** עם שני כלים:
  - `tools/deals_survey.py`: סקירה, קריאה בלבד.
  - `tools/import_deal_history.py`: ייבוא, עם ריצה יבשה לפני השמירה.

  הם מפענחים את הקבצים עם סיסמה שמוקלדת בהקלדה מוסתרת (`getpass`) ושולחים שורות מנורמלות ל-endpoint מוגן במפתח.
- **השרת:** שומר את השורות, מחיל עליהן כינויי סוכנים קנוניים ומגיש תצוגות מסוננות.

**Tech Stack:** Python 3.9, Flask (קיים), Supabase PostgREST דרך `supabase_db.py`, openpyxl 3.1.5 + msoffcrypto-tool 5.4.2 (כבר ב-requirements), JS ידני בתוך HTML כמו בשאר `effie_v2.py`.

**Spec:** `docs/superpowers/specs/2026-10-12-deals-history-design.md`

## Global Constraints
- **עברית ו-RTL מלא.** פלטה סגורה:
  - קרם `#F2EFE7`, נייבי `#1E3A5F`, כחול פעולה `#2E6BD6`.
  - זהב `#C29435`/`#E4C56B`, ירוק `#1FAF5E` (כפתור עם טקסט `#157A43`).
  - אדום `#C24040` למחיקה בלבד.
  - טקסט משני `#6B7280`.
- **רכיבים:** כרטיסים לבנים, radius 20–22px, צל `0 6px 20px rgba(30,58,95,.06)`. שטח מגע מינימלי 44px. שדות קלט ב-16px. בלי אימוג'ים. מצבי ריק מעוצבים: אייקון בעיגול זהב, כותרת והסבר.
- **שם המשרד מהקונפיג,** לעולם לא קבוע בקוד.
- **סיסמאות הקבצים:** אף פעם לא נכתבות לקוד, לריפו, ללוג או לקובץ. רק `getpass` (מקומי) או env (Render, שלב 2).
- **טבלאות קיימות לא משתנות.** רק `deal_history` חדשה.
- **הרשאות:**
  - **סוכן:** רואה רק שורות שה-`agent` הקנוני שלהן הוא הוא.
  - **מתאמת:** רואה את הסוכנים שלה.
  - **מנהלים והנהלת חשבונות:** `drole` ב-(`manager`,`developer`,`accountant`) רואים הכל.
  - **מחירי השוואה:** לא כוללים שם לקוח, טלפון, עמלות או שדות גבייה, ברמת ה-JSON.
- **"התחשבנות סוכן" לא מוצגת בשום מסך.** נשמרת ב-`raw` בלבד.
- **ייבוא ההיסטוריה לא כולל את 2026.**
- **בדיקות:**
  - כל קובץ Python עובר `ast.parse` ובדיקת כפילויות שמות פונקציה ברמת המודול.
  - כל סקריפט עמוד עובר `node --check`.
- **Git:** commit מקומי בלבד, אחרי `git pull --ff-only`. מוסיפים לקומיט רק קבצים של המשימה. בסוף כל commit:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus
1. **שורות סיכום ושורות ריקות בקבצי האקסל** (`סה"כ`, שורות של חודשים בלי סוכן) צריכות להיות מדולגות ולא להיכנס כעסקאות. בדיקה ב-Task 2.
2. **גיליונות משניים** (למשל `דוח לעו"ד`, `הפניות`, גיליון לכל חודש) מזוהים ככותרות ועלולים לייבא עסקאות פעמיים. רק גיליונות שאייל אישר ב-`deals_sources.json` מיובאים. בדיקה ב-Task 6.
3. **אותו מס"ד מופיע בשני גיליונות, או בלי מס"ד.** המפתח כולל את הגיליון ונופל למספר השורה. ייבוא חוזר לא מכפיל. בדיקה ב-Task 2 וב-Task 4.
4. **סוכן שמחובר כ"מנהל" או עם שם כללי** לא אמור לראות את כל ההיסטוריה דרך תצוגת "שלי". שם כללי מחזיר ריק. בדיקה ב-Task 5.
5. **בחיפוש מחירי השוואה עם שם לקוח** (למשל הקלדה של שם לקוח), התשובה לא מחזירה שורות לפי התאמה לשם, וגם לא שדות אישיים. החיפוש רק על עיר ורחוב. בדיקה ב-Task 5.

## File Structure
- `deals_history.py` (חדש): נרמול, תצוגות, סטטיסטיקה, ראוטים ודף. יחידה אחת לנושא, מחוץ ל-`effie_v2.py` הענק.
- `supabase_db.py` (שינוי קטן): `deal_history_upsert`, `deal_history_all`.
- `effie_v2.py` (שינוי קטן): קריאה ל-`deals_history.register` בתוך `register`, וקישורים לדף מהבית ומ"תהליכים ועסקאות".
- `tools/deals_survey.py` (חדש): סקירה מקומית, קריאה בלבד.
- `tools/import_deal_history.py` (חדש): ייבוא מקומי, ריצה יבשה ואז שמירה.
- `tools/deals_sources.json`, `tools/deals_agent_map.json` (חדשים, נוצרים מהסקירה ומאושרים ע"י אייל): שם קובץ, גיליון ושמות סוכנים בלבד. בלי פרטי לקוחות ובלי סיסמאות.
- `tests/deals_history/` (חדש): בדיקות שרצות עם `python3 <file>`, בלי pytest, כמו בשאר הריפו.
- `../remax-family/supabase/migrations/20261012_deal_history.sql` (חדש): המיגרציה. אייל מריץ ב-SQL Editor.

---

### Task 1: סקירת הקבצים (קריאה בלבד) — מקור השאלות לאייל

**Files:**
- Create: `tools/deals_survey.py`
- Test: `tests/deals_history/test_survey_pick.py`

**Interfaces:**
- Produces:
  - `pick_file(paths: list[str]) -> str | None`: בחירת הקובץ המועדף לשנה.
  - `sheet_score(header_row: list) -> int`: כמה כותרות מוכרות יש בשורה.
  - ריצה מקומית שמדפיסה, לכל משרד ושנה:
    - הקבצים המועמדים והקובץ המוצע.
    - הגיליונות, ציון הכותרות ומספר השורות.
    - שמות הסוכנים הגולמיים עם ספירה.
  - כותבת הצעה ל-`tools/deals_sources.json` ול-`tools/deals_agent_map.json`, לאישור.
- Consumes: `deals_history.find_header_row`, `deals_history.HEADER_FIELDS` מ-Task 2. **Task 2 נבנה ראשון בפועל,** ו-Task 1 נשאר ראשון בתיאור כי הוא מקור השאלות.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_survey_pick.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.deals_survey import pick_file
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
ck(pick_file(["a/מעקב עסקאות 2022 .xlsx", "a/מעקב עסקאות 2022 סופי.xlsx"]) == "a/מעקב עסקאות 2022 סופי.xlsx", "סופי wins")
ck(pick_file(["a/מעקב עסקאות 2021.xlsx", "a/מעקב עסקאות 2021 מעודכן.xlsm"]) == "a/מעקב עסקאות 2021 מעודכן.xlsm", "מעודכן wins")
ck(pick_file(["a/x (Eyal Shmul's conflicted copy 2026-03-19).xlsx", "a/x.xlsx"]) == "a/x.xlsx", "no conflicted")
ck(pick_file(["a/מעקב 2020 (version 1).xlsx", "a/מעקב 2020.xlsx"]) == "a/מעקב 2020.xlsx", "no version 1")
ck(pick_file(["a/גיבוי מעקב 2025.xlsx", "a/מעקב 2025.xlsx"]) == "a/מעקב 2025.xlsx", "no backup")
ck(pick_file(["a/sms.xlsx", "a/מעקב עסקאות 2021.xlsx"]) == "a/מעקב עסקאות 2021.xlsx", "needs מעקב/עסקאות in name")
ck(pick_file(["a/only (conflicted copy).xlsx"]) == "a/only (conflicted copy).xlsx", "fallback to the only one")
ck(pick_file([]) is None, "empty")
print("OK", n, "checks")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/deals_history/test_survey_pick.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.deals_survey'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/__init__.py  (קובץ ריק)
```

```python
# tools/deals_survey.py
"""סקירת קבצי מעקב העסקאות בדרופבוקס — קריאה בלבד, רץ על המחשב של אייל.
מדפיס לכל משרד+שנה: קבצים, קובץ מוצע, גיליונות (ציון כותרות, שורות), שמות סוכנים גולמיים.
סיסמאות: getpass בלבד — לא נשמרות, לא מודפסות. פלט: אין פרטי לקוחות."""
import os, re, io, sys, json, getpass, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.expanduser("~/Library/CloudStorage/Dropbox/הפרלמנט")
BRANCH_DIRS = {"bialik": "אייל/מעקב עסקאות", "motzkin": "אוהד/מעקב עסקאות מוצקין",
               "kiryat_yam": "מעקב עסקאות קרית ים"}
PW_GROUP = {"bialik": "ביאליק", "motzkin": "מוצקין + קרית ים", "kiryat_yam": "מוצקין + קרית ים"}
_BAD = re.compile(r"conflicted copy|'s changes|version 1|גיבוי|נשמר אוטומטית|לא פעיל|^~\$", re.I)
_GOOD = re.compile(r"סופי|מעודכן|עדכני")


def pick_file(paths):
    """הקובץ המועדף לשנה: שם עם מעקב/עסקאות, לא עותק/גיבוי/version 1; 'סופי'/'מעודכן' קודם;
    בשוויון — הארוך-שם (מפורט יותר) ואז לפי סדר. אם רק עותקים — הראשון."""
    if not paths:
        return None
    named = [p for p in paths if re.search(r"מעקב|עסקאות", os.path.basename(p))] or list(paths)
    clean = [p for p in named if not _BAD.search(os.path.basename(p))]
    pool = clean or named
    pool = sorted(pool, key=lambda p: (0 if _GOOD.search(os.path.basename(p)) else 1, p))
    return pool[0]


def _open(path, pw):
    import msoffcrypto, openpyxl
    with open(path, "rb") as f:
        raw = f.read()
    bio = io.BytesIO(raw)
    try:
        of = msoffcrypto.OfficeFile(io.BytesIO(raw))
        if of.is_encrypted():
            out = io.BytesIO()
            of.load_key(password=pw)
            of.decrypt(out)
            bio = out
    except Exception:
        bio = io.BytesIO(raw)
    bio.seek(0)
    return openpyxl.load_workbook(bio, read_only=True, data_only=True)


def survey(pws):
    from deals_history import find_header_row, normalize_header
    sources, agents = {}, {}
    for br, rel in BRANCH_DIRS.items():
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            print("!! חסרה תיקייה:", base); continue
        for yr in sorted(d for d in os.listdir(base) if re.fullmatch(r"20\d\d", d)):
            if yr == "2026":
                continue
            files = []
            for dp, _, fs in os.walk(os.path.join(base, yr)):
                files += [os.path.join(dp, f) for f in fs if re.search(r"\.xls[xmb]?$", f, re.I)]
            choice = pick_file(sorted(files))
            print("\n== %s %s · %d קבצים · מוצע: %s" % (PW_GROUP[br], yr, len(files),
                  os.path.relpath(choice, base) if choice else "—"))
            for f in sorted(files):
                print("   ", "*" if f == choice else " ", os.path.relpath(f, base))
            if not choice:
                continue
            try:
                wb = _open(choice, pws[PW_GROUP[br]])
            except Exception as e:
                print("   !! לא נפתח:", type(e).__name__); continue
            picked = []
            for ws in wb.worksheets:
                rows = list(ws.iter_rows(values_only=True, max_row=3000))
                hi, fields = find_header_row(rows)
                if hi is None:
                    print("    [%s] — אין כותרות מוכרות" % ws.title); continue
                hdr = [normalize_header(c) for c in rows[hi]]
                ai = fields.get("agent")
                cnt = collections.Counter()
                body = [r for r in rows[hi + 1:] if r and any(c not in (None, "") for c in r)]
                if ai is not None:
                    for r in body:
                        v = re.sub(r"\s+", " ", str(r[ai] or "")).strip()
                        if v:
                            cnt[v] += 1
                print("    [%s] כותרות מוכרות=%d שורות=%d סוכנים=%d" % (ws.title, len(fields), len(body), len(cnt)))
                if len(fields) >= 6 and "agent" in fields:
                    picked.append(ws.title)
                    for nm, c in cnt.items():
                        agents.setdefault(br + "|" + nm, 0)
                        agents[br + "|" + nm] += c
            sources["%s|%s" % (br, yr)] = {"file": os.path.relpath(choice, ROOT), "sheets": picked[:1]}
    return sources, agents


def main():
    print("סקירת קבצי מעקב עסקאות — קריאה בלבד. הסיסמאות לא נשמרות ולא מודפסות.")
    pws = {g: getpass.getpass("סיסמת %s: " % g) for g in ("ביאליק", "מוצקין + קרית ים")}
    sources, agents = survey(pws)
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "deals_sources.json"), "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=1, sort_keys=True)
    amap = {k: "" for k in sorted(agents)}   # אייל ממלא: שם קנוני / "-" = לא סוכן
    with open(os.path.join(here, "deals_agent_map.json"), "w", encoding="utf-8") as f:
        json.dump(amap, f, ensure_ascii=False, indent=1)
    print("\n== שמות סוכנים גולמיים (משרד | שם : מספר שורות) ==")
    for k in sorted(agents, key=lambda k: (k.split("|")[0], -agents[k])):
        print("   %s : %d" % (k, agents[k]))
    print("\nנכתבו tools/deals_sources.json ו-tools/deals_agent_map.json להצעה ואישור.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/deals_history/test_survey_pick.py`
Expected: `OK 8 checks`

- [ ] **Step 5: Commit**

```bash
git pull --ff-only
git add tools/__init__.py tools/deals_survey.py tests/deals_history/test_survey_pick.py
git commit -m "היסטוריית עסקאות: סקירת הקבצים (קריאה בלבד) — בחירת קובץ לשנה, גיליונות, שמות סוכנים

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: אייל מריץ את הסקירה (בטרמינל שלו), ושואלים אותו את השאלות**

Run (אצל אייל): `cd ~/Documents/GitHub/remax-bot && python3 tools/deals_survey.py`

מהפלט מכינים לאייל את השאלות, ולא ממשיכים ל-Task 4 עד שהוא עונה:
1. **טבלת שנה ← קובץ ← גיליון:** מאשר או מתקן.
2. **מיפוי שמות סוכנים:** לכל שם גולמי, מי הוא (שם מלא קנוני), או "-" אם זה לא סוכן (שורת סיכום או שם משרד). למלא את `tools/deals_agent_map.json` לפי התשובות.
3. **שמות שהם כנראה סוכנים שעזבו:** איך להציג אותם (שם מלא).

---

### Task 2: נרמול — כותרות, שורה, מפתח

**Files:**
- Create: `deals_history.py`
- Test: `tests/deals_history/test_normalize.py`

**Interfaces:**
- Produces:
  - `HEADER_FIELDS: list[tuple[str, list[str]]]`
  - `normalize_header(v) -> str`
  - `find_header_row(rows: list[tuple]) -> (int | None, dict[field, col_index])`
  - `parse_date(v) -> datetime.date | None`
  - `parse_num(v) -> float | None`
  - `split_client(s) -> (name, phone)`
  - `norm_side(s) -> str`
  - `normalize_row(cells: tuple, fields: dict, ctx: dict) -> (status, row)`: status ∈ `ok`/`skip`/`broken`. ctx: `branch, year, sheet, row_idx`. row dict עם עמודות הטבלה, `src_key` ו-`raw`.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_normalize.py
import sys, os, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
H26 = ("חודש", 'מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סטאוס טיפול בגבייה", "טל ושם לקוח",
       "אייליסט", "על מי לדווח", "מתווך בצד השני", "הערה", 'ממוצע עמלה לפני מע"מ', "הנחה לפני מעמ", "סכום העסקה",
       'עמלה כולל מע"מ', "עמלה לפני מעמ", "מאיפה הגיע הלקוח", "התקבל כסף", "הופקד", "חשבונית", "קבלה",
       "דווח במערכת", "אישור לרימקס", "התחשבנות סוכן", 'עו"ד / הערות')
rows = [("דוח עסקאות",) + (None,) * 26, H26]
hi, F = D.find_header_row(rows)
ck(hi == 1, "header row")
ck(F["agent"] == 6 and F["street"] == 4 and F["commission_net"] == 17 and F["serial"] == 1, ("fields", F))
ck("commission_avg" not in F and F.get("commission_net") != 13, "ממוצע עמלה is not commission_net")
ck(F["other_broker"] == 11 and F["lawyer_notes"] == 26 and F["receipt_no"] == 22, "exact before prefix")
ctx = {"branch": "motzkin", "year": 2025, "sheet": "עסקאות25", "row_idx": 7}
r = (1, 12, dt.datetime(2025, 1, 14), "קרית מוצקין", "הגפן 4", "מוכר", " משה  כהן ", "טרם שולם",
     "דנה לוי 050-1234567", None, None, "אנגלו סכסון", "", 9000, 0, "1,850,000", 21240, 18000, "יד2",
     None, None, 4512, 4513, dt.datetime(2025, 2, 3), None, 9000, "עו\"ד כהן")
st, row = D.normalize_row(r, F, ctx)
ck(st == "ok", st)
ck(row["src_key"] == "motzkin|2025|עסקאות25|12", row["src_key"])
ck(row["deal_date"] == "2025-01-14" and row["city"] == "קרית מוצקין" and row["street"] == "הגפן 4", row)
ck(row["side"] == "מוכר" and row["agent"] == "משה כהן", row["agent"])
ck(row["client_name"] == "דנה לוי" and row["client_phone"] == "0501234567", (row["client_name"], row["client_phone"]))
ck(row["deal_amount"] == 1850000 and row["commission_net"] == 18000 and row["commission_gross"] == 21240, row)
ck(row["paid_amount"] is None and row["invoice_no"] == "4512" and row["reported_date"] == "2025-02-03", row)
ck(row["raw"]["התחשבנות סוכן"] == "9000" and "agent_settlement" not in row, "settlement only in raw")
ck(row["year"] == 2025 and row["branch"] == "motzkin", "ctx")
# בלי מס"ד → מספר שורה
r2 = list(r); r2[1] = None
ck(D.normalize_row(tuple(r2), F, ctx)[1]["src_key"] == "motzkin|2025|עסקאות25|r7", "row fallback")
# שורת סיכום / ריקה
ck(D.normalize_row((None,) * 27, F, ctx)[0] == "skip", "empty")
s = [None] * 27; s[6] = 'סה"כ'; s[17] = 50000
ck(D.normalize_row(tuple(s), F, ctx)[0] == "skip", "summary")
s = [None] * 27; s[0] = "ינואר"; s[17] = 50000
ck(D.normalize_row(tuple(s), F, ctx)[0] == "skip", "month total without agent")
s = [None] * 27; s[6] = "משה"
ck(D.normalize_row(tuple(s), F, ctx)[0] == "broken", "agent only = broken")
# מבנה 2016: כתובת אחת
H16 = ("תאריך עסקה", "כתובת", "קונה / מוכר", "סוכן", "הנחה", "סכום עסקה", "עמלה כולל מעמ", "עמלה לפני מעמ", "הערות",
       "התקבל כסף", "הופקד", "חשבונית מס קבלה", "אישור לרימקס", "התחשבנות סוכן", "עו\"ד ויסמן / מאיוסט")
hi, F16 = D.find_header_row([H16])
st, row = D.normalize_row(("12/05/16", "הרצל 5 קרית ביאליק", "קונה", "נחום", None, "980000", None, "17,000", None,
                           "17000", "כן", "1023", None, None, "ויסמן"), F16, {"branch": "bialik", "year": 2016, "sheet": "מלא", "row_idx": 3})
ck(st == "ok" and row["deal_date"] == "2016-05-12" and row["city"] == "קרית ביאליק" and row["street"] == "הרצל 5", row)
ck(row["paid_amount"] == 17000 and row["invoice_no"] == "1023" and row["lawyer_notes"] == "ויסמן", row)
# עזרים
ck(D.parse_date(45306) == dt.date(2024, 1, 15), "excel serial")
ck(D.parse_date("3.2.2021") == dt.date(2021, 2, 3) and D.parse_date("טקסט") is None, "date text")
ck(D.parse_num("₪ 1,250,000") == 1250000 and D.parse_num("כן") is None and D.parse_num(0) == 0, "num")
ck(D.split_client("0521234567 יוסי") == ("יוסי", "0521234567") and D.split_client("") == ("", ""), "client")
ck(D.norm_side("משכיר") == "משכיר" and D.norm_side("שוכר") == "שוכר" and D.norm_side("קונה+מוכר") == "קונה+מוכר", "side")
print("OK", n, "checks")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/deals_history/test_normalize.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'deals_history'`

- [ ] **Step 3: Write minimal implementation**

```python
# deals_history.py
"""[DEALS-HISTORY 12/10] היסטוריית עסקאות — נרמול שורות מקבצי 'מעקב עסקאות', תצוגות לפי הרשאה,
סטטיסטיקה, ראוטים ודף /v2/history. ספק: docs/superpowers/specs/2026-10-12-deals-history-design.md"""
import re
import datetime as _dt

BRANCHES = {"bialik": "ביאליק", "motzkin": "מוצקין", "kiryat_yam": "קרית ים"}

# שדה → כותרות אפשריות (התאמה מדויקת קודם, אחר כך תחילית). הסדר חשוב: ספציפי לפני כללי.
HEADER_FIELDS = [
    ("serial", ['מס"ד', "מסד", "מס'"]),
    ("month", ["חודש"]),
    ("deal_date", ["תאריך עסקה", "תאריך"]),
    ("city", ["עיר"]),
    ("street", ["רחוב"]),
    ("address", ["כתובת"]),
    ("side", ["קונה / מוכר", "קונה/מוכר", "צד"]),
    ("other_broker", ["מתווך בצד השני"]),
    ("agent", ["סוכן", "מתווך"]),
    ("collection_status", ["סטאוס טיפול בגבייה", "סטטוס טיפול בגבייה"]),
    ("client", ["טל ושם לקוח", "שם לקוח", "לקוח"]),
    ("notes", ["הערה", "הערות"]),
    ("discount", ["הנחה לפני מעמ", 'הנחה לפני מע"מ', "הנחה"]),
    ("deal_amount", ["סכום העסקה", "סכום עסקה"]),
    ("commission_gross", ["עמלה כולל מעמ", 'עמלה כולל מע"מ']),
    ("commission_net", ["עמלה לפני מעמ", 'עמלה לפני מע"מ']),
    ("lead_source", ["מאיפה הגיע הלקוח"]),
    ("paid_amount", ["התקבל כסף"]),
    ("deposited", ["הופקד"]),
    ("invoice_no", ["חשבונית", "חשבונית מס קבלה"]),
    ("receipt_no", ["קבלה"]),
    ("reported_date", ["דווח במערכת"]),
    ("remax_approved", ["אישור לרימקס"]),
    ("lawyer_notes", ['עו"ד / הערות', 'עו"ד']),
]
_PREFIX_OK = {"lawyer_notes", "invoice_no"}   # כותרות שמגיעות עם המשך ('עו"ד ויסמן / ...', 'חשבונית מס קבלה')
CITIES = ["קרית מוצקין", "קרית ביאליק", "קרית ים", "קרית אתא", "קרית חיים", "חיפה", "עכו", "נשר"]


def normalize_header(v):
    t = re.sub(r"\s+", " ", str(v or "")).strip()
    return t.replace("״", '"').replace("׳", "'").replace("קריית", "קרית")


def find_header_row(rows, scan=10):
    """השורה הראשונה (מתוך scan) עם ≥4 כותרות מוכרות → (index, {field: col})."""
    for i, r in enumerate(rows[:scan]):
        fields = {}
        hdr = [normalize_header(c) for c in (r or ())]
        for field, names in HEADER_FIELDS:
            for col, h in enumerate(hdr):
                if not h or col in fields.values():
                    continue
                if h in names or (field in _PREFIX_OK and any(h.startswith(nm) for nm in names)):
                    fields[field] = col
                    break
        for col, h in enumerate(hdr):
            if h == "התחשבנות סוכן":
                fields["_settlement"] = col   # נשמר רק ב-raw — לא מוצג באפי
        if len([k for k in fields if not k.startswith("_")]) >= 4:
            return i, fields
    return None, {}


def parse_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return _dt.date(1899, 12, 30) + _dt.timedelta(days=int(v))
    m = re.match(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", str(v))
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return _dt.date(y, mo, d)
        except ValueError:
            return None
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", str(v))
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_num(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[₪,\s]", "", str(v))
    try:
        return float(t)
    except ValueError:
        return None


def _num_out(v):
    x = parse_num(v)
    if x is None:
        return None
    return int(x) if float(x).is_integer() else round(x, 2)


_PHONE = re.compile(r"0[2-9]\d?[\s\-]?\d{3}[\s\-]?\d{4}")


def split_client(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if not s:
        return "", ""
    m = _PHONE.search(s)
    phone = re.sub(r"\D", "", m.group(0)) if m else ""
    name = (s[:m.start()] + " " + s[m.end():]) if m else s
    name = re.sub(r"\s+", " ", re.sub(r"[-–,/|]+", " ", name)).strip()
    return name, phone


def norm_side(s):
    t = re.sub(r"\s+", "", str(s or ""))
    parts = [w for w in ("קונה", "מוכר", "משכיר") if w in t]
    if "שוכר" in t.replace("משכיר", ""):
        parts.append("שוכר")
    return "+".join(parts) if parts else re.sub(r"\s+", " ", str(s or "")).strip()


def _cell(cells, fields, f):
    i = fields.get(f)
    if i is None or i >= len(cells):
        return None
    v = cells[i]
    return None if (isinstance(v, str) and not v.strip()) else v


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.strftime("%d/%m/%Y")
    return re.sub(r"\s+", " ", str(v)).strip()


def _split_address(addr):
    a = normalize_header(addr)
    for c in CITIES:
        if c in a:
            return c, re.sub(r"\s+", " ", a.replace(c, " ").strip(" ,"))
    return "", a


def normalize_row(cells, fields, ctx):
    """שורת אקסל → ('ok'|'skip'|'broken', row). row בעמודות הטבלה + src_key + raw (כל התאים כטקסט)."""
    cells = tuple(cells or ())
    if not any(c not in (None, "") and not (isinstance(c, str) and not c.strip()) for c in cells):
        return "skip", None
    agent = _txt(_cell(cells, fields, "agent"))
    if re.search(r'סה"כ|סה״כ|סיכום|total', agent, re.I):
        return "skip", None
    amount = _num_out(_cell(cells, fields, "deal_amount"))
    comm = _num_out(_cell(cells, fields, "commission_net"))
    city = _txt(_cell(cells, fields, "city"))
    street = _txt(_cell(cells, fields, "street"))
    if not street and "address" in fields:
        c2, street = _split_address(_txt(_cell(cells, fields, "address")))
        city = city or c2
    if not agent:
        return "skip", None   # שורות סיכום חודשיות / הערות — בלי סוכן אין עסקה
    ddate = parse_date(_cell(cells, fields, "deal_date"))
    if not ddate and amount is None and comm is None and not street:
        return "broken", {"agent": agent, "src_row": ctx["row_idx"], "sheet": ctx["sheet"]}
    name, phone = split_client(_cell(cells, fields, "client"))
    serial = _txt(_cell(cells, fields, "serial"))
    key_tail = serial if re.fullmatch(r"\d+", serial or "") else "r%d" % ctx["row_idx"]
    rep = parse_date(_cell(cells, fields, "reported_date"))
    hdr_names = ctx.get("headers") or []   # כל התאים המקוריים לפי כותרת (כשהכותרות ידועות)
    raw = {}
    for i, c in enumerate(cells):
        h = hdr_names[i] if i < len(hdr_names) else ""
        if c not in (None, "") and not (isinstance(c, str) and not c.strip()) and h:
            raw[h] = _txt(c)
    si = fields.get("_settlement")
    if si is not None and si < len(cells) and cells[si] not in (None, ""):
        raw["התחשבנות סוכן"] = _txt(cells[si])
    row = {
        "branch": ctx["branch"], "year": int(ctx["year"]), "src_sheet": ctx["sheet"], "src_row": ctx["row_idx"],
        "src_serial": serial, "src_key": "%s|%s|%s|%s" % (ctx["branch"], ctx["year"], ctx["sheet"], key_tail),
        "deal_date": ddate.isoformat() if ddate else None, "city": city, "street": street,
        "side": norm_side(_cell(cells, fields, "side")), "agent": agent,
        "client_name": name, "client_phone": phone,
        "other_broker": _txt(_cell(cells, fields, "other_broker")),
        "deal_amount": amount, "commission_gross": _num_out(_cell(cells, fields, "commission_gross")),
        "commission_net": comm, "discount": _num_out(_cell(cells, fields, "discount")),
        "lead_source": _txt(_cell(cells, fields, "lead_source")),
        "paid_amount": _num_out(_cell(cells, fields, "paid_amount")),
        "deposited": _txt(_cell(cells, fields, "deposited")),
        "invoice_no": _txt(_cell(cells, fields, "invoice_no")),
        "receipt_no": _txt(_cell(cells, fields, "receipt_no")),
        "reported_date": rep.isoformat() if rep else None,
        "remax_approved": _txt(_cell(cells, fields, "remax_approved")),
        "collection_status": _txt(_cell(cells, fields, "collection_status")),
        "notes": _txt(_cell(cells, fields, "notes")),
        "lawyer_notes": _txt(_cell(cells, fields, "lawyer_notes")),
        "raw": raw,
    }
    return "ok", row
```


- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/deals_history/test_normalize.py && python3 tests/deals_history/test_survey_pick.py`
Expected: `OK 25 checks` ו-`OK 8 checks`

- [ ] **Step 5: Commit**

```bash
git pull --ff-only
git add deals_history.py tests/deals_history/test_normalize.py
git commit -m "היסטוריית עסקאות: נרמול שורות — זיהוי כותרות בכל המבנים, תאריכים/סכומים/לקוח, מפתח יציב, דילוג על סיכומים

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: מיגרציה ושכבת הנתונים

**Files:**
- Create: `/Users/eyal/Documents/remax-family/supabase/migrations/20261012_deal_history.sql`
- Modify: `supabase_db.py` (הוספה בסוף הקובץ)
- Test: `tests/deals_history/test_db.py`

**Interfaces:**
- Produces:
  - `supabase_db.deal_history_upsert(rows: list[dict]) -> int`: upsert לפי (`office_id`,`src_key`).
  - `supabase_db.deal_history_all() -> list[dict]`: כל השורות, בלי `raw`.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_db.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import supabase_db as S
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
calls = []
class R:
    def __init__(s, j=None): s._j = j
    def raise_for_status(s): pass
    def json(s): return s._j
class Q:
    def post(s, url, headers=None, params=None, json=None, timeout=None):
        calls.append(("post", url, params, json)); return R([])
    def get(s, url, headers=None, params=None, timeout=None):
        calls.append(("get", url, params, None)); return R([{"id": "1", "agent": "משה"}])
S.requests = Q(); S.SUPABASE_URL = "https://x"; S.SB_OFFICE_ID = "OFF"
rows = [{"src_key": "motzkin|2025|s|1", "agent": "משה", "raw": {"a": "b"}},
        {"src_key": "motzkin|2025|s|1", "agent": "משה כהן", "raw": {}},
        {"src_key": "motzkin|2025|s|2", "agent": "דנה"}]
ck(S.deal_history_upsert(rows) == 2, "dedup by src_key")
p = calls[0]
ck(p[1].endswith("/rest/v1/deal_history") and p[2]["on_conflict"] == "office_id,src_key", p[2])
ck(all(r["office_id"] == "OFF" for r in p[3]) and set(p[3][0]) == set(p[3][1]), "office + uniform cols")
ck([r["agent"] for r in p[3] if r["src_key"].endswith("|1")] == ["משה כהן"], "last wins")
out = S.deal_history_all()
g = calls[-1]
ck(g[0] == "get" and "raw" not in g[2]["select"] and out[0]["agent"] == "משה", g[2]["select"])
print("OK", n, "checks")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/deals_history/test_db.py`
Expected: FAIL — `AttributeError: module 'supabase_db' has no attribute 'deal_history_upsert'`

- [ ] **Step 3: Write minimal implementation**

```sql
-- 20261012_deal_history.sql — היסטוריית עסקאות (שורה = צד אחד של עסקה, כמו באקסל 'מעקב עסקאות').
-- הרצה: SQL Editor של Supabase. לא נוגע בטבלאות קיימות. גישה דרך השרת בלבד (RLS בלי policies).
create table if not exists deal_history (
  id                uuid primary key default gen_random_uuid(),
  office_id         uuid not null default '11111111-1111-4111-8111-111111111111',
  src_key           text not null,
  branch            text not null,
  year              int  not null,
  src_path          text not null default '',
  src_sheet         text not null default '',
  src_row           int,
  src_serial        text not null default '',
  deal_date         date,
  city              text not null default '',
  street            text not null default '',
  side              text not null default '',
  agent             text not null default '',
  agent_raw         text not null default '',
  client_name       text not null default '',
  client_phone      text not null default '',
  other_broker      text not null default '',
  deal_amount       numeric,
  commission_gross  numeric,
  commission_net    numeric,
  discount          numeric,
  lead_source       text not null default '',
  paid_amount       numeric,
  deposited         text not null default '',
  invoice_no        text not null default '',
  receipt_no        text not null default '',
  reported_date     date,
  remax_approved    text not null default '',
  collection_status text not null default '',
  notes             text not null default '',
  lawyer_notes      text not null default '',
  raw               jsonb not null default '{}'::jsonb,
  app_deal_id       text not null default '',
  dirty             jsonb not null default '{}'::jsonb,
  src_hash          text not null default '',
  missing_since     timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  synced_at         timestamptz,
  unique (office_id, src_key)
);
create index if not exists deal_history_agent_idx on deal_history (office_id, agent);
create index if not exists deal_history_date_idx  on deal_history (office_id, deal_date desc);
alter table deal_history enable row level security;
-- אין policies בכוונה: anon לא קורא כלום; השרת (service_role) עוקף RLS.
```

```python
# supabase_db.py — בסוף הקובץ
# ── [DEALS-HISTORY 12/10] היסטוריית עסקאות ──────────────────────────────────────
_DH_COLS = ("id,src_key,branch,year,src_sheet,src_row,src_serial,deal_date,city,street,side,agent,"
            "client_name,client_phone,other_broker,deal_amount,commission_gross,commission_net,discount,"
            "lead_source,paid_amount,deposited,invoice_no,receipt_no,reported_date,remax_approved,"
            "collection_status,notes,lawyer_notes,app_deal_id,missing_since,updated_at")


def deal_history_upsert(rows):
    """upsert לפי (office_id, src_key) במנות — עמודות אחידות, האחרון לכל מפתח גובר."""
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    prepared = []
    for r in rows or []:
        x = dict(r)
        x["office_id"] = SB_OFFICE_ID
        x["updated_at"] = now
        prepared.append(x)
    keys = set()
    for x in prepared:
        keys |= set(x.keys())
    for x in prepared:
        for k in keys:
            x.setdefault(k, None)
    return _upsert_bulk("deal_history", prepared, key_field="src_key")


def deal_history_all():
    """כל השורות של המשרד (בלי raw — הוא גדול ולא נחוץ לתצוגות)."""
    return _get_all("deal_history", _DH_COLS)
```

שים לב ל-`_upsert_bulk`: אם יש לו `single=None`, כשל של מנה זורק חריגה. זה רצוי בייבוא, כדי שהדוח יראה את הכשל ולא יבלע אותו.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/deals_history/test_db.py`
Expected: `OK 5 checks`

- [ ] **Step 5: Commit (שני ריפו)**

```bash
cd /Users/eyal/Documents/GitHub/remax-bot && git pull --ff-only
git add supabase_db.py tests/deals_history/test_db.py
git commit -m "היסטוריית עסקאות: שכבת נתונים — deal_history_upsert/all

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd /Users/eyal/Documents/remax-family && git add supabase/migrations/20261012_deal_history.sql
git commit -m "מיגרציה: טבלת deal_history (היסטוריית עסקאות)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: endpoint הייבוא (מוגן במפתח) וקנוניזציית סוכנים

**Files:**
- Modify: `deals_history.py` (הוספה)
- Modify: `effie_v2.py`, בתוך `register(app, G)`, אחרי הגדרת `_page`: קריאה ל-`deals_history.register`
- Test: `tests/deals_history/test_import_route.py`

**Interfaces:**
- Consumes:
  - `supabase_db.deal_history_upsert`
  - `G["_canon_agent_name"]`, `G["_web_auth"]`, `G["_etag_wrap"]`, `G["_log_activity"]`
- Produces:
  - `canon_agent(raw_name, branch, amap, canon) -> str`: מיפוי לפי `amap` (`"branch|raw" → שם`; `"-"` = לא סוכן, מחזיר `""`), ואז `canon()`.
  - `register(app, G, page)`: כרגע רק `POST /v2/api/deals/history/import`. כותרת `X-Import-Key` מול env `DEALS_IMPORT_KEY`. גוף: `{rows:[...], amap:{...}}`. מחזיר `{ok, saved, skipped_no_agent}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_import_route.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["DEALS_IMPORT_KEY"] = "K123"
from flask import Flask, jsonify
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
ck(D.canon_agent("משה", "motzkin", {"motzkin|משה": "משה כהן"}, lambda x: x) == "משה כהן", "mapped")
ck(D.canon_agent("סיכום", "motzkin", {"motzkin|סיכום": "-"}, lambda x: x) == "", "not an agent")
ck(D.canon_agent("בן", "bialik", {}, lambda x: {"בן": "בן קדוש"}.get(x, x)) == "בן קדוש", "alias canon")
saved = []
class SB:
    def enabled(self): return True
    def deal_history_upsert(self, rows): saved.extend(rows); return len(rows)
G = {"_canon_agent_name": lambda x: x, "_web_auth": lambda: None, "_etag_wrap": lambda d: jsonify(d),
     "_log_activity": lambda *a, **k: None, "_sbdb": SB(), "_load_config": lambda: {}}
app = Flask("t")
D.register(app, G, lambda html: html)
c = app.test_client()
body = {"rows": [{"src_key": "motzkin|2025|s|1", "agent": "משה", "branch": "motzkin", "year": 2025},
                 {"src_key": "motzkin|2025|s|2", "agent": "סיכום", "branch": "motzkin", "year": 2025}],
        "amap": {"motzkin|משה": "משה כהן", "motzkin|סיכום": "-"}}
ck(c.post("/v2/api/deals/history/import", json=body).status_code == 403, "no key")
ck(c.post("/v2/api/deals/history/import", json=body, headers={"X-Import-Key": "bad"}).status_code == 403, "bad key")
r = c.post("/v2/api/deals/history/import", json=body, headers={"X-Import-Key": "K123"}).get_json()
ck(r["ok"] and r["saved"] == 1 and r["skipped_no_agent"] == 1, r)
ck(saved[0]["agent"] == "משה כהן" and saved[0]["agent_raw"] == "משה", saved[0])
os.environ["DEALS_IMPORT_KEY"] = ""
app2 = Flask("t2"); D.register(app2, G, lambda h: h)
ck(app2.test_client().post("/v2/api/deals/history/import", json=body, headers={"X-Import-Key": ""}).status_code == 403, "empty env = off")
print("OK", n, "checks")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/deals_history/test_import_route.py`
Expected: FAIL — `AttributeError: module 'deals_history' has no attribute 'canon_agent'`

- [ ] **Step 3: Write minimal implementation**

```python
# deals_history.py — הוספה
import os, time, hmac


def canon_agent(raw_name, branch, amap, canon):
    nm = re.sub(r"\s+", " ", str(raw_name or "")).strip()
    mapped = (amap or {}).get("%s|%s" % (branch, nm), "")
    if mapped == "-":
        return ""
    return canon(mapped or nm) or ""


def register(app, G, page):
    from flask import request, jsonify
    sb = G.get("_sbdb")
    key = (os.environ.get("DEALS_IMPORT_KEY") or "").strip()

    @app.route("/v2/api/deals/history/import", methods=["POST"])
    def v2_deals_history_import():
        k = (request.headers.get("X-Import-Key") or "").strip()
        if not key or not k or not hmac.compare_digest(k, key):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        if not (sb and sb.enabled()):
            return jsonify({"ok": False, "reason": "no_db"}), 503
        b = request.get_json(silent=True) or {}
        amap = b.get("amap") or {}
        out, skipped = [], 0
        for r in (b.get("rows") or [])[:2000]:
            raw_agent = str(r.get("agent", "") or "")
            ag = canon_agent(raw_agent, r.get("branch", ""), amap, G["_canon_agent_name"])
            if not ag:
                skipped += 1
                continue
            x = dict(r)
            x["agent_raw"], x["agent"] = raw_agent, ag
            out.append(x)
        saved = sb.deal_history_upsert(out) if out else 0
        _HIST_CACHE["ts"] = 0
        G["_log_activity"]("ייבוא", "system", "", "היסטוריית עסקאות — ייבוא", "%d שורות" % saved)
        return jsonify({"ok": True, "saved": saved, "skipped_no_agent": skipped})


_HIST_CACHE = {"ts": 0, "rows": []}
```

```python
# effie_v2.py — בתוך register(app, G), מיד אחרי הגדרת def _page(html): ... (שורה ~11667)
    # [DEALS-HISTORY 12/10] היסטוריית עסקאות — מודול נפרד (ראוטים + דף /v2/history)
    try:
        import deals_history as _dh
        _dh.register(app, G, _page)   # G = הגלובלים של app.py (כולל _sbdb, _web_auth, _canon_key…)
    except Exception as _dhe:
        if log: log.error(f"deals_history register failed: {_dhe}", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/deals_history/test_import_route.py`
Expected: `OK 8 checks`

Run (רגרסיה, השרת עולה עם המודול):
```bash
CLAUDE_API_KEY=x WARMUP_ON_BOOT=0 DAILY_REPORT=0 python3 -c "import app; print([r.rule for r in app.app.url_map.iter_rules() if 'history' in r.rule])"
```
Expected: `['/v2/api/deals/history/import']` (ובהמשך יתווספו עוד ראוטים).

- [ ] **Step 5: Commit**

```bash
git pull --ff-only
git add deals_history.py effie_v2.py tests/deals_history/test_import_route.py
git commit -m "היסטוריית עסקאות: endpoint ייבוא מוגן במפתח (DEALS_IMPORT_KEY) + מיפוי סוכנים קנוני

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: תצוגות, הרשאות, סטטיסטיקה וראוטי קריאה

**Files:**
- Modify: `deals_history.py`
- Test: `tests/deals_history/test_views.py`

**Interfaces:**
- Consumes: `supabase_db.deal_history_all`, `G["_web_auth"]`, `G["_canon_key"]`, `G["_scope_keys_phones"]`, `G["_etag_wrap"]`
- Produces:
  - `is_editor(s) -> bool`: `drole` ב-(`manager`,`developer`,`accountant`).
  - `view_agent(r) -> dict`, `view_comps(r) -> dict`, `view_full(r) -> dict`
  - `scope_rows(rows, s, canon_key, coord_keys) -> list`
  - `comps_search(rows, q, cap=200) -> {results, n_sale, avg_sale, n_rent, avg_rent}`
  - `stats(rows, year) -> {byBranch, byAgent, byMonth, total, prev}`
  - `unpaid(rows, since)`, `unreported(rows, since)`
  - ראוטים:
    - `GET /v2/api/deals/history/mine?year=`
    - `GET /v2/api/deals/history/comps?q=`
    - `GET /v2/api/deals/history/stats?year=` (עורכים)
    - `GET /v2/api/deals/history/open?kind=unpaid|unreported&since=` (עורכים)
    - `GET /v2/api/deals/history/search?q=` (עורכים)

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_views.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from flask import Flask, jsonify
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
R = [
 {"id": "1", "branch": "motzkin", "year": 2025, "deal_date": "2025-03-02", "city": "קרית מוצקין", "street": "הגפן 4",
  "side": "מוכר", "agent": "משה כהן", "client_name": "דנה", "client_phone": "0501234567", "deal_amount": 1800000,
  "commission_net": 18000, "commission_gross": 21240, "paid_amount": 18000, "reported_date": "2025-04-01",
  "collection_status": "", "invoice_no": "1", "receipt_no": "", "deposited": "", "remax_approved": "", "notes": "", "lawyer_notes": "", "other_broker": "", "lead_source": ""},
 {"id": "2", "branch": "bialik", "year": 2025, "deal_date": "2025-05-10", "city": "קרית ביאליק", "street": "הגפן 9",
  "side": "שוכר", "agent": "דנה לוי", "client_name": "יוסי", "client_phone": "0529999999", "deal_amount": 5000,
  "commission_net": 5000, "commission_gross": 5900, "paid_amount": None, "reported_date": None,
  "collection_status": "טרם שולם", "invoice_no": "", "receipt_no": "", "deposited": "", "remax_approved": "", "notes": "", "lawyer_notes": "", "other_broker": "", "lead_source": ""},
 {"id": "3", "branch": "motzkin", "year": 2024, "deal_date": "2024-02-01", "city": "קרית מוצקין", "street": "הגפן 4",
  "side": "קונה", "agent": "משה כהן", "client_name": "רון", "client_phone": "", "deal_amount": 1500000,
  "commission_net": 15000, "commission_gross": None, "paid_amount": None, "reported_date": None,
  "collection_status": "", "invoice_no": "", "receipt_no": "", "deposited": "", "remax_approved": "", "notes": "", "lawyer_notes": "", "other_broker": "", "lead_source": ""},
]
ck(D.is_editor({"drole": "accountant"}) and D.is_editor({"drole": "manager"}) and not D.is_editor({"drole": "agent"}), "editor")
a = D.view_agent(R[0])
ck(a["client"] == "דנה" and a["commission_net"] == 18000 and a["paid"] == 18000 and a["reported"] == "04/2025", a)
ck("client_phone" not in a and "commission_gross" not in a, "agent view minimal")
c = D.view_comps(R[0])
ck(set(c) == {"date", "address", "kind", "side", "price", "agent", "branch"} and c["kind"] == "מכירה", c)
ck(D.view_comps(R[1])["kind"] == "השכרה", "rent")
ck("התחשבנות סוכן" not in json.dumps(D.view_full(R[0]), ensure_ascii=False), "no settlement anywhere")
ck([r["id"] for r in D.scope_rows(R, {"role": "agent", "name": "משה כהן"}, lambda x: x.replace(" ", ""), set())] == ["1", "3"], "agent own")
ck(D.scope_rows(R, {"role": "agent", "name": "מנהל"}, lambda x: x.replace(" ", ""), set()) == [], "generic name sees nothing")
ck([r["id"] for r in D.scope_rows(R, {"role": "coordinator", "name": "אוצר"}, lambda x: x.replace(" ", ""), {"דנהלוי"})] == ["2"], "coordinator")
cs = D.comps_search(R, "הגפן מוצקין")
ck([x["date"] for x in cs["results"]] == ["02/03/2025", "01/02/2024"] and cs["n_sale"] == 2 and cs["avg_sale"] == 1650000, cs)
ck(D.comps_search(R, "דנה")["results"] == [] and D.comps_search(R, "")["results"] == [], "no client-name match, empty q")
st = D.stats(R, 2025)
ck(st["total"]["n"] == 2 and st["total"]["commission"] == 23000 and st["prev"]["n"] == 1, st["total"])
ck(st["byAgent"][0]["agent"] == "משה כהן" and st["byBranch"][0]["branch"] in ("motzkin", "bialik"), st["byAgent"])
ck([r["id"] for r in D.unpaid(R, 2024)] == ["3", "2"] and [r["id"] for r in D.unpaid(R, 2025)] == ["2"], "unpaid oldest first")
ck([r["id"] for r in D.unreported(R, 2024)] == ["3", "2"], "unreported")
# ראוטים
S = {"T": {"role": "agent", "drole": "agent", "name": "משה כהן"}, "M": {"role": "admin", "drole": "manager", "name": "מנהל"}}
from flask import request
class SB:
    def enabled(self): return True
    def deal_history_all(self): return R
G = {"_web_auth": lambda: S.get(request.headers.get("X-Auth-Token", "")), "_canon_key": lambda x: x.replace(" ", ""),
     "_scope_keys_phones": lambda *a, **k: (set(), set(), True), "_etag_wrap": lambda d: jsonify(d),
     "_canon_agent_name": lambda x: x, "_log_activity": lambda *a, **k: None, "_sbdb": SB()}
app = Flask("v"); D.register(app, G, lambda h: h); c = app.test_client()
m = c.get("/v2/api/deals/history/mine", headers={"X-Auth-Token": "T"}).get_json()
ck([x["id"] for x in m["results"]] == ["1", "3"] and m["years"] == [2025, 2024], m)
cp = c.get("/v2/api/deals/history/comps?q=הגפן", headers={"X-Auth-Token": "T"}).get_data(as_text=True)
ck("0501234567" not in cp and "דנה" not in cp.replace("דנה לוי", "") and "commission" not in cp and "client" not in cp and "paid" not in cp, "comps json has no private fields")
ck(c.get("/v2/api/deals/history/stats?year=2025", headers={"X-Auth-Token": "T"}).status_code == 403, "agent no stats")
ck(c.get("/v2/api/deals/history/stats?year=2025", headers={"X-Auth-Token": "M"}).get_json()["total"]["n"] == 2, "manager stats")
op = c.get("/v2/api/deals/history/open?kind=unpaid&since=2024", headers={"X-Auth-Token": "M"}).get_json()
ck([x["id"] for x in op["results"]] == ["3", "2"] and "client_phone" in op["results"][0], op)
ck(c.get("/v2/api/deals/history/search?q=0529999999", headers={"X-Auth-Token": "M"}).get_json()["results"][0]["id"] == "2", "manager search by phone")
ck(c.get("/v2/api/deals/history/mine").status_code == 401, "no auth")
print("OK", n, "checks")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/deals_history/test_views.py`
Expected: FAIL — `AttributeError: module 'deals_history' has no attribute 'is_editor'`

- [ ] **Step 3: Write minimal implementation**

```python
# deals_history.py — הוספה (מעל register)
EDITOR_DROLES = ("manager", "developer", "accountant")
_GENERIC = {"מנהל", "סוכן", ""}


def is_editor(s):
    return (s or {}).get("drole") in EDITOR_DROLES


def _dmy(iso):
    return "%s/%s/%s" % (iso[8:10], iso[5:7], iso[:4]) if iso else ""


def _addr(r):
    return ", ".join(x for x in (r.get("street") or "", r.get("city") or "") if x)


def _kind(side):
    return "השכרה" if any(w in (side or "") for w in ("שוכר", "משכיר")) else "מכירה"


def view_agent(r):
    rep = r.get("reported_date") or ""
    return {"id": r["id"], "date": _dmy(r.get("deal_date") or ""), "address": _addr(r), "side": r.get("side") or "",
            "client": r.get("client_name") or "", "price": r.get("deal_amount"),
            "commission_net": r.get("commission_net"), "paid": r.get("paid_amount"),
            "reported": ("%s/%s" % (rep[5:7], rep[:4])) if rep else "", "branch": r.get("branch"), "year": r.get("year")}


def view_comps(r):
    return {"date": _dmy(r.get("deal_date") or ""), "address": _addr(r), "kind": _kind(r.get("side")),
            "side": r.get("side") or "", "price": r.get("deal_amount"), "agent": r.get("agent") or "",
            "branch": r.get("branch")}


_FULL = ("id", "branch", "year", "src_sheet", "src_serial", "deal_date", "city", "street", "side", "agent",
         "client_name", "client_phone", "other_broker", "deal_amount", "commission_gross", "commission_net",
         "discount", "lead_source", "paid_amount", "deposited", "invoice_no", "receipt_no", "reported_date",
         "remax_approved", "collection_status", "notes", "lawyer_notes", "missing_since")


def view_full(r):
    d = {k: r.get(k) for k in _FULL}
    d["date"] = _dmy(r.get("deal_date") or "")
    return d


def scope_rows(rows, s, canon_key, coord_keys):
    if (s or {}).get("role") == "coordinator":
        keys = set(coord_keys or set()) | {canon_key(s.get("name", ""))}
    else:
        nm = (s or {}).get("name", "") or ""
        if nm.strip() in _GENERIC:
            return []
        keys = {canon_key(nm)}
    keys.discard("")
    return [r for r in rows if canon_key(r.get("agent", "")) in keys]


def _sort_desc(rows):
    return sorted(rows, key=lambda r: (r.get("deal_date") or "", r.get("id") or ""), reverse=True)


def _norm_q(t):
    return normalize_header(t).replace("קריית", "קרית").lower()


def comps_search(rows, q, cap=200):
    toks = [t for t in _norm_q(q).split() if t]
    if not toks:
        return {"results": [], "n_sale": 0, "avg_sale": None, "n_rent": 0, "avg_rent": None}
    hit = []
    for r in rows:
        hay = _norm_q(" ".join((r.get("street") or "", r.get("city") or "")))
        if all(t in hay for t in toks):
            hit.append(r)
    hit = _sort_desc(hit)
    out = {"results": [view_comps(r) for r in hit[:cap]]}
    for kind, key in (("מכירה", "sale"), ("השכרה", "rent")):
        ps = [float(r["deal_amount"]) for r in hit if _kind(r.get("side")) == kind and r.get("deal_amount")]
        out["n_" + key] = len([r for r in hit if _kind(r.get("side")) == kind])
        out["avg_" + key] = int(round(sum(ps) / len(ps))) if ps else None
    return out


def _agg(rows):
    return {"n": len(rows), "commission": int(round(sum(float(r.get("commission_net") or 0) for r in rows)))}


def stats(rows, year):
    cur = [r for r in rows if r.get("year") == year]
    prev = [r for r in rows if r.get("year") == year - 1]
    def by(field):
        g = {}
        for r in cur:
            g.setdefault(r.get(field) or "", []).append(r)
        return sorted(({field: k, **_agg(v)} for k, v in g.items()), key=lambda x: -x["commission"])
    months = {}
    for r in cur:
        m = (r.get("deal_date") or "")[5:7]
        if m:
            months.setdefault(m, []).append(r)
    return {"year": year, "total": _agg(cur), "prev": _agg(prev), "byBranch": by("branch"), "byAgent": by("agent"),
            "byMonth": [{"month": m, **_agg(months[m])} for m in sorted(months)]}


def _since(rows, since):
    return [r for r in rows if (r.get("year") or 0) >= int(since)]


def unpaid(rows, since):
    rs = [r for r in _since(rows, since) if not r.get("paid_amount")]
    return sorted(rs, key=lambda r: (r.get("deal_date") or "9999", r.get("id") or ""))


def unreported(rows, since):
    rs = [r for r in _since(rows, since) if not r.get("reported_date")]
    return sorted(rs, key=lambda r: (r.get("deal_date") or "9999", r.get("id") or ""))


def _rows(sb):
    if time.time() - _HIST_CACHE["ts"] < 120:
        return _HIST_CACHE["rows"]
    rows = sb.deal_history_all() if (sb and sb.enabled()) else []
    _HIST_CACHE.update(ts=time.time(), rows=rows)
    return rows
```

```python
# deals_history.py — בתוך register(app, G, page), אחרי ראוט הייבוא
    def _auth():
        s = G["_web_auth"]()
        if not s:
            return None, (jsonify({"ok": False, "auth": False}), 401)
        return s, None

    def _coord_keys(s):
        if s.get("role") != "coordinator":
            return set()
        keys, _p, _m = G["_scope_keys_phones"]("coordinator", s.get("name", ""), set(),
                                                 s.get("agents"), s.get("agent_names"))
        return keys

    @app.route("/v2/api/deals/history/mine", methods=["GET"])
    def v2_deals_history_mine():
        s, err = _auth()
        if err:
            return err
        rows = scope_rows(_rows(sb), s, G["_canon_key"], _coord_keys(s))
        years = sorted({r.get("year") for r in rows if r.get("year")}, reverse=True)
        y = request.args.get("year", "")
        if y.isdigit():
            rows = [r for r in rows if r.get("year") == int(y)]
        multi = s.get("role") == "coordinator"
        res = [dict(view_agent(r), agent=r.get("agent")) if multi else view_agent(r) for r in _sort_desc(rows)]
        tot = _agg(rows)
        return G["_etag_wrap"]({"ok": True, "results": res, "years": years, "n": tot["n"], "commission": tot["commission"]})

    @app.route("/v2/api/deals/history/comps", methods=["GET"])
    def v2_deals_history_comps():
        s, err = _auth()
        if err:
            return err
        return jsonify(dict(comps_search(_rows(sb), request.args.get("q", "")), ok=True))

    def _editor():
        s, err = _auth()
        if err:
            return None, err
        if not is_editor(s):
            return None, (jsonify({"ok": False, "reason": "forbidden"}), 403)
        return s, None

    @app.route("/v2/api/deals/history/stats", methods=["GET"])
    def v2_deals_history_stats():
        s, err = _editor()
        if err:
            return err
        y = request.args.get("year", "")
        year = int(y) if y.isdigit() else time.localtime().tm_year
        rows = _rows(sb)
        years = sorted({r.get("year") for r in rows if r.get("year")}, reverse=True)
        return G["_etag_wrap"](dict(stats(rows, year), ok=True, years=years))

    @app.route("/v2/api/deals/history/open", methods=["GET"])
    def v2_deals_history_open():
        s, err = _editor()
        if err:
            return err
        since = request.args.get("since", "")
        since = int(since) if since.isdigit() else time.localtime().tm_year - 1
        fn = unreported if request.args.get("kind") == "unreported" else unpaid
        res = [view_full(r) for r in fn(_rows(sb), since)]
        return G["_etag_wrap"]({"ok": True, "results": res, "since": since})

    @app.route("/v2/api/deals/history/search", methods=["GET"])
    def v2_deals_history_search():
        s, err = _editor()
        if err:
            return err
        toks = [t for t in _norm_q(request.args.get("q", "")).split() if t]
        if not toks:
            return jsonify({"ok": True, "results": []})
        hits = []
        for r in _rows(sb):
            hay = _norm_q(" ".join(str(r.get(k) or "") for k in
                                   ("client_name", "client_phone", "street", "city", "agent", "invoice_no", "receipt_no")))
            if all(t in hay for t in toks):
                hits.append(r)
        return jsonify({"ok": True, "results": [view_full(r) for r in _sort_desc(hits)[:200]]})
```

בגרסה הזו `since` של "לא שולם" ו"לא דווח" הוא השנה הקודמת. זו שאלה פתוחה לאייל, ראה למטה, ואולי יתוקן לפי התשובה.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/deals_history/test_views.py && python3 tests/deals_history/test_import_route.py`
Expected: `OK 22 checks` ו-`OK 8 checks`

- [ ] **Step 5: Commit**

```bash
git pull --ff-only
git add deals_history.py tests/deals_history/test_views.py
git commit -m "היסטוריית עסקאות: תצוגות לפי הרשאה (שלי/השוואה/מלא), סטטיסטיקה, לא שולם/לא דווח, חיפוש — ראוטי קריאה

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: סקריפט הייבוא המקומי (ריצה יבשה ואז שמירה)

**Files:**
- Create: `tools/import_deal_history.py`
- Test: `tests/deals_history/test_import_tool.py`

**Interfaces:**
- Consumes:
  - `deals_history.find_header_row`, `normalize_row`, `normalize_header`
  - `tools/deals_sources.json`: `{"branch|year": {"file", "sheets"}}`
  - `tools/deals_agent_map.json`
  - `tools.deals_survey._open`, `ROOT`, `PW_GROUP`
- Produces:
  - `rows_from_workbook(wb, branch, year, sheets) -> (ok_rows, report)`
  - CLI:
    - `python3 tools/import_deal_history.py`: ריצה יבשה, דוח בלבד.
    - `python3 tools/import_deal_history.py --save`: שולח ל-`APP_URL/v2/api/deals/history/import` במנות של 500. מפתח הייבוא ב-`getpass`.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_import_tool.py
import sys, os, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import openpyxl
from tools.import_deal_history import rows_from_workbook
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
wb = openpyxl.Workbook()
ws = wb.active; ws.title = "עסקאות25"
ws.append(["דוח"]); ws.append(['מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ", "התחשבנות סוכן"])
ws.append([1, dt.datetime(2025, 1, 2), "קרית ים", "הרצל 1", "מוכר", "משה", 1000000, 10000, 5000])
ws.append([2, dt.datetime(2025, 1, 3), "קרית ים", "הרצל 1", "קונה", "משה", 1000000, 9000, None])
ws.append([None, None, None, None, None, 'סה"כ', None, 19000, None])
ws.append([3, None, None, None, None, "דנה", None, None, None])
lawyer = wb.create_sheet('דוח לעו"ד')
lawyer.append(["תאריך", "כתובת", "מתווך", "סכום עסקה", "התחשבנות", "עו\"ד"]); lawyer.append([dt.datetime(2025, 1, 2), "הרצל 1", "משה", 1000000, 1, "x"])
ok, rep = rows_from_workbook(wb, "kiryat_yam", 2025, ["עסקאות25"])
ck(len(ok) == 2 and rep["ok"] == 2 and rep["skip"] >= 1 and rep["broken"] == 1, rep)
ck(ok[0]["src_key"] == "kiryat_yam|2025|עסקאות25|1" and ok[0]["raw"].get("התחשבנות סוכן") == "5000", ok[0])
ck(rep["agents"] == {"משה": 2}, rep["agents"])
ck(all(r["src_sheet"] == "עסקאות25" for r in ok), "only approved sheet (no דוח לעו\"ד)")
ok2, rep2 = rows_from_workbook(wb, "kiryat_yam", 2025, ["אין כזה"])
ck(ok2 == [] and rep2["missing_sheets"] == ["אין כזה"], rep2)
print("OK", n, "checks")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/deals_history/test_import_tool.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.import_deal_history'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/import_deal_history.py
"""ייבוא היסטוריית עסקאות (2015–2025) — רץ על המחשב של אייל.
ריצה רגילה = יבשה (דוח בלבד, בלי שמירה). --save = שליחה לשרת אחרי אישור.
סיסמאות ומפתח הייבוא: getpass בלבד. הדוח לא כולל פרטי לקוחות."""
import os, sys, json, getpass, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import deals_history as D

APP_URL = os.environ.get("APP_URL", "https://remax-bot.onrender.com")


def rows_from_workbook(wb, branch, year, sheets):
    rep = {"ok": 0, "skip": 0, "broken": 0, "agents": collections.Counter(), "commission": 0,
           "missing_sheets": [], "broken_rows": []}
    out = []
    names = [ws.title for ws in wb.worksheets]
    for sh in sheets:
        if sh not in names:
            rep["missing_sheets"].append(sh)
            continue
        rows = list(wb[sh].iter_rows(values_only=True))
        hi, fields = D.find_header_row(rows)
        if hi is None:
            rep["missing_sheets"].append(sh)
            continue
        headers = [D.normalize_header(c) for c in rows[hi]]
        for i, cells in enumerate(rows[hi + 1:], start=hi + 2):
            st, row = D.normalize_row(cells, fields, {"branch": branch, "year": year, "sheet": sh,
                                                      "row_idx": i, "headers": headers})
            rep[st] += 1
            if st == "ok":
                out.append(row)
                rep["agents"][row["agent"]] += 1
                rep["commission"] += float(row.get("commission_net") or 0)
            elif st == "broken":
                rep["broken_rows"].append("%s שורה %d" % (sh, i))
    rep["agents"] = dict(rep["agents"])
    return out, rep


def main():
    from tools.deals_survey import _open, ROOT, PW_GROUP
    here = os.path.dirname(__file__)
    sources = json.load(open(os.path.join(here, "deals_sources.json"), encoding="utf-8"))
    amap = json.load(open(os.path.join(here, "deals_agent_map.json"), encoding="utf-8"))
    save = "--save" in sys.argv
    pws = {g: getpass.getpass("סיסמת %s: " % g) for g in ("ביאליק", "מוצקין + קרית ים")}
    all_rows, unmapped = [], collections.Counter()
    for key in sorted(sources):
        br, yr = key.split("|")
        src = sources[key]
        try:
            wb = _open(os.path.join(ROOT, src["file"]), pws[PW_GROUP[br]])
        except Exception as e:
            print("!! %s: לא נפתח (%s)" % (key, type(e).__name__)); continue
        rows, rep = rows_from_workbook(wb, br, int(yr), src.get("sheets") or [])
        for r in rows:
            r["src_path"] = src["file"]
            if not amap.get("%s|%s" % (br, r["agent"])):
                unmapped["%s|%s" % (br, r["agent"])] += 1
        print("%-16s שורות=%4d  דולגו=%4d  שבורות=%3d  עמלה=%10s  %s" % (
            key, rep["ok"], rep["skip"], rep["broken"], "{:,.0f}".format(rep["commission"]),
            ("גיליונות חסרים: " + ", ".join(rep["missing_sheets"])) if rep["missing_sheets"] else ""))
        all_rows += rows
    print("\nסה\"כ שורות: %d" % len(all_rows))
    if unmapped:
        print("שמות סוכנים בלי מיפוי ב-deals_agent_map.json (יישמרו כמו שהם):")
        for k, c in unmapped.most_common():
            print("   %s : %d" % (k, c))
    if not save:
        print("\nריצה יבשה — שום דבר לא נשמר. לשמירה: python3 tools/import_deal_history.py --save")
        return
    import requests
    ikey = getpass.getpass("מפתח הייבוא (DEALS_IMPORT_KEY): ")
    total = 0
    for i in range(0, len(all_rows), 500):
        r = requests.post(APP_URL + "/v2/api/deals/history/import", json={"rows": all_rows[i:i + 500], "amap": amap},
                          headers={"X-Import-Key": ikey}, timeout=120)
        j = r.json() if r.ok else {"ok": False, "reason": r.status_code}
        if not j.get("ok"):
            print("!! נכשל במנה %d: %s" % (i // 500 + 1, j)); return
        total += j["saved"]
    print("נשמרו %d שורות." % total)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/deals_history/test_import_tool.py`
Expected: `OK 5 checks`

- [ ] **Step 5: Commit**

```bash
git pull --ff-only
git add tools/import_deal_history.py tests/deals_history/test_import_tool.py
git commit -m "היסטוריית עסקאות: סקריפט ייבוא מקומי — ריצה יבשה עם דוח לשנה/משרד, ואז --save

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: דף `/v2/history` וקישורים אליו

**Files:**
- Modify: `deals_history.py` (`V2_HISTORY_HTML` + ראוט `/v2/history`)
- Modify: `effie_v2.py`: קישור "היסטוריית עסקאות" בתפריט הצד של הבית (ליד הקישור ל-`/v2/deals`, בסביבת שורה 955), וכפתור בראש `V2_DEALS_HTML`
- Test: `tests/deals_history/test_page.js`

**Interfaces:**
- Consumes: הראוטים מ-Task 5, ו-`page(html)` מ-effie_v2, שמזריק את `V2_BOOST` (whoami ממטמון, `swrU`/`swrJ`/`swrPut`).
- Produces:
  - `GET /v2/history`.
  - טאבים לפי תפקיד:
    - סוכן/מתאמת: "העסקאות שלי" · "מחירי השוואה".
    - עורך: "דוחות" · "לא שולם" · "לא דווח" · "חיפוש" · "מחירי השוואה".
  - פונקציות JS הניתנות לבדיקה: `fmtP`, `agentCard(x)`, `compCard(x)`, `openCard(x)`, `statsHtml(j)`.

- [ ] **Step 1: Write the failing test**

```javascript
// tests/deals_history/test_page.js
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'deals_history.py'), 'utf8');
const a = src.indexOf('<script>', src.indexOf('V2_HISTORY_HTML')) + 8, b = src.indexOf('</script>', a);
const js = src.slice(a, b);
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };
global.document = {getElementById: () => null, querySelectorAll: () => []};
global.localStorage = {getItem: () => null, setItem: () => {}};
global.fetch = () => new Promise(() => {}); global.location = {href: ''};
eval(js.replace(/^\(function\(\)\{[\s\S]*$/m, '') + ';global.T={fmtP,agentCard,compCard,openCard,statsHtml,esc};');
ck(T.fmtP(1850000) === '₪1,850,000' && T.fmtP(null) === '', 'fmtP');
const ac = T.agentCard({date: '02/03/2025', address: 'הגפן 4, קרית מוצקין', side: 'מוכר', client: 'דנה', price: 1800000,
  commission_net: 18000, paid: 18000, reported: '04/2025'});
ck(ac.includes('דנה') && ac.includes('₪18,000') && ac.includes('דווח 04/2025') && ac.includes('שולם ₪18,000'), ac);
ck(T.agentCard({date: '', address: 'x', side: '', client: '', price: null, commission_net: null, paid: null, reported: ''}).includes('טרם שולם'), 'unpaid label');
const cc = T.compCard({date: '01/02/2024', address: 'הגפן 4, קרית מוצקין', kind: 'מכירה', side: 'קונה', price: 1500000, agent: 'משה כהן'});
ck(cc.includes('₪1,500,000') && cc.includes('משה כהן') && !/עמלה|שולם/.test(cc), cc);
ck(T.esc('<b>') === '&lt;b&gt;', 'esc');
const oc = T.openCard({date: '10/05/2025', street: 'הגפן 9', city: 'קרית ביאליק', side: 'שוכר', agent: 'דנה לוי', client_name: 'יוסי',
  client_phone: '0529999999', commission_net: 5000, paid_amount: null, reported_date: null, collection_status: 'טרם שולם', invoice_no: '', receipt_no: ''});
ck(oc.includes('0529999999') && oc.includes('טרם שולם') && !oc.includes('התחשבנות'), oc);
const sh = T.statsHtml({year: 2025, total: {n: 2, commission: 23000}, prev: {n: 1, commission: 15000},
  byBranch: [{branch: 'motzkin', n: 1, commission: 18000}], byAgent: [{agent: 'משה כהן', n: 1, commission: 18000}], byMonth: [{month: '03', n: 1, commission: 18000}], years: [2025, 2024]});
ck(sh.includes('₪23,000') && sh.includes('מוצקין') && sh.includes('משה כהן') && sh.includes('2024'), sh);
console.log('OK', n, 'checks');
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node tests/deals_history/test_page.js`
Expected: FAIL. `V2_HISTORY_HTML` עוד לא קיים, ולכן `a` מצביע על מקום לא נכון ו-eval נכשל עם SyntaxError או ReferenceError.

- [ ] **Step 3: Write minimal implementation**

```python
# deals_history.py — הוספה (קבוע HTML + ראוט בתוך register)
V2_HISTORY_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>היסטוריית עסקאות</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{font-family:'Heebo',sans-serif;background:#F2EFE7;color:#1E3A5F;min-height:100vh}
  header{display:flex;align-items:center;gap:10px;padding:calc(env(safe-area-inset-top,0px) + 10px) 16px 6px}
  header .bk{width:44px;height:44px;border-radius:14px;background:#fff;border:1px solid #E9E4D8;display:flex;align-items:center;justify-content:center;cursor:pointer}
  header h1{font-size:19px;font-weight:800;flex:1}
  main{max-width:640px;margin:0 auto;padding:4px 16px 40px;display:flex;flex-direction:column;gap:12px}
  .segs{display:flex;background:#EBE8DD;border-radius:13px;padding:4px;gap:4px;overflow-x:auto;scrollbar-width:none}
  .segs::-webkit-scrollbar{display:none}
  .segs .sg{flex:1 0 auto;text-align:center;padding:9px 12px;min-height:40px;font-size:12.5px;font-weight:700;color:#5B6472;border-radius:10px;cursor:pointer;white-space:nowrap}
  .segs .sg.on{color:#fff;background:#2E6BD6;box-shadow:0 2px 8px rgba(46,107,214,.3)}
  .card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:14px 16px}
  .row1{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
  .ad{font-weight:800;font-size:15px}.sb{font-size:12.5px;color:#6B7280;margin-top:2px}
  .pr{font-weight:800;font-size:15px;white-space:nowrap}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .chip{font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;background:#F2EFE7;color:#5B6472}
  .chip.ok{background:#EAF5EE;color:#157A43}.chip.wait{background:#F6EEDB;color:#7A5E1C}
  .sum{display:flex;gap:10px}.sum .card{flex:1;text-align:center}.sum b{display:block;font-size:20px;font-weight:800}
  .sum span{font-size:12px;color:#6B7280}
  input.q{width:100%;font-size:16px;font-family:inherit;padding:12px 14px;border:1.5px solid #DCD6C8;border-radius:14px;background:#fff;color:#1E3A5F;outline:none}
  select.yr{font-size:16px;font-family:inherit;padding:10px 12px;border:1.5px solid #DCD6C8;border-radius:13px;background:#fff;color:#1E3A5F;min-height:44px}
  table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:7px 4px;border-bottom:1px solid #F0EDE3;text-align:right}
  th{color:#6B7280;font-weight:700}
  .empty{text-align:center;padding:36px 16px}.empty .c{width:62px;height:62px;border-radius:50%;background:#F6EEDB;margin:0 auto 12px;display:flex;align-items:center;justify-content:center}
  .empty .t{font-weight:800;font-size:17px}.empty .s{color:#6B7280;margin-top:6px;font-size:13.5px}
</style></head><body>
<header>
  <div class="bk" onclick="history.length > 1 ? history.back() : location.href='/v2/home'" aria-label="חזרה">
    <svg width="16" height="16" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5" fill="none" stroke="#1E3A5F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
  <h1>היסטוריית עסקאות</h1>
</header>
<main>
  <div class="segs" id="tabs"></div>
  <div id="tools"></div>
  <div id="list"><div class="sb" style="text-align:center;padding:20px 0">טוען…</div></div>
</main>
<div id="toast"></div>
<script>
var TOK = '', ED = false, TAB = '', YEAR = '', Q = '';
var BR = {bialik: 'ביאליק', motzkin: 'מוצקין', kiryat_yam: 'קרית ים'};
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function fmtP(p){ if (p == null || p === '') return ''; var n = Math.round(Number(p)); if (isNaN(n)) return ''; return '₪' + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function emptyHtml(t, s){ return '<div class="empty"><div class="c"><svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 11l8-7 8 7v9H4z" fill="none" stroke="#C29435" stroke-width="2" stroke-linejoin="round"/></svg></div><div class="t">' + esc(t) + '</div><div class="s">' + esc(s) + '</div></div>'; }
function agentCard(x){
  return '<div class="card"><div class="row1"><div><div class="ad">' + esc(x.address || '—') + '</div>' +
    '<div class="sb">' + esc([x.date, x.side, x.client].filter(Boolean).join(' · ')) + (x.agent ? ' · ' + esc(x.agent) : '') + '</div></div>' +
    '<div class="pr">' + esc(fmtP(x.price)) + '</div></div>' +
    '<div class="chips"><span class="chip">עמלה ' + esc(fmtP(x.commission_net) || '—') + '</span>' +
    (x.paid ? '<span class="chip ok">שולם ' + esc(fmtP(x.paid)) + '</span>' : '<span class="chip wait">טרם שולם</span>') +
    (x.reported ? '<span class="chip ok">דווח ' + esc(x.reported) + '</span>' : '<span class="chip wait">לא דווח</span>') + '</div></div>';
}
function compCard(x){
  return '<div class="card"><div class="row1"><div><div class="ad">' + esc(x.address || '—') + '</div>' +
    '<div class="sb">' + esc([x.date, x.kind, x.agent].filter(Boolean).join(' · ')) + '</div></div>' +
    '<div class="pr">' + esc(fmtP(x.price)) + '</div></div></div>';
}
function openCard(x){
  var addr = [x.street, x.city].filter(Boolean).join(', ');
  return '<div class="card"><div class="row1"><div><div class="ad">' + esc(addr || '—') + '</div>' +
    '<div class="sb">' + esc([x.date, x.side, x.agent, BR[x.branch]].filter(Boolean).join(' · ')) + '</div>' +
    '<div class="sb">' + esc([x.client_name, x.client_phone].filter(Boolean).join(' · ')) + '</div></div>' +
    '<div class="pr">' + esc(fmtP(x.commission_net)) + '</div></div>' +
    '<div class="chips">' + (x.paid_amount ? '<span class="chip ok">שולם ' + esc(fmtP(x.paid_amount)) + '</span>' : '<span class="chip wait">טרם שולם</span>') +
    (x.reported_date ? '<span class="chip ok">דווח ' + esc(x.reported_date.slice(5, 7) + '/' + x.reported_date.slice(0, 4)) + '</span>' : '<span class="chip wait">לא דווח</span>') +
    (x.collection_status ? '<span class="chip">' + esc(x.collection_status) + '</span>' : '') +
    (x.invoice_no ? '<span class="chip">חשבונית ' + esc(x.invoice_no) + '</span>' : '') +
    (x.receipt_no ? '<span class="chip">קבלה ' + esc(x.receipt_no) + '</span>' : '') + '</div></div>';
}
function statsHtml(j){
  var t = j.total || {}, p = j.prev || {};
  var tbl = function(title, rows, key, lbl){
    if (!rows || !rows.length) return '';
    return '<div class="card"><div class="ad" style="margin-bottom:6px">' + title + '</div><table><tr><th>' + lbl + '</th><th>עסקאות</th><th>עמלה</th></tr>' +
      rows.map(function(r){ return '<tr><td>' + esc(key(r)) + '</td><td>' + r.n + '</td><td>' + esc(fmtP(r.commission)) + '</td></tr>'; }).join('') + '</table></div>';
  };
  return '<div class="sum"><div class="card"><b>' + (t.n || 0) + '</b><span>עסקאות ' + j.year + '</span></div>' +
    '<div class="card"><b>' + esc(fmtP(t.commission || 0)) + '</b><span>עמלה לפני מע"מ</span></div></div>' +
    '<div class="sb" style="text-align:center">' + (j.year - 1) + ': ' + (p.n || 0) + ' עסקאות · ' + esc(fmtP(p.commission || 0)) + '</div>' +
    tbl('לפי משרד', j.byBranch, function(r){ return BR[r.branch] || r.branch; }, 'משרד') +
    tbl('לפי סוכן', j.byAgent, function(r){ return r.agent; }, 'סוכן') +
    tbl('לפי חודש', j.byMonth, function(r){ return r.month; }, 'חודש');
}
function GET(u){ return fetch(u, {headers: {'X-Auth-Token': TOK}}).then(function(r){ return r.json(); }); }
function setTab(t){ TAB = t; try{ localStorage.setItem('v2st:hist', t); }catch(e){} draw(); }
function tabsFor(){
  return ED ? [['stats', 'דוחות'], ['unpaid', 'לא שולם'], ['unrep', 'לא דווח'], ['search', 'חיפוש'], ['comps', 'מחירי השוואה']]
            : [['mine', 'העסקאות שלי'], ['comps', 'מחירי השוואה']];
}
function draw(){
  var tb = tabsFor();
  if (!tb.some(function(x){ return x[0] === TAB; })) TAB = tb[0][0];
  document.getElementById('tabs').innerHTML = tb.map(function(x){
    return '<div class="sg' + (x[0] === TAB ? ' on' : '') + '" onclick="setTab(\'' + x[0] + '\')">' + x[1] + '</div>'; }).join('');
  var tools = document.getElementById('tools'), list = document.getElementById('list');
  list.innerHTML = '<div class="sb" style="text-align:center;padding:20px 0">טוען…</div>';
  if (TAB === 'comps' || TAB === 'search'){
    tools.innerHTML = '<input class="q" id="q" type="search" enterkeyhint="search" placeholder="' +
      (TAB === 'comps' ? 'רחוב, שכונה או עיר — למשל הגפן מוצקין' : 'שם לקוח, טלפון, כתובת, סוכן או מספר חשבונית') + '" value="' + esc(Q) + '">';
    var q = document.getElementById('q');
    q.onkeydown = function(e){ if (e.key === 'Enter'){ Q = q.value.trim(); runQ(); } };
    q.onchange = function(){ Q = q.value.trim(); runQ(); };
    runQ(); return;
  }
  tools.innerHTML = '';
  if (TAB === 'mine'){
    GET('/v2/api/deals/history/mine' + (YEAR ? '?year=' + YEAR : '')).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'נסה שוב בעוד רגע'); return; }
      tools.innerHTML = '<div style="display:flex;gap:8px;align-items:center"><select class="yr" onchange="YEAR=this.value;draw()"><option value="">כל השנים</option>' +
        (j.years || []).map(function(y){ return '<option' + (String(y) === String(YEAR) ? ' selected' : '') + '>' + y + '</option>'; }).join('') +
        '</select><div class="sb">' + j.n + ' עסקאות · עמלה ' + esc(fmtP(j.commission)) + '</div></div>';
      list.innerHTML = j.results.length ? j.results.map(agentCard).join('') : emptyHtml('עוד אין עסקאות כאן', 'עסקאות שסגרת יופיעו כאן עם הגבייה והדיווח');
    }).catch(function(){ list.innerHTML = emptyHtml('לא ניתן לטעון', 'בדוק חיבור ונסה שוב'); });
  } else if (TAB === 'stats'){
    GET('/v2/api/deals/history/stats' + (YEAR ? '?year=' + YEAR : '')).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'הדוחות זמינים למנהלים ולהנהלת חשבונות'); return; }
      tools.innerHTML = '<select class="yr" onchange="YEAR=this.value;draw()">' + (j.years || []).map(function(y){
        return '<option' + (String(y) === String(j.year) ? ' selected' : '') + '>' + y + '</option>'; }).join('') + '</select>';
      list.innerHTML = statsHtml(j);
    });
  } else {
    var kind = TAB === 'unpaid' ? 'unpaid' : 'unreported';
    GET('/v2/api/deals/history/open?kind=' + kind).then(function(j){
      if (!j || !j.ok){ list.innerHTML = emptyHtml('אין הרשאה', 'זמין למנהלים ולהנהלת חשבונות'); return; }
      tools.innerHTML = '<div class="sb">' + j.results.length + ' צדדים מ-' + j.since + ' והלאה, מהישן לחדש</div>';
      list.innerHTML = j.results.length ? j.results.map(openCard).join('') :
        emptyHtml(kind === 'unpaid' ? 'הכל שולם' : 'הכל דווח', 'אין צדדים פתוחים מ-' + j.since + ' והלאה');
    });
  }
}
function runQ(){
  var list = document.getElementById('list');
  if (!Q){ list.innerHTML = emptyHtml(TAB === 'comps' ? 'מחירי השוואה' : 'חיפוש עסקה', TAB === 'comps' ? 'הקלד רחוב או שכונה וראה מה נמכר שם ובכמה' : 'הקלד שם, טלפון או כתובת'); return; }
  var u = TAB === 'comps' ? '/v2/api/deals/history/comps?q=' : '/v2/api/deals/history/search?q=';
  GET(u + encodeURIComponent(Q)).then(function(j){
    if (!j || !j.ok){ list.innerHTML = emptyHtml('לא ניתן לחפש', 'נסה שוב'); return; }
    var head = TAB === 'comps' ? '<div class="sum"><div class="card"><b>' + j.n_sale + '</b><span>מכירות · ממוצע ' + esc(fmtP(j.avg_sale) || '—') + '</span></div>' +
      '<div class="card"><b>' + j.n_rent + '</b><span>השכרות · ממוצע ' + esc(fmtP(j.avg_rent) || '—') + '</span></div></div>' : '';
    list.innerHTML = j.results.length ? head + j.results.map(TAB === 'comps' ? compCard : openCard).join('') :
      emptyHtml('לא נמצא', 'אין עסקאות עבור "' + Q + '" — נסה מילה אחרת');
  });
}
(function(){
  try{ TOK = localStorage.getItem('fbTok') || ''; TAB = localStorage.getItem('v2st:hist') || ''; }catch(e){}
  if (!TOK){ location.href = '/v2'; return; }
  GET('/api/auth/whoami').then(function(j){
    if (!j || !j.ok){ location.replace('/v2'); return; }
    ED = ['manager', 'developer', 'accountant'].indexOf(j.drole) >= 0;
    draw();
  }).catch(function(){ location.replace('/v2'); });
})();
</script></body></html>'''
```

```python
# deals_history.py — בתוך register(app, G, page)
    @app.route("/v2/history", methods=["GET"])
    def v2_history_page():
        return page(V2_HISTORY_HTML)
```

הדרישה: `whoami` מחזיר `drole`. לבדוק ב-`app.py` (`/api/auth/whoami`). אם השדה לא מוחזר, להוסיף `"drole": s.get("drole", "")` לתשובה.

```python
# effie_v2.py — בתפריט הצד של הבית, מיד אחרי הקישור הקיים ל-/v2/deals (בסביבת שורה 955), אותו סגנון:
    <a href="/v2/history" style="display:flex;align-items:center;gap:11px;padding:12px 4px;text-decoration:none;color:#1E3A5F;font-size:15px;font-weight:700;min-height:44px">
      <svg width="20" height="20" viewBox="0 0 24 24"><path d="M4 5h16M4 12h16M4 19h10" stroke="#1E3A5F" stroke-width="2" stroke-linecap="round"/></svg>היסטוריית עסקאות</a>
```

את הסגנון המדויק מעתיקים מהקישור הקיים ל-`/v2/deals` בשורה 955, כדי שהשורות ייראו זהות. בראש `V2_DEALS_HTML`, ליד הכותרת, מוסיפים כפתור משני (לבן עם מסגרת, 44px) "היסטוריה" שמוביל ל-`/v2/history`.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
node tests/deals_history/test_page.js
python3 - <<'EOF'
import re, subprocess, ast, collections
src = open('deals_history.py').read()
a = src.index('<script>', src.index('V2_HISTORY_HTML')) + 8; b = src.index('</script>', a)
open('/tmp/_hist.js', 'w').write(src[a:b])
print(subprocess.run(['node', '--check', '/tmp/_hist.js'], capture_output=True, text=True).returncode == 0)
for f in ('deals_history.py', 'effie_v2.py', 'app.py', 'supabase_db.py', 'tools/deals_survey.py', 'tools/import_deal_history.py'):
    t = ast.parse(open(f).read())
    c = collections.Counter(n.name for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    print(f, [k for k, v in c.items() if v > 1])
EOF
```
Expected: `OK 7 checks`, `True`, ואחרי כל קובץ רשימה ריקה `[]`.

Run (השרת עולה, הדף נרשם):
```bash
CLAUDE_API_KEY=x WARMUP_ON_BOOT=0 DAILY_REPORT=0 python3 -c "import app; c=app.app.test_client(); r=c.get('/v2/history'); print(r.status_code, 'היסטוריית עסקאות' in r.get_data(as_text=True))"
```
Expected: `200 True`

- [ ] **Step 5: Commit**

```bash
git pull --ff-only
git add deals_history.py effie_v2.py app.py tests/deals_history/test_page.js
git commit -m "היסטוריית עסקאות: דף /v2/history — העסקאות שלי, מחירי השוואה, דוחות/לא שולם/לא דווח/חיפוש לעורכים; קישורים מהבית ומתהליכים

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: הרצה מלאה, יומן ומסירה לאייל

**Files:**
- Modify: `/Users/eyal/Documents/remax-family/CLAUDE.md` (יומן החלטות)

- [ ] **Step 1: כל הבדיקות**

Run:
```bash
for t in tests/deals_history/test_*.py; do python3 $t || exit 1; done; node tests/deals_history/test_page.js
```
Expected: כל קובץ מסתיים ב-`OK N checks`.

- [ ] **Step 2: צילום מובייל של הדף עם נתוני דוגמה**

מריצים את `effie-v2` מ-`.claude/launch.json` דרך preview_start, וצריך לבדוק שתי נקודות:
1. בלי כניסה, הדף מפנה ל-`/v2`.
2. הצגה עם נתוני דוגמה: מזריקים ב-`javascript_tool` את `statsHtml`/`agentCard` לתוך `#list` ומצלמים ב-375px. אין בטעינה הזו כניסה אמיתית לשרת החי.

- [ ] **Step 3: רישום ביומן ההחלטות וקומיט ב-remax-family**

```bash
cd /Users/eyal/Documents/remax-family && git add CLAUDE.md && git commit -m "יומן: היסטוריית עסקאות — שלב 1 נבנה

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: הצעדים של אייל (למסירה)**

1. SQL Editor: מריצים את `supabase/migrations/20261012_deal_history.sql`.
2. Render ← Environment: מוסיפים `DEALS_IMPORT_KEY` עם ערך אקראי ארוך. אפשר ליצור אותו בטרמינל עם הפקודה `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`.
3. push ו-deploy.
4. בטרמינל: `python3 tools/import_deal_history.py`, ריצה יבשה. שולחים לי את הדוח, שבו יש רק מספרים ושמות סוכנים.
5. אחרי אישור: `python3 tools/import_deal_history.py --save`. התוכנה מבקשת את מפתח הייבוא.
6. פותחים את `/v2/history`. בודקים כסוכן (כניסה כסוכן מהניהול), ובודקים כמנהל.
