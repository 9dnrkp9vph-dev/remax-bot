# tests/deals_history/test_review_fixes.py — ממצאי הביקורת הסופית (12/10)
import sys, os, json, tempfile, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import openpyxl
import deals_history as D
from tools.import_deal_history import rows_from_workbook
from tools import deals_survey as SV
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
H = ("תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "הערה")
hi, F = D.find_header_row([H])
KY = {"branch": "kiryat_yam", "year": 2025, "sheet": "s", "row_idx": 9, "default_agent": "קובי חמו"}
# 1. שורת סה"כ בעמודה אחרת (לא בעמודת הסוכן) לא נכנסת כעסקה של סוכן ברירת המחדל
ck(D.normalize_row((None, None, 'סה"כ', None, None, 5000000, None), F, KY)[0] == "skip", "total in street col")
ck(D.normalize_row((None, 'סיכום', None, None, None, 5000000, None), F, KY)[0] == "skip", "summary in city col")
st, row = D.normalize_row((dt.datetime(2025, 1, 1), "קרית ים", "הרצל 1", "מוכר", None, 900000, "סיכום עם עו\"ד ביום ראשון"), F, KY)
ck(st == "ok" and row["agent"] == "קובי חמו", "long note mentioning סיכום is not a total row")
# 2. עסקה בלי סוכן (ובלי ברירת מחדל) → שבורה, לא נעלמת בשקט
ck(D.normalize_row((dt.datetime(2025, 1, 1), "קרית ים", "הרצל 1", "מוכר", None, 900000, None), F, dict(KY, default_agent=""))[0] == "broken", "agentless deal → broken")
ck(D.normalize_row((None, None, None, None, None, None, "הערה"), F, dict(KY, default_agent=""))[0] == "skip", "note-only row stays skip")
# 3. מס"ד כפול באותו גיליון — לא דורס; מדווח
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "ע"
ws.append(['מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה"])
ws.append([5, dt.datetime(2025, 1, 2), "קרית ים", "הרצל 1", "מוכר", "משה", 1000000])
ws.append([5, dt.datetime(2025, 1, 3), "קרית ים", "הרצל 2", "קונה", "משה", 900000])
ok, rep = rows_from_workbook(wb, "motzkin", 2025, ["ע"])
ck(len({r["src_key"] for r in ok}) == 2 and rep["dup_keys"] == ["motzkin|2025|ע|5"], (rep.get("dup_keys"), [r["src_key"] for r in ok]))
# 4. הסקירה לא דורסת קובץ מאושר
d = tempfile.mkdtemp()
p1 = SV.write_proposals(d, {"bialik|2016": {"file": "a", "sheets": ["x"]}}, {"bialik|נדב": 3})
ck(p1 == [os.path.join(d, "deals_sources.json"), os.path.join(d, "deals_agent_map.json")], p1)
json.dump({"bialik|נדב": "נדב רייזר"}, open(p1[1], "w", encoding="utf-8"), ensure_ascii=False)
p2 = SV.write_proposals(d, {"bialik|2016": {"file": "b", "sheets": []}}, {"bialik|נדב": 3})
ck(all(p.endswith(".proposed.json") for p in p2), p2)
ck(json.load(open(p1[1], encoding="utf-8")) == {"bialik|נדב": "נדב רייזר"}, "approved map untouched")
# 5. כתובת: עיר רק בסוף — 'דרך עכו 119' נשאר רחוב
ck(D._split_address("דרך עכו 119") == ("", "דרך עכו 119"), D._split_address("דרך עכו 119"))
ck(D._split_address("הרצל 5 קרית ביאליק") == ("קרית ביאליק", "הרצל 5") and D._split_address("הרצל 5, חיפה") == ("חיפה", "הרצל 5"), "city at end")
# 6. הדף: כל קריאת רשת עם catch (לא נתקע על 'טוען…')
src = open(os.path.join(os.path.dirname(__file__), "..", "..", "deals_history.py"), encoding="utf-8").read()
a = src.index("<script>", src.index("V2_HISTORY_HTML = ")); b = src.index("</script>", a); js = src[a:b]
import re as _re
calls = _re.findall(r"GET\((?:withQ\()?(?:'/v2/api/deals/history/|u \+ encodeURIComponent)", js)
catches = js.count("}).catch(function(){")
ck(len(calls) >= 8 and catches >= len(calls) + 1, ("every fetch (+whoami) has catch", len(calls), catches))
# אייל 12/10: 'קובי לא עשה עמלה כזאת' — שורת סכום בלי תווית (רק מספרים) לא נספרת כעסקה של סוכן ברירת המחדל
ck(D.normalize_row((None, None, None, None, None, 18000000, None), F, KY)[0] == "skip", "numbers-only row (sum) not a Kobi deal")
H2 = ("תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ")
hi2, F2 = D.find_header_row([H2])
ck(D.normalize_row((None, None, None, None, None, 30000000, 840000), F2, KY)[0] == "skip", "sum row with commission")
ck(D.normalize_row((dt.datetime(2026, 1, 1), None, None, "מוכר", None, 900000, 20000), F2, KY)[0] == "ok", "dated row still Kobi's")
rows_ = [dict(id="a", deal_date="2026-01-01", street="הרצל 1", client_name=""), dict(id="b", deal_date="", street="", client_name="", commission_net=840000),
         dict(id="c", deal_date="", street="", client_name="דנה")]
ck([r["id"] for r in D.active_rows(rows_)] == ["a", "c"], "active_rows drops non-deal rows already in the table")
print("OK", n, "checks")
