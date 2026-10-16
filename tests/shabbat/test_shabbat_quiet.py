# tests/shabbat/test_shabbat_quiet.py — אייל 16/10: השתקת פוש+וואטסאפ אוטומטית — שעה לפני כניסת שבת/חג עד שעה אחרי צאתם (חיפה)
import ast, os, re, json, datetime as dt
SRC = open(os.path.join(os.path.dirname(__file__), "..", "..", "app.py"), encoding="utf-8").read()
ns = {"re": re, "json": json, "os": os, "_dt": dt}
for node in ast.parse(SRC).body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_shabbat_windows", "_in_shabbat_window"):
        exec(compile(ast.Module([node], []), "app", "exec"), ns)
W, IN = ns["_shabbat_windows"], ns["_in_shabbat_window"]
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
d = lambda s: dt.datetime.strptime(s, "%Y-%m-%d %H:%M")
ev = [["c", "2026-10-16T17:35"], ["h", "2026-10-17T18:42"],
      ["c", "2026-09-25T18:10"], ["c", "2026-09-26T18:05"], ["h", "2026-09-27T19:05"]]   # חג צמוד לשבת: שתי הדלקות, צאת אחת
w = W(ev)
ck(w == [(d("2026-09-25 18:10"), d("2026-09-27 19:05")), (d("2026-10-16 17:35"), d("2026-10-17 18:42"))], w)
ck(not IN(d("2026-10-16 16:34"), w) and IN(d("2026-10-16 16:35"), w), "שעה לפני הכניסה")
ck(IN(d("2026-10-17 12:00"), w) and IN(d("2026-10-17 19:41"), w) and not IN(d("2026-10-17 19:42"), w), "עד שעה אחרי הצאת")
ck(IN(d("2026-09-26 12:00"), w), "חג+שבת ברצף — שקט לאורך כל הרצף")
ck(not IN(d("2026-10-14 12:00"), w), "יום חול")
# הקובץ האמיתי נטען ומכסה את השנים הבאות
real = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "tools", "shabbat_times_haifa.json"), encoding="utf-8"))["events"]
rw = W(real)
ck(len(rw) > 250 and IN(d("2026-10-17 10:00"), rw) and IN(d("2031-12-27 10:00"), rw), len(rw))
ck("_shabbat_quiet_now()" in SRC.split("def _quiet_mode")[1][:600], "_quiet_mode uses the schedule")
print("OK", n, "checks")
