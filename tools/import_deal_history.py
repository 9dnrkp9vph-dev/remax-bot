# tools/import_deal_history.py
"""ייבוא היסטוריית עסקאות (2015–2025) — רץ על המחשב של אייל.
ריצה רגילה = יבשה (דוח בלבד, בלי שמירה). --save = שליחה לשרת אחרי אישור.
סיסמאות ומפתח הייבוא: getpass בלבד. הדוח לא כולל פרטי לקוחות."""
import os, sys, json, getpass, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import deals_history as D

APP_URL = os.environ.get("APP_URL", "https://remax-bot.onrender.com")


def rows_from_workbook(wb, branch, year, sheets, default_agent=""):
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
            st, row = D.normalize_row(cells, fields, {"branch": branch, "year": year, "sheet": sh, "row_idx": i,
                                                      "headers": headers, "default_agent": default_agent})
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
    here = os.path.dirname(os.path.abspath(__file__))
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
        rows, rep = rows_from_workbook(wb, br, int(yr), src.get("sheets") or [], src.get("default_agent", ""))
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
