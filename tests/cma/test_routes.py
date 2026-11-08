"""CMA — ראוטים: העלאת קובץ מדלן, רשימת שכונות, תצוגה לסוכן, cma_block (תוכנית 2026-11-06-cma, משימה 3).
הרצה: python3 tests/cma/test_routes.py"""
import base64
import datetime as dt
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from flask import Flask, request  # noqa: E402
import cma  # noqa: E402

FAILS = []


def ck(cond, msg):
    print(("ok  " if cond else "FAIL") + "  " + msg)
    if not cond:
        FAILS.append(msg)


class SBM:
    def __init__(self):
        self.rows = {}
        self.raise_all = False

    def enabled(self):
        return True

    def market_upsert(self, rows):
        for r in rows:
            self.rows.setdefault(r["deal_key"], dict(r, uploaded_at=dt.datetime.now(dt.timezone.utc).isoformat()))
        return len(rows)

    def market_all(self, since):
        if self.raise_all:
            raise RuntimeError("db down")
        return [dict(r) for r in self.rows.values() if (r.get("deal_date") or "") >= since]

    def market_files(self):
        agg = {}
        for r in self.rows.values():
            a = agg.setdefault(r["nb"], {"nb": r["nb"], "last_upload": "", "n": 0, "min_date": None, "max_date": None})
            a["n"] += 1
            a["last_upload"] = max(a["last_upload"], r["uploaded_at"])
        return list(agg.values())


SESS = {"t-owner": {"name": "אייל שמול", "role": "admin", "phone": "505709865", "dev": True},
        "t-agent": {"name": "דנה כהן", "role": "agent", "phone": "521234567", "dev": False}}


def make():
    app = Flask(__name__)
    sb = SBM()
    acts = []
    G = {"_web_auth": lambda: SESS.get(request.headers.get("X-Auth-Token", "")),
         "_is_dev": lambda p: p == "505709865", "_sbdb": sb,
         "_log_activity": lambda *a: acts.append(a),
         "_deal_history_linked": lambda: [],
         "fetch_newborn": lambda: [], "fetch_external_exclusives": lambda: [],
         "_office_rows_for": lambda dc: ([], ""),
         "_swr": lambda k, t, f, max_stale=1800: f()}
    cma.register(app, G)
    return app, G, sb, acts


H = cma.MADLAN_HEADERS


def xlsx(rows, headers=H):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return "data:application/octet-stream;base64," + base64.b64encode(buf.getvalue()).decode()


def begin(house, date, price, sqm, rooms="5"):
    return [date, "בגין מנחם %d, קרית מוצקין" % house, "{:,}".format(price), "דירה", rooms, str(sqm), "3", "", "2000"]


TODAY = dt.date.today()


def d(days):
    x = TODAY - dt.timedelta(days=days)
    return "%d.%d.%d" % (x.day, x.month, x.year)


GOOD = [begin(10, d(300), 1800000, 102), begin(16, d(200), 1500000, 111), begin(18, d(150), 1650000, 122),
        begin(6, d(400), 1850000, 102), begin(25, d(500), 2030000, 121), begin(32, d(700), 1900000, 102),
        begin(34, d(600), 1800007, 107)]


def main():
    app, G, sb, acts = make()
    c = app.test_client()
    body = {"name": "t.xlsx", "data": xlsx(GOOD), "nb": "נווה גנים ומוצקין הצעירה"}

    ck(c.post("/v2/api/cma/upload", json=body).status_code == 401, "upload without login → 401")
    ck(c.post("/v2/api/cma/upload", json=body, headers={"X-Auth-Token": "t-agent"}).status_code == 403,
       "upload by agent → 403")
    j = c.post("/v2/api/cma/upload", json=body, headers={"X-Auth-Token": "t-owner"}).get_json()
    ck(j.get("ok") and j["stats"]["n"] == 7, "owner upload → ok, 7 rows")
    ck(len(sb.rows) == 7, "7 rows stored")
    ck(any("עסקאות ממדלן" in a[3] for a in acts), "upload logged")
    c.post("/v2/api/cma/upload", json=body, headers={"X-Auth-Token": "t-owner"})
    ck(len(sb.rows) == 7, "same file twice → still 7 rows")

    j = c.post("/v2/api/cma/upload", json=dict(body, nb=" "), headers={"X-Auth-Token": "t-owner"}).get_json()
    ck(j.get("ok") is False and j.get("reason") == "nb", "missing nb → reason nb")
    bad = dict(body, data=xlsx(GOOD, headers=("תאריך", "כתובת", "מחיר")))
    n0 = len(sb.rows)
    j = c.post("/v2/api/cma/upload", json=bad, headers={"X-Auth-Token": "t-owner"}).get_json()
    ck(j.get("ok") is False and j.get("reason") == "headers" and len(sb.rows) == n0, "wrong headers → reason headers, nothing stored")
    j = c.post("/v2/api/cma/upload", json=dict(body, data=""), headers={"X-Auth-Token": "t-owner"}).get_json()
    ck(j.get("reason") == "no_file", "empty file → no_file")

    ck(c.get("/v2/api/cma/files", headers={"X-Auth-Token": "t-agent"}).status_code == 403, "files by agent → 403")
    j = c.get("/v2/api/cma/files", headers={"X-Auth-Token": "t-owner"}).get_json()
    ck(j.get("ok") and j["files"][0]["n"] == 7 and j["stale"] == [], "files lists the nb, not stale")
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=46)).isoformat()
    for r in sb.rows.values():
        r["uploaded_at"] = old
    j = c.get("/v2/api/cma/files", headers={"X-Auth-Token": "t-owner"}).get_json()
    ck(j["stale"] == ["נווה גנים ומוצקין הצעירה"], "46 days old → stale")

    q = "/v2/api/cma/view?street=מנחם בגין&house=12&city=קרית מוצקין&rooms=5&sqm=107&ptype=דירה"
    ck(c.get(q).status_code == 401, "view without login → 401")
    j = c.get(q, headers={"X-Auth-Token": "t-agent"}).get_json()
    ck(j.get("ok") and j["cma"] and j["cma"]["range"] == [1620000, 1910000], "view → range 1.62–1.91M")
    j = c.get(q.replace("rooms=5", "rooms=3"), headers={"X-Auth-Token": "t-agent"}).get_json()
    ck(j.get("ok") and j["cma"] is None and j.get("reason") == "few", "too few → cma null, reason few")

    listing = {"רחוב": "מנחם בגין 12", "עיר / ישוב": "קרית מוצקין", "חדרים": "5", "sqm": "107", "ptype": "דירה"}
    ck(cma.cma_block(G, listing)["range"] == [1620000, 1910000], "cma_block → same range")
    sb.raise_all = True
    ck(cma.cma_block(G, listing) is None, "cma_block when market_all raises → None")

    vf = app.view_functions
    for ep, fn in (("/v2/api/cma/upload", "cma_upload"), ("/v2/api/cma/files", "cma_files"),
                   ("/v2/api/cma/view", "cma_view")):
        rule = next(r for r in app.url_map.iter_rules() if r.rule == ep)
        ck(vf[rule.endpoint].__name__ == fn, "route %s → %s" % (ep, fn))

    print("\n%d failures" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
