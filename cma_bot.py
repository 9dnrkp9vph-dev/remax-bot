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
REQ_CFG = "v2_cma_bot_req"     # בקשות שנשלחו לבוט: {request_id: {ts, address, akey, by, ok}}
REQ_DEDUP_DAYS = 7             # אותה כתובת שוב תוך שבוע — לא שולחים שוב לבוט
REQ_KEEP_DAYS = 30


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


def addr_key(a):
    return " ".join(str(a or "").replace("קריית", "קרית").replace(",", " ").split())


def daily_cap():
    try:
        return int(os.environ.get("CMA_BOT_DAILY", "30"))
    except ValueError:
        return 30


def recent_request(reqs, address, now):
    """בקשה שנשלחה בהצלחה לאותה כתובת בשבוע האחרון → (request_id, רשומה), אחרת (None, None)."""
    k = addr_key(address)
    best = (None, None)
    for rid, r in (reqs or {}).items():
        if r.get("ok") and r.get("akey") == k and now - float(r.get("ts") or 0) <= REQ_DEDUP_DAYS * 86400:
            if best[1] is None or r["ts"] > best[1]["ts"]:
                best = (rid, r)
    return best


def sent_today(reqs, now):
    return sum(1 for r in (reqs or {}).values() if now - float(r.get("ts") or 0) < 86400)


def request_bot(G, address, by="", force=False):
    """שולח כתובת לבוט (פעם בשבוע לכל כתובת, עד CMA_BOT_DAILY ביום). משמש את מסך ניתוח השוק ואת התיק.
    מחזיר {ok, request_id, reused?, reason?, status?}."""
    url = (os.environ.get("CMA_BOT_URL") or "").strip()
    if not url:
        return {"ok": False, "reason": "no_bot_url"}
    addr = str(address or "").strip()[:200]
    if not addr:
        return {"ok": False, "reason": "no_address"}
    now = time.time()
    reqs = (G["_load_config"]().get(REQ_CFG) or {})
    if not force:
        rid, r = recent_request(reqs, addr, now)
        if rid:
            return {"ok": True, "request_id": rid, "reused": True}
    if sent_today(reqs, now) >= daily_cap():
        return {"ok": False, "reason": "daily_cap"}
    rid = "cma-" + secrets.token_hex(6)
    try:
        import requests
        r = requests.post(url, json={"request_id": rid, "address": addr}, headers=bot_headers(), timeout=20)
        ok, code = r.status_code < 300, r.status_code
    except Exception as e:
        ok, code = False, str(e)[:120]
    rec = {"ts": now, "address": addr, "akey": addr_key(addr), "by": str(by or "")[:40], "ok": ok}

    def _m(cfg):
        d = cfg.setdefault(REQ_CFG, {})
        d[rid] = rec
        for k in [k for k, v in d.items() if now - float((v or {}).get("ts") or 0) > REQ_KEEP_DAYS * 86400]:
            d.pop(k, None)
    try:
        G["_config_mutate"](_m)
    except Exception:
        pass
    try:
        G["_log_activity"]("אפי", "system", "", "CMA — בקשה לבוט מדלן",
                           ("%s · %s" % (addr, "נשלח" if ok else "נכשל"))[:60])
    except Exception:
        pass
    out = {"ok": ok, "request_id": rid, "status": code}
    if not ok:
        out["reason"] = "bot_error"
    return out


def kit_release(G, rid):
    """[10/11] תיק שמחכה לעסקאות של הבקשה הזו — נבנה מחדש ונשלח לאישור (kit.py רושם את ההוק)."""
    hook = G.get("_kit_cma_release")
    if not hook or not rid:
        return
    try:
        hook(rid=rid)
    except Exception as e:
        lg = G.get("log")
        if lg:
            lg.warning("cma kit release: %s", e)


