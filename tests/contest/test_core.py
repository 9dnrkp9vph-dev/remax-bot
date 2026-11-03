# tests/contest/test_core.py — ליבת חישוב התחרות. python3 tests/contest/test_core.py
import os, sys, copy, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import contest as c
from goals import _IL

N = [0]
def ck(cond, m=""):
    assert cond, m
    N[0] += 1

canon = lambda n: " ".join(str(n or "").split())
disp = lambda by, ph: by
D = dt.date
NOW = dt.datetime(2026, 11, 20, 12, 0, tzinfo=_IL).timestamp()
def T(y, m, d, h=10): return dt.datetime(y, m, d, h, 0, tzinfo=_IL).timestamp()

def rec(agent, by, at, when="2026-11-25T10:00", status="meeting"):
    return {"status": status, "agent": agent, "by": by, "meeting_at": at, "date": when}

def sig(agent, addr, ts, signed=True):
    return {"agent": agent, "address": addr, "type": "בלעדיות", "signed": signed, "ts": ts}

def row(res, name):
    for g in res["groups"]:
        for r in g["rows"]:
            if r["label"] == name: return r
def coord(res, name):
    for g in res["groups"]:
        for r in g["coords"]:
            if r["name"] == name: return r

# seed
ck(c.NOV_2026["id"] == "2026-11" and c.NOV_2026["pts"] == {"gius": 30, "meeting": 5})
ck(len(c.NOV_2026["groups"]) == 2)
ck(c.NOV_2026["groups"][0]["coords"] == ["נוי רבן", "נויה"] and c.NOV_2026["groups"][1]["coords"] == ["הודיה צרויה", "אוצר בן חמו"])
ck(c.NOV_2026["groups"][0]["rows"][5] == {"label": "בן ובנימין", "members": ["בינימין אביטן", "בן קדוש"]})
ck(not any("?" in m for g in c.NOV_2026["groups"] for r in g["rows"] for m in r["members"]))
ck(any(m == "ליאור גורפינקל" for r in c.NOV_2026["groups"][0]["rows"] for m in r["members"]))

def test_pick():
    ck(c.pick({}, D(2026, 11, 15)) == (c.NOV_2026, "live"))
    ck(c.pick({}, D(2026, 12, 2))[1] == "winner")
    ck(c.pick({}, D(2026, 12, 4)) == (None, None))
    ck(c.pick({}, D(2026, 10, 31)) == (None, None))
    a = dict(c.NOV_2026, id="a", start="2026-11-10"); 
    ck(c.pick({"v2_contests": {"list": [c.NOV_2026, a]}}, D(2026, 11, 15))[0]["id"] == "a")
    ck(c.contests(None) == [c.NOV_2026])

def test_prev_month():
    ck(c.prev_month(D(2026, 11, 1)) == (D(2026, 10, 1), D(2026, 10, 31)))
    ck(c.prev_month(D(2026, 1, 1)) == (D(2025, 12, 1), D(2025, 12, 31)))

