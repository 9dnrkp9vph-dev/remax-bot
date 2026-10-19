# tests/crm/test_team_import.py — ייבוא חד-פעמי מהגיליון + השוואת גיליון מול team_contacts (טהור)
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("team_rows_from_sheet", "team_compare", "TEAM_FILLER", "_TEAM_COLS")
imp, cmp_ = ns["team_rows_from_sheet"], ns["team_compare"]
SHEET = [["שם מלא", "טלפון", "טלפון וירטואלי", "רישיון תיווך"],
         ["דנה לוי", "050-1111111", "052-9000001", "3123", "dana@x.co"],
         ["רועי כהן", "0502222222", "", "roi@x.co"],
         ["", "0503333333"],
         ["דנה לוי", "0507777777"],            # כפול — שדה לא-ריק אחרון גובר (כמו הקוראים), מדווח
         ["משרד ביאליק", "04-6000800"]]
rows, dups = imp(SHEET)
ck([r["name"] for r in rows] == ["דנה לוי", "רועי כהן"], rows)
ck(rows[0] == {"name": "דנה לוי", "phone": "0507777777", "vphone": "052-9000001", "license": "3123", "email": "dana@x.co", "active": True, "sort": 4}, rows[0])
ck(rows[1]["license"] == "roi@x.co" and rows[1]["email"] == "", "column D kept as-is (readers decide email vs license)")
ck(dups == ["דנה לוי"], dups)
table = [{"name": "דנה לוי", "phone": "0507777777", "vphone": "052-9000001", "license": "3123", "email": "dana@x.co", "active": True},
         {"name": "רועי כהן", "phone": "0502222222", "vphone": "", "license": "roi@x.co", "email": "", "active": True},
         {"name": "חדשה", "phone": "0504444444", "vphone": "", "license": "", "email": "", "active": True},
         {"name": "עזב", "phone": "0505555555", "vphone": "", "license": "", "email": "", "active": False}]
c = cmp_(SHEET, table)
ck(c["same"] == 2 and c["only_table"] == ["חדשה"] and c["only_sheet"] == [] and c["diffs"] == [], c)
table[0] = dict(table[0], phone="0501111111")
c = cmp_(SHEET, table)
ck(c["diffs"] == [{"name": "דנה לוי", "field": "phone", "sheet": "0507777777", "table": "0501111111"}] and c["same"] == 1, c)
ck(cmp_(SHEET, [])["only_sheet"] == ["דנה לוי", "רועי כהן"], "empty table")
rows2, d2 = imp([["א", "1"], ["ב", "2"], ["א", "3"]])
ck([r["phone"] for r in rows2 if r["name"] == "א"] == ["3"] and d2 == ["א"], ("duplicate: last row wins, like the sheet readers", rows2))
print("team_import OK", _load.n)
