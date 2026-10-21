# tests/crm/test_dash_story.py — [21/10 אייל: 'ריבוע בדשבורד כמה לחצו לראות את הסטורי (שאדע אם שימושי)']
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_story_stats", "story_detail")
F, D = ns["crm_story_stats"], ns["story_detail"]
ck(D(3, 8) == "ראה 3/8" and D(0, 0) == "ראה 0/0" and D(99, 4) == "ראה 4/4", "detail clamps")
NOW = 1_800_000_000.0
b = {"day": NOW - 3600, "week": NOW - 3 * 86400, "month": NOW - 20 * 86400}
A = "סטורי נכסים חמים — "
act = [{"ts": NOW - 60, "action": A + "לחיצה", "name": "רפי", "detail": "ראה 8/8"},
       {"ts": NOW - 120, "action": A + "לחיצה", "name": "רפי", "detail": "ראה 2/8"},
       {"ts": NOW - 200, "action": A + "אוטומטי", "name": "דנה", "detail": "ראה 1/8"},
       {"ts": NOW - 300, "action": A + "אוטומטי", "name": "רפי", "detail": "ראה 5/8"},
       {"ts": NOW - 5 * 86400, "action": A + "לחיצה", "name": "אבי", "detail": "ראה 4/6"},
       {"ts": NOW - 60, "action": "חיפוש נכסים", "name": "x", "detail": "y"}]
o = F(act, b)
d = o["day"]
ck(d["taps"] == 2 and d["tap_people"] == 1 and d["autos"] == 2 and d["auto_people"] == 2, d)
ck(d["full"] == 1 and d["past_summary"] == 3, ("full = saw all cards; past_summary = got beyond card 1", d))
ck(o["week"]["taps"] == 2 and o["month"]["taps"] == 3 and o["month"]["tap_people"] == 2, o)
ck(d["top"] == [["רפי", 2]], d["top"])
print("dash_story OK", _load.n)
