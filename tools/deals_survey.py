"""סקירת קבצי מעקב העסקאות בדרופבוקס — קריאה בלבד, רץ על המחשב של אייל.
מדפיס לכל משרד+שנה (2016–2025): הקבצים (עם תאריך השמירה), הקובץ המוצע, הגיליונות
(כותרות מוכרות, שורות) ושמות הסוכנים הגולמיים עם מספר שורות. בלי פרטי לקוחות.
סיסמאות: getpass בלבד — לא נשמרות, לא מודפסות.
כותב הצעה ל-tools/deals_sources.json ול-tools/deals_agent_map.json — לאישור אייל."""
import os, re, io, sys, json, time, getpass, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.expanduser("~/Library/CloudStorage/Dropbox/הפרלמנט")
BRANCH_DIRS = {"bialik": "אייל/מעקב עסקאות", "motzkin": "אוהד/מעקב עסקאות מוצקין",
               "kiryat_yam": "מעקב עסקאות קרית ים"}
PW_GROUP = {"bialik": "ביאליק", "motzkin": "מוצקין + קרית ים", "kiryat_yam": "מוצקין + קרית ים"}
YEARS = list(range(2016, 2026))   # אייל 12/10: "10 שנים אחורה" — 2026 מגיע מהסנכרון השוטף (שלב 2)
_TRACK = re.compile(r"מעקב|עסקאות")


def pick_file(paths, mtime=os.path.getmtime):
    """אייל 12/10: "הקבצים עם השמירה הכי חדשה" — מבין קבצי המעקב של השנה (שם עם מעקב/עסקאות;
    קבצי נעילה ~$ בחוץ) בוחרים את זה שנשמר אחרון, גם אם הוא עותק כפול. בלי קובץ מעקב — האחרון מכולם."""
    paths = [p for p in (paths or []) if not os.path.basename(p).startswith("~$")]
    if not paths:
        return None
    pool = [p for p in paths if _TRACK.search(os.path.basename(p))] or paths
    return max(pool, key=lambda p: (mtime(p) or 0, p))


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


def _d(p):
    try:
        return time.strftime("%d/%m/%Y", time.localtime(os.path.getmtime(p)))
    except OSError:
        return "?"


def survey(pws):
    from deals_history import find_header_row, BRANCHES
    sources, agents = {}, collections.Counter()
    for br, rel in BRANCH_DIRS.items():
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            print("!! חסרה תיקייה:", base); continue
        for yr in YEARS:
            ydir = os.path.join(base, str(yr))
            if not os.path.isdir(ydir):
                continue
            files = []
            for dp, _, fs in os.walk(ydir):
                files += [os.path.join(dp, f) for f in fs if re.search(r"\.xls[xmb]?$", f, re.I)]
            choice = pick_file(sorted(files))
            print("\n== %s %d · %d קבצים · מוצע: %s" % (BRANCHES[br], yr,
                  len(files), os.path.relpath(choice, base) if choice else "—"))
            for f in sorted(files):
                print("   %s %s  (נשמר %s)" % ("*" if f == choice else " ", os.path.relpath(f, base), _d(f)))
            if not choice:
                continue
            try:
                wb = _open(choice, pws[PW_GROUP[br]])
            except Exception as e:
                print("   !! לא נפתח (%s) — סיסמה אחרת?" % type(e).__name__); continue
            picked = []
            for ws in wb.worksheets:
                rows = list(ws.iter_rows(values_only=True, max_row=3000))
                hi, fields = find_header_row(rows)
                if hi is None:
                    print("    [%s] — אין כותרות מוכרות" % ws.title); continue
                ai = fields.get("agent")
                cnt = collections.Counter()
                body = [r for r in rows[hi + 1:] if r and any(c not in (None, "") for c in r)]
                if ai is not None:
                    for r in body:
                        v = re.sub(r"\s+", " ", str(r[ai] if ai < len(r) and r[ai] is not None else "")).strip()
                        if v:
                            cnt[v] += 1
                nf = len([k for k in fields if not k.startswith("_")])
                main = nf >= 6 and "agent" in fields and not picked
                print("    %s [%s] כותרות מוכרות=%d שורות=%d סוכנים=%d" % ("→" if main else " ", ws.title, nf, len(body), len(cnt)))
                if main:
                    picked.append(ws.title)
                    for nm, c in cnt.items():
                        agents["%s|%s" % (br, nm)] += c
            sources["%s|%d" % (br, yr)] = {"file": os.path.relpath(choice, ROOT), "sheets": picked}
    return sources, agents


def write_proposals(here, sources, agents):
    """כותב את ההצעה. קובץ שכבר קיים (אולי אושר ותוקן ידנית) לא נדרס — ההצעה ל-*.proposed.json."""
    out = []
    for name, data in (("deals_sources", sources), ("deals_agent_map", {k: "" for k in sorted(agents)})):
        path = os.path.join(here, name + ".json")
        if os.path.exists(path):
            path = os.path.join(here, name + ".proposed.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        out.append(path)
    return out


def main():
    print("סקירת קבצי מעקב עסקאות (2016–2025) — קריאה בלבד. הסיסמאות לא נשמרות ולא מודפסות.\n")
    pws = {g: getpass.getpass("סיסמת %s: " % g) for g in ("ביאליק", "מוצקין + קרית ים")}
    sources, agents = survey(pws)
    paths = write_proposals(os.path.dirname(os.path.abspath(__file__)), sources, agents)
    print("\n== שמות סוכנים גולמיים (משרד | שם : שורות) ==")
    for k in sorted(agents, key=lambda k: (k.split("|")[0], -agents[k], k)):
        print("   %s : %d" % (k, agents[k]))
    print("\nנכתבו (להצעה ואישור): " + ", ".join(os.path.basename(p) for p in paths))


if __name__ == "__main__":
    main()
