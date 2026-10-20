"""20/10 (אייל): דיווח 'ירד מפרסום' שנדחה בהגנת 48 השעות לא נזרק — נשמר כממתין ומאושר
בקליטה הבאה של הסניף אחרי שההגנה פגה (68rgph77 אהוד מנור 9: דווח פעם אחת ב-12/10, נדחה, ונשאר
פעיל באפליקציה ובאתר 8 ימים). מודעה שחוזרת בסריקה מבטלת את ההמתנה."""
import os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import supabase_db as sb
from zoneinfo import ZoneInfo

fails = 0
def check(name, cond, detail=""):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "  →  " + repr(detail)))
    if not cond:
        fails += 1

NOW = dt.datetime.now(ZoneInfo("Asia/Jerusalem"))
def ago(h):
    return (NOW - dt.timedelta(hours=h)).strftime("%d/%m/%Y %H:%M")

class R:
    def raise_for_status(s): pass

orig = (sb._get_all, sb.replace_properties, sb.enabled, sb.requests.patch)
patched, written = [], {}
cur_rows = []
sb._get_all = lambda *a, **k: cur_rows
sb.enabled = lambda: True
sb.requests.patch = lambda *a, **k: patched.append(k) or R()
sb.replace_properties = lambda rows: (written.__setitem__("rows", rows), (True, len(rows)))[1]

def by_tok(rows):
    return {r.get("מספר מודעה"): r for r in rows}

try:
    print("DP 1: mark_props_delisted — guarded report is kept as pending")
    cur_rows[:] = [{"sheet_row": 2, "raw": {"מספר מודעה": "68rgph77", "_y2_office_id": "5628636", "_y2_ingested": ago(2)}},
                   {"sheet_row": 3, "raw": {"מספר מודעה": "oldtok00", "_y2_office_id": "5628636", "_y2_ingested": ago(60)}}]
    g = []
    n = sb.mark_props_delisted(["68rgph77", "oldtok00"], "12/10/2026", guarded=g)
    check("only the old one marked now", n == 1, n)
    check("guarded list still reported", g == ["68rgph77"], g)
    raws = {p["json"]["raw"]["מספר מודעה"]: p["json"]["raw"] for p in patched}
    check("guarded row patched with pending", raws.get("68rgph77", {}).get("_y2_delist_pending") == "12/10/2026", raws.get("68rgph77"))
    check("guarded row not labeled yet", not raws.get("68rgph77", {}).get("ירד מפרסום"), raws.get("68rgph77"))
    check("old row labeled", raws.get("oldtok00", {}).get("ירד מפרסום") == "12/10/2026", raws.get("oldtok00"))

    print("DP 2: merge_office_props confirms pending after the guard window")
    cur_rows[:] = [
        {"sheet_row": 2, "raw": {"מספר מודעה": "68rgph77", "_y2_office_id": "5628636", "_y2_ingested": ago(50), "_y2_delist_pending": "12/10/2026"}},
        {"sheet_row": 3, "raw": {"מספר מודעה": "fresh001", "_y2_office_id": "5628636", "_y2_ingested": ago(3), "_y2_delist_pending": "20/10/2026"}},
        {"sheet_row": 4, "raw": {"מספר מודעה": "back0001", "_y2_office_id": "5628636", "_y2_ingested": ago(50), "_y2_delist_pending": "12/10/2026"}},
        {"sheet_row": 5, "raw": {"מספר מודעה": "stale001", "_y2_office_id": "5628636", "_y2_ingested": ago(100)}},
        {"sheet_row": 6, "raw": {"מספר מודעה": "otherbr1", "_y2_office_id": "5625538", "_y2_ingested": ago(50), "_y2_delist_pending": "12/10/2026"}},
        {"sheet_row": 7, "raw": {"מספר מודעה": "live0001", "_y2_office_id": "5628636", "_y2_ingested": ago(2)}},
    ]
    sb.merge_office_props("5628636", [{"מספר מודעה": "back0001", "_y2_office_id": "5628636", "_y2_ingested": ago(0)},
                                      {"מספר מודעה": "live0001", "_y2_office_id": "5628636", "_y2_ingested": ago(0)}],
                          stamp="20/10/2026", now_full=ago(0))
    out = by_tok(written["rows"])
    r = out["68rgph77"]
    check("pending + 48h passed + absent → labeled", r.get("ירד מפרסום") == "20/10/2026" and r.get("סטטוס") == "ירד מפרסום", r)
    check("pending cleared once labeled", "_y2_delist_pending" not in r, r)
    r = out["fresh001"]
    check("pending but sent <48h → still waiting", not r.get("ירד מפרסום") and r.get("_y2_delist_pending") == "20/10/2026", r)
    r = out["back0001"]
    check("reappeared in the scan → fresh row, no pending, no label", not r.get("ירד מפרסום") and "_y2_delist_pending" not in r, r)
    r = out["stale001"]
    check("no report from the scanner → untouched (stale rule stays paused)", not r.get("ירד מפרסום"), r)
    r = out["otherbr1"]
    check("other branch untouched by this branch's merge", not r.get("ירד מפרסום") and r.get("_y2_delist_pending"), r)
    check("nothing deleted", len(written["rows"]) == 6, len(written["rows"]))

    print("DP 3: merge guard path (delisted inside a rows batch) also leaves pending")
    cur_rows[:] = [{"sheet_row": 2, "raw": {"מספר מודעה": "gtok0001", "_y2_office_id": "5628636", "_y2_ingested": ago(1)}}] + \
                  [{"sheet_row": 3 + i, "raw": {"מספר מודעה": "k%07d" % i, "_y2_office_id": "5628636", "_y2_ingested": ago(1)}} for i in range(3)]
    g = []
    sb.merge_office_props("5628636", [{"מספר מודעה": "k%07d" % i, "_y2_office_id": "5628636"} for i in range(3)],
                          delisted_tokens={"gtok0001"}, stamp="20/10/2026", now_full=ago(0), guarded=g)
    r = by_tok(written["rows"])["gtok0001"]
    check("guarded in merge → pending, no label", r.get("_y2_delist_pending") == "20/10/2026" and not r.get("ירד מפרסום"), r)
    check("guarded reported", g == ["gtok0001"], g)

    print("DP 4: guard off (PROPS_DELIST_GUARD_HOURS=0) → pending confirmed at once")
    os.environ["PROPS_DELIST_GUARD_HOURS"] = "0"
    cur_rows[:] = [{"sheet_row": 2, "raw": {"מספר מודעה": "p0000001", "_y2_office_id": "5628636", "_y2_ingested": ago(1), "_y2_delist_pending": "20/10/2026"}},
                   {"sheet_row": 3, "raw": {"מספר מודעה": "k0000001", "_y2_office_id": "5628636", "_y2_ingested": ago(1)}}]
    sb.merge_office_props("5628636", [{"מספר מודעה": "k0000001", "_y2_office_id": "5628636"}], stamp="20/10/2026", now_full=ago(0))
    check("labeled", by_tok(written["rows"])["p0000001"].get("ירד מפרסום") == "20/10/2026")
    del os.environ["PROPS_DELIST_GUARD_HOURS"]
finally:
    sb._get_all, sb.replace_properties, sb.enabled, sb.requests.patch = orig

print("\n" + ("ALL PASS" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)
