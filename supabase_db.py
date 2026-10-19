# ============================================================================
# supabase_db.py — Family Bot: שכבת קריאה מ-Supabase ("נכס נולד", שלב 1)
# ----------------------------------------------------------------------------
# מודול עצמאי לחלוטין. app.py פונה אליו רק כאשר NEWBORN_SOURCE=supabase;
# בכל מקרה אחר הוא רדום ואין לו שום השפעה. הכתיבות ממשיכות לזרום דרך
# Apps Script (שכותב לגיליון + Supabase במקביל) — המודול הזה קורא בלבד.
#
# משתני סביבה (Render env בלבד, לא בקוד):
#   SUPABASE_URL         — https://<ref>.supabase.co
#   SUPABASE_SERVICE_KEY — service_role key
#   SB_OFFICE_ID         — מזהה המשרד (ברירת מחדל: RE/MAX Family)
#
# בדיקה מקומית:  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python3 supabase_db.py
# ============================================================================
import os
import re
import datetime as _dt

import requests

SUPABASE_URL         = (os.environ.get("SUPABASE_URL", "") or "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = (os.environ.get("SUPABASE_SERVICE_KEY", "") or "").strip()
SB_OFFICE_ID         = (os.environ.get("SB_OFFICE_ID", "") or "").strip() or \
                       "11111111-1111-4111-8111-111111111111"

# חלון הנתונים של listnewborn ב-Apps Script — 220 יום. משוחזר כאן כדי ששני
# המסלולים יחזירו בדיוק את אותן שורות (parity).
NB_SHEET_CUTOFF_DAYS = int(os.environ.get("NB_SHEET_CUTOFF_DAYS", "220") or 220)

_PAGE = 1000
_TIMEOUT = 20


def enabled():
    """האם המודול מוגדר (יש URL ומפתח)."""
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
    }


