"""[DIALER 03/11] חייגן חכם למתאמות. python3 tests/dialer/test_dialer.py"""
import os, sys, re, json, subprocess, tempfile, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from zoneinfo import ZoneInfo
from flask import Flask
import dialer as D

IL = ZoneInfo("Asia/Jerusalem")
fails = []


def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c:
        fails.append(m)


def at(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IL)


print("1. ניקוד")
s_new, w_new = D.lead_score(0, True, [], 7, True)
s_old, w_old = D.lead_score(9, False, ["דנה"], 0, False)
check(s_new > s_old, "טרי + ירידת מחיר + קונים + אף אחד לא פנה > ישן שכבר פנו אליו")
check(any("7 קונים" in t for k, t in w_new), "סיבה: 7 קונים מתאימים")
check(any("כבר פנו: דנה" in t for k, t in w_old), "סיבה: כבר פנו")
check(3 <= s_old <= 97 and 3 <= s_new <= 97, "ציון בטווח 3-97")
check(D.lead_score(0, False, [], 1, False)[1][0][1] == "קונה מתאים במשרד", "קונה אחד — יחיד")

print("2. גיל המודעה")
now = at(2026, 11, 3, 12).timestamp()
check(D.age_label(now - 38 * 60, now) == "פורסם לפני 38 דק׳", "דקות")
check(D.age_label(now - 3600, now) == "פורסם לפני שעה", "שעה")
check(D.age_label(now - 5 * 3600, now) == "פורסם לפני 5 שעות", "שעות")
check(D.age_label(now - 30 * 3600, now) == "פורסם אתמול", "אתמול")
check(D.age_label(now - 4 * 86400, now) == "פורסם לפני 4 ימים", "ימים")

print("3. מועדים פנויים")
tue = at(2026, 11, 3, 12)            # שלישי 12:00
sl = D.free_slots(tue, [], n=5)
check(sl[0]["iso"] == "2026-11-03T17:00" and sl[0]["label"] == "היום 17:00", "הראשון: היום 17:00 (12:00 קרוב מדי)")
check(sl[2]["label"] == "מחר 10:00", "מחר 10:00")
busy = [at(2026, 11, 3, 17, 30)]
sl2 = D.free_slots(tue, busy, n=3)
check(all(s["iso"] not in ("2026-11-03T17:00", "2026-11-03T18:30") for s in sl2), "פגישה ב-17:30 חוסמת 17:00 ו-18:30")
thu = at(2026, 11, 5, 19)            # חמישי ערב
sl3 = D.free_slots(thu, [], n=5)
check(sl3[0]["iso"] == "2026-11-06T10:00" and sl3[1]["iso"] == "2026-11-06T12:00", "שישי: 10:00 ו-12:00 בלבד")
check(not any(s["iso"].startswith("2026-11-07") for s in sl3), "בלי שבת")
check(sl3[2]["iso"] == "2026-11-08T10:00", "אחרי שישי — ראשון")

print("4. ניסיון חוזר")
check(D.next_retry(tue, "na") == at(2026, 11, 3, 17, 30), "לא ענה בצהריים → היום 17:30")
check(D.next_retry(at(2026, 11, 3, 18), "na") == at(2026, 11, 4, 10, 30), "לא ענה בערב → מחר 10:30")
check(D.next_retry(at(2026, 11, 6, 9), "na") == at(2026, 11, 6, 12), "שישי בבוקר → 12:00")
check(D.next_retry(at(2026, 11, 6, 12), "na") == at(2026, 11, 8, 10, 30), "שישי בצהריים → ראשון")
check(D.next_retry(tue, "back") == at(2026, 11, 4, 10, 0), "לחזור אליו → מחר 10:00")

print("5. הסוכן המומלץ")
ck = lambda n: " ".join(str(n or "").split())
rows = ([{"סוכן 1": "דנה לוי", "שכונה": "נאות אפק, אפקה", "עיר / ישוב": "קרית ביאליק"}] * 3 +
        [{"סוכן 1": "רועי אברהם", "שכונה": "הפרפר", "עיר / ישוב": "קרית ביאליק"}] * 4 +
        [{"סוכן 1": "אלון כהן", "שכונה": "נאות אפק", "עיר / ישוב": "קרית ביאליק", "סטטוס": "לא פעילה"}] * 9)
cnt = D.agent_counts(rows, ck)
r = D.rank_agents("קרית ביאליק", "נאות אפק", cnt, [], ["דנה לוי", "רועי אברהם", "אלון כהן"], ck)
check(r[0]["name"] == "דנה לוי" and "3 נכסים שלו בנאות אפק" in r[0]["why"], "דנה — הכי הרבה נכסים בשכונה")
check(r[1]["name"] == "רועי אברהם", "רועי — רק בעיר")
check(all(x["name"] != "אלון כהן" for x in r), "נכסים לא פעילים לא נספרים")
r2 = D.rank_agents("קרית ים", "", cnt, ["אלון כהן"], ["דנה לוי"], ck)
check(r2 and r2[0]["name"] == "אלון כהן" and r2[0]["mine"] and r2[0]["why"] == "מהצוות שלך", "בלי נכסים באזור — מהצוות של המתאמת")

