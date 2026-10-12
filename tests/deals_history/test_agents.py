# tests/deals_history/test_agents.py — סוכן ברירת מחדל (קרית ים) + פיצול שמות משותפים (אייל 12/10)
import sys, os, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
H = ("תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ")
hi, F = D.find_header_row([H])
ctx = {"branch": "kiryat_yam", "year": 2025, "sheet": "s", "row_idx": 4, "default_agent": "קובי חמו"}
st, row = D.normalize_row((dt.datetime(2025, 3, 1), "קרית ים", "הרצל 1", "מוכר", None, 900000, 9000), F, ctx)
ck(st == "ok" and row["agent"] == "קובי חמו", (st, row and row["agent"]))
ck(D.normalize_row((None, None, None, None, None, None, 30000), F, ctx)[0] == "skip", "total row without date/street stays skipped")
ck(D.normalize_row((dt.datetime(2025, 3, 1), "קרית ים", "הרצל 1", "מוכר", None, 900000, 9000), F, dict(ctx, default_agent=""))[0] == "broken", "no default → broken (reported, not silently dropped)")
ck(D.split_agents("אלי שמול + יהודית שמול") == ["אלי שמול", "יהודית שמול"], "split +")
ck(D.split_agents("רון/דודו") == ["רון", "דודו"] and D.split_agents("רון \\סיון") == ["רון", "סיון"], "split / \\")
ck(D.split_agents("אלעד ויזמן") == ["אלעד ויזמן"] and D.split_agents("שאול + איליה") == ["שאול", "איליה"], "no split on ו — surnames like ויזמן stay whole")
ck(D.split_agents("") == [] and D.split_agents("נדב רייזר") == ["נדב רייזר"], "single/empty")
ck(D.canon_agent("ליאור וקבלי", "bialik", {"bialik|ליאור וקבלי": "ליאור גרונפינקל + מאור קבלי"}, lambda x: x.strip()) == "ליאור גרונפינקל + מאור קבלי", "combo mapped")
ck(D.canon_agent("בן", "bialik", {"bialik|בן": "בן + קדוש"}, lambda x: {"בן": "בן קדוש"}.get(x, x)) == "בן קדוש + קדוש", "canon per member")
print("OK", n, "checks")
