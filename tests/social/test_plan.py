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

H5 = [{"property_key": "p%d" % i, "trigger": "auto", "mode": "publish", "fb_status": "ok", "created_at": iso(3 + i)} for i in range(5)]
r = SP.soc_plan_round(old + [row("new2")], st, H5, NOW, set(), False)
ck(r["publish"] == [] and "new2" in r["state"]["waiting"], r)
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
print("social_plan OK", n)
