# tests/crm/test_crm_period.py — אייל: "אפשרות לפי חודשים ושנים": סינון תקופה (שנה / חודש) ורשימת התקופות עם מונים
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_query", "crm_periods", "_CRM_MONTHS", "_crm_norm", "inv_phone9", "CRM_VIEWS", "_crm_day")
q, per = ns["crm_query"], ns["crm_periods"]
import datetime as dt
from zoneinfo import ZoneInfo
IL = ZoneInfo("Asia/Jerusalem")
ep = lambda y, m, d, h=12: dt.datetime(y, m, d, h, tzinfo=IL).timestamp()
R = [{"key": "a", "date": ep(2026, 10, 19)}, {"key": "b", "date": ep(2026, 10, 1, 0)}, {"key": "c", "date": ep(2026, 9, 30, 23)},
     {"key": "d", "date": ep(2025, 12, 31)}, {"key": "e", "date": 0}]
NOW = ep(2026, 10, 20)
T = lambda p: q(R, "", {"period": p}, "date", "desc", 1, 50, NOW, module="signatures")["total"]
ck(T("") == 5 and T("2026") == 3 and T("2026-10") == 2 and T("2026-09") == 1 and T("2025") == 1 and T("2024") == 0,
   {p: T(p) for p in ("", "2026", "2026-10", "2026-09", "2025", "2024")})
ck(T("bad") == 5, "garbage period = no filter")
P = per(R)
ck(P[0] == ["2026", "2026", 3] and ["2026-10", "אוקטובר 2026", 2] in P and ["2026-09", "ספטמבר 2026", 1] in P and ["2025", "2025", 1] in P, P)
ck([p[0] for p in P] == ["2026", "2026-10", "2026-09", "2025", "2025-12"], ("year then its months, newest first", P))
print("crm_period OK", _load.n)
