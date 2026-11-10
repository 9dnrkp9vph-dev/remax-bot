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

    # שם רחוב הפוך בקובץ, כשהרחוב כבר שמור במאגר בשם הנכון → אותו מפתח, בלי שורה כפולה
    app2, G2, sb2, _a2 = make()
    c2 = app2.test_client()
    r0 = dict(cma.madlan_rows([dict(zip(H, begin(10, d(300), 1800000, 102)))], "נ", "a", {"מנחם בגין"})[0][0],
              uploaded_at="2026-01-01T00:00:00+00:00")
    sb2.rows[r0["deal_key"]] = r0
    c2.post("/v2/api/cma/upload", json=dict(body, data=xlsx([begin(10, d(300), 1800000, 102)])),
            headers={"X-Auth-Token": "t-owner"})
    ck(len(sb2.rows) == 1, "reversed street name matches a street already stored → no duplicate row")
    # אותה עסקה בשני קבצים: בכתובת אמיתית ובשם פרויקט → נספרת פעם אחת
    app3, G3, sb3, _a3 = make()
    c3 = app3.test_client()
    dd = [d(400), "בגין מנחם 37, קרית מוצקין", "1,620,000", "דירה", "5", "116", "12", "", "2000"]
    pp = [d(399), "Dori Dream קרית מוצקין", "1,620,000", "דירה", "5", "116", "12", "", "2000"]
    c3.post("/v2/api/cma/upload", json=dict(body, data=xlsx([dd])), headers={"X-Auth-Token": "t-owner"})
    c3.post("/v2/api/cma/upload", json=dict(body, data=xlsx([pp])), headers={"X-Auth-Token": "t-owner"})
    live = [r for r in cma._inputs(G3)[0] if r.get("price") == 1620000 and not r.get("bad")]
    ck(len(live) == 1 and live[0]["house"] == 37, "same deal under address + project across two files → counted once")
    # שמירה שנכשלת → הודעה ברורה, לא 500
    app4, G4, sb4, _a4 = make()
    def boom(rows):
        raise RuntimeError("relation market_deals does not exist")
    sb4.market_upsert = boom
    r4 = app4.test_client().post("/v2/api/cma/upload", json=body, headers={"X-Auth-Token": "t-owner"})
    ck(r4.status_code == 200 and r4.get_json().get("reason") == "save", "failed save → ok false, reason save")

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
    blk = cma.cma_block(G, dict(listing, listing_key="nb:x"))
    def keys(o):
        if isinstance(o, dict):
            return set(o) | set().union(*[keys(v) for v in o.values()])
        if isinstance(o, list):
            return set().union(*[keys(v) for v in o]) if o else set()
        return set()
    ck("מנחם בגין" not in repr(blk) and not ({"street", "house"} & keys(blk)),
       "cma_block (stored in the kit snapshot) has no street or house number")
    ck(blk["street_count"] >= 1 and blk["n_used"] == 7 and blk["comps"][0]["price"],
       "cma_block keeps counts, range and street-free rows")
    j = c.get(q, headers={"X-Auth-Token": "t-agent"}).get_json()
    ck(j["cma"]["comps"][0].get("house") is not None, "agent view keeps house numbers")
    import cma_bot
    asked = []
    orig = cma_bot.request_bot
    cma_bot.request_bot = lambda G_, a, by="", force=False: asked.append((a, by)) or {"ok": True}
    G["_cma_bot_sync"] = True
    cma.cma_block(G, listing)
    ck(asked == [], "enough deals → no request to the bot")
    ck(cma.cma_block(G, dict(listing, חדרים="3")) is None and asked == [("מנחם בגין 12, קרית מוצקין", "תיק פרזנטציה")],
       "too few deals in the kit → asks the bot for the address")
    sb.raise_all = True
    ck(cma.cma_block(G, listing) is None, "cma_block when market_all raises → None")
    cma_bot.request_bot = orig

    vf = app.view_functions
    for ep, fn in (("/v2/api/cma/upload", "cma_upload"), ("/v2/api/cma/files", "cma_files"),
                   ("/v2/api/cma/view", "cma_view")):
        rule = next(r for r in app.url_map.iter_rules() if r.rule == ep)
        ck(vf[rule.endpoint].__name__ == fn, "route %s → %s" % (ep, fn))

    print("\n%d failures" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
