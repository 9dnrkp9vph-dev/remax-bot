# היסטוריית עסקאות — שלב 2א: קריאת קבצי 2026 מ-Dropbox — תוכנית מימוש

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** השרת יקרא כל 5 דקות את קבצי "מעקב עסקאות 2026" של שלושת המשרדים מ-Dropbox ויעדכן את `deal_history`. כך:
- עסקה שנוספה או שונתה באקסל מופיעה באפי.
- הרשימות "לא שולם" ו"לא דווח" מתמלאות.
- שורה שנעלמה מהאקסל מסומנת "לבדיקה".
- אפי **לא כותב** לקבצים בשלב הזה.

**Architecture:**
- **`dropbox_api.py` (מודול חדש):** לקוח Dropbox מינימלי. רענון טוקן, רשימת תיקייה והורדה. ה-`requests` מוזרק כדי שיהיה אפשר לבדוק בלי רשת.
- **`deals_history.py`:**
  - פענוח החוברת עובר מהכלי המקומי למודול, כדי שהשרת והכלי ישתמשו בקוד אחד. כולל עצירה אחרי רצף שורות ריקות, כי קבצים עם מיליון שורות ריקות לקחו דקות.
  - פונקציה טהורה `sync_plan` שמשווה את הקיים בטבלה לחדש מהקובץ.
  - thread רקע שמתחיל בבקשה הראשונה (הלקח מ-15/09), ראוט מצב, וטאב "לבדיקה".
- **`tools/dropbox_token.py` (מקומי):** מפיק לאייל את ה-refresh token ומעתיק אותו ללוח, בלי להציג אותו.

**Tech Stack:** Python 3.9, Flask, requests, openpyxl 3.1.5, msoffcrypto-tool 5.4.2 (קיימים), Dropbox HTTP API v2.

**Spec:** `docs/superpowers/specs/2026-10-12-deals-history-design.md` (סעיף 5), יחד עם החלטות אייל מ-12/10.

## Global Constraints
- **החלטות אייל 12/10:**
  - **קריאה בלבד.** אפי לא כותב לקבצים בשלב הזה.
  - **מאיזה קובץ קוראים:** בכל תיקיית 2026, קובץ המעקב שנשמר אחרון. עותק כפול נחשב, וכן גם קובץ "גיבוי…" וקבצי `~$`.
  - **פירוט עמלה, גבייה ודיווח:** רק בשורות 2026.
- **סיסמאות ומפתחות:** רק ב-env של Render:
  - `DEALS_PW_BIALIK`, `DEALS_PW_MOTZKIN_YAM`
  - `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`

  אף אחד מהם לא נכתב ללוג, לתשובת API או לריפו.
- **הפעלה:** `DEALS_SYNC=1` מפעיל. ריק או `0` = כבוי. שנת הקבצים: `DEALS_SYNC_YEAR`, וברירת המחדל היא השנה הנוכחית.
- **מחיקה:** לא מוחקים שורות מהטבלה לעולם. שורה שנעלמה מקבלת `missing_since`, ושורה שחזרה מאופסת.
- **הרשאות:** המסכים הקיימים לא משתנים. "לבדיקה" והמצב: רק עורכים, כלומר `drole` ב-`manager`/`developer`/`accountant`.
- **עיצוב:** פלטת אפי, RTL, 44px לכל נקודת מגע, שדות ב-16px, בלי אימוג'ים, מצבי ריק מעוצבים.
- **Git ובדיקות:** commit מקומי בלבד, אחרי `git pull --ff-only`. בסוף כל commit:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

  בדיקות עם `python3 <file>` ו-node. בנוסף `ast` ובדיקת כפילויות שמות.

## Review Focus
1. **קובץ שנעול או פתוח ב-Excel, הורדה שנכשלה או סיסמה שגויה:** השרת לא מסמן את כל השורות כחסרות. כשל = לא נוגעים בטבלה, ורק כותבים שגיאה למצב. נבדק ב-Task 3.
2. **הקובץ הפעיל התחלף** (עותק כפול חדש שנשמר אחרון) והגיליון בו חלקי: אחרי מעבר קובץ מסמנים שורות כחסרות רק אם הקובץ החדש מכיל לפחות 60% מהשורות הקיימות. אחרת זו התראה בלבד. נבדק ב-Task 3.
3. **בלי שינוי בקובץ (אותו `rev`):** אין הורדה ואין כתיבה לטבלה. נבדק ב-Task 4.
4. **שם סוכן חדש שלא במיפוי:** השורה נשמרת עם השם כמו שהוא ומופיעה ב"לבדיקה", כדי שאייל ימפה. נבדק ב-Task 4.
5. **ה-thread נפל או ש-env חסר:** המצב מראה שגיאה ברורה, ולא "עובד". נבדק ב-Task 4.

## File Structure
- `dropbox_api.py` (חדש): `access_token()`, `list_folder(path)`, `download(path)`. בלי תלות ב-Flask.
- `deals_history.py` (שינוי):
  - `open_workbook(data, pw)`, `pick_main_sheet(wb)`, `rows_from_workbook(...)` (עבר מ-tools, עם עצירה בריצת ריקים).
  - `pick_latest(entries)`, `row_hash(row)`, `sync_plan(existing, incoming, switched)`, `load_agent_map()`.
  - `sync_branch(...)` ולולאה. ראוטים `GET /v2/api/deals/history/sync` ו-`/review`. טאב "לבדיקה".
- `supabase_db.py` (שינוי): `deal_history_set_missing(keys, ts_or_none)`, ו-`_DH_COLS` מקבל את `src_hash`, `src_path`, `agent_raw`.
- `tools/import_deal_history.py` (שינוי): מייבא את `rows_from_workbook` מ-`deals_history`.
- `tools/dropbox_token.py` (חדש).
- `tests/deals_history/`: `test_workbook.py`, `test_dropbox.py`, `test_sync_plan.py`, `test_sync_loop.py`, ועדכון `test_page.js`.

---

### Task 1: פענוח חוברת משותף + עצירה בשורות ריקות

**Files:** Modify `deals_history.py`, `tools/import_deal_history.py`. Test `tests/deals_history/test_workbook.py`.

