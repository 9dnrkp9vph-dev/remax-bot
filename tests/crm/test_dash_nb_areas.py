# tests/crm/test_dash_nb_areas.py — לוח הבקרה: סריקת נכס נולד בנפרד לחיפה ולקריות (אייל 20/10)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_dashboard_data", "_CRM_EFFIE_AI", "CRM_STREAMS", "crm_health", "_work_hours_between", "crm_daily_series", "crm_ts",
                "inv_parse_dt", "y2_private_area", "crm_nb_area_last", "crm_period_bounds", "crm_agent_table", "crm_todo", "bs_p9", "_CRM_NB_CONTACT", "_CRM_BPAGE_SEND", "crm_wa_official", "crm_story_stats", "_CRM_WA_OFFICIAL")
area = ns["y2_private_area"]
ck(area([{"city": "חיפה"}, {"city": "חיפה"}, {"_city": "קרית ביאליק"}]) == "חיפה", "majority Haifa")
ck(area([{"city": "קריית מוצקין"}, {"city": "קרית אתא"}]) == "קריות", "Krayot (קריית spelling)")
ck(area([{"city": "חיפה", "neighborhood": "קרית חיים מערבית"}]) == "חיפה", "Kiryat Haim belongs to the Haifa scan")
ck(area([]) == "" and area([{"city": ""}]) == "", "unknown")
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 20, 13, 0, tzinfo=IL).timestamp()
act = [{"ts": now - 600, "role": "system", "action": "סריקת יד2 — נקלטה", "detail": "private · קריות · 120 שורות · נכס נולד 3"},
       {"ts": now - 4 * 3600, "role": "system", "action": "סריקת יד2 — נקלטה", "detail": "private · חיפה · 80 שורות"},
       {"ts": now - 300, "role": "system", "action": "סריקת יד2 — נקלטה", "detail": "agency · 40 שורות"}]
nb = [{"עיר": "קרית ביאליק", "נראה לראשונה": "20/10/2026 12:00"}, {"עיר": "חיפה", "שכונה": "קרית חיים מזרחית", "נראה לראשונה": "20/10/2026 07:00"}]
last = ns["crm_nb_area_last"](act, nb)
ck(abs(last["קריות"] - (now - 600)) < 1 and abs(last["חיפה"] - (now - 4 * 3600)) < 1, ("from the scanner batches", last))
last2 = ns["crm_nb_area_last"]([], nb)
ck(last2["קריות"] == ns["crm_ts"]("20/10/2026 12:00") and last2["חיפה"] == ns["crm_ts"]("20/10/2026 07:00"), ("fallback: newest listing per area", last2))
src = {"report": lambda: {"scans": {"newborn": "20/10/2026 12:00"}}, "activity": lambda t0: act, "newborn": lambda: nb}
d = ns["crm_dashboard_data"](src, now, False, "2026-10-20")
h = {x["key"]: x for x in d["health"]}
ck("newborn" not in h and h["newborn_krayot"]["label"] == "נכס נולד — קריות" and h["newborn_haifa"]["label"] == "נכס נולד — חיפה", list(h))
ck(h["newborn_krayot"]["status"] == "ok" and h["newborn_haifa"]["status"] != "ok", (h["newborn_krayot"], h["newborn_haifa"]))
print("dash_nb_areas OK")
