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
    """קריאה מדופדפת (1000 בכל עמוד) מ-PostgREST; מחזיר list של dicts."""
    out, offset = [], 0
    while True:
        params = {
            "select": select,
            "office_id": "eq." + SB_OFFICE_ID,
            "limit": str(_PAGE),
            "offset": str(offset),
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


def fetch_excl_rows():
    """'בלעדויות חיצוניות' — זהה 1:1 ל-getRaw_ (כולל _date_key)."""
    return _fetch_raw_tab("external_exclusives", "01/01/2020", "31/12/2099")


def fetch_properties_rows():
    """'נכסים במשרד' — זהה 1:1 ל-fetch_sheet_rows (dict לפי כותרות + _desc_ae),
    לפי סדר השורות בגיליון."""
    recs = _get_all("properties", "sheet_row,raw", {"order": "sheet_row.asc"})
    return [rec["raw"] for rec in recs if isinstance(rec.get("raw"), dict)]


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
