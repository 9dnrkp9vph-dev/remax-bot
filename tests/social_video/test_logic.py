# tests/social_video/test_logic.py — חיתוך, תקרות, מכונת מצבים, ניקוי (טהור)
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_video as V
from _fakes import ROW
from zoneinfo import ZoneInfo
IL = ZoneInfo("Asia/Jerusalem")
NOW = dt.datetime(2026, 11, 2, 12, 0, tzinfo=IL).timestamp()
def iso(t): return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()

# ── חיתוך ──
TL = (0.03, 0.03, 0.17, 0.13)
b = V.vid_crop_box(1440, 960, TL)
ck(b and b[2] - b[0] == 540 and b[1] == 0 and b[3] == 960, b)
ck(b[0] >= 0.17 * 1440, b)
b0 = V.vid_crop_box(1440, 960, TL, bias=0.0)
ck(b0[0] >= 0.17 * 1440, b0)
ck(V.vid_crop_box(1440, 960, None, bias=0.0)[0] == 0, "no wm, bias 0")
mid = V.vid_crop_box(1440, 960, (0.45, 0.88, 0.6, 0.97))
ck(mid and (mid[2] <= 0.45 * 1440 or mid[0] >= 0.6 * 1440), mid)
ck(V.vid_crop_box(1440, 960, (0.2, 0.9, 0.8, 0.97)) is None, "wide wm -> None")
tall = V.vid_crop_box(600, 1600, None)   # תמונה אנכית צרה מ-9:16 → חיתוך גובה
ck(tall[2] - tall[0] == 600 and tall[3] - tall[1] == int(600 * 16 / 9), tall)

pr = V.vid_pan_range(1440, 960, None)
ck(pr == (0.25, 0.75), pr)
pl = V.vid_pan_range(1440, 960, TL)
ck(pl and pl[0] * (1440 - 540) >= 0.17 * 1440 - 1 and pl[1] <= 1.0 and pl[1] > pl[0], pl)
ck(V.vid_pan_range(1440, 960, (0.2, 0.9, 0.8, 0.97)) is None, "pan none")

# ── מותר ליצור ──
ok, why = V.vid_can_create(ROW, [], NOW, set(), "manual")
ck(ok, why)
ck(V.vid_can_create(ROW, [], NOW, {"tok1"}, "manual") == (False, "מוסתר מהאתר"), "hidden")
ck(V.vid_can_create(dict(ROW, **{"סוג עסקה": "מסחרי"}), [], NOW, set(), "auto")[1] == "מסחרי", "commercial")
one = dict(ROW, **{"תמונות": ["https://img/a.jpg"], "_y2_first_seen": "01/01/2026 10:00"})
ck(V.vid_can_create(one, [], NOW, set(), "manual") == (False, "צריך לפחות 2 תמונות"), "one image")
H = [{"property_key": "tok1", "status": "published", "created_at": iso(NOW - 5 * 86400), "addr_key": "x"}]
ok, why = V.vid_can_create(ROW, H, NOW, set(), "manual")
ck(not ok and "כבר נוצר סרטון" in why, why)
same = [{"property_key": "other", "status": "pending", "created_at": iso(NOW - 86400),
         "addr_key": V.SP.soc_addr_key(ROW) + "#3"}]
ck(not V.vid_can_create(ROW, same, NOW, set(), "manual")[0], "same apartment")
for st in ("failed", "skipped", "expired"):
    ck(V.vid_can_create(ROW, [dict(H[0], status=st)], NOW, set(), "manual")[0], st)
ck(V.vid_can_create(ROW, [dict(H[0], created_at=iso(NOW - 15 * 86400))], NOW, set(), "manual")[0], "old")
ren = [{"property_key": "tok1", "status": "rendering", "created_at": iso(NOW - 60)}]
ck(V.vid_can_create(ROW, ren, NOW, set(), "manual") == (False, "כבר בתהליך"), "in flight")