print("6. התור")
now = at(2026, 11, 3, 12).timestamp()
cands = [{"key": "a", "score": 50}, {"key": "b", "score": 90}, {"key": "c", "score": 70},
         {"key": "d", "score": 60}, {"key": "e", "score": 40}, {"key": "f", "score": 30}]
mine = {"c": {"o": "na", "t": now - 600, "r": now + 3600, "n": 1}, "d": {"o": "no", "t": now - 60},
        "f": {"o": "na", "t": now - 9000, "r": now - 60, "n": 2}}
gout = {"e": {"o": "meet"}}
claims = {"a": {"by9": "500000000", "t": now - 60}}
ready, later = D.queue_split(cands, mine, gout, claims, "511111111", now)
check([c["key"] for c in ready] == ["b", "f"], "מוכנים: b (90) ואז f (הגיע זמן הניסיון החוזר)")
check(ready[1].get("tries") == 2, "ניסיון חוזר מסומן")
check([c["key"] for c in later] == ["c"], "c — מאוחר יותר")
r3, _ = D.queue_split(cands, {}, {}, {"a": {"by9": "511111111", "t": now - 60}}, "511111111", now)
check("a" in [c["key"] for c in r3], "נכס שאני תפסתי — נשאר אצלי")
r4, _ = D.queue_split(cands, {}, {}, {"a": {"by9": "500000000", "t": now - 30 * 60}}, "511111111", now)
check("a" in [c["key"] for c in r4], "תפיסה של מתאמת אחרת פגה אחרי 20 דק׳")

print("7. ראוטים")


class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


NOW = at(2026, 11, 3, 12).timestamp()
D._time.time = lambda: NOW
NB = [
    {"מזהה": "1", "רחוב1": "הנוטר 18", "עיר": "קרית ביאליק", "שכונה": "נאות אפק", "חדרים": "5", "מחיר": "2,390,000",
     "שם בעל הנכס": "מיכל", "טלפון בעל הנכס": "0521112233", "תיאור נכס": "דירה · 5 חד׳", "_c": NOW - 40 * 60},
    {"מזהה": "2", "רחוב1": "הגפן 12", "עיר": "קרית מוצקין", "שכונה": "", "חדרים": "4", "מחיר": "1,900,000",
     "שם בעל הנכס": "", "טלפון בעל הנכס": "", "תיאור נכס": "", "_c": NOW - 3600},                      # בלי טלפון
    {"מזהה": "3", "רחוב1": "בגין 4", "עיר": "קרית ים", "שכונה": "", "חדרים": "3", "מחיר": "1,100,000",
     "שם בעל הנכס": "אבי", "טלפון בעל הנכס": "0523334455", "תיאור נכס": "", "_c": NOW - 20 * 86400},     # ישן מדי
    {"מזהה": "4", "רחוב1": "עוזי חיטמן 7", "עיר": "קרית ביאליק", "שכונה": "הפרפר", "חדרים": "4", "מחיר": "1,950,000",
     "שם בעל הנכס": "רינה", "טלפון בעל הנכס": "0525556677", "תיאור נכס": "", "_c": NOW - 2 * 86400},
]


def row_out(r, ad, city, addr, owner, lister, dropped, ctx):
    return {"key": "id:" + r["מזהה"], "address": addr, "city": city, "owner": owner, "phone": r["טלפון בעל הנכס"],
            "wa": "972" + r["טלפון בעל הנכס"][1:] if r["טלפון בעל הנכס"] else "", "price": r["מחיר"], "contacted": [],
            "famexcl": False, "rent": False, "feats": [], "desc": r["תיאור נכס"], "link": ""}


def office_row(r):
    return {"עיר / ישוב": r["עיר"], "שכונה": r["שכונה"], "כתובת": r["רחוב1"], "חדרים": r["חדרים"], 'מ"ר': "",
            "קומה": "", "מחיר": r["מחיר"], "סוג נכס": "דירה", "תיאור": ""}


