# tests/signing/test_last_form_budget.py — אייל 20/10: "התקציב יהיה בדיוק כמו ההחתמה האחרונה של הלקוח,
# ואם חתם באותו טופס על כמה נכסים — ממוצע". בוריס גולדברג: 19/10 חתם על 2,350,000 ואחר כך על 3,280,000 —
# והלולאה (כל 10 דק') ייחסה כל חתימה ישנה ל'היום', כך שהישנה גברה.
import sys, os, ast, re, datetime as dt
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
EP = lambda s: dt.datetime.fromisoformat(s).timestamp() if s else 0
ns = {"re": re, "_canon_key": lambda s: re.sub(r"\s", "", str(s or "")), "_excl_epoch": EP,
      "_sign_row_prices": lambda g, i=None, x=None: [int(g["budget"])] if g.get("budget") else [], "get_signings": lambda: []}
for node in ast.parse(src).body:
    if isinstance(node, ast.FunctionDef) and node.name in ("_client_last_sign_budget", "_sig_price", "_budget_key_newer"):
        exec(compile(ast.Module([node], []), "app.py", "exec"), ns)
f, newer = ns["_client_last_sign_budget"], ns["_budget_key_newer"]
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
def row(t, b, client="בוריס גולדברג", agent="רויטל גל", typ="CLIENT_SALE"):
    return {"deal_type": typ, "client_name": client, "agent": agent, "received_at": t, "budget": str(b)}
S = [row("2026-10-19T11:00:00", 2350000), row("2026-10-19T15:30:00", 3280000),
     row("2026-10-20T09:00:00", 999, client="אחר"), row("2026-10-21T09:00:00", 5000, typ="CLIENT_RENT")]
avg, key = f("בוריס גולדברג", sigs=S)
ck(avg == 3280000 and key == "2026-10-19T15:30:00", (avg, key))          # הטופס האחרון — לא ממוצע של היום
# הלולאה מעבדת את החתימה הישנה: המחיר שלה בזמן שלה, לא 'היום'
avg, key = f("בוריס גולדברג", sigs=S, extra=[2350000], extra_ts=EP("2026-10-19T11:00:00"))
ck(avg == 3280000, (avg, key))
# הטופס הנוכחי (עוד לא ברשימה) — עכשיו, ממוצע הנכסים באותו טופס
avg, key = f("בוריס גולדברג", sigs=S, extra=[1000000, 2000000], extra_ts=EP("2026-10-20T12:00:00"))
ck(avg == 1500000 and key == "2026-10-20T12:00:00", (avg, key))
# סוכן אחר שהחתים את אותו לקוח — לא משפיע על הקונה של הסוכן הזה
S2 = S + [row("2026-10-20T10:00:00", 7000000, agent="משה")]
ck(f("בוריס גולדברג", sigs=S2, agent="רויטל גל")[0] == 3280000, "per agent")
ck(f("בוריס גולדברג", sigs=S2)[0] == 7000000, "no agent → all")
ck(f("מישהו", sigs=S) == (0, ""), "none")
# מתי מעדכנים את הקונה: טופס חדש יותר; ערך ישן בלי שעה (מלפני 20/10) — מתעדכן פעם אחת
ck(newer("2026-10-19T15:30:00", "2026-10-19T11:00:00") and not newer("2026-10-19T11:00:00", "2026-10-19T15:30:00"), "time order")
ck(not newer("2026-10-19T15:30:00", "2026-10-19T15:30:00"), "same form → no rewrite (manual edit kept)")
ck(newer("2026-10-19T15:30:00", "2026-10-20") and newer("2026-10-19T15:30:00", ""), "legacy date-only → update once")
ck(not newer("", "2026-10-20"), "no key → no update")
print("OK", n, "checks")
