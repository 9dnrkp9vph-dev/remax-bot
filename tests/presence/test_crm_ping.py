"""כל מי שנכנס ל-CRM מופיע ביומן השימוש ובלוח הבקרה (אייל 21/10).
מסכי ה-CRM לא שלחו פעימת נוכחות — עכשיו כל עמוד /v2/crm שולח פעימה עם טוקן ה-CRM.
רץ ישירות: python3 tests/presence/test_crm_ping.py"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask, Response
import office_presence as op


class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


def make(cfg=None, crm_ok=True):
    pings, logs = [], []

    class SB:
        def enabled(self): return True
        def insert_ping(self, phone, name=""): pings.append((phone, name))
    G = AutoG(log=None, _load_config=lambda: cfg or {}, _sbdb=SB(), _last9=lambda p: str(p or "")[-9:],
              _verify_crm_token=lambda t: ("501111111", "dana@x.com") if (crm_ok and t == "CRM") else None,
              _web_auth=lambda: None, _display_name_for=lambda n, p: "דנה כהן" if p == "501111111" else n,
              _log_activity=lambda *a: logs.append(a), _is_dev=lambda p: False)
    app = Flask(__name__)

    @app.route("/v2/crm/<m>")
    def crm(m):
        return Response("<html><body><h1>x</h1></body></html>", mimetype="text/html")

    @app.route("/v2/home")
    def home():
        return Response("<html><body>home</body></html>", mimetype="text/html")
    op.register(app, G)
    op._PING_SYNC = True
    return app, pings, logs


def test_crm_pages_get_heartbeat_script():
    app, _, _ = make()
    c = app.test_client()
    html = c.get("/v2/crm/calls").get_data(as_text=True)
    assert "/v2/api/crm/ping" in html and html.index("/v2/api/crm/ping") < html.index("</body>")
    assert "crmTok" in html
    assert "/v2/api/crm/ping" not in c.get("/v2/home").get_data(as_text=True)     # מסכי האפליקציה — יש להם פעימה משלהם


def test_crm_ping_writes_usage_ping():
    app, pings, _ = make()
    c = app.test_client()
    assert c.post("/v2/api/crm/ping", headers={"X-Auth-Token": "CRM"}).get_json() == {"ok": True}
    assert pings == [("501111111", "דנה כהן")]
    assert app.presence_via("501111111") == "crm"
    assert c.post("/v2/api/crm/ping", headers={"X-Auth-Token": "bad"}).status_code == 401
    assert len(pings) == 1


def test_crm_ping_records_office_presence():
    app, _, logs = make({"v2_office_ips": [{"branch": "ביאליק", "ip": "79.180.1.1"}]})
    app.test_client().post("/v2/api/crm/ping", headers={"X-Auth-Token": "CRM", "CF-Connecting-IP": "79.180.1.1"})
    assert [l[3] for l in logs] == ["מיקום: במשרד · ביאליק"] and logs[0][0] == "דנה כהן"
    assert app.presence_place("501111111") == "ביאליק"


def test_app_ping_marks_via_app():
    app = Flask(__name__)

    @app.route("/v2/api/ping", methods=["POST"])
    def ping():
        return {"ok": True}
    G = AutoG(log=None, _load_config=lambda: {}, _last9=lambda p: str(p or "")[-9:],
              _web_auth=lambda: {"phone": "0502222222", "name": "רון", "role": "agent"})
    op.register(app, G)
    app.test_client().post("/v2/api/ping")
    assert app.presence_via("502222222") == "app"


def test_usage_now_rows_via():
    import ast, re, datetime as dt
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "effie_v2.py"), encoding="utf-8").read()
    ns = {"_re": re, "re": re}
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef) and n.name in ("usage_now_rows", "_bp_digits", "bpage_iso_ep"):
            exec(compile(ast.Module([n], []), "effie_v2.py", "exec"), ns)
    pings = [{"phone": "0501111111", "name": "דנה", "ts": "2026-10-21T07:00:00+00:00"},
             {"phone": "0502222222", "name": "רון", "ts": "2026-10-21T07:00:30+00:00"}]
    now = dt.datetime(2026, 10, 21, 7, 1, tzinfo=dt.timezone.utc).timestamp()
    rows = ns["usage_now_rows"](pings, now, lambda n, p: n, via_for=lambda p: "crm" if p == "501111111" else "app")
    assert {r["name"]: r["via"] for r in rows} == {"דנה": "crm", "רון": "app"}, rows


def test_chip_labels_js():
    import ast, re, shutil, subprocess, json
    if not shutil.which("node"):
        return
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "effie_v2.py"), encoding="utf-8").read()
    consts = {n.targets[0].id: n.value.value for n in ast.parse(src).body
              if isinstance(n, ast.Assign) and isinstance(getattr(n.targets[0], "id", None), str)
              and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
    assert "viaTxt(r.via)" in consts["V2_ACTIVITY_HTML"] and "r.via==='crm'" in consts["_CRM_DASH_HTML"]
    fn = re.search(r"function viaTxt\(v\)\{.*?\n", consts["V2_ACTIVITY_HTML"]).group(0)
    out = subprocess.run(["node", "-e", fn + "console.log(JSON.stringify([viaTxt('crm'),viaTxt('app'),viaTxt(undefined)]))"],
                         capture_output=True, text=True).stdout.strip()
    assert json.loads(out) == [" · CRM", "", ""], out


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            f(); n += 1; print("ok", k)
    print("%d passed" % n)