def make(sess, coords=None, cfg=None):
    D._CACHE.update(t=0, v=None)
    st = {"cfg": cfg if cfg is not None else {"nbStatus": {}}, "logs": [], "push": []}

    def mutate(fn):
        fn(st["cfg"])
        return True, None
    G = AutoG(
        log=None, _web_auth=lambda: sess, _load_config=lambda: st["cfg"], _config_mutate=mutate,
        _log_activity=lambda *a: st["logs"].append(a), _display_name_for=lambda n, p: n,
        _canon_key=lambda n: " ".join(str(n or "").split()), _canon_agent_name=lambda n: n,
        _last9=lambda p: re.sub(r"\D", "", str(p or ""))[-9:],
        _coordinators_all=lambda: coords or {}, fetch_newborn=lambda: NB,
        _newborn_created_epoch=lambda r: r["_c"], _nb_key=lambda r: "id:" + r["מזהה"],
        _nb_clean=lambda v: str(v or "").strip(), _nb_as_office_row=office_row, _nb_row_out=row_out,
        _price_dropped_map=lambda: {}, _nb_price_key=lambda r: r["מזהה"], _fetch_newborn_contacts=lambda: {},
        _famexcl_addr_list=lambda: {}, _nb_alias_idx=lambda: None,
        _fetch_manual_buyers=lambda: [{"search": "דירה 5 חדרים בנאות אפק קרית ביאליק", "budget": "2,500,000"},
                                      {"search": "דירה 3 חדרים בקרית ים", "budget": "1,200,000"}],
        fetch_sheet_rows=lambda: [{"סוכן 1": "דנה לוי", "שכונה": "נאות אפק", "עיר / ישוב": "קרית ביאליק"}],
        fetch_agents_phones=lambda: {"דנה לוי": "0501111111", "רועי אברהם": "0502222222"},
        web_phone_name_map=lambda: {}, web_contacts_phone_name=lambda: {},
        _phones_for_name=lambda n: {"0501111111"} if n == "דנה לוי" else set(),
        send_push=lambda t, b, ids: st["push"].append((t, b, ids)))
    app = Flask(__name__)
    D.register(app, G)
    return app.test_client(), st


AG = {"name": "רויטל גל", "role": "agent", "drole": "agent", "phone": "501111111"}
CO = {"name": "מנהל", "role": "admin", "drole": "manager", "phone": "509999999"}   # מתאמת שנכנסת כמנהל
COORDS = {"509999999": {"name": "אוצר", "agents": set(), "names": set()}}

c, st = make(AG)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is False, "סוכן — אין גישה")
check(c.get("/v2/api/dialer/queue").get_json()["allowed"] is False, "סוכן — אין תור")
check(c.post("/v2/api/dialer/dial", json={"key": "id:1"}).get_json().get("allowed") is False, "סוכן — לא יכול לחייג מהחייגן")

c, st = make(CO, COORDS)
check(c.get("/v2/api/dialer/access").get_json()["allowed"] is True, "מתאמת (נכנסת כמנהל) — יש גישה")
q = c.get("/v2/api/dialer/queue").get_json()
keys = [i["key"] for i in q["items"]]
check(keys == ["id:1", "id:4"], "בתור: רק עם טלפון ומ-14 הימים האחרונים, הטרי ראשון")
it = q["items"][0]
check(it["buyers"] == 1 and it["tel"] == "0521112233", "קונה מתאים אחד, טלפון לחיוג")
check(it["agents"] and it["agents"][0]["name"] == "דנה לוי", "הסוכן המומלץ — דנה (נכס בנאות אפק)")
check(q["stats"]["calls"] == 0 and q["stats"]["goal"] == 5, "מונים")

r = c.post("/v2/api/dialer/dial", json={"key": "id:1", "addr": "הנוטר 18"}).get_json()
check(r["ok"] and st["cfg"]["v2_dialer"]["509999999"]["days"]["2026-11-03"]["calls"] == 1, "חיוג נספר")
check(st["cfg"]["v2_dialer"]["_global"]["claims"]["id:1"]["by9"] == "509999999", "הנכס נתפס למתאמת")
r = c.post("/v2/api/dialer/outcome", json={"key": "id:1", "outcome": "na", "addr": "הנוטר 18"}).get_json()
check(r["ok"] and r["retryAt"] == "17:30", "לא ענה → 17:30")
q = c.get("/v2/api/dialer/queue").get_json()
check([i["key"] for i in q["items"]] == ["id:4"] and q["later"][0]["key"] == "id:1", "עבר ל'לחזור אליהם בהמשך'")
r = c.post("/v2/api/dialer/outcome", json={"key": "id:4", "outcome": "meet", "addr": "עוזי חיטמן 7",
                                           "agent": "דנה לוי", "when": "מחר 10:00", "owner": "רינה"}).get_json()
import time as _t
_t.sleep(0.2)
check(r["ok"] and "id:4" in st["cfg"]["v2_dialer"]["_global"]["out"], "פגישה — יוצא מהתור לכל המתאמות")
check(st["push"] and st["push"][0][2] == ["501111111"] and "עוזי חיטמן 7" in st["push"][0][1], "פוש לסוכן שיגיע")
check(c.post("/v2/api/dialer/outcome", json={"key": "id:4", "outcome": "x"}).status_code == 400, "תוצאה לא חוקית — 400")
sl = c.get("/v2/api/dialer/slots?agent=דנה לוי").get_json()
check(sl["ok"] and sl["slots"][0]["label"] == "היום 17:00", "מועדים פנויים לסוכן")

print("8. JS")
js = re.search(r"<script>(.*)</script>", D.V2_DIALER_HTML, re.S).group(1)
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
    f.write(js)
rc = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
check(rc.returncode == 0, "תחביר JS תקין" + ("" if rc.returncode == 0 else ": " + rc.stderr[:200]))

print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
