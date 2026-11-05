# tests/newborn/test_nb_dropat.py — זמן ירידת המחיר בשורת נכס נולד (לסדר בתגית 'ירידות מחיר', 06/11)
import os, sys, time, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("WARMUP_ON_BOOT", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import app as A
now = time.time()
A._load_config = lambda: {"v2_price_drops": {"N:a": {"ts": now - 3600, "old": "100"}, "N:b": {"ts": now - 9 * 86400, "old": "5"}}}
m = A._price_drop_ts_map()
assert m == {"N:a": int(now - 3600)}, m
A._nb_notes_for = lambda *a, **k: []
row = {"תיאור נכס": "דירה", "מחיר": "90"}
A._nb_price_key = lambda r: "N:a"
ctx = {"contacts": {}, "statuses": {}, "pd_map": {"N:a": "100"}, "pd_ts": m, "eff_name": "x", "phone9": "", "notes_admin": False, "fam_list": {}}
out = A._nb_row_out(row, 0, "קרית מוצקין", "הרצל 5", "", "", True, ctx)
assert out["priceDropAt"] == int(now - 3600) and out["priceOld"] == "100", out
out = A._nb_row_out(row, 0, "קרית מוצקין", "הרצל 5", "", "", False, dict(ctx, pd_ts=None))
assert out["priceDropAt"] == 0
print("ok 3")
