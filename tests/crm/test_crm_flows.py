# tests/crm/test_crm_flows.py — מודולים 'נכנס ויוצא' ו'אוטומציות' (טהור)
import sys, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
import _load
from _load import ck
from zoneinfo import ZoneInfo
ns = _load.load("crm_flow_records", "crm_automation_records", "crm_query", "CRM_FLOW_MAP", "CRM_AUTOMATIONS",
                "CRM_VIEWS", "_crm_day", "_crm_norm", "crm_ts", "inv_parse_dt", "inv_phone9")
flows, autos, query = ns["crm_flow_records"], ns["crm_automation_records"], ns["crm_query"]
IL = ZoneInfo("Asia/Jerusalem")
now = datetime.datetime(2026, 10, 19, 15, 0, tzinfo=IL).timestamp()
act = [{"ts": now - 60, "name": "Fireberry", "role": "system", "action": "חתימה מפיירברי", "detail": "יעל מור הרצל 5"},
       {"ts": now - 120, "name": "וואטסאפ רשמי", "role": "system", "action": "וואטסאפ רשמי — נכשל", "detail": "…4567 · template"},
       {"ts": now - 180, "name": "אלי שמול", "role": "agent", "action": "וואטסאפ מהטלפון — נכס נולד", "detail": "/v2/newborn"},
       {"ts": now - 240, "name": "אלי שמול", "role": "agent", "action": "חיפוש נכסים", "detail": "4 חדרים"},     # לא זרם
       {"ts": now - 300, "name": "אתר", "role": "site", "action": "פנייה מהאתר — הערכת שווי", "detail": "דנה"},
       {"ts": now - 86400 * 3, "name": "סורק יד2", "role": "system", "action": "סריקת יד2 — נקלטה", "detail": "נכס נולד 40 · שת\"פ 12"}]
F = flows(act)
ck(len(F) == 5, ("only flow actions", [f["action"] for f in F]))
by = {f["action"]: f for f in F}
ck(by["חתימה מפיירברי"]["direction"] == "נכנס" and by["חתימה מפיירברי"]["channel"] == "חתימות", by["חתימה מפיירברי"])
ck(by["וואטסאפ רשמי — נכשל"]["direction"] == "יוצא" and by["וואטסאפ רשמי — נכשל"]["failed"], "failed flag")
ck(by["וואטסאפ מהטלפון — נכס נולד"]["channel"] == "וואטסאפ מהטלפון" and by["פנייה מהאתר — הערכת שווי"]["channel"] == "אתר", "channels")
ck(len({f["key"] for f in F}) == 5, "unique keys")
q = lambda **k: query(F, k.get("q", ""), k.get("filters", {}), "date", "desc", 1, 50, now, module="flows")
ck([f["action"] for f in q(filters={"view": "in"})["rows"]] == ["חתימה מפיירברי", "פנייה מהאתר — הערכת שווי", "סריקת יד2 — נקלטה"], "in view")
ck(q(filters={"view": "out"})["total"] == 2 and q(filters={"view": "failed"})["total"] == 1, "out + failed views")
ck(q(filters={"view": "today"})["total"] == 4, "today")
ck(q(q="יעל")["total"] == 1, "search detail")
A = autos(act, {"BS_ALERTS": "0"}, now)
ab = {a["key"]: a for a in A}
ck(len(A) == len(ns["CRM_AUTOMATIONS"]) and all(a["name"] and a["trigger"] for a in A), "catalog")
ck(ab["sig_ingest"]["last"] == now - 60 and ab["sig_ingest"]["count7"] == 1, ab["sig_ingest"])
ck(ab["buyer_seller"]["status"] == "כבויה", "env flag off")
ck(ab["yad2_ingest"]["count7"] == 1, "yad2 counted")
qa = query(A, "", {"view": "off"}, "name", "asc", 1, 50, now, module="automations")
ck(any(r["key"] == "buyer_seller" for r in qa["rows"]) and all(r["status"] == "כבויה" for r in qa["rows"]), "off view")
# מודול השיחות ממשיך לעבוד בברירת המחדל
ck(query([], "", {"view": "missed"}, "date", "desc", 1, 50, now)["total"] == 0, "calls default")
print("crm_flows OK", _load.n)