**Interfaces — Produces:**
- `open_workbook(data: bytes, pw: str) -> openpyxl.Workbook`: מפענח אם הקובץ מוצפן, read_only, data_only.
- `pick_main_sheet(wb) -> str | None`: הגיליון הראשון עם 6 כותרות מוכרות או יותר שכולל "סוכן".
- `rows_from_workbook(wb, branch, year, sheets, default_agent="", stop_after_empty=300) -> (rows, rep)`: אותו חוזה כמו היום, ונוסף לו `rep["stopped_at"]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_workbook.py
import sys, os, io, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import openpyxl, msoffcrypto
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "תרומות 1.26"; ws.append(["תרומה", "סכום"])
m = wb.create_sheet("עסקאות26")
m.append(["חודש", 'מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ"])
m.append(["ינואר", 1, dt.datetime(2026, 1, 5), "קרית ים", "הרצל 1", "מוכר", "קובי", 900000, 9000])
for _ in range(400): m.append([None] * 9)
m.append(["דצמבר", 99, dt.datetime(2026, 12, 1), "קרית ים", "רחוק 1", "מוכר", "קובי", 1, 1])  # אחרי 400 ריקות — לא נקרא
buf = io.BytesIO(); wb.save(buf); raw = buf.getvalue()
w2 = D.open_workbook(raw, "")
ck(D.pick_main_sheet(w2) == "עסקאות26", D.pick_main_sheet(w2))
rows, rep = D.rows_from_workbook(w2, "kiryat_yam", 2026, ["עסקאות26"])
ck(len(rows) == 1 and rep["stopped_at"] and rep["stopped_at"] < 410, rep)
# מוצפן
enc = io.BytesIO()
f = msoffcrypto.format.ooxml.OOXMLFile(io.BytesIO(raw)); f.encrypt("Pw1", enc)
w3 = D.open_workbook(enc.getvalue(), "Pw1")
ck(D.pick_main_sheet(w3) == "עסקאות26", "decrypts")
try:
    D.open_workbook(enc.getvalue(), "bad"); ck(False, "bad pw must raise")
except Exception:
    ck(True, "")
# הכלי המקומי משתמש באותה פונקציה
import tools.import_deal_history as T
ck(T.rows_from_workbook is D.rows_from_workbook, "shared")
print("OK", n, "checks")
```

- [ ] **Step 2: Run** `python3 tests/deals_history/test_workbook.py`. Expected: FAIL, `AttributeError: ... 'open_workbook'`.

- [ ] **Step 3: Implement**

ב-`deals_history.py`, אחרי `normalize_row`:

```python
def open_workbook(data, pw):
    """bytes של xlsx/xlsm (מוצפן או לא) → Workbook read_only. סיסמה שגויה → חריגה."""
    import io, msoffcrypto, openpyxl
    bio = io.BytesIO(data)
    of = msoffcrypto.OfficeFile(io.BytesIO(data))
    if of.is_encrypted():
        out = io.BytesIO()
        of.load_key(password=pw or "")
        of.decrypt(out)
        bio = out
    bio.seek(0)
    return openpyxl.load_workbook(bio, read_only=True, data_only=True)


def pick_main_sheet(wb):
    for ws in wb.worksheets:
        hi, fields = find_header_row(list(ws.iter_rows(values_only=True, max_row=12)))
        if hi is not None and "agent" in fields and len([k for k in fields if not k.startswith("_")]) >= 6:
            return ws.title
    return None


def rows_from_workbook(wb, branch, year, sheets, default_agent="", stop_after_empty=300):
    import collections
    rep = {"ok": 0, "skip": 0, "broken": 0, "agents": collections.Counter(), "commission": 0,
           "missing_sheets": [], "broken_rows": [], "dup_keys": [], "stopped_at": None}
    out, seen = [], set()
    names = [ws.title for ws in wb.worksheets]
    for sh in sheets:
        if sh not in names:
            rep["missing_sheets"].append(sh)
            continue
        it = wb[sh].iter_rows(values_only=True)
        head = []
        for r in it:
            head.append(r)
            if len(head) >= 12:
                break
        hi, fields = find_header_row(head)
        if hi is None:
            rep["missing_sheets"].append(sh)
            continue
        headers = [normalize_header(c) for c in head[hi]]
        def rows_iter():
            for k, r in enumerate(head[hi + 1:], start=hi + 2):
                yield k, r
            k = len(head) + 1
            for r in it:
                yield k, r
                k += 1
        empty = 0
        for i, cells in rows_iter():
            if not any(c not in (None, "") and not (isinstance(c, str) and not c.strip()) for c in (cells or ())):
                empty += 1
                if empty >= stop_after_empty:
                    rep["stopped_at"] = i   # קבצים עם מיליון שורות ריקות בסוף — לא קוראים את כולן
                    break
                continue
            empty = 0
            st, row = normalize_row(cells, fields, {"branch": branch, "year": year, "sheet": sh, "row_idx": i,
                                                    "headers": headers, "default_agent": default_agent})
            rep[st] += 1
            if st == "ok":
                if row["src_key"] in seen:
                    if row["src_key"] not in rep["dup_keys"]:
                        rep["dup_keys"].append(row["src_key"])
                    row["src_key"] = "%s|r%d" % (row["src_key"], i)
                seen.add(row["src_key"])
                out.append(row)
                rep["agents"][row["agent"]] += 1
                rep["commission"] += float(row.get("commission_net") or 0)
            elif st == "broken":
                rep["broken_rows"].append("%s שורה %d" % (sh, i))
    rep["agents"] = dict(rep["agents"])
    return out, rep
```

ב-`tools/import_deal_history.py` מוחקים את הגדרת `rows_from_workbook` המקומית ומוסיפים אחרי `import deals_history as D`:

```python
rows_from_workbook = D.rows_from_workbook   # [שלב 2א] קוד אחד לשרת ולכלי
```

