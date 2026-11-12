# -*- coding: utf-8 -*-
"""[CRM תהליכים 12/11] מודול 'תהליכים' מעל deals.json. python3 tests/crm/test_processes.py"""
import os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import effie_v2 as E
items = [
    {"id": "1", "agents": ["קובי חמו"], "notes": "עפרה חזה 16", "side1": "מוכר", "side2": "קונה", "price": "1,950,000",
     "stage": 'אצל עו"ד', "lawyers": "כהן", "by": "הודיה צרויה", "ts": time.time()},
    {"id": "2", "agents": ["נדב רייזר", "רפי"], "notes": "הנוטר 28", "deal": True, "sale_price": "2900000",
     "close_date": "10/11/2026", "commission": "58000", "by": "נדב רייזר", "ts": 1700000000},
    {"id": "3", "agents": ["ליקה אוברוב"], "notes": "דליה 9", "offer": True, "offer_seller": "2.1M", "offer_buyer": "1.9M", "by": "ליקה אוברוב", "ts": 1700000001},
]
R = E.crm_process_records(items)
fails = []
def ck(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)
by = {r["key"]: r for r in R}
ck(len(R) == 3, "3 רשומות")
ck(by["p:1"]["state"] == 'אצל עו"ד' and by["p:1"]["price"] == 1950000 and by["p:1"]["sides"] == "מוכר / קונה", "תהליך פתוח: שלב, מחיר, צדדים")
ck(by["p:2"]["state"] == "נסגר לעסקה" and by["p:2"]["agent"] == "נדב רייזר + רפי" and by["p:2"]["close_date"] > 0, "עסקה: מצב, שני סוכנים, תאריך סגירה")
ck(by["p:3"]["state"] == "הצעה" and "מוכר: 2.1M" in by["p:3"]["offer"], "הצעה")
import datetime
t = datetime.date.today()
V = E.CRM_VIEWS["processes"]
ck([r["key"] for r in R if V["open"](r, t)] == ["p:1", "p:3"], "תצוגת פתוחים")
ck([r["key"] for r in R if V["lawyer"](r, t)] == ["p:1"], "אצל עו\"ד")
ck([r["key"] for r in R if V["closed"](r, t)] == ["p:2"], "נסגרו")
ck([r["key"] for r in R if V["today"](r, t)] == ["p:1"], "נפתחו היום")
canon = lambda n: "".join(str(n).split())
ck([r["key"] for r in E.crm_scope_filter("processes", R, {canon("רפי")}, canon)] == ["p:2"], "היקף סוכן: עסקה משותפת")
ck([r["key"] for r in E.crm_scope_filter("processes", R, {canon("הודיה צרויה")}, canon)] == ["p:1"], "היקף: מי שפתח")
m = E.CRM_MODULES["processes"]
ck(all(c in [x[0] for x in m["columns"]] for c in m["default_cols"]), "עמודות ברירת מחדל קיימות")
ck("processes" in E.CRM_ACCESS_MODULES, "מופיע במסך ההרשאות")
print("FAIL" if fails else "OK"); raise SystemExit(1 if fails else 0)
