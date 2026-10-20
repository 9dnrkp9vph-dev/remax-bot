import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("WARMUP_ON_BOOT", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
calls = []
A.fetch_newborn = lambda: [{"מזהה": "abc", "עיר": "קרית ביאליק", "שכונה": "נאות אפק", "סוג עסקה": "מכירה", "מחיר": "1780000",
                            "תיאור נכס": "דירה · 4 חד' · קומה 4. הבנין חדש"}]
A._phones_for_name = lambda n: {"544445454"}
A._gauth_email_for_phone = lambda p: "agent@example.com"
A._agent_email_for = lambda n, p: ""
A.gcal_create_event = lambda em, s, d, st, en, **k: (calls.append((em, s, d, st, en, k)), "ev1")[1]
rec = {"status": "meeting", "addr": "עוזי חיטמן 1", "owner": "גני", "price": "1780000", "ophone": "0533412796",
       "agent": "עוז דנילוב", "pkey": "id:abc", "note": ""}
out = A._nb_cal_create(rec, "2026-10-21T10:30", "agent@example.com")
em, s, d, st, en, k = calls[0]
print(s); print(k["location"]); print(d); print(st, en, k["color_id"])
assert out == [{"email": "agent@example.com", "id": "ev1"}] and s == "פגישה עם בעל נכס - גני"
assert k["location"] == "עוזי חיטמן 1, נאות אפק, קרית ביאליק" and k["color_id"] == "11" and en == "2026-10-21T11:30:00"
assert d.startswith("למכירה: דירה, 4 חד', קומה 4, עוזי חיטמן 1, קרית ביאליק 1,780,000 ₪")
print("INTEGRATION OK")
