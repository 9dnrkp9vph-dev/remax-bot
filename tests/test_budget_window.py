"""[BUDGET-WIN 28/10] טווח תקציב לקונה: עד 20% מעל, עד 30% מתחת — בשרת (התאמות חדשות) ובחלון ההתאמות."""
import ast, os, re, subprocess, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()


def _load(names):
    tree = ast.parse(SRC)
    g = {"_bp_digits": lambda v: re.sub(r"\D", "", str(v or ""))}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in names:
            exec(compile(ast.Module([n], []), "x", "exec"), g)
    return g


def test_server_window():
    g = _load({"budget_window_ok", "bpage_new_matches"})
    rows = {"office": {
        "dani": {"מחיר": "2,490,000", "_ep": 5},   # 71% — הגפן של קובי חמו
        "low": {"מחיר": "2,400,000", "_ep": 5},    # 69% — מתחת ל-30%
        "high": {"מחיר": "4,200,000", "_ep": 5},   # 120%
        "over": {"מחיר": "4,250,000", "_ep": 5},   # מעל 20%
    }}
    got = g["bpage_new_matches"]({}, rows, set(), 0, 3500000, lambda r, q: 80)
    keys = {o["key"] for o in got}
    assert keys == {"dani", "high"}, keys


def test_client_window():
    m = re.search(r"function _budgetOk\(b\)\{.*?\n\}", SRC, re.S)
    js = """
    function _budgetNum(v){ return +String(v||'').replace(/\\D/g,'') || 0; }
    function _priceNum(v){ return +String(v||'').replace(/\\D/g,'') || 0; }
    """ + m.group(0) + """
    var ok = _budgetOk({budget:'3,500,000'});
    console.log(JSON.stringify([2490000,2400000,4200000,4250000,0].map(function(p){return ok({price:p});})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [True, False, True, False, True], out


if __name__ == "__main__":
    test_server_window(); test_client_window(); print("ok")
