# tests/social/test_can.py — soc_can_publish
import os, sys, time, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from zoneinfo import ZoneInfo
IL = ZoneInfo("Asia/Jerusalem")
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=IL).timestamp()
def ago(h): return dt.datetime.fromtimestamp(NOW - h * 3600, IL).strftime("%d/%m/%Y %H:%M")
def iso(h): return dt.datetime.fromtimestamp(NOW - h * 3600, dt.timezone.utc).isoformat()
ROW = {"מספר מודעה": "tok1", "סוג עסקה": "מכירה", "חדרים": "4", "עיר / ישוב": "קרית ביאליק",
       "כתובת": "אהוד מנור", "מספר בית": "13", "קומה": "3", "_y2_first_seen": ago(10),
       "תמונות": ["https://x/a.jpg", "https://x/b.jpg"]}
AK = SP.soc_addr_key(ROW) + "#3"
def H(**kw):
    base = {"property_key": "tok1", "addr_key": AK, "mode": "publish", "fb_status": "ok", "ig_status": "ok",
            "created_at": iso(24 * 5)}
    base.update(kw); return base

ck(SP.soc_can_publish(ROW, "fb", [], NOW, set()) == (True, ""), "clean")
ck(SP.soc_can_publish(dict(ROW, **{"ירד מפרסום": "01/11/2026"}), "fb", [], NOW, set()) == (False, "ירד מפרסום"), "delisted")
ck(SP.soc_can_publish(dict(ROW, delisted_at="2026-11-01"), "fb", [], NOW, set())[1] == "ירד מפרסום", "delisted_at")
ck(SP.soc_can_publish(ROW, "fb", [], NOW, {"tok1"}) == (False, "מוסתר מהאתר"), "hidden")
ck(SP.soc_can_publish(ROW, "fb", [], NOW, {"L:tok1"}) == (False, "מוסתר מהאתר"), "hidden with L: prefix")
ck(SP.soc_can_publish(dict(ROW, **{"סוג עסקה": "מסחרי"}), "fb", [], NOW, set()) == (False, "מסחרי"), "commercial")
one = dict(ROW, תמונות=["https://x/a.jpg"])
ck(SP.soc_can_publish(one, "fb", [], NOW, set()) == (False, "מחכה לתמונות"), "one img fresh")
ck(SP.soc_can_publish(dict(one, _y2_first_seen=ago(73)), "fb", [], NOW, set()) == (True, ""), "one img old")
ck(SP.soc_can_publish(dict(ROW, תמונות=[], תמונה=""), "fb", [], NOW, set()) == (False, "אין תמונות"), "no imgs")

ok, why = SP.soc_can_publish(ROW, "fb", [H()], NOW, set())
ck(not ok and why.startswith("פורסם ") and "אפשר שוב מ-" in why, why)
ck(SP.soc_can_publish(ROW, "ig", [H(ig_status="failed")], NOW, set()) == (True, ""), "ig failed open")
other = H(property_key="tok9", created_at=iso(72))
ck(not SP.soc_can_publish(ROW, "fb", [other], NOW, set())[0], "same apartment other token")
ck(SP.soc_can_publish(ROW, "fb", [H(property_key="tok9", addr_key=SP.soc_addr_key(ROW) + "#5")], NOW, set()) == (True, ""), "diff floor")
ck(SP.soc_can_publish(ROW, "fb", [H(property_key="tok9", addr_key=SP.soc_addr_key(ROW) + "#")], NOW, set())[0] is False, "floor unknown one side")
ck(SP.soc_can_publish(ROW, "fb", [H(mode="preview", fb_status="preview")], NOW, set()) == (True, ""), "preview not counted")
ck(SP.soc_can_publish(ROW, "fb", [H(created_at=iso(24 * 15))], NOW, set()) == (True, ""), "15 days ok")
ck(SP.soc_can_publish(ROW, "ig", [H(ig_status="unknown", fb_status="ok", created_at=iso(1))], NOW, set()) == (False, "כבר נשלח היום"), "unknown today")
ck(SP.soc_can_publish(ROW, "fb", [H(fb_status="failed", created_at=iso(1))], NOW, set()) == (True, ""), "failed today retry ok")
print("social_can OK", n)
