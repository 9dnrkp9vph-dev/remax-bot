"""העברת קונה לסוכן אחר (אייל 14/10) — מנהלים בלבד; הקונה, הדף וההתראות עוברים לסוכן החדש."""
import effie_v2
from tests.siteweb.conftest import AutoG

ROLES = {"505709865": "developer", "521111111": "manager", "522222222": "agent", "523333333": "accountant"}

def _G(writes, pushes, logs, buyers=None):
    names = {"אייל שמול": ["0505709865"], "דנה לוי": ["0522222222"], "חגית": ["0523333333"], "מתן": ["0521111111"]}
    return AutoG(
        _resolve_roles=lambda p9: ("admin" if ROLES.get(p9) != "agent" else "agent", ROLES.get(p9, "agent")),
        _last9=lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:],
        _norm_name=lambda n: " ".join(str(n or "").split()), _canon_key=lambda n: " ".join(str(n or "").split()),
        _name_key=lambda n: n, _removed_agent_keys=lambda: set(), _is_dev=lambda p: False,
        web_contacts_phone_name=lambda: {}, web_phone_name_map=lambda: {}, _load_config=lambda: {"agents": [{"name": n} for n in names]},
        _phones_for_name=lambda n: names.get(n, []),
        _fetch_manual_buyers=lambda: buyers if buyers is not None else [{"row": 7, "name": "רון כהן", "agent": "אייל שמול", "search": "4 חדרים באפקה"}],
        _buyers_write=lambda a, p: (writes.append((a, p)), {"ok": True})[1], _cache_clear=lambda *a: None,
        send_push=lambda t, b, to=None: pushes.append((t, b, to)), _log_activity=lambda *a: logs.append(a))

def test_targets_only_for_managers():
    G = _G([], [], [])
    st, j = effie_v2.buyer_transfer_targets(G, {"phone": "0522222222", "role": "agent"})
    assert st == 403
    st, j = effie_v2.buyer_transfer_targets(G, {"phone": "0521111111", "role": "admin"})
    assert st == 200 and "דנה לוי" in j["agents"] and "אייל שמול" in j["agents"] and "חגית" not in j["agents"]

def test_transfer_moves_buyer_and_notifies_new_agent():
    w, p, l = [], [], []
    G = _G(w, p, l)
    st, j = effie_v2.buyer_transfer(G, {"phone": "0505709865", "role": "admin", "name": "אייל שמול"}, 7, "דנה לוי")
    assert st == 200 and j["ok"]
    assert w == [("updatebuyer", {"row": "7", "agent": "דנה לוי", "agent_phone": "0522222222"})]
    assert p and p[0][0] == "הועבר אליך קונה" and "רון כהן" in p[0][1] and p[0][2] == ["522222222"]
    assert l and "העברת קונה" in l[0][3]

def test_transfer_rejects_agent_unknown_agent_and_missing_row():
    G = _G([], [], [])
    assert effie_v2.buyer_transfer(G, {"phone": "0522222222", "role": "agent"}, 7, "דנה לוי")[0] == 403
    assert effie_v2.buyer_transfer(G, {"phone": "0521111111", "role": "admin"}, 7, "מישהו")[0] == 400
    assert effie_v2.buyer_transfer(G, {"phone": "0521111111", "role": "admin"}, 99, "דנה לוי")[0] == 404

import json, shutil, subprocess, pytest
SRC = next(v for v in vars(effie_v2).values() if isinstance(v, str) and "function agentPickHtml(" in v) \
    if any(isinstance(v, str) and "function agentPickHtml(" in v for v in vars(effie_v2).values()) else ""

def _fn(name):
    i = SRC.index("function " + name + "(")
    depth, j = 0, SRC.index("{", i)
    for k in range(j, len(SRC)):
        depth += {"{": 1, "}": -1}.get(SRC[k], 0)
        if depth == 0:
            return SRC[i:k + 1]

@pytest.mark.skipif(not shutil.which("node"), reason="node")
def test_agent_pick_html():
    assert SRC, "agentPickHtml missing"
    js = "function esc(s){return String(s||'')}\n" + _fn("agentPickHtml") + \
         "\nconsole.log(JSON.stringify([agentPickHtml(['אייל שמול','דנה לוי'],'אייל שמול'), agentPickHtml(['דנה לוי'],'יוסי')]));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[:400]
    a, b = json.loads(out.stdout)
    assert 'id="edAgent"' in a and '<option selected>אייל שמול</option>' in a and "סוכן מטפל" in a
    assert '<option selected>יוסי</option>' in b      # סוכן נוכחי שלא ברשימה עדיין מוצג (בלי לשנות אותו בטעות)
