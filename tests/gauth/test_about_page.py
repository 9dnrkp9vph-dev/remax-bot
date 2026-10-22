# tests/gauth/test_about_page.py — אייל 22/10: אימות 'אפי · Effie' מול גוגל (OAuth consent screen)
# דורש דף בית אמיתי לאפליקציה (דו-לשוני, עם קישור למדיניות הפרטיות והסבר על השימוש ביומן)
# וקובץ אימות של Search Console בשורש הדומיין.
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["GOOGLE_SITE_VERIFICATION_FILE"] = "google0123456789abcdef.html"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
c = A.app.test_client()

r = c.get("/about")
t = r.get_data(as_text=True)
ck(r.status_code == 200, r.status_code)
ck("אפי" in t and "Effie" in t, "name in both languages")
ck('href="/privacy"' in t, "privacy link")
ck("calendar.events" in t or "Google Calendar" in t, "explains calendar use")
ck("Limited Use" in t, "Google API Services User Data Policy statement")
ck('lang="en"' in t, "english section")

# קובץ האימות של Search Console
r = c.get("/google0123456789abcdef.html")
ck(r.status_code == 200 and r.get_data(as_text=True).strip() == "google-site-verification: google0123456789abcdef.html", r.status_code)
ck(c.get("/google_other.html").status_code == 404, "other file 404")

# מדיניות הפרטיות — סעיף באנגלית על נתוני Google
p = c.get("/privacy").get_data(as_text=True)
ck("Limited Use" in p and "Google user data" in p, "privacy english google section")

# הדף הקיים בשורש לא השתנה (UptimeRobot / keepalive)
ck("Running" in c.get("/").get_data(as_text=True), "root unchanged")
print("OK", n, "checks")
