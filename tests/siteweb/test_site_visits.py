"""כניסות לאתר לפי יום ומקור (אייל 20/10) — האתר שולח, אפי שומרת ומסכמת להיום/שבוע/חודש/שנה.
רץ ישירות: python3 tests/siteweb/test_site_visits.py (בלי pytest)."""
import os, sys, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask
import site_api as sa


def test_merge_boots_and_compact():
    st = sa.visits_merge({}, "aa", [{"day": "2026-10-20", "v": 5, "src": {"google": 3, "direct": 2}}])
    st = sa.visits_merge(st, "aa", [{"day": "2026-10-20", "v": 7, "src": {"google": 4, "direct": 3}}])   # מצטבר — מחליף
    st = sa.visits_merge(st, "bb", [{"day": "2026-10-20", "v": 2, "src": {"facebook": 2}}])              # פריסה → תהליך חדש
    assert sa.visits_day(st["2026-10-20"]) == {"v": 9, "src": {"google": 4, "direct": 3, "facebook": 2}}
    st = sa.visits_merge(st, "bb", [{"day": "2026-10-24", "v": 1, "src": {"ai": 1}}])
    assert "t" in st["2026-10-20"] and "b" not in st["2026-10-20"]                     # ימים ישנים מקופלים
    assert sa.visits_day(st["2026-10-20"])["v"] == 9
    st2 = sa.visits_merge(st, "cc", [{"day": "2026-10-20", "v": 50, "src": {}}])       # דיווח מאוחר ליום סגור — מתעלמים
    assert sa.visits_day(st2["2026-10-20"])["v"] == 9


def test_sanitize():
    st = sa.visits_merge({}, "<x>", [{"day": "2026-10-20", "v": 3, "src": {"google": 2, "<script>": 9}}])
    assert st == {}                                                                       # boot לא תקין
    st = sa.visits_merge({}, "ab12", [{"day": "20/10/2026", "v": 3}, {"day": "2026-10-20", "v": -4, "src": {"google": 2, "evil": 9}}])
    assert list(st) == ["2026-10-20"] and sa.visits_day(st["2026-10-20"]) == {"v": 0, "src": {"google": 2}}


def test_summary_periods():
    st = {}
    for day, n in (("2025-12-31", 100), ("2026-10-01", 10), ("2026-10-17", 4), ("2026-10-18", 3), ("2026-10-20", 2)):
        st = sa.visits_merge(st, "aa", [{"day": day, "v": n, "src": {"google": n}}])
    s = sa.visits_summary(st, dt.date(2026, 10, 20))            # שלישי; השבוע מיום ראשון 18/10
    assert s["today"]["v"] == 2 and s["week"]["v"] == 5 and s["month"]["v"] == 19 and s["year"]["v"] == 19, s
    assert s["week"]["src"] == {"google": 5} and s["since"] == "2025-12-31"


def make(cfg):
    class AutoG(dict):
        def __missing__(self, k):
            return lambda *a, **kw: None

    def mutate(fn):
        fn(cfg)
        return True, True
    G = AutoG(log=None, _load_config=lambda: cfg, _config_mutate=mutate)

    class St:
        def all(self):
            return []
    app = Flask(__name__)
    sa.register_site(app, G, store=St())
    return app


def test_route():
    os.environ["SITE_KEY"] = "secret"
    cfg = {}
    app = make(cfg)
    c = app.test_client()
    body = {"boot": "ab12", "days": [{"day": sa._now_il().strftime("%Y-%m-%d"), "v": 4, "src": {"direct": 4}}]}
    assert c.post("/site/api/visits", json=dict(body, key="nope")).status_code == 403
    assert c.post("/site/api/visits", json=dict(body, key="secret")).get_json() == {"ok": True}
    assert app.site_visits_summary()["today"] == {"v": 4, "src": {"direct": 4}}
    assert "v2_site_visits" in cfg
    os.environ.pop("SITE_KEY", None)


def test_dashboard_table_js():
    import ast, re, shutil, subprocess
    if not shutil.which("node"):
        return
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "effie_v2.py"), encoding="utf-8").read()
    html = next(n.value.value for n in ast.parse(src).body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str) and "function visitsHtml" in n.value.value)
    assert 'id="slStats"' in html
    js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
    sl = re.search(r"var SL=\{.*?\};", js).group(0)
    fn = re.search(r"function visitsHtml\(v\)\{.*?\n(?=function siteLive)", js, re.S).group(0)
    v = "{today:{v:2,src:{google:1}},week:{v:5,src:{google:4,facebook:1}},month:{v:5,src:{}},year:{v:5,src:{}},since:'2026-10-20'}"
    out = subprocess.run(["node", "-e", sl + fn + "console.log(visitsHtml(" + v + "));console.log('['+visitsHtml(null)+']')"],
                         capture_output=True, text=True).stdout
    assert "<th>השנה</th>" in out and "<td>סה״כ</td><td>2</td><td>5</td>" in out and "פייסבוק" in out and "נספר מ-20/10/2026" in out, out
    assert out.strip().endswith("[]")


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            f(); n += 1; print("ok", k)
    print("%d passed" % n)
