# tests/deals_history/test_workbook.py
import sys, os, io, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import openpyxl, msoffcrypto
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "תרומות 1.26"; ws.append(["תרומה", "סכום"])
m = wb.create_sheet("עסקאות26")
m.append(["חודש", 'מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ"])
m.append(["ינואר", 1, dt.datetime(2026, 1, 5), "קרית ים", "הרצל 1", "מוכר", "קובי", 900000, 9000])
for _ in range(400): m.append([None] * 9)
m.append(["דצמבר", 99, dt.datetime(2026, 12, 1), "קרית ים", "רחוק 1", "מוכר", "קובי", 1, 1])  # אחרי 400 ריקות — לא נקרא
buf = io.BytesIO(); wb.save(buf); raw = buf.getvalue()
w2 = D.open_workbook(raw, "")
ck(D.pick_main_sheet(w2) == "עסקאות26", D.pick_main_sheet(w2))
rows, rep = D.rows_from_workbook(w2, "kiryat_yam", 2026, ["עסקאות26"])
ck(len(rows) == 1 and rep["stopped_at"] and rep["stopped_at"] < 410, rep)
# מוצפן
enc = io.BytesIO()
f = msoffcrypto.format.ooxml.OOXMLFile(io.BytesIO(raw)); f.encrypt("Pw1", enc)
w3 = D.open_workbook(enc.getvalue(), "Pw1")
ck(D.pick_main_sheet(w3) == "עסקאות26", "decrypts")
try:
    D.open_workbook(enc.getvalue(), "bad"); ck(False, "bad pw must raise")
except Exception:
    ck(True, "")
# הכלי המקומי משתמש באותה פונקציה
import tools.import_deal_history as T
ck(T.rows_from_workbook is D.rows_from_workbook, "shared")
print("OK", n, "checks")
