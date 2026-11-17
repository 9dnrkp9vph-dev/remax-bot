# tests/social/test_plan.py — soc_seed_known / soc_plan_round
import os, sys, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from zoneinfo import ZoneInfo
IL = ZoneInfo("Asia/Jerusalem")
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=IL).timestamp()
def iso(h): return dt.datetime.fromtimestamp(NOW - h * 3600, dt.timezone.utc).isoformat()
def fs(h): return dt.datetime.fromtimestamp(NOW - h * 3600, IL).strftime("%d/%m/%Y %H:%M")
def row(k, imgs=2, street=None):
    return {"מספר מודעה": k, "סוג עסקה": "מכירה", "חדרים": "4", "עיר / ישוב": "קרית ביאליק",
            "כתובת": street or ("רחוב " + k), "מספר בית": "1", "_y2_first_seen": fs(0),
            "תמונות": ["https://x/%s%d.jpg" % (k, i) for i in range(imgs)]}

old = [row("o%d" % i) for i in range(480)]
st = SP.soc_seed_known(old, NOW)
ck(len(st["known"]) == 480 and st.get("enabled_at") == NOW, len(st["known"]))
r = SP.soc_plan_round(old, st, [], NOW, set(), False)
ck(r["publish"] == [] and not r["flood"], r["publish"][:3])   # Review Focus 4

r = SP.soc_plan_round(old + [row("new1")], st, [], NOW, set(), False)
ck(r["publish"] == ["new1"] and "new1" in r["state"]["known"], r)

flood = [row("f%d" % i) for i in range(41)]
r = SP.soc_plan_round(old + flood, st, [], NOW, set(), False)
ck(r["publish"] == [] and r["flood"] and all("f%d" % i in r["state"]["known"] for i in range(41)), r["reason"])

H5 = [{"property_key": "p%d" % i, "trigger": "auto", "mode": "publish", "fb_status": "ok", "created_at": iso(0.5 + i * 0.5)} for i in range(5)]
four_ = [row("m%d" % i) for i in range(4)]
# [18/11 אייל] התקרה היומית: 10 פוסטים אוטומטיים ביום (היה 5)
ck(SP.DAILY_CAP == 10, SP.DAILY_CAP)
ck(SP.soc_plan_round(old + [row("new2")], st, H5, NOW, set(), False)["publish"] == ["new2"], "5 today → still room")
H9 = [dict(H5[0], property_key="q%d" % i, created_at=iso(0.5 + i * 0.5)) for i in range(9)]
ck(SP.soc_plan_round(old + four_, st, H9, NOW, set(), False)["publish"].__len__() == 1, "9 today → one slot left")
H5 = [dict(H5[0], property_key="p%d" % i, created_at=iso(0.5 + i * 0.5)) for i in range(10)]
r = SP.soc_plan_round(old + [row("new2")], st, H5, NOW, set(), False)
ck(r["publish"] == [] and "new2" in r["state"]["waiting"] and r["reason"] == "התקרה היומית", r)
Hm = [dict(h, trigger="manual") for h in H5]
ck(SP.soc_plan_round(old + [row("new2")], st, Hm, NOW, set(), False)["publish"] == ["new2"], "manual not counted")

four = [row("n%d" % i) for i in range(4)]
ck(len(SP.soc_plan_round(old + four, st, [], NOW, set(), False)["publish"]) == SP.ROUND_CAP, "round cap")
recent = [{"property_key": "zz", "trigger": "auto", "mode": "publish", "fb_status": "ok", "created_at": iso(10 / 60)}]
ck(SP.soc_plan_round(old + [row("new3")], st, recent, NOW, set(), False)["publish"] == [], "gap")

st_w = dict(st, waiting={"w1": NOW - 4 * 86400}, known=dict(st["known"], w1=NOW))
r = SP.soc_plan_round(old + [row("w1")], st_w, [], NOW, set(), False)
ck(r["publish"] == [] and "w1" not in r["state"]["waiting"], r)
st_w2 = dict(st, waiting={"w2": NOW - 3600}, known=dict(st["known"], w2=NOW))
ck(SP.soc_plan_round(old + [row("w2")], st_w2, [], NOW, set(), False)["publish"] == ["w2"], "waiting published")

night = dt.datetime(2026, 11, 3, 23, 30, tzinfo=IL).timestamp()
r = SP.soc_plan_round(old + [row("nn")], st, [], night, set(), False)
ck(r["publish"] == [] and "nn" in r["state"]["known"] and "nn" in r["state"]["waiting"], r)
r = SP.soc_plan_round(old + [row("bb")], st, [], NOW, set(), True)
ck(r["publish"] == [] and "bb" in r["state"]["known"], "blocked")

stale = dict(st, known=dict(st["known"], gone=NOW - 61 * 86400))
ck("gone" not in SP.soc_plan_round(old, stale, [], NOW, set(), False)["state"]["known"], "prune")

r = SP.soc_plan_round(old + [row("one", imgs=1)], st, [], NOW, set(), False)
ck(r["publish"] == [] and "one" in r["state"]["waiting"], r)
# [18/11 אייל] נכס עם פחות מ-2 תמונות מחכה בלי הגבלת זמן — "גם אם העדכון של התמונות אחרי חודש" — ואז עולה אוטומטית
s2, t = r["state"], NOW
for d in range(1, 41):                                  # 40 יום, סבב ביום, עדיין תמונה אחת
    t = NOW + d * 86400
    r = SP.soc_plan_round(old + [row("one", imgs=1)], s2, [], t, set(), False)
    s2 = r["state"]
    ck(r["publish"] == [] and "one" in s2["waiting"] and "one" in s2["known"], ("day", d))
r = SP.soc_plan_round(old + [row("zero", imgs=0)], st, [], NOW, set(), False)
r = SP.soc_plan_round(old + [row("zero", imgs=0)], r["state"], [], NOW + 10 * 86400, set(), False)
ck(r["publish"] == [] and "zero" in r["state"]["waiting"], "no photos at all also waits")
r = SP.soc_plan_round(old + [row("one", imgs=3)], s2, [], t + 600, set(), False)   # המזכירה הוסיפה תמונות
ck(r["publish"] == ["one"] and "one" not in r["state"]["waiting"], r)
gone = SP.soc_plan_round(old, s2, [], t + 600, set(), False)                      # הנכס ירד בינתיים → יוצא מהתור
ck("one" not in gone["state"]["waiting"], "listing gone → dropped")
print("social_plan OK", n)
