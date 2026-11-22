# tests/crm/test_props_site_link.py — [22/11 אייל: 'קישור למודעה שלנו ב-refamily.co.il של כל מודעה']
# עמודת 'באתר' בנכסי המשרד: הקישור הקצר של האתר (/n/<מזהה>) — אותו מזהה שהאתר מחשב (sha1 של משרד|מספר מודעה).
import sys, os, hashlib
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
ns = _load.load("crm_props_records", "crm_site_link", "_crm_int", "_crm_rooms", "CRM_MODULES")
rec, link = ns["crm_props_records"], ns["crm_site_link"]
OID = "11111111-1111-4111-8111-111111111111"

# אותו מזהה כמו באתר (refsite/listings.py: prop_id)
exp = hashlib.sha1((OID + "|" + "abc123").encode("utf-8")).hexdigest()[:10]
ck(link(OID, "abc123", "https://refamily.co.il/") == "https://refamily.co.il/n/" + exp, link(OID, "abc123", "https://refamily.co.il/"))
ck(link(OID, "", "https://refamily.co.il") == "" and link("", "abc", "https://refamily.co.il") == "", "empty")

base = {"סוכן 1": "רפי", "כתובת": "דובדבן", "עיר / ישוב": "קרית ביאליק", "מחיר": "1,950,000", "_ep": 0}
of = [dict(base, **{"מספר מודעה": "ok1"}),
      dict(base, **{"מספר מודעה": "hid1"}),
      dict(base, **{"מספר מודעה": "gone1", "ירד מפרסום": "20/11/2026"}),
      dict(base, **{"מספר מודעה": ""})]
h = {"prop_ep": lambda r: 0, "prop_pkey": lambda r: "L:" + r["מספר מודעה"], "agent_name": lambda n: n,
     "site_link": lambda ad: "" if ad == "hid1" else link(OID, ad, "https://refamily.co.il")}
R = {r["ad_id"]: r for r in rec([], [], of, {}, 0, h)}
ck(R["ok1"]["site"] == link(OID, "ok1", "https://refamily.co.il"), R["ok1"])
ck(R["hid1"]["site"] == "", ("hidden from site", R["hid1"]))
ck(R["gone1"]["site"] == "", ("delisted", R["gone1"]))
ck(R[""]["site"] == "", ("no ad id", R[""]))
# בלי עוזר — לא נופל
R2 = rec([], [], of[:1], {}, 0, {k: v for k, v in h.items() if k != "site_link"})
ck(R2[0]["site"] == "", R2)

cols = {c[0]: c for c in ns["CRM_MODULES"]["props"]["columns"]}
ck("site" in cols and cols["site"][2] == "link" and len(cols["site"]) > 3, cols.get("site"))
ck("site" in ns["CRM_MODULES"]["props"]["default_cols"], "default column")
src = _load._SRC
i = src.index("def _build_props():"); seg = src[i:i + 2500]
ck('"site_link"' in seg and "crm_site_link(" in seg, "route wires site_link")
print("props_site_link OK", _load.n)
