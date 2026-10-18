"""18/10: שם-ממלא-מקום מהסורק ('סוכן 8719') לא דורס סוכן אמיתי בנכסי המשרד."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import supabase_db as sb

fails = 0
def check(name, cond, detail=""):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + name + ("" if cond else "  →  " + repr(detail)))
    if not cond:
        fails += 1

print("KA 1: placeholder detection")
for s in ["", "סוכן 8719", "סוכן8719", "משרד", "משרד 4723809", "Re/max Family (לא משויך)"]:
    check("placeholder: " + repr(s), sb.is_placeholder_agent(s))
for s in ["חי חיים אלבז", "סוכן", "יאיר חנוכאייב"]:
    check("real: " + repr(s), not sb.is_placeholder_agent(s))

print("KA 2: keep_real_agents")
current = [{"raw": {"מספר מודעה": "uqf7dcew", "סוכן 1": "יאיר חנוכאייב", "טלפון 1": "050-1111111"}},
           {"raw": {"מספר מודעה": "82xuqf8j", "סוכן 1": "סוכן 8719", "טלפון 1": "04-0000000"}},
           {"raw": {"מספר מודעה": "aaaa1111", "סוכן 1": "חי חיים אלבז", "טלפון 1": "052-2222222"}}]
rows = [{"מספר מודעה": "uqf7dcew", "סוכן 1": "סוכן 8719", "טלפון 1": "04-0000000", "מחיר": "1000000"},
        {"מספר מודעה": "82xuqf8j", "סוכן 1": "סוכן 8719", "טלפון 1": "04-0000000"},
        {"מספר מודעה": "aaaa1111", "סוכן 1": "דידי לוי", "טלפון 1": "053-3333333"},
        {"מספר מודעה": "newtok00", "סוכן 1": "סוכן 8719", "טלפון 1": "04-0000000"}]
n = sb.keep_real_agents(rows, current)
check("one row fixed", n == 1, n)
check("real agent restored", rows[0]["סוכן 1"] == "יאיר חנוכאייב", rows[0])
check("agent phone restored", rows[0]["טלפון 1"] == "050-1111111", rows[0])
check("other fields from the scan kept", rows[0]["מחיר"] == "1000000")
check("existing placeholder stays placeholder", rows[1]["סוכן 1"] == "סוכן 8719")
check("a real new name from the scan wins (transfer)", rows[2]["סוכן 1"] == "דידי לוי")
check("new listing keeps the placeholder", rows[3]["סוכן 1"] == "סוכן 8719")
check("empty input", sb.keep_real_agents([], current) == 0 and sb.keep_real_agents(rows, []) == 0)

print("KA 3: merge_office_props applies it")
class R:
    def __init__(s, data=None): s._d = data or []; s.status_code = 200; s.headers = {}
    def json(s): return s._d
    def raise_for_status(s): pass
written = {}
cur_rows = [{"sheet_row": 2, "raw": {"מספר מודעה": "uqf7dcew", "סוכן 1": "יאיר חנוכאייב", "_y2_office_id": "5628636"}}]
orig_get_all, orig_replace, orig_enabled = sb._get_all, sb.replace_properties, sb.enabled
sb._get_all = lambda *a, **k: cur_rows
sb.replace_properties = lambda rows: (written.setdefault("rows", rows), (True, len(rows)))[1]
sb.enabled = lambda: True
try:
    ok, cnt, new = sb.merge_office_props("5628636", [{"מספר מודעה": "uqf7dcew", "סוכן 1": "סוכן 8719", "_y2_office_id": "5628636"}])
finally:
    sb._get_all, sb.replace_properties, sb.enabled = orig_get_all, orig_replace, orig_enabled
out = [r for r in written.get("rows", []) if r.get("מספר מודעה") == "uqf7dcew"]
check("merged row keeps the real agent", out and out[0]["סוכן 1"] == "יאיר חנוכאייב", out)

print(f"{fails} FAILURES" if fails else "ALL KEEP-AGENT TESTS PASSED")
sys.exit(1 if fails else 0)
