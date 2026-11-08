# [HOME-BUNDLE 06/11] בקשה אחת למסך הבית + חימום-מקדים
import datetime as dt
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["HOME_WARM"] = "0"   # בלי thread בבדיקות
import home_bundle as hb
from flask import Flask, jsonify, request, g


def test_trim_report():
    j = {"ok": True, "label": "השבוע", "listings": 488, "meetings": [{"a": 1}],
         "summary": {"calls": {"total": 12, "x": [1] * 50}, "sigs": {"total": 3},
                     "sigsList": [{"c": 1}, {"c": 2}], "exclusives": [{"q": 1}, {"q": 2}]}}
    t = hb.trim_part("report", j)
    assert t["summary"]["calls"] == {"total": 12}
    assert t["summary"]["sigsList"] == [{"c": 1}]
    assert len(t["summary"]["exclusives"]) == 2
    assert t["listings"] == 488 and t["label"] == "השבוע" and t["meetings"] == [{"a": 1}]


def test_trim_others():
    b = hb.trim_part("buyers", {"ok": True, "results": [{"date": "01/11/2026", "agent": "x", "phone": "05"}]})
    assert b["results"] == [{"date": "01/11/2026", "agent": "x"}]
    now = time.time()
    s = hb.trim_part("sigs", {"signatures": [{"ts": now, "type": "בלעדיות", "address": "a", "client": "c", "big": 1},
                                             {"ts": now - 30 * 86400, "type": "מוכר"}]})
    assert s["signatures"] == [{"type": "בלעדיות", "ts": now, "address": "a", "client": "c"}]
    d = hb.trim_part("deals", {"items": [{"deal": True, "x": 1}, {"deal": False}]})
    assert d["items"] == [{"deal": True}, {"deal": False}]
    n = hb.trim_part("nb", {"ok": True, "total": 2600, "results": [{"ageDays": 0, "address": "h", "city": "c", "desc": "z"},
                                                                    {"ageDays": 3}]})
    assert n["total"] == 2600 and n["results"] == [{"ageDays": 0, "address": "h", "city": "c"}]
    assert hb.trim_part("props", {"ok": True, "count": 7, "results": [1] * 99}) == {"ok": True, "count": 7}
    assert hb.trim_part("dialer", {"ok": True, "allowed": 1}) == {"ok": True, "allowed": True}
    assert hb.trim_part("meets", {"ok": True, "results": [1]}) == {"ok": True, "results": [1]}
    assert hb.trim_part("report", {"ok": False}) is None
    assert hb.trim_part("report", None) is None


def test_work_hours():
    il = hb._IL
    assert hb.work_hours(dt.datetime(2026, 11, 8, 9, 0, tzinfo=il))       # ראשון
    assert not hb.work_hours(dt.datetime(2026, 11, 8, 7, 0, tzinfo=il))
    assert not hb.work_hours(dt.datetime(2026, 11, 8, 20, 30, tzinfo=il))
    assert hb.work_hours(dt.datetime(2026, 11, 6, 13, 0, tzinfo=il))      # שישי
    assert not hb.work_hours(dt.datetime(2026, 11, 6, 15, 0, tzinfo=il))
    assert not hb.work_hours(dt.datetime(2026, 11, 7, 11, 0, tzinfo=il))  # שבת


def test_targets_and_epoch():
    now = 10000
    assert hb.warm_targets({"a": 9990, "b": 9000, "c": 9999}, now, 500) == ["c", "a"]
    assert hb.ping_epoch("2026-11-06T08:00:00Z") == dt.datetime(2026, 11, 6, 8, tzinfo=dt.timezone.utc).timestamp()
    assert hb.ping_epoch("2026-11-06T08:00:00+00:00") > 0
    assert hb.ping_epoch("bad") == 0 and hb.ping_epoch(None) == 0


