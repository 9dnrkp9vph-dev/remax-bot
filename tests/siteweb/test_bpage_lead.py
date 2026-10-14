"""'סוכן AI אישי' (14/10): בחירת עד 5 נכסי משרד לליד, והסוכן בדף = הסוכן הנוכחי של הקונה."""
from effie_v2 import bpage_lead_pick, bpage_agent_for

def test_pick_top_five_office_only_and_threshold():
    rows = {"k%d" % i: {"מחיר": str(2_000_000 + i * 10_000), "_ep": 1} for i in range(8)}
    rows["gone"] = {"מחיר": "2000000", "ירד מפרסום": "01/10/2026", "_ep": 1}
    rows["far"] = {"מחיר": "4000000", "_ep": 1}
    rows["noep"] = {"מחיר": "2000000", "_ep": 0}                       # נכס בלי תאריך — עדיין מועמד
    score = lambda r, q: 90 - int(r["מחיר"]) // 1_000_000
    out = bpage_lead_pick(rows, {}, 2_000_000, score)
    assert len(out) == 5 and "gone" not in out and "far" not in out
    assert bpage_lead_pick(rows, {}, 0, lambda r, q: 50) == []
    assert "noep" in bpage_lead_pick({"noep": rows["noep"]}, {}, 0, lambda r, q: 70)

def test_agent_follows_buyer():
    page = {"agent_name": "אייל שמול", "agent_phone": "0505709865"}
    assert bpage_agent_for(page, {"agent": "דנה כהן", "agent_phone": ""}, {"דנה כהן": "0521112222"}) == ("דנה כהן", "0521112222")
    assert bpage_agent_for(page, {}, {}) == ("אייל שמול", "0505709865")
    assert bpage_agent_for(page, None, {}) == ("אייל שמול", "0505709865")
    assert bpage_agent_for(page, {"agent": "דנה כהן", "agent_phone": "0523334444"}, {}) == ("דנה כהן", "0523334444")
    assert bpage_agent_for(page, {"agent": "מנהל"}, {}) == ("אייל שמול", "0505709865")