- [ ] **Step 4: Run** `python3 tests/deals_history/test_workbook.py && for t in tests/deals_history/test_*.py; do python3 $t | tail -1; done`. Expected: `OK 5 checks`, וכל השאר ירוקים, כולל `test_import_tool.py` ו-`test_review_fixes.py`.
- [ ] **Step 5: Commit** — `git add deals_history.py tools/import_deal_history.py tests/deals_history/test_workbook.py`, הודעה: "היסטוריית עסקאות: פענוח חוברת משותף לשרת ולכלי + עצירה אחרי רצף שורות ריקות".

---

### Task 2: לקוח Dropbox + כלי הפקת הטוקן

**Files:** Create `dropbox_api.py`, `tools/dropbox_token.py`. Test `tests/deals_history/test_dropbox.py`.

**Interfaces — Produces:**
- `dropbox_api.configured() -> bool`
- `dropbox_api.access_token(http=requests) -> str`: מרענן את הטוקן, ושומר אותו בזיכרון עד 60 שניות לפני שהוא פג.
- `dropbox_api.list_folder(path, http=requests) -> list[{name, path, rev, server_modified, size}]`: קבצים בלבד.
- `dropbox_api.download(path, http=requests) -> (bytes, rev)`

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_dropbox.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ.update(DROPBOX_APP_KEY="k", DROPBOX_APP_SECRET="s", DROPBOX_REFRESH_TOKEN="rt")
import dropbox_api as X
X._TOK.update(v="", exp=0)
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
calls = []
class R:
    def __init__(s, code=200, j=None, content=b"", headers=None): s.status_code, s._j, s.content, s.headers = code, j, content, headers or {}
    def json(s): return s._j
    def raise_for_status(s):
        if s.status_code >= 400: raise RuntimeError("http %d" % s.status_code)
class H:
    def post(s, url, data=None, headers=None, json=None, timeout=None):
        calls.append((url, data, headers, json))
        if "oauth2/token" in url:
            return R(j={"access_token": "AT", "expires_in": 14400})
        if url.endswith("list_folder"):
            return R(j={"entries": [{".tag": "file", "name": "a.xlsx", "path_display": "/p/a.xlsx", "rev": "r1",
                                     "server_modified": "2026-10-11T13:52:00Z", "size": 5},
                                    {".tag": "folder", "name": "old", "path_display": "/p/old"}], "has_more": False})
        if url.endswith("download"):
            return R(content=b"XLSX", headers={"Dropbox-API-Result": json_mod.dumps({"rev": "r9"})})
        return R(500)
json_mod = json
h = H()
ck(X.configured(), "configured")
ck(X.access_token(h) == "AT" and calls[0][1]["refresh_token"] == "rt", "refresh")
X.access_token(h); ck(len([c for c in calls if "oauth2" in c[0]]) == 1, "token cached")
lst = X.list_folder("/p", h)
ck(lst == [{"name": "a.xlsx", "path": "/p/a.xlsx", "rev": "r1", "server_modified": "2026-10-11T13:52:00Z", "size": 5}], lst)
ck(calls[-1][2]["Authorization"] == "Bearer AT" and calls[-1][3]["path"] == "/p", "list call")
data, rev = X.download("/p/a.xlsx", h)
ck(data == b"XLSX" and rev == "r9" and json.loads(calls[-1][2]["Dropbox-API-Arg"])["path"] == "/p/a.xlsx", "download")
ck(all(ord(ch) < 128 for ch in calls[-1][2]["Dropbox-API-Arg"]), "header is ASCII (Hebrew path escaped)")
os.environ["DROPBOX_REFRESH_TOKEN"] = ""
ck(not X.configured(), "not configured without token")
print("OK", n, "checks")
```

- [ ] **Step 2: Run** `python3 tests/deals_history/test_dropbox.py`. Expected: FAIL, `ModuleNotFoundError: dropbox_api`.

- [ ] **Step 3: Implement**

```python
# dropbox_api.py
"""[DEALS-SYNC 12/10] לקוח Dropbox מינימלי (HTTP API v2) — רשימת תיקייה והורדה, refresh token מ-env.
המפתחות לא נכתבים ללוג. http מוזרק לבדיקות."""
import os, json, time
import requests

_TOK = {"v": "", "exp": 0}


