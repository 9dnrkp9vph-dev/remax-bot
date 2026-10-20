# tests/crm/test_dash_agent_listings.py — לוח הבקרה: כל הסוכנים וכמה מודעות יש לכל אחד (בלעדי / רגיל / הכל) — אייל 20/10
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_agent_listings")
f = ns["crm_agent_listings"]
P = [{"source": "המשרד", "agent": "רפי", "excl": "בלעדי", "deal": "מכירה"},
     {"source": "המשרד", "agent": "רפי", "excl": "רגיל", "deal": "מכירה"},
     {"source": "המשרד", "agent": "רפי", "excl": "", "deal": "השכרה"},
     {"source": "המשרד", "agent": "רפי", "excl": "בלעדי", "deal": "מכירה", "delisted": True},     # ירד מפרסום — לא נספר
     {"source": "המשרד", "agent": "דנה ", "excl": "בלעדי", "deal": "מכירה"},
     {"source": "המשרד", "agent": "", "excl": "רגיל", "deal": "מכירה"},
     {"source": "פרטי", "agent": "", "excl": "", "deal": "מכירה"},                              # לא של המשרד
     {"source": "שת\"פ", "agent": "", "excl": "בלעדי", "deal": "מכירה"}]
R = f(P, ["רפי", "דנה", "אוצר"], lambda n: n.strip())
by = {r["name"]: r for r in R["rows"]}
ck(by["רפי"] == {"name": "רפי", "excl": 1, "reg": 1, "total": 3, "rent": 1}, by["רפי"])
ck(by["דנה"]["total"] == 1 and by["דנה"]["excl"] == 1, by["דנה"])
ck(by["אוצר"] == {"name": "אוצר", "excl": 0, "reg": 0, "total": 0, "rent": 0}, ("agent with no listings still listed", by["אוצר"]))
ck(by["(לא משויך)"]["total"] == 1, ("listings without an agent", by.get("(לא משויך)")))
ck([r["name"] for r in R["rows"]][:2] == ["רפי", "דנה"] and R["rows"][-1]["name"] == "(לא משויך)", ("most listings first, unassigned last", [r["name"] for r in R["rows"]]))
ck(R["total"] == {"excl": 2, "reg": 2, "total": 5, "rent": 1}, R["total"])
print("dash_agent_listings OK")
