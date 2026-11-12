"""[LIVE-CALLS 13/11] איחוד השורה הישירה (mk:) עם שורת פיירברי לאותה שיחה."""
import ast, hashlib, pathlib, re

SRC = (pathlib.Path(__file__).resolve().parents[2] / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
NS = {"_hashlib": hashlib, "re": re}
for n in TREE.body:
    if isinstance(n, ast.FunctionDef) and n.name in ("_dedupe_direct_calls", "_last9", "_epoch_from_iso", "_call_uid"):
        exec(compile(ast.Module([n], []), "app.py", "exec"), NS)
dd = NS["_dedupe_direct_calls"]

def row(eid, caller, agent, at, **kw):
    return dict(event_id=eid, caller_phone=caller, agent_phone=agent, received_at=at, **kw)

# לפני המעבר — אין שורות mk: → בלי שינוי
legacy = [row("fb1", "0501111111", "0522222222", "2026-11-13T10:02:00.000Z")]
assert dd(list(legacy)) == legacy

# אותה שיחה: ישירה 10:00, פיירברי 10:03 → נשארת הישירה, עם _legacy_uid
d = row("mk:aaa", "0501111111", "0522222222", "2026-11-13T10:00:00Z", transcript_summary="")
l = row("fb1", "0501111111", "0522222222", "2026-11-13T10:03:00.000Z", transcript_summary="סיכום")
out = dd([l, d])
assert out == [d] and d["_legacy_uid"] == "fb1" and d["transcript_summary"] == "סיכום", out

# טלפון לקוח אחר / רחוק מ-15 דק' → נשארות שתיהן
d2 = row("mk:bbb", "0503333333", "0522222222", "2026-11-13T11:00:00Z")
l2 = row("fb2", "0504444444", "0522222222", "2026-11-13T11:01:00Z")
l3 = row("fb3", "0503333333", "0522222222", "2026-11-13T11:30:00Z")
assert len(dd([d2, l2, l3])) == 3

# שתי שיחות של אותו לקוח → כל שורה ישירה בולעת שורה אחת בלבד (הקרובה)
a = row("mk:c1", "0505555555", "0522222222", "2026-11-13T12:00:00Z")
b = row("mk:c2", "0505555555", "0522222222", "2026-11-13T12:08:00Z")
la = row("fbA", "0505555555", "0522222222", "2026-11-13T12:02:00Z")
lb = row("fbB", "0505555555", "0522222222", "2026-11-13T12:10:00Z")
out = dd([a, b, la, lb])
assert out == [a, b] and a["_legacy_uid"] == "fbA" and b["_legacy_uid"] == "fbB", out

# חייגן: agent_phone ריק בשני הצדדים, המחייג = הקו הווירטואלי
c = row("mk:d", "0529125944", "", "2026-11-13T13:00:00Z")
lc = row("fbC", "0529125944", "", "2026-11-13T13:02:00Z")
assert dd([c, lc]) == [c]
print("ok")