def _save_async(G, rid, address, deals):
    """העסקאות שחזרו → מאגר העסקאות של ה-CMA (ברקע — הבוט מקבל תשובה מיד)."""
    def run():
        try:
            import cma
            st = cma.ingest_bot(G, address, deals)
            res = {"saved": st.get("n", 0), "bad": st.get("bad", 0)}
        except Exception as e:
            res = {"save_error": str(e)[:160]}
        def _m(cfg):
            for r in cfg.get(CFG) or []:
                if r.get("request_id") == rid:
                    r.update(res)
                    break
        try:
            G["_config_mutate"](_m)
        except Exception:
            pass
        kit_release(G, rid)
    if G.get("_cma_bot_sync"):        # בדיקות
        run()
        return
    import threading
    threading.Thread(target=run, daemon=True, name="cma-bot-save").start()


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
        if not rec["address"]:   # הבוט לא החזיר כתובת — לפי הבקשה שלנו
            rec["address"] = ((G["_load_config"]().get(REQ_CFG) or {}).get(rec["request_id"]) or {}).get("address", "")
        G["_config_mutate"](lambda cfg: cfg.__setitem__(CFG, push(cfg.get(CFG), rec)))
        if rec["address"] and rec["deals"]:
            _save_async(G, rec["request_id"], rec["address"], rec["deals"])
        elif G.get("_cma_bot_sync"):   # שגיאה / בלי עסקאות — התיק שמחכה יוצא לאישור בלי ניתוח השוק
            kit_release(G, rec["request_id"])
        else:
            import threading
            threading.Thread(target=kit_release, args=(G, rec["request_id"]), daemon=True).start()
        try:
            G["_log_activity"]("בוט מדלן", "system", "", "CMA — תוצאות מבוט מדלן",
                               ("%s · %d עסקאות" % (rec["address"], rec["n"]))[:60])
        except Exception:
            pass
        return jsonify({"ok": True, "n": rec["n"], "request_id": rec["request_id"]})

    @app.route("/v2/api/cma/yad2_deals", methods=["POST"])
    def cma_yad2_deals():
        """[13/11] הסורק (נכס נולד): 'נכסים שנמכרו באזור' מדף המודעה ביד2 → מאגר העסקאות. מפתח הבוט."""
        if not key_ok(request.headers.get("X-CMA-Key", "")):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        deals = b.get("deals") if isinstance(b.get("deals"), list) else []
        try:
            import cma
            st = cma.ingest_yad2(G, deals[:200])
        except Exception as e:
            return jsonify({"ok": False, "reason": "save", "error": str(e)[:160]}), 500
        try:
            G["_log_activity"]("סורק יד2", "system", "", "CMA — עסקאות מדף מודעה ביד2",
                               ("%s · %d עסקאות" % (str(b.get("address") or b.get("token") or "")[:40], st.get("n", 0)))[:60])
        except Exception:
            pass
        return jsonify({"ok": True, "n": st.get("n", 0), "min_date": st.get("min_date"), "max_date": st.get("max_date")})

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
        """בעל המשרד / המפתח — תמיד; כל משתמש מחובר — דרך מסך ניתוח השוק (עם התקרה היומית)."""
        try:
            sess = G["_web_auth"]()
        except Exception:
            sess = None
        if not (key_ok(request.headers.get("X-CMA-Key", "")) or sess):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        b = request.get_json(silent=True) or {}
        force = bool(b.get("force")) and _allowed()
        return jsonify(request_bot(G, b.get("address"), (sess or {}).get("name", "מפתח"), force=force))

    @app.route("/v2/api/cma/bot_status", methods=["GET"])
    def cma_bot_status():
        """לכל משתמש מחובר: האם התשובה לבקשה הגיעה ונשמרה. בלי פרטי העסקאות."""
        try:
            sess = G["_web_auth"]()
        except Exception:
            sess = None
        if not (sess or key_ok(request.headers.get("X-CMA-Key", ""))):
            return jsonify({"ok": False, "reason": "auth"}), 401
        rid = (request.args.get("id") or "").strip()
        cfg = G["_load_config"]()
        req = (cfg.get(REQ_CFG) or {}).get(rid)
        res = next((r for r in cfg.get(CFG) or [] if r.get("request_id") == rid), None)
        if not req and not res:
            return jsonify({"ok": False, "reason": "unknown"})
        out = {"ok": True, "sent_at": (req or {}).get("ts"), "done": bool(res)}
        if res:
            out.update(n=res.get("n", 0), saved="saved" in res or "save_error" in res, error=bool(res.get("save_error")))
        return jsonify(out)
