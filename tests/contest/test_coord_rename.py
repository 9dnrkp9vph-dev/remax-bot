# 17/11 (אייל): 'למה לא מופיעות הפגישות של המתאמת נויה בתחרות?' — באמצע התחרות נוסף לה שם משפחה
# ('נויה' → 'נויה אלבר'), והפגישות נספרו לפי שם בלבד. עכשיו גם לפי הטלפון שתיאמה ממנו.
import os, sys, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import contest as C

fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

canon = lambda n: " ".join(str(n or "").split())
IL = C._IL
ts = lambda d, h=12: dt.datetime(2026, 11, d, h, 0, tzinfo=IL).timestamp()
ct = {"id": "nov", "name": "x", "start": "2026-11-01", "end": "2026-11-30", "pts": {"gius": 30, "meeting": 5},
      "groups": [{"name": "A", "rows": [{"label": "רועי", "members": ["רועי עמור"]}], "coords": ["נויה אלבר"]},
                 {"name": "B", "rows": [{"label": "אחר", "members": ["אחר"]}], "coords": []}]}
nb = {
    "a": {"status": "meeting", "meeting_at": "2026-11-05T14:19", "date": "2026-11-20T10:00", "agent": "רועי עמור",
          "by": "נויה", "by_phone": "0526066767", "addr": "אלכסנדר זייד 116"},
    "b": {"status": "meeting", "meeting_at": "2026-11-12T12:12", "date": "2026-11-21T10:00", "agent": "רועי עמור",
          "by": "נויה אלבר", "by_phone": "0526066767", "addr": "נעמי שמר 6"},
    "c": {"status": "meeting", "meeting_at": "2026-11-12T12:30", "date": "2026-11-22T10:00", "agent": "רועי עמור",
          "by": "אוצר בן חמו", "by_phone": "0528899985", "addr": "מנשה 20"},
}
now = ts(17)
led = C.ledger_update({}, nb, ct, now, lambda b, p: b)
check(led["a"]["by_phone"] == "526066767", "הטלפון של מי שתיאם נשמר ברישום")

def coord(board):
    return board["groups"][0]["coords"][0]["meetings"]

b0 = C.score(ct, led, {}, [], canon, now)
check(coord(b0) == 1, "בלי טלפונים — רק הפגישה בשם החדש (המצב לפני התיקון)")
b1 = C.score(ct, led, {}, [], canon, now, coord_phones={"נויה אלבר": {"526066767"}})
check(coord(b1) == 2, "עם הטלפון — גם הפגישה שנקבעה בשם הישן נספרת")
check(b1["groups"][0]["rows"][0]["meetings"] == 0, "הסוכן לא מקבל את פגישות המתאמות (כלל 03/11 נשמר)")
led2 = dict(led); led2["d"] = dict(led["c"], by="מנהל", by_phone="526066767")
b2 = C.score(ct, led2, {}, [], canon, now, coord_phones={"נויה אלבר": {"526066767"}})
check(coord(b2) == 2, "פגישה בשם גנרי 'מנהל' לא נספרת למתאמת לפי טלפון")
print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
