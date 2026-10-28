"""POST /v2/api/goals/remind — רישום לחיצה על 'תזכורת ללקוח' / 'בקשת ביקורת'. python3 tests/goals/test_remind_route.py"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask
import goals


class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


def make(auth=True):
    logs = []
    sess = {"name": "דנה כהן", "role": "agent", "phone": "501111111"}
    G = AutoG(_web_auth=lambda: sess if auth else None, _log_activity=lambda *a: logs.append(a),
              _last9=lambda p: "".join(ch for ch in str(p or "") if ch.isdigit())[-9:])
    app = Flask(__name__)
    goals.register(app, G)
    return app, logs


def test_remind_logged():
    app, logs = make()
    r = app.test_client().post("/v2/api/goals/remind", json={"phone": "0501234567", "kind": "remind"})
    assert r.get_json() == {"ok": True}
    assert logs == [("דנה כהן", "agent", "501111111", goals.ACT_REMIND, "501234567")], logs


def test_review_logged():
    app, logs = make()
    app.test_client().post("/v2/api/goals/remind", json={"phone": "972501234567", "kind": "review"})
    assert logs[0][3] == goals.ACT_REVIEW_MANUAL and logs[0][4] == "501234567", logs


def test_unauth_and_bad_phone():
    app, logs = make(auth=False)
    assert app.test_client().post("/v2/api/goals/remind", json={"phone": "0501234567", "kind": "remind"}).status_code == 403
    app, logs = make()
    assert app.test_client().post("/v2/api/goals/remind", json={"phone": "12345", "kind": "remind"}).status_code == 400
    assert app.test_client().post("/v2/api/goals/remind", json={"phone": "0501234567", "kind": "zzz"}).status_code == 400
    assert not logs


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
