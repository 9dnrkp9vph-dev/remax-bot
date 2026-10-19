# tests/crm/test_dash_series.py — דשבורד: סדרה יומית (יום ישראלי) לגרפים
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_daily_series", "crm_ts", "inv_parse_dt")
series = ns["crm_daily_series"]
rows = [{"t": "2026-10-19T06:00:00Z"}, {"t": "18/10/2026 23:30"}, {"t": "2026-10-18T22:30:00Z"}, {"t": ""}, {"t": "2026-09-01"}, {"t": "2026-10-20T09:00:00Z"}]
s = series(rows, lambda r: r["t"], 3, "2026-10-19")
ck(s == [0, 1, 2], s)   # 22:30Z = 00:30 ב-19/10 (שעון חורף +2); עתידי ומחוץ לטווח לא נספרים
ck(series([], lambda r: r, 30, "2026-10-19") == [0] * 30, "empty")
print("dash_series OK", _load.n)
