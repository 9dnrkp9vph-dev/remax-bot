# tests/social_video/test_mem_guard.py — [22/11] אחרי נפילת השרת על חוסר זיכרון באמצע רינדור:
# לא מתחילים סרטון בלי זיכרון פנוי; רשומה שנתקעה 'בהכנה' אחרי אתחול משתחררת מיד; שאריות tmp נמחקות.
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m=""):
    global n; assert c, m; n += 1
import social_video as V
from _fakes import ROW, make_G

MB = 1 << 20
def cg(cur, lim, file_=0, shmem=0):
    d = {"/sys/fs/cgroup/memory.current": str(cur), "/sys/fs/cgroup/memory.max": str(lim),
         "/sys/fs/cgroup/memory.stat": "anon 1\nfile %d\nshmem %d\nactive_file 0\ninactive_file 0\n" % (file_, shmem)}
    def read(p):
        if p not in d: raise IOError(p)
        return d[p]
    return read

# מצב הזיכרון: מטמון קבצים לא נספר, tmpfs כן
ck(V.vid_mem_state(cg(1800 * MB, 2048 * MB, file_=500 * MB)) == (1300 * MB, 2048 * MB))
ck(V.vid_mem_state(cg(1800 * MB, 2048 * MB, file_=500 * MB, shmem=400 * MB)) == (1700 * MB, 2048 * MB))
ck(V.vid_mem_state(cg(100, "max")) == (None, None), "no limit")
def boom(p): raise IOError(p)
ck(V.vid_mem_state(boom) == (None, None), "unreadable (mac/tests)")

# ההחלטה
ck(V.vid_mem_ok({}, (1200 * MB, 2048 * MB)) == (True, 848))
ck(V.vid_mem_ok({}, (1600 * MB, 2048 * MB)) == (False, 448))
ck(V.vid_mem_ok({"VID_MEM_HEADROOM_MB": "300"}, (1600 * MB, 2048 * MB))[0] is True, "env threshold")
ck(V.vid_mem_ok({"VID_MEM_HEADROOM_MB": "0"}, (2040 * MB, 2048 * MB))[0] is True, "0 = off")
ck(V.vid_mem_ok({}, (None, None)) == (True, None), "unknown → allow")

# יצירה בלי זיכרון: נדחית בלי רשומה (האוטומטי ינסה שוב), עם הודעה לסוכן
ENV = {"SOCIAL_MODE": "publish", "APP_BASE_URL": "https://app", "META_TOKEN": "t"}
G, st, sb = make_G()
orig = V.vid_mem_state
V.vid_mem_state = lambda read=None: (1900 * MB, 2048 * MB)
try:
    r = V.vid_create_one(G, ROW["מספר מודעה"], "manual", "521234567", env=ENV, store=V.VidStore(tempfile.mkdtemp()))
finally:
    V.vid_mem_state = orig
ck(r["ok"] is False and r["reason"] == V.MEM_BUSY, r)
ck(not sb.videos, "no record written")

# רשומה שהתחילה לפני עליית התהליך = מתה מיד; רשומה טרייה של התהליך הזה — לא
now = time.time()
ck(V._dead_or_stale(now - 60, now, boot=now - 10) is True, "before boot")
ck(V._dead_or_stale(now - 60, now, boot=now - 600) is False, "ours, fresh")
ck(V._dead_or_stale(now - V.STALE_S - 1, now, boot=now - 99999) is True, "old")
ck(V._dead_or_stale(now - 3, now, boot=now) is False, "5s margin")

def iso(t): return V._iso(t)
G, st, sb = make_G()
old = sb.video_insert({"property_key": "k1", "status": "rendering"})
sb.videos[-1]["created_at"] = sb.videos[-1]["updated_at"] = iso(V._BOOT_TS - 120)
V._recover_stale(G, sb.videos, V._BOOT_TS + 30)
ck(sb.videos[-1]["status"] == "failed", sb.videos[-1])
fresh = sb.video_insert({"property_key": "k2", "status": "rendering"})
sb.videos[-1]["created_at"] = sb.videos[-1]["updated_at"] = iso(V._BOOT_TS + 20)
V._recover_stale(G, sb.videos, V._BOOT_TS + 30)
ck(sb.videos[-1]["status"] == "rendering", "live render untouched")

# ניקוי tmp: תיקיית רינדור ישנה נמחקת, טרייה ותיקיות אחרות נשארות
root = tempfile.mkdtemp()
for nm in ("vid_old", "vidc_old", "vid_new", "other"):
    os.mkdir(os.path.join(root, nm)); open(os.path.join(root, nm, "f"), "wb").write(b"x" * 10)
t0 = time.time()
for nm in ("vid_old", "vidc_old", "other"):
    os.utime(os.path.join(root, nm), (t0 - 7200, t0 - 7200))
gone, left = V.vid_tmp_sweep(t0, root=root)
ck(gone == 2 and sorted(os.listdir(root)) == ["other", "vid_new"], os.listdir(root))

ck("anon=" in V.vid_mem_report(cg(100 * MB, 2048 * MB)) and V.vid_mem_report(boom) == "")
print("ok", n)
