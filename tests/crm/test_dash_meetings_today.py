# tests/crm/test_dash_meetings_today.py — לוח הבקרה: כרטיס 'פגישות היום' (אייל 20/10)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_meetings_today", "crm_ts", "inv_parse_dt", "_crm_day")
f = ns["crm_meetings_today"]
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 20, 9, 0, tzinfo=IL).timestamp()
ts = ns["crm_ts"]
recs = [{"date": ts("2026-10-20T14:30"), "kind": "פגישה", "agent": "רפי", "by": "אוצר", "source": "נכס נולד", "address": "הנשיא 4", "state": "פתוח"},
        {"date": ts("2026-10-20T10:00"), "kind": "פגישה", "agent": "דנה", "by": "דנה", "source": "ידני", "address": "הרצל 2", "state": "פתוח"},
        {"date": ts("2026-10-20"), "kind": "פולו-אפ", "agent": "דנה", "by": "דנה", "source": "ידני", "address": "", "state": "בוצע"},
        {"date": ts("2026-10-21T10:00"), "kind": "פגישה", "agent": "רפי", "by": "רפי", "source": "ידני", "address": "מחר", "state": "פתוח"}]
D = f(recs, now)
ck(D["meetings"] == 2 and D["followups"] == 1 and D["done"] == 1, D)
ck([r["address"] for r in D["rows"]] == ["", "הרצל 2", "הנשיא 4"], ("by time of day, day-only first", [r["address"] for r in D["rows"]]))
ck(D["rows"][2]["by"] == "אוצר" and D["rows"][2]["source"] == "נכס נולד", D["rows"][2])
print("dash_meetings_today OK")
