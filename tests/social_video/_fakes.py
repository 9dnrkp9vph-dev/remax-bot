"""עזרי בדיקה ל-tests/social_video: Supabase בזיכרון ו-G מזויף (מרחיב את tests/social/_fakes)."""
import os, sys, threading, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("social_fakes", os.path.join(HERE, "..", "social", "_fakes.py"))
SF = _ilu.module_from_spec(_sp); _sp.loader.exec_module(SF)   # tests/social/_fakes.py

ROW = dict(SF.ROW, **{"סוכן 1": "דנה כהן",
                      "תמונות": ["https://img/a.jpg", "https://img/b.jpg", "https://img/c.jpg", "https://img/d.jpg"]})


class SBV(SF.SB):
    def __init__(self):
        super().__init__()
        self.videos, self.links, self._lk = [], {}, threading.Lock()

    def video_insert(self, rec):
        r = dict(rec, id="v%d" % (len(self.videos) + 1))
        r.setdefault("created_at", dt.datetime.now(dt.timezone.utc).isoformat())
        self.videos.append(r); return dict(r)

    def video_update(self, vid, f):
        for r in self.videos:
            if r["id"] == vid: r.update(f)
        return True

    def video_claim(self, vid, frm, to, f):
        with self._lk:
            for r in self.videos:
                if r["id"] == vid and r.get("status") == frm:
                    r.update(f, status=to); return True
            return False

    def video_get(self, vid):
        return next((dict(r) for r in self.videos if r["id"] == vid), None)

    def video_recent(self, days):
        return [dict(r) for r in reversed(self.videos)]

    def link_insert(self, rec):
        self.links[rec["code"]] = dict(rec, clicks=0, id="l%d" % (len(self.links) + 1)); return self.links[rec["code"]]

    def link_get(self, code):
        return self.links.get(code)

    def link_click(self, code):
        if code in self.links: self.links[code]["clicks"] += 1


def make_G(rows=None, cfg=None):
    G, st, _ = SF.make_G(rows=rows if rows is not None else [ROW], cfg=cfg)
    sb = SBV()
    G["_sbdb"] = sb
    st.update(sent=[], posted=[], window=set())
    G["_vphone_for_name"] = lambda n: "072-555-0101" if n == "דנה כהן" else ""
    G["_phones_for_name"] = lambda n: ["0521234567", "0725550101"] if n == "דנה כהן" else []
    G["_agent_vphones9"] = lambda: {"725550101"}
    G["send_text"] = lambda to, txt: (st["sent"].append((to, txt)), True)[1]
    G["_d360_on"] = lambda: True
    G["_wa_window_open"] = lambda to: str(to)[-9:] in st["window"]
    G["_d360_post_message"] = lambda payload: (st["posted"].append(payload), {"ok": True})[1]
    G["_quiet_hours"] = lambda: False
    G["DEV_PHONES"] = {"505709865"}
    return G, st, sb
