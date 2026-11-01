# tests/wa/test_d360_err.py — [01/11 אייל] 'כן, תוסיף': ביומן ליד 'וואטסאפ רשמי — נכשל' גם קוד השגיאה של 360dialog,
# כדי לראות מיד למה הודעה נדחתה (התקלה של 01/11 11:48–16:05 נראתה ביומן רק כ'נכשל').
import ast, os, json
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SRC = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
fn = [n for n in ast.parse(SRC).body if isinstance(n, ast.FunctionDef) and n.name == "_d360_err"]
assert fn, "_d360_err חסרה"
g = {}
exec(ast.get_source_segment(SRC, fn[0]), g)
E = g["_d360_err"]
n = 0
def ck(c, m):
    global n
    assert c, m
    n += 1

class R:
    def __init__(self, status, body):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body)
    def json(self):
        return json.loads(self.text)

# פורמט Meta (Cloud API דרך 360)
e = E(R(400, {"error": {"message": "(#131047) Re-engagement message", "code": 131047, "error_data": {"details": "More than 24 hours have passed"}}}))
ck("400" in e and "131047" in e and "24 hours" in e, e)
# פורמט 360 הישן
e = E(R(401, {"meta": {"http_code": 401, "developer_message": "Invalid api key"}}))
ck("401" in e and "Invalid api key" in e, e)
# errors כרשימה
e = E(R(429, {"errors": [{"code": 130429, "title": "Rate limit hit"}]}))
ck("429" in e and "130429" in e and "Rate limit" in e, e)
# גוף שאינו JSON / ריק
ck("502" in E(R(502, "<html>Bad Gateway</html>")), "html")
ck(E(R(500, "")).startswith("HTTP 500"), "ריק")
ck(len(E(R(400, {"error": {"message": "x" * 900}}))) <= 200, "קצר")
# בלי אובייקט תשובה (חריגה) — לא נופל
ck(E(None) == "", "None")

# ההדבקה: הפירוט ביומן בכשל כולל את השגיאה
body = SRC.split("def _d360_post_message")[1][:1500]
ck("_d360_err(r)" in body and '" · שגיאה: " + _e' in body, "השגיאה נכנסת ליומן, בסוף הפירוט")
print("OK", n, "checks")
