# tests/crm/test_invoices_direct.py — CRM שלב 1: חשבוניות מהתוכנה החיצונית (?via=direct) → צל עד הניתוק
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["INVOICES_INGEST_KEY"] = "ik"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
class FakeSB:
    def __init__(s): s.shadow, s.inv = [], []
    def enabled(s): return True
    def shadow_upsert(s, st, sk, iso, raw): s.shadow.append((st, sk, iso, raw)); return True
    def insert_invoice_row(s, row): s.inv.append(row); return False   # False → בלי וואטסאפ בבדיקה
fs = FakeSB(); A._sbdb = fs
A._log_activity = lambda *a: None
c = A.app.test_client(); H = {"X-Ingest-Key": "ik"}
body = {"name": "מילה ברזין", "phone": "0508148184", "doc_type": "חשבונית מס", "doc_num": "25134",
        "amount": "3422.00", "created": "15/10/2026 13:06", "link": "bit.ly/x"}
os.environ.pop("INVOICES_DIRECT", None)
j = c.post("/v2/api/invoices/ingest?via=direct", json=body, headers=H).get_json()
ck(j["ok"] and j.get("mode") == "shadow", j)
ck(len(fs.shadow) == 1 and not fs.inv, (fs.shadow, fs.inv))
st, sk, iso, raw = fs.shadow[0]
ck(st == "invoices" and sk == raw["row_hash"] and raw["doc_num"] == "25134" and iso.startswith("2026-10-15"), fs.shadow[0])
j = c.post("/v2/api/invoices/ingest", json=body, headers=H).get_json()
ck(j["ok"] and len(fs.inv) == 1 and len(fs.shadow) == 1, "no via → existing path")
os.environ["INVOICES_DIRECT"] = "live"
c.post("/v2/api/invoices/ingest?via=direct", json=body, headers=H)
ck(len(fs.inv) == 2 and len(fs.shadow) == 1, "live → existing path")
print("invoices_direct OK", n)