def configured():
    return all((os.environ.get(k) or "").strip() for k in ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"))


def access_token(http=requests):
    if _TOK["v"] and time.time() < _TOK["exp"] - 60:
        return _TOK["v"]
    r = http.post("https://api.dropboxapi.com/oauth2/token", timeout=20, data={
        "grant_type": "refresh_token", "refresh_token": os.environ.get("DROPBOX_REFRESH_TOKEN", "").strip(),
        "client_id": os.environ.get("DROPBOX_APP_KEY", "").strip(),
        "client_secret": os.environ.get("DROPBOX_APP_SECRET", "").strip()})
    r.raise_for_status()
    j = r.json()
    _TOK.update(v=j["access_token"], exp=time.time() + int(j.get("expires_in", 14400)))
    return _TOK["v"]


def list_folder(path, http=requests):
    r = http.post("https://api.dropboxapi.com/2/files/list_folder", timeout=30,
                  headers={"Authorization": "Bearer " + access_token(http), "Content-Type": "application/json"},
                  json={"path": path, "recursive": False})
    r.raise_for_status()
    out = []
    for e in (r.json() or {}).get("entries", []):
        if e.get(".tag") == "file":
            out.append({"name": e["name"], "path": e["path_display"], "rev": e.get("rev", ""),
                        "server_modified": e.get("server_modified", ""), "size": e.get("size", 0)})
    return out


def download(path, http=requests):
    r = http.post("https://content.dropboxapi.com/2/files/download", timeout=120,
                  headers={"Authorization": "Bearer " + access_token(http),
                           "Dropbox-API-Arg": json.dumps({"path": path}, ensure_ascii=True)})
    r.raise_for_status()
    meta = json.loads(r.headers.get("Dropbox-API-Result") or "{}")
    return r.content, meta.get("rev", "")
```

השדה `Dropbox-API-Arg` בכותרת חייב להיות ASCII, ולכן `ensure_ascii=True` (נתיבי הדרופבוקס בעברית).

```python
# tools/dropbox_token.py
"""מפיק refresh token לאפליקציית Dropbox של אפי — רץ על המחשב של אייל, פעם אחת.
App key: הקלדה רגילה. App secret וקוד האישור: הקלדה מוסתרת. ה-refresh token מועתק ללוח (pbcopy) — לא מודפס."""
import getpass, subprocess, webbrowser, urllib.parse, requests


def main():
    key = input("App key: ").strip()
    secret = getpass.getpass("App secret: ").strip()
    url = "https://www.dropbox.com/oauth2/authorize?" + urllib.parse.urlencode(
        {"client_id": key, "response_type": "code", "token_access_type": "offline"})
    print("נפתח דפדפן לאישור. אחרי 'Allow' — העתק את הקוד שמוצג.")
    webbrowser.open(url)
    code = getpass.getpass("הדבק את הקוד: ").strip()
    r = requests.post("https://api.dropboxapi.com/oauth2/token", timeout=20,
                      data={"code": code, "grant_type": "authorization_code", "client_id": key, "client_secret": secret})
    j = r.json() if r.ok else {}
    rt = j.get("refresh_token", "")
    if not rt:
        print("לא התקבל טוקן (%s). נסה שוב." % r.status_code)
        return
    subprocess.run(["pbcopy"], input=rt.encode(), check=True)
    print("ה-refresh token הועתק ללוח. הדבק אותו ב-Render כ-DROPBOX_REFRESH_TOKEN.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run** `python3 tests/deals_history/test_dropbox.py`. Expected: `OK 8 checks`.
- [ ] **Step 5: Commit** — `git add dropbox_api.py tools/dropbox_token.py tests/deals_history/test_dropbox.py`, הודעה: "היסטוריית עסקאות: לקוח Dropbox (רשימה/הורדה, refresh token) + כלי הפקת טוקן מקומי".

---

### Task 3: תכנון הסנכרון (טהור) + סימון חסרים בטבלה

**Files:** Modify `deals_history.py`, `supabase_db.py`. Test `tests/deals_history/test_sync_plan.py`.

**Interfaces — Produces:**
- `pick_latest(entries) -> dict | None`: קובץ `.xls*` עם "מעקב" או "עסקאות" בשם, בלי `~$`, ה-`server_modified` הגבוה ביותר.
- `row_hash(row) -> str`: sha1 של השדות המנורמלים, בלי `raw` ובלי מפתחות שמתחילים ב-`_`.
- `sync_plan(existing: list[row], incoming: list[row], switched: bool) -> {"upsert": [...], "missing": [keys], "back": [keys], "guarded": bool}`
  - upsert: חדשות, או שה-hash שלהן השתנה.
  - missing: מפתחות קיימים שלא הגיעו ושעוד אין להם `missing_since`.
  - back: מפתחות שחזרו.
  - guarded: כשהקובץ התחלף (`switched`) והחדש מכיל פחות מ-60% מהמפתחות הקיימים, `missing` מתרוקן ו-`guarded=True`.
- `supabase_db.deal_history_set_missing(keys, ts_iso_or_None) -> int`: PATCH לפי `src_key` במנות של 100.
- `_DH_COLS` מקבל את `src_hash`, `src_path`, `agent_raw`.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_sync_plan.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import deals_history as D
import supabase_db as S
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
E = [{"name": "מעקב עסקאות 2026.xlsx", "path": "/a/1", "rev": "1", "server_modified": "2026-07-09T10:47:00Z"},
     {"name": "מעקב עסקאות 2026 (Ohad Peled's conflicted copy 2026-02-11).xlsx", "path": "/a/2", "rev": "2", "server_modified": "2026-10-11T13:52:00Z"},
     {"name": "~$מעקב עסקאות 2026.xlsx", "path": "/a/3", "rev": "3", "server_modified": "2026-10-12T00:00:00Z"},
     {"name": "סיכום_עסקאות_אפריל_2026.txt", "path": "/a/4", "rev": "4", "server_modified": "2026-10-12T00:00:00Z"}]
ck(D.pick_latest(E)["path"] == "/a/2", "newest tracking file, conflicted allowed, ~$ and txt ignored")
ck(D.pick_latest([]) is None, "empty")
a = {"src_key": "b|2026|s|1", "agent": "x", "deal_amount": 1, "raw": {"z": 1}}
ck(D.row_hash(a) == D.row_hash(dict(a, raw={"z": 2}, _x=5)) and D.row_hash(a) != D.row_hash(dict(a, deal_amount=2)), "hash ignores raw/_")
ex = [dict(src_key="k1", src_hash=D.row_hash({"src_key": "k1", "v": 1})),
      dict(src_key="k2", src_hash="old"), dict(src_key="k3", src_hash="h"),
      dict(src_key="k4", src_hash="h", missing_since="2026-10-01T00:00:00Z")]
inc = [{"src_key": "k1", "v": 1}, {"src_key": "k2", "v": 2}, {"src_key": "k4", "v": 4}, {"src_key": "k5", "v": 5}]
p = D.sync_plan(ex, inc, switched=False)
ck(sorted(r["src_key"] for r in p["upsert"]) == ["k2", "k4", "k5"], p["upsert"])
ck(all(r.get("src_hash") for r in p["upsert"]), "upserts carry hash")
ck(p["missing"] == ["k3"] and p["back"] == ["k4"] and not p["guarded"], p)
few = D.sync_plan(ex, [{"src_key": "k5", "v": 5}], switched=True)
ck(few["missing"] == [] and few["guarded"], "switched file with <60% → no missing marks")
ck(D.sync_plan(ex, [{"src_key": "k5", "v": 5}], switched=False)["missing"] == ["k1", "k2", "k3"], "same file → missing marked")
# שכבת נתונים
calls = []
class Rq:
    def patch(s, url, headers=None, params=None, json=None, timeout=None):
        calls.append((params, json));
        class X:
            def raise_for_status(self): pass
        return X()
S.requests = Rq(); S.SUPABASE_URL = "https://x"; S.SB_OFFICE_ID = "OFF"
ck(S.deal_history_set_missing(["k1", 'a"b'], "2026-10-12T00:00:00Z") == 2, "count")
ck(calls[0][1] == {"missing_since": "2026-10-12T00:00:00Z"} and calls[0][0]["src_key"].startswith("in.(") and calls[0][0]["office_id"] == "eq.OFF", calls[0])
ck('"a\\"b"' in calls[0][0]["src_key"], "quoted keys")
ck(S.deal_history_set_missing([], None) == 0, "empty")
ck("src_hash" in S._DH_COLS and "src_path" in S._DH_COLS and "agent_raw" in S._DH_COLS, "cols")
print("OK", n, "checks")
```

- [ ] **Step 2: Run.** Expected: FAIL, `AttributeError: pick_latest`.

- [ ] **Step 3: Implement**

```python
# deals_history.py — הוספה
import hashlib as _hashlib, json as _json

_TRACK_NAME = re.compile(r"מעקב|עסקאות")


def pick_latest(entries):
    """אייל 12/10: בכל תיקייה — קובץ המעקב שנשמר אחרון (גם עותק כפול)."""
    pool = [e for e in (entries or []) if re.search(r"\.xls[xmb]?$", e.get("name", ""), re.I)
            and not e["name"].startswith("~$") and _TRACK_NAME.search(e["name"])]
    return max(pool, key=lambda e: (e.get("server_modified") or "", e["name"])) if pool else None


def row_hash(row):
    core = {k: v for k, v in (row or {}).items() if k != "raw" and not k.startswith("_") and k != "src_hash"}
    return _hashlib.sha1(_json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def sync_plan(existing, incoming, switched):
    ex = {r["src_key"]: r for r in existing or []}
    seen = set()
    up = []
    for r in incoming or []:
        h = row_hash(r)
        seen.add(r["src_key"])
        old = ex.get(r["src_key"])
        if not old or old.get("src_hash") != h or old.get("missing_since"):
            up.append(dict(r, src_hash=h))
    missing = [k for k, r in ex.items() if k not in seen and not r.get("missing_since")]
    back = [k for k, r in ex.items() if k in seen and r.get("missing_since")]
    guarded = False
    if switched and ex and len(seen & set(ex)) < 0.6 * len(ex):
        missing, guarded = [], True
    return {"upsert": up, "missing": sorted(missing), "back": sorted(back), "guarded": guarded}
```

```python
# supabase_db.py — _DH_COLS: להוסיף ",src_hash,src_path,agent_raw" בסוף המחרוזת; ופונקציה חדשה:
def deal_history_set_missing(keys, ts):
    """missing_since=ts (או null — חזרה) לשורות לפי src_key. מנות של 100."""
    keys = [k for k in (keys or []) if k]
    n = 0
    for i in range(0, len(keys), 100):
        part = keys[i:i + 100]
        lst = ",".join('"%s"' % k.replace('"', '\\"') for k in part)
        r = requests.patch(SUPABASE_URL + "/rest/v1/deal_history", headers={**_headers(), "Prefer": "return=minimal"},
                           params={"office_id": "eq." + SB_OFFICE_ID, "src_key": "in.(%s)" % lst},
                           json={"missing_since": ts}, timeout=_TIMEOUT)
        r.raise_for_status()
        n += len(part)
    return n
```

- [ ] **Step 4: Run** את הבדיקה ואת כל החבילה. Expected: `OK 13 checks`, הכל ירוק.
- [ ] **Step 5: Commit** — הודעה: "היסטוריית עסקאות: תכנון סנכרון — הקובץ האחרון, hash לשורה, חסרים/חזרו, הגנה במעבר קובץ".

---

### Task 4: לולאת הסנכרון, מצב, התראות

**Files:** Modify `deals_history.py`. Test `tests/deals_history/test_sync_loop.py`.

**Interfaces:**
- Consumes: `dropbox_api.*`, `open_workbook`, `pick_main_sheet`, `rows_from_workbook`, `sync_plan`, `canon_agent`, `supabase_db.deal_history_all/upsert/set_missing`, `G["send_push"]`, `G["_canon_agent_name"]`, `G["_log_activity"]`.
- Produces:
  - `SYNC_DIRS(year) -> {branch: path}`. ברירת מחדל:
    - `/הפרלמנט/אייל/מעקב עסקאות/{year}`
    - `/הפרלמנט/אוהד/מעקב עסקאות מוצקין/{year}`
    - `/הפרלמנט/מעקב עסקאות קרית ים/{year}`

    כל אחד ניתן לדריסה דרך env, למשל `DEALS_DIR_BIALIK`.
  - `BRANCH_PW = {"bialik": "DEALS_PW_BIALIK", "motzkin": "DEALS_PW_MOTZKIN_YAM", "kiryat_yam": "DEALS_PW_MOTZKIN_YAM"}`.
  - `DEFAULT_AGENT = {"kiryat_yam": "קובי חמו"}`.
  - `load_agent_map() -> dict`: מתוך `tools/deals_agent_map.json`, עם מטמון.
  - `sync_branch(branch, year, sb, dbx, canon, now_iso) -> dict state`. המצב: `{file, rev, rows, upserted, missing, back, guarded, unmapped:[names], error, ts, switched}`.
  - `SYNC_STATE: {branch: state}`.
  - `sync_tick(...)`.
  - הלולאה רצה כל 5 דקות, ומתחילה ב-`before_request` רק כש-`DEALS_SYNC=1`.
  - `GET /v2/api/deals/history/sync`: לעורכים. מחזיר `{ok, enabled, configured, year, branches: SYNC_STATE}`, בלי סודות.
  - `GET /v2/api/deals/history/review`: לעורכים. מחזיר `{ok, missing:[view_full], unmapped:[{branch, name, n}]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/deals_history/test_sync_loop.py
import sys, os, io, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import openpyxl
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
def xlsx(rows):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "עסקאות26"
    ws.append(['מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ", "התקבל כסף"])
    for r in rows: ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()
FILES = {"/d": [{"name": "מעקב עסקאות 2026.xlsx", "path": "/d/m.xlsx", "rev": "r1", "server_modified": "2026-10-12T10:00:00Z"}]}
CONTENT = {"/d/m.xlsx": xlsx([[1, dt.datetime(2026, 1, 5), "קרית ים", "הרצל 1", "מוכר", "נדב", 900000, 9000, None],
                              [2, dt.datetime(2026, 2, 5), "קרית ים", "הרצל 2", "קונה", "חדש בלי מיפוי", 800000, 8000, 8000]])}
dl = []
class DBX:
    def configured(self): return True
    def list_folder(self, p): return FILES[p]
    def download(self, p): dl.append(p); return CONTENT[p], FILES["/d"][0]["rev"]
DB = {}
class SB:
    def enabled(self): return True
    def deal_history_all(self): return list(DB.values())
    def deal_history_upsert(self, rows):
        for r in rows: DB[r["src_key"]] = dict(r, id=r["src_key"])
        return len(rows)
    def deal_history_set_missing(self, keys, ts):
        for k in keys: DB[k]["missing_since"] = ts
        return len(keys)
D._AGENT_MAP_CACHE.clear(); D._AGENT_MAP_CACHE.update(m={"bialik|נדב": "נדב רייזר"}, ts=9e18)
st = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "2026-10-12T10:05:00Z", folder="/d", pw="")
ck(st["error"] == "" and st["rows"] == 2 and st["upserted"] == 2 and st["file"] == "מעקב עסקאות 2026.xlsx", st)
ck(DB["bialik|2026|עסקאות26|1"]["agent"] == "נדב רייזר" and DB["bialik|2026|עסקאות26|1"]["agent_raw"] == "נדב", "mapped")
ck(st["unmapped"] == ["חדש בלי מיפוי"], st["unmapped"])
ck(DB["bialik|2026|עסקאות26|2"]["paid_amount"] == 8000 and DB["bialik|2026|עסקאות26|2"]["src_path"] == "/d/m.xlsx", "fields")
# אותו rev → בלי הורדה ובלי כתיבה
before = len(dl)
st2 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "2026-10-12T10:10:00Z", folder="/d", pw="", last=st)
ck(len(dl) == before and st2["upserted"] == 0 and st2.get("skipped"), st2)
# rev חדש, שורה 2 נמחקה → מסומנת חסרה
CONTENT["/d/m.xlsx"] = xlsx([[1, dt.datetime(2026, 1, 5), "קרית ים", "הרצל 1", "מוכר", "נדב", 900000, 9000, 9000]])
FILES["/d"][0]["rev"] = "r2"
st3 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "2026-10-12T10:15:00Z", folder="/d", pw="", last=st)
ck(st3["upserted"] == 1 and st3["missing"] == 1 and DB["bialik|2026|עסקאות26|2"]["missing_since"] == "2026-10-12T10:15:00Z", st3)
ck(DB["bialik|2026|עסקאות26|1"]["paid_amount"] == 9000, "update applied")
# כשל הורדה / סיסמה → שגיאה במצב, הטבלה לא נגעה
class BAD(DBX):
    def download(self, p): raise RuntimeError("boom")
FILES["/d"][0]["rev"] = "r3"
snap = {k: dict(v) for k, v in DB.items()}
st4 = D.sync_branch("bialik", 2026, SB(), BAD(), lambda x: x, "2026-10-12T10:20:00Z", folder="/d", pw="", last=st3)
ck("boom" in st4["error"] and DB == snap, st4)
# בלי קובץ מעקב בתיקייה
FILES["/e"] = []
st5 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "t", folder="/e", pw="")
ck(st5["error"] == "אין קובץ מעקב בתיקייה", st5)
# מעבר קובץ → switched + התראה
pushes = []
FILES["/d"].append({"name": "מעקב עסקאות 2026 (Ohad's conflicted copy).xlsx", "path": "/d/c.xlsx", "rev": "c1", "server_modified": "2026-10-12T11:00:00Z"})
CONTENT["/d/c.xlsx"] = CONTENT["/d/m.xlsx"]
st6 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "t6", folder="/d", pw="", last=st3, push=lambda t, b: pushes.append((t, b)))
ck(st6["switched"] and pushes and "conflicted" in pushes[0][1], (st6, pushes))
print("OK", n, "checks")
```

- [ ] **Step 2: Run.** Expected: FAIL, `AttributeError: _AGENT_MAP_CACHE`.

- [ ] **Step 3: Implement**

```python
# deals_history.py — הוספה
import threading as _threading

BRANCH_PW = {"bialik": "DEALS_PW_BIALIK", "motzkin": "DEALS_PW_MOTZKIN_YAM", "kiryat_yam": "DEALS_PW_MOTZKIN_YAM"}
DEFAULT_AGENT = {"kiryat_yam": "קובי חמו"}
_DIRS = {"bialik": "/הפרלמנט/אייל/מעקב עסקאות/{y}", "motzkin": "/הפרלמנט/אוהד/מעקב עסקאות מוצקין/{y}",
         "kiryat_yam": "/הפרלמנט/מעקב עסקאות קרית ים/{y}"}
_AGENT_MAP_CACHE = {}
SYNC_STATE = {}
_SYNC_THREAD = [None]
_SYNC_LOCK = _threading.Lock()


def SYNC_DIRS(year):
    return {b: (os.environ.get("DEALS_DIR_" + b.upper()) or p).format(y=year) for b, p in _DIRS.items()}


def load_agent_map():
    if _AGENT_MAP_CACHE.get("ts", 0) > time.time() - 600 and "m" in _AGENT_MAP_CACHE:
        return _AGENT_MAP_CACHE["m"]
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "deals_agent_map.json")
        m = _json.load(open(p, encoding="utf-8"))
    except Exception:
        m = {}
    _AGENT_MAP_CACHE.update(m=m, ts=time.time())
    return m