def _get_all(table, select, extra_params=None):
    """קריאה מדופדפת (1000 בכל עמוד) מ-PostgREST; מחזיר list של dicts.
    🐞 10/09: דפדוף limit/offset בלי ORDER BY אינו יציב — Postgres מחזיר עמודים בסדר
    שרירותי, ובטבלה שמתעדכנת כל דקה (נכס נולד 2,500+ שורות = 3 עמודים) שורות נפלו
    בין העמודים ("נכסים נחמקים") או הוכפלו. מיון קבוע לפי id (uuid, יציב) כברירת מחדל;
    קריאה שמעבירה order משלה (properties לפי sheet_row) שומרת אותו."""
    out, offset = [], 0
    while True:
        params = {
            "select": select,
            "office_id": "eq." + SB_OFFICE_ID,
            "limit": str(_PAGE),
            "offset": str(offset),
            "order": "id.asc",
        }
        if extra_params:
            params.update(extra_params)
        r = requests.get(SUPABASE_URL + "/rest/v1/" + table,
                         headers=_headers(), params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        page = r.json() or []
        out.extend(page)
        if len(page) < _PAGE:
            return out
        offset += _PAGE


def _nb_parse_date_ms(s):
    """שחזור מדויק של _nbParseDate מה-Apps Script: dd/mm/yyyy או dd.mm.yyyy,
    אחרת ISO (10 תווים ראשונים). כישלון פענוח → 0 (=נכלל, לא מסונן)."""
    s = str(s or "").strip()
    if not s:
        return 0
    m = re.match(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
    if m:
        try:
            return int(_dt.datetime(int(m.group(3)), int(m.group(2)),
                                    int(m.group(1))).timestamp() * 1000)
        except Exception:
            return 0
    try:
        return int(_dt.datetime.fromisoformat(s[:10]).timestamp() * 1000)
    except Exception:
        return 0


DELISTED_GRACE_DAYS = 3   # "ירד מפרסום" מוצג עם תווית 3 ימים ואז נעלם (החלטת אייל 09/09)

def delisted_visible(stamp):
    """stamp של ירד-מפרסום (DD/MM/YYYY) → האם עדיין בחלון התווית. ריק=פעיל=מוצג;
    חותמת לא-פריסה = ירד, לא מוצג."""
    t = str(stamp or "").strip()
    if not t:
        return True
    m = re.match(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{4})", t)
    if not m:
        return False
    try:
        d = _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except Exception:
        return False
    return (_dt.date.today() - d).days < DELISTED_GRACE_DAYS


# רשימת ערים סגורה (החלטת אייל 01/09 לנכס נולד; 28/09 גם לשת"פ): רק 4 הקריות + קרית חיים
# מזרחית/מערבית (חלק מעיריית חיפה — מזוהה לפי שכונה/רחוב/כתובת). כל השאר נשאר ב-DB, לא מוצג.
_KRAYOT_CITIES = ("קרית אתא", "קרית מוצקין", "קרית ביאליק", "קרית ים")

def krayot_city_ok(city, zone_text=""):
    """True = מוצג. עיר ריקה → מוצג (הצינור הישן). חיפה/קרית חיים → רק אם zone_text
    (שכונה+רחוב+כתובת+עיר) מכיל 'קרית חיים'. ערים אחרות → רק מרשימת הקריות."""
    _city = str(city or "").strip().replace("קריית", "קרית")
    if not _city:
        return True
    if "חיפה" in _city or "קרית חיים" in _city:
        return bool(re.search(r"קרי+ת חיים", str(zone_text or "").replace("קריית", "קרית")))
    return any(w in _city for w in _KRAYOT_CITIES)


def fetch_newborn_rows():
    """שורות 'נכס נולד' — אותו פורמט בדיוק כמו listnewborn מה-Apps Script:
    list של dicts עם מפתחות עבריים (העמודה raw שנשמרה 1:1 מהגיליון),
    כולל אותו חיתוך של NB_SHEET_CUTOFF_DAYS ימים על 'נוצר בתאריך'."""
    recs = _get_all("newborn_listings", "source_key,raw")
    cutoff_ms = (_dt.datetime.now().timestamp() - NB_SHEET_CUTOFF_DAYS * 86400) * 1000
    rows = []
    for rec in recs:
        key = str(rec.get("source_key") or "")
        if key.startswith("test:"):
            continue
        raw = rec.get("raw")
        if not isinstance(raw, dict) or not raw:
            continue
        ep = _nb_parse_date_ms(raw.get("נוצר בתאריך", ""))
        if ep and ep < cutoff_ms:
            continue          # ישן מדי — זהה להתנהגות listnewborn
        # השכרות מסריקת יד2 לא מוצגות בנכס נולד (החלטת אייל 31/08) — נשארות ב-DB
        # לאופציה עתידית פר-סוכן ב"ניהול". שורות הצינור הישן בלי "סוג עסקה" — עוברות.
        if "שכר" in str(raw.get("סוג עסקה") or ""):
            continue
        # 24/09 (אייל): בנכס נולד מודעה שירדה מיד2 *נשארת* עם התווית "ירד מפרסום" (לא נעלמת אחרי 3 ימים);
        # הפיד ממיין אותה לסוף. (במשרד/שת"פ נשאר חלון 3 הימים.)
        # רשימת ערים סגורה (החלטת אייל 01/09) — krayot_city_ok (משותף עם השת"פ מ-28/09)
        if not krayot_city_ok(raw.get("עיר") or raw.get("עיר / ישוב"),
                              " ".join(str(raw.get(k) or "") for k in ("שכונה", "רחוב", "רחוב1", "כתובת", "עיר"))):
            continue   # עיר מחוץ לרשימה (נשר/עכו/חריש/בת ים/חיפה-שאינה-קרית-חיים) — מוסתר
        rows.append(raw)
    return rows


def fetch_newborn_contacts():
    """פניות 'כבר פנו' — אותו מבנה כמו _fetch_newborn_contacts ב-app.py:
    {listing_key: [agent, agent, ...]} בלי כפילויות."""
    recs = _get_all("newborn_contacts", "listing_key,agent_name")
    d = {}
    for rec in recs:
        k = str(rec.get("listing_key") or "").strip()
        ag = str(rec.get("agent_name") or "").strip()
        if not k or k.startswith("test:"):
            continue
        d.setdefault(k, [])
        if ag and ag not in d[k]:
            d[k].append(ag)
    return d


def _parse_ddmmyyyy(s):
    """פענוח 'dd/mm/yyyy' (וגם dd-mm-yyyy / yyyy-mm-dd) לתאריך; None אם נכשל.
    מקביל ל-parseDate_ ב-Apps Script עבור גבולות from/to של getRaw_."""
    s = str(s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", s)
    if m:
        try:
            return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except Exception:
            return None
    m = re.match(r"^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return None


def _fetch_raw_tab(table, frm, to):
    """שורות טאב במבנה של getRaw_ מה-Apps Script: dicts עם המפתחות המקוריים
    + _date_key (dd/mm/yyyy). הסינון לפי עמודת received_at (תאריך-בלבד) שחושבה
    ע"י parseDate_ בזמן הכתיבה — אותה סמנטיקה: שורות בלי תאריך תקין לא מוחזרות."""
    d_from = _parse_ddmmyyyy(frm)
    d_to = _parse_ddmmyyyy(to)
    conds = ["received_at.not.is.null"]
    if d_from:
        conds.append("received_at.gte." + d_from.isoformat())
    if d_to:
        conds.append("received_at.lte." + d_to.isoformat())
    # PostgREST: כמה תנאים על אותה עמודה — דרך פרמטר and=(...)
    recs = _get_all(table, "received_at,raw", {"and": "(" + ",".join(conds) + ")"})
    rows = []
    for rec in recs:
        raw = rec.get("raw")
        if not isinstance(raw, dict) or not raw:
            continue
        d = rec.get("received_at")
        try:
            dd = _dt.date.fromisoformat(str(d))
        except Exception:
            continue
        obj = dict(raw)
        obj["_date_key"] = f"{dd.day:02d}/{dd.month:02d}/{dd.year}"
        rows.append(obj)
    return rows


def fetch_calls_rows(frm="01/01/2020", to="31/12/2099"):
    """'שיחות' — זהה 1:1 ל-getRaw_('שיחות', from, to)."""
    return _fetch_raw_tab("calls", frm, to)


def fetch_signatures_rows(frm="01/01/2020", to="31/12/2099"):
    """'חתימות' — זהה 1:1 ל-getRaw_('חתימות', from, to)."""
    return _fetch_raw_tab("signatures", frm, to)


def fetch_buyers_rows():
    """'קונים' — אותו מבנה בדיוק כמו listbuyers מה-Apps Script:
    [{row, date, name, phone, budget, summary, agent, agent_phone, search}, ...]
    ממוין לפי מספר שורה בגיליון."""
    recs = _get_all("buyers", "sheet_row,raw",
                    {"order": "sheet_row.asc"})
    rows = []
    for rec in recs:
        raw = rec.get("raw")
        if not isinstance(raw, dict):
            continue
        obj = dict(raw)
        obj["row"] = rec.get("sheet_row")
        rows.append(obj)
    return rows


_BUYER_KEYS = ("date", "name", "phone", "budget", "summary", "agent", "agent_phone", "search")
# 01/10: שדות עזר שנשמרים ב-raw בעדכון (לא חלק ממבנה listbuyers) — budget_day = יום החתימה שממנה
# נלקח התקציב; בלעדיו כל סבב (ייבוא/לולאה/פיירברי) "מעדכן" שוב ודורס עריכה ידנית של הסוכן
_BUYER_EXTRA_KEYS = ("budget_day",)

def buyers_insert(raw):
    """קונה חדש — כתיבה ישירה (23/08: הקונים מוזנים רק מהאפליקציה; הגיליון קפא).
    sheet_row = הגבוה ביותר + 1 (ממשיך את המספור הקיים); על התנגשות ייחודיות (409)
    ניסיון חוזר עד 3 פעמים. מחזיר את מספר השורה. raw תמיד עם 8 המפתחות (מבנה listbuyers)."""
    rec = {k: str(raw.get(k, "") if raw.get(k) is not None else "") for k in _BUYER_KEYS}
    last_err = None
    for _attempt in range(3):
        g = requests.get(SUPABASE_URL + "/rest/v1/buyers", headers=_headers(),
                         params={"select": "sheet_row", "office_id": "eq." + SB_OFFICE_ID,
                                 "order": "sheet_row.desc", "limit": "1"}, timeout=_TIMEOUT)
        g.raise_for_status()
        top = g.json() or []
        row = int(top[0]["sheet_row"]) + 1 if top else 2   # שורה 1 = כותרות בגיליון
        r = requests.post(SUPABASE_URL + "/rest/v1/buyers",
                          headers={**_headers(), "Prefer": "return=minimal"},
                          json=[{"office_id": SB_OFFICE_ID, "sheet_row": row, "raw": rec,
                                 "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}],
                          timeout=_TIMEOUT)
        if r.status_code == 409:
            last_err = "conflict on row %s" % row
            continue
        r.raise_for_status()
        return row
    raise RuntimeError("buyers_insert: %s" % last_err)


def buyers_update(row, fields):
    """עדכון שדות בקונה קיים (לפי sheet_row): ממזג לתוך raw ו-PATCH. שורה לא קיימת → False."""
    row = int(row)
    g = requests.get(SUPABASE_URL + "/rest/v1/buyers", headers=_headers(),
                     params={"select": "raw", "office_id": "eq." + SB_OFFICE_ID,
                             "sheet_row": "eq.%d" % row, "limit": "1"}, timeout=_TIMEOUT)
    g.raise_for_status()
    cur = g.json() or []
    if not cur:
        return False
    raw = dict(cur[0].get("raw") or {})
    for k, v in (fields or {}).items():
        if (k in _BUYER_KEYS or k in _BUYER_EXTRA_KEYS) and v is not None:
            raw[k] = str(v)
    r = requests.patch(SUPABASE_URL + "/rest/v1/buyers",
                       headers={**_headers(), "Prefer": "return=minimal"},
                       params={"office_id": "eq." + SB_OFFICE_ID, "sheet_row": "eq.%d" % row},
                       json={"raw": raw, "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
                       timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def buyers_delete(row):
    """מחיקת קונה — RPC buyers_delete_row הקיים (מוחק ומזיז את השורות שאחריו, כמו בגיליון)."""
    r = requests.post(SUPABASE_URL + "/rest/v1/rpc/buyers_delete_row", headers=_headers(),
                      json={"p_office": SB_OFFICE_ID, "p_row": int(row)}, timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def fetch_excl_rows():
    """'בלעדויות חיצוניות' — זהה 1:1 ל-getRaw_ (כולל _date_key). מודעה שירדה מפרסום
    ביד2 (raw.delisted_at, מסומנת רק בסריקה מלאה) לא מוזרמת לאפליקציה — נשארת ב-DB
    (החלטת אייל 09/09: סנכרון מלא, בלי למחוק היסטוריה)."""
    rows = _fetch_raw_tab("external_exclusives", "01/01/2020", "31/12/2099")
    # 28/09 (אייל: "למה אני רואה בשת\"פ את חיפה"): אותה רשימת ערים סגורה כמו בנכס נולד —
    # הקריות + קרית חיים מזרחית/מערבית; חיפה (כרמל/נווה שאנן…) ונשר/חריש/טירת כרמל נשארים ב-DB בלבד.
    return [r for r in rows
            if delisted_visible(r.get("delisted_at"))
            and krayot_city_ok(r.get("city"), " ".join(str(r.get(k) or "") for k in ("neighborhood", "street", "city")))]


def signatures_delete(event_id="", received_at="", client_name=""):
    """מחיקת שורת חתימה מהמראה (טבלת signatures) — לפי event_id, או לקוח+תאריך.
    best-effort: הגיליון נשאר מקור האמת; זה רק מוריד את השורה מהקריאות מיד."""
    if not enabled():
        return False
    try:
        params = {"office_id": "eq." + SB_OFFICE_ID}
        if event_id:
            params["raw->>event_id"] = "eq." + str(event_id)
        elif client_name and received_at:
            params["raw->>client_name"] = "eq." + str(client_name)
            params["raw->>received_at"] = "eq." + str(received_at)
        else:
            return False
        r = requests.delete(SUPABASE_URL + "/rest/v1/signatures",
                            headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        return True
    except Exception:
        return False


def activity_insert(entry):
    """רשומת יומן-פעילות — כתיבה ישירה ל-activity_log (24/08: "הקטנים" עוזבים את גוגל).
    entry במבנה _log_activity: ts (epoch), name, role, phone, action, detail."""
    ts = float(entry.get("ts") or 0) or None
    iso = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).isoformat() if ts else \
        _dt.datetime.now(_dt.timezone.utc).isoformat()
    r = requests.post(SUPABASE_URL + "/rest/v1/activity_log",
                      headers={**_headers(), "Prefer": "return=minimal"},
                      json=[{"office_id": SB_OFFICE_ID, "user_name": str(entry.get("name", "") or ""),
                             "role": str(entry.get("role", "") or ""), "phone": str(entry.get("phone", "") or ""),
                             "action": str(entry.get("action", "") or ""),
                             "target": str(entry.get("detail", "") or ""), "ts": iso}],
                      timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def fetch_activity_today(t0_epoch):
    """רשומות activity_log מ-t0 (epoch) — במבנה שמסך הפעילות מצפה לו (name/detail/ts-epoch)."""
    iso = _dt.datetime.fromtimestamp(float(t0_epoch), _dt.timezone.utc).isoformat()
    recs = _get_all("activity_log", "user_name,role,phone,action,target,ts",
                    {"and": "(ts.gte." + iso + ")", "order": "ts.desc"})
    out = []
    for rec in recs:
        try:
            ep = _dt.datetime.fromisoformat(str(rec.get("ts"))).timestamp()
        except Exception:
            continue
        out.append({"ts": float(ep), "name": rec.get("user_name") or "", "role": rec.get("role") or "",
                    "phone": rec.get("phone") or "", "action": rec.get("action") or "",
                    "detail": rec.get("target") or ""})
    return out


def hidden_add(event_id):
    """הסתרת שיחה — כתיבה ישירה ל-hidden_calls (ignore-duplicates: הסתרה חוזרת לא מכפילה)."""
    r = requests.post(SUPABASE_URL + "/rest/v1/hidden_calls",
                      headers={**_headers(), "Prefer": "resolution=ignore-duplicates"},
                      params={"on_conflict": "office_id,event_id"},
                      json=[{"office_id": SB_OFFICE_ID, "event_id": str(event_id)}],
                      timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def hidden_remove(event_id):
    """שחזור שיחה מוסתרת — מחיקה מ-hidden_calls."""
    r = requests.delete(SUPABASE_URL + "/rest/v1/hidden_calls", headers=_headers(),
                        params={"office_id": "eq." + SB_OFFICE_ID,
                                "event_id": "eq." + str(event_id)},
                        timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def newborn_contact_add(listing_key, agent_name, addr=""):
    """רישום "כבר פנו" — כתיבה ישירה ל-newborn_contacts (ignore-duplicates)."""
    r = requests.post(SUPABASE_URL + "/rest/v1/newborn_contacts",
                      headers={**_headers(), "Prefer": "resolution=ignore-duplicates"},
                      params={"on_conflict": "office_id,listing_key,agent_name"},
                      json=[{"office_id": SB_OFFICE_ID, "listing_key": str(listing_key),
                             "agent_name": str(agent_name or ""), "addr": str(addr or "")}],
                      timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def newborn_upsert_row(source_key, rec):
    """מודעת נכס-נולד מ-yad2 ingest — upsert לפי (office_id, source_key), אותה קונבנציה
    כמו sbNewbornUpsert_ ב-Apps Script (החפיפה עם הצינור הישן מתאחדת במפתח)."""
    row = {"office_id": SB_OFFICE_ID, "source_key": source_key,
           "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    for k in ("pid", "owner_name", "owner_phone", "street", "city", "price",
              "description", "link", "notes", "lister", "created_at_source", "raw"):
        if k in rec:
            row[k] = rec[k]
    r = requests.post(SUPABASE_URL + "/rest/v1/newborn_listings",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                      params={"on_conflict": "office_id,source_key"},
                      json=[row], timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def excl_upsert_row(source_key, rec):
    """מודעת משרד-אחר (שת"פ) מ-yad2 ingest — upsert ל-external_exclusives."""
    row = {"office_id": SB_OFFICE_ID, "source_key": source_key,
           "event_id": rec.get("event_id", ""), "street": rec.get("street", ""),
           "dest": rec.get("dest", ""), "link": rec.get("link", ""),
           "price": rec.get("price", ""),
           "received_at": _dt.date.today().isoformat(), "raw": rec.get("raw") or {},
           "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    r = requests.post(SUPABASE_URL + "/rest/v1/external_exclusives",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                      params={"on_conflict": "office_id,source_key"},
                      json=[row], timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def _upsert_bulk(table, rows, key_field="source_key", chunk=100, single=None):
    """upsert של הרבה שורות בקריאות מעטות (15/09: ה-ingest של יד2 עשה POST לכל שורה —
    200 שורות = 200 סיבובי-רשת = ~50ש׳ למנה, ולכן הסורק הספיק להעביר מנה אחת לסריקה).
    PostgREST דורש אותן עמודות בכל השורות ואוסר על אותו מפתח פעמיים בקריאה אחת —
    לכן: דדופ לפי המפתח (האחרון גובר) וסדר עמודות אחיד. כשל של מנה → נפילה לשורה-שורה
    (single) כדי ששורה אחת פגומה לא תפיל 99 תקינות. מחזיר כמה שורות נכתבו."""
    if not rows:
        return 0
    seen = {}
    for r in rows:
        seen[str(r.get(key_field, ""))] = r          # האחרון גובר — כמו בקריאות הבודדות ברצף
    rows = list(seen.values())
    n = 0
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        try:
            r = requests.post(SUPABASE_URL + "/rest/v1/" + table,
                              headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                              params={"on_conflict": "office_id," + key_field},
                              json=part, timeout=max(_TIMEOUT, 60))
            r.raise_for_status()
            n += len(part)
        except Exception:
            if not single:
                raise
            for row in part:                          # נפילה: שורה-שורה, שגיאה בודדת לא עוצרת את השאר
                try:
                    single(row)
                    n += 1
                except Exception:
                    pass
    return n


def _newborn_row(source_key, rec):
    row = {"office_id": SB_OFFICE_ID, "source_key": source_key,
           "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    for k in ("pid", "owner_name", "owner_phone", "street", "city", "price",
              "description", "link", "notes", "lister", "created_at_source", "raw"):
        if k in rec:
            row[k] = rec[k]
    return row


def newborn_upsert_rows(items):
    """items = [(source_key, rec)] — כמו newborn_upsert_row, במנות של 100 (ראה _upsert_bulk)."""
    rows = [_newborn_row(sk, rec) for sk, rec in items]
    keys = set()
    for r in rows:
        keys |= set(r.keys())
    for r in rows:                                    # עמודות אחידות — דרישת PostgREST ל-bulk
        for k in keys:
            r.setdefault(k, None)
    def _single(row):
        r = requests.post(SUPABASE_URL + "/rest/v1/newborn_listings",
                          headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                          params={"on_conflict": "office_id,source_key"}, json=[row], timeout=_TIMEOUT)
        r.raise_for_status()
    return _upsert_bulk("newborn_listings", rows, single=_single)


def _excl_row(source_key, rec):
    return {"office_id": SB_OFFICE_ID, "source_key": source_key,
            "event_id": rec.get("event_id", ""), "street": rec.get("street", ""),
            "dest": rec.get("dest", ""), "link": rec.get("link", ""),
            "price": rec.get("price", ""),
            "received_at": _dt.date.today().isoformat(), "raw": rec.get("raw") or {},
            "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}


def excl_upsert_rows(items):
    """items = [(source_key, rec)] — כמו excl_upsert_row, במנות של 100."""
    rows = [_excl_row(sk, rec) for sk, rec in items]
    def _single(row):
        r = requests.post(SUPABASE_URL + "/rest/v1/external_exclusives",
                          headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                          params={"on_conflict": "office_id,source_key"}, json=[row], timeout=_TIMEOUT)
        r.raise_for_status()
    return _upsert_bulk("external_exclusives", rows, single=_single)


def excl_delete_keys(source_keys):
    """מחיקת שורות שת"פ לפי source_key (ריפוי עצמי: נכסי הסניפים שלנו שנכנסו לשת"פ
    כאנונימיים לפני תיקון זיהוי המשרד, 09/09). מחזיר כמה בקשות הצליחו."""
    keys = [k for k in (source_keys or []) if k and not k.endswith("y2x:")]
    if not (enabled() and keys):
        return 0
    n = 0
    for i in range(0, len(keys), 50):
        chunk = keys[i:i + 50]
        try:
            r = requests.delete(SUPABASE_URL + "/rest/v1/external_exclusives", headers=_headers(),
                                params={"office_id": "eq." + SB_OFFICE_ID,
                                        "source_key": "in.(" + ",".join('"%s"' % k for k in chunk) + ")"},
                                timeout=_TIMEOUT)
            r.raise_for_status()
            n += 1
        except Exception:
            continue
    return n


def avatar_save(phone, img_b64):
    """תמונת פרופיל (base64 JPEG אחרי ההקטנה) → טבלת avatars — שורדת deploy
    (הדיסק של Render מתאפס בכל פריסה; התגלה חי 01/09). best-effort."""
    if not (enabled() and phone and img_b64):
        return False
    try:
        r = requests.post(SUPABASE_URL + "/rest/v1/avatars?on_conflict=office_id,phone",
                          headers={**_headers(), "Content-Type": "application/json",
                                   "Prefer": "resolution=merge-duplicates"},
                          json={"office_id": SB_OFFICE_ID, "phone": str(phone)[-9:], "img": img_b64,
                                "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
                          timeout=15)
        r.raise_for_status()
        return True
    except Exception:
        return False


def avatar_phones(phones):
    """אילו מהמספרים (9 ספרות) יש להם תמונה ב-avatars — שאילתה אחת. None = לא ידוע (כשל)."""
    ps = []
    for p in phones or []:
        d = "".join(ch for ch in str(p or "") if ch.isdigit())[-9:]
        if d and d not in ps:
            ps.append(d)
    if not ps:
        return set()
    if not enabled():
        return None
    try:
        r = requests.get(SUPABASE_URL + "/rest/v1/avatars", headers=_headers(),
                         params={"select": "phone", "office_id": "eq." + SB_OFFICE_ID,
                                 "phone": "in.(" + ",".join(ps) + ")"},
                         timeout=10)
        r.raise_for_status()
        return {str(x.get("phone") or "") for x in (r.json() or [])}
    except Exception:
        return None


def avatar_get(phone):
    """base64 של תמונת הפרופיל מ-Supabase, או '' — fallback כשהדיסק התאפס."""
    if not (enabled() and phone):
        return ""
    try:
        r = requests.get(SUPABASE_URL + "/rest/v1/avatars",
                         headers=_headers(),
                         params={"select": "img", "office_id": "eq." + SB_OFFICE_ID,
                                 "phone": "eq." + str(phone)[-9:], "limit": "1"},
                         timeout=10)
        r.raise_for_status()
        rows = r.json() or []
        return str(rows[0].get("img") or "") if rows else ""
    except Exception:
        return ""


def newborn_meta(source_keys):
    """'נוצר בתאריך' + 'נראה לראשונה' הקיימים לכל source_key (ingest יד2): לשימור שעה שכבר נקבעה,
    ולשימור 'נראה לראשונה' שלעולם אינו משתנה (26/09). מחזיר {source_key: {"d":..., "fs":...}}."""
    out = {}
    if not (enabled() and source_keys):
        return out
    for i in range(0, len(source_keys), 100):
        chunk = source_keys[i:i + 100]
        try:
            r = requests.get(SUPABASE_URL + "/rest/v1/newborn_listings", headers=_headers(),
                             params={"select": "source_key,d:raw->>נוצר בתאריך,fs:raw->>נראה לראשונה",
                                     "office_id": "eq." + SB_OFFICE_ID,
                                     "source_key": "in.(" + ",".join('"%s"' % k for k in chunk) + ")"},
                             timeout=_TIMEOUT)
            r.raise_for_status()
            for rec in (r.json() or []):
                out[str(rec.get("source_key") or "")] = {"d": str(rec.get("d") or ""), "fs": str(rec.get("fs") or "")}
        except Exception:
            continue   # best-effort: בלי שעה קיימת פשוט לא משמרים
    return out


def newborn_dates(source_keys):
    """תאימות: {source_key: 'נוצר בתאריך'} — ראה newborn_meta."""
    return {k: v.get("d", "") for k, v in newborn_meta(source_keys).items()}


def mark_delisted(table, source_keys, stamp):
    """תווית "ירד מפרסום" (החלטת אייל 30/08 — לא מוחקים): raw.delisted_at=stamp.
    בתוך ה-jsonb — בלי מיגרציית סכימה. מחזיר כמה שורות עודכנו."""
    n = 0
    for i in range(0, len(source_keys), 50):
        chunk = source_keys[i:i + 50]
        g = requests.get(SUPABASE_URL + "/rest/v1/" + table, headers=_headers(),
                         params={"select": "id,raw", "office_id": "eq." + SB_OFFICE_ID,
                                 "source_key": "in.(" + ",".join('"%s"' % k for k in chunk) + ")"},
                         timeout=_TIMEOUT)
        g.raise_for_status()
        for rec in (g.json() or []):
            raw = dict(rec.get("raw") or {})
            if raw.get("delisted_at"):
                continue   # כבר מסומן — לא דורסים את התאריך המקורי
            raw["delisted_at"] = stamp
            r = requests.patch(SUPABASE_URL + "/rest/v1/" + table, headers=_headers(),
                               params={"id": "eq.%s" % rec["id"]},
                               json={"raw": raw,
                                     "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat()},
                               timeout=_TIMEOUT)
            r.raise_for_status()
            n += 1
    return n


def props_seen_recently(raw, now_ts=None, hours=None):
    """[DELIST-GUARD 07/10] הסורק שלח את המודעה כפעילה ב-X השעות האחרונות (ברירת מחדל 48)?
    אייל: אהוד מנור 13 נשלח כפעיל ב-14:41 וסומן 'ירד מפרסום' באותו יום, והוא באוויר — 22 כאלה
    ב-06-07/10. דיווח ירידה שסותר שליחה טרייה = כנראה טעות הסורק → לא מסמנים (ורושמים).
    env PROPS_DELIST_GUARD_HOURS (0 = כבוי)."""
    try:
        h = float(os.environ.get("PROPS_DELIST_GUARD_HOURS", "48")) if hours is None else float(hours)
    except ValueError:
        h = 48.0
    if h <= 0 or not isinstance(raw, dict):
        return False
    import time as _t
    now_ts = _t.time() if now_ts is None else now_ts
    last = _il_epoch(raw.get("_y2_ingested"))
    return bool(last) and now_ts - last < h * 3600

def mark_props_delisted(tokens, stamp, guarded=None):
    """תווית "ירד מפרסום" לנכסי המשרד (טבלת properties) לפי טוקן יד2 ('מספר מודעה') —
    לאירועי ירידה שמגיעים מהסורק במנה נפרדת, בלי שורות הסניף (05/10). אותו מבנה כמו
    merge_office_props: raw['ירד מפרסום']=stamp + סטטוס. שורה שכבר מסומנת לא נדרסת;
    מודעה שחוזרת בסריקה מוחלפת בגרסה הטרייה ב-merge (בלי התווית). מחזיר כמה עודכנו."""
    toks = set(str(t).strip() for t in (tokens or ()) if str(t).strip())
    if not enabled() or not toks:
        return 0
    current = _get_all("properties", "sheet_row,raw", {"order": "sheet_row.asc"})
    n = 0
    for rec in current:
        raw = rec.get("raw")
        if not isinstance(raw, dict) or raw.get("ירד מפרסום"):
            continue
        if str(raw.get("מספר מודעה") or "").strip() not in toks:
            continue
        if props_seen_recently(raw):   # [DELIST-GUARD] נשלח כפעיל לאחרונה — לא מסמנים
            if guarded is not None:
                guarded.append(str(raw.get("מספר מודעה") or "").strip())
            continue
        raw = dict(raw)
        raw["ירד מפרסום"] = stamp
        raw["סטטוס"] = "ירד מפרסום"
        r = requests.patch(SUPABASE_URL + "/rest/v1/properties",
                           headers={**_headers(), "Content-Type": "application/json"},
                           params={"office_id": "eq." + SB_OFFICE_ID, "sheet_row": "eq.%s" % rec.get("sheet_row")},
                           json={"raw": raw}, timeout=_TIMEOUT)
        r.raise_for_status()
        n += 1
    return n


def signature_record(source_key, received_iso, raw):
    """שורת signatures במבנה הטבלה — משותף ל-webhook ולייבוא ההיסטוריה (CRM-1)."""
    return {"office_id": SB_OFFICE_ID, "source_key": source_key,
            "event_id": raw.get("event_id", ""), "deal_type": raw.get("deal_type", ""),
            "agent": raw.get("agent", ""), "client_name": raw.get("client_name", ""),
            "address": raw.get("address", ""), "city": raw.get("city", ""),
            "commission_pct": raw.get("commission_pct", ""), "notes": raw.get("notes", ""),
            "received_at": received_iso, "raw": raw}


def upsert_signature_row(source_key, received_iso, raw):
    """שורת חתימה מ-webhook פיירברי — upsert לפי (office_id, source_key):
    הטריגר "נוצרה או עודכנה" מעדכן שורה קיימת במקום להכפיל; retry לא מכפיל.
    raw = במבנה getRaw_ (המפתחות ש-fetch_signatures_rows מחזיר 1:1)."""
    row = signature_record(source_key, received_iso, raw)
    r = requests.post(SUPABASE_URL + "/rest/v1/signatures",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                      params={"on_conflict": "office_id,source_key"},
                      json=[row], timeout=15)
    r.raise_for_status()
    return True




def signdoc_save(doc):
    """upsert מסמך חתימה לפי token (טבלת sign_docs). doc במבנה של savesigndoc:
    doc_token, event_id, status, header, docs (מחרוזת JSON), signature, signed_at."""
    if not enabled():
        return False
    token = str(doc.get("doc_token") or "").strip()
    if not token:
        return False
    try:
        import json as _json
        try:
            docs_j = _json.loads(doc.get("docs") or "[]")
        except Exception:
            docs_j = []
        row = {"office_id": SB_OFFICE_ID, "token": token,
               "event_id": str(doc.get("event_id") or ""),
               "status": str(doc.get("status") or "pending"),
               "header": str(doc.get("header") or ""), "docs": docs_j,
               "signature": str(doc.get("signature") or ""),
               "signed_at": str(doc.get("signed_at") or "")}
        r = requests.post(SUPABASE_URL + "/rest/v1/sign_docs",
                          headers={**_headers(),
                                   "Prefer": "resolution=merge-duplicates,return=minimal"},
                          params={"on_conflict": "token"}, json=[row], timeout=15)
        r.raise_for_status()
        return True
    except Exception:
        return False


def signdoc_get(token):
    """מסמך חתימה לפי token → dict במבנה doc של getsigndoc (docs כמחרוזת JSON), או None."""
    if not enabled():
        return None
    try:
        r = requests.get(SUPABASE_URL + "/rest/v1/sign_docs", headers=_headers(),
                         params={"office_id": "eq." + SB_OFFICE_ID, "token": "eq." + str(token or ""),
                                 "select": "token,event_id,status,header,docs,signature,signed_at",
                                 "limit": "1"},
                         timeout=12)
        r.raise_for_status()
        rows = r.json() or []
        if not rows:
            return None
        import json as _json
        rec = rows[0]
        return {"doc_token": rec.get("token", ""), "event_id": rec.get("event_id", ""),
                "status": rec.get("status", ""), "header": rec.get("header", ""),
                "docs": _json.dumps(rec.get("docs") or [], ensure_ascii=False),
                "signature": rec.get("signature", ""), "signed_at": rec.get("signed_at", "")}
    except Exception:
        return None


def signdoc_update(token, fields):
    """עדכון שדות במסמך קיים לפי token. True=עודכן (נמצא); False=לא נמצא/כשל
    (הקורא נופל חזרה ל-Apps Script — מסמכים ישנים חיים רק בגיליון)."""
    if not enabled():
        return False
    try:
        body = {}
        for k in ("event_id", "status", "header", "signature", "signed_at"):
            if k in fields:
                body[k] = str(fields.get(k) or "")
        if not body:
            return False
        r = requests.patch(SUPABASE_URL + "/rest/v1/sign_docs",
                           headers={**_headers(), "Prefer": "return=representation"},
                           params={"office_id": "eq." + SB_OFFICE_ID, "token": "eq." + str(token or "")},
                           json=body, timeout=12)
        r.raise_for_status()
        rows = r.json() if r.text else []
        return bool(rows)
    except Exception:
        return False


def signdoc_times():
    """{token: signed_at} לכל המסמכים החתומים — שעת החתימה האמיתית לרשימת החתימות."""
    if not enabled():
        return {}
    try:
        recs = _get_all("sign_docs", "token,signed_at", {"status": "eq.signed"})
        return {r.get("token", ""): r.get("signed_at", "") for r in recs if r.get("token")}
    except Exception:
        return {}


def insert_invoice_row(row):
    """הוספת חשבונית בודדת (קליטה מ-Fireberry). כפילות row_hash נבלעת בשקט.
    מחזיר True רק כשנוספה שורה חדשה (01/10: שליחת החשבונית ללקוח — לא פעמיים על ניסיון חוזר)."""
    r = requests.post(SUPABASE_URL + "/rest/v1/invoices",
                      headers={**_headers(), "Prefer": "resolution=ignore-duplicates,return=representation"},
                      params={"on_conflict": "row_hash"},
                      json=[{**row, "office_id": SB_OFFICE_ID}], timeout=_TIMEOUT)
    r.raise_for_status()
    try:
        return bool(r.json())
    except Exception:
        return True


# ── [CRM-1 19/10] זרמים ישירים (Make / תוכנת חשבוניות) — צל עד הניתוק מפיירברי + תמלול מלא ──
def shadow_upsert(stream, source_key, received_iso, raw):
    """שורה בטבלת הצל (ingest_shadow) — retry לא מכפיל (on_conflict על office+stream+key)."""
    row = {"office_id": SB_OFFICE_ID, "stream": stream, "source_key": source_key,
           "received_at": received_iso or None, "raw": raw}
    r = requests.post(SUPABASE_URL + "/rest/v1/ingest_shadow",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "office_id,stream,source_key"},
                      json=[row], timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def transcript_upsert(source_key, event_id, transcript, recording_url):
    """תמלול מלא + קישור הקלטה (call_transcripts). בלי שניהם — לא כותבים (False)."""
    if not (transcript or recording_url):
        return False
    import datetime as _dt_t
    row = {"office_id": SB_OFFICE_ID, "source_key": source_key, "event_id": event_id,
           "transcript": transcript or None, "recording_url": recording_url or None,
           "updated_at": _dt_t.datetime.now(_dt_t.timezone.utc).isoformat()}
    r = requests.post(SUPABASE_URL + "/rest/v1/call_transcripts",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "office_id,source_key"},
                      json=[row], timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def call_record(source_key, received_iso, raw):
    """שורת calls — אותן עמודות ש-_sbCallRecord_ ב-Apps Script כותב (משותף לזרם הישיר ולייבוא)."""
    import datetime as _dt_c
    g = lambda k: str(raw.get(k, "") or "")
    return {"office_id": SB_OFFICE_ID, "source_key": source_key, "event_id": g("event_id"),
            "status": g("status"), "agent": g("agent"), "agent_phone": g("agent_phone"),
            "caller_phone": g("caller_phone"), "duration_sec": g("duration_sec"),
            "transcript_summary": g("transcript_summary"), "received_at": received_iso,
            "raw": raw, "updated_at": _dt_c.datetime.now(_dt_c.timezone.utc).isoformat()}


def call_upsert_direct(source_key, received_iso, raw):
    """שיחה ישירות לטבלת calls."""
    row = call_record(source_key, received_iso, raw)
    r = requests.post(SUPABASE_URL + "/rest/v1/calls",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "office_id,source_key"},
                      json=[row], timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def insert_invoice_rows(rows):
    """[CRM-1] ייבוא היסטוריה: הרבה חשבוניות, כפילות row_hash נבלעת. מחזיר כמה נשלחו."""
    n = 0
    for i in range(0, len(rows), 100):
        part = [{**r, "office_id": SB_OFFICE_ID} for r in rows[i:i + 100]]
        r = requests.post(SUPABASE_URL + "/rest/v1/invoices",
                          headers={**_headers(), "Prefer": "resolution=ignore-duplicates,return=minimal"},
                          params={"on_conflict": "row_hash"}, json=part, timeout=max(_TIMEOUT, 60))
        r.raise_for_status()
        n += len(part)
    return n


# ── [CRM-2 19/10] שכבת העריכות של מסכי ה-CRM ──
def crm_overrides_fetch(module):
    """{record_key: fields} — העריכות שנשמרו ב-CRM למודול."""
    recs = _get_all("crm_overrides", "record_key,fields", {"module": "eq." + module})
    return {r.get("record_key"): dict(r.get("fields") or {}) for r in recs if r.get("record_key")}


def crm_override_upsert(module, key, fields, by):
    """מיזוג שדות חדשים מעל העריכות הקיימות של הרשומה (שדה ריק = נשמר ריק, לא נמחק)."""
    import datetime as _dt_o
    merged = dict(crm_overrides_fetch(module).get(key) or {})
    merged.update(fields or {})
    row = {"office_id": SB_OFFICE_ID, "module": module, "record_key": key, "fields": merged,
           "updated_at": _dt_o.datetime.now(_dt_o.timezone.utc).isoformat(), "updated_by": by or ""}
    r = requests.post(SUPABASE_URL + "/rest/v1/crm_overrides",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "office_id,module,record_key"}, json=[row], timeout=_TIMEOUT)
    r.raise_for_status()
    return merged


def transcript_get(source_key):
    """התמלול המלא + קישור ההקלטה של שיחה (call_transcripts), או None."""
    recs = _get_all("call_transcripts", "source_key,transcript,recording_url", {"source_key": "eq." + str(source_key)})
    return recs[0] if recs else None


# ── [TEAM 19/10] אנשי צוות — מחליף את גיליון 'אנשי קשר' (CONTACTS_SOURCE=supabase) ──
_TEAM_FIELDS = ("name", "phone", "vphone", "license", "email", "active", "sort")


def team_fetch(active_only=False):
    """כל אנשי הצוות, ממוינים לפי sort ואז שם."""
    recs = _get_all("team_contacts", "id,name,phone,vphone,license,email,active,sort,updated_at,updated_by")
    if active_only:
        recs = [r for r in recs if r.get("active")]
    return sorted(recs, key=lambda r: (int(r.get("sort") or 0), str(r.get("name") or "")))


def team_upsert(rows, by):
    """הוספה/עדכון לפי שם (ייבוא חד-פעמי מהגיליון וכפתור '+ חדש')."""
    import datetime as _dt_t
    now = _dt_t.datetime.now(_dt_t.timezone.utc).isoformat()
    body = [{**{k: r[k] for k in _TEAM_FIELDS if k in r}, "office_id": SB_OFFICE_ID, "updated_at": now, "updated_by": by or ""}
            for r in rows if str(r.get("name") or "").strip()]
    if not body:
        return 0
    r = requests.post(SUPABASE_URL + "/rest/v1/team_contacts",
                      headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
                      params={"on_conflict": "office_id,name"}, json=body, timeout=max(_TIMEOUT, 30))
    r.raise_for_status()
    return len(body)


def team_update(row_id, fields, by):
    """עדכון שורה לפי id (כולל שינוי שם)."""
    import datetime as _dt_u
    body = {k: fields[k] for k in _TEAM_FIELDS if k in fields}
    body.update({"updated_at": _dt_u.datetime.now(_dt_u.timezone.utc).isoformat(), "updated_by": by or ""})
    r = requests.patch(SUPABASE_URL + "/rest/v1/team_contacts",
                       headers={**_headers(), "Prefer": "return=minimal"},
                       params={"id": "eq." + str(row_id), "office_id": "eq." + SB_OFFICE_ID}, json=body, timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def fetch_shadow(stream, since_iso, until_iso=None):
    """שורות הצל של זרם מאז since_iso (ועד until_iso, אם ניתן) — raw + source_key + received_at."""
    conds = ["received_at.gte." + since_iso] + (["received_at.lte." + until_iso] if until_iso else [])
    recs = _get_all("ingest_shadow", "source_key,received_at,raw",
                    {"stream": "eq." + stream, "and": "(" + ",".join(conds) + ")"})
    return [dict(r.get("raw") or {}, _source_key=r.get("source_key"), _received_at=r.get("received_at"))
            for r in recs]


def fetch_newborn_raw_all():
    """[01/10] כל שורות נכס נולד (raw) בלי סינוני התצוגה (ערים/השכרות) — לבדיקת "קונה שמפרסם נכס"."""
    return [rec.get("raw") for rec in _get_all("newborn_listings", "source_key,raw")
            if isinstance(rec.get("raw"), dict) and rec.get("raw")
            and not str(rec.get("source_key") or "").startswith("test:")]


def fetch_invoices_rows(q="", limit=400):
    """חשבוניות (הנהלת חשבונות). בלי q — האחרונות; עם q — חיפוש שם (name_key
    ממוין-טוקנים, ilike לכל טוקן ב-OR) או טלפון (ספרות → phone9)."""
    sel = ("client_name,name_key,phone,phone9,doc_type,doc_num,charge_line,"
           "created_at,source,link,amount")
    params = {"select": sel, "office_id": "eq." + SB_OFFICE_ID,
              "order": "created_at.desc.nullslast", "limit": str(int(limit))}
    q = str(q or "").strip()
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        ors = ["name_key.ilike.*%s*" % t.replace(",", "").replace("(", "").replace(")", "")
               for t in q.split() if not t.isdigit()]
        if digits and len(digits) >= 4:
            ors.append("phone9.like.*%s*" % digits[-9:])
        if ors:
            params["or"] = "(" + ",".join(ors) + ")"
    r = requests.get(SUPABASE_URL + "/rest/v1/invoices", headers=_headers(),
                     params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json() or []


def office_deal(raw):
    """[DEALS 13/10] סוג העסקה של נכס משרד: 'מכירה' (ברירת מחדל — כל השורות הקיימות) / 'השכרה' / 'מסחרי'."""
    v = str((raw or {}).get("סוג עסקה") or "").strip()
    if not v or v in ("מכירה", "למכירה"):
        return "מכירה"
    if "שכר" in v:
        return "השכרה"
    return "מסחרי" if "מסחר" in v else v


def fetch_properties_rows(deals=("מכירה",)):
    """'נכסים במשרד' — זהה 1:1 ל-fetch_sheet_rows (dict לפי כותרות + _desc_ae),
    לפי סדר השורות בגיליון. שורות "ירד מפרסום" (תיוג יד2) לא מוזרמות לאפליקציה —
    תוויות UI לירד-מפרסום הן צעד נפרד (יומן 01/09).
    [DEALS 13/10] ברירת המחדל — מכירה בלבד: השכרה/מסחרי של סניפי Family (מהסורק מ-v13.45) לא נכנסים
    לאף צרכן קיים (חיפוש, התאמות, דוחות, מפה, אתר); מסך הנכסים מבקש אותם במפורש. deals=None = הכל."""
    recs = _get_all("properties", "sheet_row,raw", {"order": "sheet_row.asc"})
    return [rec["raw"] for rec in recs
            if isinstance(rec.get("raw"), dict) and delisted_visible(rec["raw"].get("ירד מפרסום"))
            and (deals is None or office_deal(rec["raw"]) in deals)]


# ── [STALE-PROPS 05/10] נכס שהסורק הפסיק לשלוח → "ירד מפרסום" (אייל: "3 סריקות + 24 שעות") ──────
# הרקע: נכס יורד רק באות 'ירד מפרסום' מפורש מהסורק, וזה לא נקלט עד 05/10 — נשארו נכסים מתחילת ספטמבר.
# מאז 15/09 הסורק שולח בעיקר שינויים + סבב מלא בחלקים, ולכן "לא הופיע במנה" לבדו אינו אות. הכלל:
#   (1) 3 מנות לפחות של הסניף שבהן הנכס לא הופיע (מנות בהפרש 30 דק' ומעלה = סריקות נפרדות);
#   (2) 24 שעות לפחות מאז שהסורק שלח אותו לאחרונה (_y2_ingested; אחרת _y2_first_seen; אחרת "מזמן");
#   (3) שער כיסוי: לפחות 60% מהנכסים הפעילים של הסניף הגיעו מהסורק ב-24 השעות האחרונות — הוכחה שהסבב
#       המלא באמת רץ. סורק תקוע / רק-שינויים → אף נכס לא יורד. סניף עם פחות מ-5 נכסים — לא נוגעים.
# הנכס לא נמחק: תווית 'ירד מפרסום' (3 ימים ואז נעלם); חוזר לפעיל כשהסורק שולח אותו שוב.
STALE_MISSES, STALE_HOURS, STALE_COVERAGE, STALE_MIN_BRANCH, STALE_MISS_GAP = 3, 24, 0.6, 5, 1800

def _il_epoch(s):
    """'DD/MM/YYYY[ HH:MM]' (שעון ישראל) → epoch; לא-פריס → 0."""
    m = re.match(r"^\s*(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?:[ T](\d{1,2}):(\d{2}))?", str(s or ""))
    if not m:
        return 0.0
    try:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Jerusalem")
        except Exception:
            tz = _dt.timezone(_dt.timedelta(hours=3))
        return _dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                            int(m.group(4) or 0), int(m.group(5) or 0), tzinfo=tz).timestamp()
    except Exception:
        return 0.0

def stale_office_update(branch_rows, incoming, now_ts):
    """[STALE-PROPS] branch_rows = שורות הסניף הקיימות שלא הגיעו במנה ולא מסומנות 'ירד מפרסום' (dicts
    שמתעדכנים במקום); incoming = השורות שהגיעו במנה. מעדכן מוני החמצה; מחזיר רשימת שורות שנעשו ישנות
    (הקורא מסמן אותן). פונקציה טהורה — נבדקת בלי רשת."""
    total = len(branch_rows) + len(incoming)
    if total < STALE_MIN_BRANCH:
        return []
    day = STALE_HOURS * 3600
    def _last(r):
        return _il_epoch(r.get("_y2_ingested")) or _il_epoch(r.get("_y2_first_seen"))
    recent = len(incoming) + sum(1 for r in branch_rows if now_ts - _last(r) < day)
    for r in branch_rows:   # מונה החמצות — פעם אחת לכל סריקה (מנות צמודות = אותה סריקה)
        try:
            at = float(r.get("_y2_miss_ts") or 0)
        except (TypeError, ValueError):
            at = 0.0
        if now_ts - at >= STALE_MISS_GAP:
            try:
                r["_y2_miss"] = int(r.get("_y2_miss") or 0) + 1
            except (TypeError, ValueError):
                r["_y2_miss"] = 1
            r["_y2_miss_ts"] = str(int(now_ts))
    if recent < STALE_COVERAGE * total:
        return []   # הסבב המלא לא מוכח — לא מורידים כלום
    return [r for r in branch_rows if int(r.get("_y2_miss") or 0) >= STALE_MISSES and now_ts - _last(r) >= day]

_PLACEHOLDER_AGENT_RE = re.compile(r"^(סוכן\s*\d+|משרד(\s*\d+)?)$")


def is_placeholder_agent(name):
    """שם סוכן שאינו שם אמיתי: ריק, 'סוכן 8719' (מזהה דף סוכן ביד2 בלי שם), 'משרד', '… (לא משויך)'."""
    s = str(name or "").strip()
    return (not s) or bool(_PLACEHOLDER_AGENT_RE.match(s)) or "(לא משויך)" in s


def keep_real_agents(raw_rows, current):
    """18/10 (אייל: "נעלמו המון נכסים לחי אלבז"): הסורק שולח 'סוכן 8719' כשהשם שלמד מדף
    המודעה לא זמין לו (זיכרון הסוכנים נמחק עם נתוני האתר), ודרס סוכנים אמיתיים — 60 נכסים
    נעלמו מ'שלי' ומהאתר. שורה שמגיעה עם שם-ממלא-מקום שומרת את הסוכן (וטלפון הסוכן) מהשורה
    הקיימת. ה-CRM כבר נוהג כך (isRealAgentName ב-Code.gs). מחזיר כמה שורות תוקנו."""
    by_tok = {}
    for rec in current or ():
        raw = rec.get("raw") if isinstance(rec, dict) else None
        if isinstance(raw, dict):
            by_tok[str(raw.get("מספר מודעה") or "")] = raw
    fixed = 0
    for r in raw_rows or ():
        if not is_placeholder_agent(r.get("סוכן 1")):
            continue
        ex = by_tok.get(str(r.get("מספר מודעה") or ""))
        if ex and not is_placeholder_agent(ex.get("סוכן 1")):
            r["סוכן 1"] = ex.get("סוכן 1")
            if ex.get("טלפון 1"):
                r["טלפון 1"] = ex.get("טלפון 1")
            fixed += 1
    return fixed


def merge_office_props(office_tag, raw_rows, delisted_tokens=None, stamp="", now_full="", guarded=None):
    """נכסי המשרד מיד2 (שלב ב', החלטת אייל 01/09): מחליף את שורות הסניף office_tag
    ברשימה החדשה ושומר את שאר הסניפים. שורה של הסניף שנעדרת מהסריקה: ב-delisted →
    נשארת עם תווית "ירד מפרסום"; אחרת נשארת כמו שהיא (סריקה חלקית לא מוחקת).
    שורות ללא _y2_office_id (הגיליון הישן) נמחקות בכתיבה הראשונה. מחזיר (ok, n)."""
    if not enabled() or not raw_rows:
        return False, 0, []
    office_tag = str(office_tag or "").strip()
    delisted_tokens = set(delisted_tokens or ())
    new_tokens = set(str(r.get("מספר מודעה") or "") for r in raw_rows)
    current = _get_all("properties", "sheet_row,raw", {"order": "sheet_row.asc"})
    # שער-שפיות (אייל 09/09): batch שקטן בחצי ומטה מהפעילים הקיימים של הסניף = סריקה
    # חלקית/תקלה — לא מסמנים "ירד מפרסום" (רק מעדכנים מה שהגיע); נחזור לסנכרן בסריקה שפויה.
    cur_active = sum(1 for rec in current
                     if isinstance(rec.get("raw"), dict)
                     and str(rec["raw"].get("_y2_office_id") or "").strip() == office_tag
                     and not rec["raw"].get("ירד מפרסום"))
    if delisted_tokens and cur_active >= 10 and len(raw_rows) < 0.5 * cur_active:
        delisted_tokens = set()
    # "נראה לראשונה" (אייל 09/09 — מיון מהחדש לישן + תווית 'חדש' 3 ימים): שורה קיימת שומרת
    # את החותמת המקורית שלה; שורה חדשה מקבלת imported_at מהסורק אם הגיע, אחרת את זמן הקליטה.
    first_seen = {}
    for rec in current:
        raw = rec.get("raw")
        if isinstance(raw, dict) and raw.get("_y2_first_seen"):
            first_seen[str(raw.get("מספר מודעה") or "")] = raw["_y2_first_seen"]
    # 11/09: שורה שהגיעה בלי טוקן (מפתח addr:…) — אם באותו סניף כבר יש שורת-טוקן לאותה כתובת,
    # מקפלים אותה לתוכה: שומרים טוקן/קישור/סוכן/נראה-לראשונה של הקיימת, מעדכנים מחיר ופרטים.
    def _addr_of(r):
        return (str(r.get("כתובת") or "").strip() + "|" + str(r.get("מספר בית") or "").strip()
                + "|" + str(r.get("עיר / ישוב") or "").strip())
    by_addr = {}
    for rec in current:
        raw = rec.get("raw")
        if isinstance(raw, dict) and str(raw.get("_y2_office_id") or "").strip() == office_tag \
                and not str(raw.get("מספר מודעה") or "").startswith("addr:"):
            by_addr.setdefault(_addr_of(raw), raw)
    raw_rows = list(raw_rows)
    for r in raw_rows:
        if str(r.get("מספר מודעה") or "").startswith("addr:"):
            ex = by_addr.get(_addr_of(r))
            if ex:
                r["מספר מודעה"] = ex.get("מספר מודעה")
                _lk = str(r.get("קישור") or "").strip()
                if (not _lk or _lk.rstrip("/").endswith("/item/0")) and ex.get("קישור"):
                    r["קישור"] = ex.get("קישור")
                for k in ("תמונה", "_y2_first_seen", "סוכן 1"):
                    if not str(r.get(k) or "").strip() and ex.get(k):
                        r[k] = ex.get(k)
    # שורה בלי מפתח בכלל (בלי טוקן ובלי כתובת) — לא נכתבת
    raw_rows = [r for r in raw_rows if str(r.get("מספר מודעה") or "").strip()]
    try:
        _fx = keep_real_agents(raw_rows, current)   # [AGENT-KEEP 18/10]
        if _fx:
            print(f"props merge {office_tag}: kept real agent on {_fx} rows (placeholder from scanner)", flush=True)
    except Exception:
        pass   # לעולם לא מפיל את הקליטה
    new_tokens = set(str(r.get("מספר מודעה") or "") for r in raw_rows)
    existing_tokens = set(str(rec["raw"].get("מספר מודעה") or "") for rec in current if isinstance(rec.get("raw"), dict))
    new_rows = [r for r in raw_rows if str(r.get("מספר מודעה") or "") not in existing_tokens]   # לפוש לסוכן
    for r in raw_rows:
        tok = str(r.get("מספר מודעה") or "")
        # תאריך מפורש מהסורק (imported_at) גובר — הוא האמת; בלעדיו: החותמת השמורה, ואחרת זמן הקליטה
        r["_y2_first_seen"] = r.get("_y2_first_seen") or first_seen.get(tok) or now_full or stamp
    keep = []
    for rec in current:
        raw = rec.get("raw")
        if not isinstance(raw, dict):
            continue
        tag = str(raw.get("_y2_office_id") or "").strip()
        if not tag:
            continue   # שורת הגיליון הישן — יורדת
        tok = str(raw.get("מספר מודעה") or "")
        if tok in new_tokens:
            continue   # מוחלפת בגרסה הטרייה — גם אם תויגה בעבר לסניף/תג אחר ('family' → מזהה אמיתי)
        if tag != office_tag:
            keep.append(raw)
            continue
        if tok in delisted_tokens:
            if not raw.get("ירד מפרסום") and props_seen_recently(raw):   # [DELIST-GUARD]
                if guarded is not None:
                    guarded.append(tok)
            else:
                if not raw.get("ירד מפרסום"):
                    raw["ירד מפרסום"] = stamp
                raw["סטטוס"] = "ירד מפרסום"
        keep.append(raw)
    # [STALE-PROPS 05/10] נכסי הסניף שלא הגיעו — מוני החמצה, ו"ירד מפרסום" לפי הכלל (3 סריקות + 24ש' + כיסוי)
    # ⏸ מושהה (אייל 07/10): "עד שנמצא למה הסורק מפספס — אחרת ~70 נכסים פעילים עלולים להיעלם, גם מדף הקונה".
    # הפעלה מחדש: env PROPS_STALE_DELIST=1. כבוי = לא סופרים ולא מסמנים בכלל.
    if os.environ.get("PROPS_STALE_DELIST", "0") == "1":
        try:
            import time as _time
            _absent = [r for r in keep if str(r.get("_y2_office_id") or "").strip() == office_tag
                       and not r.get("ירד מפרסום")]
            for r in stale_office_update(_absent, list(raw_rows), _time.time()):
                r["ירד מפרסום"] = stamp or _il_today().strftime("%d/%m/%Y")
                r["סטטוס"] = "ירד מפרסום"
                r["_y2_auto_delist"] = r["ירד מפרסום"]   # סימון: ירד לפי הכלל (לא אות מהסורק)
        except Exception:
            pass   # הכלל לעולם לא מפיל את הקליטה
    ok, n = replace_properties(keep + list(raw_rows))
    return ok, n, new_rows


def replace_properties(raw_rows):
    """החלפה מלאה של נכסי המשרד: מוחק את שורות המשרד ומכניס raw_rows (list של dicts גולמיים,
    כל אחד = כותרת→ערך + _desc_ae). מחזיר (ok, count). הגנה: לא מוחק אם הרשימה ריקה."""
    if not enabled():
        return False, 0
    if not raw_rows:
        return False, 0   # מניעת מחיקת כל הנכסים בטעות
    hdr = {**_headers(), "Content-Type": "application/json"}
    requests.delete(SUPABASE_URL + "/rest/v1/properties",
                    headers=hdr, params={"office_id": "eq." + SB_OFFICE_ID}, timeout=60).raise_for_status()
    recs = [{"office_id": SB_OFFICE_ID, "sheet_row": i + 2, "raw": raw}
            for i, raw in enumerate(raw_rows)]
    n = 0
    for j in range(0, len(recs), 500):
        chunk = recs[j:j + 500]
        requests.post(SUPABASE_URL + "/rest/v1/properties",
                      headers=hdr, json=chunk, timeout=90).raise_for_status()
        n += len(chunk)
    return True, n


# ── גיבוי/שחזור נכסי המשרד (אייל 11/09: "לחזור אחורה אם הסורק מפקשש") ─────────────
PROPS_SNAPSHOT_KEEP = 3   # תאריכים אחרונים של גיבוי אוטומטי

def _il_today():
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    except Exception:
        return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=3)).date()

def props_snapshot_list(limit=12):
    """הגיבויים הקיימים (בלי התוכן): [{id, taken_at, label, n}] מהחדש לישן."""
    if not enabled():
        return []
    r = requests.get(SUPABASE_URL + "/rest/v1/properties_snapshots", headers=_headers(),
                     params={"office_id": "eq." + SB_OFFICE_ID, "select": "id,taken_at,label,n",
                             "order": "taken_at.desc", "limit": str(limit)}, timeout=20)
    r.raise_for_status()
    return r.json() or []

def props_snapshot_take(label="auto"):
    """צילום כל שורות נכסי המשרד (raw) לטבלת properties_snapshots. label='auto' = לכל היותר אחד
    ביום (הראשון — המצב שלפני הסריקה הראשונה של היום); נשמרים PROPS_SNAPSHOT_KEEP התאריכים
    האחרונים. label אחר (manual / before-restore) נשמר תמיד ולא נגזם. מחזיר (id או '', n)."""
    if not enabled():
        return "", 0
    if label == "auto":
        today = _il_today().isoformat()
        r = requests.get(SUPABASE_URL + "/rest/v1/properties_snapshots", headers=_headers(),
                         params={"office_id": "eq." + SB_OFFICE_ID, "label": "eq.auto", "select": "id,taken_at",
                                 "order": "taken_at.desc", "limit": "1"}, timeout=20)
        r.raise_for_status()
        last = (r.json() or [None])[0]
        if last and str(last.get("taken_at", ""))[:10] == today:
            return "", 0   # כבר יש גיבוי אוטומטי היום
    recs = _get_all("properties", "sheet_row,raw", {"order": "sheet_row.asc"})
    rows = [rec["raw"] for rec in recs if isinstance(rec.get("raw"), dict)]
    if not rows:
        return "", 0   # אין מה לגבות (ומצב ריק לא שווה שחזור)
    hdr = {**_headers(), "Content-Type": "application/json", "Prefer": "return=representation"}
    r = requests.post(SUPABASE_URL + "/rest/v1/properties_snapshots", headers=hdr,
                      json={"office_id": SB_OFFICE_ID, "label": label, "n": len(rows), "rows": rows}, timeout=120)
    r.raise_for_status()
    sid = ((r.json() or [{}])[0] or {}).get("id", "")
    if label == "auto":
        try:   # גיזום: משאירים את PROPS_SNAPSHOT_KEEP האוטומטיים האחרונים
            ra = requests.get(SUPABASE_URL + "/rest/v1/properties_snapshots", headers=_headers(),
                              params={"office_id": "eq." + SB_OFFICE_ID, "label": "eq.auto", "select": "id",
                                      "order": "taken_at.desc"}, timeout=20)
            ra.raise_for_status()
            old = [x["id"] for x in (ra.json() or [])[PROPS_SNAPSHOT_KEEP:] if x.get("id")]
            if old:
                requests.delete(SUPABASE_URL + "/rest/v1/properties_snapshots", headers=_headers(),
                                params={"id": "in.(" + ",".join(old) + ")"}, timeout=30).raise_for_status()
        except Exception:
            pass
    return sid, len(rows)

def props_snapshot_restore(snapshot_id):
    """שחזור מלא של נכסי המשרד מגיבוי: קודם צילום 'before-restore' של המצב הנוכחי (השחזור הפיך),
    ואז replace_properties בשורות הגיבוי. מחזיר (ok, n, reason)."""
    if not enabled() or not snapshot_id:
        return False, 0, "disabled"
    r = requests.get(SUPABASE_URL + "/rest/v1/properties_snapshots", headers=_headers(),
                     params={"office_id": "eq." + SB_OFFICE_ID, "id": "eq." + str(snapshot_id),
                             "select": "id,rows,n"}, timeout=120)
    r.raise_for_status()
    snap = (r.json() or [None])[0]
    if not snap or not isinstance(snap.get("rows"), list) or not snap["rows"]:
        return False, 0, "not_found"
    try:
        props_snapshot_take("before-restore")
    except Exception:
        return False, 0, "backup_failed"   # בלי צילום של המצב הנוכחי לא משחזרים
    ok, n = replace_properties(snap["rows"])
    return ok, n, "" if ok else "replace_failed"


def insert_ping(phone, name=""):
    """פעימת נוכחות (heartbeat) לטבלת usage_pings — לחישוב זמן-פעיל אמיתי ביומן השימוש. best-effort."""
    if not enabled():
        return False
    try:
        r = requests.post(SUPABASE_URL + "/rest/v1/usage_pings",
                          headers={**_headers(), "Content-Type": "application/json"},
                          json={"office_id": SB_OFFICE_ID, "phone": str(phone or ""), "name": str(name or "")},
                          timeout=8)
        r.raise_for_status()
        return True
    except Exception:
        return False


def prune_pings(days=60):
    """גיזום פעימות ישנות (60+ יום) — שהטבלה לא תגדל לנצח. best-effort."""
    if not enabled():
        return False
    try:
        import datetime as _dt
        cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)).isoformat()
        r = requests.delete(SUPABASE_URL + "/rest/v1/usage_pings",
                            headers=_headers(),
                            params={"office_id": "eq." + SB_OFFICE_ID, "ts": "lt." + cutoff},
                            timeout=30)
        r.raise_for_status()
        return True
    except Exception:
        return False


def fetch_pings_today(iso_from):
    """פעימות מ-iso_from ואילך → list של {phone, name, ts}.
    מדופדף (תקרת ה-1,000 של PostgREST) — והעמודים מעבר לראשון מובאים במקביל:
    בטווח 30 יום יש עשרות עמודים, והבאה טורית לקחה ~15ש' ותפסה thread."""
    if not enabled():
        return []
    def _page_params(offset):
        return {"office_id": "eq." + SB_OFFICE_ID, "ts": "gte." + iso_from,
                "select": "phone,name,ts", "order": "ts.asc",
                "limit": str(_PAGE), "offset": str(offset)}
    try:
        r = requests.get(SUPABASE_URL + "/rest/v1/usage_pings",
                         headers={**_headers(), "Prefer": "count=exact"},
                         params=_page_params(0), timeout=20)
        r.raise_for_status()
        out = r.json() or []
        total = 0
        try:
            total = int((r.headers.get("Content-Range", "") or "/0").split("/")[-1])
        except Exception:
            total = len(out)
        total = min(total, 200000)   # תקרת בטיחות
        if total <= _PAGE:
            return out
        offsets = list(range(_PAGE, total, _PAGE))
        from concurrent.futures import ThreadPoolExecutor
        def _fetch(off):
            try:
                rr = requests.get(SUPABASE_URL + "/rest/v1/usage_pings",
                                  headers=_headers(), params=_page_params(off), timeout=20)
                rr.raise_for_status()
                return rr.json() or []
            except Exception:
                return []
        with ThreadPoolExecutor(max_workers=5) as ex:
            for page in ex.map(_fetch, offsets):
                out.extend(page)
        return out
    except Exception:
        return []


def fetch_config():
    """הקונפיג המלא — dict מורכב משורות office_config (שורה לכל מפתח).
    זהה 1:1 לבלוב של getconfig; כתיבת מפתח אחד אינה נוגעת באחרים."""
    recs = _get_all("office_config", "key,value")
    return {rec["key"]: rec["value"] for rec in recs if rec.get("key")}


def save_config_key(key, value):
    """שמירת מפתח קונפיג בודד — בלי לגעת בשאר המפתחות."""
    r = requests.post(SUPABASE_URL + "/rest/v1/office_config?on_conflict=office_id,key",
                      headers={**_headers(), "Content-Type": "application/json",
                               "Prefer": "resolution=merge-duplicates"},
                      json={"office_id": SB_OFFICE_ID, "key": key, "value": value},
                      timeout=_TIMEOUT)
    r.raise_for_status()
    return True


def fetch_hidden_call_ids():
    """מזהי שיחות מוסתרות — set של מחרוזות, כמו _fetch_hidden_calls ב-app.py."""
    recs = _get_all("hidden_calls", "event_id")
    return set(str(rec.get("event_id") or "").strip()
               for rec in recs if str(rec.get("event_id") or "").strip())


if __name__ == "__main__":
    # בדיקה עצמית מקומית — קריאה בלבד, מדפיס ספירות
    if not enabled():
        print("❌ חסרים SUPABASE_URL / SUPABASE_SERVICE_KEY בסביבה")
        raise SystemExit(1)
    rows = fetch_newborn_rows()
    contacts = fetch_newborn_contacts()
    print(f"✅ מודעות בחלון {NB_SHEET_CUTOFF_DAYS} ימים: {len(rows)}")
    print(f"✅ נכסים עם פניות: {len(contacts)} (סה\"כ {sum(len(v) for v in contacts.values())} פניות)")
    if rows:
        first = rows[0]
        print("דוגמה:", {k: first.get(k, "") for k in ("רחוב", "עיר", "נוצר בתאריך")})


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


# ── [DEALS-HISTORY 12/10] היסטוריית עסקאות ──────────────────────────────────────
_DH_COLS = ("id,src_key,branch,year,src_sheet,src_row,src_serial,deal_date,city,street,side,agent,"
            "client_name,client_phone,other_broker,deal_amount,commission_gross,commission_net,discount,"
            "lead_source,paid_amount,deposited,invoice_no,receipt_no,reported_date,remax_approved,"
            "collection_status,notes,lawyer_notes,app_deal_id,missing_since,updated_at,src_hash,src_path,agent_raw,"
            "status:raw->_status")   # צבעי 'התקבל כסף'/'הופקד'/'דווח' (אייל 12/10)


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
