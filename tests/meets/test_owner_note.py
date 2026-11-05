"""הערות בעל הנכס (טקסט המודעה) נכנסות לבד להערה של פגישה מנכס נולד (אייל 05/11)."""
import ast, pathlib, re

SRC = (pathlib.Path(__file__).resolve().parents[2] / "app.py").read_text(encoding="utf-8")

def _load(*names):
    tree = ast.parse(SRC)
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = {"re": re, "_newborn_price": lambda p: str(p or "")}
    exec(compile(ast.Module(body=fns, type_ignores=[]), "x", "exec"), ns)
    return ns

ROW = {"תיאור נכס": "גג/ פנטהאוז · 4 חד' · 130 מ\"ר. מיני פנטהאוז בבניין של 6 קומות", "עיר": "קרית ביאליק"}

def test_owner_notes_extracts_listing_text():
    f = _load("_nb_owner_notes")["_nb_owner_notes"]
    assert f(ROW) == "מיני פנטהאוז בבניין של 6 קומות"
    assert f({"תיאור נכס": "רק טקסט חופשי"}) == "רק טקסט חופשי"
    assert f(None) == "" and f({}) == ""

def test_calendar_does_not_repeat_note_equal_to_owner_text():
    ns = _load("_nb_owner_notes", "_nb_cal_text")
    rec = {"status": "meeting", "addr": "נעמי שמר 18", "note": "מיני פנטהאוז בבניין של 6 קומות"}
    _, desc, _ = ns["_nb_cal_text"](rec, ROW)
    assert desc.count("מיני פנטהאוז") == 1
    assert "הערות בעל הנכס:" in desc and "הערה:" not in desc.replace("הערות בעל הנכס:", "")

def test_save_and_list_use_owner_notes():
    save = SRC[SRC.index("def api_newborn_status("):SRC.index("def api_newborn_status(") + 6000]
    assert "_nb_owner_notes(" in save
    lst = SRC[SRC.index("def api_newborn_meetings"):SRC.index("@app.route(\"/api/newborn/status/delete\"")]
    assert "_nb_owner_notes(" in lst
