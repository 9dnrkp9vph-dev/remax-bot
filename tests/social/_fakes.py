"""עזרי בדיקה משותפים ל-tests/social (G מזויף, Supabase בזיכרון, Graph מזויף)."""
import datetime as dt
import social_publish as SP
_GUARD = SP.Graph._guard   # לפני שהבדיקה מחליפה את SP.Graph
REAL_GRAPH = SP.Graph

ROW = {"מספר מודעה": "tok1", "סוג עסקה": "מכירה", "סוג נכס": "דירה", "חדרים": "4", "שכונה": "נאות אפק",
       "עיר / ישוב": "קרית ביאליק", "כתובת": "אהוד מנור", "מספר בית": "13", "מחיר": "1890000",
       'מ"ר': "110", "קומה": "3", "_desc_ae": "דירה יפה", "_y2_first_seen": "01/11/2026 10:00",
       "תמונות": ["https://img/a.jpg", "https://img/b.jpg"]}


class SB:
    def __init__(self):
        self.rows = []
    def enabled(self): return True
    def social_insert(self, rec):
        r = dict(rec, id="r%d" % (len(self.rows) + 1))
        r.setdefault("created_at", dt.datetime.now(dt.timezone.utc).isoformat())
        self.rows.append(r); return r
    def social_update(self, rid, f):
        for r in self.rows:
            if r["id"] == rid: r.update(f)
        return True
    def social_recent(self, days): return list(reversed(self.rows))


class FakeGraph:
    """מחליף את SP.Graph: מקליט קריאות; fb/ig יכולים להיכשל לפי err."""
    instances = []
    def __init__(self, http, token, env, sleep=None, version=None):
        self.token, self.env, self.calls = token, env, []
        self.err = FakeGraph.next_err
        self.quota = FakeGraph.next_quota
        FakeGraph.instances.append(self)
    def me(self): return {"id": "1", "name": "sys"}
    def page_ig_id(self, pid): return "IG"
    def ig_quota(self, ig): return self.quota
    def fb_post(self, pid, msg, urls):
        _GUARD(self)
        self.calls.append(("fb", pid, msg, list(urls)))
        e = self.err.get("fb")
        if e: raise e
        return "P1", "https://fb/p1"
    def ig_post(self, ig, cap, urls):
        _GUARD(self)
        self.calls.append(("ig", ig, cap, list(urls)))
        e = self.err.get("ig")
        if e: raise e
        return "M1", "https://ig/m1"
FakeGraph.next_err = {}
FakeGraph.next_quota = 25


def make_G(rows=None, cfg=None):
    st = {"cfg": cfg if cfg is not None else {"v2_office": {"name": "רימקס פמילי"}}, "acts": [], "push": []}
    sb = SB()

    def mutate(fn):
        res = fn(st["cfg"]); return True, res

    G = {"fetch_sheet_rows": lambda: list(rows if rows is not None else [ROW]),
         "fetch_sheet_rows_deal": lambda d: [],
         "_load_config": lambda: st["cfg"], "_config_mutate": mutate,
         "_row_feats": lambda r: [], "_shabbat_quiet_now": lambda: False, "_quiet_mode": lambda: False,
         "_log_activity": lambda *a: st["acts"].append(a), "send_push": lambda t, b, *a, **k: st["push"].append((t, b)),
         "_display_name_for": lambda n, p: "אייל שמול", "_sbdb": sb, "log": None}
    return G, st, sb


class ImgHttp:
    """http להורדת תמונות: מחזיר PNG אמיתי, או כשל לכתובות שמכילות 'bad'."""
    def __init__(self):
        import io
        from PIL import Image
        b = io.BytesIO(); Image.new("RGB", (800, 600), (10, 120, 200)).save(b, "PNG"); self.png = b.getvalue()
    def get(self, url, timeout=None, headers=None, params=None):
        class R: pass
        r = R()
        if "bad" in url:
            r.status_code, r.content = 404, b""
        else:
            r.status_code, r.content = 200, self.png
        return r