def _app(fail=(), slow=()):
    app = Flask("t")
    calls = []
    logs = []
    sessions = {"TOK": {"phone": "501234567"}}

    def auth():
        t = request.headers.get("X-Auth-Token")
        return sessions.get(t)

    def mk(path, payload):
        def v():
            s = auth()
            calls.append((path, request.headers.get("X-Auth-Token"), request.args.to_dict()))
            if not s:
                return jsonify({"ok": False}), 401
            if path in slow:
                time.sleep(1.5)
            if path in fail:
                return jsonify({"ok": False, "reason": "x"}), 500
            if not getattr(g, "effie_warm", False):
                logs.append(path)
            return jsonify(payload)
        v.__name__ = "v_" + path.replace("/", "_")
        app.add_url_rule(path, v.__name__, v, methods=["GET", "POST"])

    mk("/api/newborn/meetings", {"ok": True, "results": [{"date": "2026-11-06T10:00"}]})
    mk("/api/report", {"ok": True, "label": "השבוע", "summary": {"calls": {"total": 5}}})
    mk("/api/my/buyers", {"ok": True, "results": [{"date": "06/11/2026", "agent": "a", "phone": "x"}]})
    mk("/api/my/properties", {"ok": True, "count": 4, "results": []})
    mk("/api/signatures", {"ok": True, "signatures": []})
    mk("/v2/api/sign/drafts", {"ok": True, "drafts": []})
    mk("/api/deals", {"ok": True, "items": [{"deal": False}]})
    mk("/api/newborn", {"ok": True, "total": 9, "results": []})
    mk("/v2/api/dialer/access", {"ok": True, "allowed": False})
    mk("/v2/api/brief", {"ok": True})
    G = {"log": logging.getLogger("t"), "_web_sessions": sessions, "_last9": lambda p: str(p)[-9:],
         "_web_auth": auth, "_session_from_phone": lambda p: {"phone": p}, "_is_suspended": lambda p: False}
    hb.register(app, G)
    return app, calls, logs, sessions


def test_bundle_all_parts():
    app, calls, logs, _ = _app()
    r = app.test_client().get("/v2/api/home/bundle", headers={"X-Auth-Token": "TOK"})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["miss"] == []
    assert set(j["parts"]) == {k for k, _ in hb.PARTS}
    assert j["parts"]["report"]["summary"]["calls"]["total"] == 5
    assert j["parts"]["buyers"]["results"] == [{"date": "06/11/2026", "agent": "a"}]
    # הטוקן של המשתמש עבר לכל ראוט, והפרמטרים נשמרו
    assert all(c[1] == "TOK" for c in calls)
    assert ("/api/report", "TOK", {"period": "week"}) in calls
    assert ("/api/newborn", "TOK", {"limit": "120"}) in calls
    assert "/api/my/properties" in logs   # בקשה אמיתית — נרשמת כמו קודם


def test_bundle_auth_and_miss():
    app, calls, _, _ = _app(fail=("/api/signatures",))
    c = app.test_client()
    assert c.get("/v2/api/home/bundle").status_code == 401
    j = c.get("/v2/api/home/bundle", headers={"X-Auth-Token": "TOK"}).get_json()
    assert j["miss"] == ["sigs"] and "sigs" not in j["parts"]


def test_bundle_timeout(monkeypatch):
    monkeypatch.setattr(hb, "BUNDLE_TIMEOUT", 0.5)
    app, _, _, _ = _app(slow=("/api/report",))
    j = app.test_client().get("/v2/api/home/bundle", headers={"X-Auth-Token": "TOK"}).get_json()
    assert "report" in j["miss"] and "props" in j["parts"]


def test_warm_one_no_logs_and_cleans_session():
    app = Flask("t2")
    calls, logs, sessions = [], [], {}

    def auth():
        return sessions.get(request.headers.get("X-Auth-Token"))

    for path in hb.WARM_PATHS:
        p = path.split("?")[0]

        def v(p=p):
            calls.append((p, bool(auth())))
            if not getattr(g, "effie_warm", False):
                logs.append(p)
            return jsonify({"ok": True})
        app.add_url_rule(p, "v" + p.replace("/", "_"), v)
    G = {"log": logging.getLogger("t"), "_web_sessions": sessions, "_last9": lambda x: str(x)[-9:],
         "_web_auth": auth, "_session_from_phone": lambda ph: {"phone": ph},
         "_is_suspended": lambda ph: ph == "999999999"}
    api = hb.register(app, G)
    api["warm_one"]("501234567")
    assert [c[0] for c in calls] == [x.split("?")[0] for x in hb.WARM_PATHS]
    assert all(c[1] for c in calls)          # הסשן הזמני עבד
    assert logs == [] and sessions == {}     # לא נרשם ביומן, הסשן נמחק
    calls.clear()
    api["warm_one"]("999999999")             # מושהה — לא מחממים
    assert calls == []


