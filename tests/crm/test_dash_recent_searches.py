# tests/crm/test_dash_recent_searches.py — לוח הבקרה: 10 חיפושי ה-AI האחרונים (נכסים) באתר ובאפי — אייל 20/10
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_recent_searches", "_CRM_SEARCH_SITE", "_CRM_SEARCH_EFFIE")
f = ns["crm_recent_searches"]
now = 1_800_000_000.0
act = [{"ts": now - 60, "name": "אתר", "role": "site", "action": "חיפוש AI באתר", "detail": "4 חדרים באפקה · 12 נכסים"},
       {"ts": now - 120, "name": "רפי", "role": "agent", "action": "חיפוש נכסים", "detail": "5 חדרים במוצקין"},
       {"ts": now - 150, "name": "רפי", "role": "agent", "action": "חיפוש נכסים", "detail": "5 חדרים במוצקין"},     # אותו חיפוש שוב — פעם אחת
       {"ts": now - 200, "name": "דנה", "role": "agent", "action": "חיפוש נכסים", "detail": "(כל הנכסים)"},        # בלי טקסט — לא חיפוש AI
       {"ts": now - 300, "name": "דנה", "role": "agent", "action": "חיפוש נכס נולד", "detail": "5 חדרים במוצקין"}]  # כפילות של אותו חיפוש
act += [{"ts": now - 1000 - i, "name": "אתר", "role": "site", "action": "חיפוש AI באתר", "detail": "חיפוש %d · %d נכסים" % (i, i)} for i in range(70)]
ck(len(f(act)["site"]) == 50, "default: 50 per column (אייל 20/10)")
R = f(act, 10)
ck(len(R["site"]) == 10 and R["site"][0] == {"ts": now - 60, "q": "4 חדרים באפקה", "n": "12", "who": ""}, R["site"][:2])
ck(R["effie"] == [{"ts": now - 120, "q": "5 חדרים במוצקין", "n": "", "who": "רפי"}], R["effie"])
print("dash_recent_searches OK")
