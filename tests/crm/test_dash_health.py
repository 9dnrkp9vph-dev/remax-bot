# tests/crm/test_dash_health.py — דשבורד: מצב בריאות לכל זרם (שעות עבודה, שבת, אין נתון)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_health", "_work_hours_between", "crm_ts", "inv_parse_dt")
health = ns["crm_health"]
IL = ZoneInfo("Asia/Jerusalem")
def ts(s): return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=IL).timestamp()
H = 3600; mon10 = ts("2026-10-19 15:00")      # יום שני 15:00 (כל הפערים בתוך שעות העבודה)
ck(health(mon10 - 1*H, mon10, 3, True, False) == "ok", "ok")
ck(health(mon10 - 5*H, mon10, 3, True, False) == "warn", "warn")
ck(health(mon10 - 7*H, mon10, 3, True, False) == "bad", "bad")
ck(health(ts("2026-10-18 19:30"), ts("2026-10-19 08:30"), 3, True, False) == "ok", "night not counted")
ck(health(mon10 - 5*H, mon10, 3, True, True) == "quiet", "shabbat")
ck(health(None, mon10, 3, True, False) == "none", "no data")
ck(health(mon10 - 40*H, mon10, 30, False, False) == "warn", "calendar hours")
# שישי 12:00 → ראשון 09:00: שעה בשישי + שעה בראשון = 2 שעות עבודה
ck(abs(ns["_work_hours_between"](ts("2026-10-16 12:00"), ts("2026-10-18 09:00")) - 2) < 0.01, "friday short day")
print("dash_health OK", _load.n)
