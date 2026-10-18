#!/usr/bin/env python3
"""[CRM-1 19/10] ייבוא היסטוריה מ-CSV של פיירברי (לוג שיחות / מתעניינים / מקבלי מסמכים) לאפי.

    python3 tools/import_fireberry.py calls      "לוג שיחות.csv"
    python3 tools/import_fireberry.py signatures "מתעניינים.csv"
    python3 tools/import_fireberry.py invoices   "מקבלי מסמכים.csv"   [--save]

בלי --save: ריצה יבשה — דוח בלבד, שום דבר לא נכתב. עם --save: רק הרשומות שסווגו "חדשה".
SUPABASE_URL / SUPABASE_SERVICE_KEY / SB_OFFICE_ID מה-env (חסר → שאלה מוסתרת).
המנרמלים נלקחים מ-effie_v2.py עצמו (אותו מפתח ואותו hash כמו הקליטה החיה). קובצי ה-CSV לא נכנסים לגיט.
"""
import ast, csv, getpass, hashlib, io, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
_NAMES = ("call_ingest_norm", "sig_ingest_norm", "inv_ingest_row", "inv_parse_dt", "inv_phone9",
          "inv_name_key", "inv_norm_type", "crm_ts")
_ns = {"_re": re, "re": re}
for _node in ast.parse(open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()).body:
    if isinstance(_node, ast.FunctionDef) and _node.name in _NAMES:
        exec(compile(ast.Module([_node], []), "effie_v2.py", "exec"), _ns)
call_ingest_norm, sig_ingest_norm, inv_ingest_row = _ns["call_ingest_norm"], _ns["sig_ingest_norm"], _ns["inv_ingest_row"]
inv_phone9, crm_ts = _ns["inv_phone9"], _ns["crm_ts"]

# שמות עמודות בייצוא פיירברי → השמות שהמנרמלים מכירים (ראשון שקיים ולא ריק)
_CALL_COLS = {"call_uuid": ("מזהה", "מזהה רשומה", "id"), "agent": ("שם הסוכן", "סוכן"),
              "caller_phone": ("טלפון לקוח",), "agent_phone": ("טלפון סוכן",),
              "callstatus": ("סטטוס",), "created": ("נוצר בתאריך", "תאריך"),
              "summary": ("סיכום תמלול", "סיכום"), "duration_sec": ("משך שיחה", "משך")}
_SIG_ALIAS = {"תאריך": ("נוצר בתאריך",), "commission_pct": ("קישור1", "קישור", "עמלה"),
              "phone": ("סלולרי", "סלולרי בלי 0")}


def _pick(row, names):
    for n in names:
        v = row.get(n)
        if v is not None and str(v).strip() not in ("", "-"):
            return str(v).strip()
    return ""