def test_validate():
    ck(c.validate(c.NOV_2026, canon) is None)
    x = copy.deepcopy(c.NOV_2026); x["groups"][1]["rows"][0]["members"].append("נדב רייזר")
    ck(isinstance(c.validate(x, canon), str))
    x = copy.deepcopy(c.NOV_2026); x["groups"][1]["coords"].append("נדב  רייזר")   # סוכן=מתאמת, רווח כפול
    ck(isinstance(c.validate(x, canon), str))
    x = copy.deepcopy(c.NOV_2026); x["end"] = "2026-10-01"
    ck(isinstance(c.validate(x, canon), str))
    x = copy.deepcopy(c.NOV_2026); x["start"] = "זבל"
    ck(isinstance(c.validate(x, canon), str))
    x = copy.deepcopy(c.NOV_2026); x["pts"]["gius"] = -1
    ck(isinstance(c.validate(x, canon), str))
    x = copy.deepcopy(c.NOV_2026); x["pts"]["meeting"] = 1001
    ck(isinstance(c.validate(x, canon), str))
    x = copy.deepcopy(c.NOV_2026); x["groups"] = x["groups"][:1]
    ck(isinstance(c.validate(x, canon), str))
    # [FIX4] מבנה: כל צורה שבורה נדחית (ולא מפילה)
    def bad(mut):
        x = copy.deepcopy(c.NOV_2026); mut(x)
        try:
            r = c.validate(x, canon)
        except Exception as e:
            raise AssertionError("validate crashed: %r" % e)
        ck(isinstance(r, str), r)
    bad(lambda x: x.__setitem__("groups", "ab"))
    bad(lambda x: x["groups"].__setitem__(0, "קבוצה"))
    bad(lambda x: x["groups"][0].__setitem__("name", 5))
    bad(lambda x: x["groups"][0].__setitem__("rows", "x"))
    bad(lambda x: x["groups"][0]["rows"].__setitem__(0, "נדב"))
    bad(lambda x: x["groups"][0]["rows"][0].__setitem__("label", ""))
    bad(lambda x: x["groups"][0]["rows"][0].__setitem__("label", 7))
    bad(lambda x: x["groups"][0]["rows"][0].__setitem__("members", "נדב רייזר"))
    bad(lambda x: x["groups"][0]["rows"][0].__setitem__("members", []))
    bad(lambda x: x["groups"][0]["rows"][0].__setitem__("members", [""]))
    bad(lambda x: x["groups"][0]["rows"][0].__setitem__("members", [3]))
    bad(lambda x: x["groups"][0].__setitem__("coords", "נוי"))
    bad(lambda x: x["groups"][0].__setitem__("coords", [None]))
    bad(lambda x: x["pts"].__setitem__("gius", 2.5))
    bad(lambda x: x["pts"].__setitem__("meeting", True))
    bad(lambda x: x.__setitem__("pts", "x"))

def test_ledger_add():
    nb = {"k1": rec("רויטל גל", "נוי רבן", "05/11/2026 10:00"),
          "manual:x": rec("נדב רייזר", "נדב רייזר", "2026-11-05T09:00:00+02:00"),
          "old": rec("רויטל גל", "נוי רבן", "30/10/2026 10:00"),
          "f": rec("רויטל גל", "נוי רבן", "05/11/2026 10:00", status="followup")}
    L = c.ledger_update({}, nb, c.NOV_2026, NOW, disp)
    ck(set(L) == {"k1", "manual:x"}, L)
    ck(L["k1"]["agent"] == "רויטל גל" and L["k1"]["by"] == "נוי רבן" and L["k1"]["when"] == T(2026, 11, 25))
    ck(L["k1"]["at"] == T(2026, 11, 5))
    src = {}; c.ledger_update(src, nb, c.NOV_2026, NOW, disp); ck(src == {})

def test_ledger_keeps_real_by():
    # [FIX-m3] שם גנרי ('מנהל…' / ריק) לא דורס שם אמיתי שכבר ברישום
    nb = {"k1": rec("רויטל גל", "מנהל", "05/11/2026 10:00")}
    old = {"k1": {"agent": "רויטל גל", "by": "נוי רבן", "at": T(2026, 11, 5), "when": T(2026, 11, 25)}}
    L = c.ledger_update(old, nb, c.NOV_2026, NOW, lambda by, ph: "מנהל · 1234" if by == "מנהל" else by)
    ck(L["k1"]["by"] == "נוי רבן", L)
    L = c.ledger_update({}, nb, c.NOV_2026, NOW, lambda by, ph: "מנהל · 1234")
    ck(L["k1"]["by"] == "מנהל · 1234", L)
    L = c.ledger_update(old, {"k1": rec("רויטל גל", "הודיה צרויה", "05/11/2026 10:00")}, c.NOV_2026, NOW, disp)
    ck(L["k1"]["by"] == "הודיה צרויה", L)

