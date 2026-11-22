"""media_app.py — שרת המדיה: מרכיב סרטונים (ffmpeg + Pillow) בשביל אפי, ושום דבר אחר.

שירות נפרד ב-Render מאותו ריפו:  gunicorn media_app:app   (gunicorn.conf.py: worker אחד — העבודות בזיכרון)
משתנה סביבה יחיד: MEDIA_KEY (זהה לזה שבאפי). בלי מפתח — הכל מחזיר 503.

אין כאן מסד נתונים, וואטסאפ, Meta או לולאות רקע. מקבל חומרים → מחזיר קובץ. רינדור אחד בכל רגע.
"""
from __future__ import annotations
import hmac
import os
import secrets
import shutil
import tempfile
import threading
import time

from flask import Flask, jsonify, request, send_file

import media_remote as MR

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 150 * (1 << 20)

JOBS = {}              # id → {'status','dir','ts','duration','error','video','cover'}
_LK = threading.Lock()
_RENDER = threading.Lock()
MAX_QUEUE = 6
KEEP_S = 3600


def _auth():
    want = str(os.environ.get("MEDIA_KEY") or "").strip()
    if not want:
        return jsonify({"ok": False, "error": "MEDIA_KEY not set"}), 503
    got = str(request.headers.get("X-Media-Key") or "")
    if not hmac.compare_digest(got.encode(), want.encode()):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return None


def _sweep(now=None):
    now = time.time() if now is None else now
    with _LK:
        old = [k for k, j in JOBS.items() if now - j["ts"] > KEEP_S and j["status"] in ("done", "failed")]
        dirs = [JOBS.pop(k)["dir"] for k in old]
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)


def compose(kind, a, out_path):
    """הקריאה עצמה לפונקציות ההרכבה של אפי (אותו קוד, אותו חוזה)."""
    import social_video as V
    if kind == "tour":
        import social_video_tour as T
        return T.vid_compose_tour(a.get("photos") or {}, a.get("shots") or [], a.get("texts") or {}, a.get("theme"),
                                  a.get("music"), out_path, V._logo_path(), a.get("agent_photo"))
    if kind == "classic":
        tl = [tuple(x) for x in (a.get("timeline") or [])]
        slides = [(s[0], s[1]) for s in (a.get("slides") or [])]
        layers = V.vid_layers(a.get("texts") or {}, tl, V._logo_path(), bool(a.get("ai")),
                              os.path.join(os.path.dirname(out_path), "L"))
        return V.vid_compose(a.get("clip"), slides, layers, tl, a.get("music"), out_path)
    if kind == "sold":
        import social_sold as S
        return S.sold_compose(a.get("kind"), a.get("photo"), a.get("texts") or {}, a.get("agents"),
                              a.get("music"), out_path, V._logo_path())
    return {"ok": False, "error": "unknown kind"}


def _run(jid, kind, raw_args):
    j = JOBS.get(jid)
    if not j:
        return
    with _RENDER:
        j["status"], j["ts"] = "running", time.time()
        try:
            args = MR.decode(raw_args, j["dir"])
            out_path = os.path.join(j["dir"], "out.mp4")
            out = compose(kind, args, out_path) or {}
            if out.get("ok") and os.path.exists(out_path):
                j.update(status="done", duration=out.get("duration"), video=out_path, cover=out.get("cover"))
            else:
                j.update(status="failed", error=str(out.get("error") or "רינדור נכשל")[:400])
        except Exception as e:
            j.update(status="failed", error=("%s: %s" % (type(e).__name__, e))[:400])
        j["ts"] = time.time()


@app.route("/health")
def health():
    import social_video as V
    with _LK:
        n = {s: sum(1 for j in JOBS.values() if j["status"] == s) for s in ("queued", "running", "done", "failed")}
    return jsonify({"ok": True, "ffmpeg": bool(V.vid_ffmpeg()), "key": bool(os.environ.get("MEDIA_KEY")), "jobs": n})


@app.route("/render", methods=["POST"])
def render():
    err = _auth()
    if err:
        return err
    _sweep()
    body = request.get_json(silent=True) or {}
    kind = str(body.get("kind") or "")
    if kind not in ("tour", "classic", "sold"):
        return jsonify({"ok": False, "error": "kind"}), 400
    with _LK:
        if sum(1 for j in JOBS.values() if j["status"] in ("queued", "running")) >= MAX_QUEUE:
            return jsonify({"ok": False, "error": "busy"}), 429
        jid = secrets.token_urlsafe(12)
        JOBS[jid] = {"status": "queued", "dir": tempfile.mkdtemp(prefix="mjob_"), "ts": time.time()}
    threading.Thread(target=_run, args=(jid, kind, body.get("args") or {}), daemon=True, name="media-render").start()
    return jsonify({"ok": True, "id": jid})


@app.route("/job/<jid>")
def job(jid):
    err = _auth()
    if err:
        return err
    j = JOBS.get(jid)
    if not j:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "status": j["status"], "duration": j.get("duration"), "error": j.get("error")})


@app.route("/job/<jid>/<part>")
def job_file(jid, part):
    err = _auth()
    if err:
        return err
    j = JOBS.get(jid)
    p = (j or {}).get(part) if part in ("video", "cover") else None
    if not p or not os.path.exists(p):
        return jsonify({"ok": False, "error": "not found"}), 404
    return send_file(p, mimetype="video/mp4" if part == "video" else "image/jpeg")


@app.route("/job/<jid>/done", methods=["POST"])
def job_done(jid):
    err = _auth()
    if err:
        return err
    with _LK:
        j = JOBS.pop(jid, None)
    if j:
        shutil.rmtree(j["dir"], ignore_errors=True)
    return jsonify({"ok": True})
