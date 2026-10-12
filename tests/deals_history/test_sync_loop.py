# tests/deals_history/test_sync_loop.py
import sys, os, io, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import openpyxl
import deals_history as D
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
def xlsx(rows):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "עסקאות26"
    ws.append(['מס"ד', "תאריך עסקה", "עיר", "רחוב", "קונה / מוכר", "סוכן", "סכום העסקה", "עמלה לפני מעמ", "התקבל כסף"])
    for r in rows: ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()
FILES = {"/d": [{"name": "מעקב עסקאות 2026.xlsx", "path": "/d/m.xlsx", "rev": "r1", "server_modified": "2026-10-12T10:00:00Z"}]}
CONTENT = {"/d/m.xlsx": xlsx([[1, dt.datetime(2026, 1, 5), "קרית ים", "הרצל 1", "מוכר", "נדב", 900000, 9000, None],
                              [2, dt.datetime(2026, 2, 5), "קרית ים", "הרצל 2", "קונה", "חדש בלי מיפוי", 800000, 8000, 8000]])}
dl = []
class DBX:
    def configured(self): return True
    def list_folder(self, p): return FILES[p]
    def download(self, p): dl.append(p); return CONTENT[p], FILES["/d"][0]["rev"]
DB = {}
class SB:
    def enabled(self): return True
    def deal_history_all(self): return list(DB.values())
    def deal_history_upsert(self, rows):
        for r in rows: DB[r["src_key"]] = dict(r, id=r["src_key"])
        return len(rows)
    def deal_history_set_missing(self, keys, ts):
        for k in keys: DB[k]["missing_since"] = ts
        return len(keys)
D._AGENT_MAP_CACHE.clear(); D._AGENT_MAP_CACHE.update(m={"bialik|נדב": "נדב רייזר"}, ts=9e18)
st = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "2026-10-12T10:05:00Z", folder="/d", pw="")
ck(st["error"] == "" and st["rows"] == 2 and st["upserted"] == 2 and st["file"] == "מעקב עסקאות 2026.xlsx", st)
ck(DB["bialik|2026|עסקאות26|1"]["agent"] == "נדב רייזר" and DB["bialik|2026|עסקאות26|1"]["agent_raw"] == "נדב", "mapped")
ck(st["unmapped"] == ["חדש בלי מיפוי"], st["unmapped"])
ck(DB["bialik|2026|עסקאות26|2"]["paid_amount"] == 8000 and DB["bialik|2026|עסקאות26|2"]["src_path"] == "/d/m.xlsx", "fields")
# אותו rev → בלי הורדה ובלי כתיבה
before = len(dl)
st2 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "2026-10-12T10:10:00Z", folder="/d", pw="", last=st)
ck(len(dl) == before and st2["upserted"] == 0 and st2.get("skipped"), st2)
# rev חדש, שורה 2 נמחקה → מסומנת חסרה
CONTENT["/d/m.xlsx"] = xlsx([[1, dt.datetime(2026, 1, 5), "קרית ים", "הרצל 1", "מוכר", "נדב", 900000, 9000, 9000]])
FILES["/d"][0]["rev"] = "r2"
st3 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "2026-10-12T10:15:00Z", folder="/d", pw="", last=st)
ck(st3["upserted"] == 1 and st3["missing"] == 1 and DB["bialik|2026|עסקאות26|2"]["missing_since"] == "2026-10-12T10:15:00Z", st3)
ck(DB["bialik|2026|עסקאות26|1"]["paid_amount"] == 9000, "update applied")
# כשל הורדה / סיסמה → שגיאה במצב, הטבלה לא נגעה
class BAD(DBX):
    def download(self, p): raise RuntimeError("boom")
FILES["/d"][0]["rev"] = "r3"
snap = {k: dict(v) for k, v in DB.items()}
st4 = D.sync_branch("bialik", 2026, SB(), BAD(), lambda x: x, "2026-10-12T10:20:00Z", folder="/d", pw="", last=st3)
ck("boom" in st4["error"] and DB == snap, st4)
# בלי קובץ מעקב בתיקייה
FILES["/e"] = []
st5 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "t", folder="/e", pw="")
ck(st5["error"] == "אין קובץ מעקב בתיקייה", st5)
# מעבר קובץ → switched + התראה
pushes = []
FILES["/d"].append({"name": "מעקב עסקאות 2026 (Ohad's conflicted copy).xlsx", "path": "/d/c.xlsx", "rev": "c1", "server_modified": "2026-10-12T11:00:00Z"})
CONTENT["/d/c.xlsx"] = CONTENT["/d/m.xlsx"]
st6 = D.sync_branch("bialik", 2026, SB(), DBX(), lambda x: x, "t6", folder="/d", pw="", last=st3, push=lambda t, b: pushes.append((t, b)))
ck(st6["switched"] and pushes and "conflicted" in pushes[0][1], (st6, pushes))
print("OK", n, "checks")
