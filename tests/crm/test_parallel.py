# tests/crm/test_parallel.py — CRM שלב 1: השוואת הזרם הישיר (צל) מול המסלול דרך פיירברי, ומי עוד מחתים בחתימה טובה
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_ts", "parallel_match_calls", "parallel_match_invoices", "sig_nonapp_by_agent",
                "inv_parse_dt", "inv_phone9")
match_calls, match_inv, sig_nonapp = ns["parallel_match_calls"], ns["parallel_match_invoices"], ns["sig_nonapp_by_agent"]

L = [dict(caller_phone="0546631493", agent_phone="0505235330", agent="אלי שמול", received_at="2026-10-18T14:08:10.000Z")]
D = [dict(caller_phone="546631493", agent_phone="505235330", agent="אלי שמול", received_at="18/10/2026 17:09")]
ck(match_calls(L, D)["matched"] == 1, "±120s, phone formats, Z vs Israel time")
D2 = [dict(caller_phone="546631493", agent_phone="505235330", received_at="18/10/2026 17:12")]
r = match_calls(L, D2)
ck(len(r["only_legacy"]) == 1 and len(r["only_direct"]) == 1 and r["matched"] == 0, r)
ck(r["only_legacy"][0]["phone"] == "1493" and r["only_legacy"][0]["agent"] == "אלי שמול", "privacy: last 4 only")
ck(match_calls(L + L, D)["matched"] == 1 and len(match_calls(L + L, D)["only_legacy"]) == 1, "one-to-one")
ck(match_inv([dict(doc_num="25134", phone9="504422040", amount="1", created_at="2026-10-16T10:12:00+03:00")],
             [dict(doc_num="25134", phone9="", amount="", created_at="")])["matched"] == 1, "doc_num wins")
ck(match_inv([dict(doc_num="", phone9="508148184", amount="3422.00", created_at="2026-10-15T13:06:00+03:00")],
             [dict(doc_num="", phone9="508148184", amount="3422", created_at="2026-10-15T13:26:00+03:00")])["matched"] == 1,
   "phone+amount+day")
ck(match_inv([dict(doc_num="1", phone9="", amount="", created_at="")], [])["only_legacy"], "missing direct")
sigs = [dict(agent="דידי לוי", commission_pct="https://sign.hatimatova.co.il/signpad/abc/?p=5", received_at="20/10/2026 10:00"),
        dict(agent="דידי לוי", commission_pct="https://sign.hatimatova.co.il/signpad/def/?p=5", received_at="21/10/2026 10:00"),
        dict(agent="יובל כהן", commission_pct="https://remax-bot.onrender.com/s/tok", received_at="20/10/2026 10:00"),
        dict(agent="רויטל גל", commission_pct="https://sign.hatimatova.co.il/signpad/old/?p=5", received_at="10/10/2026 10:00")]
ck(sig_nonapp(sigs, "2026-10-19") == [("דידי לוי", 2)], sig_nonapp(sigs, "2026-10-19"))
print("parallel OK", _load.n)
