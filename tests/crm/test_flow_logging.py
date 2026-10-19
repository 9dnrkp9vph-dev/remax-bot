# tests/crm/test_flow_logging.py — רישום ביומן של מה שיוצא (פוש, SMS בלי תוכן, מייל דוח) — ל'נכנס ויוצא'
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
LOG = []
A._log_activity = lambda *a: LOG.append(a)
A._send_push_raw = lambda title, body, external_id=None: True
ck(A.send_push("נכס נולד חדש", "גוף", ["111", "222"]) is True, "push returns")
ck(LOG[-1][3] == "פוש — נשלח" and "נכס נולד חדש" in LOG[-1][4] and "2" in LOG[-1][4], LOG[-1])
A._web_send_sms_raw = lambda last9, body: False
ck(A.web_send_sms("501234567", "קוד הכניסה שלך: 4821") is False, "sms returns")
ck(LOG[-1][3] == "SMS — נכשל" and "4567" in LOG[-1][4] and "4821" not in str(LOG[-1]), ("no SMS content in log", LOG[-1]))
A._report_send_email_raw = lambda subject, html, text, to=None, attachments=None: (True, "ok")
ck(A._report_send_email("סיכום שבועי · 12–18/10", "<p>", "t")[0], "mail returns")
ck(LOG[-1][3] == "סיכום שבועי — נשלח", LOG[-1])
A._report_send_email("דוח יומי רימקס פמילי · 18/10/2026", "<p>", "t")
ck(LOG[-1][3] == "דוח יומי — נשלח", LOG[-1])
# פירוט (אייל: "תוסיף פירוט בלוג"): למי (שם לפי הטלפון), מטרה, ותוכן קצר בלי קישורים — אף פעם לא קוד כניסה
A.web_phone_name_map = lambda: {"501234567": "דנה לוי"}
A.web_contacts_phone_name = lambda: {}
A._buyer_phone_names = lambda: {"529998888": "משה כהן (קונה)"}
A._web_send_sms_raw = lambda last9, body: True
A.web_send_sms("501234567", "קוד הכניסה שלך: 4821")
ck("דנה לוי" in LOG[-1][4] and "קוד כניסה" in LOG[-1][4] and "4821" not in str(LOG[-1]), LOG[-1])
A.web_send_sms("529998888", "שלום, לחתימה: https://remax-bot.onrender.com/s/abcTOKEN")
ck("משה כהן" in LOG[-1][4] and "קישור חתימה" in LOG[-1][4] and "abcTOKEN" not in str(LOG[-1]), LOG[-1])
A.send_push("נכס נולד", "3 נכסים חדשים בקרית ביאליק", ["501234567", "529998888", "500000001", "500000002"])
ck("דנה לוי" in LOG[-1][4] and "3 נכסים חדשים" in LOG[-1][4] and "ועוד" in LOG[-1][4], LOG[-1])
class R:
    ok = True; status_code = 200; text = ""
    def json(s): return {"messages": [{"id": "x"}]}
A.requests.post = lambda *a, **k: R()
A._switch_off = lambda n: False
A._d360_post_message({"to": "972529998888", "type": "text", "text": {"body": "היי משה, הנה הדף שלך https://x.co/b/SECRET תודה"}})
ck("משה כהן" in LOG[-1][4] and "הנה הדף שלך" in LOG[-1][4] and "SECRET" not in str(LOG[-1]), LOG[-1])
A._d360_post_message({"to": "972501234567", "type": "template", "template": {"name": "family_update", "components": [{"type": "body", "parameters": [{"type": "text", "text": "שיחה חדשה מלקוח"}]}]}})
ck("דנה לוי" in LOG[-1][4] and "family_update" in LOG[-1][4] and "שיחה חדשה מלקוח" in LOG[-1][4], LOG[-1])
print("flow_logging OK", n)