def sync_branch(branch, year, sb, dbx, canon, now_iso, folder=None, pw=None, last=None, push=None):
    """קובץ אחד → הטבלה. כל כשל = מצב עם שגיאה, בלי לגעת בטבלה (מקור האמת לא נפגע)."""
    st = {"file": "", "rev": "", "rows": 0, "upserted": 0, "missing": 0, "back": 0, "guarded": False,
          "unmapped": [], "error": "", "ts": now_iso, "switched": False}
    last = last or {}
    try:
        folder = folder or SYNC_DIRS(year)[branch]
        e = pick_latest(dbx.list_folder(folder))
        if not e:
            st["error"] = "אין קובץ מעקב בתיקייה"
            return st
        st.update(file=e["name"], rev=e["rev"], path=e["path"])
        st["switched"] = bool(last.get("path")) and last.get("path") != e["path"]
        if not st["switched"] and last.get("rev") == e["rev"] and not last.get("error"):
            st.update(skipped=True, rows=last.get("rows", 0), unmapped=last.get("unmapped", []))
            return st
        data, _rev = dbx.download(e["path"])
        wb = open_workbook(data, pw if pw is not None else os.environ.get(BRANCH_PW[branch], ""))
        sh = pick_main_sheet(wb)
        if not sh:
            st["error"] = "לא נמצא גיליון עסקאות בקובץ"
            return st
        rows, rep = rows_from_workbook(wb, branch, year, [sh], DEFAULT_AGENT.get(branch, ""))
        amap = load_agent_map()
        unm = set()
        for r in rows:
            raw = r["agent"]
            r["agent_raw"] = raw
            r["agent"] = canon_agent(raw, branch, amap, canon) or raw
            r["src_path"] = e["path"]
            if "%s|%s" % (branch, raw) not in amap and raw != DEFAULT_AGENT.get(branch):
                unm.add(raw)
        existing = [x for x in sb.deal_history_all() if x.get("branch") == branch and x.get("year") == year]
        plan = sync_plan(existing, rows, st["switched"])
        if plan["upsert"]:
            sb.deal_history_upsert(plan["upsert"])
        if plan["missing"]:
            sb.deal_history_set_missing(plan["missing"], now_iso)
        if plan["back"]:
            sb.deal_history_set_missing(plan["back"], None)
        st.update(rows=len(rows), upserted=len(plan["upsert"]), missing=len(plan["missing"]),
                  back=len(plan["back"]), guarded=plan["guarded"], unmapped=sorted(unm), sheet=sh)
        if st["switched"] and push:
            push("מעקב עסקאות — הקובץ הפעיל התחלף", "%s: עכשיו נקרא %s" % (BRANCHES[branch], e["name"]))
        _HIST_CACHE["ts"] = 0
    except Exception as ex:
        st["error"] = "%s: %s" % (type(ex).__name__, str(ex)[:160])
    return st


