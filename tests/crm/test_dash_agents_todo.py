# tests/crm/test_dash_agents_todo.py — לוח הבקרה: טבלת סוכנים לפי תקופה + 'מחכה לטיפול' (אייל 20/10: "גם וגם")
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_agent_table", "crm_todo", "crm_period_bounds", "crm_ts", "inv_parse_dt", "bs_p9", "_CRM_NB_CONTACT", "_CRM_BPAGE_SEND")
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 20, 15, 0, tzinfo=IL).timestamp()           # שלישי
B = ns["crm_period_bounds"](now)
ck(datetime.datetime.fromtimestamp(B["day"], IL).strftime("%d/%m %H:%M") == "20/10 00:00", B)
ck(datetime.datetime.fromtimestamp(B["week"], IL).strftime("%a %d/%m") == "Sun 18/10", ("week starts Sunday", B))
ck(datetime.datetime.fromtimestamp(B["month"], IL).strftime("%d/%m") == "01/10" and datetime.datetime.fromtimestamp(B["year"], IL).strftime("%d/%m") == "01/01", B)
ans = lambda st: str(st).upper() in ("ANSWER", "CALL2CALL")
h = {"ts": ns["crm_ts"], "answered": ans, "canon": lambda n: {"רפי ": "רפי"}.get(n, n)}
calls = [{"agent": "רפי ", "status": "ANSWER", "received_at": "20/10/2026 10:00"},
         {"agent": "רפי", "status": "NOANSWER", "received_at": "20/10/2026 11:00"},
         {"agent": "דנה", "status": "ANSWER", "received_at": "05/10/2026 10:00"}]
sigs = [{"agent": "דנה", "received_at": "19/10/2026 12:00"}, {"agent": "רפי", "received_at": "02/03/2026 12:00"}]
buyers = [{"agent": "רפי", "date": "20/10/2026"}]
act = [{"ts": now - 600, "name": "רפי", "action": "דף קונה — שליחה"}, {"ts": now - 700, "name": "דנה", "action": "📲 וואטסאפ — נכס נולד"},
       {"ts": now - 800, "name": "", "action": "דף קונה — שליחה"}]
usage = {"day": [{"name": "רפי", "min": 40}], "month": [{"name": "דנה", "min": 300}]}
T = ns["crm_agent_table"](calls, sigs, buyers, act, usage, B, h)
day = {r["name"]: r for r in T["day"]}
ck(day["רפי"] == {"name": "רפי", "calls": 2, "answered": 1, "sigs": 0, "buyers": 1, "bpage": 1, "nb": 0, "min": 40}, day["רפי"])
ck(day["דנה"]["nb"] == 1 and day["דנה"]["calls"] == 0 and "" not in day, day)
ck(T["day"][0]["name"] == "רפי", ("most active first", T["day"]))
mon = {r["name"]: r for r in T["month"]}
ck(mon["דנה"]["answered"] == 1 and mon["דנה"]["sigs"] == 1 and mon["דנה"]["min"] == 300, mon["דנה"])
ck({r["name"]: r["sigs"] for r in T["year"]} == {"רפי": 1, "דנה": 1}, T["year"])
# ── מחכה לטיפול ──
cl = [{"caller_phone": "0541111111", "agent": "רפי", "status": "NOANSWER", "received_at": "20/10/2026 09:00"},   # חזרו אליו
      {"caller_phone": "0541111111", "agent": "רפי", "status": "CALL2CALL", "received_at": "20/10/2026 09:30"},
      {"caller_phone": "0542222222", "agent": "דנה", "status": "NOANSWER", "received_at": "20/10/2026 12:00"},   # לא חזרו
      {"caller_phone": "0542222222", "agent": "דנה", "status": "BUSY", "received_at": "20/10/2026 12:05"},
      {"caller_phone": "0543333333", "agent": "דנה", "status": "NOANSWER", "received_at": "10/10/2026 12:00"}]  # ישנה מדי
sr = [{"client": "א", "agent": "רפי", "type": "קונים", "status": "ממתין", "date": now - 3 * 86400, "link": "/s/x"},
      {"client": "ב", "agent": "רפי", "type": "קונים", "status": "ממתין", "date": now - 3600, "link": ""},           # טרייה מדי
      {"client": "ג", "agent": "רפי", "type": "בלעדיות", "status": "נחתם", "date": now - 3 * 86400, "link": ""}]
ac = [{"ts": now - 3600, "name": "רפי", "action": "סימון בדף קונה", "detail": "משה: מתאים · הרצל 5"},
      {"ts": now - 3600, "name": "רפי", "action": "סימון בדף קונה", "detail": "משה: לא מתאים · הרצל 7"}]
nb = [{"k": "a", "נראה לראשונה": "20/10/2026 10:00", "רחוב": "הנשיא 4", "עיר": "קרית ביאליק", "מחיר": "2000000", "קישור": "https://y/1"},
      {"k": "b", "נראה לראשונה": "20/10/2026 11:00", "רחוב": "הרצל 1", "עיר": "קרית ים"},
      {"k": "c", "נראה לראשונה": "15/10/2026 11:00", "רחוב": "ישן 1", "עיר": "קרית ים"}]
D = ns["crm_todo"](cl, sr, ac, nb, {"b": ["רפי"]}, now, {"ts": ns["crm_ts"], "answered": ans, "nb_key": lambda r: r["k"]})
ck([m["phone"] for m in D["missed"]] == ["0542222222"] and D["missed"][0]["agent"] == "דנה" and D["missed"][0]["tries"] == 2, D["missed"])
ck([s["client"] for s in D["pending_sigs"]] == ["א"], D["pending_sigs"])
ck(len(D["likes"]) == 1 and "מתאים · הרצל 5" in D["likes"][0]["detail"], D["likes"])
ck(D["nb_untouched"]["n"] == 1 and D["nb_untouched"]["list"][0]["address"] == "הנשיא 4, קרית ביאליק", D["nb_untouched"])
print("dash_agents_todo OK")