# ── תקרות ──
auto3 = [{"trigger": "auto", "ai": True, "created_at": iso(NOW - 60 * i)} for i in range(3)]
ck(V.vid_caps(auto3, NOW, "auto") == (False, "תקרה יומית (3)"), "daily")
ck(V.vid_caps(auto3, NOW, "manual")[0], "manual not daily")
yday = [{"trigger": "auto", "ai": True, "created_at": iso(NOW - 86400 - 60 * i)} for i in range(3)]
ck(V.vid_caps(yday, NOW, "auto")[0], "yesterday")
m100 = [{"trigger": "manual", "ai": True, "created_at": iso(NOW - 60 * i)} for i in range(100)]
ck(V.vid_caps(m100, NOW, "manual") == (False, "תקרה חודשית (100 קליפים)"), "monthly")
ck(V.vid_caps([dict(r, ai=False) for r in m100], NOW, "manual")[0], "non-ai not counted")

# ── מכונת מצבים ──
rec = {"status": "pending", "sent_at": iso(NOW - 3600)}
ck(V.vid_decide(rec, "pub", "אייל", NOW) == ("approved", "יעלה עכשיו"), V.vid_decide(rec, "pub", "אייל", NOW))
ck(V.vid_decide(rec, "skip", "אייל", NOW)[0] == "skipped", "skip")
done = {"status": "approved", "decided_by": "אייל", "sent_at": iso(NOW - 3600)}
ck(V.vid_decide(done, "pub", "דנה", NOW) == (None, "כבר פורסם ע\"י אייל"), V.vid_decide(done, "pub", "דנה", NOW))
ck(V.vid_decide(dict(done, status="skipped"), "pub", "דנה", NOW) == (None, "כבר דולג ע\"י אייל"), "skipped msg")
old = {"status": "pending", "sent_at": iso(NOW - 49 * 3600)}
ck(V.vid_decide(old, "pub", "אייל", NOW) == ("expired", "הסרטון כבר לא בתוקף"), "expired")
ck(V.vid_decide(dict(old, status="expired"), "pub", "x", NOW)[1] == "הסרטון כבר לא בתוקף", "expired again")

# ── מתי לפרסם ──
ck(V.vid_publish_when(NOW, False) == NOW, "now")
night = dt.datetime(2026, 11, 2, 23, 30, tzinfo=IL).timestamp()
ck(V.vid_publish_when(night, True) == dt.datetime(2026, 11, 3, 8, 0, tzinfo=IL).timestamp(), "next 8am")
early = dt.datetime(2026, 11, 3, 6, 0, tzinfo=IL).timestamp()
ck(V.vid_publish_when(early, True) == dt.datetime(2026, 11, 3, 8, 0, tzinfo=IL).timestamp(), "same-day 8am")

# ── ניקוי ──
D = 86400
files = [("a", 10, NOW - 4 * D), ("b", 10, NOW - 4 * D), ("c", 10, NOW - 11 * D), ("d", 10, NOW - 1 * D), ("e", 10, NOW - 4 * D)]
recs = {"a": {"status": "published", "updated_at": iso(NOW - 4 * D)},
        "b": {"status": "pending", "updated_at": iso(NOW - 4 * D)},
        "c": {"status": "pending", "updated_at": iso(NOW - 11 * D)},
        "d": {"status": "skipped", "updated_at": iso(NOW - 1 * D)},
        "e": {"status": "partial", "updated_at": iso(NOW - 4 * D)}}
gone = set(V.vid_gc(files, recs, NOW))
ck(gone == {"a", "c", "e"}, gone)   # partial: עבר זמן הניסיון החוזר (3 ימים)
ck("x" in V.vid_gc([("x", 1, NOW - 2 * D)], {}, NOW) and not V.vid_gc([("y", 1, NOW - 600)], {}, NOW), "orphan file (>1 day)")
big = [("o%d" % i, 400_000_000, NOW - (10 - i) * 3600) for i in range(4)]
bigrec = {f[0]: {"status": "skipped", "updated_at": iso(NOW - 3600)} for f in big}
ck(V.vid_gc(big, bigrec, NOW) == ["o0", "o1"], V.vid_gc(big, bigrec, NOW))
print("video_logic OK", n)
