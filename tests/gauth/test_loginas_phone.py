"""כניסה כסוכן: הטלפון של הסשן = הטלפון שהסוכן באמת נכנס איתו (רועי עמור 05/11).
עד היום נבחר טלפון שרירותי מתוך set — והאזור האישי הראה 'לא מחובר' ונוסח ברירת מחדל."""
import ast, pathlib

SRC = (pathlib.Path(__file__).resolve().parents[2] / "app.py").read_text(encoding="utf-8")

def _load():
    tree = ast.parse(SRC)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_loginas_primary_phone")
    ns = {"_last9": lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:]}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "x", "exec"), ns)
    return ns["_loginas_primary_phone"]

def test_prefers_google_linked_phone():
    f = _load()
    got = f({"0554314582", "0521112222"}, {}, lambda p: "roee@gmail.com" if p.endswith("521112222") else "")
    assert got == "0521112222"

def test_then_phone_with_personal_settings():
    f = _load()
    cfg = {"v2_nb_wa_texts": {"521112222": "שלום"}}
    assert f({"0554314582", "0521112222"}, cfg, lambda p: "") == "0521112222"
    cfg = {"v2_licenses": {"521112222": "123"}}
    assert f({"0554314582", "0521112222"}, cfg, lambda p: "") == "0521112222"

def test_stable_fallback_and_empty():
    f = _load()
    a = f({"0554314582", "0521112222"}, {}, lambda p: "")
    b = f({"0521112222", "0554314582"}, {}, lambda p: "")
    assert a == b and a in {"0554314582", "0521112222"}
    assert f(set(), {}, lambda p: "") == ""

def test_loginas_uses_it():
    body = SRC[SRC.index("def api_admin_loginas"):SRC.index("def api_dev_config_get")]
    assert "_loginas_primary_phone(" in body
    assert "next(iter(phones))" not in body
