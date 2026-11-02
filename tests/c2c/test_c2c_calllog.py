# -*- coding: utf-8 -*-
"""יומן השיחות לשיחות click2call (02/11): השורות של מסקיו (המחייג = הקו הווירטואלי) מתאחדות לשורה
אחת עם הלקוח האמיתי. python3 tests/c2c/test_c2c_calllog.py"""
import ast, os, re, sys, types
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)
def _src(n):
    for x in TREE.body:
        if isinstance(x, ast.FunctionDef) and x.name == n:
            return ast.get_source_segment(SRC, x)
    raise AssertionError(n)
fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)
from datetime import datetime, timezone
def iso(h, m, s=0): return datetime(2026, 11, 2, h, m, s, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def ep(h, m, s=0): return datetime(2026, 11, 2, h, m, s, tzinfo=timezone.utc).timestamp()
G = {"re": re, "time": types.SimpleNamespace(time=lambda: ep(21, 0)),
     "_last9": lambda p: re.sub(r"\D", "", str(p or ""))[-9:],
     "_epoch_from_iso": lambda s: datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() if s else 0,
     "_c2c_clicks": lambda: []}
for n in ("_c2c_parse_detail", "_apply_c2c"):
    exec(_src(n), G)
parse, apply = G["_c2c_parse_detail"], G["_apply_c2c"]

print("1. parse detail")
check(parse("0525640615 · 052-9125944 ✓") == ("525640615", "529125944", True), "פורמט חדש")
check(parse("0525640615 ✓") == ("525640615", "", True), "פורמט ישן בלי קו")
check(parse("0525640615 · 0529125944 ✗ Maskyoo: x")[2] is False, "✗ = לא חויג")

CL = [{"ts": ep(20, 28, 20), "to9": "525640615", "vp9": "529125944", "agent9": "505709865"}]
print("2. שיחה שנענתה (שתי רגליים ANSWER)")
rows = [{"caller_phone": "529125944", "agent_phone": "505709865", "status": "ANSWER", "received_at": iso(20, 29, 20), "transcript_summary": "שיחה קצרה"},
        {"caller_phone": "529125944", "agent_phone": "", "status": "ANSWER", "received_at": iso(20, 29, 22), "transcript_summary": "הלקוח מחפש 4 חדרים בביאליק, תקציב 2 מיליון"},
        {"caller_phone": "0501111111", "status": "ANSWER", "received_at": iso(20, 30), "transcript_summary": "שיחה רגילה"}]
out = apply(rows, CL)
c2c = [r for r in out if r.get("c2c")]
check(len(out) == 2 and len(c2c) == 1, "שתי הרגליים → שורה אחת; שיחה רגילה נשארת")
m = c2c[0]
check(m["caller_phone"] == "0525640615", "הלקוח = מי שחויג")
check(m["agent_phone"] == "0505709865", "טלפון הסוכן = הנייד שלו")
check(m["status"] == "CALL2CALL", "סטטוס שיחה יוצאת")
check("4 חדרים" in m["transcript_summary"], "הסיכום הארוך נבחר")
check(out[0] is m, "השורה המאוחדת במקום של הרגל הראשונה")

print("3. הלקוח לא ענה")
rows = [{"caller_phone": "529125944", "agent_phone": "505709865", "status": "ANSWER", "received_at": iso(20, 18, 10), "transcript_summary": ""},
        {"caller_phone": "529125944", "status": "CALLER CANCEL", "received_at": iso(20, 18, 10), "transcript_summary": "https://maskyoo.com/zipper_993/api/public.php?service=click2call_link&t=x"}]
out = apply(rows, [{"ts": ep(20, 17, 3), "to9": "525640615", "vp9": "529125944", "agent9": "505709865"}])
check(len(out) == 1 and out[0]["status"] == "C2C_MISS", "C2C_MISS ('יוצאת · לא ענה')")
check(out[0]["transcript_summary"] == "", "בלי קישור click2call_link מת בסיכום")

print("4. בלי חיוג תואם / מחוץ לחלון")
r0 = {"caller_phone": "529125944", "status": "ANSWER", "received_at": iso(23, 0)}
check(apply([r0], CL) == [r0], "שורה מהקו הווירטואלי שעה אחרי → בלי שינוי")
check(apply([r0], []) == [r0], "בלי חיוגים → בלי שינוי")

print("5. שני חיוגים באותו ערב — כל שורה לחיוג האחרון שלפניה")
CL2 = [{"ts": ep(20, 0), "to9": "525640615", "vp9": "529125944", "agent9": "505709865"},
       {"ts": ep(20, 10), "to9": "559922649", "vp9": "529125944", "agent9": "505709865"}]
out = apply([{"caller_phone": "529125944", "status": "ANSWER", "received_at": iso(20, 1)},
             {"caller_phone": "529125944", "status": "CALLER CANCEL", "received_at": iso(20, 11)}], CL2)
check([r["caller_phone"] for r in out] == ["0525640615", "0559922649"], "כל שורה לחיוג שלה")

print("6. חיווט")
check("rows = _apply_c2c(rows)" in SRC, "web_fetch_raw מפעיל את האיחוד")
check('to + " · " + vphone' in SRC, "activity_log שומר גם את הקו")
V2 = open(os.path.join(ROOT, "effie_v2.py"), encoding="utf-8").read()
check("'C2C_MISS' ? 'יוצאת · לא ענה'" in V2 and '"C2C_MISS": "יוצאת · לא ענה"' in V2, "תווית במסך השיחות וב-CRM")
print("\nRESULT:", "ALL GREEN" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