def sync_tick(sb, dbx, canon, push=None, log=None):
    year = int(os.environ.get("DEALS_SYNC_YEAR") or _dt.date.today().year)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    for b in BRANCHES:
        prev = SYNC_STATE.get(b)
        st = sync_branch(b, year, sb, dbx, canon, now, last=prev, push=push)
        SYNC_STATE[b] = st
        if st["error"] and log and (not prev or prev.get("error") != st["error"]):
            log.warning("deals sync %s: %s" % (b, st["error"]))
```

```python
# deals_history.py — בתוך register(app, G, page), בסוף:
    import dropbox_api as _dbx

    def _sync_loop():
        while True:
            try:
                sync_tick(sb, _dbx, G["_canon_agent_name"], push=G.get("send_push"), log=G.get("log"))
            except Exception as e:
                SYNC_STATE["_loop"] = {"error": str(e)[:160]}
            time.sleep(300)

    @app.before_request
    def _deals_sync_ensure():
        if (os.environ.get("DEALS_SYNC") or "") != "1" or not _dbx.configured():
            return None
        with _SYNC_LOCK:
            th = _SYNC_THREAD[0]
            if th is None or not th.is_alive():
                _SYNC_THREAD[0] = _threading.Thread(target=_sync_loop, daemon=True, name="deals-sync")
                _SYNC_THREAD[0].start()
        return None

    @app.route("/v2/api/deals/history/sync", methods=["GET"])
    def v2_deals_history_sync():
        s, err = _editor()
        if err:
            return err
        th = _SYNC_THREAD[0]
        return jsonify({"ok": True, "enabled": (os.environ.get("DEALS_SYNC") or "") == "1",
                        "configured": _dbx.configured(), "alive": bool(th and th.is_alive()),
                        "year": int(os.environ.get("DEALS_SYNC_YEAR") or _dt.date.today().year),
                        "branches": {k: v for k, v in SYNC_STATE.items()}})

    @app.route("/v2/api/deals/history/review", methods=["GET"])
    def v2_deals_history_review():
        s, err = _editor()
        if err:
            return err
        miss = [view_full(r) for r in _rows(sb) if r.get("missing_since")]
        unm = [{"branch": b, "name": nm} for b, st in SYNC_STATE.items() if isinstance(st, dict)
               for nm in (st.get("unmapped") or [])]
        return jsonify({"ok": True, "missing": miss, "unmapped": unm})
