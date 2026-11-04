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
    ck((x["meetings"], x["gius"], x["points"]) == (2, 1, 40), x)
    ck("pd" not in x and x["power_pts"] == 0 and r["power_today"] is False and r["power_days"] == [])
    ck(r["days_left"] == 11 and r["pts"] == {"gius": 30, "meeting": 5})
    ck(c.score(c.NOV_2026, led, sigs, [], canon, T(2026, 12, 5))["days_left"] == 0)

def test_team_shared_gius():
    sigs = [sig("אלי שמול", "הרצל 5", "10/11/2026 10:00"), sig("יהודית שמול", "הרצל 5 קומה 2", "11/11/2026 10:00")]
    x = row(c.score(c.NOV_2026, {}, sigs, [], canon, NOW), "אלי ויהודית")
    ck(x["gius"] == 1 and x["points"] == 30)

def test_coord_credit():
    # לפני 03/11 14:35 — הכלל הקודם: לסוכן, ומתאמת שקבעה לסוכן גם לה
    led = {"1": {"agent": "רויטל גל", "by": "נוי רבן", "at": T(2026, 11, 3), "when": None},
           "2": {"agent": "רויטל גל", "by": "אייל שמול", "at": T(2026, 11, 3), "when": None},
           "3": {"agent": "נוי רבן", "by": "נוי רבן", "at": T(2026, 11, 3), "when": None}}
    r = c.score(c.NOV_2026, led, [], [], canon, NOW)
    ck(row(r, "רויטל גל")["meetings"] == 2)
    ck(coord(r, "נוי רבן")["meetings"] == 1 and coord(r, "נוי רבן")["points"] == 5)

def test_booker_only_from_cutoff():
    # [03/11] מ-14:35 — רק למי שתיאם; לפני כן — הכלל הקודם
    ck(c.BOOKER_ONLY_FROM == T(2026, 11, 3, 14) + 35 * 60)
    late = T(2026, 11, 3, 15)
    led = {"1": {"agent": "רויטל גל", "by": "נוי רבן", "at": late, "when": None},
           "2": {"agent": "רויטל גל", "by": "אייל שמול", "at": late, "when": None},
           "3": {"agent": "נוי רבן", "by": "נוי רבן", "at": late, "when": None},
           "4": {"agent": "רויטל גל", "by": "רויטל גל", "at": late, "when": None},
           "5": {"agent": "רויטל גל", "by": "מנהל", "at": late, "when": None},
           "6": {"agent": "נדב רייזר", "by": "רויטל גל", "at": late, "when": None},
           "7": {"agent": "נדב רייזר", "by": "נוי רבן", "at": T(2026, 11, 3, 14), "when": None}}
    r = c.score(c.NOV_2026, led, [], [], canon, NOW)
    ck(row(r, "רויטל גל")["meetings"] == 3, row(r, "רויטל גל"))   # 4, 6, 5 (מתאם לא ידוע)
    ck(row(r, "נדב רייזר")["meetings"] == 1, row(r, "נדב רייזר"))  # 7 — לפני הזמן, לסוכן
    ck(coord(r, "נוי רבן")["meetings"] == 3)                       # 1, 3 (אחרי) + 7 (לפני, לסוכן אחר)
    r2 = c.score(dict(c.NOV_2026, booker_only_from=0), led, [], [], canon, NOW)
    ck(row(r2, "נדב רייזר")["meetings"] == 0)

def test_total_and_adj():
    led = {"1": {"agent": "רויטל גל", "by": "נוי רבן", "at": T(2026, 11, 3), "when": None}}
    adj = [{"id": "1", "group": "קבוצה א'", "kind": "row", "label": "נדב רייזר", "pts": 25, "reason": "", "by": "", "at": 0},
           {"id": "2", "group": "קבוצה א'", "kind": "coord", "label": "נוי רבן", "pts": -5, "reason": "", "by": "", "at": 0}]
    r = c.score(c.NOV_2026, led, [], adj, canon, NOW)
    ck(row(r, "נדב רייזר")["points"] == 25 and row(r, "נדב רייזר")["adj"] == 25)
    ck(coord(r, "נוי רבן")["points"] == 0 and coord(r, "נוי רבן")["adj"] == -5)
    ck(r["groups"][0]["total"] == 30)      # 25 + 5 של רויטל (נקבעה לפני 03/11 14:35 — הכלל הקודם); בלי המתאמת
    ck(row(r, "נדב רייזר")["rank"] == 1 and row(r, "רויטל גל")["rank"] == 2)

def test_unknown_and_missing():
    r = c.score(c.NOV_2026, {}, [], [], canon, NOW)
    ck(coord(r, "נויה")["meetings"] == 0 and coord(r, "נויה")["points"] == 0)
    r = c.score(c.NOV_2026, {"1": {"agent": "נדב רייזר", "by": "נדב רייזר", "at": T(2026, 11, 3), "when": None}}, None, [], canon, NOW)
    x = row(r, "נדב רייזר")
    ck(x["gius"] is None and x.get("partial") is True and x["points"] == 5)
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

