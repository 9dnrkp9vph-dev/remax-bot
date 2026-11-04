"""04/11 (אייל): 'חיוג רגיל בנכס נולד' דלוק → גם החייגן החכם מחייג מהטלפון ולא דרך מסקיו.
python3 tests/dialer/test_dialer_plain.py"""
import os, sys, re, json, subprocess
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask
import dialer as D

fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None

def queue(entry):
    D._CACHE.update(t=0, v=None)
    cfg = {"nbStatus": {}, "v2_dialer_users": ["דנה לוי"]}
    G = AutoG(log=None, _web_auth=lambda: {"name": "דנה לוי", "role": "agent", "drole": "agent", "phone": "501111111"},
              _load_config=lambda: cfg, _config_mutate=lambda fn: (fn(cfg), (True, None))[1],
              _display_name_for=lambda n, p: n, _canon_key=lambda n: " ".join(str(n or "").split()),
              _canon_agent_name=lambda n: n, _last9=lambda p: re.sub(r"\D", "", str(p or ""))[-9:],
              _coordinators_all=lambda: {}, _is_dev=lambda p: False, _phones_for_name=lambda n: {"0501111111"},
              fetch_newborn=lambda: [], fetch_sheet_rows=lambda: [], _fetch_manual_buyers=lambda: [],
              fetch_agents_phones=lambda: {"דנה לוי": "0501111111"}, web_phone_name_map=lambda: {},
              web_contacts_phone_name=lambda: {}, _price_dropped_map=lambda: {}, _fetch_newborn_contacts=lambda: {},
              _famexcl_addr_list=lambda: {}, _office_name=lambda: "המשרד", _c2c_agent_entry=lambda s: entry)
    app = Flask(__name__); D.register(app, G)
    return app.test_client().get("/v2/api/dialer/queue").get_json()

print("1. שרת: plainDial בתור")
check(queue(None).get("plainDial") is True, "בלי רשומה — חיוג רגיל (ברירת המחדל)")
check(queue({"name": "דנה לוי"}).get("plainDial") is True, "רשומה בלי השדה — חיוג רגיל")
check(queue({"name": "דנה לוי", "newbornPlainDial": False}).get("plainDial") is False, "כבוי במפורש — מרכזיה")

print("2. קליינט: dial()")
src = open(os.path.join(os.path.dirname(D.__file__), "dialer.py"), encoding="utf-8").read()
m = re.search(r"(function dial\(\)\{.*?\n\})\n", src, re.S)
js = r"""
var LOG = {c2c: 0, href: ''}; var location = {set href(v){ LOG.href = v; }, get href(){ return LOG.href; }};
function c2cDial(t){ LOG.c2c++; } function POST(){ return {catch: function(){}}; } function render(){}
var MODE, SECS, D = {stats: {calls: 0}, plainDial: PLAIN};
function cur(){ return {key: 'k', address: 'א', tel: '0521234567'}; }
""" + m.group(1) + "\ndial(); console.log(JSON.stringify(LOG));"
for plain, exp_c2c, exp_href, msg in ((True, 0, "tel:0521234567", "דלוק — tel: בלי מסקיו"),
                                      (False, 1, "", "כבוי — דרך המרכזיה")):
    out = subprocess.run(["node", "-e", js.replace("PLAIN", "true" if plain else "false")], capture_output=True, text=True)
    R = json.loads(out.stdout or "{}")
    check(R.get("c2c") == exp_c2c and R.get("href") == exp_href, msg)

print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
