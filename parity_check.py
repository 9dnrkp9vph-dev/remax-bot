# ============================================================================
# parity_check.py — השוואת "נכס נולד": Apps Script (הגיליון) ↔ supabase_db
# ----------------------------------------------------------------------------
# סקריפט עצמאי, קריאה בלבד משני הצדדים. מדמה בדיוק את מה ש-app.py יקבל
# מכל אחד מהמסלולים, ומשווה שורה-שורה ושדה-שדה.
#
# הרצה (Terminal, מתוך תיקיית הריפו):
#   APPS_SCRIPT_URL=... APPS_SCRIPT_TOKEN=... \
#   SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python3 parity_check.py
# ============================================================================
import os
import sys

import requests

import supabase_db

APPS_SCRIPT_URL   = (os.environ.get("APPS_SCRIPT_URL", "") or "").strip()
APPS_SCRIPT_TOKEN = (os.environ.get("APPS_SCRIPT_TOKEN", "") or "").strip()


def _apps_post(action):
    # זהה ל-_buyers_apps_post ב-app.py: form-data + allow_redirects
    r = requests.post(APPS_SCRIPT_URL,
                      data={"action": action, "token": APPS_SCRIPT_TOKEN},
                      timeout=60, allow_redirects=True)
    r.raise_for_status()
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"{action}: {j}")
    return j


def _nb_key(r):
    """שחזור _nb_key מ-app.py — המפתח היציב של מודעה."""
    pid = (r.get("מזהה", "") or "").strip()
    if pid:
        return "id:" + pid
    link = (r.get("קישור", "") or "").strip()
    if link:
        return "ln:" + link
    addr = (r.get("רחוב1", "") or r.get("רחוב", "") or "").strip()
    return "ad:" + addr + "|" + (r.get("נוצר בתאריך", "") or "").strip()


def _dedupe_last(rows):
    d = {}
    for r in rows:
        d[_nb_key(r)] = r
    return d


def main():
    problems = 0

    # ── מודעות ──
    sheet_rows = _apps_post("listnewborn").get("rows", []) or []
    sb_rows = supabase_db.fetch_newborn_rows()
    print(f"🏠 מודעות — גיליון (listnewborn): {len(sheet_rows)} · Supabase: {len(sb_rows)}")

    sheet_by = _dedupe_last(sheet_rows)
    sb_by = _dedupe_last(sb_rows)
    missing = [k for k in sheet_by if k not in sb_by]
    extra = [k for k in sb_by if k not in sheet_by]
    if missing:
        problems += 1
        print(f"❌ חסרות במסלול Supabase: {len(missing)} — {missing[:3]}")
    if extra:
        problems += 1
        print(f"⚠️ עודפות במסלול Supabase: {len(extra)} — {extra[:3]}")

    # השוואת שדות — על כל המפתחות המשותפים
    diff_fields = 0
    example = None
    for k in sheet_by:
        if k not in sb_by:
            continue
        a, b = sheet_by[k], sb_by[k]
        keys = set(a.keys()) | set(b.keys())
        for f in keys:
            va = str(a.get(f, "") or "").strip()
            vb = str(b.get(f, "") or "").strip()
            if va != vb:
                diff_fields += 1
                if example is None:
                    example = (k, f, va[:60], vb[:60])
    if diff_fields:
        problems += 1
        print(f"❌ אי-התאמות שדה: {diff_fields}")
        print(f"   לדוגמה: נכס {example[0]} · שדה '{example[1]}':")
        print(f"   גיליון:  '{example[2]}'")
        print(f"   Supabase: '{example[3]}'")
    else:
        print("✅ כל השדות זהים בכל המודעות המשותפות")

    # ── פניות ──
    sheet_c = {}
    for r in (_apps_post("listnewborncontacts").get("rows", []) or []):
        k = (r.get("key", "") or "").strip()
        ag = (r.get("agent", "") or "").strip()
        if not k:
            continue
        sheet_c.setdefault(k, [])
        if ag and ag not in sheet_c[k]:
            sheet_c[k].append(ag)
    sb_c = supabase_db.fetch_newborn_contacts()
    same = {k: sorted(v) for k, v in sheet_c.items()} == {k: sorted(v) for k, v in sb_c.items()}
    print(f"📲 פניות — גיליון: {len(sheet_c)} נכסים · Supabase: {len(sb_c)} נכסים · "
          + ("✅ זהות לחלוטין" if same else "❌ שונות"))
    if not same:
        problems += 1
        only_sheet = [k for k in sheet_c if sorted(sheet_c[k]) != sorted(sb_c.get(k, []))]
        print(f"   נכסים עם הבדל: {len(only_sheet)} — {only_sheet[:3]}")

    print()
    if problems == 0:
        print("🟢 PARITY מלא — מסלול Supabase מחזיר לאפליקציה בדיוק את אותם נתונים. בטוח להדליק את הדגל.")
        return 0
    print(f"🔴 נמצאו {problems} סוגי פערים — לא להדליק את הדגל עדיין.")
    return 1


if __name__ == "__main__":
    if not (APPS_SCRIPT_URL and APPS_SCRIPT_TOKEN):
        print("❌ חסרים APPS_SCRIPT_URL / APPS_SCRIPT_TOKEN")
        sys.exit(2)
    if not supabase_db.enabled():
        print("❌ חסרים SUPABASE_URL / SUPABASE_SERVICE_KEY")
        sys.exit(2)
    sys.exit(main())
