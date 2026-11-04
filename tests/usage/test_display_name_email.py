"""[04/11 'eyal-shmul' בכרטיס החיפושים] שם כניסה באנגלית בלי טלפון שמזוהה → השם האמיתי לפי המייל בטבלת הצוות.
CLAUDE_API_KEY=dummy WARMUP_ON_BOOT=0 CONFIG_SOURCE=sheets python3 tests/usage/test_display_name_email.py"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import app

app.web_phone_name_map = lambda: {"529125944": "eyal-shmul"}
app.web_contacts_phone_name = lambda: {}
app._config_agent_phones = lambda: {}
app._name_for_phone = lambda p: ""
app._contacts_rows = lambda: [["אייל שמול", "0505709865", "", "", "eyalshmul@gmail.com"],
                              ["אודי שמול", "0546000808", "", "", "ushmul@gmail.com"],
                              ["הודיה צרויה", "0547971159", "", "", "dingabay01@gmail.com‎"]]
fails = []
def check(c, m):
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fails.append(m)

D = app._display_name_for
check(D("eyal-shmul", "529125944") == "אייל שמול", "טלפון שלא בצוות — לפי המייל")
check(D("eyal-shmul", "") == "אייל שמול", "בלי טלפון — לפי המייל")
check(D("Eyal.Shmul", "") == "אייל שמול", "נקודה/אותיות גדולות")
check(D("dingabay01", "") == "הודיה צרויה", "מייל עם תו נסתר")
check(D("john-doe", "") == "john-doe", "אין התאמה — נשאר כמו שהוא")
check(D("shmul", "") == "shmul", "רק חלק מהשם — לא מנחשים")
check(D("נדב רייזר", "") == "נדב רייזר", "שם בעברית לא נוגעים")
# [04/11 באוויר] פעימות של מנהל נשמרות בשם הגנרי 'מנהל' — לפי הטלפון חוזר שם הכניסה מ-Google
app._name_for_phone = lambda p: {"505709865": "eyal-shmul"}.get(p, "")
check(D("מנהל", "505709865") == "אייל שמול", "שם גנרי → שם כניסה באנגלית → לפי המייל")
app._name_for_phone = lambda p: {"505709865": "נוי רבן"}.get(p, "")
check(D("מנהל", "505709865") == "נוי רבן", "שם גנרי → שם בעברית כמו קודם")
print("\nRESULT:", "ALL GREEN" if not fails else "%d FAILED: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
