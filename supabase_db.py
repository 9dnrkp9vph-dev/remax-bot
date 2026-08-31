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
        # השכרות מסריקת יד2 לא מוצגות בנכס נולד (החלטת אייל 31/08) — נשארות ב-DB
        # לאופציה עתידית פר-סוכן ב"ניהול". שורות הצינור הישן בלי "סוג עסקה" — עוברות.
        if "שכר" in str(raw.get("סוג עסקה") or ""):
            continue
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
        if k in _BUYER_KEYS and v is not None:
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
    """'בלעדויות חיצוניות' — זהה 1:1 ל-getRaw_ (כולל _date_key)."""
    return _fetch_raw_tab("external_exclusives", "01/01/2020", "31/12/2099")


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


def newborn_dates(source_keys):
    """'נוצר בתאריך' הקיים לכל source_key — לשימור שעה שכבר נקבעה (ingest יד2).
    מחזיר {source_key: המחרוזת הקיימת} רק לשורות שנמצאו."""
    out = {}
    if not (enabled() and source_keys):
        return out
    for i in range(0, len(source_keys), 100):
        chunk = source_keys[i:i + 100]
        try:
            r = requests.get(SUPABASE_URL + "/rest/v1/newborn_listings", headers=_headers(),
                             params={"select": "source_key,d:raw->>נוצר בתאריך",
                                     "office_id": "eq." + SB_OFFICE_ID,
                                     "source_key": "in.(" + ",".join('"%s"' % k for k in chunk) + ")"},
                             timeout=_TIMEOUT)
            r.raise_for_status()
            for rec in (r.json() or []):
                out[str(rec.get("source_key") or "")] = str(rec.get("d") or "")
        except Exception:
            continue   # best-effort: בלי שעה קיימת פשוט לא משמרים
    return out


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


def upsert_signature_row(source_key, received_iso, raw):
    """שורת חתימה מ-webhook פיירברי — upsert לפי (office_id, source_key):
    הטריגר "נוצרה או עודכנה" מעדכן שורה קיימת במקום להכפיל; retry לא מכפיל.
    raw = במבנה getRaw_ (המפתחות ש-fetch_signatures_rows מחזיר 1:1)."""
    row = {"office_id": SB_OFFICE_ID, "source_key": source_key,
           "event_id": raw.get("event_id", ""), "deal_type": raw.get("deal_type", ""),
           "agent": raw.get("agent", ""), "client_name": raw.get("client_name", ""),
           "address": raw.get("address", ""), "city": raw.get("city", ""),
           "commission_pct": raw.get("commission_pct", ""), "notes": raw.get("notes", ""),
           "received_at": received_iso, "raw": raw}
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
    """הוספת חשבונית בודדת (קליטה מ-Fireberry). כפילות row_hash נבלעת בשקט."""
    r = requests.post(SUPABASE_URL + "/rest/v1/invoices",
                      headers={**_headers(), "Prefer": "resolution=ignore-duplicates"},
                      params={"on_conflict": "row_hash"},
                      json=[{**row, "office_id": SB_OFFICE_ID}], timeout=_TIMEOUT)
    r.raise_for_status()
    return True


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
