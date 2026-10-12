# tests/deals_history/test_phone.py — אייל 12/10: 'ברוב הנכסים של חי יש נייד לקוח' — עמודת 'נייד לקוח' נפרדת, מספר בלי 0
import sys, os, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
H = ('מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ", "שם לקוח", "נייד לקוח")
hi, F = D.find_header_row([H])
ck(F.get("client_phone") == 9 and F.get("client") == 8, F)
ctx = {"branch": "bialik", "year": 2026, "sheet": "s", "row_idx": 5}
base = (13, dt.datetime(2026, 1, 5), "ביאליק", "שושנה דמרי 3", "מוכר", "חי", 2330000, 39491, "דמיטרי")
for v in (546334989, 546334989.0, "546334989", "054-6334989", "+972546334989"):
    st, r = D.normalize_row(base + (v,), F, ctx)
    ck(st == "ok" and r["client_phone"] == "0546334989" and r["client_name"] == "דמיטרי", (v, r and r["client_phone"]))
st, r = D.normalize_row(base + (None,), F, ctx)
ck(r["client_phone"] == "", "no phone")
# בלי עמודת נייד — הטלפון מתוך 'טל ושם לקוח' כמו קודם
H2 = ('מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "טל ושם לקוח")
hi2, F2 = D.find_header_row([H2])
st, r = D.normalize_row((1, dt.datetime(2026, 1, 5), "ביאליק", "הרצל 1", "מוכר", "חי", 900000, "דנה 0521234567"), F2, ctx)
ck(r["client_phone"] == "0521234567" and r["client_name"] == "דנה", r)
print("OK", n, "checks")
