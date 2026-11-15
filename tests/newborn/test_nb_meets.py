"""15/11 (אייל): בנכס נולד — פגישה שתואמה מופיעה מתחת ל'פנו' עם המועד; למנהל/מתאמת גם למי תואמה.
python3 tests/newborn/test_nb_meets.py"""
import os, re, ast, json, subprocess
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "nb_meet_index")
ns = {}; exec(ast.get_source_segment(src, fn), ns)
idx = ns["nb_meet_index"]({
    "נחמי זקס::N:1": {"status": "meeting", "date": "2026-11-17T10:30", "agent": "נחמי זקס", "pkey": "N:1"},
    "רויטל גל::N:1": {"status": "meeting", "date": "2026-11-16T09:00", "agent": "רויטל גל"},
    "עוז::N:2": {"status": "followup", "date": "2026-11-16", "agent": "עוז"},
    "עוז::N:3": {"status": "meeting", "date": "2026-11-10T09:00", "agent": "עוז", "done": True},
    "manual:x": {"status": "meeting", "date": "2026-11-16", "agent": "עוז", "pkey": "manual:x"}})
check([m["agent"] for m in idx.get("N:1", [])] == ["רויטל גל", "נחמי זקס"], "שתי פגישות על אותו נכס, לפי המועד")
check("N:2" not in idx and "N:3" not in idx and "manual:x" not in idx, "בלי פולו-אפ, בלי 'בוצע', בלי פגישות ידניות")
check('"meets":' in src and 'm["ak"] != _canon_key(ctx["eff_name"])' in src, "בכרטיס — בלי הפגישה של המשתמש עצמו (כבר בשורת הסטטוס)")

ev = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
blk = re.search(r"(  // \[NB-MEET 15/11\].*?contacted \+= meets;)", ev, re.S).group(1)
js = """function esc(s){return String(s);} var contacted='';
var r = {meets:[{date:'2026-11-16T09:00', agent:'רויטל גל'}]};
var out = {};
MGR = false; (function(){ var contacted=''; %s out.agent = contacted; })();
MGR = true;  (function(){ var contacted=''; %s out.mgr = contacted; })();
console.log(JSON.stringify(out));""" % (blk, blk)
o = json.loads(subprocess.run(["node", "-e", "var MGR;" + js], capture_output=True, text=True).stdout)
check("תואמה פגישה · 16/11 09:00" in o["agent"] and "רויטל" not in o["agent"], "סוכן — רואה את המועד בלבד")
check("לסוכן רויטל גל" in o["mgr"], "מנהל/מתאמת — גם למי תואמה")
print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
raise SystemExit(1 if fails else 0)
