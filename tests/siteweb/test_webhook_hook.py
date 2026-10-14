"""ה-webhook של 360 מעביר הודעות טקסט ל'סוכן AI אישי' (14/10) — בדיקה על הפונקציה האמיתית מ-app.py."""
import ast, os

def _load():
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "app.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "_d360_webhook")
    calls, marks = [], []
    class Log:
        def warning(self, *a): pass
    g = {"_wa_window_mark": marks.append, "log": Log(), "_WA_STATUS_LOG": [], "_il_now_hm": lambda: "", "_wa_diag_save": lambda: None,
         "_site_lead_inbound": lambda *a: calls.append(a)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "app.py", "exec"), g)
    return g["_d360_webhook"], calls, marks

def test_text_message_reaches_handler_with_profile_name():
    hook, calls, marks = _load()
    hook({"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "972521234567", "profile": {"name": "דנה כהן"}}],
          "messages": [{"from": "972521234567", "type": "text", "text": {"body": "היי, אני מחפש/ת: דירה"}},
                       {"from": "972521234567", "type": "image"}]}}]}]})
    assert calls == [("972521234567", "דנה כהן", "היי, אני מחפש/ת: דירה")] and len(marks) == 2

def test_handler_error_does_not_break_webhook():
    hook, calls, marks = _load()
    hook.__globals__["_site_lead_inbound"] = lambda *a: 1 / 0
    hook({"entry": [{"changes": [{"value": {"messages": [{"from": "9725", "type": "text", "text": {"body": "x"}}]}}]}]})
    assert marks == ["9725"]