```

`deal_history_all` מחזיר `src_hash` ו-`missing_since`, כי `_DH_COLS` עודכן ב-Task 3. כש-`sync_plan` מקבל `existing` מהטבלה, הוא משווה את ה-`src_hash`.

- [ ] **Step 4: Run** את הבדיקה, את כל החבילה, ואת בדיקת העלייה:

  ```bash
  CLAUDE_API_KEY=x WARMUP_ON_BOOT=0 DAILY_REPORT=0 python3 -c "import app; print(sorted(r.rule for r in app.app.url_map.iter_rules() if 'deals/history' in r.rule))"
  ```

  Expected: `OK 10 checks`, וברשימה מופיעים `/sync` ו-`/review`.
- [ ] **Step 5: Commit** — הודעה: "היסטוריית עסקאות: סנכרון קבצי 2026 מ-Dropbox כל 5 דקות (קריאה בלבד) — מצב, לבדיקה, התראה על מעבר קובץ".

---

### Task 5: טאב "לבדיקה" ושורת מצב הסנכרון בדף

**Files:** Modify `deals_history.py` (`V2_HISTORY_HTML`). Test: עדכון `tests/deals_history/test_page.js`.

**Interfaces — Produces:**
- `syncLine(j) -> html`: שורת מצב בראש טאב "דוחות" לעורכים. לכל משרד: "עודכן לפני X דק'", או שגיאה באדום-טקסט `#C24040`, או "כבוי".
- `reviewHtml(j) -> html`: שתי קבוצות:
  - "נעלמו מהאקסל": כרטיסים עם `openCard`.
  - "שמות סוכנים בלי מיפוי": משרד + שם, עם הסבר "לשלוח לאייל/Claude למיפוי".
