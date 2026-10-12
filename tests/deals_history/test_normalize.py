# tests/deals_history/test_normalize.py
import sys, os, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
H26 = ("חודש", 'מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סטאוס טיפול בגבייה", "טל ושם לקוח",
       "אייליסט", "על מי לדווח", "מתווך בצד השני", "הערה", 'ממוצע עמלה לפני מע"מ', "הנחה לפני מעמ", "סכום העסקה",
       'עמלה כולל מע"מ', "עמלה לפני מעמ", "מאיפה הגיע הלקוח", "התקבל כסף", "הופקד", "חשבונית", "קבלה",
       "דווח במערכת", "אישור לרימקס", "התחשבנות סוכן", 'עו"ד / הערות')
rows = [("דוח עסקאות",) + (None,) * 26, H26]
hi, F = D.find_header_row(rows)
ck(hi == 1, "header row")
ck(F["agent"] == 6 and F["street"] == 4 and F["commission_net"] == 17 and F["serial"] == 1, ("fields", F))
ck("commission_avg" not in F and F.get("commission_net") != 13, "ממוצע עמלה is not commission_net")
ck(F["other_broker"] == 11 and F["lawyer_notes"] == 26 and F["receipt_no"] == 22, "exact before prefix")
ctx = {"branch": "motzkin", "year": 2025, "sheet": "עסקאות25", "row_idx": 7}
r = (1, 12, dt.datetime(2025, 1, 14), "קרית מוצקין", "הגפן 4", "מוכר", " משה  כהן ", "טרם שולם",
     "דנה לוי 050-1234567", None, None, "אנגלו סכסון", "", 9000, 0, "1,850,000", 21240, 18000, "יד2",
     None, None, 4512, 4513, dt.datetime(2025, 2, 3), None, 9000, "עו\"ד כהן")
st, row = D.normalize_row(r, F, ctx)
ck(st == "ok", st)
ck(row["src_key"] == "motzkin|2025|עסקאות25|12", row["src_key"])
ck(row["deal_date"] == "2025-01-14" and row["city"] == "קרית מוצקין" and row["street"] == "הגפן 4", row)
ck(row["side"] == "מוכר" and row["agent"] == "משה כהן", row["agent"])
ck(row["client_name"] == "דנה לוי" and row["client_phone"] == "0501234567", (row["client_name"], row["client_phone"]))
ck(row["deal_amount"] == 1850000 and row["commission_net"] == 18000 and row["commission_gross"] == 21240, row)
ck(row["paid_amount"] is None and row["invoice_no"] == "4512" and row["reported_date"] == "2025-02-03", row)
ck(row["raw"]["התחשבנות סוכן"] == "9000" and "agent_settlement" not in row, "settlement only in raw")
ck(row["year"] == 2025 and row["branch"] == "motzkin", "ctx")
# בלי מס"ד → מספר שורה
r2 = list(r); r2[1] = None
ck(D.normalize_row(tuple(r2), F, ctx)[1]["src_key"] == "motzkin|2025|עסקאות25|r7", "row fallback")
# שורת סיכום / ריקה
ck(D.normalize_row((None,) * 27, F, ctx)[0] == "skip", "empty")
s = [None] * 27; s[6] = 'סה"כ'; s[17] = 50000
ck(D.normalize_row(tuple(s), F, ctx)[0] == "skip", "summary")
s = [None] * 27; s[0] = "ינואר"; s[17] = 50000
ck(D.normalize_row(tuple(s), F, ctx)[0] == "skip", "month total without agent")
s = [None] * 27; s[6] = "משה"
ck(D.normalize_row(tuple(s), F, ctx)[0] == "broken", "agent only = broken")
# מבנה 2016: כתובת אחת
H16 = ("תאריך עסקה", "כתובת", "קונה / מוכר", "סוכן", "הנחה", "סכום עסקה", "עמלה כולל מעמ", "עמלה לפני מעמ", "הערות",
       "התקבל כסף", "הופקד", "חשבונית מס קבלה", "אישור לרימקס", "התחשבנות סוכן", "עו\"ד ויסמן / מאיוסט")
hi, F16 = D.find_header_row([H16])
st, row = D.normalize_row(("12/05/16", "הרצל 5 קרית ביאליק", "קונה", "נחום", None, "980000", None, "17,000", None,
                           "17000", "כן", "1023", None, None, "ויסמן"), F16, {"branch": "bialik", "year": 2016, "sheet": "מלא", "row_idx": 3})
ck(st == "ok" and row["deal_date"] == "2016-05-12" and row["city"] == "קרית ביאליק" and row["street"] == "הרצל 5", row)
ck(row["paid_amount"] == 17000 and row["invoice_no"] == "1023" and row["lawyer_notes"] == "ויסמן", row)
# עזרים
ck(D.parse_date(45306) == dt.date(2024, 1, 15), "excel serial")
ck(D.parse_date("3.2.2021") == dt.date(2021, 2, 3) and D.parse_date("טקסט") is None, "date text")
ck(D.parse_num("₪ 1,250,000") == 1250000 and D.parse_num("כן") is None and D.parse_num(0) == 0, "num")
ck(D.split_client("0521234567 יוסי") == ("יוסי", "0521234567") and D.split_client("") == ("", ""), "client")
ck(D.norm_side("משכיר") == "משכיר" and D.norm_side("שוכר") == "שוכר" and D.norm_side("קונה+מוכר") == "קונה+מוכר", "side")
print("OK", n, "checks")
