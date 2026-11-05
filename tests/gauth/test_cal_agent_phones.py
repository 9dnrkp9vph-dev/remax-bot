"""פגישה שמתאמת קובעת לסוכן נכנסת ליומן Google של הסוכן גם כשהחשבון מקושר לטלפון אחר שלו
(נויה → רועי עמור 05/11: נבחר טלפון אחד באקראי מתוך כל הטלפונים של הסוכן)."""
import ast, pathlib

SRC = (pathlib.Path(__file__).resolve().parents[2] / "app.py").read_text(encoding="utf-8")

def _load(gauth):
    tree = ast.parse(SRC)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_gauth_email_for_phones")
    ns = {"_last9": lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:],
          "_gauth_all": lambda: gauth}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "x", "exec"), ns)
    return ns["_gauth_email_for_phones"]

G = {"roee@gmail.com": {"phone": "521112222", "refresh_token": "rt", "ts": 5},
     "old@gmail.com": {"phone": "554314582", "ts": 9}}

def test_finds_link_on_any_phone():
    f = _load(G)
    assert f({"0554314582x", "0521112222"}) == "roee@gmail.com"
    assert f(["0559999999", "0521112222"]) == "roee@gmail.com"

def test_prefers_calendar_token_over_newer_without():
    f = _load(G)
    assert f({"0554314582", "0521112222"}) == "roee@gmail.com"

def test_none():
    f = _load(G)
    assert f({"0500000000"}) == "" and f(set()) == ""

def test_cal_create_uses_all_phones():
    body = SRC[SRC.index("def _nb_cal_create"):SRC.index("def _newborn_created_epoch")]
    assert "_gauth_email_for_phones(" in body
    assert "_gauth_email_for_phone(_ps[0])" not in body
