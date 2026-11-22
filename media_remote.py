"""media_remote.py — הרכבת הווידאו בשרת נפרד (media_app.py), כדי ש-ffmpeg לא יפיל את אפי (נפילת 22/11).

אפי שולחת לשרת המדיה את החומרים (תמונות, טקסטים, מוזיקה) ומקבלת בחזרה קובץ סרטון + תמונת שער.
כל השאר — נתונים, וואטסאפ, פרסום ל-Meta — נשאר באפי; שרת המדיה לא שולח הודעות ולא נוגע במסד.

הפעלה: MEDIA_URL + MEDIA_KEY ב-Render של אפי (אותו MEDIA_KEY גם בשרת המדיה). בלי שניהם — רינדור מקומי כמו קודם.
"""
from __future__ import annotations
import base64
import os
import time

POLL_S = 3
WAIT_S = 900          # תור + רינדור: עד רבע שעה
BUSY = "שרת הסרטונים לא זמין כרגע — נסו שוב בעוד כמה דקות"


class File:
    """סימון של נתיב מקומי שהתוכן שלו נשלח לשרת המדיה (שם הוא נכתב לקובץ זמני והנתיב מוחלף)."""
    def __init__(self, path):
        self.path = path


def _env(env):
    return os.environ if env is None else env


def url(env=None):
    return str(_env(env).get("MEDIA_URL") or "").strip().rstrip("/")


def key(env=None):
    return str(_env(env).get("MEDIA_KEY") or "").strip()


def enabled(env=None):
    return bool(url(env) and key(env))


# ── קידוד: bytes / קבצים / מפתחות שאינם מחרוזת — בתוך JSON ─────────────────────────
def encode(o):
    if isinstance(o, File):
        if not o.path or not os.path.exists(o.path):
            return None
        with open(o.path, "rb") as f:
            return {"$f": base64.b64encode(f.read()).decode("ascii"),
                    "ext": os.path.splitext(o.path)[1][:8]}
    if isinstance(o, (bytes, bytearray)):
        return {"$b": base64.b64encode(bytes(o)).decode("ascii")}
    if isinstance(o, dict):
        if all(isinstance(k, str) for k in o):
            return {k: encode(v) for k, v in o.items()}
        return {"$d": [[encode(k), encode(v)] for k, v in o.items()]}
    if isinstance(o, (list, tuple)):
        return [encode(v) for v in o]
    return o


def decode(o, tmp_dir):
    """ההפך של encode. קבצים נכתבים ל-tmp_dir והערך הופך לנתיב."""
    if isinstance(o, dict):
        if "$b" in o and len(o) == 1:
            return base64.b64decode(o["$b"])
        if "$f" in o:
            ext = "".join(c for c in str(o.get("ext") or "") if c.isalnum() or c == ".")[:8]
            n = len(os.listdir(tmp_dir))
            p = os.path.join(tmp_dir, "in%d%s" % (n, ext))
            with open(p, "wb") as f:
                f.write(base64.b64decode(o["$f"]))
            return p
        if "$d" in o and len(o) == 1:
            return {decode(k, tmp_dir): decode(v, tmp_dir) for k, v in o["$d"]}
        return {k: decode(v, tmp_dir) for k, v in o.items()}
    if isinstance(o, list):
        return [decode(v, tmp_dir) for v in o]
    return o


# ── הלקוח (רץ באפי) ──────────────────────────────────────────────────────────────
def render(kind, args, out_path, env=None, http=None, sleep=None, clock=None):
    """→ {'ok','duration','cover','error'} — אותו חוזה של vid_compose. הסרטון נשמר ל-out_path והשער לצידו."""
    if http is None:
        import requests as http
    sleep, clock = sleep or time.sleep, clock or time.time
    base, hd = url(env), {"X-Media-Key": key(env)}
    try:
        r = http.post(base + "/render", json={"kind": kind, "args": encode(args)}, headers=hd, timeout=120)
        j = r.json() if r.status_code == 200 else {}
        jid = j.get("id")
        if not jid:
            return {"ok": False, "error": "%s (%s)" % (BUSY, r.status_code)}
        t0, st = clock(), {}
        while clock() - t0 < WAIT_S:
            sleep(POLL_S)
            try:
                rr = http.get(base + "/job/" + jid, headers=hd, timeout=30)
            except Exception:
                continue   # שיהוק רשת — ממשיכים לחכות
            if rr.status_code == 404:
                return {"ok": False, "error": BUSY + " (העבודה אבדה — אתחול)"}
            if rr.status_code != 200:
                continue
            st = rr.json() or {}
            if st.get("status") in ("done", "failed"):
                break
        if st.get("status") != "done":
            return {"ok": False, "error": st.get("error") or (BUSY + " (timeout)")}
        cover = out_path.rsplit(".", 1)[0] + "-cover.jpg"
        for part, dst in (("video", out_path), ("cover", cover)):
            g = http.get(base + "/job/%s/%s" % (jid, part), headers=hd, timeout=300, stream=True)
            if g.status_code != 200:
                return {"ok": False, "error": BUSY + " (הורדה %s)" % g.status_code}
            with open(dst, "wb") as f:
                for chunk in g.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
        try:
            http.post(base + "/job/%s/done" % jid, headers=hd, timeout=15)
        except Exception:
            pass   # השרת מנקה לבד אחרי שעה
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            return {"ok": False, "error": BUSY + " (קובץ ריק)"}
        return {"ok": True, "duration": st.get("duration"), "cover": cover}
    except Exception as e:
        return {"ok": False, "error": "%s (%s)" % (BUSY, type(e).__name__)}
