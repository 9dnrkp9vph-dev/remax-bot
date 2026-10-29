# tests/crm/test_dash_data.py — דשבורד: הרכבת הנתונים ממקורות מוזרקים (כולל מקור שנופל)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_dashboard_data", "_CRM_EFFIE_AI", "CRM_STREAMS", "crm_health", "_work_hours_between", "crm_daily_series", "crm_ts", "inv_parse_dt", "crm_nb_area_last", "crm_period_bounds", "crm_agent_table", "crm_todo", "bs_p9", "_CRM_NB_CONTACT", "_CRM_BPAGE_SEND", "crm_wa_official", "crm_story_stats", "_CRM_WA_OFFICIAL")
build = ns["crm_dashboard_data"]
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 19, 15, 0, tzinfo=IL).timestamp()
rep = {"calls": {"day": 5, "week": 20, "month": 80, "year": 900}, "calls_answered": {"day": 4, "week": 15, "month": 60, "year": 700},
       "signings": {"day": 1, "week": 3, "month": 9, "year": 99}, "signings_by_label": {"בלעדיות": {"day": 0, "week": 1, "month": 2, "year": 20}},
       "buyers": {"day": 2, "week": 5, "month": 9, "year": 90}, "newborn": {"day": 7, "week": 30, "month": 90, "year": 900},
       "shtaf": {"day": 1, "week": 2, "month": 3, "year": 4}, "deals_opened": {"day": 0, "week": 1, "month": 2, "year": 3},
       "deals_closed": {"day": 0, "week": 0, "month": 1, "year": 5}, "office_active": 410, "office_active_excl": 260, "open_now": 7, "lawyer_now": 2,
       "scans": {"office": "19/10/2026 13:30", "shtaf": "19/10/2026 09:00", "newborn": "19/10/2026 14:40"}, "insights": ["תובנה"]}
act = [{"ts": now - 600, "role": "agent", "action": "חיפוש נכסים", "name": "א", "detail": "4 חדרים באפקה"},
       {"ts": now - 650, "role": "agent", "action": "חיפוש נכסים", "name": "א", "detail": "(כל הנכסים)"},
       {"ts": now - 60, "role": "client", "action": "סימון בדף קונה", "name": "לקוח"},
       {"ts": now - 100, "role": "agent", "action": "וואטסאפ מהטלפון — נכס נולד", "name": "א"},
       {"ts": now - 110, "role": "agent", "action": "וואטסאפ מהטלפון — נכס נולד", "name": "ב"},
       {"ts": now - 120, "role": "agent", "action": "וואטסאפ מהטלפון — קונים", "name": "א"},
       {"ts": now - 86400 - 60, "role": "agent", "action": "וואטסאפ מהטלפון — קונים", "name": "א"},
       {"ts": now - 130, "role": "system", "action": "וואטסאפ רשמי — נשלח", "name": "וואטסאפ רשמי"},
       {"ts": now - 140, "role": "system", "action": "וואטסאפ רשמי — נכשל", "name": "וואטסאפ רשמי"},
       {"ts": now - 700, "role": "agent", "action": "שאל את אפי", "name": "א"},
       {"ts": now - 3600, "role": "site", "action": "ליד מהאתר — סוכן AI אישי", "name": "ליד"}]
def boom(*a): raise RuntimeError("down")
src = {"report": lambda: rep,
       "calls": lambda: [{"received_at": "2026-10-19T11:30:00Z"}],
       "signings": boom,                                    # מקור שנופל
       "buyers": lambda: [{"date": "19/10/2026"}],
       "newborn": lambda: [{"נוצר בתאריך": "19/10/2026 14:40"},
                           {"נוצר בתאריך": "19/10/2026 09:00", "נראה לראשונה": "02/10/2026 11:00"}],   # מודעה ישנה שנערכה היום ביד2
       "last_invoice": lambda: None,
       "activity": lambda t0: act,
       "usage": lambda t0: [{"name": "א", "min": 40}],
       "site_ai": lambda: {"2026-10-19": {"site_ai": 12, "site_cache": 3, "site_blocked": 0, "lead_ai": 2, "hours": {"14": {"site_ai": 5}}}},
       "ai_cap": lambda: 500}
d = build(src, now, False, "2026-10-19")
H = {h["key"]: h for h in d["health"]}
ck(H["calls"]["status"] == "ok" and H["signatures"]["status"] == "none", H)       # נופל → none, לא קריסה
ck(H["invoices"]["status"] == "none" and H["office"]["status"] == "ok" and H["site_leads"]["status"] == "ok", H)
ck(H["app_usage"]["status"] == "ok", "app usage from agent activity")
ck(d["periods"]["calls"]["month"] == 80 and d["periods"]["office_active"] == 410 and d["periods"]["office_active_excl"] == 260, d["periods"])
ck(len(d["series"]["days"]) == 30 and d["series"]["days"][-1] == "2026-10-19" and d["series"]["calls"][-1] == 1, d["series"]["calls"][-3:])
ck(d["series"]["signings"] == [0] * 30, "failed source → zeros")
ck(d["series"]["newborn"][-1] == 1 and d["series"]["newborn"][-18] == 1, ("newborn by first-seen, not yad2 edit date", d["series"]["newborn"]))
ck(d["ai"]["site"]["today"] == 14 and d["ai"]["site"]["cap"] == 500 and d["ai"]["site"]["hours"]["14"] == 5, d["ai"]["site"])
ck(d["ai"]["effie_today"]["props"] == 1 and d["ai"]["effie_today"]["ask"] == 1, d["ai"]["effie_today"])
ck(len(d["ai"]["site_7d"]) == 7 and d["ai"]["site_7d"][-1] == 14, d["ai"]["site_7d"])
ck(d["usage_today"] == [{"name": "א", "min": 40}], "usage")
W = d["wa"]
ck(W["agents_today"] == {"נכס נולד": 2, "קונים": 1} and W["agents_7d"][-1] == 3 and W["agents_7d"][-2] == 1, W)
ck(W["official_today"] == {"sent": 1, "failed": 1} and W["official_7d"][-1] == 1, W)
ck(H["app_usage"]["last"] == now - 100, "whatsapp click = app usage")
ck("insights" not in d, "no yesterday-worded insights on a partial day")
ck(H["app_usage"]["last"] != now - 60, "client (buyer page) activity is not Effie usage")
q = build(src, now, True, "2026-10-19")
ck(all(h["status"] == "quiet" for h in q["health"] if h["key"] in ("calls", "newborn_krayot", "newborn_haifa", "app_usage")), "shabbat quiet for work-hours streams")
ck(build({"report": boom}, now, False, "2026-10-19")["periods"]["calls"] == {}, "everything down → still builds")
# [29/10] ריבוע 'סיכום יעדים שבועי' — מגיע מוכן מ-goals (src['goals_weekly']); מקור שנופל → בלי ריבוע, בלי קריסה
tile = {"key": "goals_weekly", "label": "סיכום יעדים שבועי", "status": "ok", "last": now - 3600}
dw = build({"goals_weekly": lambda: tile}, now, False, "2026-10-19")
ck({h["key"]: h for h in dw["health"]}.get("goals_weekly") == tile, dw["health"])
ck(all(h["key"] != "goals_weekly" for h in build({"goals_weekly": boom}, now, False, "2026-10-19")["health"]), "source down → no tile")
print("dash_data OK", _load.n)
