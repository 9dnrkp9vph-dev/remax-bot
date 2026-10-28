"""[GOALS2 29/10] מי שנרשם בניהול נכנס לטבלת הצוות. python3 tests/goals/test_team_sync.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crm"))
import _load
from _load import ck

ns = _load.load("team_sync_missing", "_TEAM_SYNC_SKIP")
f = ns["team_sync_missing"]
key = lambda s: "".join(str(s or "").split())
l9 = lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:]

agents = [{"name": "נחמי זקס", "phone": "0521111111"},
          {"name": "מירי ישראלוב", "phone": "0522222222"},
          {"name": "רון לוי", "phone": "0523333333"},          # כבר בטבלה לפי שם
          {"name": "רוני  לוי", "phone": "0524444444"},        # כבר בטבלה לפי טלפון (שם אחר)
          {"name": "מושהה", "phone": "0525555555"},
          {"name": "נמחקה", "phone": "0526666666"},
          {"name": "חשבון בדיקה", "phone": "0527777777"},
          {"name": "מנהל", "phone": "0528888888"},
          {"name": "בלי טלפון", "phone": ""},
          {"name": "הושבת", "phone": "0529999999"},
          {"name": "נחמי זקס", "phone": "0521111111"},         # כפול בקונפיג
          "junk"]
team = [{"name": "רון לוי", "phone": "0500000000", "active": True},
        {"name": "מישהו", "phone": "0524444444", "active": True},
        {"name": "הושבת", "phone": "0501231234", "active": False}]   # מושבת בצוות — לא חוזר לבד
out = f(agents, team, {"525555555"}, {key("נמחקה")}, key, l9)
ck([a["name"] for a in out] == ["נחמי זקס", "מירי ישראלוב"], out)
ck(out[0] == {"name": "נחמי זקס", "phone": "0521111111", "active": True}, out[0])
ck(f([], team, set(), set(), key, l9) == [], "empty config")
ck(f(agents[:1], [], set(), set(), key, l9)[0]["name"] == "נחמי זקס", "empty team")

bad = [{"name": "מנהל · 1234", "phone": "0541111111"}, {"name": "eyal-shmul", "phone": "0542222222"},
       {"name": "x@y.com", "phone": "0543333333"}]
ck(f(bad, [], set(), set(), key, l9) == [], "only real names")
ck("fetch_pings_today" in src.split("def _team_sync_run")[1][:1500] if (src := _load._SRC) else False, "also people who logged in")
# החיווט: ההזמנה מפעילה סנכרון, ויש בדיקה תקופתית שרצה ברקע
src = _load._SRC
ck('_team_sync_bg(s.get("name", "") or "ניהול")' in src, "invite triggers sync")
ck("def _team_sync_tick():" in src and "_TEAM_SYNC_EVERY = 6 * 3600" in src, "periodic sync")
ck('!= "supabase"' in src.split("def _team_sync_run")[1][:600], "only when contacts come from the table")
print("team_sync OK", _load.n)
