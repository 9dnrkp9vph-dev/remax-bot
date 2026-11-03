"""04/11 (אייל: 'כן תבנה את הכלל של 7 ימים'): נכס משרד שהסורק לא שלח 7 ימים, בזמן שהסניף שלו
נסרק כרגיל, מסומן 'ירד מפרסום' בתאריך השליחה האחרונה. ספיר 3 (bol7k1cw) נשלח לאחרונה ב-12/10
ונשאר פעיל באפליקציה שלושה שבועות — יחד עם עוד 52 נכסים."""
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
NOW_TS = NOW.timestamp()
def ago(days):
    return (NOW - dt.timedelta(days=days)).strftime("%d/%m/%Y %H:%M")
def day_of(days):
    return (NOW - dt.timedelta(days=days)).strftime("%d/%m/%Y")

def row(tok, days, office="5625538", **kw):
    r = {"מספר מודעה": tok, "_y2_office_id": office, "_y2_ingested": ago(days)}
    r.update(kw)
    return r

print("S7 1: pure rule")
absent = [row("bol7k1cw", 23)] + [row("a%02d" % i, 1) for i in range(8)]
incoming = [row("in1", 0)]
out = sb.stale7_office_rows(absent, incoming, NOW_TS)
check("23 days old, healthy branch → stale", [r["מספר מודעה"] for r in out] == ["bol7k1cw"], out)
out = sb.stale7_office_rows([row("x6", 6.5)] + [row("a%02d" % i, 1) for i in range(8)], incoming, NOW_TS)
check("6.5 days → not yet", out == [], out)
out = sb.stale7_office_rows([row("x8", 8, _y2_ingested="")] + [row("a%02d" % i, 1) for i in range(8)], incoming, NOW_TS)
check("no send stamp and no first_seen → skipped", out == [], out)
out = sb.stale7_office_rows([row("x8", 8, _y2_ingested="", _y2_first_seen=ago(30))] + [row("a%02d" % i, 1) for i in range(8)], incoming, NOW_TS)
check("falls back to _y2_first_seen", len(out) == 1, out)
out = sb.stale7_office_rows([row("old%d" % i, 10) for i in range(7)] + [row("a1", 1), row("a2", 1)], incoming, NOW_TS)
check("gate: most of the branch not sent in 7 days → nothing marked", out == [], out)
out = sb.stale7_office_rows([row("old", 10), row("a1", 1)], [row("in1", 0)], NOW_TS)
check("branch under 5 rows → untouched", out == [], out)

print("S7 2: merge_office_props integration")
class R:
    def raise_for_status(s): pass
orig = (sb._get_all, sb.replace_properties, sb.enabled)
written, cur_rows = {}, []
sb._get_all = lambda *a, **k: cur_rows
sb.enabled = lambda: True
sb.replace_properties = lambda rows: (written.__setitem__("rows", rows), (True, len(rows)))[1]
def by_tok(rows):
    return {r.get("מספר מודעה"): r for r in rows}
os.environ.pop("PROPS_STALE_DAYS", None)
os.environ.pop("PROPS_STALE_DELIST", None)
try:
    base = [{"sheet_row": i + 10, "raw": row("live%02d" % i, 1)} for i in range(8)]
    cur_rows[:] = base + [
        {"sheet_row": 2, "raw": row("bol7k1cw", 23)},
        {"sheet_row": 3, "raw": row("fresh6d", 6)},
        {"sheet_row": 4, "raw": row("gone0001", 30, **{"ירד מפרסום": "01/10/2026", "סטטוס": "ירד מפרסום"})},
        {"sheet_row": 5, "raw": row("otherbr1", 30, office="5628636")},
    ]
    sb.merge_office_props("5625538", [row("live00", 0)], stamp=day_of(0), now_full=ago(0))
    out = by_tok(written["rows"])
    r = out["bol7k1cw"]
    check("default on: stale → labeled with the last-send date", r.get("ירד מפרסום") == day_of(23) and r.get("סטטוס") == "ירד מפרסום", r)
    check("marked as rule-made", r.get("_y2_auto_delist") == day_of(23), r)
    check("6 days → still active", not out["fresh6d"].get("ירד מפרסום"), out["fresh6d"])
    check("already delisted keeps its date", out["gone0001"].get("ירד מפרסום") == "01/10/2026", out["gone0001"])
    check("other branch untouched", not out["otherbr1"].get("ירד מפרסום"), out["otherbr1"])
    check("nothing deleted", len(written["rows"]) == len(cur_rows), len(written["rows"]))

    os.environ["PROPS_STALE_DAYS"] = "0"
    cur_rows[:] = base + [{"sheet_row": 2, "raw": row("bol7k1cw", 23)}]
    sb.merge_office_props("5625538", [row("live00", 0)], stamp=day_of(0), now_full=ago(0))
    check("PROPS_STALE_DAYS=0 → off", not by_tok(written["rows"])["bol7k1cw"].get("ירד מפרסום"))

    os.environ["PROPS_STALE_DAYS"] = "30"
    sb.merge_office_props("5625538", [row("live00", 0)], stamp=day_of(0), now_full=ago(0))
    check("threshold from env (30 days) → 23 days not stale", not by_tok(written["rows"])["bol7k1cw"].get("ירד מפרסום"))
finally:
    os.environ.pop("PROPS_STALE_DAYS", None)
    sb._get_all, sb.replace_properties, sb.enabled = orig

print("FAIL %d" % fails if fails else "ALL OK")
sys.exit(1 if fails else 0)
