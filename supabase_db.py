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