def test_ledger_deleted():
    led = {"k": {"agent": "א", "by": "ב", "at": T(2026, 11, 5), "when": T(2026, 11, 25)}}
    ck(c.ledger_update(led, {}, c.NOV_2026, NOW, disp) == {})                      # לפני המועד
    led["k"]["when"] = T(2026, 11, 10)
    ck("k" in c.ledger_update(led, {}, c.NOV_2026, NOW, disp))                      # אחרי המועד
    led["k"]["when"] = T(2026, 11, 25)
    nb = {"k": rec("א", "ב", "05/11/2026 10:00", status="followup")}
    ck(c.ledger_update(led, nb, c.NOV_2026, NOW, disp) == {})                       # הפך לפולו-אפ
    ck(c.ledger_update(led, None, c.NOV_2026, NOW, disp) == led)                    # כשל
    ck(c.ledger_update(led, None, c.NOV_2026, NOW, disp) is not led)

def test_score_basic():
    led = {"a": {"agent": "נדב רייזר", "by": "נדב רייזר", "at": T(2026, 11, 3), "when": None},
           "b": {"agent": "נדב רייזר", "by": "נדב רייזר", "at": T(2026, 11, 4), "when": None}}
    sigs = [sig("נדב רייזר", "הרצל 5", "10/11/2026 10:00"),
            sig("נדב רייזר", "ויצמן 3", "11/11/2026 10:00", signed=False),
            sig("נדב רייזר", "בגין 1", "12/10/2026 10:00")]
    r = c.score(c.NOV_2026, led, sigs, [], canon, NOW)
    x = row(r, "נדב רייזר")
    ck((x["meetings"], x["gius"], x["pd"], x["points"]) == (2, 1, 1, 40), x)
    ck(r["days_left"] == 11 and r["pts"] == {"gius": 30, "meeting": 5})
    ck(c.score(c.NOV_2026, led, sigs, [], canon, T(2026, 12, 5))["days_left"] == 0)

def test_team_shared_gius():
    sigs = [sig("אלי שמול", "הרצל 5", "10/11/2026 10:00"), sig("יהודית שמול", "הרצל 5 קומה 2", "11/11/2026 10:00")]
    x = row(c.score(c.NOV_2026, {}, sigs, [], canon, NOW), "אלי ויהודית")
    ck(x["gius"] == 1 and x["points"] == 30)

def test_coord_credit():
    led = {"1": {"agent": "רויטל גל", "by": "נוי רבן", "at": T(2026, 11, 3), "when": None},
           "2": {"agent": "רויטל גל", "by": "אייל שמול", "at": T(2026, 11, 3), "when": None},
           "3": {"agent": "נוי רבן", "by": "נוי רבן", "at": T(2026, 11, 3), "when": None},
           "4": {"agent": "רויטל גל", "by": "רויטל גל", "at": T(2026, 11, 3), "when": None},
           "5": {"agent": "רויטל גל", "by": "מנהל", "at": T(2026, 11, 3), "when": None},
           "6": {"agent": "נדב רייזר", "by": "רויטל גל", "at": T(2026, 11, 3), "when": None}}
    r = c.score(c.NOV_2026, led, [], [], canon, NOW)
    # [03/11] רק למי שתיאם: 1 ו-3 לנוי, 2 לאייל, 4 ו-6 לרויטל, 5 (מתאם לא ידוע) לסוכן
    ck(row(r, "רויטל גל")["meetings"] == 3, row(r, "רויטל גל"))
    ck(row(r, "נדב רייזר")["meetings"] == 0)
    ck(coord(r, "נוי רבן")["meetings"] == 2 and coord(r, "נוי רבן")["points"] == 10)