def test_power_day_scoring():
    # [POWER-DAY 04/11] גיוס 60 לפי יום החתימה, פגישה 10 לפי יום הקביעה; תיקון ידני לא מוכפל
    PD = "2026-11-10"
    led = {"a": {"agent": "נדב רייזר", "by": "נדב רייזר", "at": T(2026, 11, 10, 11), "when": T(2026, 11, 18)},  # נקבעה ב-PD
           "b": {"agent": "נדב רייזר", "by": "נדב רייזר", "at": T(2026, 11, 8), "when": T(2026, 11, 10)},       # מתקיימת ב-PD, נקבעה קודם
           "c": {"agent": "רויטל גל", "by": "נוי רבן", "at": T(2026, 11, 10, 15), "when": None}}               # מתאמת ב-PD (אחרי 03/11)
    sigs = [sig("נדב רייזר", "הרצל 5", "10/11/2026 10:00"), sig("נדב רייזר", "ויצמן 3", "09/11/2026 10:00"),
            sig("נדב רייזר", "הרצל 5", "12/11/2026 10:00")]   # אותו נכס שוב — הראשונה (ב-PD) קובעת
    adj = [{"id": "1", "group": "קבוצה א'", "kind": "row", "label": "נדב רייזר", "pts": 7, "reason": "", "by": "", "at": 0}]
    r = c.score(c.NOV_2026, led, sigs, adj, canon, NOW, [PD])
    x = row(r, "נדב רייזר")
    ck((x["gius"], x["meetings"]) == (2, 2), x)
    ck(x["points"] == 60 + 30 + 10 + 5 + 7, x)
    ck((x["power_gius"], x["power_meetings"], x["power_pts"]) == (1, 1, 70), x)
    y = coord(r, "נוי רבן")
    ck(y["points"] == 10 and y["power_pts"] == 10 and y["power_meetings"] == 1, y)
    ck(row(r, "רויטל גל")["points"] == 0)
    ck(r["groups"][0]["total"] == 112, r["groups"][0]["total"])   # בלי המתאמת
    ck(r["power_today"] is False and r["power_days"] == [PD] and r["power_mult"] == 2)
    # ביום עצמו
    r2 = c.score(c.NOV_2026, led, sigs, [], canon, T(2026, 11, 10, 18), [PD])
    ck(r2["power_today"] is True)
    # יום עתידי — לא נספר ולא נחשף
    r3 = c.score(c.NOV_2026, led, sigs, [], canon, T(2026, 11, 9, 18), [PD])
    ck(r3["power_today"] is False and r3["power_days"] == [] and row(r3, "נדב רייזר")["power_pts"] == 0)
    # בלי power — כמו קודם
    ck(row(c.score(c.NOV_2026, led, sigs, [], canon, NOW), "נדב רייזר")["points"] == 30 + 30 + 5 + 5)
    # חתימות נכשלו — פגישות עדיין מוכפלות, גיוס לא ידוע
    r4 = c.score(c.NOV_2026, led, None, [], canon, NOW, [PD])
    ck(row(r4, "נדב רייזר")["points"] == 15 and row(r4, "נדב רייזר")["gius"] is None)


def test_power_days_cfg():
    cfg = {"v2_contest_power": {"2026-11": ["2026-11-12", "bad", "2026-11-05", "2026-11-12"]}}
    ck(c.power_days(cfg, "2026-11") == ["2026-11-05", "2026-11-12"])
    ck(c.power_days({}, "2026-11") == [] and c.power_days(None, "x") == [])
    ck(c.il_day(T(2026, 11, 10, 23)) == "2026-11-10" and c.il_day(T(2026, 11, 11, 0)) == "2026-11-11")


def test_power_message_and_recipients():
    t = c.power_text(c.NOV_2026)
    ck("\n" not in t and "בתחרות נובמבר" in t and "60 נקודות" in t and "פגישה 10" in t, t)
    names = c.power_recipients(c.NOV_2026, ["אייל שמול", "אודי שמול", "מתן ביטון", "נדב רייזר"], canon)
    ck(names.count("נדב רייזר") == 1 and "נוי רבן" in names and "אוצר בן חמו" in names, names)
    ck(names[-3:] == ["אייל שמול", "אודי שמול", "מתן ביטון"], names[-3:])
    ck("בינימין אביטן" in names and "בן קדוש" in names and "בן ובנימין" not in names)
    ck(len(names) == 23 + 4 + 3, len(names))


def test_power_due_and_pending():
    IL = _IL
    day = "2026-11-10"
    at = lambda h, m=0: dt.datetime(2026, 11, 10, h, m, tzinfo=IL)
    ck(c.power_due(at(8, 59), [day], False) is None)
    ck(c.power_due(at(9, 0), [day], False) == day)
    ck(c.power_due(at(19, 59), [day], False) == day and c.power_due(at(20, 0), [day], False) is None)
    ck(c.power_due(at(10), [day], True) is None)          # שבת / השתקה
    ck(c.power_due(at(10), ["2026-11-11"], False) is None)
    now = at(10).timestamp()
    rec = {"א": {"r": "sent", "ts": now - 10, "tries": 1}, "ב": {"r": "fail", "ts": now - 60, "tries": 1},
           "ג": {"r": "fail", "ts": now - 1000, "tries": 1}, "ד": {"r": "no_phone", "ts": 0, "tries": 1},
           "ה": {"r": "fail", "ts": 0, "tries": 8}}
    ck(c.power_pending(["א", "ב", "ג", "ד", "ה", "ו"], rec, now, canon) == ["ג", "ו"])
    s = c.power_sent_summary({"v2_contest_power_sent": {"2026-11": {day: rec}}}, "2026-11")
    ck(s[day] == {"sent": 1, "fail": 3, "no_phone": 1}, s)


for k, f in list(globals().items()):
    if k.startswith("test_"): f()
print("OK", N[0])