def call_triple(caller, agent_phone, when):
    ts = crm_ts(when)
    return (inv_phone9(caller), inv_phone9(agent_phone), None if ts is None else int(ts // 60))


def _inv_triple(rec):
    try:
        amt = round(float(str(rec.get("amount", "")).replace(",", "")), 2)
    except ValueError:
        amt = None
    return (rec.get("phone9", ""), amt, str(rec.get("created_at", ""))[:10])


def _record(module, sk, riso, raw):
    import supabase_db as S
    return S.call_record(sk, riso, raw) if module == "calls" else S.signature_record(sk, riso, raw)


def fb_plan(module, rows, existing):
    """לכל שורת CSV: {"action": new|exists|reject, "source_key", "reason", "record"}.
    existing — calls: {event_ids, triples}; signatures: {keys, event_ids}; invoices: {hashes, docnums, triples}.
    רשומה שמופיעה פעמיים בקובץ נספרת חדשה פעם אחת."""
    out, seen = [], set()
    for row in rows:
        if module == "invoices":
            rec = inv_ingest_row(row)
            if not rec:
                out.append({"action": "reject", "source_key": "", "reason": "no_name", "record": None})
                continue
            sk, trip = rec["row_hash"], _inv_triple(rec)
            if (sk in existing["hashes"] or sk in seen or (rec["doc_num"] and rec["doc_num"] in existing["docnums"])
                    or (trip[0] and trip[1] is not None and trip in existing["triples"])):
                out.append({"action": "exists", "source_key": sk, "reason": "", "record": rec})
            else:
                out.append({"action": "new", "source_key": sk, "reason": "", "record": rec})
            seen.add(sk)
            continue
        if module == "calls":
            body = {k: _pick(row, v) for k, v in _CALL_COLS.items()}
            fid = body["call_uuid"]
            if not fid:
                if not (body["caller_phone"] or body["agent_phone"]):
                    out.append({"action": "reject", "source_key": "", "reason": "empty", "record": None})
                    continue
                body["call_uuid"] = hashlib.sha1("|".join([body["caller_phone"], body["agent_phone"], body["created"]])
                                                 .encode("utf-8")).hexdigest()
            _, riso, raw, _, _ = call_ingest_norm(body)
            sk = ("fbimp:" + fid) if fid else ("fbimph:" + body["call_uuid"])
            raw["event_id"] = fid or sk
            c, a, m = call_triple(body["caller_phone"], body["agent_phone"], body["created"])
            near = m is not None and any((c, a, m + d) in existing["triples"] for d in (-1, 0, 1))
            dup = (fid and fid in existing["event_ids"]) or near or sk in seen
            out.append({"action": "exists" if dup else "new", "source_key": sk, "reason": "",
                        "record": _record("calls", sk, riso, raw)})
            seen.add(sk)
            continue
        # signatures
        body = dict(row)
        for k, names in _SIG_ALIAS.items():
            if not _pick(body, (k,)):
                body[k] = _pick(row, names)
        norm = sig_ingest_norm(body)
        if not norm:
            out.append({"action": "reject", "source_key": "", "reason": "empty", "record": None})
            continue
        sk, riso, raw = norm
        eid = raw.get("event_id", "")
        dup = sk in existing["keys"] or (eid and eid in existing["event_ids"]) or sk in seen
        out.append({"action": "exists" if dup else "new", "source_key": sk, "reason": "",
                    "record": _record("signatures", sk, riso, raw)})
        seen.add(sk)
    return out


def _load_existing(module):
    import supabase_db as S
    if module == "calls":
        recs = S._get_all("calls", "event_id,caller_phone,agent_phone,raw")
        return {"event_ids": {r.get("event_id") for r in recs if r.get("event_id")},
                "triples": {call_triple(r.get("caller_phone"), r.get("agent_phone"), (r.get("raw") or {}).get("received_at"))
                            for r in recs}}
    if module == "signatures":
        recs = S._get_all("signatures", "source_key,event_id")
        return {"keys": {r.get("source_key") for r in recs}, "event_ids": {r.get("event_id") for r in recs if r.get("event_id")}}
    recs = S._get_all("invoices", "row_hash,doc_num,phone9,amount,created_at")
    return {"hashes": {r.get("row_hash") for r in recs}, "docnums": {r.get("doc_num") for r in recs if r.get("doc_num")},
            "triples": {_inv_triple(r) for r in recs}}


def _read_csv(path):
    data = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1255"):
        try:
            return list(csv.DictReader(io.StringIO(data.decode(enc))))
        except UnicodeDecodeError:
            continue
    raise SystemExit("לא הצלחתי לקרוא את הקובץ (קידוד)")


def _mask(rec):
    raw = (rec or {}).get("raw") or rec or {}
    who = raw.get("agent") or raw.get("client_name") or (rec or {}).get("client_name", "")
    ph = raw.get("caller_phone") or raw.get("phone") or (rec or {}).get("phone", "")
    when = raw.get("received_at") or (rec or {}).get("created_at", "")
    return "%s · %s · …%s" % (when, who, inv_phone9(ph)[-4:])


def main(argv):
    if len(argv) < 3 or argv[1] not in ("calls", "signatures", "invoices"):
        raise SystemExit(__doc__)
    module, path, save = argv[1], argv[2], "--save" in argv
    for var in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SB_OFFICE_ID"):
        if not os.environ.get(var):
            os.environ[var] = getpass.getpass(var + ": ").strip()
    import supabase_db as S
    rows = _read_csv(path)
    print("שורות בקובץ: %d · עמודות: %s" % (len(rows), ", ".join(rows[0].keys()) if rows else "-"))
    items = fb_plan(module, rows, _load_existing(module))
    by = {}
    for it in items:
        by.setdefault(it["action"], []).append(it)
    for act in ("new", "exists", "reject"):
        lst = by.get(act, [])
        print("\n%s: %d" % (act, len(lst)))
        for it in lst[:10]:
            print("   ", _mask(it["record"]) if it["record"] else it["reason"])
    new = [it["record"] for it in by.get("new", [])]
    if not save:
        print("\nריצה יבשה — לא נכתב כלום. להרצה אמיתית: הוסף --save")
        return
    if module == "invoices":
        n = S.insert_invoice_rows(new)
    else:
        n = S._upsert_bulk(module, new)
    print("\nנכתבו %d רשומות ל-%s" % (n, module))


if __name__ == "__main__":
    main(sys.argv)
