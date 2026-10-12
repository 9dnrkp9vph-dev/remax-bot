# tests/deals_history/test_sync_fixes.py — ממצאי הביקורת של שלב 2א (12/10)
import sys, os, io, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import openpyxl
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
# 1. ההגנה לא תלויה בזיכרון: אחרי אתחול (last=None) קובץ חלקי לא מסמן הכל כחסר
ex = [dict(src_key="k%d" % i, src_hash="h", src_path="/d/main.xlsx") for i in range(20)]
p = D.sync_plan(ex, [{"src_key": "k1"}, {"src_key": "k2"}, {"src_key": "k3"}], switched=False)
ck(p["missing"] == [] and p["guarded"], ("coverage <60% guarded even without switch flag", p["missing"][:3]))
p2 = D.sync_plan(ex, [{"src_key": "k%d" % i} for i in range(19)], switched=False)
ck(p2["missing"] == ["k19"] and not p2["guarded"], "one real deletion is marked")
ck(D.sync_plan(ex[:3], [], switched=False)["missing"] == ["k0", "k1", "k2"], "tiny sheet (<5 rows) not guarded")
# 2. שורות שנעלמו לא נספרות בדוחות/רשימות/השוואה/שלי
R = [dict(id="1", year=2026, branch="bialik", agent="משה", deal_date="2026-01-01", street="הרצל 1", city="קרית ים", side="מוכר",
          deal_amount=1000000, commission_net=10000, paid_amount=None, reported_date=None),
     dict(id="2", year=2026, branch="bialik", agent="משה", deal_date="2026-01-02", street="הרצל 1", city="קרית ים", side="מוכר",
          deal_amount=2000000, commission_net=20000, paid_amount=None, reported_date=None, missing_since="2026-10-12T00:00:00Z")]
act = D.active_rows(R)
ck([r["id"] for r in act] == ["1"], "active excludes missing")
ck(D.stats(act, 2026)["total"]["commission"] == 10000 and [r["id"] for r in D.unpaid(act)] == ["1"], "stats/unpaid on active")
# 3. מפתח הסנכרון בלי שם הגיליון (שינוי שם טאב לא משכפל); בלי מס"ד — לפי תוכן, לא לפי מיקום
H = ('מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה")
hi, F = D.find_header_row([H])
c1 = {"branch": "bialik", "year": 2026, "sheet": "עסקאות26", "row_idx": 5, "key_mode": "sync"}
row = (7, dt.datetime(2026, 1, 5), "קרית ים", "הרצל 1", "מוכר", "משה", 900000)
k1 = D.normalize_row(row, F, c1)[1]["src_key"]
k2 = D.normalize_row(row, F, dict(c1, sheet="עסקאות 2026 חדש", row_idx=9))[1]["src_key"]
ck(k1 == k2 == "bialik|2026|7", (k1, k2))
nos = (None,) + row[1:]
a = D.normalize_row(nos, F, c1)[1]["src_key"]; b = D.normalize_row(nos, F, dict(c1, row_idx=40))[1]["src_key"]
ck(a == b and a.startswith("bialik|2026|h"), (a, b))
ck(D.normalize_row(nos[:6] + (950000,), F, c1)[1]["src_key"] == a, "content key ignores amount change")
ck(D.normalize_row(row, F, dict(c1, key_mode=""))[1]["src_key"] == "bialik|2026|עסקאות26|7", "history import keys unchanged")
# הסנכרון משתמש במפתח הזה
def xlsx(title):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = title; ws.append(list(H)); ws.append(list(row))
    b_ = io.BytesIO(); wb.save(b_); return b_.getvalue()
ok, rep = D.rows_from_workbook(D.open_workbook(xlsx("גיליון חדש"), ""), "bialik", 2026, ["גיליון חדש"], key_mode="sync")
ck(ok[0]["src_key"] == "bialik|2026|7", ok[0]["src_key"])
print("OK", n, "checks")