def test_seed_from_pings():
    app = Flask("t3")
    class SB:
        def enabled(self): return True
        def fetch_pings_today(self, frm):
            return [{"phone": "0501234567", "ts": "2026-11-06T08:00:00Z"},
                    {"phone": "0501234567", "ts": "2026-11-06T09:00:00Z"},
                    {"phone": "", "ts": "x"}]
    G = {"log": logging.getLogger("t"), "_web_sessions": {}, "_last9": lambda x: str(x)[-9:],
         "_web_auth": lambda: None, "_session_from_phone": lambda ph: {}, "_is_suspended": lambda ph: False,
         "_sbdb": SB()}
    api = hb.register(app, G)
    api["seed"]()
    assert api["seen"] == {"501234567": hb.ping_epoch("2026-11-06T09:00:00Z")}


def test_app_log_activity_skips_warm():
    import ast
    src = open(os.path.join(os.path.dirname(hb.__file__), "app.py"), encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_log_activity")
    ns = {"time": time, "_activity": [], "_login_where": lambda: "", "_persist_activity": lambda e: None,
          "_threading": __import__("threading")}
    exec(compile(ast.Module([fn], []), "x", "exec"), ns)
    app = Flask("t4")
    with app.test_request_context("/"):
        g.effie_warm = True
        ns["_log_activity"]("n", "agent", "1", "הנכסים שלי")
    assert ns["_activity"] == []
    with app.test_request_context("/"):
        ns["_log_activity"]("n", "agent", "1", "הנכסים שלי")
    ns["_log_activity"]("n", "agent", "1", "בלי בקשה")   # מחוץ לבקשה — כרגיל
    assert [e["action"] for e in ns["_activity"]] == ["הנכסים שלי", "בלי בקשה"]


def test_round_skips_stuck_user_and_continues(monkeypatch, caplog):
    """[HOME-WARM-TIMEOUT] משתמש שנתקע לא עוצר את הסבב; אחרי 3 תקועים לא מתחילים סבב חדש."""
    monkeypatch.setattr(hb, "WARM_USER_TIMEOUT", 0.3)
    monkeypatch.setattr(hb, "WARM_GAP", 0)
    release = __import__("threading").Event()
    warmed = []

    def sess(ph):
        if ph.startswith("5"):        # 'תקועים'
            release.wait(5)
            return None
        warmed.append(ph)
        return None                    # בלי סשן — _warm_one חוזר מיד

    app = Flask("t4")
    G = {"log": logging.getLogger("t"), "_web_sessions": {}, "_last9": lambda x: str(x)[-9:],
         "_web_auth": lambda: None, "_session_from_phone": sess, "_is_suspended": lambda ph: False}
    api = hb.register(app, G)
    now = time.time()
    api["seen"].update({"511111111": now, "422222222": now - 1, "433333333": now - 2})
    caplog.set_level(logging.INFO, logger="t")
    api["round"](3600, "recent")
    assert warmed == ["422222222", "433333333"]          # התקוע דולג, השאר חוממו
    assert api["stuck"]["n"] == 1
    assert "stuck" in caplog.text and "start 3 users" in caplog.text
    # שלושה תקועים → הסבב הבא לא מתחיל בכלל
    api["seen"].clear()
    api["seen"].update({"511111112": now, "511111113": now})
    api["round"](3600, "recent")
    assert api["stuck"]["n"] == 3
    warmed.clear()
    api["seen"]["444444444"] = now
    api["round"](3600, "recent")
    assert warmed == [] and "still stuck" in caplog.text
    # כשהתקועים משתחררים — המונה יורד והסבב חוזר לעבוד
    release.set()
    time.sleep(0.3)
    assert api["stuck"]["n"] == 0
    api["round"](3600, "recent")
    assert "444444444" in warmed
