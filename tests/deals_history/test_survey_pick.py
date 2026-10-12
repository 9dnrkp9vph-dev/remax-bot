# tests/deals_history/test_survey_pick.py — בחירת הקובץ לשנה: השמירה האחרונה מבין קבצי המעקב (אייל 12/10)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.deals_survey import pick_file, YEARS
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
MT = {"a/מעקב עסקאות 2022 .xlsx": 200, "a/מעקב עסקאות 2022 סופי.xlsx": 100,
      "a/x (Eyal Shmul's conflicted copy 2026-03-19).xlsx": 300, "a/x.xlsx": 100,
      "a/sms.xlsx": 999, "a/מעקב עסקאות 2021.xlsx": 10, "a/תזרים.xlsx": 999,
      "a/~$מעקב עסקאות 2020.xlsx": 999, "a/מעקב עסקאות 2020.xlsx": 5}
mt = MT.get
ck(pick_file(["a/מעקב עסקאות 2022 .xlsx", "a/מעקב עסקאות 2022 סופי.xlsx"], mt) == "a/מעקב עסקאות 2022 .xlsx", "newest wins, not 'סופי'")
ck(pick_file(["a/x (Eyal Shmul's conflicted copy 2026-03-19).xlsx", "a/x.xlsx"], mt) == "a/x (Eyal Shmul's conflicted copy 2026-03-19).xlsx", "newest even if conflicted copy")
ck(pick_file(["a/sms.xlsx", "a/מעקב עסקאות 2021.xlsx"], mt) == "a/מעקב עסקאות 2021.xlsx", "non-tracking file (sms) ignored even if newer")
ck(pick_file(["a/תזרים.xlsx", "a/sms.xlsx"], mt) == "a/תזרים.xlsx" or pick_file(["a/תזרים.xlsx", "a/sms.xlsx"], mt) == "a/sms.xlsx", "only non-tracking files → newest of them")
ck(pick_file(["a/~$מעקב עסקאות 2020.xlsx", "a/מעקב עסקאות 2020.xlsx"], mt) == "a/מעקב עסקאות 2020.xlsx", "office lock file ignored")
ck(pick_file([], mt) is None, "empty")
ck(YEARS == list(range(2016, 2026)), YEARS)
print("OK", n, "checks")
