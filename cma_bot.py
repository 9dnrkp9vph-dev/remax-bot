"""CMA — בוט מדלן חיצוני (אייל 10/11): אפי שולחת לבוט כתובת, והבוט מחזיר אחרי כמה דקות את העסקאות.

שלב בדיקה בלבד: כאן רק השליחה, הקבלה והשמירה של מה שחזר. החישוב (cma.py) לא מחובר עדיין.
אימות: מפתח סודי ב-env CMA_BOT_KEY בכותרת X-CMA-Key (גם לבוט וגם לקריאת התוצאות),
או סשן של בעל המשרד. כתובת הבוט: env CMA_BOT_URL, וההזדהות מולו: env CMA_BOT_AUTH.
נשמר בקונפיג v2_cma_bot — 20 התשובות האחרונות, עד 500 עסקאות לתשובה.
"""
import hmac
import json
import os
import secrets
import time

KEEP = 20
MAX_DEALS = 500
CFG = "v2_cma_bot"


def _key():
    return (os.environ.get("CMA_BOT_KEY") or "").strip()


def key_ok(k):
    kk = _key()
    return bool(kk) and bool(k) and hmac.compare_digest(str(k), kk)


def bot_headers():
    """env CMA_BOT_AUTH = הערך של כותרת Authorization מפאנל ה-webhook של הבוט (למשל 'Bearer ...').
    מקבל גם הדבקה של השורה כולה ('Authorization: Bearer ...')."""
    v = (os.environ.get("CMA_BOT_AUTH") or "").strip().strip('"').strip("'")
    if v.lower().startswith("authorization:"):
        v = v.split(":", 1)[1].strip()
    return {"Authorization": v} if v else {}


def ingest_record(body, now=None):
    """גוף מהבוט → רשומה לשמירה. לא מסנן ולא מתקן — שומר כמו שהגיע (נבדוק את האיכות)."""
    body = body if isinstance(body, dict) else {}
    deals = body.get("deals")
    if not isinstance(deals, list):
        deals = []
    rec = {"ts": now if now is not None else time.time(),
           "request_id": str(body.get("request_id") or "")[:80],
           "address": str(body.get("address") or "")[:200],
           "n": len(deals),
           "deals": deals[:MAX_DEALS],
           "keys": sorted(k for k in body.keys())[:30]}
    extra = {k: v for k, v in body.items() if k not in ("deals", "request_id", "address")}
    if extra:
        s = json.dumps(extra, ensure_ascii=False, default=str)
        rec["extra"] = json.loads(s) if len(s) <= 4000 else {"_truncated": True}
    return rec


def push(lst, rec):
    lst = [r for r in (lst or []) if isinstance(r, dict)]
    lst.insert(0, rec)
    return lst[:KEEP]


def register(app, G):
    from flask import jsonify, request

    def _owner():
        try:
            s = G["_web_auth"]()
        except Exception:
            s = None
        return bool(s) and (s.get("dev") or G["_is_dev"](s.get("phone", "")))

    def _allowed():
        return key_ok(request.headers.get("X-CMA-Key", "")) or _owner()

    @app.route("/v2/api/cma/ingest", methods=["POST"])
    def cma_bot_ingest():
        if not key_ok(request.headers.get("X-CMA-Key", "") or request.args.get("k", "")):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        body = request.get_json(silent=True)
        if body is None:
            try:
                body = json.loads(request.get_data(as_text=True) or "{}")
            except Exception:
                body = {}
        rec = ingest_record(body)
        G["_config_mutate"](lambda cfg: cfg.__setitem__(CFG, push(cfg.get(CFG), rec)))
        try:
            G["_log_activity"]("בוט מדלן", "system", "", "CMA — תוצאות מבוט מדלן",
                               ("%s · %d עסקאות" % (rec["address"], rec["n"]))[:60])
        except Exception:
            pass
        return jsonify({"ok": True, "n": rec["n"], "request_id": rec["request_id"]})

    @app.route("/v2/api/cma/bot_results", methods=["GET"])
    def cma_bot_results():
        if not _allowed():
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        lst = (G["_load_config"]().get(CFG) or [])
        rid = (request.args.get("id") or "").strip()
        if rid:
            lst = [r for r in lst if r.get("request_id") == rid]
        return jsonify({"ok": True, "results": lst})

    @app.route("/v2/api/cma/bot_request", methods=["POST"])
    def cma_bot_request():
        if not _allowed():
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        url = (os.environ.get("CMA_BOT_URL") or "").strip()
        if not url:
            return jsonify({"ok": False, "reason": "no_bot_url"})
        addr = str((request.get_json(silent=True) or {}).get("address") or "").strip()[:200]
        if not addr:
            return jsonify({"ok": False, "reason": "no_address"})
        rid = "cma-" + secrets.token_hex(6)
        try:
            import requests
            r = requests.post(url, json={"request_id": rid, "address": addr}, headers=bot_headers(), timeout=20)
            ok, code = r.status_code < 300, r.status_code
        except Exception as e:
            ok, code = False, str(e)[:120]
        try:
            G["_log_activity"]("אפי", "system", "", "CMA — בקשה לבוט מדלן",
                               ("%s · %s" % (addr, "נשלח" if ok else "נכשל"))[:60])
        except Exception:
            pass
        return jsonify({"ok": ok, "request_id": rid, "status": code})
