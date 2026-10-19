# tests/crm/test_contacts_source.py — מתג CONTACTS_SOURCE: אותם נתונים מהגיליון ומ-team_contacts → פלט זהה
# בארבעת הקוראים (כניסה, ספרייה, מיילים, וירטואלי). נפילה ל-Supabase → הגיליון.
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
SHEET = [["שם מלא", "טלפון", "טלפון וירטואלי", "רישיון תיווך", "מייל"],
         ["דנה לוי", "050-1111111", "052-9000001", "3123", "dana@x.co"],
         ["רועי כהן", "0502222222", "", "roi@x.co"],          # מייל בעמודה D, בלי E
         ["משרד ביאליק", "04-6000800"],
         ["מיכל", ""]]
class R:
    status_code = 200; text = ""
    def json(s): return {"values": SHEET}
CALLS = []
A.GOOGLE_SHEETS_API_KEY = "k"
A.requests.get = lambda url, timeout=None: (CALLS.append(url), R())[1]
A._load_config = lambda: {}
def snap():
    A._contacts_cache_clear()
    return (A.fetch_agents_phones(), A.fetch_agents_full(), A.web_agent_emails(), A.fetch_agent_virtual_phones())
os.environ.pop("CONTACTS_SOURCE", None)
sheet = snap()
ck(sheet[0] == {"דנה לוי": "050-1111111", "רועי כהן": "0502222222", "משרד ביאליק": "04-6000800"} or "משרד ביאליק" not in sheet[0], sheet[0])
ck(sheet[0]["דנה לוי"] == "050-1111111" and "שם מלא" not in sheet[0], sheet[0])
ck(sheet[2].get("p:501111111") == "dana@x.co" and sheet[2].get("p:502222222") == "roi@x.co", sheet[2])
ck(len(CALLS) == 1, ("one sheet fetch serves all four readers", len(CALLS)))
class FakeSB:
    def enabled(s): return True
    def team_fetch(s, active_only=False):
        return [{"name": r[0], "phone": r[1] if len(r) > 1 else "", "vphone": r[2] if len(r) > 2 else "",
                 "license": r[3] if len(r) > 3 else "", "email": r[4] if len(r) > 4 else "", "active": True}
                for r in SHEET[1:]] + ([] if active_only else [{"name": "עזב", "phone": "0509999999", "active": False, "vphone": "", "license": "", "email": ""}])
A._sbdb = FakeSB()
os.environ["CONTACTS_SOURCE"] = "supabase"
CALLS.clear()
sup = snap()
ck(sup == sheet, ("identical output from both sources", sup, sheet))
ck(not CALLS, "no Google Sheets call in supabase mode")
class Broken(FakeSB):
    def team_fetch(s, active_only=False): raise RuntimeError("down")
A._sbdb = Broken()
fb = snap()
ck(fb == sheet and CALLS, "supabase down → falls back to the sheet")
os.environ.pop("CONTACTS_SOURCE", None)
print("contacts_source OK", n)
