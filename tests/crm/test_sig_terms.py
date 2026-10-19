# tests/crm/test_sig_terms.py — אייל: "לראות את התקציב גם במוכר ובבלעדיות, עד איזה תאריך וכמה עמלה"
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A, effie_v2 as E
T = {"fee": "2%", "rent": "", "excl_from": "2026-10-19", "excl_to": "2027-01-19"}
own = A._sign_terms(T, "OWNER_SALE", [2390000])
exc = A._sign_terms(T, "OWNER_EXCLUSIVE", [2390000])
buy = A._sign_terms(T, "CLIENT_SALE", [1500000, 1700000])
rnt = A._sign_terms({"rent": "1 חודשים"}, "OWNER_RENT", [6000])
ck(own == {"budget": "2390000", "fee": "2%"}, own)
ck(exc == {"budget": "2390000", "fee": "2%", "excl_from": "2026-10-19", "excl_to": "2027-01-19"}, exc)
ck(buy == {"budget": "1600000", "fee": "2%"}, buy)
ck(rnt == {"budget": "6000", "fee": "1 חודשים"}, rnt)
ck(A._sign_terms({"fee": "x" * 500}, "OWNER_SALE", [])["fee"] == "x" * 40, "capped")
ck(A._sign_terms(None, "OWNER_SALE", []) == {}, "no terms")
src = open(os.path.join(os.path.dirname(A.__file__), "app.py"), encoding="utf-8").read()
ck(src.count("_srec.update(_sign_terms(") == 2, "both signing routes store the terms")
ev = open(os.path.join(os.path.dirname(A.__file__), "effie_v2.py"), encoding="utf-8").read()
ck(ev.count("terms: TERMS") == 2, "the signing form sends the terms on both routes")
lab = {"OWNER_EXCLUSIVE": "בלעדיות", "OWNER_SALE": "מוכר"}
R = E.crm_sig_records([{"event_id": "e1", "deal_type": "OWNER_EXCLUSIVE", "client_name": "א", "budget": "2390000", "fee": "2%",
                        "excl_to": "2027-01-19", "commission_pct": "https://x/s/abc", "received_at": "1"},
                       {"event_id": "e2", "deal_type": "OWNER_SALE", "client_name": "ב", "commission_pct": "1.5", "received_at": "1"}],
                      {"ep": lambda s: 1.0, "label": lambda c: lab.get(c, c)})
ck(R[0]["budget"] == 2390000 and R[0]["fee"] == "2%" and R[0]["excl_to"] == "19/01/2027", R[0])
ck(R[1]["fee"] == "1.5%", ("Fireberry commission number shown as the fee", R[1]))
cols = [c[0] for c in E.CRM_MODULES["signatures"]["columns"]]
ck("fee" in cols and "excl_to" in cols and "fee" in E.CRM_MODULES["signatures"]["default_cols"], cols)
f = E.sig_ingest_norm({"event_id": "9", "agent": "רפי", "deal_type": "OWNER_EXCLUSIVE", "תאריך סיום בלעדיות": "19/01/2027"})
ck(f and f[2].get("excl_to") == "19/01/2027", ("Fireberry exclusivity end accepted", f))
print("sig_terms OK", n)