def test_total_and_adj():
    led = {"1": {"agent": "רויטל גל", "by": "נוי רבן", "at": T(2026, 11, 3), "when": None}}
    adj = [{"id": "1", "group": "קבוצה א'", "kind": "row", "label": "נדב רייזר", "pts": 25, "reason": "", "by": "", "at": 0},
           {"id": "2", "group": "קבוצה א'", "kind": "coord", "label": "נוי רבן", "pts": -5, "reason": "", "by": "", "at": 0}]
    r = c.score(c.NOV_2026, led, [], adj, canon, NOW)
    ck(row(r, "נדב רייזר")["points"] == 25 and row(r, "נדב רייזר")["adj"] == 25)
    ck(coord(r, "נוי רבן")["points"] == 0 and coord(r, "נוי רבן")["adj"] == -5)
    ck(r["groups"][0]["total"] == 25)      # הפגישה שנוי קבעה לרויטל — לנוי בלבד, לא לקבוצה
    ck(row(r, "נדב רייזר")["rank"] == 1 and row(r, "רויטל גל")["rank"] == 2)

def test_unknown_and_missing():
    r = c.score(c.NOV_2026, {}, [], [], canon, NOW)
    ck(coord(r, "נויה")["meetings"] == 0 and coord(r, "נויה")["points"] == 0)
    r = c.score(c.NOV_2026, {"1": {"agent": "נדב רייזר", "by": "נדב רייזר", "at": T(2026, 11, 3), "when": None}}, None, [], canon, NOW)
    x = row(r, "נדב רייזר")
    ck(x["gius"] is None and x["pd"] is None and x.get("partial") is True and x["points"] == 5)
    ck(r.get("partial") is True and r["leader"] is None, "board partial + no leader when sigs fail")
    ck("partial" not in c.score(c.NOV_2026, {}, [], [], canon, NOW))

def test_leader():
    r = c.score(c.NOV_2026, {}, [], [], canon, NOW); ck(r["leader"] is None)
    led = {"1": {"agent": "נדב רייזר", "by": "נדב רייזר", "at": T(2026, 11, 3), "when": None}}
    ck(c.score(c.NOV_2026, led, [], [], canon, NOW)["leader"] == 0)

def test_anchors():
    ck(c.listing_anchors(["א"], (0, 1), None, canon) is None)
    ck(c.listing_anchors(["א"], (0, 1e12), [], canon) == set())

def test_ledger_dupes_and_generic_agent():
    # [02/11 'נחמי זקס 9'] אותה פגישה נשמרה 4 פעמים → אחת; [02/11 'אייל שמול פגישה?'] סוכן 'מנהל' → לפי הטלפון
    nb = {"manual:%d" % i: dict(rec("נחמי זקס", "נחמי זקס", "05/11/2026 10:00"), addr="רועי") for i in range(4)}
    nb["m"] = dict(rec("מנהל", "מנהל", "05/11/2026 11:00"), by_phone="111", addr="נעמי שמר 18")
    d2 = lambda by, ph: "אוצר בן חמו" if ph == "111" else by
    L = c.ledger_update({}, nb, c.NOV_2026, NOW, d2)
    ck(sum(1 for r in L.values() if r["agent"] == "נחמי זקס") == 1, L)
    ck(L["m"]["agent"] == "אוצר בן חמו" and L["m"]["by"] == "אוצר בן חמו", L["m"])
    # כפילות ישנה שכבר ברישום (מועד שעבר) לא חוזרת כשהמקורית עדיין קיימת
    old = {k: dict(v, when=T(2026, 11, 1)) for k, v in L.items()}
    nb1 = {"manual:0": dict(rec("נחמי זקס", "נחמי זקס", "05/11/2026 10:00", when="2026-11-01T10:00"), addr="רועי")}
    old["manual:9"] = dict(old["manual:0"])
    L2 = c.ledger_update(old, nb1, c.NOV_2026, NOW, disp)
    ck(sum(1 for r in L2.values() if r["agent"] == "נחמי זקס") == 1, L2)

for k, f in list(globals().items()):
    if k.startswith("test_"): f()
print("OK", N[0])