- טאב חדש "לבדיקה" לעורכים, אחרי "לא דווח".

- [ ] **Step 1: Test.** להוסיף ל-`test_page.js`, לפני `console.log`:

```javascript
eval(js.replace(/\(function\(\)\{\s*try\{ TOK[\s\S]*$/, '') + ';global.T2={syncLine,reviewHtml};');
const sl = T2.syncLine({enabled: true, configured: true, alive: true, branches: {bialik: {ts: new Date(Date.now() - 120000).toISOString(), file: 'מעקב עסקאות 2026.xlsx', error: ''},
  motzkin: {ts: new Date().toISOString(), error: 'BadPassword: x'}}});
ck(sl.includes('ביאליק') && sl.includes('לפני 2 דק') && sl.includes('מוצקין') && sl.includes('#C24040'), sl);
ck(T2.syncLine({enabled: false}).includes('כבוי'), 'off');
const rv = T2.reviewHtml({missing: [{date: '01/02/2026', street: 'הרצל 2', city: 'קרית ים', agent: 'נדב רייזר', year: 2026}], unmapped: [{branch: 'bialik', name: 'חדש'}]});
ck(rv.includes('נעלמו מהאקסל') && rv.includes('הרצל 2') && rv.includes('ביאליק') && rv.includes('חדש'), rv);
ck(T2.reviewHtml({missing: [], unmapped: []}).includes('אין מה לבדוק'), 'empty');
```

- [ ] **Step 2: Run** `node tests/deals_history/test_page.js`. Expected: FAIL, `ReferenceError: syncLine`.
- [ ] **Step 3: Implement** בתוך ה-`<script>` של `V2_HISTORY_HTML`:

```javascript
function agoTx(iso){ var m = Math.round((Date.now() - Date.parse(iso || 0)) / 60000); return isNaN(m) ? '' : (m < 1 ? 'עכשיו' : 'לפני ' + m + ' דק\''); }
function syncLine(j){
  if (!j || !j.enabled) return '<div class="sb">סנכרון קבצי השנה כבוי</div>';
  if (!j.configured) return '<div class="sb" style="color:#C24040">סנכרון: חסרים מפתחות Dropbox</div>';
  var b = j.branches || {};
  return '<div class="sb">' + ['bialik', 'motzkin', 'kiryat_yam'].filter(function(k){ return b[k]; }).map(function(k){
    var s = b[k];
    return esc(BR[k]) + ': ' + (s.error ? '<span style="color:#C24040">' + esc(s.error) + '</span>' : 'עודכן ' + esc(agoTx(s.ts)));
  }).join(' · ') + '</div>';
}
function reviewHtml(j){
  var m = (j && j.missing) || [], u = (j && j.unmapped) || [];
  if (!m.length && !u.length) return emptyHtml('אין מה לבדוק', 'שורות שנעלמו מקבצי השנה ושמות סוכנים חדשים יופיעו כאן');
  var h = '';
  if (m.length) h += '<div class="ad">נעלמו מהאקסל · ' + m.length + '</div>' + m.map(openCard).join('');
  if (u.length) h += '<div class="card"><div class="ad">שמות סוכנים בלי מיפוי</div><div class="sb">שלח את השמות למיפוי — עד אז הם לא מקושרים לסוכן באפליקציה</div>' +
    u.map(function(x){ return '<div class="sb">' + esc(BR[x.branch] || x.branch) + ' · ' + esc(x.name) + '</div>'; }).join('') + '</div>';
  return h;
}
```

ב-`tabsFor()` לעורכים מוסיפים את `['review', 'לבדיקה']` אחרי `['unrep', 'לא דווח']`.

ב-`draw()`:
- ענף חדש `TAB === 'review'`: `GET('/v2/api/deals/history/review')`, ואז `list.innerHTML = reviewHtml(j)` עם `.catch` כמו בשאר.
- בענף `stats`: אחרי טעינת הדוחות, `GET('/v2/api/deals/history/sync').then(function(s){ tools.insertAdjacentHTML('beforeend', syncLine(s)); }).catch(function(){})`.

- [ ] **Step 4: Run** `node tests/deals_history/test_page.js`, ואחריו `node --check` לסקריפט הדף, ואת כל החבילה. Expected: `OK 14 checks`, הכל ירוק.
- [ ] **Step 5: Commit** — הודעה: "היסטוריית עסקאות: טאב 'לבדיקה' ושורת מצב הסנכרון בדוחות".

---

### Task 6: ביקורת, יומן ומסירה

- [ ] **Step 1:**
  - כל הבדיקות, ast, בדיקת כפילויות שמות.
  - בדיקת עלייה של `app` עם `DEALS_SYNC` ריק: אין thread, ו-`/sync` מחזיר `enabled:false`.
  - ביקורת סופית של מבקר טרי (Opus) לפי ה-Review Focus.
- [ ] **Step 2:** תיקוני ביקורת: Critical ו-Important, כל אחד RED→GREEN.
- [ ] **Step 3:** רישום ביומן ההחלטות ב-CLAUDE.md, וקומיט ב-remax-family.
- [ ] **Step 4:** הצעדים של אייל:
  1. יצירת אפליקציה ב-Dropbox (dropbox.com/developers/apps):
     - Scoped access, Full Dropbox.
     - הרשאות: `files.metadata.read` ו-`files.content.read`.
     - Submit.
  2. `python3 tools/dropbox_token.py`: מדביקים App key ו-App secret, מאשרים בדפדפן ומדביקים את הקוד. ה-refresh token מועתק ללוח.
  3. ב-Render מגדירים:
     - `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`
     - `DEALS_PW_BIALIK`, `DEALS_PW_MOTZKIN_YAM`
     - `DEALS_SYNC=1`
  4. push, deploy, ופתיחת `/v2/history`. ב"דוחות" מופיעה שורת המצב, וב"לא שולם" מופיעות שורות 2026.
