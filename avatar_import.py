"""השלמת תמונות סוכנים מהאתר הישן לאפי (אייל 18/10: "סנכרון מלא — כל תמונה תופיע גם וגם", אפשרות א).

עד היום הכיוון היה אחד: תמונה שהועלתה באפי → האתר. לסוכנים בלי תמונה באפי האתר הציג את התמונה
מהאתר הישן (נאספה 14/10), ואפי לא הכירה אותה. כאן: סוכן בלי תמונה באפי מקבל את התמונה מהאתר הישן,
נשמרת בטבלת avatars תחת טלפוני הכניסה שלו. מכאן אפי היא המקור — העלאה באפי מחליפה גם באתר.
לא דורסים תמונה קיימת; כשלא ידוע אם יש תמונה (Supabase נפל) — לא מייבאים.
הקבצים: site_photos/ (העתק מ-refamily-site/refsite/static/old/agents, אותם בייטים — כך שהאתר
ממשיך להציג את הגרסה המעובדת שלו, שמזוהה לפי sha של המקור)."""
import json
import os

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site_photos")
# השם באפי → השם באתר הישן (אותה טבלה כמו ב-refamily-site/refsite/agentphotos.py)
ALIASES = {"בינימין אביטן": "בנימין אביטן", "ליאור גרונפינקל": "ליאור גורפינקל", "דודו עובדיה": "דוד עובדיה",
           "זאודיטו בזונך": "חן בזונך", "רפי דפיצוטו": "רפי דה פיצ'וטו"}


def load_index():
    try:
        with open(os.path.join(DIR, "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def people_from(phone_name, key, removed=()):
    """{טלפון: שם} (אנשי קשר + כניסות) → [{name, key, phones}] — אדם אחד לכל שם (לפי key)."""
    by = {}
    for p, nm in (phone_name or {}).items():
        p9 = "".join(ch for ch in str(p or "") if ch.isdigit())[-9:]
        nm = " ".join(str(nm or "").split())
        k = key(nm)
        if not (p9 and nm and k) or k in removed:
            continue
        a = by.setdefault(k, {"name": nm, "key": k, "phones": []})
        if p9 not in a["phones"]:
            a["phones"].append(p9)
    return list(by.values())


def plan(people, index, key, has_photo, aliases=ALIASES):
    """has_photo(phones) → True/False/None. מחזיר import (שם, טלפונים, קובץ) / has / missing / unknown."""
    idx = {key(x.get("name", "")): x.get("file") for x in index or [] if x.get("file")}
    out = {"import": [], "has": [], "missing": [], "unknown": []}
    for p in sorted(people or [], key=lambda x: x["name"]):
        al = (aliases or {}).get(p["name"])
        f = idx.get(p["key"]) or (idx.get(key(al)) if al else None)
        if not f:
            out["missing"].append(p["name"])
            continue
        h = has_photo(p["phones"])
        if h is None:
            out["unknown"].append(p["name"])
        elif h:
            out["has"].append(p["name"])
        else:
            out["import"].append({"name": p["name"], "phones": list(p["phones"]), "file": f})
    return out


def photo_bytes(fname):
    if not fname or os.path.basename(fname) != fname:
        return b""
    try:
        with open(os.path.join(DIR, fname), "rb") as f:
            return f.read()
    except OSError:
        return b""
