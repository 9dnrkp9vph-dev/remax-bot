"""
שרת בוט וואטסאפ — מצגות נדל"ן אוטומטיות + חיפוש קונים
RE/MAX Family | Railway.app deployment
זרימה:
1. סוכן שולח "מצגת" + טקסט + תמונות → מצגת PDF
2. סוכן שולח "מחפש דירה ..." → חיפוש נכסים מהמאגר
3. סוכן שולח "מחפש קונה ..." → חיפוש קונים בשיחות שלו
"""
import os, re, json, time, uuid, base64, tempfile, subprocess, logging, threading
from pathlib import Path
from io import BytesIO
import requests
from flask import Flask, request, jsonify, redirect
# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
app = Flask(__name__)
# ── Config from env vars ───────────────────────────────────────────────────────
MAYTAPI_TOKEN    = os.environ["MAYTAPI_TOKEN"]
MAYTAPI_PHONE_ID = os.environ["MAYTAPI_PHONE_ID"]
MAYTAPI_PRODUCT  = os.environ["MAYTAPI_PRODUCT_ID"]
CLAUDE_API_KEY   = os.environ["CLAUDE_API_KEY"]
TRIGGER_WORD     = os.environ.get("TRIGGER_WORD", "מצגת")
GOOGLE_SHEETS_API_KEY  = os.environ.get("GOOGLE_SHEETS_API_KEY", "")
PROPERTIES_SHEET_ID    = os.environ.get("PROPERTIES_SHEET_ID", "1PnQm-ifyLrh6sBbNNQbNlAHmJWeBnbzXJJERmTuaAVM")
PROPERTIES_SHEET_NAME  = "נכסים"
CONTACTS_SHEET_NAME    = "אנשי קשר"
SEARCH_TRIGGERS        = ["מחפש דירה", "מחפשת דירה", "מחפש נכס", "מחפשת נכס"]
# Apps Script — לחיפוש קונים בשיחות (דוחות נדלן וואן)
APPS_SCRIPT_URL   = os.environ.get("APPS_SCRIPT_URL", "")
APPS_SCRIPT_TOKEN = os.environ.get("APPS_SCRIPT_TOKEN", "")
BUYER_SEARCH_TRIGGERS = ["מחפש קונה", "מחפשת קונה"]
_buyer_calls_cache = {"data": None, "ts": 0}
MAYTAPI_BASE = f"https://api.maytapi.com/api/{MAYTAPI_PRODUCT}/{MAYTAPI_PHONE_ID}"
# מזהי קבוצות וואטסאפ למנהלים (chat id של הקבוצה, למשל 120363xxxxxxxxxx@g.us) — נשלח אליהן בנוסף לסוכן האישי
WA_GROUP_CALLS      = os.environ.get("WA_GROUP_CALLS", "120363409255066492@g.us").strip()       # קבוצת "שיחות"
WA_GROUP_SIGNATURES = os.environ.get("WA_GROUP_SIGNATURES", "120363430208269536@g.us").strip()  # קבוצת "חתימות"
# ── Push notifications (OneSignal) — נחוץ לאפליקציה הנייד, לא להסיר ──────────────
ONESIGNAL_APP_ID   = "f13c245a-17c2-415d-a81d-41a3df58e1a9"
ONESIGNAL_REST_KEY = os.environ.get("ONESIGNAL_REST_KEY", "")   # נשמר ב-Render בלבד, לא בקוד
# ── Google Sign-In + Calendar — נחוץ לכניסה עם גוגל וסנכרון יומן (לא להסיר) ───────
# כל המפתחות נשמרים ב-Render בלבד, לא בקוד. ריק = הפיצ'ר רדום והכניסה הרגילה לא מושפעת.
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI  = os.environ.get("GOOGLE_REDIRECT_URI", "https://remax-bot.onrender.com/auth/google/callback").strip()
_PUSH_LAST = {}   # אבחון אחרון של שליחת Push — לצפייה ב-/api/push/test
OWNER_PUSH_ID = "505709865"   # טלפון אייל (9 ספרות) — אליאס הפוש של הבעלים (במקום "owner" שירד)
_QUIET_PATH = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(__file__), "quiet_mode.json")

def _quiet_mode():
    """מצב שקט: QUIET_MODE ב-env גובר תמיד; אחרת — המתג מהקונסולה (נשמר לדיסק)."""
    if (os.environ.get("QUIET_MODE") or "").strip():
        return True
    try:
        with open(_QUIET_PATH, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("on"))
    except Exception:
        return False

def _quiet_set(on):
    try:
        with open(_QUIET_PATH, "w", encoding="utf-8") as f:
            json.dump({"on": bool(on)}, f)
        return True
    except Exception:
        return False

_QUIET_START = int(os.environ.get("QUIET_HOURS_START", "22") or 22)   # 22:00
_QUIET_END   = int(os.environ.get("QUIET_HOURS_END", "8") or 8)       # 08:00
def _quiet_hours():
    """שעות שקט (ברירת מחדל 22:00–08:00, שעון ישראל): חוסם פוש ווואטסאפ אוטומטיים
    מהמערכת. לא חל על SMS כניסה (קוד התחברות) ולא על פעולות שהמשתמש יזם."""
    try:
        from zoneinfo import ZoneInfo
        import datetime as _dtq
        h = _dtq.datetime.now(ZoneInfo("Asia/Jerusalem")).hour
    except Exception:
        import datetime as _dtq
        h = (_dtq.datetime.utcnow().hour + 3) % 24   # קירוב לשעון ישראל
    if _QUIET_START == _QUIET_END:
        return False
    if _QUIET_START < _QUIET_END:               # חלון באותו יום
        return _QUIET_START <= h < _QUIET_END
    return h >= _QUIET_START or h < _QUIET_END   # חלון שחוצה חצות (22→8)

def send_push(title, body, external_id=OWNER_PUSH_ID):
    """שולח התראת Push דרך OneSignal לפי external_id (alias). מחזיר True/False.
    שומר אבחון מלא ב-_PUSH_LAST (סטטוס + תגובת OneSignal) לצורך /api/push/test."""
    global _PUSH_LAST
    if _quiet_mode():   # מתג השתקה כללי (שבת/חג/תחזוקה) — env או כפתור בקונסולה
        _PUSH_LAST = {"ok": False, "reason": "QUIET_MODE"}
        log.info("QUIET_MODE — push suppressed")
        return False
    if _quiet_hours():   # שעות לילה (22:00–08:00) — לא מטרידים בפוש
        _PUSH_LAST = {"ok": False, "reason": "QUIET_HOURS"}
        return False
    if not ONESIGNAL_REST_KEY:
        _PUSH_LAST = {"ok": False, "reason": "no_rest_key (משתנה הסביבה ONESIGNAL_REST_KEY לא מוגדר ב-Render)"}
        return False
    ids = external_id if isinstance(external_id, list) else [external_id]
    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "target_channel": "push",
        "include_aliases": {"external_id": ids},
        "headings": {"en": title},
        "contents": {"en": body},
    }
    def _post(scheme):
        return requests.post(
            "https://api.onesignal.com/notifications",
            headers={"Authorization": scheme + " " + ONESIGNAL_REST_KEY,
                     "Content-Type": "application/json"},
            json=payload, timeout=10)
    try:
        scheme = "Key"
        r = _post(scheme)
        # מפתח legacy של OneSignal דורש 'Basic' במקום 'Key' — ננסה אוטומטית אם נדחה
        if r.status_code in (401, 403):
            r2 = _post("Basic")
            if r2.status_code not in (401, 403):
                r, scheme = r2, "Basic"
        _PUSH_LAST = {"ok": r.ok, "status": r.status_code, "scheme": scheme,
                      "ids": ids, "resp": (r.text or "")[:600]}
        if not r.ok:
            log.error(f"push http {r.status_code} ({scheme}): {(r.text or '')[:300]}")
        return r.ok
    except Exception as e:
        _PUSH_LAST = {"ok": False, "ids": ids, "reason": str(e)[:300]}
        log.error(f"push error: {e}")
        return False
# ── Temp dir for processing ────────────────────────────────────────────────────
WORK_DIR = Path(tempfile.gettempdir()) / "remax_bot"
WORK_DIR.mkdir(exist_ok=True)
# ── Active sessions: phone → {text, images, timer} ────────────────────────────
sessions = {}
SESSION_TIMEOUT = 45
# ══════════════════════════════════════════════════════════════════════════════
# MAYTAPI HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def maytapi_headers():
    return {"x-maytapi-key": MAYTAPI_TOKEN, "Content-Type": "application/json"}
_WA_LAST = {}   # אבחון אחרון של שליחת WhatsApp — לצפייה ב-/api/wa/test
_wa_throttle = {"ts": 0.0}
_wa_throttle_lock = threading.Lock()
WA_MIN_GAP = float(os.environ.get("WA_MIN_GAP", "4") or 4)   # שניות מינימום בין הודעות

def _wa_auto_on():
    """התראות וואטסאפ אוטומטיות מהשרת (שיחה חדשה/חתימה). מושהות כברירת מחדל —
    בקשת אייל (2026-07-06), שוקל מעבר ל-API הרשמי. הפעלה מחדש: המתג "וואטסאפ
    אוטומטי" בניהול /v2/admin (config v2_policies.wa_auto). תשובות הבוט לפקודות
    ושליחת חוזים ע"י סוכן אינן מושפעות — הן "מבחירה"."""
    if _quiet_hours():   # שעות לילה (22:00–08:00) — לא שולחים וואטסאפ אוטומטי
        return False
    try:
        return bool((_load_config().get("v2_policies") or {}).get("wa_auto"))
    except Exception:
        return False

def send_text(to: str, text: str):
    """שולח הודעת WhatsApp דרך Maytapi. מחזיר True/False לפי הצלחה אמיתית (success מ-Maytapi)."""
    global _WA_LAST
    if _quiet_mode():   # מתג השתקה כללי (שבת/חג/תחזוקה) — env או כפתור בקונסולה
        _WA_LAST = {"ok": False, "reason": "QUIET_MODE"}
        log.info("QUIET_MODE — WhatsApp suppressed")
        return False
    # מגביל-קצב: מרווח מינימלי בין הודעות — מונע פרצים שגורמים ל-WhatsApp לחסום את המספר
    with _wa_throttle_lock:
        _gap = time.time() - _wa_throttle["ts"]
        if _gap < WA_MIN_GAP:
            time.sleep(WA_MIN_GAP - _gap)
        _wa_throttle["ts"] = time.time()
    try:
        r = requests.post(f"{MAYTAPI_BASE}/sendMessage",
            headers=maytapi_headers(),
            json={"to_number": to, "type": "text", "message": text}, timeout=20)
        ok = False
        try:
            j = r.json()
            ok = bool(r.ok and isinstance(j, dict) and j.get("success"))
        except Exception:
            pass
        _WA_LAST = {"ok": ok, "status": r.status_code, "to": to, "resp": (r.text or "")[:400]}
        log.info(f"send_text → {to} · {r.status_code} ok={ok} · {(r.text or '')[:150]}")
        return ok
    except Exception as e:
        _WA_LAST = {"ok": False, "to": to, "reason": str(e)[:200]}
        log.error(f"send_text error: {e}")
        return False
def download_profile_pic(phone: str, dest: Path) -> bool:
    """הורד תמונת פרופיל ושמור לקובץ — מנסה כמה endpoints"""
    try:
        number = phone.replace("+","").replace("-","").strip()
        number_at = f"{number}@c.us"
        endpoints = [
            {"method": "GET",  "url": f"{MAYTAPI_BASE}/getProfilePic", "params": {"number": number_at}},
            {"method": "GET",  "url": f"{MAYTAPI_BASE}/getProfilePic", "params": {"number": number}},
            {"method": "POST", "url": f"{MAYTAPI_BASE}/getProfilePic", "json": {"number": number_at}},
            {"method": "GET",  "url": f"{MAYTAPI_BASE}/profile/pic",   "params": {"number": number_at}},
        ]
        for ep in endpoints:
            try:
                if ep["method"] == "GET":
                    r = requests.get(ep["url"], headers=maytapi_headers(),
                        params=ep.get("params"), timeout=10)
                else:
                    r = requests.post(ep["url"], headers=maytapi_headers(),
                        json=ep.get("json"), timeout=10)
                log.info(f"Profile pic endpoint {ep['url']}: {r.status_code} {r.text[:100]}")
                if r.status_code == 200:
                    data = r.json()
                    pic_url = (data.get("data") or data.get("url") or
                               data.get("imgUrl") or data.get("profilePicUrl") or
                               data.get("image"))
                    if pic_url and pic_url.startswith("http"):
                        img_r = requests.get(pic_url, timeout=15)
                        if img_r.status_code == 200:
                            dest.write_bytes(img_r.content)
                            log.info("Profile pic downloaded OK")
                            return True
            except Exception as ex:
                log.warning(f"Endpoint {ep['url']} failed: {ex}")
                continue
    except Exception as e:
        log.error(f"Download profile pic error: {e}")
    return False
def send_document(to: str, file_path: str, filename: str, caption: str = ""):
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    r = requests.post(f"{MAYTAPI_BASE}/sendMessage",
        headers=maytapi_headers(),
        json={
            "to_number": to,
            "type": "media",
            "message": f"data:application/pdf;base64,{b64}",
            "text": caption,
            "filename": filename,
        })
    log.info(f"send_document → {r.status_code} {r.text[:120]}")
    return r.status_code == 200
def download_media(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, headers={"x-maytapi-key": MAYTAPI_TOKEN}, timeout=30)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return True
        log.warning(f"Media download failed: {r.status_code}")
        return False
    except Exception as e:
        log.error(f"Download error: {e}")
        return False
# ══════════════════════════════════════════════════════════════════════════════
# CLAUDE API — פירסור טקסט
# ══════════════════════════════════════════════════════════════════════════════
def parse_listing_text(raw_text: str) -> dict:
    prompt = f"""אתה מנתח מודעות נדל"ן בעברית. קרא את הטקסט הבא והחזר JSON בלבד (ללא backticks).
שדות נדרשים:
- address: כתובת מלאה
- city: עיר
- neighborhood: שכונה (אם יש)
- price: מחיר (מספר בלבד, ללא ₪)
- price_display: מחיר לתצוגה (עם ₪)
- rooms: מספר חדרים
- size_sqm: שטח מ"ר (מספר)
- balcony_sqm: מרפסת מ"ר (או null)
- floor: קומה (מספר)
- total_floors: סה"כ קומות
- elevator: true/false
- parking: תיאור חניה או null
- storage: true/false
- shelter: true/false (ממ"ד)
- condition: תיאור מצב הנכס
- agent_name: שם הסוכן
- agent_phone: טלפון (מספרים בלבד, ללא מקפים)
- agency: שם הסוכנות
- property_type: סוג נכס (דירה/פנטהאוז/קוטג'/בית)
- exclusive: true אם בלעדיות
- description: תיאור שיווקי מלא מהמודעה
- highlights: רשימת יתרונות (array of strings)
- image_labels: רשימה של 4 כיתובים לתמונות לפי מה שמוזכר בטקסט (למשל ["סלון","מטבח","חדר הורים","אמבטיה"]) — השתמש תמיד ב-4 פריטים
טקסט:
{raw_text}"""
    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={
            "anthropic-version": "2023-06-01",
            "x-api-key": CLAUDE_API_KEY,
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}]
        })
    if r.status_code != 200:
        log.error(f"Claude API error: {r.text}")
        return {}
    text = r.json()["content"][0]["text"].strip()
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = text.strip("`").strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group()
    try:
        return json.loads(text)
    except Exception as e:
        log.error(f"JSON parse error: {e}\nText: {text[:200]}")
        return {}
# ══════════════════════════════════════════════════════════════════════════════
# PDF GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
def install_deps():
    pkgs = ["reportlab", "arabic-reshaper", "python-bidi", "Pillow"]
    subprocess.run(
        ["pip", "install", "--break-system-packages", "-q"] + pkgs,
        capture_output=True)
def has_remax_logo(img_path: Path) -> bool:
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(img_path).convert("RGB")
        arr = np.array(img)
        h, w = arr.shape[:2]
        corners = [arr[:h//4, :w//4], arr[:h//4, 3*w//4:],
                   arr[3*h//4:, :w//4], arr[3*h//4:, 3*w//4:]]
        for region in corners:
            red = (region[:,:,0] > 150) & (region[:,:,1] < 80) & (region[:,:,2] < 80)
            if red.sum() > 50:
                return True
        return False
    except:
        return False
def remove_logo_from_image(img_path: Path, out_path: Path):
    from PIL import Image, ImageFilter, ImageDraw
    import numpy as np
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]
    crop_top = int(h * 0.25)
    cropped = img.crop((0, crop_top, w, h))
    cropped.save(out_path, "JPEG", quality=93)
def add_remax_logo_to_image(img_path: Path, out_path: Path, logo_path: Path):
    from PIL import Image
    img = Image.open(img_path).convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")
    iw, ih = img.size
    logo_w = int(iw * 0.22)
    logo_h = int(logo_w * logo.size[1] / logo.size[0])
    logo_r = logo.resize((logo_w, logo_h), Image.LANCZOS)
    mx, my = int(iw * 0.015), int(ih * 0.02)
    img.paste(logo_r, (iw - logo_w - mx, ih - logo_h - my), logo_r)
    img.convert("RGB").save(out_path, "JPEG", quality=93)
def get_area_info(city: str, neighborhood: str) -> list:
    area = neighborhood or city
    if not area:
        return []
    prompt = f"""חפש מידע אמיתי ועדכני על שכונת "{area}" ב{city} לרוכשי דירות.
חפש: תחבורה ציבורית, מוסדות חינוך, מרכזים מסחריים, שטחי טבע, מגמות נדל"ן.
לאחר החיפוש, החזר JSON בלבד — מערך של 5 אובייקטים עם שדות:
- icon (אימוג'י מתאים)
- title (כותרת קצרה בעברית)
- desc (תיאור 1-2 משפטים בעברית עם עובדות אמיתיות)"""
    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={"anthropic-version":"2023-06-01","x-api-key":CLAUDE_API_KEY,"content-type":"application/json"},
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 2000,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=50)
    if r.status_code != 200:
        log.error(f"Area info error: {r.text}")
        return []
    content = r.json().get("content", [])
    text = ""
    for block in reversed(content):
        if block.get("type") == "text":
            text = block["text"].strip()
            break
    text = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try: return json.loads(match.group())
        except: pass
    return []
def get_transactions(city: str, neighborhood: str, rooms: str, address: str) -> list:
    area = neighborhood or city
    street = address.split(",")[0].strip() if address else area
    prompt = f"""חפש עסקאות נדל"ן אמיתיות ועדכניות ברחוב "{street}", {city} לדירות {rooms} חדרים, 2024-2025.
חפש ב: nadlan.gov.il, madlan.co.il, mynet, ynet.
סדר עדיפויות:
1. עסקאות מרחוב {street} עצמו — {rooms} חדרים
2. אם אין — שכונת {area} — {rooms} חדרים
3. מחירים בטווח של עד 30% ממחיר הנכס
4. מהעדכניות ביותר (2025 לפני 2024)
החזר JSON בלבד — מערך 5-6 עסקאות, שדות:
- price: מחיר ב-₪ (למשל "1,800,000 ₪")
- floor: קומה (חובה! אם לא ידוע השתמש ב"?/?" — לעולם לא "לא צוין")
- area: שטח במ"ר (חובה! אם לא ידוע השתמש בשטח ממוצע לאזור — לעולם לא "לא צוין")
- ppm: מחיר/מ"ר מחושב (חובה! חשב price/area — לעולם לא "לא צוין")
- date: תאריך (למשל "מאי 25")
- details: "רח' X — {rooms} חד', [תיאור]"
מיין מהעדכני לישן."""
    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={"anthropic-version":"2023-06-01","x-api-key":CLAUDE_API_KEY,"content-type":"application/json"},
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 2000,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=50)
    if r.status_code != 200:
        log.error(f"Transactions error: {r.text}")
        return []
    content = r.json().get("content", [])
    text = ""
    for block in reversed(content):
        if block.get("type") == "text":
            text = block["text"].strip()
            break
    text = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try: return json.loads(match.group())
        except: pass
    return []
def generate_pdf(data: dict, image_paths: list, session_dir: Path) -> Path:
    """צור PDF פרמיום 6 עמודים בסגנון RE/MAX"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as RLImage, PageBreak, HRFlowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from bidi.algorithm import get_display
    import arabic_reshaper
    from PIL import Image as PILImage
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
        "/app/fonts/DejaVuSans.ttf",
    ]
    font_reg = next((p for p in font_paths if os.path.exists(p)), None)
    if not font_reg:
        font_dir = Path("/tmp/fonts"); font_dir.mkdir(exist_ok=True)
        font_reg = str(font_dir / "DejaVuSans.ttf")
        if not os.path.exists(font_reg):
            r = requests.get("https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf")
            Path(font_reg).write_bytes(r.content)
    font_bold = font_reg.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
    if not os.path.exists(font_bold):
        font_bold = font_reg
    try:
        pdfmetrics.registerFont(TTFont("Reg", font_reg))
    except: pass
    try:
        pdfmetrics.registerFont(TTFont("Bold", font_bold))
    except: pass
    INK   = colors.HexColor("#0D1B2A")
    CHAR  = colors.HexColor("#162030")
    GOLD  = colors.HexColor("#C9972A")
    WARM  = colors.HexColor("#1E3050")
    MID   = colors.HexColor("#90A8C8")
    WHITE = colors.white
    GREEN = colors.HexColor("#4ADE80")
    RED   = colors.HexColor("#CC0033")
    BLUE  = colors.HexColor("#003DA5")
    D1    = colors.HexColor("#1A2438")
    PAGE_W, PAGE_H = A4
    M  = 16*mm
    CW = PAGE_W - 2*M
    def h(text):
        if not text: return ""
        return get_display(arabic_reshaper.reshape(str(text)))
    def S(name, size=11, color=WHITE, align=TA_RIGHT, bold=False, leading=None):
        return ParagraphStyle(name, fontName="Bold" if bold else "Reg",
            fontSize=size, textColor=color, alignment=align,
            leading=leading or size*1.55)
    def fit_img(path, mw, mh):
        try:
            img = PILImage.open(path)
            iw, ih = img.size
            r = min(mw/iw, mh/ih)
            return RLImage(str(path), width=iw*r, height=ih*r)
        except: return None
    def logo_flowable(max_w, max_h):
        logo_path = "/app/logo.png" if os.path.exists("/app/logo.png") else "logo.png"
        if not os.path.exists(logo_path):
            return None
        try:
            logo = PILImage.open(logo_path).convert("RGBA")
            bg = PILImage.new("RGBA", logo.size, (13, 27, 42, 255))
            comp = PILImage.alpha_composite(bg, logo).convert("RGB")
            tmp = str(session_dir / "logo_dark.jpg")
            comp.save(tmp, "JPEG", quality=95)
            iw, ih = comp.size
            r = min(max_w/iw, max_h/ih)
            return RLImage(tmp, width=iw*r, height=ih*r)
        except: return None
    def cover_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, PAGE_H-4*mm, PAGE_W, 4*mm, fill=1, stroke=0)
        canvas.setFillColor(RED)
        canvas.rect(0, PAGE_H-8*mm, PAGE_W, 4*mm, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.rect(0, 0, PAGE_W, 2*mm, fill=1, stroke=0)
        canvas.restoreState()
    def inner_bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, PAGE_H-4*mm, PAGE_W, 4*mm, fill=1, stroke=0)
        canvas.setFillColor(RED)
        canvas.rect(0, PAGE_H-13*mm, PAGE_W, 9*mm, fill=1, stroke=0)
        agent = f"{data.get('agent_name','')} | {data.get('agency','RE/MAX Family')} | {data.get('agent_phone','')}"
        canvas.setFillColor(WHITE)
        canvas.setFont("Bold", 8)
        canvas.drawCentredString(PAGE_W/2, PAGE_H-10*mm, h(agent))
        canvas.setFillColor(GOLD)
        canvas.rect(0, 0, PAGE_W, 9*mm, fill=1, stroke=0)
        canvas.setFillColor(INK)
        canvas.setFont("Bold", 8)
        canvas.drawCentredString(PAGE_W/2, 3*mm, str(doc.page))
        canvas.setFillColor(BLUE)
        canvas.rect(M-5*mm, 12*mm, 3, PAGE_H-24*mm, fill=1, stroke=0)
        canvas.restoreState()
    def page_cb(canvas, doc):
        cover_bg(canvas, doc) if doc.page == 1 else inner_bg(canvas, doc)
    story = []
    # PAGE 1: COVER
    hero = fit_img(image_paths[0], PAGE_W-2*M, 82*mm) if image_paths else None
    if hero:
        hero.hAlign = "CENTER"
        story.append(Spacer(1, 8*mm))
        story.append(hero)
    story.append(Spacer(1, 5*mm))
    story.append(Table([[""]], colWidths=[CW],
        style=[("LINEABOVE",(0,0),(-1,-1),1.5,GOLD),("TOPPADDING",(0,0),(-1,-1),0)]))
    story.append(Spacer(1, 4*mm))
    excl = "  ✨ בלעדיות | לא פורסמה מעולם  " if data.get("exclusive") else "  🏠 למכירה  "
    story.append(Paragraph(h(excl), S("badge",12,GOLD,TA_CENTER,bold=True)))
    story.append(Spacer(1, 3*mm))
    addr = data.get("address","")
    neighborhood = data.get("neighborhood","")
    city = data.get("city","")
    subtitle = f"{neighborhood} — {city}".strip(" —") if neighborhood else city
    story.append(Paragraph(h(addr), S("addr",26,WHITE,TA_CENTER,bold=True,leading=32)))
    story.append(Paragraph(h(subtitle), S("city",13,MID,TA_CENTER,leading=20)))
    story.append(Spacer(1, 5*mm))
    price_display = data.get("price_display","")
    pt = Table([[Paragraph(h(price_display), S("price",22,GOLD,TA_CENTER,bold=True))]], colWidths=[82*mm])
    pt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),BLUE),("ROUNDEDCORNERS",[5]),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
    ]))
    story.append(Table([[pt]], colWidths=[CW],
        style=[("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(Spacer(1, 5*mm))
    story.append(Table([[""]], colWidths=[CW],
        style=[("LINEABOVE",(0,0),(-1,-1),1.5,GOLD),("TOPPADDING",(0,0),(-1,-1),0)]))
    story.append(Spacer(1, 4*mm))
    rooms = str(data.get("rooms",""))
    size  = str(data.get("size_sqm",""))
    balc  = str(data.get("balcony_sqm","")) if data.get("balcony_sqm") else "—"
    floor = f"{data.get('floor','')}/{data.get('total_floors','')}"
    stats = []
    for val, lbl in [(rooms,"חדרים"),(size,'מ"ר'),(balc,'מרפסת'),(floor,"קומה")]:
        stats.append(Table([
            [Paragraph(h(val), S("sv",19,GOLD,TA_CENTER,bold=True))],
            [Paragraph(h(lbl), S("sl",9,MID,TA_CENTER))],
        ], colWidths=[CW/4]))
    story.append(Table([stats], colWidths=[CW/4]*4,
        style=[("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
               ("LINEBEFORE",(1,0),(-1,-1),0.5,CHAR)]))
    story.append(Spacer(1, 5*mm))
    logo = logo_flowable(52*mm, 18*mm)
    if logo:
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 3*mm))
    phone_raw = data.get("agent_phone","")
    agent_line = f"{data.get('agent_name','')}  |  {phone_raw}"
    story.append(Paragraph(h(agent_line), S("ac",10,MID,TA_CENTER)))
    story.append(PageBreak())
    # PAGE 2: GALLERY
    story.append(Spacer(1,5*mm))
    story.append(Paragraph(h("הנכס"), S("sec",16,GOLD,TA_RIGHT,bold=True)))
    story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=4*mm))
    ph_w = (CW-3*mm)/2
    ph_h = 54*mm
    if len(image_paths) == 1:
        big = fit_img(image_paths[0], CW, 110*mm)
        if big:
            big.hAlign = "CENTER"
            story.append(big)
    elif len(image_paths) >= 2:
        imgs = image_paths[:4]
        while len(imgs) < 4:
            imgs.append(None)
        row1 = []
        caps1 = []
        img_labels = data.get("image_labels", [])
        captions = (img_labels + ["📷 תמונה 1","📷 תמונה 2","📷 תמונה 3","📷 תמונה 4"])[:4]
        for i in range(2):
            im = fit_img(imgs[i], ph_w, ph_h) if imgs[i] else None
            if im: im.hAlign = "CENTER"
            row1.append(im or Paragraph("",S(f"e{i}",8,MID,TA_CENTER)))
            caps1.append(Paragraph(h(captions[i]), S(f"c{i}",9,MID,TA_CENTER)))
        grid = [row1]
        row_h = [ph_h]
        if len(image_paths) >= 3:
            row2 = []
            for i in range(2, min(4, len(image_paths))):
                im = fit_img(image_paths[i], ph_w, ph_h)
                if im: im.hAlign = "CENTER"
                row2.append(im or Paragraph("",S(f"e2{i}",8,MID,TA_CENTER)))
            while len(row2) < 2:
                row2.append(Paragraph("",S("ep",8,MID,TA_CENTER)))
            grid += [row2]
            row_h += [ph_h]
        story.append(Table(grid, colWidths=[ph_w,ph_w], rowHeights=row_h,
            style=[("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                   ("COLPADDING",(0,0),(-1,-1),2),("ROWPADDING",(0,0),(-1,-1),1)]))
    story.append(Spacer(1,4*mm))
    amenities = []
    if data.get("parking"): amenities.append(("P","חניה"))
    if data.get("elevator"): amenities.append(("↑","מעלית"))
    if data.get("storage"): amenities.append(("■","מחסן"))
    if data.get("shelter"): amenities.append(("*",'ממ"ד'))
    if not amenities:
        amenities = [("◆","נכס"),("m",'מ"ר'),("K","מפתח"),("★","איכות")]
    amenities = amenities[:4]
    bar_cells = [Table([
        [Paragraph(icon, S("bi",14,GOLD,TA_CENTER))],
        [Paragraph(h(txt), S("bt",9,WHITE,TA_CENTER,bold=True))],
    ], colWidths=[CW/len(amenities)]) for icon,txt in amenities]
    bt = Table([bar_cells], colWidths=[CW/len(amenities)]*len(amenities))
    bt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),BLUE),("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("ROUNDEDCORNERS",[4]),
    ]))
    story.append(bt)
    story.append(PageBreak())
    # PAGE 3: DETAILS
    story.append(Spacer(1,5*mm))
    story.append(Paragraph(h("פרטי הנכס"), S("sec2",16,GOLD,TA_RIGHT,bold=True)))
    story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=4*mm))
    detail_rows = [
        ("כתובת",     data.get("address","")),
        ("מחיר",      data.get("price_display","")),
        ("חדרים",     str(data.get("rooms",""))),
        ("שטח",       f"{data.get('size_sqm','')} מ\"ר"),
        ("מרפסת",     f"{data.get('balcony_sqm','')} מ\"ר" if data.get("balcony_sqm") else ""),
        ("קומה",      f"{data.get('floor','')} מתוך {data.get('total_floors','')}"),
        ("חניה",      str(data.get("parking","")) if data.get("parking") else ""),
        ("מחסן",      "כן" if data.get("storage") else ""),
        ('ממ"ד',      "כן" if data.get("shelter") else ""),
        ("מצב",       data.get("condition","")),
    ]
    rows_data = [[
        Paragraph(h(v), S("dv",11,WHITE,TA_RIGHT,bold=True)),
        Paragraph(h(l), S("dl",10,MID,TA_RIGHT)),
    ] for l,v in detail_rows if v]
    dt = Table(rows_data, colWidths=[CW*0.62, CW*0.38])
    dt.setStyle(TableStyle([
        ("ALIGN",(0,0),(-1,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[CHAR, D1]),
        ("LINEBELOW",(0,0),(-1,-1),0.4,WARM),("ROUNDEDCORNERS",[3]),
    ]))
    story.append(dt)
    story.append(Spacer(1,5*mm))
    desc = data.get("description","")
    if desc:
        story.append(Paragraph(h("על הנכס"), S("sec3",16,GOLD,TA_RIGHT,bold=True)))
        story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=4*mm))
        for line in desc.split("\n"):
            if line.strip():
                story.append(Paragraph(h(line.strip()), S("body",11,WHITE,TA_RIGHT,leading=17)))
                story.append(Spacer(1,2*mm))
    story.append(PageBreak())
    # PAGE 4: AREA
    try:
        area_items = data.get("_area_info") or get_area_info(data.get("city",""), data.get("neighborhood",""))
        if area_items:
            story.append(Spacer(1,5*mm))
            area_name = data.get("neighborhood") or data.get("city","")
            story.append(Paragraph(h(f"למה {area_name}?"), S("sec4",16,GOLD,TA_RIGHT,bold=True)))
            story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=4*mm))
            for item in area_items:
                if isinstance(item, dict):
                    row = [[
                        Paragraph(h(item.get("desc","")), S("ad",10,WHITE,TA_RIGHT,leading=15)),
                        Paragraph(h(item.get("title","")), S("at",11,WHITE,TA_RIGHT,bold=True)),
                        Paragraph(str(item.get("icon","🏠")), S("ai2",15,GOLD,TA_CENTER)),
                    ]]
                    rt = Table(row, colWidths=[CW*0.60, CW*0.28, CW*0.12])
                    rt.setStyle(TableStyle([
                        ("ALIGN",(0,0),(-1,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"TOP"),
                        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
                        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),6),
                        ("BACKGROUND",(0,0),(-1,-1),CHAR),("ROUNDEDCORNERS",[4]),
                        ("BOX",(0,0),(-1,-1),0.5,WARM),
                    ]))
                    story.append(rt)
                    story.append(Spacer(1,2.5*mm))
            story.append(PageBreak())
    except Exception as e:
        log.error(f"Area info page error: {e}")
    # PAGE 5: TRANSACTIONS
    try:
        transactions = data.get("_transactions") or get_transactions(
            data.get("city",""), data.get("neighborhood",""),
            str(data.get("rooms","")), data.get("address",""))
        if transactions:
            story.append(Spacer(1,5*mm))
            area_name = data.get("neighborhood") or data.get("city","")
            story.append(Paragraph(
                h(f"דוח עסקאות — {area_name} | {data.get('rooms','')} חדרים | 2024–2025"),
                S("sec5",13,GOLD,TA_RIGHT,bold=True)))
            story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=3*mm))
            story.append(Paragraph(h('מקור: רשות המסים, mynet, מדלן | עסקאות מאומתות'),
                S("src",9,MID,TA_RIGHT)))
            story.append(Spacer(1,3*mm))
            col_w = [CW*0.22,CW*0.13,CW*0.13,CW*0.13,CW*0.12,CW*0.27]
            header = [
                Paragraph(h("מחיר עסקה"), S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h("קומה"),       S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h('מ"ר'),       S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h('מחיר/מ"ר'),  S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h("תאריך"),      S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h("פרטים"),      S("th",9.5,WHITE,TA_RIGHT,bold=True)),
            ]
            tbl_data = [header]
            for t in transactions:
                if isinstance(t, dict):
                    tbl_data.append([
                        Paragraph(h(str(t.get("price",""))),   S("td",9.5,GREEN,TA_CENTER,bold=True)),
                        Paragraph(h(str(t.get("floor",""))),   S("td",9.5,WHITE,TA_CENTER)),
                        Paragraph(h(str(t.get("area",""))),    S("td",9.5,WHITE,TA_CENTER)),
                        Paragraph(h(str(t.get("ppm",""))),     S("td",9,MID,TA_CENTER)),
                        Paragraph(h(str(t.get("date",""))),    S("td",9,MID,TA_CENTER)),
                        Paragraph(h(str(t.get("details",""))), S("td",9,WHITE,TA_RIGHT)),
                    ])
            tt = Table(tbl_data, colWidths=col_w)
            tt.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),BLUE),
                ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
                ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[CHAR, D1]),
                ("LINEBELOW",(0,0),(-1,-1),0.4,WARM),
                ("LINEBELOW",(0,0),(-1,0),1.5,GOLD),
                ("ROUNDEDCORNERS",[3]),("BOX",(0,0),(-1,-1),0.5,WARM),
            ]))
            story.append(tt)
            story.append(Spacer(1,5*mm))
            story.append(HRFlowable(width="100%",thickness=0.5,color=WARM,spaceAfter=4*mm))
            story.append(Paragraph(h("ניתוח השוק"), S("sumh",13,GOLD,TA_RIGHT,bold=True)))
            story.append(Spacer(1,2*mm))
            prices = []
            ppms = []
            for t in transactions:
                if isinstance(t, dict):
                    try:
                        p = str(t.get("price","")).replace("₪","").replace(",","").replace(" ","").strip()
                        if p: prices.append(int(float(p)))
                    except: pass
                    try:
                        pm = str(t.get("ppm","")).replace("~","").replace(",","").replace(" ","").strip()
                        if pm: ppms.append(int(float(pm)))
                    except: pass
            summary_rows = []
            if prices:
                mn, mx = min(prices), max(prices)
                avg_ppm = int(sum(ppms)/len(ppms)) if ppms else 0
                price_display = data.get("price_display","")
                rooms_str = str(data.get("rooms",""))
                shekel = "₪"
                summary_rows = [
                    (f"טווח מחירים — {rooms_str} חד' באזור:", f"{mn:,} – {mx:,} {shekel}"),
                    ('מחיר ממוצע למ"ר:', f"~{avg_ppm:,} {shekel}" if avg_ppm else "—"),
                    ("מחיר השיווק:", f"{price_display}  ← השווה לשוק"),
                ]
            for lbl, val in summary_rows:
                sr = Table([[
                    Paragraph(h(val), S("sv2",11,GREEN,TA_RIGHT,bold=True)),
                    Paragraph(h(lbl), S("sl2",10,MID,TA_RIGHT)),
                ]], colWidths=[CW*0.45, CW*0.55])
                sr.setStyle(TableStyle([
                    ("ALIGN",(0,0),(-1,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
                    ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
                    ("ROWBACKGROUNDS",(0,0),(-1,-1),[CHAR]),
                    ("LINEBELOW",(0,0),(-1,-1),0.4,WARM),
                ]))
                story.append(sr)
            story.append(Spacer(1,3*mm))
            story.append(Paragraph(
                h("* הנתונים מבוססים על עסקאות שדווחו לרשות המסים ופורסמו בתקשורת. אינם מהווים ייעוץ השקעות."),
                S("disc2",8,MID,TA_RIGHT)))
            story.append(PageBreak())
    except Exception as e:
        log.error(f"Transactions page error: {e}")
    # PAGE 6: CONTACT
    story.append(Spacer(1,10*mm))
    story.append(Paragraph(h(addr), S("recap",18,WHITE,TA_CENTER,bold=True,leading=24)))
    story.append(Spacer(1,3*mm))
    summary = f"{rooms} חדרים | {size} מ\"ר | קומה {floor}"
    story.append(Paragraph(h(summary), S("recap2",11,MID,TA_CENTER)))
    story.append(Spacer(1,5*mm))
    story.append(HRFlowable(width="70%",thickness=1,color=WARM,spaceAfter=5*mm))
    logo2 = logo_flowable(68*mm, 24*mm)
    phone_fmt = phone_raw
    if len(phone_fmt) == 10:
        phone_fmt = f"{phone_fmt[:3]}-{phone_fmt[3:6]}-{phone_fmt[6:]}"
    profile_pic_path = data.get("_profile_pic")
    profile_pic_img = None
    if profile_pic_path and os.path.exists(profile_pic_path):
        try:
            from PIL import Image as PILImg
            pic = PILImg.open(profile_pic_path).convert("RGB")
            size_px = min(pic.size)
            left = (pic.width - size_px) // 2
            top  = (pic.height - size_px) // 2
            pic = pic.crop((left, top, left+size_px, top+size_px))
            pic = pic.resize((200, 200))
            tmp_pic = str(Path(profile_pic_path).parent / "profile_square.jpg")
            pic.save(tmp_pic, "JPEG", quality=90)
            profile_pic_img = RLImage(tmp_pic, width=28*mm, height=28*mm)
            profile_pic_img.hAlign = "CENTER"
        except Exception as e:
            log.error(f"Profile pic in PDF error: {e}")
    contact_rows = []
    if logo2:
        logo2.hAlign = "CENTER"
        contact_rows += [[logo2],[Spacer(1,4*mm)]]
    if profile_pic_img:
        contact_rows += [[profile_pic_img],[Spacer(1,3*mm)]]
    contact_rows += [
        [Paragraph(h(data.get("agent_name","")), S("cn",23,WHITE,TA_CENTER,bold=True))],
        [Spacer(1,2*mm)],
        [Paragraph(h(data.get("agency","RE/MAX Family")), S("ct",11,MID,TA_CENTER))],
        [Spacer(1,6*mm)],
        [Paragraph(h(f"📲  {phone_fmt}"), S("cp",21,GOLD,TA_CENTER,bold=True))],
        [Spacer(1,8*mm)],
        [Paragraph(h("לפרטים נוספים ולתיאום סיור — צרו קשר עכשיו!"),
            S("cta",12,GOLD,TA_CENTER,bold=True))],
        [Spacer(1,8*mm)],
        [HRFlowable(width="60%",thickness=1,color=WARM)],
        [Spacer(1,5*mm)],
        [Paragraph(h(f"מחיר: {price_display}"), S("pf",22,GOLD,TA_CENTER,bold=True))],
    ]
    ct = Table(contact_rows, colWidths=[CW])
    ct.setStyle(TableStyle([
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("BACKGROUND",(0,0),(-1,-1),CHAR),
        ("BOX",(0,0),(-1,-1),1,WARM),("ROUNDEDCORNERS",[6]),
        ("TOPPADDING",(0,0),(0,0),14),("BOTTOMPADDING",(0,-1),(-1,-1),14),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),
    ]))
    story.append(ct)
    story.append(Spacer(1,5*mm))
    story.append(Paragraph(h("המידע כפוף לאימות ובדיקה."), S("disc",8,MID,TA_CENTER)))
    out_path = session_dir / "presentation.pdf"
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=14*mm, bottomMargin=12*mm)
    doc.build(story, onFirstPage=page_cb, onLaterPages=page_cb)
    return out_path
# VERSION: v13-buyers
# ══════════════════════════════════════════════════════════════════════════════
# SESSION PROCESSOR
# ══════════════════════════════════════════════════════════════════════════════
def process_session(phone: str):
    session = sessions.pop(phone, None)
    if not session:
        return
    send_text(phone, "⏳ מכין את המצגת... כולל חיפוש עסקאות ומידע על השכונה.\nאנא המתן כ-90 שניות 🏠")
    session_dir = WORK_DIR / str(uuid.uuid4())
    session_dir.mkdir(exist_ok=True)
    try:
        log.info(f"Parsing text for {phone}")
        data = parse_listing_text(session["text"])
        if not data:
            send_text(phone, "❌ לא הצלחתי לפרסר את פרטי הנכס. נסה שוב.")
            return
        processed_images = []
        for _lp in [Path("/app/logo.png"), Path("logo.png"), Path(__file__).parent / "logo.png"]:
            if _lp.exists():
                logo_path = _lp
                break
        else:
            logo_path = None
        log.info(f"Logo path: {logo_path}")
        for i, img_info in enumerate(session["images"][:4]):
            img_path = session_dir / f"img_{i}.jpg"
            if img_info.get("url"):
                ok = download_media(img_info["url"], img_path)
                if not ok:
                    continue
            elif img_info.get("data"):
                img_path.write_bytes(base64.b64decode(img_info["data"]))
            if has_remax_logo(img_path):
                processed_images.append(img_path)
                log.info(f"Image {i}: RE/MAX logo found — keeping as-is")
            else:
                if logo_path and logo_path.exists():
                    out_img = session_dir / f"img_{i}_logo.jpg"
                    add_remax_logo_to_image(img_path, out_img, logo_path)
                    processed_images.append(out_img)
                    log.info(f"Image {i}: added RE/MAX logo")
                else:
                    processed_images.append(img_path)
                    log.info(f"Image {i}: no logo file available")
        from concurrent.futures import ThreadPoolExecutor
        area_result = [None]
        trans_result = [None]
        def fetch_area():
            try:
                area_result[0] = get_area_info(data.get("city",""), data.get("neighborhood",""))
                log.info(f"Area info fetched: {len(area_result[0]) if isinstance(area_result[0], list) else 0} items")
            except Exception as e:
                log.error(f"Area fetch error: {e}")
        def fetch_trans():
            try:
                trans_result[0] = get_transactions(
                    data.get("city",""), data.get("neighborhood",""),
                    str(data.get("rooms","")), data.get("address",""))
                log.info(f"Transactions fetched: {len(trans_result[0]) if isinstance(trans_result[0], list) else 0} items")
            except Exception as e:
                log.error(f"Trans fetch error: {e}")
        def fetch_pic():
            try:
                pic_path = session_dir / "profile_pic.jpg"
                ok = download_profile_pic(phone, pic_path)
                if ok:
                    data["_profile_pic"] = str(pic_path)
                    log.info("Profile pic fetched OK")
                else:
                    log.info("Profile pic not available")
            except Exception as e:
                log.error(f"Profile pic fetch error: {e}")
        with ThreadPoolExecutor(max_workers=1) as executor:
            f3 = executor.submit(fetch_pic)
        fetch_area()
        time.sleep(5)
        fetch_trans()
        try: f3.result(timeout=15)
        except: pass
        data["_area_info"]    = area_result[0] if isinstance(area_result[0], list) else []
        data["_transactions"] = trans_result[0] if isinstance(trans_result[0], list) else []
        log.info(f"Generating PDF for {phone}")
        pdf_path = generate_pdf(data, processed_images, session_dir)
        addr  = data.get("address", "נכס")
        price = data.get("price_display", "")
        fname = f"מצגת_{addr.replace(' ','_')[:30]}.pdf"
        caption = f"✅ מצגת מוכנה!\n📍 {addr}\n💰 {price}"
        ok = send_document(phone, str(pdf_path), fname, caption)
        if ok:
            log.info(f"PDF sent successfully to {phone}")
        else:
            send_text(phone, "⚠️ ה-PDF נוצר אך נכשל בשליחה. נסה שוב.")
    except Exception as e:
        log.error(f"Process error for {phone}: {e}", exc_info=True)
        send_text(phone, f"❌ שגיאה בעיבוד: {str(e)[:100]}")
    finally:
        import shutil
        try: shutil.rmtree(session_dir)
        except: pass
def schedule_processing(phone: str):
    if phone in sessions and sessions[phone].get("timer"):
        sessions[phone]["timer"].cancel()
    timer = threading.Timer(SESSION_TIMEOUT, process_session, args=[phone])
    timer.daemon = True
    timer.start()
    if phone in sessions:
        sessions[phone]["timer"] = timer
# ══════════════════════════════════════════════════════════════════════════════
# SEARCH BOT — מציאת נכסים תואמים (קונה מחפש דירה)
# ══════════════════════════════════════════════════════════════════════════════
_CITY_NB_MAP_HE = """נרמול ערים — הערים האפשריות:
- "מוצקין" / "קרית מוצקין" / "קריית מוצקין" → city = "קרית מוצקין"
- "ביאליק" / "קרית ביאליק" → city = "קרית ביאליק"
- "אתא" / "קרית אתא" → city = "קרית אתא"
- "ים" / "קרית ים" → city = "קרית ים"
- "חיים" / "קרית חיים" → city = "חיפה" (קרית חיים היא שכונה בחיפה)
- "חיפה" → city = "חיפה"
מיפוי מלא של שכונות לערים (חשוב מאוד!):

🏙️ **קרית ביאליק**:
- "אפק" / "נאות אפק" / "אפקה" / "הברושים" → neighborhood="אפק"
- "צור שלום" → neighborhood="צור שלום"
- "גבעת הרקפות בביאליק" → neighborhood="גבעת הרקפות"
- "הפרפר" → neighborhood="הפרפר"
- "מרכז העיר בביאליק" / "סביניה" → neighborhood="מרכז" / "סביניה"
- "הוותיקה בביאליק" → neighborhood="ותיק"
- "ביאליק דרום" → neighborhood="ביאליק דרום"

🏙️ **קרית מוצקין**:
- "מוצקין הותיקה" / "ותיקה" (ברירת מחדל) → neighborhood="ותיק"
- "אביבים" → neighborhood="אביבים"
- "נווה גנים" → neighborhood="נווה גנים"
- "משכנות האומנים" / "משכנות אומנים" / "משכנות" → neighborhood="משכנות"
- "לב מוצקין" / "בנה ביתך" → neighborhood="לב מוצקין"

🏙️ **קרית ים**:
- "קרית ים א'" / "קרית ים ב'" / "קרית ים ג'" / "קרית ים ד'" → neighborhood="קרית ים X"
- "פסגות ים" → neighborhood="פסגות ים"
- "סביונים" / "סביוני ים" → neighborhood="סביונ"
- "גלי ים" → neighborhood="גלי ים"
- "אלמוגים" → neighborhood="אלמוגים"
- "בנה ביתך" (בקרית ים — לא להתבלבל עם לב מוצקין שבקרית מוצקין) → neighborhood="בנה ביתך"
- "יוספטל" → neighborhood="יוספטל"
- "אג״ש" → neighborhood="אג״ש"
- "נווה חוף" → neighborhood="נווה חוף"
- "לכיש" → neighborhood="לכיש"

🏙️ **קרית אתא**:
- "גבעת רם" → neighborhood="גבעת רם"
- "גבעת הרקפות באתא" / "גבעת תל חי" → neighborhood="גבעת הרקפות"
- "גבעת טל" → neighborhood="גבעת טל"
- "אלונים" / "גבעת אלונים" → neighborhood="אלונים"
- "מרכז העיר באתא" → neighborhood="מרכז"
- "קרית בנימין" → neighborhood="קרית בנימין"
- "גבעה א'" / "שביט" → neighborhood="גבעה א" / "שביט"
- "בית וגן" → neighborhood="בית וגן"
- "בן גוריון" → neighborhood="בן גוריון"
- "נווה חן" → neighborhood="נווה חן"
- "נווה אברהם" → neighborhood="נווה אברהם"
- "אברמסקי" → neighborhood="אברמסקי"
- "פרוסטיג" → neighborhood="פרוסטיג"
- "דשנים" → neighborhood="דשנים"
- "גבעת הכלניות" → neighborhood="גבעת הכלניות"

🏙️ **חיפה**:
- "קרית חיים מערבית" / "מערבית" → neighborhood="מערבית"
- "קרית חיים מזרחית" / "מזרחית" → neighborhood="מזרחית"
- "קרית חיים" (בלי כיוון) → neighborhood="קרית חיים"

⚠️ כללים חשובים:
1. אם הסוכן ציין שכונה — תמצא בה את העיר הנכונה מהרשימה. אל תניח אוטומטית "קרית מוצקין".
2. שכונות עם אותו שם בערים שונות (גבעת הרקפות / מרכז העיר / ותיקה) — חכה לציון מפורש של העיר. אם לא צוינה עיר, שאל: השתמש בברירת המחדל הנפוצה (לרוב מוצקין).
3. אם השכונה לא מופיעה ברשימה ולא צוינה עיר — השאר city=null ואל תנחש."""

# מיפוי שכונות חד-משמעיות → עיר (לאכיפה בצד השרת, כדי שלא ייכנסו נכסים מעיר אחרת עם אותו שם רחוב)
_NB_TO_CITY = {
    "נווה גנים": "קרית מוצקין", "אביבים": "קרית מוצקין", "משכנות": "קרית מוצקין", "לב מוצקין": "קרית מוצקין",
    "אפק": "קרית ביאליק", "צור שלום": "קרית ביאליק", "הפרפר": "קרית ביאליק", "ביאליק דרום": "קרית ביאליק",
    "פסגות ים": "קרית ים", "סביונ": "קרית ים", "גלי ים": "קרית ים", "אלמוגים": "קרית ים",
    "יוספטל": "קרית ים", "נווה חוף": "קרית ים", "לכיש": "קרית ים",
    "גבעת רם": "קרית אתא", "גבעת טל": "קרית אתא", "אלונים": "קרית אתא", "קרית בנימין": "קרית אתא",
    "בית וגן": "קרית אתא", "בן גוריון": "קרית אתא", "נווה חן": "קרית אתא", "נווה אברהם": "קרית אתא",
    "אברמסקי": "קרית אתא", "פרוסטיג": "קרית אתא", "דשנים": "קרית אתא", "גבעת הכלניות": "קרית אתא",
}
# שכונות עמומות (אותו שם בכמה ערים) — לא אוכפים: גבעת הרקפות, מרכז, ותיק, בנה ביתך, שביט, גבעה א'

def _enforce_nb_city(parsed):
    """אם צוינה שכונה אחת חד-משמעית — אוכפים את העיר שלה (מונע דליפת נכסים מעיר אחרת)."""
    try:
        if isinstance(parsed, dict) and not parsed.get("neighborhoods"):
            pn = (parsed.get("neighborhood") or "").strip()
            if pn:
                for nb, ct in _NB_TO_CITY.items():
                    if pn == nb or nb in pn:   # שם השכונה המלא מופיע בערך שחזר מהפענוח
                        parsed["city"] = ct
                        parsed["cities"] = None
                        break
    except Exception:
        pass
    return parsed

def _enforce_ptype(parsed, text):
    """אכיפת סוג נכס מתוך טקסט החיפוש — אם הפענוח פספס (קבוצת גן / פנטהאוז)."""
    try:
        t = str(text or "")
        if re.search(r"דיר\S*\s*גן|גינה|קומת\s*קרקע|קומה\s*0|קרקע|קוטג", t):
            parsed["property_type"] = "דירת גן"   # קבוצת גן: גן/קרקע/קומה 0/קוטג'
        elif re.search(r"פנטהאו", t):
            parsed["property_type"] = "פנטהאוז"
    except Exception:
        pass
    return parsed

def parse_search_query(text: str) -> dict:
    prompt = f"""אתה עוזר לסוכן נדל"ן ברימקס שמחפש נכסים במאגר המשרד עבור לקוח.
הסוכן שלח לך הודעה עם דרישות הלקוח. חלץ פרמטרים ל-JSON בלבד (ללא markdown, ללא backticks).
{_CITY_NB_MAP_HE}
חוקי זיהוי must_have — חשוב מאוד!
- "דירת גן" / "עם גינה" / "עם חצר" → must_have כולל "גינה", property_type = "דירת גן"
- "עם חנייה" / "חנייה פרטית" → must_have כולל "חנייה"
- "עם מעלית" → must_have כולל "מעלית"
- "עם ממ"ד" → must_have כולל "ממ\"ד"
- "עם מרפסת" → must_have כולל "מרפסת"
- "קרקע" / "קומת קרקע" / "קומה 0" → must_have כולל "גינה", property_type = "דירת גן"
חוקי property_type — חשוב מאוד!
- קבוצת "גן" (כולן נחשבות חיפוש דירת גן): "דירת גן" / "קרקע" / "קומת קרקע" / "קומה 0" / "קוטג'" / "מיני קוטג'" → property_type = "דירת גן" (לא "דירה"! לא פנטהאוז!) וגם must_have כולל "גינה"
- "פנטהאוז" / "גג" / "קומה עליונה" → property_type = "פנטהאוז"
- "דו משפחתי" / "בית פרטי" → property_type = "קוטג'"
- "וילה" → property_type = "וילה"
- "דופלקס" → property_type = "דופלקס"
- דירה רגילה ללא ציון מיוחד → property_type = "דירה"
שדות JSON:
- city: עיר ראשית (אחת מהערים למעלה או null) — אם ציינו עיר אחת
- cities: רשימת ערים (אם ציינו יותר מעיר אחת, למשל ["קרית מוצקין","קרית ביאליק"]) — אחרת null
- neighborhood: שכונה (substring לחיפוש, או null) — אם ציינו שכונה אחת
- neighborhoods: רשימת שכונות (אם ציינו יותר משכונה אחת, למשל ["סביונ","פסגות ים"]) — אחרת null
- street: שם רחוב (אם הסוכן ציין, או null)
- rooms_min: מספר חדרים מינימלי (מספר עשרוני, או null)
- rooms_max: מספר חדרים מקסימלי (מספר עשרוני, או null) - "4 חדרים" → min=max=4
- budget_min: מחיר מינימלי בש"ח (מספר, או null) - "בין 3 ל-3.5 מיליון" → budget_min=3000000
- budget_max: מחיר מקסימלי בש"ח (מספר, או null) - "עד 2 מיליון" → 2000000, "בין 3 ל-3.5 מיליון" → budget_max=3500000
- size_min: מ"ר מינימלי (מספר, או null)
- size_max: מ"ר מקסימלי (מספר, או null)
- floor_max: קומה מקסימלית (מספר, או null) - "עד קומה 2" → floor_max=2, "קומה נמוכה" → floor_max=3
- property_type: סוג נכס מנורמל ("דירה" / "פנטהאוז" / "דופלקס" / "קוטג'" / "וילה" / "דו משפחתי" / null)
- deal_type: "מכירה" / "השכרה" - ברירת מחדל "מכירה" אם לא צוין
- must_have: רשימת תכונות חובה לפי החוקים למעלה (מערך, יכול להיות ריק)
- summary_he: סיכום קצר בעברית של הבקשה (משפט אחד)
דוגמאות:
- "מחפש דירת גן 4 חדרים בביאליק עד 3 מיליון" →
  city="קרית ביאליק", rooms_min=4, rooms_max=4, budget_max=3000000,
  property_type="דירת גן", must_have=["גינה"]
- "מחפש פנטהאוז 5 חדרים בחיפה" →
  city="חיפה", rooms_min=5, rooms_max=5, property_type="פנטהאוז", must_have=[]
- "מחפש דירה בביאליק עם מעלית עד קומה 2" →
  city="קרית ביאליק", property_type="דירה", floor_max=2, must_have=["מעלית"]
- "מחפש דירה 4 חדרים בקרית מוצקין עד 2 מיליון" →
  city="קרית מוצקין", rooms_min=4, rooms_max=4, budget_max=2000000,
  property_type="דירה", must_have=[]
- "אני מחפש דירת גן בסביוני ים" → (שכונה בלי ציון עיר מפורש — הסק את העיר מהשכונה)
  city="קרית ים", neighborhood="סביונ", property_type="דירת גן", must_have=["גינה"]
- "4 חדרים בפסגות ים או בסביונים" → (כמה שכונות)
  city="קרית ים", neighborhoods=["פסגות ים","סביונ"], rooms_min=4, rooms_max=4
- "דירה בקרית מוצקין או קרית ביאליק" → (כמה ערים)
  cities=["קרית מוצקין","קרית ביאליק"], property_type="דירה"
טקסט:
{text}"""
    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={
            "anthropic-version": "2023-06-01",
            "x-api-key": CLAUDE_API_KEY,
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}]
        }, timeout=20)
    if r.status_code != 200:
        log.error(f"Search parse error: {r.text}")
        return {}
    text_out = r.json()["content"][0]["text"].strip()
    text_out = re.sub(r"```(?:json)?\s*", "", text_out).strip("` \n")
    match = re.search(r'\{.*\}', text_out, re.DOTALL)
    if match:
        text_out = match.group()
    try:
        return _enforce_ptype(_enforce_nb_city(json.loads(text_out)), text)
    except Exception as e:
        log.error(f"Search JSON parse error: {e}")
        return {}
_agents_cache = {"data": None, "ts": 0}
def fetch_agents_phones() -> dict:
    if _agents_cache["data"] is not None and (time.time() - _agents_cache["ts"]) < 300:
        return _agents_cache["data"]
    if not GOOGLE_SHEETS_API_KEY:
        return {}
    from urllib.parse import quote
    sheet_encoded = quote(CONTACTS_SHEET_NAME)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{sheet_encoded}!A1:B200?key={GOOGLE_SHEETS_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            log.error(f"Contacts API error {r.status_code}: {r.text[:300]}")
            return {}
        data = r.json().get("values", [])
        agents = {}
        for row in data:
            if len(row) < 2:
                continue
            name = (row[0] or "").strip()
            phone = (row[1] or "").strip()
            if name and phone and name not in ("שם מלא", "משרד", "משרד ביאליק"):
                agents[name] = phone
        _agents_cache["data"] = agents
        _agents_cache["ts"] = time.time()
        log.info(f"Loaded {len(agents)} agent contacts")
        return agents
    except Exception as e:
        log.error(f"Fetch agents error: {e}")
        return {}

_agents_full_cache = {"data": None, "ts": 0}
def fetch_agents_full() -> dict:
    """מפה: שם מנורמל -> {name, phone, license} מגיליון 'אנשי קשר' (A=שם, B=טלפון, D=רישיון תיווך)."""
    if _agents_full_cache["data"] is not None and (time.time() - _agents_full_cache["ts"]) < 300:
        return _agents_full_cache["data"]
    if not GOOGLE_SHEETS_API_KEY:
        return {}
    from urllib.parse import quote
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{quote(CONTACTS_SHEET_NAME)}!A1:D200?key={GOOGLE_SHEETS_API_KEY}"
    out = {}
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return {}
        for row in r.json().get("values", []):
            name = (row[0] if len(row) > 0 else "").strip()
            phone = (row[1] if len(row) > 1 else "").strip()
            lic = (row[3] if len(row) > 3 else "").strip()
            if "@" in lic: lic = ""   # עמודה D מכילה מייל, לא רישיון — לא להציג כרישיון על מסמכים
            if name and name not in ("שם מלא", "משרד", "משרד ביאליק", "רישיון תיווך"):
                out[_norm_name(name)] = {"name": name, "phone": phone, "license": lic}
        _agents_full_cache["data"] = out
        _agents_full_cache["ts"] = time.time()
        return out
    except Exception as e:
        log.error(f"agents full error: {e}")
        return {}

_agent_emails_cache = {"data": None, "ts": 0}
def web_agent_emails():
    """מיילים של סוכנים מגיליון 'אנשי קשר' (A=שם, B=טלפון, E=מייל). מפתחות: canon(שם) ו-'p:'+last9(טלפון)."""
    if _agent_emails_cache["data"] is not None and (time.time() - _agent_emails_cache["ts"]) < 300:
        return _agent_emails_cache["data"]
    out = {}
    if not GOOGLE_SHEETS_API_KEY:
        return out
    from urllib.parse import quote
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{quote(CONTACTS_SHEET_NAME)}!A1:E200?key={GOOGLE_SHEETS_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            for row in r.json().get("values", []):
                name = (row[0] if len(row) > 0 else "").strip()
                phone = (row[1] if len(row) > 1 else "").strip()
                # מייל בעמודה D; אם יש עמודה E עם מייל — עדיפה (גמיש לשני המבנים)
                email = (row[3] if len(row) > 3 else "").strip().lower()
                _e5 = (row[4] if len(row) > 4 else "").strip().lower()
                if "@" in _e5: email = _e5
                if not email or "@" not in email:
                    continue
                if name: out[_canon_key(name)] = email
                _l9 = _last9(phone)
                if _l9: out["p:" + _l9] = email
            _agent_emails_cache["data"] = out
            _agent_emails_cache["ts"] = time.time()
    except Exception as e:
        log.error(f"agent emails error: {e}")
    return out
def _agent_email_for(name="", phone=""):
    m = web_agent_emails()
    if phone:
        e = m.get("p:" + _last9(phone))
        if e: return e
    if name:
        return m.get(_canon_key(name), "")
    return ""

def _fmt_vphone(v):
    """נרמול טלפון ישראלי לתצוגה: 0XXXXXXXXX."""
    d = re.sub(r"\D", "", str(v or ""))
    if not d:
        return ""
    if d.startswith("972"):
        d = "0" + d[3:]
    elif not d.startswith("0"):
        d = "0" + d
    return d

_vphone_cache = {"data": None, "ts": 0}
def fetch_agent_virtual_phones() -> dict:
    """מפה: שם סוכן (מנורמל) -> טלפון וירטואלי. גיליון 'אנשי קשר' (עמודה C) + דריסת קונפיג."""
    cached = _vphone_cache["data"] if (_vphone_cache["data"] is not None and (time.time() - _vphone_cache["ts"]) < 300) else None
    if cached is not None:
        out = dict(cached)
    else:
        out = {}
        if GOOGLE_SHEETS_API_KEY:
            from urllib.parse import quote
            url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{quote(CONTACTS_SHEET_NAME)}!A1:C200?key={GOOGLE_SHEETS_API_KEY}"
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    for row in r.json().get("values", []):
                        if len(row) < 3: continue
                        name = (row[0] or "").strip()
                        vp = _fmt_vphone((row[2] or "").strip())
                        if name and vp and name not in ("שם מלא", "משרד", "משרד ביאליק", "טלפון וירטואלי"):
                            out[_norm_name(name)] = vp
            except Exception as e:
                log.error(f"vphone fetch error: {e}")
        _vphone_cache["data"] = dict(out)
        _vphone_cache["ts"] = time.time()
    # דריסת קונפיג (קונסולת המפתח) — מספר וירטואלי שהוגדר ידנית
    try:
        for ag in (_load_config().get("agents") or []):
            vp = (ag.get("vphone") or "").strip()
            nm = _norm_name(ag.get("name", ""))
            if vp and nm: out[nm] = _fmt_vphone(vp)
    except Exception:
        pass
    return out

import threading as _threading
_TTL_CACHE = {}
_TTL_LOCK = _threading.Lock()
def _cache_get(key, ttl):
    with _TTL_LOCK:
        e = _TTL_CACHE.get(key)
        if e and (time.time() - e[0]) < ttl:
            return e[1]
    return None
def _cache_put(key, val):
    with _TTL_LOCK:
        _TTL_CACHE[key] = (time.time(), val)
def _cache_clear(key):
    with _TTL_LOCK:
        _TTL_CACHE.pop(key, None)

def fetch_sheet_rows() -> list:
    c = _cache_get('sheet_rows', _src_ttl(PROPS_SOURCE, 60, 90))
    if c is not None:
        return c
    if PROPS_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            rows = _sbdb.fetch_properties_rows()
            if rows:
                _cache_put('sheet_rows', rows)
            return rows
        except Exception as _sbe:
            log.error(f"supabase properties read failed — falling back to sheets: {_sbe}")
    rows = _fetch_sheet_rows_raw()
    if rows:
        _cache_put('sheet_rows', rows)
    return rows
def _fetch_sheet_rows_raw() -> list:
    if not GOOGLE_SHEETS_API_KEY:
        log.error("GOOGLE_SHEETS_API_KEY not set!")
        return []
    from urllib.parse import quote
    sheet_encoded = quote(PROPERTIES_SHEET_NAME)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{sheet_encoded}!A1:AR?key={GOOGLE_SHEETS_API_KEY}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            log.error(f"Sheets API error {r.status_code}: {r.text[:300]}")
            return []
        data = r.json().get("values", [])
        if len(data) < 2:
            return []
        headers_row = data[0]
        rows = []
        for row in data[1:]:
            row_padded = row + [""] * (len(headers_row) - len(row))
            d = dict(zip(headers_row, row_padded))
            # תיאור הנכס מעמודה AE (אינדקס 30) — לתצוגת "עוד" בכרטיס
            if len(row_padded) > 30:
                d["_desc_ae"] = str(row_padded[30] or "").strip()
            rows.append(d)
        # אין סוכנים מוחרגים — אווה אזולאי שוחררה להתנהג כסוכנת רגילה (בקשת אייל 13/07).
        # להחרגה עתידית: להוסיף שמות ל-EXCLUDED_AGENTS.
        EXCLUDED_AGENTS = set()
        if EXCLUDED_AGENTS:
            rows = [r for r in rows
                    if (r.get("סוכן 1","") or "").strip() not in EXCLUDED_AGENTS
                    and (r.get("סוכן 2","") or "").strip() not in EXCLUDED_AGENTS]
        return rows
    except Exception as e:
        log.error(f"Fetch sheet error: {e}")
        return []
SIGNINGS_SHEET_TAB = os.environ.get("SIGNINGS_SHEET_TAB", "חתימות")
def fetch_signings_from_sheet():
    """קורא חתימות מטאב מלא (ייצוא מהקרם) בגיליון הנכסים. ריק/לא קיים -> [] ונפילה חזרה."""
    c = _cache_get("signings_sheet", 300)
    if c is not None:
        return c
    if not GOOGLE_SHEETS_API_KEY:
        return []
    from urllib.parse import quote
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{quote(SIGNINGS_SHEET_TAB)}!A1:Z?key={GOOGLE_SHEETS_API_KEY}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json().get("values", [])
        if len(data) < 2:
            return []
        headers = [str(h).strip() for h in data[0]]
        def col(row, name):
            try:
                i = headers.index(name)
            except ValueError:
                return ""
            return row[i] if i < len(row) else ""
        out = []
        for row in data[1:]:
            dt = col(row, "סוג הסכם"); agent = col(row, "סוכן")
            if not dt and not agent:
                continue
            rec = col(row, "נוצר בתאריך")
            out.append({
                "agent": agent,
                "agent_phone": col(row, "מספר טלפון סוכן 1"),
                "deal_type": dt,
                "received_at": rec,
                "_date_key": rec,
                "address": col(row, "כתובת") or col(row, "רחוב"),
                "city": "",
                "client_name": col(row, "שם לקוח"),
                "commission_pct": col(row, "העמלה שנחתמה"),
                "notes": col(row, "notes") or col(row, "הערות"),
            })
        _cache_put("signings_sheet", out)
        return out
    except Exception as e:
        log.error(f"signings sheet error: {e}")
        return []
_RECENT_SIGNS = []   # (ts, rec) — גשר נראות: חתימה שנשלחה עכשיו מופיעה מיד, עד שהסנכרון למקור נוחת
def _recent_signs_add(rec):
    try:
        _RECENT_SIGNS.append((time.time(), dict(rec)))
    except Exception:
        pass
def _recent_signs_mark_signed(token, link, cid):
    """הלקוח חתם — מסמן את רשומת הנראות-המיידית כ'נחתם' מיד (link + event_id=ת״ז),
    בלי להמתין לסנכרון גיליון→Supabase. gunicorn=worker יחיד → הזיכרון משותף לכל
    הבקשות, כך שהסוכן רואה 'נחתם' תכף ומיד. (תיקון 'ממתין למרות שחתם', 16/07)"""
    try:
        for i, (t, r) in enumerate(list(_RECENT_SIGNS)):
            if str(r.get("event_id", "") or "") == str(token):
                r = dict(r)
                r["commission_pct"] = link
                if cid:
                    r["event_id"] = cid
                _RECENT_SIGNS[i] = (time.time(), r)   # רענון ה-ts כדי שלא יפוג לפני שהאמת נוחתת
    except Exception:
        pass

_RECENT_SIGN_DELS = []   # (ts, eid, received, client_canon) — הסתרה מיידית של חתימות שנמחקו
def _recent_sign_del_add(eid, received, client):
    try:
        _RECENT_SIGN_DELS.append((time.time(), str(eid or ""), str(received or ""), _canon_key(client or "")))
    except Exception:
        pass
def _recent_sign_dels_filter(rows):
    now = time.time()
    keep = [x for x in _RECENT_SIGN_DELS if now - x[0] < 900]
    _RECENT_SIGN_DELS[:] = keep
    if not keep:
        return rows
    def _gone(r):
        r_eid = str(r.get("event_id", "") or "")
        r_rc = str(r.get("received_at", "") or "")
        r_cl = _canon_key(r.get("client_name", "") or "")
        for (_t, eid, rc, cl) in keep:
            if eid and r_eid == eid and (not rc or r_rc == rc):
                return True
            if not eid and cl and r_cl == cl and rc and r_rc == rc:
                return True
        return False
    return [r for r in rows if not _gone(r)]

def _recent_signs_merge(rows):
    """מוסיף חתימות טריות (עד 15 דק') שעוד לא הגיעו מהמקור. דדופ יציב: גם לפי
    event_id+deal_type וגם לפי סוכן+לקוח+deal_type — כי כשהלקוח חותם, event_id של
    השורה משתנה מהטוקן ל-ת״ז, ודדופ לפי טוקן בלבד היה משאיר רשומת 'ממתין' יתומה
    ליד ה'נחתם' (כפילות שאייל ראה 16/07)."""
    now = time.time()
    keep = [(t, r) for (t, r) in _RECENT_SIGNS if now - t < 900]
    _RECENT_SIGNS[:] = keep
    if not keep:
        return rows

    def _tokkey(r):
        return (str(r.get("event_id", "") or ""), str(r.get("deal_type", "") or ""))

    def _stablekey(r):
        return (_canon_key(r.get("agent", "") or ""),
                _canon_key(r.get("client_name", "") or ""),
                str(r.get("deal_type", "") or ""))

    # מפת "נחתם מהגשר" — לשדרוג שורות אמת שעדיין 'ממתין' אך כבר נחתמו בפועל
    # (הגשר סומן ע"י _recent_signs_mark_signed; בלי זה המיזוג היה מעדיף את שורת
    #  האמת הממתינה וזורק את הגשר החתום → 'ממתין למרות שחתם', תיקון 16/07).
    signed_link = {}
    for (t, r) in keep:
        _lk = str(r.get("commission_pct", "") or "")
        if _lk:
            signed_link[_stablekey(r)] = _lk
            signed_link[_tokkey(r)] = _lk

    out = []
    for r in rows:
        if not str(r.get("commission_pct", "") or ""):   # שורת אמת ממתינה
            _lk = signed_link.get(_stablekey(r)) or signed_link.get(_tokkey(r))
            if _lk:
                r = dict(r)
                r["commission_pct"] = _lk                 # שדרוג ל'נחתם'
        out.append(r)

    seen_tok = set(_tokkey(r) for r in rows)
    seen_stable = set(_stablekey(r) for r in rows)
    # דדופ גם בין רשומות הגשר עצמן (stablekey) — שליחה כפולה/פיצול שיצרו שתי
    # רשומות לאותו סוכן+לקוח+deal_type לא יופיעו פעמיים (כפילות בלעדיות, 19/07).
    extra = []
    added_stable = set()
    for (t, r) in keep:
        sk = _stablekey(r)
        if _tokkey(r) in seen_tok or sk in seen_stable or sk in added_stable:
            continue
        added_stable.add(sk)
        extra.append(r)
    return out + extra

def get_signings(frm="01/01/2020", to="31/12/2099"):
    """חתימות לתקופה. אם יש טאב מלא (ייצוא מהקרם) — הוא הבסיס המדויק, ומוסיפים מהמקור
    האוטומטי (Apps Script) רק חתימות חדשות יותר מההדבקה האחרונה, כך שהדוח תמיד עדכני
    גם בלי הדבקה ידנית כל יום. אם אין טאב מלא — נופלים חזרה למקור האוטומטי בלבד."""
    manual = fetch_signings_from_sheet()
    if manual:
        try:
            auto = web_fetch_raw("חתימות")
        except Exception:
            auto = []
        # מפתח זהות לזיהוי כפילות בין הייצוא מהקרם לבין החתימות הדיגיטליות (סוכן+לקוח+יום).
        # לא משווים לפי חותמת זמן — חתימה דיגיטלית נושאת אזור-זמן ישראל, מה שהיה גורם לה
        # ליפול מתחת לחותמת של רשומות קרם מאותו יום ולהיעלם מהטאב.
        def _sig_day(s):
            e = _excl_epoch(s)
            if not e: return ""
            import datetime as _dt
            try: return _dt.datetime.fromtimestamp(e).strftime("%d/%m/%Y")
            except Exception: return ""
        def _sig_key(g):
            # כולל את תווית ההסכם המנורמלת (_deal_label מנרמל עברית-גיליון ואנגלית-אוטומטי
            # לאותה תווית) — כך שבלעדיות ומכר של אותו נכס/יום נשמרות כשתי חתימות נפרדות,
            # אבל אותה חתימה משני מקורות עדיין מזוהה ככפילות.
            return (_canon_key(g.get("agent", "")), _canon_key(g.get("client_name", "")),
                    _sig_day(g.get("received_at", "")), _deal_label(g.get("deal_type", "")))
        seen = set(_sig_key(g) for g in manual)
        extra = [g for g in auto if _sig_key(g) not in seen]
        allsig = manual + extra
    else:
        allsig = web_fetch_raw("חתימות", frm, to)
    allsig = _recent_signs_merge(allsig)
    allsig = _recent_sign_dels_filter(allsig)
    # שורות זהות לגמרי = כפילות ודאית במקור — מסננים.
    # חשוב: כולל deal_type — נכס אחד מייצר זוג חתימות (OWNER_EXCLUSIVE + OWNER_SALE)
    # עם אותו event_id/לקוח ולעיתים אותה חותמת-זמן; בלי deal_type הבלעדיות נזרקת בטעות.
    _seen_exact = set()
    _dedup = []
    for g in allsig:
        _k = (str(g.get("event_id", "") or ""), str(g.get("received_at", "") or ""),
              _canon_key(g.get("client_name", "")), str(g.get("deal_type", "") or ""))
        if _k in _seen_exact:
            continue
        _seen_exact.add(_k)
        _dedup.append(g)
    allsig = _dedup
    lo = _excl_epoch(frm); hi = _excl_epoch(to) + 86399
    out = []
    for g in allsig:
        e = _excl_epoch(g.get("received_at", ""))
        if e and lo <= e <= hi:
            out.append(g)
    return out
def normalize_city(city: str) -> str:
    if not city:
        return ""
    c = city.strip().replace("קריית", "קרית")
    return re.sub(r"\s+", " ", c)
# שכונות "הקריות" של חיפה שרשומות בגיליון תחת עיר="חיפה" (05/08: "הנוטר 28" נעלם
# מחיפוש "קרית חיים" כי המפענח הוציא אותה כעיר ופילטר העיר פסל) — חיפוש בשם
# השכונה תופס גם עיר="חיפה", בניקוד נמוך מעט מהתאמת עיר מפורשת.
HAIFA_KRAYOT_NEIGHBORHOODS = {"קרית חיים", "קרית חיים מזרחית", "קרית חיים מערבית", "קרית שמואל"}
def parse_price(s: str) -> int:
    if not s:
        return 0
    digits = re.sub(r"[^\d]", "", str(s))
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0
def score_match(row: dict, query: dict, flex_level: int = 0) -> int:
    score = 0
    deal_type = (row.get("סוג עסקה", "") or "").strip()
    want_deal = query.get("deal_type", "מכירה") or "מכירה"
    if deal_type and deal_type != want_deal:
        return 0
    floor_max = query.get("floor_max")
    if floor_max:
        r_floor_raw = (row.get("קומה", "") or "").strip()
        try:
            r_floor = int(float(r_floor_raw)) if r_floor_raw else None
            if r_floor is not None and r_floor > floor_max:
                return 0   # "עד קומה X" — סינון קשיח, מעל הקומה לא תואם
        except ValueError:
            pass
    r_city = normalize_city(row.get("עיר / ישוב", "") or "")
    q_cities_raw = query.get("cities") or []
    q_city_single = normalize_city(query.get("city", "") or "")
    if q_cities_raw and isinstance(q_cities_raw, list):
        q_cities = [normalize_city(c) for c in q_cities_raw if c]
    elif q_city_single:
        q_cities = [q_city_single]
    else:
        q_cities = []
    implied_neigh = ""   # שכונת-קריות שחיפשו כ"עיר" — תוזן לניקוד השכונה למטה
    if q_cities:
        matched_city = False
        for qc in q_cities:
            if r_city == qc:
                score += 30
                matched_city = True
                break
            elif r_city and (r_city in qc or qc in r_city):
                score += 18
                matched_city = True
                break
            elif qc in HAIFA_KRAYOT_NEIGHBORHOODS and r_city == "חיפה":
                # מיפוי עיר↔שכונה: הנכס רשום עיר="חיפה" והחיפוש הוא שכונת-קריות שלה
                score += 22
                matched_city = True
                implied_neigh = qc
                break
        if not matched_city:
            return 0
    else:
        score += 5
    # ── שכונה — חובה ב-flex 0 ו-1, בונוס/קנס ב-flex 2 ──
    q_neighs_raw = query.get("neighborhoods") or []
    if not (isinstance(q_neighs_raw, list) and q_neighs_raw):
        _qn = (query.get("neighborhood") or "").strip()
        q_neighs_raw = [_qn] if _qn else []
    q_neighs = [str(n).strip() for n in q_neighs_raw if str(n).strip()]
    if not q_neighs and implied_neigh:
        # החיפוש "קרית חיים" בלי שכונה מפורשת — השכונה המשתמעת עוברת את אותו ניקוד:
        # שכונה תואמת +30, אין-נתון-שכונה +6, שכונת-חיפה אחרת → כלל ה-±10% הקיים
        q_neighs = [implied_neigh]
    if q_neighs:
        r_neigh = (row.get("שכונה", "") or "").strip()
        r_addr_n = (row.get("כתובת", "") or "").strip()
        hit_nb = False
        for qn in q_neighs:
            # התאמה גם אם השכונה מופיעה רק בכתובת (עמודת "שכונה" לרוב ריקה)
            if (r_neigh and (qn in r_neigh or (len(r_neigh) >= 2 and r_neigh in qn))) or (qn in r_addr_n):
                hit_nb = True; break
        if hit_nb:
            score += 30
        elif not r_neigh:
            # אין נתון שכונה בגיליון (העמודה לרוב ריקה) והעיר כבר תאמה — לא פוסלים
            # (05/08: "הנוטר" נעלם מחיפוש "מזרחית" כי אין לו שכונה רשומה), רק בלי הבונוס
            score += 6
        else:
            # שכונה אחרת מפורשת (05/08): מוצגת רק כשהמחיר צמוד לתקציב — ±10%
            # מהתקרה — קרבת-תקציב מצדיקה להציע חציית שכונה; אחרת מחוץ לחיפוש
            _bm2 = query.get("budget_max")
            _pr2 = parse_price(row.get("מחיר", ""))
            if not (_bm2 and _pr2 and abs(_pr2 - _bm2) / _bm2 <= 0.10):
                return 0
            score -= 6   # נכנס, אבל תמיד אחרי נכסי השכונה המבוקשת
    q_street = (query.get("street") or "").strip()
    r_street = (row.get("כתובת", "") or "").strip()
    if q_street and r_street:
        if q_street in r_street or r_street in q_street:
            score += 25
    q_bmax = query.get("budget_max")
    q_bmin = query.get("budget_min")
    r_price = parse_price(row.get("מחיר", ""))
    if q_bmax and r_price:
        if flex_level == 0:
            max_allowed = q_bmax * 1.10
        elif flex_level == 1:
            max_allowed = q_bmax * 1.20
        else:
            max_allowed = q_bmax * 1.35
        if r_price > max_allowed:
            return 0
        if q_bmin and r_price < q_bmin * 0.7:
            return 0
        diff_pct = abs(r_price - q_bmax) / q_bmax
        if q_bmin:
            if diff_pct < 0.05:
                score += 25
            elif diff_pct < 0.10:
                score += 20
            elif diff_pct < 0.20:
                score += 15
            else:
                score += 8
        else:
            # רק תקרה ("עד X") — הקרוב לתקציב מדורג ראשון (בקשת אייל 05/08): רציף עד +40,
            # ונכס מתחת ל-55% מהתקציב = ליגת-מחיר אחרת, סופג קנס (מוצג, אבל בתחתית)
            score += max(0, 40 - int(diff_pct * 80))
            if r_price < q_bmax * 0.55:
                score -= 18
    q_rmin = query.get("rooms_min")
    q_rmax = query.get("rooms_max")
    r_rooms_raw = (row.get("חדרים", "") or "").strip()
    try:
        r_rooms = float(r_rooms_raw) if r_rooms_raw else None
    except ValueError:
        r_rooms = None
    if r_rooms is not None and (q_rmin or q_rmax):
        flex = 0.5 if flex_level == 1 else (1.0 if flex_level == 2 else 0)
        rmin_eff = (q_rmin - flex) if q_rmin else None
        rmax_eff = (q_rmax + flex) if q_rmax else None
        in_range = True
        if rmin_eff is not None and r_rooms < rmin_eff:
            in_range = False
        if rmax_eff is not None and r_rooms > rmax_eff:
            in_range = False
        exact_n = bool(q_rmin and q_rmax and q_rmin == q_rmax)
        if in_range:
            if exact_n and r_rooms == q_rmin:
                score += 20
            else:
                score += 12
        elif exact_n and q_rmax < r_rooms <= q_rmax + 2:
            # חיפוש "N חדרים" בדיוק (לא "עד N" ולא טווח): דירה גדולה יותר עד +2 חד'
            # רלוונטית לקונה — לא נפסלת ב-flex 0, רק מדורגת מתחת להתאמות המדויקות
            # (05/08: הנוטר 28, 6.5 חד' מול חיפוש 5, נעלם — flex 0 פסל וסולם ה-flex
            # עצר מוקדם כי כבר היו >=3 תוצאות)
            score += max(0, 10 - int((r_rooms - q_rmax) * 4))
        elif flex_level == 0:
            return 0
    q_smin = query.get("size_min")
    q_smax = query.get("size_max")
    r_size_raw = (row.get('מ"ר', "") or row.get("מ״ר", "") or "").strip()
    try:
        r_size = int(float(r_size_raw)) if r_size_raw else None
    except ValueError:
        r_size = None
    if r_size and (q_smin or q_smax):
        if q_smin and r_size >= q_smin:
            score += 8
        if q_smax and r_size <= q_smax:
            score += 8
    q_ptype = (query.get("property_type") or "").strip()
    r_ptype = (row.get("סוג נכס", "") or "").strip()
    PENTHOUSE_TYPES = {"פנטהאוז", "גג", "מיני פנטהאוז"}
    if q_ptype == "דירת גן":
        # סינון קשיח: רק דירת גן/קרקע/קוטג'/מיני קוטג'/דו משפחתי או קומה 0
        r_floor_g = (row.get("קומה", "") or "").strip()
        ground0 = False
        try: ground0 = (r_floor_g != "" and int(float(r_floor_g)) == 0)
        except ValueError: pass
        if any(t in r_ptype for t in ("גן", "גינה", "קרקע", "קוטג", "דו משפח")) or ground0:
            score += 30
        else:
            return 0
    elif q_ptype == "דירה":
        # דירה רגילה (ברירת מחדל) — לא מסננים בקשיחות; רק פנטהאוז לא מתאים
        if r_ptype in PENTHOUSE_TYPES:
            return 0
        if q_ptype == r_ptype: score += 15
        elif r_ptype and (q_ptype in r_ptype or r_ptype in q_ptype): score += 7
    elif q_ptype:
        # סוג ספציפי (פנטהאוז/קוטג'/דופלקס/וילה) — סינון קשיח: רק הסוג המבוקש
        if r_ptype and (q_ptype == r_ptype or q_ptype in r_ptype or r_ptype in q_ptype):
            score += 15
        else:
            return 0
    must_have = query.get("must_have") or []
    if isinstance(must_have, list) and must_have:
        col_map = {
            "מעלית": "מעלית",
            "חנייה": "חנייה",
            'ממ"ד': 'ממ״ד',
            'ממ״ד': 'ממ״ד',
            "מרפסת": "מרפסת",
            "גישה לנכים": "גישה לנכים",
        }
        missing_features = 0
        garden_only = True
        for feature in must_have:
            feature_clean = feature.strip()
            if feature_clean == "גינה":
                # רך — לא מסנן (מציג את כל הנכסים בשכונה); גן/גינה/קרקע/קוטג'/קומה 0 מקבלים בונוס דירוג
                pv = (row.get("סוג נכס", "") or "").strip()
                fr2 = (row.get("קומה", "") or "").strip()
                g0 = False
                try: g0 = (fr2 != "" and int(float(fr2)) == 0)
                except ValueError: pass
                if any(t in pv for t in ("גן", "גינה", "קרקע", "קוטג", "דו משפח")) or g0:
                    score += 20
                continue
            garden_only = False
            col = col_map.get(feature_clean, feature_clean)
            val = (row.get(col, "") or "").strip()
            has_feature = val and val not in ("ללא", "לא", "", "0", "אין")
            if has_feature:
                score += 10
            else:
                missing_features += 1
                if flex_level <= 1:
                    return 0
                score -= 15
        if flex_level == 2 and not garden_only and missing_features == len([f for f in must_have if f.strip() != "גינה"]):
            return 0
    return max(0, score)
def search_listings_in_sheet(query: dict) -> list:
    rows = fetch_sheet_rows()
    if not rows:
        return []
    _has_nb = bool((query.get("neighborhoods")) or (query.get("neighborhood") or "").strip())
    cap = 40 if _has_nb else 25   # תקרת תוצאות
    for flex in [0, 1, 2]:
        scored = []
        for row in rows:
            s = score_match(row, query, flex_level=flex)
            if s > 0:
                scored.append((s, row, flex))
        scored.sort(key=lambda x: -x[0])
        if len(scored) >= 3 or flex == 2:
            return [(s, r, f) for (s, r, f) in scored[:cap]]
    return []
def format_match_reply(query: dict, matches: list) -> str:
    if not matches:
        return ("\U0001f50d חיפשתי במאגר הנכסים ולא מצאתי נכס מתאים כרגע.\n\n"
                "טיפים:\n"
                "• נסה לציין רק עיר ומספר חדרים\n"
                "• הרחב את טווח התקציב\n"
                "• דוגמה: \"מחפש דירה 4 חדרים בקרית ביאליק עד 2 מיליון\"")
    summary = query.get("summary_he", "")
    # ── בדיקה: האם התוצאות באמת בשכונה שביקשו? ──
    q_neigh = (query.get("neighborhood") or "").strip()
    neighborhood_mismatch = False
    if q_neigh:
        match_in_neigh = 0
        for _, row, _ in matches:
            r_neigh = (row.get("שכונה", "") or "").strip()
            if r_neigh and (q_neigh in r_neigh or r_neigh in q_neigh):
                match_in_neigh += 1
        if match_in_neigh == 0:
            neighborhood_mismatch = True
    lines = [f"\U0001f3e0 *מצאתי {len(matches)} נכסים מתאימים!*"]
    if summary:
        lines.append(f"_{summary}_")
    if neighborhood_mismatch:
        lines.append(f"⚠️ לא מצאתי דירות בשכונת *{q_neigh}*. הנה דירות באזורים סמוכים:")
    lines.append("")
    for i, (score, row, flex) in enumerate(matches, 1):
        city      = (row.get("עיר / ישוב", "") or "").strip()
        neigh     = (row.get("שכונה", "") or "").strip()
        street    = (row.get("כתובת", "") or "").strip()
        number    = (row.get("מספר בית", "") or "").strip()
        rooms     = (row.get("חדרים", "") or "").strip()
        size      = (row.get('מ"ר', "") or row.get("מ״ר", "") or "").strip()
        floor     = (row.get("קומה", "") or "").strip()
        total_floors = (row.get("מספר קומות", "") or "").strip()
        price_raw = (row.get("מחיר", "") or "").strip()
        prop_type = (row.get("סוג נכס", "") or "").strip()
        agent_name  = (row.get("סוכן 1", "") or "").strip()
        agent_phone = (row.get("טלפון 1", "") or "").strip()
        match_pct = min(100, int(score))
        badge = "\U0001f7e2 התאמה מצוינת" if score >= 70 else ("\U0001f7e1 התאמה טובה" if score >= 50 else "\U0001f7e0 התאמה חלקית")
        address_full = f"{street} {number}".strip()
        location = address_full
        if neigh:
            location += f" — {neigh}"
        if city:
            location += f", {city}"
        lines.append(f"*{i}. {prop_type or 'נכס'}* — {match_pct}% {badge}")
        lines.append(f"   \U0001f4cd {location}")
        details = []
        if rooms: details.append(f"{rooms} חדרים")
        if size: details.append(f"{size} מ\"ר")
        if floor and total_floors and floor != "0":
            details.append(f"קומה {floor}/{total_floors}")
        if details:
            lines.append("   " + " | ".join(details))
        if price_raw:
            lines.append(f"   \U0001f4b0 {price_raw}")
        features = []
        if (row.get("חנייה", "") or "").strip() == "כן": features.append("חנייה")
        if (row.get("מעלית", "") or "").strip() == "כן": features.append("מעלית")
        if (row.get("מרפסת", "") or "").strip() == "כן": features.append("מרפסת")
        if (row.get("מ״ד", "") or "").strip() == "כן": features.append('ממ"ד')
        if features:
            lines.append(f"   ✨ {' • '.join(features)}")
        if agent_name:
            lines.append(f"   \U0001f464 סוכן: *{agent_name}*")
        agents_phones = fetch_agents_phones()
        real_phone = agents_phones.get(agent_name, agent_phone)
        if real_phone:
            wa_clean = re.sub(r"[^\d]", "", real_phone)
            if wa_clean and not wa_clean.startswith("972"):
                wa_clean = "972" + wa_clean.lstrip("0")
            lines.append(f"   \U0001f4f2 https://wa.me/{wa_clean}")
        lines.append("")
    lines.append("━" * 9)
    lines.append("\U0001f4a1 לחץ על קישור ה-WhatsApp לקבלת פרטים מהסוכן")
    return "\n".join(lines)
def handle_search_request(sender_phone: str, message_text: str):
    try:
        send_text(sender_phone, "🔍 מחפש נכסים מתאימים במאגר...\nרגע ⏳")
        parsed = parse_search_query(message_text)
        log.info(f"Parsed search: {parsed}")
        if not parsed:
            send_text(sender_phone,
                "❌ לא הצלחתי להבין את הבקשה.\n\n"
                "נסה לכתוב כך:\n"
                "*מחפש דירה 4 חדרים בקרית ביאליק עד 2 מיליון*")
            return
        matches = search_listings_in_sheet(parsed)
        log.info(f"Found {len(matches)} matches")
        reply = format_match_reply(parsed, matches)
        send_text(sender_phone, reply)
    except Exception as e:
        log.error(f"Search handler error: {e}", exc_info=True)
        send_text(sender_phone, f"❌ שגיאה: {str(e)[:100]}")
def is_search_query(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if t.startswith("אני "):
        t = t[4:].strip()
    pattern = r'^מחפש[ת]?\s+דיר[הת]\b'
    return bool(re.match(pattern, t))
# ══════════════════════════════════════════════════════════════════════════════
# BUYER SEARCH — מציאת קונים תואמים בשיחות (סוכן מחפש קונה)
# ══════════════════════════════════════════════════════════════════════════════
def normalize_phone_simple(p: str) -> str:
    """0522575747 / 972522575747 / 052-2575747 → 522575747"""
    digits = re.sub(r"\D", "", str(p or ""))
    if digits.startswith("972"): digits = digits[3:]
    if digits.startswith("0"):   digits = digits[1:]
    return digits
def fetch_calls_for_agent(agent_phone: str) -> list:
    """קרא שיחות מ-Apps Script (cache 5 דקות), סנן רק ANSWER של הסוכן הזה"""
    if not APPS_SCRIPT_URL or not APPS_SCRIPT_TOKEN:
        log.error("APPS_SCRIPT_URL or APPS_SCRIPT_TOKEN missing in env")
        return []
    if _buyer_calls_cache["data"] is not None and (time.time() - _buyer_calls_cache["ts"]) < 300:
        all_rows = _buyer_calls_cache["data"]
    else:
        try:
            from urllib.parse import quote
            url = (f"{APPS_SCRIPT_URL}?action=raw&type={quote('שיחות')}"
                   f"&from=01/01/2020&to=31/12/2099&token={APPS_SCRIPT_TOKEN}")
            r = requests.get(url, timeout=30, allow_redirects=True)
            if r.status_code != 200:
                log.error(f"Apps Script error {r.status_code}: {r.text[:200]}")
                return []
            all_rows = r.json().get("rows", [])
            _buyer_calls_cache["data"] = all_rows
            _buyer_calls_cache["ts"] = time.time()
            log.info(f"Loaded {len(all_rows)} call rows from Apps Script")
        except Exception as e:
            log.error(f"Fetch calls error: {e}")
            return []
    norm = normalize_phone_simple(agent_phone)
    filtered = []
    for row in all_rows:
        if str(row.get("status", "")).upper() != "ANSWER":
            continue
        if normalize_phone_simple(str(row.get("agent_phone", ""))) != norm:
            continue
        filtered.append(row)
    return filtered
def parse_buyer_search_query(text: str) -> dict:
    """חלץ מילות מפתח + תקציב מבקשת החיפוש של הסוכן"""
    cleaned = re.sub(r"^(אני\s+)?(מחפש|מחפשת)\s+קונה\s*", "", text.strip()).strip()
    if not cleaned:
        return {"query_text": "", "keywords": [], "summary_he": "כל הקונים האחרונים שלך", "budget": None}
    prompt = f"""אתה עוזר לסוכן נדל"ן ברימקס שמחפש קונה במאגר השיחות שלו.
הסוכן ביקש: "{cleaned}"
חלץ JSON בלבד (ללא markdown):
- keywords: רשימת מילות מפתח חשובות בעברית לחיפוש בתמלולי שיחות (לדוגמה: "4 חדרים" → "4 חדרים"; אזור → שם האזור)
- budget: התקציב המבוקש בש"ח כמספר עגול (לדוגמה: "2 מיליון" → 2000000, "1.8 מ" → 1800000, "עד 2.5 מ ש"ח" → 2500000). אם לא צוין — null.
- summary_he: סיכום קצר בעברית (משפט אחד) של מה הסוכן מחפש"""
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"anthropic-version":"2023-06-01","x-api-key":CLAUDE_API_KEY,"content-type":"application/json"},
            json={"model":"claude-sonnet-4-5","max_tokens":400,
                  "messages":[{"role":"user","content":prompt}]}, timeout=15)
        if r.status_code != 200:
            return {"query_text": cleaned, "keywords": cleaned.split(), "summary_he": cleaned, "budget": None}
        out = r.json()["content"][0]["text"].strip()
        out = re.sub(r"```(?:json)?\s*","",out).strip("` \n")
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if m: out = m.group()
        parsed = json.loads(out)
        parsed["query_text"] = cleaned
        if "budget" not in parsed:
            parsed["budget"] = None
        return parsed
    except Exception as e:
        log.error(f"Buyer query parse error: {e}")
        return {"query_text": cleaned, "keywords": cleaned.split(), "summary_he": cleaned, "budget": None}

def extract_budget_from_transcript(transcript: str):
    """חלץ תקציב מתמלול שיחה. מחזיר מספר בש\"ח או None."""
    if not transcript:
        return None
    t = str(transcript)
    # 1. מיליונים: "2 מיליון", "1.8 מליון", "2.5 מ'", "2 מ ש"ח"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:מיליון|מליון|מ['׳`]?\s*(?:ש[\"״']ח|₪)?)", t)
    if m:
        try:
            return int(float(m.group(1).replace(",", ".")) * 1_000_000)
        except: pass
    # 2. מספרים עם פסיקים: "1,800,000 ש"ח"
    m = re.search(r"(\d{1,3}(?:,\d{3})+)\s*(?:ש[\"״']ח|₪|שח)?", t)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except: pass
    # 3. מספר גדול חשוף: "1800000 ש"ח"
    m = re.search(r"\b(\d{6,8})\s*(?:ש[\"״']ח|₪|שח)\b", t)
    if m:
        try:
            return int(m.group(1))
        except: pass
    return None

def format_price_il(n) -> str:
    if not n: return ""
    try:
        return f"{int(n):,} ₪"
    except:
        return str(n)
def _epoch_from_iso(s: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(s).replace("Z","+00:00")).timestamp()
    except:
        return 0
def _fmt_il_dt(s: str) -> str:
    from datetime import datetime, timezone, timedelta
    try:
        d = datetime.fromisoformat(str(s).replace("Z","+00:00"))
        # ערך ללא אזור-זמן נחשב UTC (כך מגיע מהמקור), וממירים לשעון ישראל
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            d = d.astimezone(ZoneInfo("Asia/Jerusalem"))
        except Exception:
            d = d.astimezone(timezone.utc) + timedelta(hours=3)
        return d.strftime("%d/%m/%Y %H:%M")
    except:
        return ""
def _excl_epoch(s) -> float:
    """תאריך → epoch למיון. תומך גם ב-ISO (2026-06-07T03:04:15Z) וגם ב-DD/MM/YYYY [HH:MM[:SS]].
    מחזיר 0 אם לא ניתן לפענח. מבטיח שנכסים חדשים תמיד ממוינים ראשונים גם אם הפורמט משתנה."""
    from datetime import datetime
    s = str(s or "").strip()
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except Exception:
        pass
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mi, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
        try:
            return datetime(y, mo, d, hh, mi, ss).timestamp()
        except Exception:
            return 0.0
    return 0.0

def _is_our_office(o):
    """האם שם המשרד הוא RE/MAX Family (כל הווריאציות)."""
    t = re.sub(r"[\s/\\.\-_'\"׳״]", "", str(o or "").lower())
    rmx = ("remax" in t) or ("רימקס" in t) or ("רמקס" in t)
    fam = ("family" in t) or ("פמילי" in t) or ("פמלי" in t)
    return rmx and fam
def _prop_epoch(row) -> float:
    """תאריך יצירה של נכס מגיליון המשרד → epoch למיון. תומך ב-DD.M.YYYY (18.5.2026),
    DD/MM/YYYY ו-ISO. נכסים חדשים יותר מקבלים ערך גבוה יותר (מיון יורד = החדש ראשון)."""
    from datetime import datetime
    s = str(row.get("תאריך יצירה", "") or "").strip()
    if not s:
        return 0.0
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d).timestamp()
        except Exception:
            return 0.0
    return _excl_epoch(s)
def format_buyer_match_reply(summary: str, matches: list) -> str:
    if not matches:
        return ("🔍 לא מצאתי קונים תואמים בשיחות שלך.\n\n"
                "טיפ: שלח 'מחפש קונה' לבד וקבל את 5 הקונים האחרונים שלך.")
    lines = [f"🏠 *מצאתי {len(matches)} קונים תואמים*"]
    if summary: lines.append(f"_{summary}_")
    lines.append("")
    for i, c in enumerate(matches, 1):
        phone = re.sub(r"\D", "", str(c.get("caller_phone","")))
        date_s = _fmt_il_dt(c.get("received_at",""))
        t = re.sub(r"https?://\S+", "", str(c.get("transcript_summary",""))).strip()
        budget = extract_budget_from_transcript(c.get("transcript_summary",""))
        lines.append(f"*{i}.* 📞 {phone}")
        if date_s: lines.append(f"   📅 {date_s}")
        if budget: lines.append(f"   💰 תקציב: {format_price_il(budget)}")
        if t: lines.append(f"   {t}")
        if phone:
            wa = phone if phone.startswith("972") else "972" + phone.lstrip("0")
            lines.append(f"   📲 https://wa.me/{wa}")
        lines.append("")
    return "\n".join(lines)
def handle_buyer_search_request(sender_phone: str, message_text: str):
    try:
        send_text(sender_phone, "🔍 מחפש קונים מתאימים בשיחות שלך... ⏳")
        parsed = parse_buyer_search_query(message_text)
        log.info(f"Parsed buyer search: {parsed}")
        candidates = fetch_calls_for_agent(sender_phone)
        log.info(f"{len(candidates)} ANSWER calls for {sender_phone}")
        if not candidates:
            send_text(sender_phone,
                "🔍 לא מצאתי שיחות שענית להן.\n\n"
                "אם זו טעות — בדוק שמספר הטלפון שלך מופיע בעמודה agent_phone בגיליון.")
            return

        # סינון לפי תקציב — סנן החוצה קונים עם הפרש >30% מהמבוקש
        target_budget = parsed.get("budget")
        if target_budget:
            filtered = []
            for c in candidates:
                cb = extract_budget_from_transcript(c.get("transcript_summary",""))
                if cb is None:
                    # ללא תקציב ידוע — סנן החוצה (כדי לעמוד בדרישה)
                    continue
                diff_pct = abs(cb - target_budget) / target_budget
                if diff_pct <= 0.30:
                    filtered.append(c)
            log.info(f"Budget filter ±30% of {target_budget}: {len(candidates)} → {len(filtered)}")
            candidates = filtered

        keywords = parsed.get("keywords") or []
        if not keywords:
            candidates.sort(key=lambda c: _epoch_from_iso(c.get("received_at","")), reverse=True)
            matches = candidates[:5]
        else:
            scored = []
            for c in candidates:
                t = str(c.get("transcript_summary","")).lower()
                s = sum(1 for k in keywords if str(k).strip().lower() in t)
                if s > 0: scored.append((s, c))
            scored.sort(key=lambda x: (-x[0], -_epoch_from_iso(x[1].get("received_at",""))))
            matches = [c for _, c in scored[:5]]
            if not matches:
                candidates.sort(key=lambda c: _epoch_from_iso(c.get("received_at","")), reverse=True)
                matches = candidates[:5]
        send_text(sender_phone, format_buyer_match_reply(parsed.get("summary_he",""), matches))
    except Exception as e:
        log.error(f"Buyer search error: {e}", exc_info=True)
        send_text(sender_phone, f"❌ שגיאה: {str(e)[:100]}")
def is_buyer_search_query(text: str) -> bool:
    if not text: return False
    t = text.strip()
    if t.startswith("אני "): t = t[4:].strip()
    return bool(re.match(r'^מחפש[ת]?\s+קונה\b', t))

# ══════════════════════════════════════════════════════════════════════════════
# EXCLUSIVITY SEARCH — חיפוש בלעדויות חיצוניות מלשונית "בלעדויות חיצוניות"
# ══════════════════════════════════════════════════════════════════════════════
_external_excl_cache = {"data": None, "ts": 0}

def fetch_external_exclusives() -> list:
    """קרא בלעדויות חיצוניות מ-Apps Script (cache 5 דקות)"""
    if not APPS_SCRIPT_URL or not APPS_SCRIPT_TOKEN:
        log.error("APPS_SCRIPT_URL or APPS_SCRIPT_TOKEN missing in env")
        return []
    if _external_excl_cache["data"] is not None and (time.time() - _external_excl_cache["ts"]) < _src_ttl(EXCL_SOURCE, 300, 60):
        return _external_excl_cache["data"]
    if EXCL_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            rows = _sbdb.fetch_excl_rows()
            if rows:
                _external_excl_cache["data"] = rows
                _external_excl_cache["ts"] = time.time()
            return rows
        except Exception as _sbe:
            log.error(f"supabase excl read failed — falling back to sheets: {_sbe}")
    try:
        from urllib.parse import quote
        url = (f"{APPS_SCRIPT_URL}?action=raw&type={quote('בלעדויות חיצוניות')}"
               f"&from=01/01/2020&to=31/12/2099&token={APPS_SCRIPT_TOKEN}")
        r = requests.get(url, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            log.error(f"Apps Script error {r.status_code}: {r.text[:200]}")
            return []
        rows = r.json().get("rows", [])
        _external_excl_cache["data"] = rows
        _external_excl_cache["ts"] = time.time()
        log.info(f"Loaded {len(rows)} external exclusives")
        return rows
    except Exception as e:
        log.error(f"Fetch external exclusives error: {e}")
        return []

def parse_exclusivity_search_query(text: str) -> dict:
    """חלץ פרמטרי חיפוש עבור בלעדויות חיצוניות (זהה ל-parse_search_query אבל פשוט יותר)"""
    cleaned = re.sub(r"^(אני\s+)?(מחפש|מחפשת)\s+בלעדיות?\s*", "", text.strip()).strip()
    if not cleaned:
        return {"query_text": "", "keywords": [], "summary_he": "כל הבלעדויות האחרונות", "budget_max": None, "city": None, "neighborhood": None, "rooms": None}
    prompt = f"""אתה עוזר לסוכן נדל"ן ברימקס שמחפש בלעדויות במאגר.
הסוכן ביקש: "{cleaned}"
{_CITY_NB_MAP_HE}
חלץ JSON בלבד (ללא markdown):
- keywords: רשימת מילות מפתח חשובות בעברית לחיפוש בתיאורי נכסים
- city: עיר מנורמלת לפי הרשימה למעלה, או null — אם ציינו עיר אחת
- cities: רשימת ערים (אם ציינו יותר מעיר אחת) — אחרת null
- neighborhood: שכונה מנורמלת לפי הרשימה למעלה (substring לחיפוש), או null — אם ציינו שכונה אחת
- neighborhoods: רשימת שכונות (אם ציינו יותר משכונה אחת) — אחרת null
- rooms: מספר חדרים (מספר עשרוני) או null
- budget_max: תקציב מקסימלי בש"ח כמספר (לדוגמה "עד 2 מיליון" → 2000000), או null
- property_type: סוג נכס מנורמל, או null. קבוצת "גן" — "דירת גן"/"קרקע"/"קומת קרקע"/"קומה 0"/"קוטג'"/"מיני קוטג'" → "דירת גן". אחרת: "פנטהאוז"/"דירה" וכו'
- summary_he: סיכום קצר בעברית של מה הסוכן מחפש"""
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"anthropic-version":"2023-06-01","x-api-key":CLAUDE_API_KEY,"content-type":"application/json"},
            json={"model":"claude-sonnet-4-5","max_tokens":500,
                  "messages":[{"role":"user","content":prompt}]}, timeout=15)
        if r.status_code != 200:
            return {"query_text": cleaned, "keywords": cleaned.split(), "summary_he": cleaned, "budget_max": None, "city": None, "neighborhood": None, "rooms": None}
        out = r.json()["content"][0]["text"].strip()
        out = re.sub(r"```(?:json)?\s*","",out).strip("` \n")
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if m: out = m.group()
        parsed = json.loads(out)
        parsed["query_text"] = cleaned
        return _enforce_ptype(_enforce_nb_city(parsed), cleaned)
    except Exception as e:
        log.error(f"Exclusivity query parse error: {e}")
        return {"query_text": cleaned, "keywords": cleaned.split(), "summary_he": cleaned, "budget_max": None, "city": None, "neighborhood": None, "rooms": None}

def _parse_price_to_int(p: str):
    """'1,800,000 ₪' → 1800000"""
    if not p: return None
    s = re.sub(r"[^\d.]", "", str(p))
    try:
        return int(float(s)) if s else None
    except:
        return None

def score_exclusivity_match(row: dict, query: dict) -> int:
    """דרג נכס: 0=לא רלוונטי, 100=מושלם"""
    score = 0
    street = (row.get("street","") or "")
    dest = (row.get("dest","") or "")
    desti = (row.get("desti","") or "")
    combined = f"{street} {dest} {desti}".lower()

    # עיר — תמיכה בכמה ערים; אם צוינו ערים, חובה התאמה לאחת מהן
    q_cities = query.get("cities") or []
    if not (isinstance(q_cities, list) and q_cities):
        _qc = (query.get("city") or "").strip()
        q_cities = [_qc] if _qc else []
    q_cities = [str(c).strip() for c in q_cities if str(c).strip()]
    if q_cities:
        hit_city = any((c.lower() in combined) or (c.replace("קרית","קריית").lower() in combined) for c in q_cities)
        if hit_city:
            score += 30
        else:
            return 0

    # שכונה — אם צוינו שכונות, חובה התאמה לאחת מהן (תוצאות רק מהשכונה/ות)
    q_nbs = query.get("neighborhoods") or []
    if not (isinstance(q_nbs, list) and q_nbs):
        _qn = (query.get("neighborhood") or "").strip()
        q_nbs = [_qn] if _qn else []
    q_nbs = [str(n).strip() for n in q_nbs if str(n).strip()]
    if q_nbs:
        if any(n.lower() in combined for n in q_nbs):
            score += 25
        else:
            return 0

    # סוג נכס — סינון קשיח (זיהוי מתוך הטקסט, לשת"פ אין שדה סוג מסודר)
    q_pt = (query.get("property_type") or "").strip()
    if q_pt == "דירת גן":
        # רק ביטויים מפורשים של גן — לא "קרקע" בתוך "תת קרקעית" ולא "גן" בתוך "גני ילדים"
        if not re.search(r"דיר[הת]\s*גן|דירות\s*גן|קומת\s*קרקע|בקרקע|קומה\s*0|קוטג|דו\s*משפח", combined):
            return 0
        score += 20
    elif q_pt in ("פנטהאוז", "גג", "מיני פנטהאוז"):
        if not re.search(r"פנטהאוז|פנטהאוס|גג", combined):
            return 0
        score += 20
    elif q_pt == "קוטג'":
        if "קוטג" not in combined:
            return 0
        score += 20

    # חדרים
    q_rooms = query.get("rooms")
    if q_rooms is not None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*חדרים?", dest)
        if m:
            try:
                r_rooms = float(m.group(1))
                if abs(r_rooms - float(q_rooms)) < 0.6:
                    score += 25
                elif abs(r_rooms - float(q_rooms)) < 1.1:
                    score += 10
                else:
                    return 0
            except: pass

    # תקציב
    q_bmax = query.get("budget_max")
    if q_bmax:
        r_price = _parse_price_to_int(row.get("price",""))
        if r_price:
            if r_price > q_bmax * 1.15:
                return 0
            diff_pct = abs(r_price - q_bmax) / q_bmax
            if diff_pct < 0.05: score += 20
            elif diff_pct < 0.15: score += 12
            else: score += 5

    # מילות מפתח
    keywords = query.get("keywords") or []
    if keywords:
        kw_hits = sum(1 for kw in keywords if str(kw).strip().lower() in combined and len(str(kw).strip()) > 1)
        score += min(kw_hits * 5, 25)

    return score

def format_exclusivity_match_reply(query: dict, matches: list) -> str:
    if not matches:
        return ("🔍 לא מצאתי בלעדויות תואמות במאגר.\n\n"
                "נסה לחפש עם פחות פרטים, או \"מחפש בלעדיות\" לבד לקבלת הבלעדויות האחרונות.")
    summary = query.get("summary_he","")
    lines = [f"🏠 *מצאתי {len(matches)} בלעדויות תואמות*"]
    if summary: lines.append(f"_{summary}_")
    lines.append("")
    for i, m in enumerate(matches, 1):
        street = (m.get("street","") or "").strip()
        dest = (m.get("dest","") or "").strip()
        desti = (m.get("desti","") or "").strip()
        price = (m.get("price","") or "").strip()
        office = (m.get("office","") or "").strip()
        link = (m.get("link","") or "").strip()
        received = (m.get("received_at","") or "").strip()

        lines.append(f"*{i}.* 📍 {street}")
        if dest: lines.append(f"   🏘 {dest}")
        if price: lines.append(f"   💰 {price}")
        if office: lines.append(f"   🏢 {office}")
        if received: lines.append(f"   📅 {received[:10]}")
        if desti: lines.append(f"   📝 {desti}")
        if link: lines.append(f"   🔗 {link}")
        lines.append("")
    return "\n".join(lines)

def handle_exclusivity_search_request(sender_phone: str, message_text: str):
    try:
        send_text(sender_phone, "🔍 מחפש בלעדויות מתאימות במאגר... ⏳")
        parsed = parse_exclusivity_search_query(message_text)
        log.info(f"Parsed exclusivity search: {parsed}")
        all_rows = fetch_external_exclusives()
        if not all_rows:
            send_text(sender_phone, "🔍 אין כרגע בלעדויות במאגר. בדוק שה-MailParser → Sheets פעיל.")
            return

        # אם אין קריטריונים — החזר את 5 האחרונות
        if not (parsed.get("city") or parsed.get("cities") or parsed.get("neighborhood") or parsed.get("neighborhoods") or parsed.get("rooms") or parsed.get("budget_max") or parsed.get("keywords") or parsed.get("property_type")):
            all_rows.sort(key=lambda r: _excl_epoch(r.get("received_at","")), reverse=True)
            matches = all_rows[:5]
        else:
            scored = [(score_exclusivity_match(r, parsed), r) for r in all_rows]
            scored = [(s, r) for s, r in scored if s > 0]
            scored.sort(key=lambda x: (-x[0], -_excl_epoch(x[1].get("received_at",""))))
            matches = [r for _, r in scored[:5]]

        send_text(sender_phone, format_exclusivity_match_reply(parsed, matches))
    except Exception as e:
        log.error(f"Exclusivity search error: {e}", exc_info=True)
        send_text(sender_phone, f"❌ שגיאה: {str(e)[:100]}")

def is_exclusivity_search_query(text: str) -> bool:
    if not text: return False
    t = text.strip()
    if t.startswith("אני "): t = t[4:].strip()
    return bool(re.match(r'^מחפש[ת]?\s+בלעדיות?\b', t))
# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "ok", "message": "RE/MAX Bot Webhook Active"}), 200
    # הבוט הנכנס בוואטסאפ (חיפוש דירה/קונה/בלעדיות + מצגת PDF) הושבת לבקשת המשתמש —
    # Maytapi משמש ליציאה בלבד (תמלול שיחה + חתימות). מתעלמים מכל הודעה נכנסת.
    return jsonify({"ok": True, "message": "inbound disabled"})
    try:
        body = request.get_json(force=True)
        log.info(f"Webhook: {json.dumps(body)[:300]}")
        if body.get("type") in ("ack", "status", "notify", "error"):
            return jsonify({"ok": True})
        msg  = body.get("message", {})
        user_obj = body.get("user") if isinstance(body.get("user"), dict) else {}
        user_phone = user_obj.get("phone", "")
        conversation = body.get("conversation", "")
        if "@lid" in conversation and user_phone:
            from_number = user_phone
        else:
            from_number = (conversation
                           or user_phone
                           or msg.get("from_number", "")
                           or body.get("from", ""))
        if not from_number:
            return jsonify({"ok": True})
        msg_type = msg.get("type", "")
        text     = msg.get("text", "") or msg.get("caption", "") or ""
        media    = msg.get("url", "") or msg.get("media_url", "")
        # ── טריגר חיפוש קונה — "מחפש קונה" / "מחפשת קונה" ──────────────
        if msg_type == "text" and is_buyer_search_query(text):
            threading.Thread(
                target=handle_buyer_search_request,
                args=[from_number, text],
                daemon=True
            ).start()
            return jsonify({"ok": True})

        # ── טריגר חיפוש בלעדויות — "מחפש בלעדיות" / "מחפשת בלעדיות" ─────
        if msg_type == "text" and is_exclusivity_search_query(text):
            threading.Thread(
                target=handle_exclusivity_search_request,
                args=[from_number, text],
                daemon=True
            ).start()
            return jsonify({"ok": True})
        # ── טריגר חיפוש דירה ──
        if msg_type == "text" and is_search_query(text):
            threading.Thread(
                target=handle_search_request,
                args=[from_number, text],
                daemon=True
            ).start()
            return jsonify({"ok": True})
        # ── טריגר מצגת ──
        if msg_type == "text" and TRIGGER_WORD in text:
            body_text = text.replace(TRIGGER_WORD, "").strip()
            sessions[from_number] = {
                "text": body_text,
                "images": [],
                "timer": None,
            }
            send_text(from_number,
                f"✅ קיבלתי! עכשיו שלח את תמונות הנכס (עד 4).\n"
                f"אחרי התמונות — אחפש עסקאות ומידע על השכונה ואשלח מצגת תוך ~90 שניות.")
            return jsonify({"ok": True})
        if from_number in sessions and msg_type in ("image", "media"):
            sessions[from_number]["images"].append({
                "url": media,
                "data": msg.get("data"),
            })
            count = len(sessions[from_number]["images"])
            send_text(from_number, f"📸 קיבלתי תמונה {count}/4")
            if count >= 4:
                threading.Thread(target=process_session, args=[from_number], daemon=True).start()
            else:
                schedule_processing(from_number)
            return jsonify({"ok": True})
        if from_number in sessions and msg_type == "text" and text:
            sessions[from_number]["text"] += "\n" + text
            schedule_processing(from_number)
            return jsonify({"ok": True})
    except Exception as e:
        log.error(f"Webhook error: {e}", exc_info=True)
    return jsonify({"ok": True})
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "trigger": TRIGGER_WORD})
@app.route("/", methods=["GET"])
def index():
    return "RE/MAX Bot 🏠 — Running"
# ══════════════════════════════════════════════════════════════════════════════
# FAMILY BOT — WEB APP LAYER  (אפליקציית web, ללא תלות בוואטסאפ)
# ══════════════════════════════════════════════════════════════════════════════
import secrets as _secrets
from flask import send_file, Response, redirect

# --- Twilio + admin config (env vars) ---
TWILIO_SID   = os.environ.get("TWILIO_SID", "")
TWILIO_AUTH  = os.environ.get("TWILIO_AUTH", "")
TWILIO_FROM  = os.environ.get("TWILIO_FROM", "")           # +972... או MG... (Messaging Service)
# ── ספק SMS חלופי: Maskyoo / sms.deals (חיסכון בעלויות Twilio) ──
SMS_DEALS_TOKEN  = os.environ.get("SMS_DEALS_TOKEN", "").strip()
SMS_DEALS_SENDER = os.environ.get("SMS_DEALS_SENDER", "").strip()
SMS_DEALS_URL    = (os.environ.get("SMS_DEALS_URL", "") or "https://sms.deals/api/ws.php").strip()
# מנהלים קבועים (מוגדרים לפי מספר טלפון) — בנוסף למשתנה הסביבה ADMIN_PHONES אם קיים
_DEFAULT_ADMIN_PHONES = [
    "0546000808",  # אודי שמול
    "0544448065",  # מתן ביטון
    "0525640615",  # אוריין שמול
]
ADMIN_PHONES = _DEFAULT_ADMIN_PHONES + [p.strip() for p in os.environ.get("ADMIN_PHONES", "").split(",") if p.strip()]

# קודי כניסה קבועים שעוקפים את ה-SMS (Twilio) — { 9 ספרות אחרונות של הטלפון: קוד }
# לשימוש אישי בלבד. מי שמכניס מספר+קוד תואמים נכנס בלי SMS.
# קוד כניסה קבוע בוטל (בקשת אייל 13/07) — כולם נכנסים עם קוד SMS. אייל מזוהה כ-admin
# דרך DEV_PHONES ב-web_role_for, כך שאין נעילה. להוסיף חזרה: {"<last9>": "<code>"}.
# חשבון ביקורת App Store: 0501234567 + קוד קבוע — הבודקים של אפל לא מקבלים SMS ישראלי.
# מקבל role=agent בלבד (לא admin — ראה api_auth_verify). להסרה אחרי האישור: לרוקן ל-{}.
_BYPASS_LOGINS = {"501234567": "1905"}

# --- in-memory OTP + sessions ---
_otp_store = {}     # last9 -> {"code","exp","tries"}
_web_sessions = {}  # token -> {"phone","role","name","exp"}
_OTP_TTL  = 300
_SESS_TTL = 6 * 3600

# ── טוקן חתום (stateless) ששורד רסטארט/cold-start של Render ──────────────────────
import hmac as _hmac, hashlib as _hashlib
_SESSION_SECRET = (os.environ.get("SESSION_SECRET") or os.environ.get("APPS_SCRIPT_TOKEN")
                   or "fb-static-session-secret-v1").encode()
def _b64u(b): return base64.urlsafe_b64encode(b).decode().rstrip("=")
def _b64u_dec(s):
    s = str(s) + "=" * (-len(str(s)) % 4)
    return base64.urlsafe_b64decode(s.encode())
def _mint_token(phone, ttl=_SESS_TTL):
    """טוקן חתום: טלפון + תוקף, חתום ב-HMAC. תקף גם אחרי שהשרת התעורר מחדש."""
    exp = int(time.time() + ttl)
    data = _b64u(json.dumps({"p": _last9(phone), "e": exp}).encode())
    sig = _b64u(_hmac.new(_SESSION_SECRET, data.encode(), _hashlib.sha256).digest())
    return data + "." + sig
def _verify_token(tok):
    """מאמת חתימה+תוקף ומחזיר את הטלפון, או None."""
    try:
        data, sig = str(tok).split(".", 1)
        good = _b64u(_hmac.new(_SESSION_SECRET, data.encode(), _hashlib.sha256).digest())
        if not _hmac.compare_digest(sig, good): return None
        obj = json.loads(_b64u_dec(data))
        if int(obj.get("e", 0)) < time.time(): return None
        return _last9(str(obj.get("p", "")))
    except Exception:
        return None
def _session_from_phone(phone):
    """בונה מחדש סשן מהטלפון בלבד (לשחזור אחרי רסטארט) — זהה לכניסה רגילה."""
    phone = _last9(phone)
    scope, drole = _resolve_roles(phone)
    if not scope: scope = "agent"
    if _is_dev(phone): scope = "admin"; drole = "developer"
    name = _login_name(phone, scope, drole)
    sess = {"phone": phone, "role": scope, "drole": drole, "name": name, "exp": time.time() + _SESS_TTL}
    if _is_dev(phone): sess["dev"] = True
    _cc = _coordinators_all()
    if scope == "coordinator" and phone in _cc:
        sess["agents"] = list(_cc[phone]["agents"])
        sess["agent_names"] = list(_cc[phone]["names"])
    return sess

def _last9(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d[-9:]

def _to_e164(last9):
    return "+972" + last9

def _wa_phone(p):
    d = re.sub(r"\D", "", str(p or ""))
    if not d: return ""
    return d if d.startswith("972") else "972" + d.lstrip("0")

def _il_phone(p):
    """מחזיר (תצוגה מקומית 05X..., קישור חיוג +972...)"""
    d = re.sub(r"\D", "", str(p or ""))
    if not d: return ("", "")
    if d.startswith("972"): d = d[3:]
    d = d.lstrip("0")
    return ("0" + d, "+972" + d)

def _norm_name(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def _name_key(s):
    """מפתח השוואה גמיש לשמות — מתעלם מרווחים, יוד/וו כפול, גרשיים ואותיות סופיות.
    משמש *רק* להתאמה (לא לתצוגה), כדי שסוכן יזוהה גם אם נכתב מעט אחר בלשוניות שונות."""
    t = re.sub(r"[֑-ׇ]", "", str(s or ""))   # הסר ניקוד/דגש
    t = re.sub(r"[\s'\"`׳״’.\-_,()\[\]]", "", t)
    for _a, _b in (("ך", "כ"), ("ם", "מ"), ("ן", "נ"), ("ף", "פ"), ("ץ", "צ")):
        t = t.replace(_a, _b)
    return t.replace("יי", "י").replace("וו", "ו")

# ── קונפיג מרכזי + זיהוי מפתח (קונסולת ניהול) ──────────────────────────────────
import json as _json
_DEV_PHONES_RAW = ["0505709865"]  # אייל שמול (מפתח)
DEV_PHONES = set(_last9(p) for p in _DEV_PHONES_RAW
                 + [x.strip() for x in os.environ.get("DEV_PHONES", "").split(",") if x.strip()])
def _is_dev(phone):
    return _last9(phone) in DEV_PHONES

_LAST_GOOD_CONFIG = None   # קונפיג תקין אחרון — מגן מפני דריסה כש-getconfig נכשל זמנית

def _load_config():
    """קונפיג מערכת (dict) מטאב 'config' ב-Apps Script. מטמון 60ש'.
    קריטי: אם getconfig נכשל/לא-ok — לא שומרים {} במטמון (זה גרם בעבר לדריסת הקונפיג
    ומחיקת סוכנים), אלא מחזירים את הקונפיג התקין האחרון כך שכתיבה הבאה לא תמחק נתונים."""
    global _LAST_GOOD_CONFIG
    c = _cache_get("app_config", 60)
    if c is not None: return c
    with _sf_lock("app_config"):
        c = _cache_get("app_config", 60)
        if c is not None: return c
        # מסלול Supabase — קונפיג משורות office_config (מהיר, בלי גוגל)
        if CONFIG_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
            try:
                cfg = _sbdb.fetch_config()
                if isinstance(cfg, dict) and cfg:
                    _LAST_GOOD_CONFIG = cfg
                    _cache_put("app_config", cfg)
                    return cfg
            except Exception as _sbe:
                log.error(f"supabase config read failed — falling back to sheets: {_sbe}")
        j = None
        try:
            j = _buyers_apps_post("getconfig", {})
        except Exception:
            j = None
        if j and j.get("ok"):
            raw = (j.get("config") or "").strip()
            cfg = None
            if raw:
                try: cfg = _json.loads(raw)
                except Exception: cfg = None
            else:
                cfg = {}
            if isinstance(cfg, dict):
                _LAST_GOOD_CONFIG = cfg
                _cache_put("app_config", cfg)
                return cfg
        # נכשל/לא תקין — לא מאחסנים {} (כדי לנסות שוב בפעם הבאה), נופלים לקונפיג התקין האחרון
        if isinstance(_LAST_GOOD_CONFIG, dict):
            return _LAST_GOOD_CONFIG
        return {}

def _save_config(cfg):
    """כתיבת הקונפיג חזרה ל-Apps Script. מעדכן מטמון בהצלחה.
    הגנה: לא כותבים קונפיג שמרוקן את הסוכנים+תפקידים אם קודם היו כאלה (מונע מחיקה בטעות)."""
    global _LAST_GOOD_CONFIG
    if not isinstance(cfg, dict):
        return False
    if isinstance(_LAST_GOOD_CONFIG, dict) and (_LAST_GOOD_CONFIG.get("agents") or _LAST_GOOD_CONFIG.get("roles")):
        if not (cfg.get("agents") or cfg.get("roles")):
            log.error("save_config refused: would wipe agents/roles (likely stale/empty config)")
            return False
    # מסלול Supabase — כותבים רק את המפתחות שהשתנו (שמירה אטומית פר-מפתח,
    # במקום דריסת הבלוב כולו). הגיליון מתעדכן במקביל דרך ה-hook ב-Apps Script.
    if CONFIG_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            prev = _LAST_GOOD_CONFIG if isinstance(_LAST_GOOD_CONFIG, dict) else None
            if prev is None:
                # שמירה ראשונה אחרי אתחול: בלי prev נכתבים *כל* המפתחות — אם הטעינה
                # שביד הייתה ישנה (בזמן דפלוי) זה דורס שינויים טריים (כמו שחזור סוכן).
                # לכן משווים מול קריאה טרייה מהמקור וכותבים רק מה שבאמת השתנה.
                try:
                    prev = _sbdb.fetch_config() or {}
                except Exception:
                    prev = {}
            changed = [k for k in cfg if _json.dumps(cfg.get(k), sort_keys=True, ensure_ascii=False)
                       != _json.dumps(prev.get(k), sort_keys=True, ensure_ascii=False)]
            for k in changed:
                _sbdb.save_config_key(k, cfg[k])
            _LAST_GOOD_CONFIG = cfg
            _cache_put("app_config", cfg)
            _cache_clear("alias_key_map")
            _cache_clear("newborn_delays")
            # שכפול לגיליון — אם נכשל, הסנכרון גיליון→Supabase עלול להחזיר מצב ישן; חייבים לוג
            try:
                _bj = _buyers_apps_post("setconfig", {"config": _json.dumps(cfg, ensure_ascii=False)})
                if not (_bj and _bj.get("ok")):
                    log.error(f"config sheet backup failed (sync may resurrect stale state): {str(_bj)[:200]}")
            except Exception as _be:
                log.error(f"config sheet backup exception: {_be}")
            return True
        except Exception as _sbe:
            log.error(f"supabase config save failed — falling back to sheets: {_sbe}")
    try:
        j = _buyers_apps_post("setconfig", {"config": _json.dumps(cfg, ensure_ascii=False)})
        ok = bool(j and j.get("ok"))
        if ok:
            _LAST_GOOD_CONFIG = cfg
            _cache_put("app_config", cfg)
            _cache_clear("alias_key_map")
            _cache_clear("newborn_delays")
        return ok
    except Exception:
        return False

# ── שינוי קונפיג בטוח (RMW) — מונע דריסת סוכן מוזמן ──────────────────────────────
# הבאג: כל שינוי לרשימת האנשים עשה _load_config()→שינוי→_save_config() בלי נעילה,
# ו-_mark_joined רץ ב-thread רקע בכל כניסה ועושה בדיוק את זה. סוכן שהוזמן נדרס כש-
# thread רקע קרא קונפיג-רגע-לפני ושמר אותו בחזרה. תיקון: נעילה גלובלית + קריאה
# טרייה מהמקור בתוך הנעילה + מוטציה על עותק (כדי שה-diff של _save_config במצב
# Supabase יזהה שינוי ויכתוב לדיסק — מוטציה במקום על אותו object נבלעה).
_cfg_mut_lock = _threading.Lock()
def _config_mutate(fn):
    """RMW אטומי של הקונפיג. fn(cfg) משנה את cfg במקום (ויכול להחזיר ערך).
    מחזיר (ok, ערך-שהוחזר-מ-fn). שתי כתיבות בו-זמנית מסתדרות בתור, כל אחת רואה
    את תוצאת קודמתה."""
    import copy as _copy
    with _cfg_mut_lock:
        _cache_clear("app_config")          # כפה קריאה טרייה מהמקור (לא מהקאש)
        base = _load_config()               # base נשמר כ-_LAST_GOOD_CONFIG (טרי)
        cfg = _copy.deepcopy(base)          # מוטציה על עותק → ה-diff יזהה שינוי אמיתי
        res = fn(cfg)
        ok = _save_config(cfg)
        return ok, res

def _suspended_set():
    """קבוצת טלפונים (9 ספרות) של סוכנים מושהים — חוסם SMS וכניסה (חיסכון בטווילו)."""
    try:
        return set(_last9(p) for p in (_load_config().get("suspended") or []) if p)
    except Exception:
        return set()
def _is_suspended(last9):
    return _last9(last9) in _suspended_set()

def _alias_key_map():
    """name_key(שם או כינוי) -> name_key קנוני של הסוכן. מאפשר זיהוי גם באיות חלופי."""
    c = _cache_get("alias_key_map", 60)
    if c is not None: return c
    m = {}
    for ag in (_load_config().get("agents") or []):
        ck = _name_key(ag.get("name", ""))
        if not ck: continue
        m[ck] = ck
        for al in (ag.get("aliases") or []):
            ak = _name_key(al)
            if ak: m[ak] = ck
    _cache_put("alias_key_map", m)
    return m

def _alias_name_map():
    """name_key(שם/כינוי) -> השם הקנוני המלא של הסוכן (בן → בן קדוש)."""
    c = _cache_get("alias_name_map", 60)
    if c is not None: return c
    m = {}
    for ag in (_load_config().get("agents") or []):
        nm = (ag.get("name", "") or "").strip()
        ck = _name_key(nm)
        if not ck: continue
        m[ck] = nm
        for al in (ag.get("aliases") or []):
            ak = _name_key(al)
            if ak: m[ak] = nm
    _cache_put("alias_name_map", m)
    return m

def _canon_agent_name(name):
    """השם הקנוני המלא לתצוגה — ממפה כינוי (בן) לשם מלא (בן קדוש); אחרת מחזיר כמו שהוא."""
    nm = (name or "").strip()
    return _alias_name_map().get(_name_key(nm), nm) if nm else nm

def _canon_key(name):
    """מפתח התאמה קנוני: name_key אחרי מיפוי כינויים (אם הוגדרו בקונפיג)."""
    k = _name_key(name)
    return _alias_key_map().get(k, k)

# ── תפקידים (6) → היקף נתונים + טאבים. קונפיג ריק = התנהגות נוכחית מדויקת. ──────
_ROLE_SCOPE = {"developer": "admin", "manager": "admin", "accountant": "admin",
               "secretary": "admin", "coordinator": "coordinator", "agent": "agent"}
_ALL_TABS = ["calls", "buyers", "sigs", "props", "excl", "newborn", "report", "activity"]

# מנהלים עם השהיית צפייה בשיחות (לפי שם) — רואים הכל מיד, אבל שיחות רק אחרי X ימים, ו"נכס נולד" לא מיידי.
# ריק — אווה אזולאי שוחררה להתנהג כסוכנת רגילה (בקשת אייל 13/07). להחזרת מנהל-מושהה: להוסיף שם/טלפון.
_DELAYED_ADMINS = {}          # שם → ימי השהיה לשיחות
_DELAYED_ADMIN_PHONES = {}    # טלפון (9 ספרות) → ימי השהיה (אמין יותר מהשם)
def _delayed_admin_days(name=None, phone=None):
    if NEWBORN_DELAYS_DISABLED: return 0   # השהיות מבוטלות — אף מנהל אינו מושהה
    if phone:
        d = _DELAYED_ADMIN_PHONES.get(_last9(phone))
        if d:
            try: return int(d)
            except Exception: pass
    ck = _canon_key(name or "")
    if ck:
        for nm, days in _DELAYED_ADMINS.items():
            if _canon_key(nm) == ck:
                try: return int(days)
                except Exception: return 0
    return 0
def _name_for_phone(last9):
    return (web_phone_name_map().get(last9) or web_contacts_phone_name().get(last9)
            or _config_agent_phones().get(last9) or "")

def _resolve_roles(last9):
    """מחזיר (scope_role, display_role). scope ל-data (admin/coordinator/agent), display ל-UI/טאבים.
    אם אין תפקיד בקונפיג — נופל בדיוק להתנהגות הקיימת (web_role_for)."""
    disp = (_load_config().get("roles") or {}).get(last9)
    if disp in _ROLE_SCOPE:
        return _ROLE_SCOPE[disp], disp
    # מנהל מושהה לפי טלפון/שם (כמו אווה אזולאי) — סקופ מנהל מלא
    try:
        if _delayed_admin_days(_name_for_phone(last9), last9) > 0:
            return "admin", "manager"
    except Exception:
        pass
    base = web_role_for(last9) or "agent"
    return base, {"admin": "manager", "coordinator": "coordinator", "agent": "agent"}.get(base, "agent")

def _tabs_for_role(drole):
    """רשימת הטאבים הגלויים לתפקיד. ללא הגדרה בקונפיג = כל הטאבים (אפס שינוי)."""
    perms = (_load_config().get("rolePerms") or {}).get(drole)
    if perms and isinstance(perms.get("tabs"), list):
        return [t for t in perms["tabs"] if t in _ALL_TABS]
    return list(_ALL_TABS)

def _login_name(phone, scope, drole):
    _cc = _coordinators_all()
    if drole == "coordinator" and phone in _cc:
        return _cc[phone]["name"]
    if scope == "admin" and drole in ("manager", "developer"):
        return "מנהל"
    return (web_contacts_phone_name().get(phone) or web_phone_name_map().get(phone)
            or _config_agent_phones().get(phone) or ("מנהל" if scope == "admin" else "סוכן"))

def _team_for(name):
    """צוות הסוכן: (phones:set, keys:set) של כל החברים כולל עצמו. None אם אין צוות.
    אדיטיבי והדדי — מאחד את כל הצוותים שהסוכן חבר בהם (לא רק הראשון),
    כך שאם סוכן מופיע בכמה צוותים הוא מקושר לכולם וכל החברים רואים זה את זה."""
    ck = _canon_key(name)
    if not ck: return None
    phones = set(); keys = set(); found = False
    for grp in (_load_config().get("teams") or []):
        if not isinstance(grp, list): continue
        gkeys = set(_canon_key(m) for m in grp if m)
        if ck in gkeys:
            found = True
            for m in grp:
                k = _canon_key(m)
                if k: keys.add(k)
                for ph in _phones_for_name(m):
                    if ph: phones.add(ph)
    keys.discard("")
    return (phones, keys) if found else None

def _row_owned(row, keys, phones):
    """האם שורת נכס שייכת לאחד מחברי הצוות (שם קנוני או טלפון)."""
    for col in ("סוכן 1", "סוכן 2"):
        if _canon_key(row.get(col, "")) in keys: return True
    if phones:
        for col in ("טלפון 1", "טלפון 2", "טלפון"):
            ph = _last9(row.get(col, ""))
            if ph and ph in phones: return True
    return False

def _scope_keys_phones(role, name, own_phones, agents=None, agent_names=None):
    """מחזיר (keys:set, phones:set, multi:bool) לסינון נכסים/קונים.
    - מתאמת: כל הסוכנים שלה (חד-כיווני) — הסוכנים עצמם אינם מקבלים את הצוות הזה.
    - צוות (קונפיג teams): הדדי — כל חברי הצוות.
    - יחיד: רק הסוכן עצמו.
    multi=True כשהתצוגה כוללת כמה סוכנים (כדי להציג את שם הסוכן על כל כרטיס)."""
    keys = set(); phones = set(_last9(p) for p in (own_phones or set()) if _last9(p))
    nk = _canon_key(name)
    if nk: keys.add(nk)
    # מתאמת — רואה את כל הסוכנים שלה (לא הדדי בין הסוכנים)
    if role == "coordinator":
        for a in (agents or []):
            aa = _last9(a)
            if aa: phones.add(aa)
            k = _canon_key(web_phone_name_map().get(aa, ""))
            if k: keys.add(k)
        for nm in (agent_names or []):
            k = _canon_key(nm)
            if k: keys.add(k)
        keys.discard("")
        return keys, phones, True
    # צוות הדדי
    t = _team_for(name)
    if t:
        tphones, tkeys = t
        keys |= tkeys; phones |= tphones
        keys.discard("")
        return keys, phones, True
    keys.discard("")
    return keys, phones, False

def _valid_il_id(idnum):
    """בדיקת תקינות תעודת זהות ישראלית (ספרת ביקורת לפי התקן)."""
    s = re.sub(r"\D", "", str(idnum or ""))
    if not s or len(s) > 9:
        return False
    s = s.zfill(9)
    total = 0
    for i, ch in enumerate(s):
        d = int(ch) * (1 if i % 2 == 0 else 2)
        total += d if d < 10 else d - 9
    return total % 10 == 0

def _vphone_for_name(name):
    """מספר וירטואלי של סוכן — חיפוש גמיש (גם אם השם כתוב מעט אחר בלשוניות שונות)."""
    vm = fetch_agent_virtual_phones()
    v = vm.get(_norm_name(name))
    if v: return v
    ck = _canon_key(name)
    for nm, vp in vm.items():
        if _canon_key(nm) == ck: return vp
    return ""

def _deal_label(code):
    c = str(code or "").upper()
    if "OWNER_EXCLUSIVE" in c: return "בלעדיות"
    if "CLIENT_SALE" in c:     return "קונים"
    if "OWNER_RENT" in c or "CLIENT_RENT" in c: return "שכירות"
    if "OWNER_SALE" in c:      return "מוכר"
    return code or "חתימה"

def _web_valid_pct(v):
    if v is None or v == "": return None
    if isinstance(v, str) and re.search(r"https?://", v): return None
    try: return float(v)
    except: return None

def _sms_local_il(last9):
    """ממיר מזהה טלפון לפורמט מקומי ישראלי 05xxxxxxxx (Maskyoo דורש מקומי, לא +972)."""
    d = re.sub(r"\D", "", str(last9 or ""))
    if d.startswith("972"): d = d[3:]
    d = d.lstrip("0")[-9:]
    return ("0" + d) if d else ""

def _send_sms_dealsmaskyoo(last9, body):
    """שליחה דרך sms.deals (Maskyoo). מחזיר True/False אם נשלח,
    או None אם הספק לא מוגדר — אז web_send_sms נופלת חזרה ל-Twilio."""
    if not (SMS_DEALS_TOKEN and SMS_DEALS_SENDER):
        return None
    dest = _sms_local_il(last9)
    if not dest:
        log.error("sms.deals: invalid destination")
        return False
    # הטוקן נשלח גם כפרמטר בכתובת וגם ב-Bearer header — בדיוק כמו בדוגמת ה-PHP הרשמית של Maskyoo
    params  = {"service": "send_sms", "dest": dest, "sender": SMS_DEALS_SENDER, "message": body, "token": SMS_DEALS_TOKEN}
    headers = {"Authorization": "Bearer " + SMS_DEALS_TOKEN}
    try:
        r = requests.get(SMS_DEALS_URL, params=params, headers=headers, timeout=15)
        if r.status_code >= 300:
            log.error(f"sms.deals HTTP {r.status_code}: {r.text[:300]}")
            return False
        low = (r.text or "").lower()
        # הצלחה לפי סמן מובהק (Message_id / Message in Action) — לא לפי היעדר 'error'
        # (תשובת הצלחה עלולה להכיל שדה כמו Error:0 וגרמה לסימון כשל שגוי).
        if ("message_id" in low) or ("message in action" in low) or ("messageid" in low):
            return True
        log.error(f"sms.deals failed (HTTP {r.status_code}): {r.text[:300]}")
        return False
    except Exception as e:
        log.error(f"sms.deals error: {e}")
        return False

def web_send_sms(last9, body):
    res = _send_sms_dealsmaskyoo(last9, body)
    if res is not None:
        return res
    if not (TWILIO_SID and TWILIO_AUTH and TWILIO_FROM):
        log.error("Twilio not configured")
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    data = {"To": _to_e164(last9), "Body": body}
    if TWILIO_FROM.startswith("MG"): data["MessagingServiceSid"] = TWILIO_FROM
    else: data["From"] = TWILIO_FROM
    try:
        r = requests.post(url, data=data, auth=(TWILIO_SID, TWILIO_AUTH), timeout=15)
        if r.status_code >= 300:
            log.error(f"Twilio error {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        log.error(f"Twilio send error: {e}")
        return False

# Single-flight: כשהרבה בקשות נכשלות במטמון בו-זמנית (למשל 20 סוכנים בבוקר על מטמון קר),
# רק חוט אחד מבצע את הקריאה ל-Apps Script והשאר ממתינים לתוצאה — במקום 20 קריאות מקבילות.
_sf_locks = {}
_sf_guard = _threading.Lock()
def _sf_lock(key):
    with _sf_guard:
        lk = _sf_locks.get(key)
        if lk is None:
            lk = _threading.Lock(); _sf_locks[key] = lk
        return lk

def web_fetch_raw(type_he, frm="01/01/2020", to="31/12/2099"):
    _ck = "raw:" + str(type_he) + ":" + str(frm) + ":" + str(to)
    _ttl = 60
    if type_he == "שיחות":     _ttl = _src_ttl(CALLS_SOURCE, 60, 90)
    elif type_he == "חתימות":  _ttl = _src_ttl(SIGNATURES_SOURCE, 60, 90)
    c = _cache_get(_ck, _ttl)
    if c is not None:
        return c
    with _sf_lock(_ck):
        c = _cache_get(_ck, _ttl)   # בדיקה כפולה — אולי חוט אחר כבר מילא בזמן ההמתנה
        if c is not None:
            return c
        rows = _web_fetch_raw_uncached(type_he, frm, to)
        if rows:
            _cache_put(_ck, rows)
        return rows
def _web_fetch_raw_uncached(type_he, frm="01/01/2020", to="31/12/2099"):
    if type_he == "שיחות" and CALLS_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            return _sbdb.fetch_calls_rows(frm, to)
        except Exception as _sbe:
            log.error(f"supabase calls read failed — falling back to sheets: {_sbe}")
    if type_he == "חתימות" and SIGNATURES_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            return _sbdb.fetch_signatures_rows(frm, to)
        except Exception as _sbe:
            log.error(f"supabase signatures read failed — falling back to sheets: {_sbe}")
    if not (APPS_SCRIPT_URL and APPS_SCRIPT_TOKEN):
        return []
    from urllib.parse import quote
    url = (f"{APPS_SCRIPT_URL}?action=raw&type={quote(type_he)}"
           f"&from={frm}&to={to}&token={APPS_SCRIPT_TOKEN}")
    try:
        r = requests.get(url, timeout=30, allow_redirects=True)
        j = r.json()
        return j.get("rows", []) if j.get("ok") else []
    except Exception as e:
        log.error(f"web_fetch_raw {type_he}: {e}")
        return []

_web_phonemap = {"data": None, "ts": 0}
def web_phone_name_map():
    if _web_phonemap["data"] is not None and (time.time() - _web_phonemap["ts"]) < 3600:
        return _web_phonemap["data"]
    rows = web_fetch_raw("שיחות")
    m = {}
    for r in rows:
        ph = _last9(r.get("agent_phone", "")); ag = (r.get("agent", "") or "").strip()
        if ph and ag: m[ph] = ag
    _web_phonemap["data"] = m; _web_phonemap["ts"] = time.time()
    return m

def web_contacts_phone_name():
    """{last9(phone): name} מלשונית 'אנשי קשר' (A=שם, B=טלפון) — מקור הכניסה לסוכנים."""
    m = {}
    for name, phone in fetch_agents_phones().items():
        p = _last9(phone)
        if p and name:
            m[p] = name
    return m

def _office_agent_keys():
    """canon-keys של סוכני המשרד — מאנשי קשר + ספריית הקונסולה, בלי שנמחקו.
    משמש לסינון ספירת עסקאות/תהליכים: מתווך חיצוני שאינו מהמשרד לא נספר."""
    rem = _removed_agent_keys()
    keys = set()
    for _n in web_contacts_phone_name().values():
        if _n and _name_key(_n) not in rem:
            _k = _canon_key(_n)
            if _k: keys.add(_k)
    for _ag in (_load_config().get("agents") or []):
        _nm = _ag.get("name", "")
        if _nm and _name_key(_nm) not in rem:
            _k = _canon_key(_nm)
            if _k: keys.add(_k)
    return keys

def _phones_for_name(name):
    nn = _norm_name(name)
    if not nn: return set()
    ck = _canon_key(name)   # התאמה קנונית — אותו סוכן בשני איותים (רווחים/גרשים) עדיין נמצא
    s = set(p for p, n in web_phone_name_map().items()
            if _norm_name(n) == nn or _canon_key(n) == ck)
    for p, n in web_contacts_phone_name().items():
        if _norm_name(n) == nn or _canon_key(n) == ck:
            s.add(p)
    ck = _canon_key(name)
    for ag in (_load_config().get("agents") or []):
        if _canon_key(ag.get("name", "")) == ck:
            for fld in ("phone", "vphone"):
                v = _last9(ag.get(fld, ""))
                if v: s.add(v)
    return s

def _parse_coordinators():
    """COORDINATORS env (JSON): {"<טלפון מתאמת>":{"name":"...","agents":["<טלפון סוכן>",...]}}"""
    raw = os.environ.get("COORDINATORS", "").strip()
    if not raw: return {}
    try:
        data = json.loads(raw)
    except Exception:
        log.error("COORDINATORS env is not valid JSON"); return {}
    out = {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        kk = _last9(k)
        if not kk or not isinstance(v, dict): continue
        agents = set(_last9(a) for a in (v.get("agents") or []) if _last9(a))
        names = set(_norm_name(n) for n in (v.get("names") or []) if _norm_name(n))
        out[kk] = {"name": v.get("name") or "מתאמת", "agents": agents, "names": names}
    return out
_COORDINATORS = _parse_coordinators()

def _coordinators_all():
    """כל המתאמות: env (_COORDINATORS) + קונפיג מרכזי (coordinators).
    הקונפיג נשמר לפי שמות (מתאמת + סוכנים) ומומר כאן לטלפונים.
    מחזיר { טלפון_מתאמת(9): {name, agents:set(טלפונים), names:set(שמות)} }."""
    out = {}
    for k, v in _COORDINATORS.items():
        kk = _last9(k)
        if kk:
            out[kk] = {"name": v.get("name") or "מתאמת",
                       "agents": set(v.get("agents") or set()),
                       "names": set(v.get("names") or set())}
    cc = _load_config().get("coordinators")
    items = cc if isinstance(cc, list) else []
    for it in items:
        if not isinstance(it, dict): continue
        cname = str(it.get("coordinator") or it.get("name") or "").strip()
        agnames = it.get("agents")
        if not cname or not isinstance(agnames, list): continue
        ag_phones = set(); ag_names = set()
        for an in agnames:
            an = str(an).strip()
            if not an: continue
            ag_names.add(_norm_name(an))
            for ph in _phones_for_name(an):
                if ph: ag_phones.add(ph)
        for cp in _phones_for_name(cname):
            cp = _last9(cp)
            if not cp: continue
            ex = out.get(cp) or {"name": cname, "agents": set(), "names": set()}
            ex["name"] = cname or ex["name"]
            ex["agents"] = set(ex["agents"]) | ag_phones
            ex["names"] = set(ex["names"]) | ag_names
            out[cp] = ex
    return out

def _config_agent_phones():
    """{last9(phone): name} מתוך טלפונים אישיים שהוגדרו ידנית בקונסולה (agents[].phone)."""
    out = {}
    for ag in (_load_config().get("agents") or []):
        nm = (ag.get("name") or "").strip()
        ph = _last9(ag.get("phone", ""))
        if nm and ph: out[ph] = nm
    return out

def _removed_agent_keys():
    """name_key של סוכנים שנמחקו — לא מופיעים בספרייה ולא יכולים להתחבר.
    כולל גם purgedAgents (נמחקו לצמיתות — לא מוצגים אף לשחזור)."""
    cfg = _load_config()
    names = list(cfg.get("removedAgents") or []) + list(cfg.get("purgedAgents") or [])
    return set(_name_key(n) for n in names if _name_key(n))

def web_role_for(last9):
    if _last9(last9) in DEV_PHONES: return "admin"   # מפתח/בעלים — תמיד admin (רשת ביטחון לכניסה)
    if last9 in set(_last9(a) for a in ADMIN_PHONES): return "admin"
    if last9 in _coordinators_all(): return "coordinator"
    nm = (web_contacts_phone_name().get(last9) or web_phone_name_map().get(last9)
          or _config_agent_phones().get(last9))
    if nm:
        if _name_key(nm) in _removed_agent_keys(): return None   # סוכן שנמחק — חסום
        return "agent"
    return None

def _refresh_coordinator_scope(s):
    """סקופ מתאמת חי — נמשך מהקונפיג בכל בקשה, לא רק בכניסה. מתקן את הבאג שמתאמת
    לא ראתה את הסוכנים שלה: שיוך שנעשה בניהול אחרי שהיא כבר מחוברת (או תפקיד
    מתאמת שניתן לסשן קיים) תופס מיד, בלי כניסה מחדש."""
    try:
        ph = _last9(s.get("phone", ""))
        if not ph or s.get("role") == "admin":
            return s
        cc = _coordinators_all()
        if ph in cc:
            s["role"] = "coordinator"
            if s.get("drole") in ("", "agent", None):
                s["drole"] = "coordinator"
            s["agents"] = list(cc[ph]["agents"])
            s["agent_names"] = list(cc[ph]["names"])
        elif s.get("role") == "coordinator":
            s["role"] = "agent"          # הוסרה מהשיוך — חוזרת לסקופ אישי
            if s.get("drole") == "coordinator":
                s["drole"] = "agent"
            s.pop("agents", None); s.pop("agent_names", None)
    except Exception:
        pass
    return s

def _web_auth():
    tok = (request.headers.get("X-Auth-Token") or request.args.get("token")
           or ((request.get_json(silent=True) or {}).get("token") if request.method == "POST" else None))
    if not tok: return None
    s = _web_sessions.get(tok)
    if s:
        if s["exp"] < time.time():
            _web_sessions.pop(tok, None); return None
        if _is_suspended(s.get("phone", "")) and not _is_dev(s.get("phone", "")):
            return None   # סוכן מושהה — חסום (לא נועל את המפתח)
        _mark_joined(s.get("phone", ""))   # יציאה מ"ממתין לכניסה ראשונה" גם ל-session קיים
        return _refresh_coordinator_scope(s)
    # נפילה לטוקן חתום (stateless) — שורד רסטארט של השרת, בלי לזרוק את המשתמש החוצה
    phone = _verify_token(tok)
    if phone:
        if _is_suspended(phone) and not _is_dev(phone):
            return None
        sess = _session_from_phone(phone)
        _web_sessions[tok] = sess
        _mark_joined(phone)
        return _refresh_coordinator_scope(sess)
    return None

# --- activity log (in-memory, newest last) ---
_activity = []
def _persist_activity(entry):
    try:
        _buyers_apps_post("logactivity", {"entry": json.dumps(entry, ensure_ascii=False)})
    except Exception:
        pass
def _log_activity(name, role, phone, action, detail=""):
    entry = {
        "ts": time.time(), "name": name or "", "role": role or "",
        "phone": phone or "", "action": action, "detail": str(detail)[:80],
    }
    _activity.append(entry)
    if len(_activity) > 800:
        del _activity[:len(_activity) - 800]
    try:
        _threading.Thread(target=_persist_activity, args=(entry,), daemon=True).start()
    except Exception:
        pass

_joined_seen = set()   # short-circuit בתהליך — מונע עבודה חוזרת בכל בקשה מאומתת
def _mark_joined(phone):
    """מסמן שסוכן נכנס בפועל (SMS/Google/כל בקשה מאומתת) — כדי שלא יישאר 'ממתין לכניסה ראשונה'.
    לא חוסם: הכתיבה רצה ב-thread; פעם ראשונה בלבד לכל טלפון (short-circuit דרך _joined_seen)."""
    p = _last9(phone)
    if not p or p in _joined_seen:
        return
    _joined_seen.add(p)   # מיידי — כדי לא לשגר עוד thread לאותו טלפון
    def _w():
        try:
            # RMW בטוח: לא לדרוס סוכן שהוזמן בו-זמנית (thread רקע קרא קונפיג ישן ושמר)
            def _mut(cfg):
                joined = [x for x in (cfg.get("v2_joined") or []) if x]
                if p in joined:
                    return False   # כבר מסומן — לא צריך לכתוב
                joined.append(p)
                cfg["v2_joined"] = joined
                return True
            ok, changed = _config_mutate(_mut)
            if not (ok or changed is False):
                _joined_seen.discard(p)   # כתיבה נכשלה — לאפשר ניסיון חוזר
        except Exception:
            _joined_seen.discard(p)   # כשל — לאפשר ניסיון חוזר בבקשה הבאה
    try:
        _threading.Thread(target=_w, daemon=True).start()
    except Exception:
        _joined_seen.discard(p)

# --- recent searches per user (phone -> {kind: [queries]}) ---
_recent = {}
def _push_recent(phone, kind, q):
    q = (q or "").strip()
    if not q or not phone: return
    # חיפושי משרד ושת"פ משותפים — כל חיפוש מופיע ב"חיפושים אחרונים" של שני הטאבים
    kinds = ["props", "excl"] if kind in ("props", "excl") else [kind]
    for k in kinds:
        lst = _recent.setdefault(phone, {}).setdefault(k, [])
        lst[:] = [x for x in lst if x != q]
        lst.insert(0, q)
        del lst[8:]

# ── Auth endpoints ─────────────────────────────────────────────────────────────
@app.route("/api/auth/request", methods=["POST"])
def api_auth_request():
    phone = _last9((request.get_json(silent=True) or {}).get("phone", ""))
    if not phone: return jsonify({"ok": False, "reason": "bad_phone"})
    if not web_role_for(phone) and phone not in _BYPASS_LOGINS:
        return jsonify({"ok": False, "reason": "unknown"})
    if phone in _BYPASS_LOGINS:
        return jsonify({"ok": True})   # קוד קבוע — אין צורך ב-SMS, הקש את הקוד שלך
    if _is_suspended(phone):
        return jsonify({"ok": False, "reason": "suspended"})   # מושהה — לא שולחים SMS (חיסכון בטווילו)
    code = f"{_secrets.randbelow(9000) + 1000}"   # 4 ספרות (בקשת אייל 13/07) — מוגן ע"י תקרת 5 ניסיונות + תוקף 5 ד'
    _otp_store[phone] = {"code": code, "exp": time.time() + _OTP_TTL, "tries": 0}
    # נוסח שהמפענח של iOS מזהה כקוד אימות (מציע מעל המקלדת): שורה עברית נקייה
    # בלי לטינית בין "קוד" למספר, שורה אנגלית בתבנית code: — ובלי ספרות מתחרות ("חמש" במילים).
    _sms = f"קוד הכניסה שלך לאפי: {code}\nEffie code: {code}\n(תקף לחמש דקות)"
    if not web_send_sms(phone, _sms):
        return jsonify({"ok": False, "reason": "sms_failed"})
    return jsonify({"ok": True})

@app.route("/api/auth/verify", methods=["POST"])
def api_auth_verify():
    body  = request.get_json(silent=True) or {}
    phone = _last9(body.get("phone", "")); code = str(body.get("code", "")).strip()
    # קוד כניסה קבוע (עוקף SMS) — רק למספרים שהוגדרו ב-_BYPASS_LOGINS
    if phone in _BYPASS_LOGINS and code == _BYPASS_LOGINS[phone]:
        scope, drole = _resolve_roles(phone)
        if not scope: scope = "agent"   # בייפאס לא-רשום (חשבון ביקורת) = סוכן, לא admin
        if _is_dev(phone): scope = "admin"; drole = "developer"
        role = scope
        name = _login_name(phone, scope, drole)
        token = _mint_token(phone)
        sess = {"phone": phone, "role": role, "drole": drole, "name": name, "exp": time.time() + _SESS_TTL}
        if _is_dev(phone): sess["dev"] = True
        _cc = _coordinators_all()
        if role == "coordinator" and phone in _cc:
            sess["agents"] = list(_cc[phone]["agents"])
            sess["agent_names"] = list(_cc[phone]["names"])
        _web_sessions[token] = sess
        _log_activity(name, sess["role"], phone, "כניסה (קוד קבוע)")
        return jsonify({"ok": True, "token": token, "role": role, "drole": drole, "name": name, "dev": sess.get("dev", False), "tabs": _tabs_for_role(drole)})
    rec = _otp_store.get(phone)
    if not rec or rec["exp"] < time.time(): return jsonify({"ok": False, "reason": "expired"})
    if rec["tries"] >= 5: _otp_store.pop(phone, None); return jsonify({"ok": False, "reason": "too_many"})
    if code != rec["code"]:
        rec["tries"] += 1; return jsonify({"ok": False, "reason": "wrong"})
    _otp_store.pop(phone, None)
    scope, drole = _resolve_roles(phone)
    if _is_dev(phone): scope = "admin"; drole = "developer"
    role = scope
    name = _login_name(phone, scope, drole)
    token = _mint_token(phone)
    sess = {"phone": phone, "role": role, "drole": drole, "name": name, "exp": time.time() + _SESS_TTL}
    if _is_dev(phone): sess["dev"] = True
    _cc = _coordinators_all()
    if role == "coordinator" and phone in _cc:
        sess["agents"] = list(_cc[phone]["agents"])
        sess["agent_names"] = list(_cc[phone]["names"])
    _web_sessions[token] = sess
    _log_activity(name, sess["role"], phone, "כניסה")
    _mark_joined(phone)   # יציאה מ"ממתין לכניסה ראשונה" גם בכניסת SMS
    return jsonify({"ok": True, "token": token, "role": role, "drole": drole, "name": name, "dev": sess.get("dev", False), "tabs": _tabs_for_role(drole)})

# ── Google Sign-In (OAuth) + יומן Google ────────────────────────────────────────
# כניסה עם Google כאופציה ראשית; SMS נשאר כגיבוי. בכניסה ראשונה הסוכן מקשר את
# חשבון הגוגל לטלפון שלו (אימות SMS פעם אחת) ומאז נכנס בקליק. רדום אם אין מפתחות.
from urllib.parse import urlencode as _urlencode
_goauth_state   = {}   # state(csrf) -> {"exp", "native"}
NATIVE_URL_SCHEME = os.environ.get("NATIVE_URL_SCHEME", "remaxfamily")   # deep-link חזרה לאפליקציה
_goauth_pending = {}   # glink token -> {"email","name","refresh_token","exp"} לאימייל שעוד לא מקושר

def _gauth_enabled():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

_GAUTH_PATH = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(os.path.abspath(__file__)),
                           "v2_gauth.json")
_gauth_lock = threading.Lock()
_gauth_seeded = [False]

def _gauth_disk_load():
    try:
        with open(_GAUTH_PATH, encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}

def _gauth_disk_save(m):
    try:
        with open(_GAUTH_PATH, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
    except Exception as _e:
        log.error(f"gauth disk save failed: {_e}")

def _gauth_all():
    # קישורי גוגל בדיסק הקבוע — הסנכרון מהגיליון לא נוגע בהם. שחזור חד-פעמי מהקונפיג
    # (מי שעדיין מקושר שם לא יאבד; אחרי השחזור המקור הבלעדי הוא הדיסק).
    with _gauth_lock:
        disk = _gauth_disk_load()
        if not _gauth_seeded[0]:
            _gauth_seeded[0] = True
            legacy = _load_config().get("gauth")
            if isinstance(legacy, dict) and legacy:
                merged = dict(legacy)
                merged.update(disk)   # הדיסק גובר על עותק ישן בקונפיג
                if merged != disk:
                    _gauth_disk_save(merged)
                return merged
        return disk

def _gauth_email_for_phone(phone):
    phone = _last9(phone)
    for em, rec in _gauth_all().items():
        if _last9((rec or {}).get("phone", "")) == phone:
            return em
    return ""

def _gauth_link(email, phone, refresh_token=None, name=""):
    """מקשר אימייל-גוגל ↔ טלפון-סוכן ושומר refresh_token לשימוש ביומן. בדיסק הקבוע."""
    email = (email or "").strip().lower()
    if not email:
        return
    _gauth_all()   # מוודא שחזור מהקונפיג לפני כתיבה
    with _gauth_lock:
        g = _gauth_disk_load()
        rec = g.get(email) or {}
        rec["phone"] = _last9(phone)
        if name:
            rec["name"] = name
        if refresh_token:             # גוגל מחזירה refresh_token רק בהסכמה הראשונה — לא לדרוס בריק
            rec["refresh_token"] = refresh_token
        rec["ts"] = int(time.time())
        g[email] = rec
        _gauth_disk_save(g)

def _g_token_exchange(code):
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI, "grant_type": "authorization_code"}, timeout=15)
        return r.json() if r.ok else None
    except Exception as e:
        log.error(f"google token exchange: {e}"); return None

def _g_access_from_refresh(rt):
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "refresh_token": rt, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token"}, timeout=15)
        return (r.json() or {}).get("access_token") if r.ok else None
    except Exception as e:
        log.error(f"google refresh: {e}"); return None

def _g_userinfo(access_token):
    try:
        r = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": "Bearer " + access_token}, timeout=15)
        return r.json() if r.ok else None
    except Exception as e:
        log.error(f"google userinfo: {e}"); return None

def _g_mint(phone, label="כניסה עם Google"):
    """מנפיק את אותו סשן/טוקן בדיוק כמו כניסת SMS — כדי שהתפקידים/הטאבים זהים."""
    phone = _last9(phone)
    scope, drole = _resolve_roles(phone)
    if not scope: scope = "agent"
    if _is_dev(phone): scope = "admin"; drole = "developer"
    role = scope
    name = _login_name(phone, scope, drole)
    token = _mint_token(phone)
    sess = {"phone": phone, "role": role, "drole": drole, "name": name, "exp": time.time() + _SESS_TTL}
    if _is_dev(phone): sess["dev"] = True
    _cc = _coordinators_all()
    if role == "coordinator" and phone in _cc:
        sess["agents"] = list(_cc[phone]["agents"])
        sess["agent_names"] = list(_cc[phone]["names"])
    _web_sessions[token] = sess
    _log_activity(name, role, phone, label)
    return token, {"token": token, "role": role, "drole": drole, "name": name,
                   "phone": phone, "dev": sess.get("dev", False), "tabs": _tabs_for_role(drole)}

def _g_page(inner):
    return ("<!doctype html><html lang=he dir=rtl><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1,maximum-scale=1'>"
            "<title>Family Bot</title></head>"
            "<body style=\"margin:0;background:#eef1f5;font-family:Heebo,Arial,sans-serif;"
            "min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px\">"
            "<div style=\"width:100%;max-width:340px;text-align:center\">"
            "<img src='/assets/logo' style='height:46px;margin-bottom:22px' onerror=\"this.style.display='none'\">"
            + inner + "</div></body></html>")

def _g_msg(title, sub="", href="/app", btn="חזרה לכניסה"):
    return _g_page(
        "<div style='font-size:20px;font-weight:800;color:#0D1B2A;margin-bottom:8px'>" + title + "</div>"
        + ("<div style='font-size:14px;color:#6b7280;margin-bottom:22px'>" + sub + "</div>" if sub else "")
        + "<a href='" + href + "' style='display:inline-block;padding:13px 22px;background:#0D1B2A;color:#fff;"
          "border-radius:13px;font-weight:800;text-decoration:none'>" + btn + "</a>")

def _g_done_page(payload, dest="/app"):
    js = _json.dumps(payload, ensure_ascii=False)
    return _g_page(
        "<div style='font-size:18px;font-weight:800;color:#0D1B2A'>מתחבר…</div>"
        "<script>var p=" + js + ";try{localStorage.setItem('fbTok',p.token);"
        "localStorage.setItem('fbRole',p.role||'');localStorage.setItem('fbDrole',p.drole||'');"
        "localStorage.setItem('fbName',p.name||'');localStorage.setItem('fbDev',p.dev?'1':'0');"
        "if(p.phone)localStorage.setItem('fbPhone',p.phone);"
        "localStorage.setItem('fbTabs',JSON.stringify(p.tabs||null));}catch(e){}"
        "location.replace(" + _json.dumps(dest) + ");</script>")

def _g_link_page(glink, email, dest="/app"):
    return _g_page(
        "<div style='font-size:19px;font-weight:800;color:#0D1B2A;margin-bottom:6px'>חיבור ראשון</div>"
        "<div style='font-size:14px;color:#6b7280;margin-bottom:18px'>" + email +
        "<br>הזן את מספר הטלפון שלך כדי לקשר את החשבון פעם אחת</div>"
        "<input id='ph' type='tel' inputmode='numeric' placeholder='מספר טלפון' "
        "style='width:100%;padding:13px;border:1px solid #cbd5e1;border-radius:12px;font-size:16px;text-align:center;margin-bottom:10px'>"
        "<div id='codewrap' style='display:none'><input id='cd' type='tel' inputmode='numeric' placeholder='קוד מ-SMS' "
        "style='width:100%;padding:13px;border:1px solid #cbd5e1;border-radius:12px;font-size:16px;text-align:center;margin-bottom:10px'></div>"
        "<button id='btn' onclick='go()' style='width:100%;padding:14px;background:#0D1B2A;color:#fff;border:none;"
        "border-radius:13px;font-size:16px;font-weight:800'>שלח קוד</button>"
        "<div id='err' style='color:#dc2626;font-size:13px;margin-top:10px;min-height:18px'></div>"
        "<script>var G='" + glink + "',stage=0;"
        "function px(u,d){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(function(r){return r.json()})}"
        "function go(){var e=document.getElementById('err');e.textContent='';"
        "var ph=document.getElementById('ph').value.replace(/\\D/g,'');"
        "if(stage===0){px('/api/auth/glink_request',{glink:G,phone:ph}).then(function(j){"
        "if(!j.ok){e.textContent=(j.reason==='unknown')?'המספר לא רשום במערכת':'שגיאה, נסה שוב';return;}"
        "stage=1;document.getElementById('codewrap').style.display='block';document.getElementById('btn').textContent='התחבר';"
        "});}else{var cd=document.getElementById('cd').value.replace(/\\D/g,'');"
        "px('/api/auth/glink_verify',{glink:G,phone:ph,code:cd}).then(function(p){"
        "if(!p.ok){e.textContent='קוד שגוי, נסה שוב';return;}"
        "if(p.native&&!window.Capacitor){location.href='" + NATIVE_URL_SCHEME + "://login?token='+p.token;"
        "setTimeout(function(){try{localStorage.setItem('fbTok',p.token);localStorage.setItem('fbRole',p.role||'');"
        "if(p.phone)localStorage.setItem('fbPhone',p.phone);"
        "localStorage.setItem('fbDrole',p.drole||'');localStorage.setItem('fbName',p.name||'');"
        "localStorage.setItem('fbDev',p.dev?'1':'0');localStorage.setItem('fbTabs',JSON.stringify(p.tabs||null));}catch(x){}"
        "location.replace('/v2/home');},1800);return;}"
        "if(p.native){try{localStorage.setItem('fbTok',p.token);localStorage.setItem('fbRole',p.role||'');"
        "if(p.phone)localStorage.setItem('fbPhone',p.phone);"
        "localStorage.setItem('fbDrole',p.drole||'');localStorage.setItem('fbName',p.name||'');"
        "localStorage.setItem('fbDev',p.dev?'1':'0');localStorage.setItem('fbTabs',JSON.stringify(p.tabs||null));}catch(x){}"
        "location.replace('/v2/home');return;}"
        "try{localStorage.setItem('fbTok',p.token);localStorage.setItem('fbRole',p.role||'');"
        "if(p.phone)localStorage.setItem('fbPhone',p.phone);"
        "localStorage.setItem('fbDrole',p.drole||'');localStorage.setItem('fbName',p.name||'');"
        "localStorage.setItem('fbDev',p.dev?'1':'0');localStorage.setItem('fbTabs',JSON.stringify(p.tabs||null));}catch(x){}"
        "location.replace(" + _json.dumps(dest) + ");});}}"
        "</script>")

@app.route("/auth/google/login")
def auth_google_login():
    if not _gauth_enabled():
        return _g_msg("התחברות Google אינה פעילה עדיין", "פנה למנהל המערכת"), 200
    state = _secrets.token_urlsafe(16)
    native = request.args.get("native") == "1"
    _goauth_state[state] = {"exp": time.time() + 600, "native": native,
                            "next": ("v2" if request.args.get("next") == "v2" else "")}
    params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": GOOGLE_REDIRECT_URI,
              "response_type": "code",
              "scope": "openid email profile https://www.googleapis.com/auth/calendar.events",
              "access_type": "offline", "prompt": "select_account", "include_granted_scopes": "true",
              "state": state}
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + _urlencode(params))

@app.route("/auth/google/callback")
def auth_google_callback():
    if not _gauth_enabled():
        return _g_msg("התחברות Google אינה פעילה עדיין", "פנה למנהל המערכת"), 200
    if request.args.get("error"):
        return _g_msg("הכניסה בוטלה", "אפשר לנסות שוב או להיכנס עם טלפון")
    state = request.args.get("state", "")
    st = _goauth_state.get(state)
    if not st or st.get("exp", 0) < time.time():
        return _g_msg("פג תוקף ההתחברות", "נסה להתחבר שוב")
    _goauth_state.pop(state, None)
    native = bool(st.get("native"))
    _dest = "/v2/home" if st.get("next") == "v2" else "/app"   # אפי (/v2) חוזרת אליה, לא לאפליקציה הקיימת
    tok = _g_token_exchange(request.args.get("code", ""))
    if not tok or not tok.get("access_token"):
        return _g_msg("שגיאת התחברות מול Google", "נסה שוב")
    info = _g_userinfo(tok["access_token"]) or {}
    email = (info.get("email") or "").strip().lower()
    name = info.get("name") or ""
    rt = tok.get("refresh_token")
    if not email:
        return _g_msg("לא הצלחנו לקרוא את כתובת האימייל", "נסה שוב")
    rec = _gauth_all().get(email)
    if rec and rec.get("phone"):
        if _is_suspended(rec["phone"]):
            return _g_msg("המשתמש מושהה", "פנה למנהל המערכת"), 200   # חסום כניסה עם מייל
        if rt:
            _gauth_link(email, rec["phone"], rt, name)   # רענון הטוקן אם הגיע חדש
        token, payload = _g_mint(rec["phone"])
        if native:   # אפליקציה — בתוך ה-WebView (אנדרואיד): שמירת טוקן והמשך ישיר;
                     # דפדפן חיצוני (iOS/ספארי): deep-link חזרה לאפליקציה (אוטומטי + כפתור גיבוי).
                     # תיקון 21/07: באנדרואיד ה-OAuth רץ בתוך ה-WebView עצמו, וה-deep-link
                     # שם התפרש עקום (נפתח Gmail) והטוקן אבד — window.Capacitor מכריע.
            _scheme = NATIVE_URL_SCHEME + "://login?token=" + token
            _pj = _json.dumps(payload, ensure_ascii=False)
            return ('<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Family Bot</title></head>'
                    '<body style="font-family:-apple-system,Heebo,Arial,sans-serif;background:#0D1B2A;color:#fff;text-align:center;padding:64px 24px;margin:0">'
                    '<div style="font-size:52px">✅</div>'
                    '<h2 style="margin:14px 0 6px">התחברת בהצלחה</h2>'
                    '<div style="opacity:.75;font-size:15px">חוזר לאפליקציה…</div>'
                    '<a href="' + _scheme + '" style="display:inline-block;margin-top:22px;background:#e0b85a;color:#231700;font-weight:800;font-size:18px;padding:15px 30px;border-radius:14px;text-decoration:none">חזור לאפליקציה</a>'
                    '<script>var p=' + _pj + ';'
                    'if(window.Capacitor){try{localStorage.setItem("fbTok",p.token);'
                    'localStorage.setItem("fbRole",p.role||"");localStorage.setItem("fbDrole",p.drole||"");'
                    'localStorage.setItem("fbName",p.name||"");localStorage.setItem("fbDev",p.dev?"1":"0");'
                    'if(p.phone)localStorage.setItem("fbPhone",p.phone);'
                    'localStorage.setItem("fbTabs",JSON.stringify(p.tabs||null));}catch(e){}'
                    'location.replace("/v2/home");}'
                    'else{setTimeout(function(){location.href=' + _json.dumps(_scheme) + ';},250);'
                    'setTimeout(function(){try{localStorage.setItem("fbTok",p.token);'
                    'localStorage.setItem("fbRole",p.role||"");localStorage.setItem("fbDrole",p.drole||"");'
                    'localStorage.setItem("fbName",p.name||"");localStorage.setItem("fbDev",p.dev?"1":"0");'
                    'if(p.phone)localStorage.setItem("fbPhone",p.phone);'
                    'localStorage.setItem("fbTabs",JSON.stringify(p.tabs||null));}catch(e){}'
                    'location.replace("/v2/home");},1800);}'
                    '</script>'
                    '</body></html>'), 200
        return _g_done_page(payload, _dest)
    # אימייל שעוד לא מקושר → דף קישור חד-פעמי עם אימות טלפון
    glink = _secrets.token_urlsafe(18)
    _goauth_pending[glink] = {"email": email, "name": name, "refresh_token": rt,
                              "native": native, "exp": time.time() + 900}
    return _g_link_page(glink, email, _dest)

@app.route("/api/auth/glink_request", methods=["POST"])
def api_glink_request():
    b = request.get_json(silent=True) or {}
    glink = b.get("glink", ""); phone = _last9(b.get("phone", ""))
    pend = _goauth_pending.get(glink)
    if not pend or pend["exp"] < time.time():
        return jsonify({"ok": False, "reason": "expired"})
    if not phone:
        return jsonify({"ok": False, "reason": "bad_phone"})
    if not web_role_for(phone) and phone not in _BYPASS_LOGINS:
        return jsonify({"ok": False, "reason": "unknown"})
    if phone in _BYPASS_LOGINS:
        return jsonify({"ok": True})   # קוד קבוע — אין SMS
    if _is_suspended(phone):
        return jsonify({"ok": False, "reason": "suspended"})
    code = f"{_secrets.randbelow(9000) + 1000}"   # 4 ספרות — כמו בכניסה הרגילה (בקשת אייל 13/07)
    _otp_store[phone] = {"code": code, "exp": time.time() + _OTP_TTL, "tries": 0}
    # נוסח שהמפענח של iOS מזהה כקוד אימות (מציע מעל המקלדת): שורה עברית נקייה
    # בלי לטינית בין "קוד" למספר, שורה אנגלית בתבנית code: — ובלי ספרות מתחרות ("חמש" במילים).
    _sms = f"קוד הכניסה שלך לאפי: {code}\nEffie code: {code}\n(תקף לחמש דקות)"
    if not web_send_sms(phone, _sms):
        return jsonify({"ok": False, "reason": "sms_failed"})
    return jsonify({"ok": True})

@app.route("/api/auth/glink_verify", methods=["POST"])
def api_glink_verify():
    b = request.get_json(silent=True) or {}
    glink = b.get("glink", ""); phone = _last9(b.get("phone", "")); code = str(b.get("code", "")).strip()
    pend = _goauth_pending.get(glink)
    if not pend or pend["exp"] < time.time():
        return jsonify({"ok": False, "reason": "expired"})
    if phone in _BYPASS_LOGINS and code == _BYPASS_LOGINS[phone]:
        pass
    else:
        rec = _otp_store.get(phone)
        if not rec or rec["exp"] < time.time():
            return jsonify({"ok": False, "reason": "expired"})
        if rec["tries"] >= 5:
            _otp_store.pop(phone, None); return jsonify({"ok": False, "reason": "too_many"})
        if code != rec["code"]:
            rec["tries"] += 1; return jsonify({"ok": False, "reason": "wrong"})
        _otp_store.pop(phone, None)
    _gauth_link(pend["email"], phone, pend.get("refresh_token"), pend.get("name", ""))
    _goauth_pending.pop(glink, None)
    token, payload = _g_mint(phone, "כניסה עם Google (קישור ראשון)")
    return jsonify({"ok": True, "native": bool(pend.get("native")), **payload})

# ── Sign in with Apple (App Store Guideline 4.8) ────────────────────────────────
# הקליינט הנייטיבי (Capacitor) מקבל identityToken מהמכשיר ושולח לכאן. השרת מאמת את
# ה-JWT מול המפתחות הציבוריים של אפל (JWKS), וממפה apple-sub ↔ טלפון-סוכן — קישור
# חד-פעמי באימות SMS, בדיוק כמו קישור Google. אין OAuth-דפדפן ואין סוד שרת.
APPLE_BUNDLE_ID = (os.environ.get("APPLE_BUNDLE_ID") or "com.remaxfamily.familybot").strip()
_APPLE_PATH = os.path.join(os.path.dirname(_GAUTH_PATH), "apple_auth.json")
_apple_lock = threading.Lock()
_appleauth_pending = {}   # alink -> {"sub","email","name","exp"} — Apple ID שטרם קושר לטלפון

def _apple_links_all():
    with _apple_lock:
        try:
            with open(_APPLE_PATH, encoding="utf-8") as f:
                m = json.load(f)
            return m if isinstance(m, dict) else {}
        except Exception:
            return {}

def _apple_unlink_sub(sub):
    """מסיר קישור Apple-ID בודד (לבדיקה חוזרת של מסלול המשתמש-החדש)."""
    with _apple_lock:
        try:
            with open(_APPLE_PATH, encoding="utf-8") as f:
                m = json.load(f)
            if not isinstance(m, dict): return
        except Exception:
            return
        if str(sub) in m:
            m.pop(str(sub), None)
            try:
                with open(_APPLE_PATH, "w", encoding="utf-8") as f:
                    json.dump(m, f, ensure_ascii=False)
            except Exception:
                pass

def _apple_link(sub, phone, email="", name=""):
    """מקשר Apple-ID (sub) ↔ טלפון-סוכן. בדיסק הקבוע, כמו קישורי Google."""
    with _apple_lock:
        try:
            with open(_APPLE_PATH, encoding="utf-8") as f:
                m = json.load(f)
            if not isinstance(m, dict): m = {}
        except Exception:
            m = {}
        m[str(sub)] = {"phone": _last9(phone), "email": (email or "").strip().lower(),
                       "name": name or "", "ts": int(time.time())}
        try:
            with open(_APPLE_PATH, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False)
        except Exception as _e:
            log.warning(f"apple link save failed: {_e}")

_apple_jwks = [None]
def _apple_verify_token(id_token):
    """אימות identityToken: חתימת RS256 מול JWKS של אפל + iss/aud/exp. מחזיר payload או None."""
    try:
        import jwt as _pyjwt
        from jwt import PyJWKClient as _PyJWKClient
    except Exception:
        log.error("apple auth: PyJWT not installed (add PyJWT[crypto] to requirements)")
        return None
    try:
        if _apple_jwks[0] is None:
            _apple_jwks[0] = _PyJWKClient("https://appleid.apple.com/auth/keys", cache_keys=True)
        key = _apple_jwks[0].get_signing_key_from_jwt(id_token)
        return _pyjwt.decode(id_token, key.key, algorithms=["RS256"],
                             audience=APPLE_BUNDLE_ID, issuer="https://appleid.apple.com")
    except Exception as _e:
        log.warning(f"apple auth: token verify failed: {_e}")
        return None

@app.route("/api/auth/apple", methods=["POST"])
def api_auth_apple():
    b = request.get_json(silent=True) or {}
    payload = _apple_verify_token(str(b.get("token") or ""))
    if not payload or not payload.get("sub"):
        return jsonify({"ok": False, "reason": "bad_token"})
    sub = str(payload["sub"])
    email = (payload.get("email") or "").strip().lower()
    name = str(b.get("name") or "").strip()   # השם מגיע מהמכשיר רק בהרשאה הראשונה
    rec = _apple_links_all().get(sub)
    if rec and rec.get("phone"):
        if _is_suspended(rec["phone"]):
            return jsonify({"ok": False, "reason": "suspended"})
        token, out = _g_mint(rec["phone"], "כניסה עם Apple")
        return jsonify({"ok": True, **out})
    # Apple ID שטרם קושר → אימות טלפון חד-פעמי (מקביל לקישור Google)
    alink = _secrets.token_urlsafe(18)
    _appleauth_pending[alink] = {"sub": sub, "email": email, "name": name,
                                 "exp": time.time() + 900}
    return jsonify({"ok": True, "link": alink, "email": email})

@app.route("/api/auth/alink_request", methods=["POST"])
def api_alink_request():
    b = request.get_json(silent=True) or {}
    alink = b.get("alink", ""); phone = _last9(b.get("phone", ""))
    pend = _appleauth_pending.get(alink)
    if not pend or pend["exp"] < time.time():
        return jsonify({"ok": False, "reason": "expired"})
    if not phone:
        return jsonify({"ok": False, "reason": "bad_phone"})
    if not web_role_for(phone) and phone not in _BYPASS_LOGINS:
        return jsonify({"ok": False, "reason": "unknown"})
    if phone in _BYPASS_LOGINS:
        return jsonify({"ok": True})   # חשבון ביקורת — קוד קבוע, אין SMS
    if _is_suspended(phone):
        return jsonify({"ok": False, "reason": "suspended"})
    code = f"{_secrets.randbelow(9000) + 1000}"
    _otp_store[phone] = {"code": code, "exp": time.time() + _OTP_TTL, "tries": 0}
    _sms = f"קוד הכניסה שלך לאפי: {code}\nEffie code: {code}\n(תקף לחמש דקות)"
    if not web_send_sms(phone, _sms):
        return jsonify({"ok": False, "reason": "sms_failed"})
    return jsonify({"ok": True})

@app.route("/api/auth/alink_verify", methods=["POST"])
def api_alink_verify():
    b = request.get_json(silent=True) or {}
    alink = b.get("alink", ""); phone = _last9(b.get("phone", "")); code = str(b.get("code", "")).strip()
    pend = _appleauth_pending.get(alink)
    if not pend or pend["exp"] < time.time():
        return jsonify({"ok": False, "reason": "expired"})
    if phone in _BYPASS_LOGINS and code == _BYPASS_LOGINS[phone]:
        pass
    else:
        rec = _otp_store.get(phone)
        if not rec or rec["exp"] < time.time():
            return jsonify({"ok": False, "reason": "expired"})
        if rec["tries"] >= 5:
            _otp_store.pop(phone, None); return jsonify({"ok": False, "reason": "too_many"})
        if code != rec["code"]:
            rec["tries"] += 1; return jsonify({"ok": False, "reason": "wrong"})
        _otp_store.pop(phone, None)
    _apple_link(pend["sub"], phone, pend.get("email", ""), pend.get("name", ""))
    _appleauth_pending.pop(alink, None)
    token, out = _g_mint(phone, "כניסה עם Apple (קישור ראשון)")
    return jsonify({"ok": True, **out})

@app.route("/api/auth/whoami", methods=["GET", "POST"])
def api_auth_whoami():
    """החזרת תפקיד/שם/טאבים מהטוקן — ל-hydration אחרי כניסת Google ב-deep-link (טוקן בלבד)."""
    s = _web_auth()
    if not s:
        return jsonify({"ok": False, "auth": False}), 401
    out = {"ok": True, "role": s.get("role"), "drole": s.get("drole", ""),
           "name": s.get("name", ""), "phone": _last9(s.get("phone", "")),
           "dev": bool(s.get("dev", False)),
           "tabs": _tabs_for_role(s.get("drole", ""))}
    return jsonify(out)

def gcal_create_event(email, summary, description="", start_iso=None, end_iso=None,
                      location=None, tz="Asia/Jerusalem", attendees=None, send_updates="none"):
    """יוצר אירוע ביומן הראשי של הסוכן (לפי האימייל המקושר). מחזיר eventId או None.
    attendees = רשימת מיילים שיוזמנו (מקבלים הזמנה במייל אם send_updates='all').
    לעולם לא זורק חריגה — כשל ביומן לא ישבור את הפעולה במערכת.
    start_iso/end_iso = '2026-06-25T17:00:00' לאירוע עם שעה, או '2026-06-25' ליום שלם."""
    try:
        email = (email or "").strip().lower()
        rec = _gauth_all().get(email) or {}
        rt = rec.get("refresh_token")
        if not rt:
            return None
        if rec.get("cal_off"):           # הסוכן כיבה סנכרון יומן
            return None
        access = _g_access_from_refresh(rt)
        if not access:
            return None
        ev = {"summary": summary or "", "description": description or ""}
        if location:
            ev["location"] = location
        if attendees:
            _at = [{"email": a} for a in attendees if a and "@" in a]
            if _at: ev["attendees"] = _at
        if start_iso and end_iso and "T" in start_iso:
            ev["start"] = {"dateTime": start_iso, "timeZone": tz}
            ev["end"]   = {"dateTime": end_iso, "timeZone": tz}
        elif start_iso:
            ev["start"] = {"date": start_iso[:10]}
            ev["end"]   = {"date": (end_iso or start_iso)[:10]}
        _url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        if send_updates and send_updates != "none":
            _url += "?sendUpdates=" + send_updates
        r = requests.post(_url,
            headers={"Authorization": "Bearer " + access, "Content-Type": "application/json"},
            json=ev, timeout=15)
        if r.ok:
            return (r.json() or {}).get("id")
        log.error(f"gcal create {r.status_code}: {(r.text or '')[:200]}")
        return None
    except Exception as e:
        log.error(f"gcal error: {e}"); return None

def gcal_delete_event(email, event_id):
    """מוחק אירוע מהיומן (ומודיע למוזמנים על הביטול). מחזיר True/False."""
    try:
        email = (email or "").strip().lower()
        rec = _gauth_all().get(email) or {}
        rt = rec.get("refresh_token")
        if not rt or not event_id:
            return False
        access = _g_access_from_refresh(rt)
        if not access:
            return False
        r = requests.delete(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events/" + str(event_id) + "?sendUpdates=all",
            headers={"Authorization": "Bearer " + access}, timeout=15)
        return r.status_code in (200, 204, 404, 410)   # 404/410 = כבר נמחק
    except Exception as e:
        log.error(f"gcal delete: {e}"); return False

@app.route("/api/gcal/test", methods=["GET", "POST"])
def api_gcal_test():
    """בדיקת יומן: יוצר אירוע דמו ביומן של המשתמש המחובר (לאימות שהחיבור עובד)."""
    s = _web_auth()
    if not s:
        return jsonify({"ok": False, "reason": "no_session"}), 401
    email = _gauth_email_for_phone(s.get("phone", ""))
    if not email:
        return jsonify({"ok": False, "reason": "no_google_link (התחבר פעם אחת עם Google)"})
    eid = gcal_create_event(email, "בדיקת Family Bot ✅",
                            "אירוע בדיקה — אם אתה רואה אותו, סנכרון היומן עובד.",
                            start_iso=None, end_iso=None)
    return jsonify({"ok": bool(eid), "eventId": eid, "email": email})

@app.route("/api/admin/loginas", methods=["POST"])
def api_admin_loginas():
    """כניסת בדיקה: מנהל מקבל סשן סוכן אמיתי (role=agent) — לא התחזות."""
    s = _web_auth()
    if not s or s["role"] != "admin":
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    name = ((request.get_json(silent=True) or {}).get("name", "") or "").strip()
    if not name:
        return jsonify({"ok": False, "reason": "no_name"}), 400
    phones = _phones_for_name(name)
    phone = next(iter(phones)) if phones else ""
    # פתרון התפקיד והסקופ של הנבדק — כדי שהטאבים *וגם הנתונים* יוצגו בדיוק כמו בכניסה אמיתית שלו
    _scope, drole = _resolve_roles(_last9(phone)) if phone else ("agent", "agent")
    token = _secrets.token_urlsafe(24)
    sess = {"phone": phone, "role": _scope, "drole": drole, "name": name, "exp": time.time() + _SESS_TTL}
    # סינון שיחות/נתונים לפי *כל* הטלפונים של הסוכן (כמו ב"צפה כסוכן") — לא רק טלפון אחד שרירותי
    if phones:
        sess["phones"] = [_last9(p) for p in phones if _last9(p)]
    _cc = _coordinators_all()
    if _scope == "coordinator" and _last9(phone) in _cc:
        sess["agents"] = list(_cc[_last9(phone)]["agents"])
        sess["agent_names"] = list(_cc[_last9(phone)]["names"])
    _web_sessions[token] = sess
    _log_activity(s["name"], s["role"], s["phone"], "כניסת בדיקה כסוכן", name)
    return jsonify({"ok": True, "token": token, "role": _scope, "drole": drole,
                    "name": name, "tabs": _tabs_for_role(drole)})

# ── קונסולת מפתח: קריאה/כתיבה של הקונפיג המרכזי (מוגן ל-DEV בלבד) ──────────────
@app.route("/api/dev/config", methods=["GET"])
def api_dev_config_get():
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    return jsonify({"ok": True, "config": _load_config()})

@app.route("/api/dev/config", methods=["POST"])
def api_dev_config_set():
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    cfg = body.get("config")
    if not isinstance(cfg, dict):
        return jsonify({"ok": False, "reason": "bad_config"}), 400
    ok = _save_config(cfg)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון הגדרות מערכת")
    return jsonify({"ok": ok})

@app.route("/api/dev/people", methods=["GET"])
def api_dev_people():
    """ספריית סוכנים (קנוני מ'אנשי קשר' + קונפיג) + שמות בחתימות/נכסים שלא מזוהים לאף סוכן."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    cfg = _load_config()
    cfg_roles = cfg.get("roles") or {}
    cfg_by_key = {_name_key(a.get("name", "")): a for a in (cfg.get("agents") or []) if a.get("name")}
    delays = _fetch_newborn_delays()
    _nb_def = int(delays.get("_default", 0))
    contacts = web_contacts_phone_name()       # {last9: name}
    vmap = fetch_agent_virtual_phones()         # {norm_name: vphone}
    known = {}   # name_key -> {name, phones:set, vphone, aliases:[]}
    for ph, nm in contacts.items():
        k = _name_key(nm)
        if not k: continue
        d = known.setdefault(k, {"name": nm, "phones": set(), "vphone": vmap.get(_norm_name(nm), ""), "aliases": []})
        d["phones"].add(ph)
    alias_keys = {}   # name_key(alias) -> canonical name
    for ag in (cfg.get("agents") or []):
        cn = (ag.get("name") or "").strip()
        if not cn: continue
        k = _name_key(cn)
        d = known.setdefault(k, {"name": cn, "phones": set(), "vphone": ag.get("vphone", ""), "aliases": []})
        if ag.get("phone"): d["phones"].add(_last9(ag["phone"]))
        if ag.get("vphone") and not d["vphone"]: d["vphone"] = ag["vphone"]
        for al in (ag.get("aliases") or []):
            al = (al or "").strip()
            if al:
                d["aliases"].append(al)
                alias_keys[_name_key(al)] = cn
    known_keys = set(known.keys()) | set(alias_keys.keys())
    _removed_keys = _removed_agent_keys()   # שם שנמחק — לא מוצג גם ברשימת הלא-משויכים
    def _scan(names):
        cnt = {}
        for nm in names:
            nm = (nm or "").strip()
            if nm: cnt[nm] = cnt.get(nm, 0) + 1
        out = [{"name": nm, "count": c} for nm, c in cnt.items()
               if _name_key(nm) not in known_keys and _name_key(nm) not in _removed_keys]
        out.sort(key=lambda x: -x["count"])
        return out
    sig_names = [g.get("agent", "") for g in get_signings()]
    list_names = []
    for r in fetch_sheet_rows():
        list_names.append(r.get("סוכן 1", "")); list_names.append(r.get("סוכן 2", ""))
    removed = _removed_agent_keys()
    _susp = _suspended_set()
    agents = []
    for v in sorted(known.values(), key=lambda x: x["name"]):
        if _name_key(v["name"]) in removed: continue   # סוכן שנמחק — מוסתר מהספרייה
        role = ""
        for ph in v["phones"]:
            if ph in cfg_roles: role = cfg_roles[ph]; break
        _ce = cfg_by_key.get(_name_key(v["name"]), {})
        _cnd = _ce.get("newbornDelay")
        if _cnd in ("hidden", "מוסתר"):
            nb_val, nb_hidden = "", True
        elif _cnd not in (None, ""):
            nb_val, nb_hidden = _cnd, False
        else:
            nb_val, nb_hidden = "", False
        agents.append({"name": v["name"], "vphone": v["vphone"],
                       "phones": sorted(p for p in v["phones"] if p),
                       "aliases": v["aliases"], "role": role,
                       "phone": (_ce.get("phone", "") or (sorted(v["phones"])[0] if v["phones"] else "")),
                       "nbDelay": nb_val, "nbHidden": nb_hidden,
                       "suspended": bool(set(v["phones"]) & _susp)})
    # חברי צוות שנמחקו — חוזרים עם מונה חתימות, לשחזור מהניהול. בלי זה סוכן שנמחק
    # "נעלם" מכל הרשימות (ספרייה + לא-משויכים) למרות שכבר ביצע חתימות (בקשת אייל 13/07).
    _sig_cnt = {}
    for _nm in sig_names:
        _k = _name_key(_nm)
        if _k: _sig_cnt[_k] = _sig_cnt.get(_k, 0) + 1
    removed_out = [{"name": _nm, "sigs": _sig_cnt.get(_name_key(_nm), 0)}
                   for _nm in (str(x or "").strip() for x in (cfg.get("removedAgents") or [])) if _nm]
    return jsonify({"ok": True, "agents": agents, "nbDefault": _nb_def,
                    "unmatchedSignings": _scan(sig_names),
                    "unmatchedListings": _scan(list_names),
                    "removed": removed_out})

@app.route("/api/dev/parity", methods=["GET"])
def api_dev_parity():
    """הרצת parity_check על השרת (שם הסודות כבר בסביבה) — מפתח בלבד.
    מחזיר את הדוח המלא; green=true אומר שבטוח להדליק את דגלי ה-Supabase."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    import io as _io, contextlib as _ctx
    buf = _io.StringIO()
    try:
        import parity_check as _pc
        with _ctx.redirect_stdout(buf):
            code = _pc.main()
        return jsonify({"ok": True, "green": code == 0, "report": buf.getvalue()})
    except Exception as e:
        return jsonify({"ok": False, "report": buf.getvalue(), "error": str(e)[:300]})

@app.route("/api/dev/suspend", methods=["POST"])
def api_dev_suspend():
    """השהיית/שחרור סוכן — מפתח בלבד. מושהה לא יכול לקבל SMS או להיכנס (חיסכון בטווילו)."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    b = request.get_json(silent=True) or {}
    ph = _last9(b.get("phone", ""))
    if not ph:
        return jsonify({"ok": False, "reason": "bad_phone"})
    _res = {}
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        susp = set(_last9(p) for p in (cfg.get("suspended") or []) if p)
        if b.get("suspend"): susp.add(ph)
        else: susp.discard(ph)
        cfg["suspended"] = sorted(susp)
        _res["on"] = ph in susp
    ok, _ = _config_mutate(_mut)
    if not ok:
        return jsonify({"ok": False, "reason": "save_failed"})
    return jsonify({"ok": True, "suspended": _res.get("on", False)})

@app.route("/api/dev/quiet", methods=["GET", "POST"])
def api_dev_quiet():
    """מתג השתקת התראות (וואטסאפ+פוש) מהקונסולה — מפתח בלבד. env גובר על הכפתור."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    env_forced = bool((os.environ.get("QUIET_MODE") or "").strip())
    if request.method == "POST":
        on = bool((request.get_json(silent=True) or {}).get("on"))
        _quiet_set(on)
        _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                      "השתקת התראות" if on else "הפעלת התראות", "מהקונסולה")
    return jsonify({"ok": True, "on": _quiet_mode(), "env": env_forced})

@app.route("/api/dev/smstest", methods=["POST"])
def api_dev_smstest():
    """אבחון ספק SMS (Maskyoo/sms.deals) — מפתח בלבד. שולח הודעת בדיקה ומחזיר את
    התשובה הגולמית של הספק, כדי לאתר בעיית IP/שולח/טוקן. שולח למספר של המפתח כברירת מחדל."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    b = request.get_json(silent=True) or {}
    to = (b.get("phone") or s.get("phone", "")).strip()
    dest = _sms_local_il(to)
    out = {"ok": True, "provider": "sms.deals", "dest": dest, "sender": SMS_DEALS_SENDER,
           "token_set": bool(SMS_DEALS_TOKEN), "sender_set": bool(SMS_DEALS_SENDER), "url": SMS_DEALS_URL,
           "token_len": len(SMS_DEALS_TOKEN),
           "token_preview": ((SMS_DEALS_TOKEN[:4] + "…" + SMS_DEALS_TOKEN[-4:]) if len(SMS_DEALS_TOKEN) >= 8 else "?")}
    # ה-IP היוצא בפועל — נבדק כמה פעמים כדי לחשוף אם Render משתמש במאגר כתובות מתחלף
    _ips = []
    for _i in range(6):
        try:
            _ipr = requests.get("https://api.ipify.org", timeout=6)
            if _ipr.status_code < 300 and (_ipr.text or "").strip():
                _ip = (_ipr.text or "").strip()[:60]
                if _ip not in _ips: _ips.append(_ip)
        except Exception:
            continue
    out["outbound_ips"] = _ips
    out["outbound_ip"] = (_ips[0] if _ips else "?")
    if not (SMS_DEALS_TOKEN and SMS_DEALS_SENDER):
        out["ok"] = False; out["reason"] = "not_configured"
        return jsonify(out)
    if not dest:
        out["ok"] = False; out["reason"] = "bad_dest"
        return jsonify(out)
    params  = {"service": "send_sms", "dest": dest, "sender": SMS_DEALS_SENDER, "message": "בדיקת Family Bot", "token": SMS_DEALS_TOKEN}
    headers = {"Authorization": "Bearer " + SMS_DEALS_TOKEN}
    try:
        r = requests.get(SMS_DEALS_URL, params=params, headers=headers, timeout=15)
        low = (r.text or "").lower()
        out["status"] = r.status_code
        out["response"] = (r.text or "")[:600]
        out["sent_ok"] = (r.status_code < 300) and (("message_id" in low) or ("message in action" in low) or ("messageid" in low))
    except Exception as e:
        out["ok"] = False; out["reason"] = str(e)[:240]
    return jsonify(out)

@app.route("/api/dev/alias", methods=["POST"])
def api_dev_alias():
    """שיוך שם לא-מזוהה (איות חלופי) לסוכן קנוני — נשמר בקונפיג, משפיע מיד על ההתאמה."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    alias = (body.get("alias") or "").strip()
    agent = (body.get("agent") or "").strip()
    if not alias or not agent:
        return jsonify({"ok": False, "reason": "missing"}), 400
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        agents = cfg.setdefault("agents", [])
        entry = next((a for a in agents if _name_key(a.get("name", "")) == _name_key(agent)), None)
        if not entry:
            entry = {"name": agent, "aliases": []}
            agents.append(entry)
        al = entry.setdefault("aliases", [])
        if alias not in al:
            al.append(alias)
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "שיוך כינוי שם", agent + " ← " + alias)
    return jsonify({"ok": ok})

@app.route("/api/dev/agent_add", methods=["POST"])
def api_dev_agent_add():
    """הוספת סוכן קנוני חדש לקונפיג (כדי שיהיה ניתן לשייך אליו / שיופיע כסוכן מוכר)."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "reason": "missing"}), 400
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        agents = cfg.setdefault("agents", [])
        if not any(_name_key(a.get("name", "")) == _name_key(name) for a in agents):
            ent = {"name": name, "aliases": []}
            if (body.get("phone") or "").strip():  ent["phone"]  = _last9(body["phone"])
            if (body.get("vphone") or "").strip(): ent["vphone"] = body["vphone"].strip()
            agents.append(ent)
        # אם הסוכן היה מסומן כמחוק (רגיל או לצמיתות) — להחזיר אותו
        cfg["removedAgents"] = [x for x in (cfg.get("removedAgents") or []) if _name_key(x) != _name_key(name)]
        cfg["purgedAgents"] = [x for x in (cfg.get("purgedAgents") or []) if _name_key(x) != _name_key(name)]
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "הוספת סוכן", name)
    return jsonify({"ok": ok})

@app.route("/api/dev/agent_update", methods=["POST"])
def api_dev_agent_update():
    """עדכון שדות סוכן בקונפיג: מספר וירטואלי, טלפון, וימי השהיה לנכס נולד."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "reason": "missing"}), 400
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        agents = cfg.setdefault("agents", [])
        entry = next((a for a in agents if _name_key(a.get("name", "")) == _name_key(name)), None)
        if not entry:
            entry = {"name": name, "aliases": []}
            agents.append(entry)
        if "vphone" in body:
            vp = (body.get("vphone") or "").strip()
            if vp: entry["vphone"] = vp
            else: entry.pop("vphone", None)
        if "phone" in body:
            ph = _last9(body.get("phone") or "")
            if ph: entry["phone"] = ph
            else: entry.pop("phone", None)
        if "newbornDelay" in body:
            nd = body.get("newbornDelay")
            if nd in ("", None): entry.pop("newbornDelay", None)
            elif str(nd) in ("hidden", "מוסתר", "-1"): entry["newbornDelay"] = "hidden"
            else:
                try: entry["newbornDelay"] = int(nd)
                except Exception: pass
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון סוכן", name)
    return jsonify({"ok": ok})

@app.route("/api/dev/agent_delete", methods=["POST"])
def api_dev_agent_delete():
    """מחיקת סוכן מהקונסולה: מסיר רשומת קונפיג, תפקיד ושיוכי צוות/מתאמת,
    מסתיר אותו מהספרייה (גם אם מקורו ב'אנשי קשר') וחוסם כניסה."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    # מחיקה = בחירה מפורשת של בעל המשרד בלבד (בקשת אייל 13/07): הכפתור חי רק בכרטיס
    # החבר (עם אישור דו-שלבי) — לא בפח של "שמות לא משויכים" (שם נמחק בטעות סוכן בדיקה 4).
    # השם שנמחק נכנס לרשימת "חברי צוות שנמחקו" בניהול — ממנה משחזרים או מוחקים לצמיתות.
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "reason": "missing"}), 400
    nk = _name_key(name); ck = _canon_key(name)
    phs = set(_phones_for_name(name))
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        cfg["agents"] = [a for a in (cfg.get("agents") or [])
                         if _name_key(a.get("name", "")) != nk]
        roles = cfg.get("roles") or {}
        for ph in list(roles.keys()):
            if _last9(ph) in phs: roles.pop(ph, None)
        cfg["roles"] = roles
        new_teams = []
        for grp in (cfg.get("teams") or []):
            if not isinstance(grp, list): continue
            members = [m for m in grp if _canon_key(m) != ck]
            if len(members) >= 2: new_teams.append(members)
        cfg["teams"] = new_teams
        new_co = []
        for it in (cfg.get("coordinators") or []):
            if not isinstance(it, dict): continue
            if _canon_key(it.get("coordinator", "")) == ck: continue
            ags = [a for a in (it.get("agents") or []) if _canon_key(a) != ck]
            if ags: new_co.append({"coordinator": it.get("coordinator"), "agents": ags})
        cfg["coordinators"] = new_co
        rem = cfg.get("removedAgents") or []
        if not any(_name_key(x) == nk for x in rem):
            rem.append(name)
        cfg["removedAgents"] = rem
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "מחיקת סוכן", name)
    return jsonify({"ok": ok})

@app.route("/api/dev/agent_purge", methods=["POST"])
def api_dev_agent_purge():
    """מחיקה לצמיתות מרשימת המחוקים: השם נשאר חסום ומוסתר (purgedAgents) אך לא מוצג
    יותר לשחזור. הרשומות ההיסטוריות בגיליון נשארות. הזמנה מחדש מפורשת עדיין משחררת."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "reason": "missing"}), 400
    nk = _name_key(name)
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        cfg["removedAgents"] = [x for x in (cfg.get("removedAgents") or []) if _name_key(x) != nk]
        pg = cfg.get("purgedAgents") or []
        if not any(_name_key(x) == nk for x in pg):
            pg.append(name)
        cfg["purgedAgents"] = pg
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "מחיקת סוכן לצמיתות", name)
    return jsonify({"ok": ok})

@app.route("/api/dev/role", methods=["POST"])
def api_dev_role():
    """שיוך תפקיד לאדם (לפי טלפון). ריק = הסרה (חוזר לברירת מחדל)."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    phone = _last9(body.get("phone") or "")
    role = (body.get("role") or "").strip()
    if not phone:
        return jsonify({"ok": False, "reason": "missing"}), 400
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        roles = cfg.setdefault("roles", {})
        if role in _ROLE_SCOPE:
            roles[phone] = role
        else:
            roles.pop(phone, None)
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "שיוך תפקיד", role + " ← " + phone)
    return jsonify({"ok": ok})

@app.route("/api/dev/roleperms", methods=["GET", "POST"])
def api_dev_roleperms():
    """מטריצת טאבים לכל תפקיד. GET=קריאה, POST {role, tabs:[...]}=עדכון."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    if request.method == "GET":
        out = {}
        for r in _ROLE_SCOPE:
            out[r] = _tabs_for_role(r)
        return jsonify({"ok": True, "allTabs": _ALL_TABS, "perms": out})
    body = request.get_json(silent=True) or {}
    role = (body.get("role") or "").strip()
    tabs = body.get("tabs")
    if role not in _ROLE_SCOPE or not isinstance(tabs, list):
        return jsonify({"ok": False, "reason": "bad"}), 400
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        cfg.setdefault("rolePerms", {})[role] = {"tabs": [t for t in tabs if t in _ALL_TABS]}
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון הרשאות תפקיד", role)
    return jsonify({"ok": ok})

@app.route("/api/dev/teams", methods=["GET", "POST"])
def api_dev_teams():
    """צוותים (מי רואה את מי). GET=קריאה, POST {teams:[[name,name,...],...]}=שמירה."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    if request.method == "GET":
        return jsonify({"ok": True, "teams": _load_config().get("teams") or []})
    body = request.get_json(silent=True) or {}
    teams = body.get("teams")
    if not isinstance(teams, list):
        return jsonify({"ok": False, "reason": "bad"}), 400
    clean = []
    for grp in teams:
        if isinstance(grp, list):
            members = []
            for m in grp:
                m = str(m).strip()
                if m and m not in members: members.append(m)
            if len(members) >= 2: clean.append(members)
    # RMW בטוח — צוות "נמחק אחרי כמה דקות" כי _mark_joined ברקע דרס את הכתיבה
    def _mut(cfg): cfg["teams"] = clean
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון צוותים", str(len(clean)))
    return jsonify({"ok": ok})

@app.route("/api/dev/coordinators", methods=["GET", "POST"])
def api_dev_coordinators():
    """מתאמות (מי רואה אילו סוכנים — חד-כיווני). GET=קריאה,
    POST {coordinators:[{coordinator:name, agents:[name,...]},...]}=שמירה."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    if request.method == "GET":
        cc = _load_config().get("coordinators")
        out = cc if isinstance(cc, list) else []
        return jsonify({"ok": True, "coordinators": out})
    body = request.get_json(silent=True) or {}
    coords = body.get("coordinators")
    if not isinstance(coords, list):
        return jsonify({"ok": False, "reason": "bad"}), 400
    clean = []
    for it in coords:
        if not isinstance(it, dict): continue
        cname = str(it.get("coordinator") or it.get("name") or "").strip()
        if not cname: continue
        agents = []
        for a in (it.get("agents") or []):
            a = str(a).strip()
            if a and a != cname and a not in agents: agents.append(a)
        if agents:
            clean.append({"coordinator": cname, "agents": agents})
    def _mut(cfg): cfg["coordinators"] = clean   # RMW בטוח (נגד דריסת רקע)
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון מתאמות", str(len(clean)))
    return jsonify({"ok": ok})

_CONTRACT_TYPES = {
    "buyer_both": "מתעניין — קניה ושכירות",
    "buyer_buy":  "מתעניין — קניה",
    "buyer_rent": "מתעניין — שכירות",
    "seller_both": "בעל נכס — מכירה והשכרה",
    "seller_sell": "בעל נכס — מכירה",
    "exclusive":  "בלעדיות",
    "shtaf":      "שיתוף פעולה (שת״פ)",
}
_PARTIES = """בין הלקוח, שפרטיו המלאים מופיעים לעיל ו/או מי מטעמו
לבין מנהלי המשרד RE/MAX Family, אייל שמול, ת.ז 039627989, מ.ר 20039
ו/או אודי שמול, ת.ז 301055901, מ.ר 313254 ו/או גיל קדם ת.ז 039456868 מ.ר 313369 ו/או אוהד פלד ת.ז 033056938 מ.ר 3156247
והמתווך שפרטיו מופיעים לעיל
ממשרד רימקס פמילי (פמלי נדל"ן והשקעות בע"מ) שכתובתו רח' יגאל בשן 2, ק. ביאליק ח.פ. 515506293 ו/או (פמלי תיווך בע"מ) שושנה דמארי 4, קרית מוצקין ח.פ 515466548
ו/או כל מורשה אחר שהוסמך על ידם לביצוע הזמנה זו (כולם ביחד, להלן: "המתווך")."""

# נוסחי ברירת מחדל (ניתנים לעריכה בקונסולה — config דורס). משתנים: SALE_FEE / RENT_FEE / EXCLUSIVE_FROM / EXCLUSIVE_TO / CON_REF_ID / CON_REF_DATE.
_DEFAULT_CONTRACTS = {
"buyer_both": _PARTIES + """
1. הלקוח מזמין שרותי תיווך מקרקעין מהמתווך, כדי לקבל שירותי תיווך בקשר לנכסים המפורטים לעיל.
2. הלקוח מאשר כי המתווך הציג בפניו את הנכסים המפורטים להלן, והוא מתחייב לדווח למתווך מיד על כל משא ומתן המתנהל עמו ו/או עם שולחו בקשר לאחד או יותר מהנכסים, וכן מיד עם חתימת הסכם מחייב ו/או עם התחייבות לביצוע העסקה, המוקדם מביניהם, ביחס לאחד או יותר מהנכסים להלן.
3. הלקוח מתחייב לשלם למתווך דמי תיווך בשיעור המפורט להלן בסעיף 5 מיד עם חתימת הסכם מחייב ו/או עם התחייבות לביצוע העסקה המוקדם מביניהם, בנוגע לאחד או יותר מהנכסים המפורטים לעיל.
4. הלקוח מתחייב לא למסור לגורם כלשהו מידע שיקבל מהמתווך בנוגע לנכסים שלהלן ומתחייב לפצות את המתווך על כל נזק שייגרם לו באם יפר התחייבות זאת.
5. דמי התיווך שישולמו למתווך כמפורט בסעיף 3 לעיל, יהיו במזומן כדלקמן:
   5.1  בקניה: SALE_FEE ממחיר המכירה הכולל של הנכס, בתוספת מע"מ.
   5.2  בכל מקרה עמלת התיווך בקנייה לא תפחת מ-26,500 ש"ח + מע"מ (עמלת מינימום בנכסים מתחת ל-1,325,000 ש"ח).
   5.3  בהשכרה: דמי שכירות של RENT_FEE בתוספת מע"מ.
   5.4  האמור לעיל בא בנוסף לזכותו של המתווך לגבות דמי תיווך מהמוכר / משכיר.
   5.5  היה ותתפתח עסקה דרך בעל נכס שפרטיו רשומים בפרטי הנכס לעיל עם הקונה הנ"ל, יחוייב בדמי תיווך כמסומן בסעיף 5.1 וגם 5.2.
   5.6  במידה ותיחתם עסקה שלא בידיעת המתווך/משרד התיווך ו/או אי תשלום שכ"ט תוך 30 יום מיום ביצוע העסקה, יפוצה המתווך ב-1% + מע"מ נוספים ללא הוכחת נזק או חודש שכירות נוסף (בשכירות בלבד).
6. הלקוח מאשר כי עם מכירת הנכס ורכישתו על ידי הקונה המתווך יוכל להודיע לציבור כי הנכס נמכר.
7. הלקוח מצהיר כי ידוע לו כי דמי התיווך ייגבו על ידי מנהל המשרד וכנגד חשבונית מס כחוק מטעם פמילי נדל"ן והשקעות בע"מ ו/או פמילי תיווך בע"מ.
8. הלקוח מאשר שהומלץ לו על ידי המתווך להסתייע בשרותי עורך דין ו/או מומחים אחרים לפי העניין והצורך במהלך העסקה.
9. בחתימתי מטה הנני מאשר לחברת רימקס לעדכן אותי בנכסים מוצעים למכירה ועדכונים שוטפים על אופן השיווק אפשרויות מימון ובכלל.""",
"buyer_buy": _PARTIES + """
1. הלקוח מזמין שרותי תיווך מקרקעין מהמתווך, כדי לקבל שירותי תיווך בקשר לנכסים המפורטים לעיל.
2. הלקוח מאשר כי המתווך הציג בפניו את הנכסים המפורטים להלן, והוא מתחייב לדווח למתווך מיד על כל משא ומתן המתנהל עמו ו/או עם שולחו בקשר לאחד או יותר מהנכסים, וכן מיד עם חתימת הסכם מחייב ו/או עם התחייבות לביצוע העסקה, המוקדם מביניהם, ביחס לאחד או יותר מהנכסים להלן.
3. הלקוח מתחייב לשלם למתווך דמי תיווך בשיעור המפורט להלן בסעיף 5 מיד עם חתימת הסכם מחייב ו/או עם התחייבות לביצוע העסקה המוקדם מביניהם, בנוגע לאחד או יותר מהנכסים המפורטים לעיל.
4. הלקוח מתחייב לא למסור לגורם כלשהו מידע שיקבל מהמתווך בנוגע לנכסים שלהלן ומתחייב לפצות את המתווך על כל נזק שייגרם לו באם יפר התחייבות זאת.
5. דמי התיווך שישולמו למתווך כמפורט בסעיף 3 לעיל, יהיו במזומן כדלקמן:
   5.1  בקניה: SALE_FEE ממחיר המכירה הכולל של הנכס, בתוספת מע"מ.
   5.2  בכל מקרה עמלת התיווך בקנייה לא תפחת מ-26,500 ש"ח + מע"מ (עמלת מינימום בנכסים מתחת ל-1,325,000 ש"ח).
   5.3  האמור לעיל בא בנוסף לזכותו של המתווך לגבות דמי תיווך מהמוכר / משכיר.
   5.4  היה ותתפתח עסקה דרך בעל נכס שפרטיו רשומים בפרטי הנכס לעיל עם הקונה הנ"ל, יחוייב בדמי תיווך כמסומן בסעיף 5.1 וגם 5.2.
   5.5  במידה ותיחתם עסקה שלא בידיעת המתווך/משרד התיווך ו/או אי תשלום שכ"ט תוך 30 יום מיום ביצוע העסקה, יפוצה המתווך ב-1% + מע"מ נוספים ללא הוכחת נזק או חודש שכירות נוסף (בשכירות בלבד).
6. הלקוח מאשר כי עם מכירת הנכס ורכישתו על ידי הקונה המתווך יוכל להודיע לציבור כי הנכס נמכר.
7. הלקוח מצהיר כי ידוע לו כי דמי התיווך ייגבו על ידי מנהל המשרד וכנגד חשבונית מס כחוק מטעם פמילי נדל"ן והשקעות בע"מ ו/או פמילי תיווך בע"מ.
8. הלקוח מאשר שהומלץ לו על ידי המתווך להסתייע בשרותי עורך דין ושמאי מוסמך ו/או מומחים אחרים טרם ביצוע העסקה.
9. בחתימתי מטה הנני מאשר לחברת רימקס לעדכן אותי בנכסים מוצעים למכירה ועדכונים שוטפים על אופן השיווק אפשרויות מימון ובכלל.""",
"buyer_rent": _PARTIES + """
1. הלקוח מזמין שרותי תיווך מקרקעין מהמתווך, כדי לקבל שירותי תיווך בקשר לנכסים המפורטים לעיל.
2. הלקוח מאשר כי המתווך הציג בפניו את הנכסים המפורטים להלן, והוא מתחייב לדווח למתווך מיד על כל משא ומתן המתנהל עמו ו/או עם שולחו בקשר לאחד או יותר מהנכסים, וכן מיד עם חתימת הסכם מחייב ו/או עם התחייבות לביצוע העסקה, המוקדם מביניהם, ביחס לאחד או יותר מהנכסים להלן.
3. הלקוח מתחייב לשלם למתווך דמי תיווך בשיעור המפורט להלן בסעיף 5 מיד עם חתימת הסכם מחייב ו/או עם התחייבות לביצוע העסקה המוקדם מביניהם, בנוגע לאחד או יותר מהנכסים המפורטים לעיל.
4. הלקוח מתחייב לא למסור לגורם כלשהו מידע שיקבל מהמתווך בנוגע לנכסים שלהלן ומתחייב לפצות את המתווך על כל נזק שייגרם לו באם יפר התחייבות זאת.
5. דמי התיווך שישולמו למתווך כמפורט בסעיף 3 לעיל, יהיו במזומן כדלקמן:
   5.1  בשכירות: דמי שכירות של RENT_FEE בתוספת מע"מ.
   5.2  האמור לעיל בא בנוסף לזכותו של המתווך לגבות דמי תיווך מהמשכיר.
   5.3  היה ותתפתח עסקה דרך בעל הנכס שפרטיו רשומים בפרטי הנכס עם הקונה הנ"ל, יחוייב בדמי תיווך כמסומן בסעיף 5.1.
   5.4  במידה ותיחתם עסקה שלא בידיעת המתווך/משרד התיווך, יפוצה המתווך בחודש שכירות נוסף.
6. הלקוח מאשר כי עם מכירת הנכס ורכישתו על ידי הקונה המתווך יוכל להודיע לציבור כי הנכס נמכר.
7. הלקוח מצהיר כי ידוע לו כי דמי התיווך ייגבו על ידי מנהל המשרד וכנגד חשבונית מס כחוק מטעם פמילי נדל"ן והשקעות בע"מ ו/או פמילי תיווך בע"מ.
8. הלקוח מאשר שהומלץ לו על ידי המתווך להסתייע בשרותי עורך דין ו/או מומחים אחרים לפי העניין והצורך במהלך העסקה.
9. בחתימתי מטה הנני מאשר לחברת רימקס לעדכן אותי בנכסים מוצעים למכירה ועדכונים שוטפים על אופן השיווק אפשרויות מימון ובכלל.""",
"seller_both": _PARTIES + """
הסכם והזמנה זו מתייחסים לנכס שפרטיו רשומים בנספח להלן וכן לכל עסקת מקרקעין אחרת שתתפתח בעסקה זו.
1. הלקוח מצהיר כי הינו בעל הזכויות המלאות בנכס המקרקעין המתואר לעיל והמהווה חלק בלתי נפרד מהסכם זה (להלן "הנכס") או שהינו מורשה מטעם בעל/י הזכויות למוכרו ו/או להשכירו. הלקוח מצהיר כי הובהר לו כי פרטי הנכס יועמדו לידיעת קונים/שוכרים/מתווכים כדי לקדם את שיווק הנכס וכן שפרטי הנכס שמסר למתווך והרשומים בנספח הינם הפרטים המהותיים, הנכונים והמלאים.
2. הלקוח מתחייב להמציא למתווך מיידית נסח רישום או אישור זכויות מהמנהל ו/או החברה המשכנת, עדכניים.
3. הלקוח ישלם למתווך עבור פעולת התיווך מיד עם חתימת הסכם מחייב למכירת או השכרת הנכס (עד 3 ימי עסקים מחתימת הסכם מחייב) בסכומים המפורטים בסעיף 4.
4. דמי התיווך שהלקוח מתחייב לשלמם בהתאם לאמור בסעיף 3 לעיל יהיו כדלקמן:
   4.1  במכירה SALE_FEE ממחיר המכירה הכולל של הנכס, בתוספת מע"מ.
   4.2  בכל מקרה עמלת התיווך לא תפחת מ-26,500 ש"ח + מע"מ (עמלת מינימום בנכסים מתחת ל-1,325,000 ש"ח).
   4.3  בהשכרה: דמי שכירות של RENT_FEE בתוספת מע"מ.
   4.4  האמור לעיל בא בנוסף לזכותו של המתווך לגבות דמי תיווך מהקונה/שוכר.
   4.5  במידה ותיחתם עסקה שלא בידיעת המתווך/משרד התיווך ו/או אי תשלום שכ"ט תוך 30 יום מיום ביצוע העסקה, יפוצה המתווך ב-1% + מע"מ נוספים ללא הוכחת נזק או חודש שכירות נוסף (בשכירות בלבד).
5. הלקוח מאשר כי עם מכירת הנכס המתווך יוכל להודיע לציבור כי הנכס נמכר.
6. הלקוח מאשר שהומלץ לו על ידי המתווך להסתייע בשירותי עורך דין ו/או מומחים אחרים לפי העניין והצורך במהלך העסקה.
7. הלקוח מצהיר כי ידוע לו כי דמי התיווך ייגבו על ידי מנהל המשרד וכנגד חשבונית מס כחוק מטעם פמילי נדל"ן והשקעות בע"מ ו/או פמילי תיווך בע"מ.
8. בחתימתי מטה הנני מאשר לחברת רימקס לעדכן אותי בנכסים מוצעים למכירה ועדכונים שוטפים על אופן השיווק אפשרויות מימון ובכלל.""",
"seller_sell": "",
"exclusive": _PARTIES + """
הסכם זה מהווה חלק בלתי נפרד מהסכם הזמנת שירותי תיווך מספר CON_REF_ID אשר נחתמה בין הצדדים ביום CON_REF_DATE
ומתייחס לנכס שפרטיו רשומים לעיל בהזמנה כאמור (להלן: "הנכס") וכן לכל עסקת מקרקעין אחרת שתתפתח מהסכם והזמנה אלו.
1. הלקוח מצהיר בזאת כי הינו בעל הזכויות המלאות ב"נכס" ומהווה חלק בלתי נפרד מהסכם זה, או שהינו מורשה מטעם בעל/י הזכויות בנכס למוכרו ו/או להשכירו. הלקוח מצהיר כי הובהר לו כי פרטי הנכס יועברו לידיעת קונים/שוכרים/מתווכים כדי לקדם את שיווק הנכס וכן שפרטי הנכס שמסר למתווך והרשומים בנספח הינם הפרטים המהותיים, הנכונים והמלאים.
2. הלקוח מתחייב להמציא למתווך מיידית נוסח רישום או אישור זכויות מהמנהל ו/או החברה המשכנת, עדכניים. הלקוח מייפה בזה את כוחו של המתווך או באי כוחו לפנות ולקבל בשמו ועבורו את כל הידע הדרוש לשיווק הנכס מכל רשות, משרד, עירייה, אדם או גוף כלשהוא ולמסרם ללקוחות פוטנציאליים לצורך שיווק הנכס.
3. הלקוח מזמין מהמתווך שירותי תיווך ומסמיך אותו לפעול עבורו באופן בלעדי לשיווק הנכס לתקופה מיום EXCLUSIVE_FROM ועד יום EXCLUSIVE_TO (להלן: "תקופת הבלעדיות"). עם גמר תקופת הבלעדיות יהווה הסכם זה הזמנת שירותי תיווך רגילה, ללא בלעדיות, של הלקוח מהמתווך. המתווך יוכל אז לשווק את הנכס ואם הנכס יירכש כתוצאה מטיפול המתווך יהיה המתווך זכאי לדמי תיווך כמפורט להלן בסעיף 5.
4. הלקוח ישלם למתווך עבור פעולת התיווך, מיד עם חתימת הסכם מחייב למכירת או השכרת הנכס, דמי תיווך בשיעורים המפורטים בסעיף 5 להלן, וזאת בכל מקרה אם ההסכם ייחתם במהלך תקופת הבלעדיות ובהמשך לסעיף 14ב' לחוק המתווכים. במידה והנכס ימכר/יושכר ע"י המתווך לאחר תקופת הבלעדיות יהיה זכאי המתווך לדמי התיווך בשיעורים המפורטים בסעיף 5.
5. דמי התיווך שהלקוח מתחייב בזה לשלמם, בהתאם לאמור בסעיף 4 לעיל הם בהתאם למפורט ומוסכם בהסכם הזמנת שירותי תיווך מספר CON_REF_ID מיום CON_REF_DATE.
6. הלקוח מצהיר כי ידוע לו כי דמי התיווך ייגבו על ידי המתווך הח"מ וכנגד חשבונית מס כחוק מטעם פמילי נדל"ן והשקעות בע"מ ו/או פמילי תיווך בע"מ.
7. הלקוח מאשר שהומלץ לו ע"י המתווך להסתייע בשרותי עורך דין ו/או מומחים אחרים לפני העניין והצורך במהלך העסקה.
8. המתווך ירכז את כל הפעולות לשיווקו של הנכס בתקופת הבלעדיות. הלקוח מתחייב כי בתקופה זו לא יבקש ו/או יקבל שירותי תיווך לשיווק הנכס מכל מתווך אחר וכי כל קשר ו/או משא ומתן בינו לבין מתווכים אחרים ו/או קונים ו/או שוכרים מיועדים יעשה אך ורק דרך המתווך ובאמצעותו. הלקוח מצהיר כי ידוע לו שהפרת סעיף זה עלולה לפגוע ביכולתו של המתווך, בחוסר תום לב, לשמש כגורם היעיל בעסקה, וכי במקרה של הפרה יהיה המתווך זכאי כפיצוי למלוא העמלה שהייתה מגיעה לו, בנוסף לכיסוי כל נזק אחר אשר נגרם לו כתוצאה מההפרה, בכפוף לסעיף 14 (ב) לחוק המתווכים.
9. הלקוח יביא את עובדת התקשרותו בהסכם זה לידיעת הפונים אליו ישירות ובמיוחד לכל מתווך אחר ו/או קונה ו/או שוכר עמם היה קשור בעבר. כמו כן יביא לסיומה המיידי של כל התחייבות קיימת הסותרת התחייבויותיו עפ"י הסכם זה. המתווך מתחייב לפעול בשקידה, במסירות ובנאמנות ולשתף מתווכים ומשרדי תיווך אחרים במציאת קונים מעוניינים ולבנות ולבצע תכנית שיווקית ופרסומית לקידום שיווק הנכס. כל זאת בהתאם לשיקול דעתו המקצועית ובהתאם למפרט בטופס פעולות שיווקיות המצורף להזמנה זו.
10. מובן וידוע ללקוח בזאת שהלקוח ממנה את המתווך להיות הגורם הפעיל והיחיד שיפעל לקידום מכירת ו/או השכרת הנכס.
11. בחתימתי מטה הנני מאשר לחברת רימקס לעדכן אותי בנכסים מוצעים למכירה ועדכונים שוטפים על אופן השיווק אפשרויות מימון ובכלל.""",
"shtaf": "",
}

def _contract_title(ctype):
    return {"buyer_both": "הזמנת שירותי תיווך לקניה/שכירות נכס מקרקעין",
            "buyer_buy": "הזמנת שירותי תיווך לקניית נכס מקרקעין",
            "buyer_rent": "הזמנת שירותי תיווך לשכירות נכס מקרקעין",
            "seller_both": "הזמנת שירותי תיווך למכירת ו/או השכרת נכס מקרקעין",
            "seller_sell": "הזמנת שירותי תיווך למכירת נכס מקרקעין",
            "exclusive": "הזמנת שירותי תיווך בבלעדיות",
            "shtaf": "הסכם שיתוף פעולה"}.get(ctype, "הזמנת שירותי תיווך")

_CONTRACT_FALLBACK = {"seller_sell": "seller_both"}

def _contract_text(ctype):
    """הנוסח האפקטיבי: מה שנשמר ב-config, ואם ריק — ברירת המחדל המוטמעת (עם נפילה הגיונית)."""
    c = (_load_config().get("contracts") or {}).get(ctype)
    if c is not None and str(c).strip() != "":
        return c
    d = _DEFAULT_CONTRACTS.get(ctype, "")
    if d.strip():
        return d
    fb = _CONTRACT_FALLBACK.get(ctype)
    return _DEFAULT_CONTRACTS.get(fb, "") if fb else ""

@app.route("/api/dev/contract", methods=["GET", "POST"])
def api_dev_contract():
    """נוסחי ההסכמים (ניתנים לעריכה במנהל). GET=קריאה, POST {type, body}=שמירה."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    if request.method == "GET":
        eff = {t: _contract_text(t) for t in _CONTRACT_TYPES}
        return jsonify({"ok": True, "types": _CONTRACT_TYPES, "contracts": eff})
    body = request.get_json(silent=True) or {}
    ctype = (body.get("type") or "").strip()
    text = body.get("body")
    if ctype not in _CONTRACT_TYPES or not isinstance(text, str):
        return jsonify({"ok": False, "reason": "bad"}), 400
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        cfg.setdefault("contracts", {})[ctype] = text
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון נוסח הסכם", _CONTRACT_TYPES.get(ctype, ctype))
    return jsonify({"ok": ok})

@app.route("/api/sign/contract")
def api_sign_contract():
    """נוסח ההסכם לסוכן (לא רק למפתח) — לשימוש במסך החתימה."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    t = (request.args.get("type") or "buyer_both").strip()
    return jsonify({"ok": True, "type": t, "body": _contract_text(t), "title": _contract_title(t), "types": _CONTRACT_TYPES})

@app.route("/api/sign/validate_id")
def api_sign_validate_id():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    return jsonify({"ok": True, "valid": _valid_il_id(request.args.get("id", ""))})

def _eff_agent_ctx(s):
    """(name, phones, is_all) של הסוכן האפקטיבי לבקשה (כולל צפייה-כסוכן + צוות)."""
    name = s.get("name", "")
    as_name = request.args.get("as", "").strip() if s.get("role") in ("admin", "coordinator") else ""
    if as_name: name = as_name
    phs = set(_phones_for_name(name))
    if s.get("phone"): phs.add(_last9(s["phone"]))
    t = _team_for(name)
    if t: phs |= t[0]
    is_all = (s.get("role") == "admin" and not as_name)
    return name, phs, is_all

@app.route("/api/sign/clients")
def api_sign_clients():
    """לקוחות לבחירה — המתקשרים בהיסטוריית השיחות של הסוכן (טלפון + תאריך אחרון)."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    name, phs, is_all = _eff_agent_ctx(s)
    calls = web_fetch_raw("שיחות")
    if not is_all and phs:
        calls = [c for c in calls if _last9(c.get("agent_phone", "")) in phs]
    seen = {}
    for c in sorted(calls, key=lambda c: _epoch_from_iso(c.get("received_at", "")), reverse=True):
        ph = _last9(c.get("caller_phone", ""))
        if not ph or ph in seen: continue
        disp = _il_phone(c.get("caller_phone", ""))[0]
        seen[ph] = {"phone": disp, "date": (_fmt_il_dt(c.get("received_at", "")) or "")[:10]}
        if len(seen) >= 200: break
    return jsonify({"ok": True, "clients": list(seen.values())})

@app.route("/api/sign/properties")
def api_sign_properties():
    """נכסים לבחירה — המודעות של הסוכן (כתובת + מחיר)."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    name, phs, is_all = _eff_agent_ctx(s)
    if request.args.get("all") == "1":   # השלמה אוטומטית מכל מודעות המשרד (לא רק של הסוכן)
        is_all = True
    rows = fetch_sheet_rows()
    out, seen = [], set()
    for r in rows:
        if not is_all and not _agent_owns_row(r, name, phs): continue
        street = (r.get("רחוב1", "") or r.get("רחוב", "") or r.get("כתובת", "") or "").strip()
        house = (r.get("מספר בית", "") or r.get("מס בית", "") or r.get("מס' בית", "") or r.get("בית", "") or "").strip()
        if street and house and house not in street.split():
            street = (street + " " + house).strip()
        city = (r.get("עיר / ישוב", "") or r.get("עיר", "") or r.get("ישוב", "") or "").strip()
        addr = ", ".join([x for x in [street, city] if x])
        if not addr or addr in seen: continue
        seen.add(addr)
        out.append({"address": addr, "price": (r.get("מחיר", "") or "").strip(),
                    "type": (r.get("סוג נכס", "") or "").strip(),
                    "rooms": (r.get("חדרים", "") or "").strip(),
                    "size": (r.get('מ"ר', "") or r.get("מ״ר", "") or "").strip()})
        if len(out) >= 300: break
    return jsonify({"ok": True, "properties": out})

@app.route("/api/sign/submit", methods=["POST"])
def api_sign_submit():
    """שמירת חתימה דיגיטלית → רשומה בגליון 'חתימות' (נכנס לדוחות) + שמירת המסמך לצפייה."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    docs = body.get("docs") or []
    agent = (body.get("agent") or s.get("name", "")).strip()
    client = (body.get("client") or "").strip()
    cid = re.sub(r"\D", "", (body.get("cid") or ""))
    address = (body.get("address") or "").strip()
    phone = (body.get("phone") or "").strip()
    notes = (body.get("notes") or "").strip()
    signature = body.get("signature") or ""
    header = body.get("header") or ""
    if not docs:
        return jsonify({"ok": False, "reason": "no_docs"}), 400
    if not cid:
        return jsonify({"ok": False, "reason": "no_id"}), 400
    # פיצול כתובת לרחוב + עיר (כמו בגליון: address נפרד מ-city)
    city = ""
    if "|" in address:
        pass  # מתעניין על כמה נכסים — לא מפצלים לעיר
    elif "," in address:
        _p = address.rsplit(",", 1)
        address, city = _p[0].strip(), _p[1].strip()
    else:
        _c = _detect_city(address)
        if _c and _c != "אחר": city = _c
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        now_iso = _dt.datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat()
    except Exception:
        now_iso = _dt.datetime.utcnow().isoformat()
    eid = cid if cid else ("SIGN%d" % int(time.time() * 1000))   # event_id = ת"ז הלקוח (משותף לכל מסמכי החתימה)
    token = _secrets.token_urlsafe(12)
    base = (os.environ.get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/")
    link = base + "/s/" + token
    # ⚡ מהירות (בקשת אייל 13/07): סינכרוני רק שמירת המסמך החתום (חיוני); שורות
    # הגיליון, הקונה, הפוש וה-SMS לסוכן — ברקע. _recent_signs_add שומר נראות מיידית.
    recs = []
    for d in docs:
        _srec = {"event_id": eid, "deal_type": d.get("deal_type", ""), "agent": agent,
                 "client_name": client, "address": address, "city": city,
                 "commission_pct": link, "received_at": now_iso, "notes": notes}
        recs.append(_srec)
    doc_saved = False; doc_resp = ""
    try:   # שמירת המסמך לעמוד הציבורי (טוקן → הסכם + חתימה) — סינכרוני, זה המסמך החתום
        jd = _signdoc_save({
            "doc_token": token, "event_id": eid, "status": "signed",
            "header": header, "docs": _json.dumps(docs, ensure_ascii=False),
            "signature": signature, "signed_at": now_iso})
        doc_saved = bool(jd and jd.get("ok"))
        doc_resp = str(jd)[:200] if jd is not None else "None (אין תגובה)"
    except Exception as _e:
        doc_saved = False; doc_resp = "EXC: " + str(_e)[:160]
    if doc_saved:
        for _r in recs:
            _recent_signs_add(_r)   # נראות מיידית במסך החתימות
    s_name, s_role, s_phone = s.get("name", ""), s.get("role", ""), s.get("phone", "")
    def _sign_submit_bg():
        try:
            for _r in recs:
                _buyers_apps_post("addsigning", _r)
            _cache_clear("signings_sheet")
            _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
            _log_activity(s_name, s_role, s_phone, "החתמה דיגיטלית", (client + " · " + address).strip(" ·"))
            # רק חתימת קונה (לא מוכר/בלעדיות) נכנסת אוטומטית ל"קונים שלי" של הסוכן
            if any(str(d.get("deal_type", "")).startswith("CLIENT") for d in docs):
                _add_buyer_from_signing(agent, client, phone, address, "מהחתמה דיגיטלית",
                                        deal_kind=("rent" if any("RENT" in str(d.get("deal_type", "")).upper() for d in docs) else "sale"))
            # פוש לכל המנהלים על חתימה חדשה + SMS לסוכן
            _notify_managers_signing("נחתם", client, agent, address)
            _sms_agent_signing(client, agent, address, link)
            # עותק ללקוח (החתמה במקום — בקשת אייל 05/08): קישור להסכם החתום שלו.
            # בהחתמה מרחוק הלקוח כבר מחזיק את הקישור; כאן הוא חתם על מכשיר הסוכן.
            try:
                _cl9 = _last9(phone)
                if _cl9:
                    _first = (client or "").split()[0] if (client or "").strip() else ""
                    web_send_sms(_cl9, "שלום" + ((" " + _first) if _first else "") +
                                 ", ההסכם שחתמת מטעם RE/MAX Family זמין לצפייה ולשמירה:\n" + link)
            except Exception:
                pass
        except Exception as _bge:
            log.error(f"sign submit bg error: {_bge}")
    if doc_saved:   # נכשל = הסוכן ינסה שוב — לא כותבים שורות שיוכפלו בניסיון הבא
        import threading as _thr
        _thr.Thread(target=_sign_submit_bg, daemon=True).start()
    return jsonify({"ok": doc_saved, "event_id": eid, "link": link, "doc_saved": doc_saved, "doc_resp": doc_resp})

def _sign_now_iso():
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat()
    except Exception:
        return _dt.datetime.utcnow().isoformat()

# ── זיהוי נכס מהחתמה בנכסי המשרד/שת"פ + ממוצע נצפים (בקשת אייל 13/07) ──────────
def _sign_addr_key(s):
    """מפתח השוואת כתובות: אותיות/ספרות בלבד — עמיד לפסיקים, גרשים, רווחים וקריית/קרית."""
    return re.sub(r"[^א-ת0-9a-z]", "", str(s or "").lower().replace("קריית", "קרית"))

def _office_prop_index():
    """אינדקס מפתח-כתובת → שורת נכס מגיליון המשרד. cache 60ש' — נבנה פעם, לא פר-בקשה."""
    c = _cache_get("sign_office_idx", 60)
    if c is not None:
        return c
    idx = {}
    for r in fetch_sheet_rows():
        street = (r.get("כתובת", "") or r.get("רחוב1", "") or r.get("רחוב", "") or "").strip()
        house = (r.get("מספר בית", "") or r.get("מס בית", "") or r.get("מס' בית", "") or r.get("בית", "") or "").strip()
        if street and house and house not in street.split():
            street = (street + " " + house).strip()
        if not street:
            continue
        city = (r.get("עיר / ישוב", "") or r.get("עיר", "") or "").strip()
        idx.setdefault(_sign_addr_key(street + city), r)
        idx.setdefault(_sign_addr_key(street), r)   # חתימות נשמרות לעיתים בלי עיר
    _cache_put("sign_office_idx", idx)
    return idx

def _excl_key_list():
    """שת"פ עם מפתח-כתובת מחושב מראש: [(key, row)]. cache 300ש' (כמו מקור השת"פ).
    ⚡ ביצועים: בלי זה _sign_prop_lookup טיקנן את כל השת"פ מחדש בכל קריאה —
    ~200K הפעלות regex לבקשת /api/signatures אחת (סעיף 2 בדוח הביצועים 14/07)."""
    c = _cache_get("excl_key_list", 300)
    if c is not None:
        return c
    out = []
    for r in (fetch_external_exclusives() or []):
        ks = _sign_addr_key(r.get("street", ""))
        if ks:
            out.append((ks, r))
    _cache_put("excl_key_list", out)
    return out

def _price_int(v):
    d = re.sub(r"[^0-9]", "", str(v or ""))
    return int(d) if d else 0

def _office_prop_desc(r):
    """תיאור נכס משרד לשדה 'מה מחפש' של הקונה — סוג · חדרים · מ"ר · קומה · שכונה · עיר · עד מחיר."""
    size = (r.get('מ"ר', "") or r.get("מ״ר", "") or "").strip()
    parts = [(r.get("סוג נכס", "") or "").strip(),
             ((r.get("חדרים", "") or "").strip() + " חדרים") if (r.get("חדרים", "") or "").strip() else "",
             (size + ' מ"ר') if size else "",
             ("קומה " + (r.get("קומה", "") or "").strip()) if (r.get("קומה", "") or "").strip() else "",
             (r.get("שכונה", "") or "").strip(),
             (r.get("עיר / ישוב", "") or r.get("עיר", "") or "").strip()]
    p = _price_int(r.get("מחיר", ""))
    if p:
        parts.append("עד {:,}".format(p))
    return " · ".join([x for x in parts if x])

def _sign_prop_lookup(address, city="", idx=None, excl=None):
    """מזהה את נכס החתימה — קודם בנכסי המשרד, אחר-כך בשת"פ.
    מחזיר {desc, price, src} או None. idx/excl ניתנים להעברה כדי לא לבנות מחדש בלולאה."""
    addr = str(address or "").strip()
    if not addr:
        return None
    if idx is None:
        idx = _office_prop_index()
    k_city = _sign_addr_key(addr + str(city or ""))
    k = _sign_addr_key(addr)
    r = idx.get(k_city) or idx.get(k)
    if r:
        return {"desc": _office_prop_desc(r), "price": _price_int(r.get("מחיר", "")), "src": "משרד"}
    if len(k) < 6:   # כתובת קצרה מדי — התאמת-הכלה בשת"פ תיתן זיהויי שווא
        return None
    # שת"פ — מהרשימה המטוקננת-מראש (cache); הפרמטר excl נשמר לתאימות אך אינו נדרש עוד
    for ks, r in _excl_key_list():
        if (k in ks or ks in k):
            desc = " · ".join([x for x in [
                str(r.get("dest", "") or "").strip(),
                str(r.get("desti", "") or "").strip()[:120]] if x])
            p = _price_int(r.get("price", ""))
            if p:
                desc = (desc + " · " if desc else "") + "עד {:,}".format(p)
            return {"desc": desc, "price": p, "src": 'שת"פ'}
    return None

def _client_view_prices(client, kind="sale", idx=None, excl=None, sigs=None):
    """מחירי כל הנכסים שהלקוח חתם עליהם (טפסי מתעניין CLIENT_*), מופרד מכירה/שכירות
    כדי שממוצע קנייה לא יתערבב בשכר-דירה. לפי זיהוי הכתובת בנכסי המשרד/שת"פ."""
    ck = _canon_key(client)
    if not ck:
        return []
    if sigs is None:
        try:
            sigs = get_signings()
        except Exception:
            return []
    if idx is None:
        idx = _office_prop_index()
    prices = []
    for g in sigs:
        dt = str(g.get("deal_type", "")).upper()
        if not dt.startswith("CLIENT"):
            continue
        if ("RENT" in dt) != (kind == "rent"):
            continue
        if _canon_key(g.get("client_name", "")) != ck:
            continue
        for part in str(g.get("address", "") or "").split("|"):
            info = _sign_prop_lookup(part.strip(), g.get("city", ""), idx=idx, excl=excl)
            if info and info.get("price"):
                prices.append(info["price"])
    return prices

def _merge_buyer_search(r, desc, budget_txt=""):
    """קונה קיים שחתם על נכס נוסף — מוסיף את תיאור הנכס ל'מה מחפש' (בלי לדרוס טקסט של הסוכן)."""
    try:
        if not desc or not r.get("row"):
            return
        old = str(r.get("search", "") or "").strip()
        if _sign_addr_key(desc) and _sign_addr_key(desc) in _sign_addr_key(old):
            return   # התיאור הזה כבר שם
        up = {"row": str(r.get("row")), "search": ((old + " · " + desc).strip(" ·") if old else desc)[:480]}
        if budget_txt:
            up["budget"] = budget_txt   # ממוצע נצפים מעודכן — ייקלט אם ה-Apps Script תומך, יתעלם אחרת
        j = _buyers_apps_post("updatebuyer", up)
        if j and j.get("ok"):
            _cache_clear("buyers")
    except Exception:
        pass

def _add_buyer_from_signing(agent, client, phone="", address="", origin="החתמה דיגיטלית", deal_kind="sale"):
    """כל מתעניין שחותם / שנשלחה לו חתימה — נכנס אוטומטית כקונה אצל הסוכן (אם עוד לא קיים).
    אם הנכס מזוהה בנכסי המשרד/שת"פ — הקונה נכנס עם תיאור הנכס (search) ותקציב = ממוצע הנצפים;
    ואם הקונה כבר קיים — התיאור החדש מתווסף ל'מה מחפש' שלו (להתאמות נוספות)."""
    try:
        agent = (agent or "").strip()
        client = (client or "").strip()
        phone = (phone or "").strip()
        if not (client or phone):
            return False
        ps = list(_phones_for_name(agent))
        agent_phone = ps[0] if ps else ""
        ln = _last9(phone)
        # זיהוי הנכס/ים שנחתמו בנכסי המשרד/שת"פ — תיאור לקונה + ממוצע הנצפים כתקציב
        info_desc, budget_txt = "", ""
        try:
            idx = _office_prop_index()
            excl = fetch_external_exclusives() or []
            infos = [x for x in (_sign_prop_lookup(a.strip(), idx=idx, excl=excl)
                                 for a in str(address or "").split("|")) if x]
            if infos:
                info_desc = next((x["desc"] for x in infos if x.get("desc")), "")
                vals = _client_view_prices(client, kind=deal_kind, idx=idx, excl=excl)
                for p in [x["price"] for x in infos if x.get("price")]:
                    if p not in vals:   # החתימה הנוכחית אולי טרם נחתה בגיליון — צירוף בלי כפל
                        vals.append(p)
                if vals:
                    budget_txt = "{:,}".format(sum(vals) // len(vals))
        except Exception:
            pass
        # מניעת כפילות — אם כבר קיים קונה לאותו סוכן עם אותו טלפון (או אותו שם כשאין טלפון);
        # קונה קיים שחתם על נכס נוסף — מקבל את התיאור החדש ל"מה מחפש" (התאמות נוספות).
        # קריטי: אם קריאת הקונים נכשלת — לא יוצרים חדש (למנוע כפילות מדיווח אייל 19/07),
        # אלא מוותרים על ההוספה האוטומטית הפעם. קאש נקי + ניסיון חוזר לצמצם race/תקלה.
        _dedup_ok = False
        for _attempt in range(2):
            try:
                if _attempt:
                    _cache_clear("buyers")
                rows = _fetch_manual_buyers()
                _dedup_ok = True
                ak = _canon_key(agent)
                ck = _canon_key(client)
                for r in rows:
                    same_agent = (_canon_key(r.get("agent", "")) == ak) or (
                        agent_phone and _last9(r.get("agent_phone", "")) == _last9(agent_phone))
                    if not same_agent:
                        continue
                    # התאמה לפי טלפון או לפי שם (טלפון בפורמט שונה לא יוצר כפיל)
                    if (ln and _last9(r.get("phone", "")) == ln) or (ck and _canon_key(r.get("name", "")) == ck):
                        _merge_buyer_search(r, info_desc, budget_txt)
                        return False
                break
            except Exception:
                _dedup_ok = False
        if not _dedup_ok:
            log.warning("add_buyer_from_signing: buyers read failed — skipping auto-add to avoid duplicate")
            return False
        from datetime import datetime, timezone, timedelta
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Asia/Jerusalem"))
        except Exception:
            now = datetime.now(timezone.utc) + timedelta(hours=3)
        summary = origin + ((" · " + address) if address else "")
        payload = {
            "date": now.strftime("%d/%m/%Y %H:%M"),
            "name": client, "phone": phone, "budget": budget_txt, "summary": summary,
            "agent": agent, "agent_phone": agent_phone, "search": info_desc,
        }
        j = _buyers_apps_post("addbuyer", payload)
        if j and j.get("ok"):
            _cache_clear("buyers")
            # addbuyer עשוי להתעלם מ-search (תלוי בגרסת ה-Apps Script) — מוודאים שהתיאור
            # נכתב דרך updatebuyer (עמודה 'חיפוש' — מסלול מוכח). no-op אם כבר נקלט.
            if info_desc:
                try:
                    ak2 = _canon_key(agent)
                    for r in _fetch_manual_buyers():
                        if _canon_key(r.get("agent", "")) != ak2 and not (
                                agent_phone and _last9(r.get("agent_phone", "")) == _last9(agent_phone)):
                            continue
                        if (ln and _last9(r.get("phone", "")) == ln) or (
                                (not ln) and client and _canon_key(r.get("name", "")) == _canon_key(client)):
                            _merge_buyer_search(r, info_desc, budget_txt)
                            break
                except Exception:
                    pass
            return True
    except Exception:
        pass
    return False

def _manager_push_ids():
    """external_id (=9 ספרות אחרונות של הטלפון) של כל מי שמוגדר 'מנהל' — לקבלת פוש על חתימות.
    כולל גם 'owner' כדי שמכשיר הבעלים הקיים (שרשום כ-owner ב-OneSignal) ימשיך לקבל."""
    ids = set()
    for p in ADMIN_PHONES:
        l = _last9(p)
        if l: ids.add(l)
    for ph, role in (_load_config().get("roles") or {}).items():
        if _ROLE_SCOPE.get(role) == "admin":
            l = _last9(ph)
            if l: ids.add(l)
    ids.add(OWNER_PUSH_ID)   # אייל (במקום אליאס "owner" שירד מ-OneSignal)
    return [i for i in ids if i]

def _sms_agent_signing(client, agent, address, link=""):
    """SMS לנייד האישי של הסוכן על חתימה שהושלמה — עובד גם כשהוואטסאפ האוטומטי מושהה.
    לא לוירטואלי (מרכזיה — לא מקבל SMS)."""
    try:
        _v = _last9(_vphone_for_name(agent or "") or "")
        targets = sorted(set(_last9(p) for p in _phones_for_name(agent or "")
                             if _last9(p) and _last9(p) != _v))
        if not targets:
            log.error(f"sms_agent_signing: no phone for agent '{agent}'")
            return
        msg = "נחתם: " + (client or "לקוח")
        if address: msg += " · " + address
        if link:    msg += "\nלמסמך החתום: " + link
        def _send():
            for _p in targets[:2]:
                try: web_send_sms(_p, msg)
                except Exception: pass
        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        pass

def _notify_managers_signing(status_label, client, agent, address):
    """פוש לכל המנהלים על חתימה שנכנסה לטאב 'חתימות' — לא חוסם את התשובה."""
    try:
        ids = set(_manager_push_ids())
        for _ph in _phones_for_name(agent or ""):   # + הסוכן שביצע את החתימה
            _l = _last9(_ph)
            if _l: ids.add(_l)
        ids = list(ids)
        if not ids:
            return
        body = status_label + ": " + (client or "לקוח")
        if agent:   body += " · 👤 " + agent
        if address: body += " · " + address
        threading.Thread(target=send_push, args=("חתימה חדשה ✍️", body, ids), daemon=True).start()
    except Exception:
        pass

def _wa_signing(client, agent, address, link):
    """וואטסאפ לסוכן + מנהלים על כל חתימה שנחתמה — לא חוסם את התשובה."""
    try:
        msg = "✍️ *חתימה חדשה*\n"
        if client:  msg += "לקוח: " + client + "\n"
        if agent:   msg += "סוכן: " + agent + "\n"
        if address: msg += "נכס: " + address + "\n"
        if link:    msg += "למסמך החתום:\n" + link
        agent_phones = set(p for p in _phones_for_name(agent) if p)   # לסוכן האישי
        def _send():
            for last9 in agent_phones:
                wa = _wa_phone(last9)
                if wa:
                    try: send_text(wa, msg)
                    except Exception: pass
            if WA_GROUP_SIGNATURES:                                    # לקבוצת "חתימות" של המנהלים
                try: send_text(WA_GROUP_SIGNATURES, msg)
                except Exception: pass
        if _wa_auto_on():   # מושהה כברירת מחדל — בקשת אייל 06/07
            threading.Thread(target=_send, daemon=True).start()
    except Exception:
        pass

@app.route("/api/sign/send_remote", methods=["POST"])
def api_sign_send_remote():
    """שלב 2 — שליחת קישור חתימה ללקוח (SMS+WhatsApp). יוצר חתימה 'ממתינה' ללא קישור עד שהלקוח חותם."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    docs = body.get("docs") or []
    agent = (body.get("agent") or s.get("name", "")).strip()
    client = (body.get("client") or "").strip()
    phone = (body.get("phone") or "").strip()
    address = (body.get("address") or "").strip()
    notes = (body.get("notes") or "").strip()
    header = body.get("header") or ""
    if not docs:
        return jsonify({"ok": False, "reason": "no_docs"}), 400
    if not client:
        return jsonify({"ok": False, "reason": "no_client"}), 400
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 9:
        return jsonify({"ok": False, "reason": "bad_phone"}), 400
    last9 = digits.lstrip("0")[-9:]
    # פיצול כתובת לרחוב + עיר
    city = ""
    if "|" in address:
        pass  # מתעניין על כמה נכסים — לא מפצלים לעיר
    elif "," in address:
        _p = address.rsplit(",", 1)
        address, city = _p[0].strip(), _p[1].strip()
    else:
        _c = _detect_city(address)
        if _c and _c != "אחר": city = _c
    now_iso = _sign_now_iso()
    token = _secrets.token_urlsafe(12)
    base = (os.environ.get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/")
    link = base + "/s/" + token
    # ⚡ מהירות (בקשת אייל 13/07): הסוכן חיכה 10-20 שניות ("האפליקציה תקועה") כי כל
    # קריאות ה-Apps Script רצו סינכרונית. עכשיו: סינכרוני רק מה שחיוני לפני התשובה —
    # שמירת המסמך (הקישור ב-SMS חייב לעבוד) + ה-SMS עצמו. שורות הגיליון, הקונה
    # האוטומטי והיומן רצים ברקע; הנראות המיידית במסך החתימות נשמרת דרך _recent_signs_add.
    # בלעדיות = הסכם נפרד (דרישה משפטית, 16/07): המוכר נחתם ראשון; לבלעדיות טוקן,
    # מספר הסכם וחתימה משלה; ומספר הסכם המוכר נשתל בשורת "מספר ___" שבגוף הבלעדיות.
    token2 = ""
    _excl_i = next((i for i, d in enumerate(docs)
                    if "OWNER_EXCLUSIVE" in str(d.get("deal_type", "")).upper()), None)
    if _excl_i is not None and len(docs) >= 2:
        token2 = _secrets.token_urlsafe(12)
        _num1 = "%05d" % ((sum(ord(c) for c in token) * 7) % 90000 + 10000)   # אותה נוסחת מספר של עמוד הצפייה
        _d2 = dict(docs[_excl_i])
        # כל המופעים של "מספר ____" (המבוא + סעיף 5), עמיד לתווי כיווניות נסתרים ולקו מקוף/מפריד
        _b2, _nsub = re.subn(r"(מספר|מס['׳]?)[\s‎‏‪-‮]*[_–—־]{2,}",
                             "\\g<1> " + _num1, str(_d2.get("body", "")))
        if _nsub:
            _d2["body"] = _b2
            log.info(f"sign split: seller number injected into {_nsub} blank(s) in exclusivity body")
        else:
            log.warning("sign split: exclusivity number blank not found in contract body — number shown in title only")
        _d2["title"] = str(_d2.get("title", "")).strip() + " · להסכם מס' " + _num1
        docs1 = [dict(d) for i, d in enumerate(docs) if i != _excl_i]
        docs1[0]["next_token"] = token2
        docs1[0]["next_title"] = str(docs[_excl_i].get("title", "")).strip() or "הסכם בלעדיות"
        # שרשור סימטרי (05/08): לקוח שנכנס מקישור הבלעדיות (ה-SMS הכפול) מנותב
        # אחרי חתימתה גם להסכם המוכר — בלי זה חצי מהזוג נשאר "ממתין לחתימה"
        _d2["next_token"] = token
        _d2["next_title"] = str(docs1[0].get("title", "")).strip() or "הסכם מוכר"
        docs2 = [_d2]
    else:
        docs1, docs2 = list(docs), None
    recs = []
    for d in docs:
        _ev = token2 if (token2 and "OWNER_EXCLUSIVE" in str(d.get("deal_type", "")).upper()) else token
        _srec = {"event_id": _ev, "doc_token": _ev, "deal_type": d.get("deal_type", ""), "agent": agent,
                 "client_name": client, "address": address, "city": city,
                 "commission_pct": "", "received_at": now_iso, "notes": notes}
        recs.append(_srec)
    # שמירת המסמכים במצב 'pending' — סינכרוני: הקישור ב-SMS חייב לעבוד, וגם הסכם ההמשך
    doc_saved = False
    try:
        jd = _signdoc_save({
            "doc_token": token, "event_id": token, "status": "pending",
            "header": header, "docs": _json.dumps(docs1, ensure_ascii=False),
            "signature": "", "signed_at": ""})
        doc_saved = bool(jd and jd.get("ok"))
    except Exception:
        doc_saved = False
    if doc_saved and docs2 is not None:
        try:
            jd2 = _signdoc_save({
                "doc_token": token2, "event_id": token2, "status": "pending",
                "header": header, "docs": _json.dumps(docs2, ensure_ascii=False),
                "signature": "", "signed_at": ""})
            if not (jd2 and jd2.get("ok")):
                doc_saved = False
        except Exception:
            doc_saved = False
    if not doc_saved:
        # אין מסמך = הקישור שבור — לא שולחים SMS ומבקשים לנסות שוב (במקום לשלוח קישור מת)
        return jsonify({"ok": False, "reason": "doc_save_failed"})
    for _r in recs:
        _recent_signs_add(_r)   # נראות מיידית ב"ממתין לחתימה" — עד שהכתיבה ברקע נוחתת
    # שליחה אוטומטית ב-SMS בלבד. וואטסאפ = אופציה ידנית לסוכן (כפתור בצד הלקוח, נשלח מהוואטסאפ של הסוכן — לא אוטומטית מהשרת)
    if token2:
        # זוג בלעדיות (בקשת אייל 05/08): שני הקישורים כבר ב-SMS הראשון — מוכר + בלעדיות
        msg = ("שלום %s,\nהתבקשת לחתום על 2 מסמכים מטעם RE/MAX Family (%s).\n"
               "הסכם מוכר — לצפייה וחתימה:\n%s\n"
               "הסכם בלעדיות — לצפייה וחתימה:\n%s" % (client, agent, link, base + "/s/" + token2))
    else:
        msg = ("שלום %s,\nהתבקשת לחתום על מסמך מטעם RE/MAX Family (%s).\nלצפייה וחתימה:\n%s" % (client, agent, link))
    sms_ok = False
    try: sms_ok = bool(web_send_sms(last9, msg))
    except Exception: sms_ok = False
    wa_link = _wa_phone(phone)   # מספר wa.me לכפתור השיתוף הידני (בלי שליחה אוטומטית)
    s_name, s_role, s_phone = s.get("name", ""), s.get("role", ""), s.get("phone", "")
    def _send_remote_bg():
        try:
            for _r in recs:
                _buyers_apps_post("addsigning", _r)
            _cache_clear("signings_sheet")
            _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
            _log_activity(s_name, s_role, s_phone, "שליחת חתימה מרחוק", (client + " · " + address).strip(" ·"))
            # רק חתימת קונה (לא מוכר/בלעדיות) — גם אם עוד לא חתם — נכנסת ל"קונים שלי"
            if any(str(d.get("deal_type", "")).startswith("CLIENT") for d in docs):
                _add_buyer_from_signing(agent, client, phone, address, "נשלחה חתימה",
                                        deal_kind=("rent" if any("RENT" in str(d.get("deal_type", "")).upper() for d in docs) else "sale"))
        except Exception as _bge:
            log.error(f"sign send_remote bg error: {_bge}")
    import threading as _thr
    _thr.Thread(target=_send_remote_bg, daemon=True).start()
    return jsonify({"ok": True, "sms": sms_ok, "phone": last9, "link": link, "waPhone": wa_link})

@app.route("/api/sign/complete", methods=["POST"])
def api_sign_complete():
    """ציבורי — הלקוח חתם מרחוק: מאמת ת״ז, שומר חתימה, מוסיף את הקישור לשורת החתימה הקיימת."""
    body = request.get_json(silent=True) or {}
    token = (body.get("token") or "").strip()
    cid = re.sub(r"\D", "", (body.get("cid") or ""))
    signature = body.get("signature") or ""
    if not token:
        return jsonify({"ok": False, "reason": "no_token"}), 400
    if not _valid_il_id(cid):
        return jsonify({"ok": False, "reason": "bad_id"}), 400
    if not signature:
        return jsonify({"ok": False, "reason": "no_signature"}), 400
    j = _signdoc_get(token)
    if not (j and j.get("ok") and j.get("found")):
        return jsonify({"ok": False, "reason": "not_found"}), 404
    doc = j.get("doc", {})
    if str(doc.get("status", "")) == "signed":
        return jsonify({"ok": False, "reason": "already_signed"}), 409
    # הוספת ת״ז לשורת ה'לקוח' בכותרת
    header = str(doc.get("header", ""))
    if cid and ("ת״ז" not in header and "ת\"ז" not in header):
        lines = header.split("\n")
        for _i, _ln in enumerate(lines):
            if _ln.startswith("לקוח"):
                lines[_i] = _ln + " · ת״ז " + cid
                break
        header = "\n".join(lines)
    now_iso = _sign_now_iso()
    base = (os.environ.get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/")
    link = base + "/s/" + token
    upd_ok = False
    try:
        ju = _signdoc_update(token, {
            "event_id": cid, "status": "signed",
            "header": header, "signature": signature, "signed_at": now_iso})
        upd_ok = bool(ju and ju.get("ok"))
    except Exception:
        upd_ok = False
    # נראות מיידית: מסמנים את גשר הנראות כ'נחתם' עכשיו — הסוכן לא ממתין לסנכרון המקור
    _recent_signs_mark_signed(token, link, cid)
    _cache_clear("signdoc:" + token)   # שהעמוד הציבורי יציג את החתימה, לא עותק ממתין מה-cache
    # השאר — שורת חתימה, קאש והתראות — ברקע: הלקוח מקבל אישור מיד אחרי שמירת המסמך
    # (אותו דפוס כמו האצת send_remote — הסינכרוני הוא רק מה שקובע הצלחה/כישלון).
    def _post_sign_bg():
        try:
            _buyers_apps_post("updatesigning", {"doc_token": token, "commission_pct": link, "event_id": cid})
        except Exception:
            pass
        # כשמקור החתימות הוא Supabase — עדכון ישיר של השורה (הקישור=נחתם), אחרת הסטטוס
        # באפליקציה מחכה לסנכרון הגיליון→Supabase ו"ממתין לחתימה" נשאר תקוע דקות ארוכות.
        try:
            if SIGNATURES_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
                from urllib.parse import quote as _q2
                rows = []
                _flt = ""
                for _key in ("doc_token", "token"):   # שם המפתח בשורת הגיליון
                    _flt = "raw->>" + _key + "=eq." + _q2(token, safe="")
                    _rr = requests.get(_sbdb.SUPABASE_URL + "/rest/v1/signatures?" + _flt + "&select=raw",
                                       headers=_sbdb._headers(), timeout=12)
                    rows = _rr.json() if _rr.status_code == 200 else []
                    if isinstance(rows, list) and rows:
                        break
                if isinstance(rows, list) and rows:
                    _raw0 = rows[0].get("raw") or {}
                    _raw0["commission_pct"] = link
                    if cid:
                        _raw0["event_id"] = cid
                    requests.patch(_sbdb.SUPABASE_URL + "/rest/v1/signatures?" + _flt,
                                   headers={**_sbdb._headers(), "Prefer": "return=minimal"},
                                   json={"raw": _raw0}, timeout=12)
                else:
                    log.warning(f"sign complete: signatures row not found in supabase for token")
        except Exception as _e:
            log.warning(f"sign complete: supabase link update failed: {_e}")
        _cache_clear("signings_sheet")
        _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
        try:
            _ag = _cl = _addr = ""
            for _ln in header.split("\n"):
                _ln = _ln.strip()
                if "הסוכן:" in _ln:
                    _ag = _ln.split("הסוכן:", 1)[1].strip()
                elif _ln.startswith("לקוח"):
                    _cl = re.split(r"\s*·\s*", _ln.split(":", 1)[-1].strip())[0].strip() if ":" in _ln else _ln[4:].strip()
                elif _ln.startswith("נכס"):
                    _addr = re.split(r"\s*·\s*", _ln.split(":", 1)[-1].strip())[0].strip()
            _notify_managers_signing("נחתם", _cl, _ag, _addr)
            _sms_agent_signing(_cl, _ag, _addr, link)
            _wa_signing(_cl, _ag, _addr, link)
        except Exception:
            pass
    if upd_ok:
        try:
            _threading.Thread(target=_post_sign_bg, daemon=True).start()
        except Exception:
            _post_sign_bg()   # נפילה חזרה לסינכרוני — שלא יאבדו התראות
    _nx, _nxt = "", ""
    try:   # הסכם-אח בזוג (מוכר↔בלעדיות): מוצע להמשך רק אם עדיין לא נחתם
        _docs0 = _json.loads(doc.get("docs") or "[]")
        _nt = str((_docs0[0].get("next_token") if _docs0 else "") or "")
        if _nt:
            _sj = _signdoc_get(_nt)
            if _sj and _sj.get("found") and str((_sj.get("doc") or {}).get("status", "")) != "signed":
                _nx = _nt
                _nxt = str((_docs0[0].get("next_title") if _docs0 else "") or "")
    except Exception:
        pass
    return jsonify({"ok": upd_ok, "link": link, "next": _nx, "next_title": _nxt})

@app.route("/api/sign/share", methods=["POST"])
def api_sign_share():
    """שיתוף קישור החתימה החתומה ללקוח (אחרי הפקה במקום) — WhatsApp + SMS."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    phone = (body.get("phone") or "").strip()
    link = (body.get("link") or "").strip()
    client = (body.get("client") or "").strip()
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 9 or not link:
        return jsonify({"ok": False, "reason": "bad_input"}), 400
    last9 = digits.lstrip("0")[-9:]
    msg = ("שלום %s,\nמצורף קישור למסמך החתום שלך מ-RE/MAX Family:\n%s" % (client, link))
    wa_ok = False; sms_ok = False
    try:
        wa = _wa_phone(phone)
        if wa: wa_ok = bool(send_text(wa, msg))
    except Exception: wa_ok = False
    try: sms_ok = bool(web_send_sms(last9, msg))
    except Exception: sms_ok = False
    return jsonify({"ok": (wa_ok or sms_ok), "wa": wa_ok, "sms": sms_ok})

def _parse_sign_header(header):
    """מפרק את מחרוזת הכותרת המובנית (תאריך/סוכן/לקוח/נכסים) לשדות לרינדור נקי בעמוד ההסכם."""
    import re as _re2
    out = {"date": "", "agent": "", "client": "", "phone": "", "cid": "", "props": []}
    for ln in str(header or "").split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith("תאריך:"):
            m = _re2.search(r"תאריך:\s*([^·]+)", ln)
            if m: out["date"] = m.group(1).strip()
            m = _re2.search(r"הסוכן:\s*(.+)$", ln)
            if m: out["agent"] = m.group(1).strip()
        elif ln.startswith("לקוח:"):
            parts = [p.strip() for p in ln[len("לקוח:"):].strip().split("·")]
            if parts and parts[0]: out["client"] = parts[0]
            for p in parts[1:]:
                if "טל" in p: out["phone"] = _re2.sub(r"[^0-9+\-]", "", p)
                elif "ז" in p and "ת" in p: out["cid"] = _re2.sub(r"[^0-9]", "", p)
        elif ln.startswith("נכס:"):
            seg = ln[len("נכס:"):].strip().split("·")
            addr = seg[0].strip()
            price = ""
            for s in seg[1:]:
                if "מחיר" in s: price = _re2.sub(r"[^0-9,]", "", s)
            if addr: out["props"].append({"addr": addr, "price": price})
        elif _re2.match(r"^\d+\.", ln):
            m = _re2.match(r"^\d+\.\s*(.+?)\s*—\s*(.+)$", ln)
            if m:
                out["props"].append({"addr": m.group(1).strip(), "price": _re2.sub(r"[^0-9,]", "", m.group(2))})
            else:
                out["props"].append({"addr": _re2.sub(r"^\d+\.\s*", "", ln), "price": ""})
    return out

@app.route("/s/<token>")
def public_sign_doc(token):
    """עמוד ציבורי של ההסכם החתום (ללא התחברות) — נפתח מהקישור בשורת החתימה / מה-SMS.
    עם cache: מסמך חתום קבוע לנצח (6ש'); ממתין-לחתימה — 120ש'. בלי זה כל פתיחה
    משכה מ-Apps Script (נמדד 20-40ש' בזמן האטה של גוגל) ותקעה thread."""
    import html as _h
    _ck = "signdoc:" + token
    j = _cache_get(_ck, 21600)
    if j is not None and str(((j.get("doc") or {}) if isinstance(j, dict) else {}).get("status", "")) != "signed":
        j = _cache_get(_ck, 120)   # טרם נחתם — טריות קצרה, שהחתימה תופיע מהר
    if j is None:
        j = _signdoc_get(token)
        if j and j.get("ok") and j.get("found"):
            _cache_put(_ck, j)
    if not (j and j.get("ok") and j.get("found")):
        _dbg = _h.escape(str(j)[:400]) if j else "אין תגובה מ-Apps Script (None)"
        return ("<!DOCTYPE html><html dir=rtl lang=he><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'><title>מסמך</title></head>"
                "<body style='font-family:Arial;text-align:center;padding:40px'><h2>המסמך לא נמצא</h2>"
                "<p>ייתכן שהקישור שגוי או שפג תוקפו.</p>"
                "<p style='color:#bbb;font-size:11px;direction:ltr;word-break:break-all'>token=" + _h.escape(token) +
                "<br>resp=" + _dbg + "</p></body></html>"), 404
    doc = j.get("doc", {})
    header = str(doc.get("header", ""))
    try:
        docs = _json.loads(doc.get("docs") or "[]")
    except Exception:
        docs = []
    signature = str(doc.get("signature", ""))
    status = str(doc.get("status", "signed"))
    docs_html = "".join(
        "<div class=doc><h2>%s</h2><div class=body>%s</div></div>" % (
            _h.escape(str(d.get("title", ""))), _h.escape(str(d.get("body", "")))) for d in docs)
    # הסכם המשך (בלעדיות): מוצג כ"חתימה ממתינה" מתחת להסכם המוכר, ונפתח אחרי חתימתו
    _next_tok = str((docs[0].get("next_token") if docs else "") or "")
    _next_title = str((docs[0].get("next_title") if docs else "") or "")
    _sib_pending = False
    if _next_tok and status == "pending":
        try:   # מציגים "חתימה ממתינה" רק כשהאח באמת טרם נחתם (Supabase — מילישניות)
            _sj = _signdoc_get(_next_tok)
            _sib_pending = bool(_sj and _sj.get("found")
                                and str((_sj.get("doc") or {}).get("status", "")) != "signed")
        except Exception:
            _sib_pending = True   # ספק — עדיף להציג
    if _sib_pending:
        docs_html += ("<div style='display:flex;align-items:center;gap:11px;background:#faf8f4;border:1.5px dashed var(--gold);"
                      "border-radius:14px;padding:13px 15px;margin-top:4px'>"
                      "<div style='width:10px;height:10px;border-radius:50%;background:var(--gold);flex:0 0 auto'></div>"
                      "<div><div style='font-weight:800;font-size:14px'>" + _h.escape(_next_title or "הסכם בלעדיות") + " · חתימה ממתינה</div>"
                      "<div style='font-size:12.5px;color:#67707e;font-weight:600'>ייפתח לחתימה מיד לאחר חתימת ההסכם הזה</div></div></div>")
    sig_html = ("<div class=sig><div>חתימת הלקוח:</div><img src='" + signature + "' alt='חתימה'></div>") if signature else ""
    _head = ("<!DOCTYPE html><html dir=rtl lang=he><head><meta charset=utf-8>"
             "<meta name=viewport content='width=device-width,initial-scale=1'>"
             "<link href='https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800;900&display=swap' rel='stylesheet'>"
             "<title>הסכם — RE/MAX Family</title><style>"
             ":root{--ink:#15263b;--gold:#bb8a2c;--green:#1f8a4c;--muted:#8b93a1;--line:#efece6}"
             "*{box-sizing:border-box}"
             "body{font-family:'Heebo',Arial,sans-serif;background:#f6f5f2;color:var(--ink);margin:0;padding:22px 14px 40px;direction:rtl;letter-spacing:-.011em;-webkit-font-smoothing:antialiased}"
             ".page{max-width:820px;margin:0 auto;background:#fff;padding:30px 32px 26px;border-radius:18px;box-shadow:0 1px 2px rgba(20,30,50,.04),0 14px 40px rgba(20,30,50,.07);border:1px solid var(--line)}"
             ".logobar{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding-bottom:16px;margin-bottom:6px;position:relative;border-bottom:none}"
             ".logobar:after{content:'';position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}"
             ".logobar img{height:48px;width:auto;object-fit:contain;flex:0 0 auto}"
             ".agentbox .an{font-size:17px;font-weight:800}"
             ".agentbox .al{font-size:12.5px;color:var(--muted);font-weight:600;margin-top:2px}"
             ".docnum{font-size:12px;font-weight:800;color:var(--gold);letter-spacing:.04em;margin:14px 0 4px}"
             ".cline{font-size:13.5px;color:#46505f;font-weight:600;line-height:1.7;background:#faf8f4;border:1px solid var(--line);border-radius:12px;padding:11px 14px;margin-bottom:14px}"
             ".cline b{color:var(--ink)}"
             ".ptt{font-size:13px;font-weight:800;color:#67707e;margin:0 2px 7px;display:flex;align-items:center;gap:7px}"
             ".ptt:before{content:'';width:14px;height:2px;border-radius:2px;background:var(--gold)}"
             ".ptable{width:100%;border-collapse:separate;border-spacing:0;margin-bottom:18px;border:1px solid var(--line);border-radius:12px;overflow:hidden}"
             ".ptable th{background:#faf8f4;font-size:12.5px;color:#67707e;font-weight:800;padding:10px 13px;text-align:start;border-bottom:1px solid var(--line)}"
             ".ptable td{padding:11px 13px;font-size:14px;font-weight:600;border-bottom:1px solid var(--line)}"
             ".ptable tr:last-child td{border-bottom:none}"
             ".doc{margin-bottom:18px}"
             ".doc h2{font-size:19px;font-weight:800;margin:18px 0 10px;padding-inline-start:11px;border-inline-start:4px solid var(--gold);line-height:1.3}"
             ".doc .body{font-size:14.5px;line-height:1.85;color:#33405a;white-space:pre-line}"
             ".signbox{margin-top:22px;border-top:2px solid var(--line);padding-top:20px}"
             ".signlbl{font-weight:800;font-size:14px;margin-bottom:8px}"
             ".signinp{width:100%;box-sizing:border-box;padding:13px 14px;font-size:16px;font-weight:700;border:1.5px solid #e0e4e9;border-radius:12px;direction:ltr;text-align:center;letter-spacing:1px;background:#fbfcfd;font-family:inherit}"
             ".signinp::placeholder{color:#bcc2cc;letter-spacing:.5px}"
             "#idmsg{font-size:12.5px;margin-top:6px;font-weight:700;color:var(--green)}"
             ".signpad{width:100%;height:170px;border:1.5px dashed #d6d0c4;border-radius:14px;background:#fff;margin-top:6px;touch-action:none;display:block}"
             ".clrbtn{background:none;border:none;color:var(--muted);font-size:13px;font-weight:700;cursor:pointer;padding:6px}"
             ".sig{margin-top:20px;border-top:1px solid var(--line);padding-top:14px;font-size:14px;font-weight:600}"
             ".sig img{max-width:260px;height:auto}"
             ".pb{display:block;width:100%;max-width:820px;margin:18px auto 6px;padding:16px;background:linear-gradient(180deg,#d4a437,#c0901f);color:#231700;border:none;border-radius:14px;font-size:16px;font-weight:800;font-family:inherit;cursor:pointer;box-shadow:0 8px 20px rgba(187,138,44,.28)}"
             ".agentrow{display:flex;align-items:center;gap:12px}"
             ".avwrap{width:56px;height:56px;border-radius:50%;border:2.5px solid var(--gold);padding:2px;flex:0 0 auto;box-sizing:border-box}"
             ".avin{position:relative;width:100%;height:100%;border-radius:50%;background:#15263b;display:flex;align-items:center;justify-content:center;overflow:hidden}"
             ".avin span{color:#fff;font-size:21px;font-weight:800;line-height:1}"
             ".avin img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}"
             ".okcard{text-align:center;padding:14px 0 4px}"
             ".okcard .big{font-size:44px}"
             ".okcard h2{font-size:20px;font-weight:800;margin:8px 0 4px}"
             ".okcard p{font-size:14px;color:#67707e;font-weight:600;margin:0 0 16px;line-height:1.6}"
             ".stickybar{position:fixed;left:0;right:0;bottom:0;padding:10px 14px calc(env(safe-area-inset-bottom,0px) + 12px);"
             "background:linear-gradient(180deg,rgba(246,245,242,0),rgba(246,245,242,.94) 38%);z-index:5}"
             ".stickybar .pb{margin:0 auto;box-shadow:0 10px 26px rgba(187,138,44,.4)}"
             ".greet{font-size:19px;font-weight:800;margin:4px 0 2px}"
             ".greet2{font-size:13.5px;color:#67707e;font-weight:600;margin-bottom:14px}"
             ".agree{display:flex;align-items:flex-start;gap:9px;margin:16px 0 4px;font-size:13.5px;font-weight:600;color:#46505f;line-height:1.55}"
             ".agree input{width:19px;height:19px;margin-top:1px;accent-color:#bb8a2c;flex:0 0 auto}"
             ".backlink{display:block;text-align:center;margin-top:12px;background:none;border:none;color:#67707e;font-size:13.5px;font-weight:700;cursor:pointer;font-family:inherit;text-decoration:underline;width:100%}"
             ".efoot{display:flex;align-items:center;justify-content:center;gap:7px;margin-top:20px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);font-weight:600}"
             ".efoot a{color:var(--muted)}"
             "#step2{display:none}"
             "@media print{.pb,.signbox,.stickybar,.efoot,.backlink{display:none}body{background:#fff;padding:0}.page{box-shadow:none;border-radius:0;max-width:100%;border:none}}"
             "</style></head><body><div class=page>")
    _p = _parse_sign_header(header)
    _docnum = "%05d" % ((sum(ord(c) for c in token) * 7) % 90000 + 10000)
    _cid_eff = _p["cid"]
    if not _cid_eff:
        _ev = str(doc.get("event_id", ""))
        if _ev.isdigit() and len(_ev) >= 7: _cid_eff = _ev
    _rows = ""
    for pr in _p["props"]:
        _prc = (_h.escape(pr["price"]) + " ₪") if pr.get("price") else "—"
        _rows += "<tr><td>" + _h.escape(pr["addr"]) + "</td><td>" + _prc + "</td></tr>"
    _ptbl = ("<div class=ptt>פרטי הנכס</div><table class=ptable><tr><th>כתובת</th><th>מחיר מבוקש</th></tr>" + _rows + "</table>") if _p["props"] else ""
    _cparts = []
    if _p["client"]: _cparts.append("שם הלקוח: <b>" + _h.escape(_p["client"]) + "</b>")
    if _cid_eff: _cparts.append("ת״ז: " + _h.escape(_cid_eff))
    if _p["phone"]: _cparts.append("טל': " + _h.escape(_p["phone"]))
    if _p["date"]: _cparts.append("תאריך: " + _h.escape(_p["date"]))
    _ainfo = {}
    if _p["agent"]:
        try: _ainfo = fetch_agents_full().get(_norm_name(_p["agent"]), {})
        except Exception: _ainfo = {}
    _aphone = _fmt_vphone(_ainfo.get("phone", "")) if _ainfo.get("phone") else ""
    _alic = (_ainfo.get("license", "") or "").strip()
    try:   # רישיון שהסוכן הזין באזור האישי גובר על עמודת הגיליון
        _lic_own = (_load_config().get("v2_licenses") or {}).get(_last9(_ainfo.get("phone", "")), "")
        if _lic_own:
            _alic = str(_lic_own)
    except Exception:
        pass
    _agent_box = ""
    if _p["agent"]:
        # תמונת הסוכן מהאפליקציה (כמו בסטורי) — טבעת זהב; בלי תמונה: האות הראשונה על נייבי.
        # הטלפון נפתר מכל מספרי הסוכן הידועים (מפת החברים+אנשי קשר+קונפיג) — ונבחר
        # דווקא המספר שיש לו תמונה שמורה בדיסק, לא סתם הראשון.
        _avraw = ""
        try:
            _av_dir = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(os.path.abspath(__file__)), "v2_avatars")
            _cands = []
            try:
                _cands = [c for c in (_last9(x) for x in (_phones_for_name(_p["agent"]) or set())) if c]
            except Exception:
                pass
            _ai9 = "".join(ch for ch in str(_ainfo.get("phone", "")) if ch.isdigit())[-9:]
            if _ai9 and _ai9 not in _cands:
                _cands.append(_ai9)
            for _c in _cands:
                if os.path.exists(os.path.join(_av_dir, _c + ".jpg")):
                    _avraw = _c
                    break
            if not _avraw and _cands:
                _avraw = _cands[0]
        except Exception:
            _avraw = ""
        _aletter = _h.escape(_p["agent"].strip()[:1]) if _p["agent"].strip() else ""
        _av = ("<div class=avwrap><div class=avin><span>" + _aletter + "</span>" +
               (("<img src='/v2/api/avatar?p=" + _avraw + "' alt='' onerror='this.remove()'>") if _avraw else "") +
               "</div></div>")
        _agent_box = ("<div class=agentrow>" + _av +
            "<div class=agentbox><div class=an>" + _h.escape(_p["agent"]) + "</div>" +
            (("<div class=al>רישיון תיווך מס׳: " + _h.escape(_alic) + "</div>") if _alic else "") +
            (("<div class=al>טלפון: " + _h.escape(_aphone) + "</div>") if _aphone else "") +
            "<div class=al>RE/MAX Family</div></div></div>")
    _logobar = "<div class=logobar>" + _agent_box + "<img src='/assets/logo?v=3' alt='RE/MAX Family'></div>"
    _efoot = ("<div class=efoot>"
              "<svg width='16' height='14' viewBox='0 0 118 106'><path d='M58 8L20 44l14 54h48l14-54z' fill='#E4C56B'/><path d='M20 44l-14 8 14 6z' fill='#1E3A5F'/><circle cx='40' cy='34' r='4.2' fill='#1E3A5F'/></svg>"
              "מופעל על ידי אפי · <a href='/sign-terms' target='_blank' rel='noopener'>תנאי שימוש ופרטיות</a></div>")
    meta_html = (_logobar +
        "<div class=docnum>הסכם מס׳ " + _docnum + "</div>" +
        (("<div class=cline>" + " · ".join(_cparts) + "</div>") if _cparts else "") +
        _ptbl)
    if status == "pending":
        _greet = ("<div class=greet>שלום" + ((" " + _h.escape(_p["client"])) if _p["client"] else "") + ",</div>"
                  "<div class=greet2>קראת את ההסכם — נשאר רק לאמת זהות ולחתום. לוקח פחות מדקה.</div>")
        _form = ("<div id=step1>" + docs_html +
                 "<div style='height:66px'></div></div>"   # מרווח לכפתור הצף
                 "<div id=step2><div class=signbox style='border-top:none;margin-top:4px;padding-top:0'>" +
                 _greet +
                 "<div class=signlbl>תעודת זהות</div>"
                 "<input id=cid class=signinp type=text inputmode=numeric maxlength=9 name=sg_tz autocomplete=off autocorrect=off data-form-type=other data-lpignore=true placeholder='9 ספרות' oninput='chkId()'>"
                 "<div id=idmsg></div>"
                 "<div class=signlbl style='margin-top:14px'>✍️ חתימה באצבע, בתוך המסגרת</div>"
                 "<canvas id=pad class=signpad></canvas>"
                 "<div style='text-align:left'><button class=clrbtn onclick='clrPad()'>נקה וחתום מחדש</button></div>"
                 "<label class=agree><input id=agree type=checkbox> קראתי את ההסכם ואני מסכים/ה "
                 "<a href='/sign-terms' target='_blank' rel='noopener'>לתנאי השימוש והפרטיות</a> של מערכת החתימה</label>"
                 "<button id=sbtn class=pb onclick='doSign()'>✅ אשר וחתום</button>"
                 "<button class=backlink onclick='backToDoc()'>חזרה לקריאת ההסכם</button>"
                 "</div></div>" + _efoot + "</div>"
                 "<div class=stickybar id=contBar><button class=pb onclick='showSign()'>המשך לחתימה ›</button></div>")
        _js = ("<script>var TOKEN=" + _json.dumps(token) + ",NEXT=" + _json.dumps(_next_tok) + ",NEXTT=" + _json.dumps(_next_title) + ";"
               "function showSign(){document.getElementById('step1').style.display='none';"
               "document.getElementById('contBar').style.display='none';"
               "document.getElementById('step2').style.display='block';"
               "szPad();window.scrollTo(0,0);}"
               "function backToDoc(){document.getElementById('step2').style.display='none';"
               "document.getElementById('step1').style.display='block';"
               "document.getElementById('contBar').style.display='block';window.scrollTo(0,0);}"
               "function validIL(v){v=String(v).replace(/\\D/g,'');if(v.length>9)return false;while(v.length<9)v='0'+v;var s=0;for(var i=0;i<9;i++){var n=parseInt(v[i],10)*((i%2)+1);if(n>9)n-=9;s+=n;}return s%10===0;}"
               "function chkId(){var v=document.getElementById('cid').value;var m=document.getElementById('idmsg');if(!v){m.textContent='';return;}if(validIL(v)){m.textContent='✓ תקין';m.style.color='#1a8a4a';}else{m.textContent='✗ ת״ז לא תקינה';m.style.color='#c0392b';}}"
               "var cv=document.getElementById('pad'),cx=cv.getContext('2d'),drawing=false,signed=false;"
               "function szPad(){var r=cv.getBoundingClientRect();if(r.width<10)return;cv.width=r.width;cv.height=180;cx.lineWidth=2.5;cx.lineCap='round';cx.lineJoin='round';cx.strokeStyle='#0D1B2A';}"
               "szPad();"
               "function pos(e){var r=cv.getBoundingClientRect();var t=(e.touches&&e.touches[0])?e.touches[0]:e;return{x:t.clientX-r.left,y:t.clientY-r.top};}"
               "function dn(e){drawing=true;var p=pos(e);cx.beginPath();cx.moveTo(p.x,p.y);if(e.cancelable)e.preventDefault();}"
               "function mv(e){if(!drawing)return;var p=pos(e);cx.lineTo(p.x,p.y);cx.stroke();signed=true;if(e.cancelable)e.preventDefault();}"
               "function up(){drawing=false;}"
               "cv.addEventListener('mousedown',dn);cv.addEventListener('mousemove',mv);window.addEventListener('mouseup',up);"
               "cv.addEventListener('touchstart',dn,{passive:false});cv.addEventListener('touchmove',mv,{passive:false});cv.addEventListener('touchend',up);"
               "function clrPad(){cx.clearRect(0,0,cv.width,cv.height);signed=false;}"
               "function doSign(){var id=(document.getElementById('cid').value||'').replace(/\\D/g,'');if(!id){alert('נא להזין תעודת זהות');return;}if(!validIL(id)){alert('תעודת הזהות אינה תקינה');return;}if(!signed){alert('נא לחתום בתיבת החתימה');return;}"
               "if(!document.getElementById('agree').checked){alert('נא לאשר את תנאי השימוש והפרטיות');return;}"
               "var tw=440,th=Math.round(tw*cv.height/cv.width);var c=document.createElement('canvas');c.width=tw;c.height=th;var x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,tw,th);x.drawImage(cv,0,0,tw,th);var sig=c.toDataURL('image/jpeg',0.55);"
               "var b=document.getElementById('sbtn');b.disabled=true;b.textContent='שומר…';"
               "fetch('/api/sign/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:TOKEN,cid:id,signature:sig})}).then(function(r){return r.json();}).then(function(r){if(r&&r.ok){"
               "var NX=(r.next!==undefined)?r.next:NEXT,NXT=(r.next_title)||NEXTT;var okh = NX"
               "? '<div class=okcard><div class=big>✅</div><h2>ההסכם נחתם</h2><p>נותר הסכם אחד לחתימה: '+(NXT||'ההסכם הנוסף')+'.</p><button class=pb onclick=\"location.href=\\'/s/\\'+encodeURIComponent(NX)\">המשך לחתימת '+(NXT||'ההסכם הנוסף')+' ›</button></div>'"
               ": '<div class=okcard><div class=big>🎉</div><h2>ההסכם נחתם ונשמר</h2><p>עותק חתום נשמר אצל המתווך.<br>מומלץ לשמור עותק גם אצלך.</p><button class=pb onclick=\"location.reload()\">צפייה במסמך החתום · שמירת PDF</button></div>';"
               "document.getElementById('step2').innerHTML=okh;"
               "window.scrollTo(0,0);}else{b.disabled=false;b.textContent='✅ אשר וחתום';alert('שמירה נכשלה: '+((r&&r.reason)||'שגיאה'));}}).catch(function(){b.disabled=false;b.textContent='✅ אשר וחתום';alert('שגיאת רשת');});}"
               "</script>")
        return _head + meta_html + _form + _js + "</body></html>"
    _tail = (docs_html + sig_html + _efoot + "</div>"
             "<button class=pb onclick='window.print()'>שמור / הדפס PDF</button></body></html>")
    return _head + meta_html + _tail

@app.route("/api/dev/newborn_default", methods=["POST"])
def api_dev_nb_default():
    """ברירת מחדל לימי השהיה של נכס נולד (לכל סוכן ללא הגדרה אישית)."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    v = body.get("days")
    if v not in ("", None):
        try: v = int(v)
        except Exception: return jsonify({"ok": False, "reason": "bad"}), 400
    def _mut(cfg):   # RMW בטוח (נגד דריסת רקע)
        if v in ("", None): cfg.pop("newbornDefaultDelay", None)
        else: cfg["newbornDefaultDelay"] = v
    ok, _ = _config_mutate(_mut)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "ברירת מחדל נכס נולד", str(v))
    return jsonify({"ok": ok})

@app.route("/api/dev/sources", methods=["GET"])
def api_dev_sources():
    """מצב מקורות הנתונים — אילו מודולים קוראים מ-Supabase ואילו מהגיליון. מפתח בלבד."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    flags = {"נכס נולד": NEWBORN_SOURCE, "שיחות": CALLS_SOURCE, "חתימות": SIGNATURES_SOURCE,
             "קונים": BUYERS_SOURCE, "שת\"פ": EXCL_SOURCE, "נכסים": PROPS_SOURCE, "קונפיג": CONFIG_SOURCE}
    on_sb = [k for k, v in flags.items() if v == "supabase"]
    return jsonify({"ok": True, "flags": flags,
                    "supabase_ready": bool(_sbdb and _sbdb.enabled()),
                    "all_on_supabase": len(on_sb) == len(flags),
                    "count": f"{len(on_sb)}/{len(flags)}"})

@app.route("/api/dev/diag", methods=["GET"])
def api_dev_diag():
    """אבחון חיבור הקונפיג ל-Apps Script — לזיהוי 'השמירה נכשלה'."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    raw_get = _buyers_apps_post("getconfig", {})
    getok = bool(raw_get and raw_get.get("ok") and "config" in raw_get)
    probe = dict(_load_config()); probe["_diag_ts"] = int(time.time())
    wrote = _save_config(probe)
    raw2 = _buyers_apps_post("getconfig", {})
    readback = bool(raw2 and raw2.get("ok") and ("_diag_ts" in (raw2.get("config") or "")))
    if getok and wrote and readback:
        msg = "✅ החיבור תקין — שמירה וקריאה עובדות."
    elif not APPS_SCRIPT_URL:
        msg = "❌ APPS_SCRIPT_URL לא מוגדר בשרת."
    elif not getok:
        msg = "❌ getconfig לא עונה ok — ה-Apps Script כנראה לא פרוס בגרסה חדשה (חסר getconfig/setconfig), או טוקן שגוי."
    elif not wrote or not readback:
        msg = "❌ setconfig לא כותב — ודא שפרסת גרסה חדשה ושלגיליון יש הרשאת כתיבה."
    else:
        msg = "⚠️ מצב לא ידוע."
    # [PERF-4 מדידה] גודל בלוב הקונפיג + הרכבו — לדעת מתי ארכוב nbStatus נהיה נחוץ
    _cfg_stats = {}
    try:
        _cfg = _load_config()
        _cfg_stats = {"config_kb": round(len(_json.dumps(_cfg, ensure_ascii=False)) / 1024, 1),
                      "nbStatus_n": len(_cfg.get("nbStatus") or {}),
                      "nbNotes_n": sum(len(v) for v in (_cfg.get("nbNotes") or {}).values() if isinstance(v, list))}
    except Exception:
        pass
    return jsonify({"ok": True, "msg": msg, "url_set": bool(APPS_SCRIPT_URL),
                    "getconfig_ok": getok, "write_ok": bool(wrote), "readback_ok": readback,
                    "raw": str(raw_get)[:200], **_cfg_stats})

# ── History (calls + signatures) ───────────────────────────────────────────────
def _call_uid(c):
    """מזהה יציב לשיחה. אם אין event_id (קורה בחלק מהשיחות) — בונים hash דטרמיניסטי
    מהטלפון+הזמן+הסוכן, כדי שאפשר יהיה להסתיר/לשחזר גם שיחות ללא מזהה."""
    eid = str(c.get("event_id", "") or "").strip()
    if eid: return eid
    base = (str(c.get("caller_phone", "")) + "|" + str(c.get("received_at", "")) +
            "|" + str(c.get("agent_phone", "")) + "|" + str(c.get("status", "")))
    return "h" + _hashlib.md5(base.encode("utf-8")).hexdigest()[:16]

@app.route("/api/history", methods=["GET"])
def api_history():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    eff = s
    if s["role"] == "admin":                       # "צפה כסוכן" — למנהל בלבד (לפי שם)
        as_name = request.args.get("as", "").strip()
        if as_name:
            phones = _phones_for_name(as_name)
            if phones:
                eff = {"role": "agent", "name": as_name, "phones": phones}
    calls = web_fetch_raw("שיחות"); sigs = get_signings()
    if eff["role"] == "coordinator":
        agset = set(eff.get("agents") or [])
        names = set(_canon_key(n) for n in (eff.get("agent_names") or []))
        for a in agset:
            nm = _canon_key(web_phone_name_map().get(a, ""))
            if nm: names.add(nm)
        names.discard("")
        calls = [c for c in calls if _last9(c.get("agent_phone", "")) in agset]
        sigs  = [g for g in sigs if _canon_key(g.get("agent", "")) in names]
    elif eff["role"] != "admin":
        _team = _team_for(eff["name"])
        if _team:
            tphones, tkeys = _team
            own = set(eff.get("phones") or ([eff["phone"]] if eff.get("phone") else []))
            tphones = tphones | own
            calls = [c for c in calls if _last9(c.get("agent_phone", "")) in tphones]
            sigs  = [g for g in sigs if _canon_key(g.get("agent", "")) in tkeys]
        else:
            nm = _canon_key(eff["name"])
            if eff.get("phones"):
                pset = eff["phones"]
                calls = [c for c in calls if _last9(c.get("agent_phone", "")) in pset]
            else:
                ph = eff["phone"]
                calls = [c for c in calls if _last9(c.get("agent_phone", "")) == ph]
            sigs  = [g for g in sigs if _canon_key(g.get("agent", "")) == nm]
    _hidden = _fetch_hidden_calls()
    if request.args.get("hidden") == "1":
        calls = [c for c in calls if _call_uid(c) in _hidden]
    else:
        calls = [c for c in calls if _call_uid(c) not in _hidden]
    # מנהל מושהה (כמו אווה אזולאי) — רואה שיחות רק אחרי X ימים. המפתח רואה הכל מיד.
    _dly = _delayed_admin_days(eff.get("name", ""), eff.get("phone", ""))
    if _dly and not _is_dev(s.get("phone", "")):
        _cut = time.time() - _dly * 86400
        calls = [c for c in calls
                 if 0 < _epoch_from_iso(c.get("received_at", "")) <= _cut]
    calls.sort(key=lambda c: _epoch_from_iso(c.get("received_at", "")), reverse=True)
    sigs.sort(key=lambda g: _excl_epoch(g.get("received_at", "")), reverse=True)
    call_out = []
    for c in calls[:500]:
        raw = str(c.get("transcript_summary", ""))
        m = re.search(r"https?://\S+", raw)
        callback = m.group(0) if (m and ("maskyoo" in raw or "click2call" in raw)) else ""
        text = re.sub(r"https?://\S+", "", raw)
        text = re.sub(r"\*", "", text)                       # נקה כוכביות (סימון bold של וואטסאפ)
        text = re.sub(r"AI מתמלל ומסכם שיחות", "", text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        client_details = ""
        mi = text.find("פרטים שנאספו על הלקוח")
        if mi >= 0:
            client_details = text[mi:].strip()
            text = text[:mi].strip()
        # אם אחרי הסרת התווית "סיכום השיחה:" לא נשאר תוכן אמיתי — אין סיכום
        if not re.sub(r"[\s.\-–—:·•]", "", re.sub(r"^\s*סיכום השיחה:?\s*", "", text)):
            text = ""
        caller_disp, caller_tel = _il_phone(c.get("caller_phone", ""))
        call_out.append({
            "time": _fmt_il_dt(c.get("received_at", "")),
            "status": str(c.get("status", "")).upper(),
            "caller": caller_disp,
            "tel": caller_tel,
            "wa": _wa_phone(c.get("caller_phone", "")),
            "duration": c.get("duration_sec", ""),
            "agent": (c.get("agent", "") or "").strip(),
            "summary": text,
            "clientDetails": client_details,
            "callback": callback,
            "id": _call_uid(c),
            "ts": _epoch_from_iso(c.get("received_at", "")),
        })
    sig_out = [{
        "time": (_fmt_il_dt(g.get("received_at", "")) or str(g.get("received_at", "") or "").strip()),
        "type": _deal_label(g.get("deal_type", "")),
        "client": (g.get("client_name", "") or "").strip(),
        "address": ", ".join([x for x in [g.get("address", ""), g.get("city", "")] if x]),
        "pct": _web_valid_pct(g.get("commission_pct")),
        "link": (str(g.get("commission_pct")).strip()
                 if isinstance(g.get("commission_pct"), str) and re.search(r"https?://", str(g.get("commission_pct"))) else ""),
        "agent": (g.get("agent", "") or "").strip(),
        "ts": _excl_epoch(g.get("received_at", "")),
        "eid": str(g.get("event_id", "") or "").strip(),
        "notes": (g.get("notes") or g.get("הערות") or "").strip(),
        "raw": str(g.get("received_at", "") or "").strip(),
    } for g in sigs[:500]]
    # שעת החתימה האמיתית (sign_docs ב-Supabase) — "נחתם · <מתי נחתם>" במקום שעת השליחה.
    # מסמכים מלפני המעבר (05/08) אינם בטבלה — יציגו את שעת השליחה כמו קודם.
    _sdt = _cache_get("signdoc_times", 60)
    if _sdt is None:
        _sdt = (_sbdb.signdoc_times() if (_sbdb and _sbdb.enabled()) else {})
        _cache_put("signdoc_times", _sdt)
    for _r0 in sig_out:
        _lk = _r0.get("link") or ""
        if "/s/" in _lk:
            _sa = _sdt.get(_lk.rsplit("/s/", 1)[-1].strip("/ "))
            if _sa:
                _r0["signed_time"] = _fmt_il_dt(_sa) or _sa
    vphone = _vphone_for_name(eff["name"])
    return jsonify({"ok": True, "role": eff["role"], "name": eff["name"],
                    "dev": bool(s.get("dev", False)),
                    "drole": s.get("drole", ""), "tabs": _tabs_for_role(s.get("drole", "")),
                    "vphone": vphone, "calls": call_out, "signatures": sig_out})

@app.route("/api/signatures", methods=["GET"])
def api_signatures():
    """חתימות בלבד — קליל ומהיר (לא מושך/מעבד את כל השיחות כמו /api/history)."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    eff = s
    if s["role"] == "admin":
        as_name = request.args.get("as", "").strip()
        if as_name:
            phones = _phones_for_name(as_name)
            if phones:
                eff = {"role": "agent", "name": as_name, "phones": phones}
    sigs = get_signings()
    if eff["role"] == "coordinator":
        names = set(_canon_key(n) for n in (eff.get("agent_names") or []))
        for a in (eff.get("agents") or []):
            nm = _canon_key(web_phone_name_map().get(a, ""))
            if nm: names.add(nm)
        names.discard("")
        sigs = [g for g in sigs if _canon_key(g.get("agent", "")) in names]
    elif eff["role"] != "admin":
        _team = _team_for(eff["name"])
        if _team:
            _tphones, tkeys = _team
            sigs = [g for g in sigs if _canon_key(g.get("agent", "")) in tkeys]
        else:
            nm = _canon_key(eff["name"])
            sigs = [g for g in sigs if _canon_key(g.get("agent", "")) == nm]
    sigs.sort(key=lambda g: _excl_epoch(g.get("received_at", "")), reverse=True)
    sig_out = [{
        "time": (_fmt_il_dt(g.get("received_at", "")) or str(g.get("received_at", "") or "").strip()),
        "type": _deal_label(g.get("deal_type", "")),
        "client": (g.get("client_name", "") or "").strip(),
        "address": ", ".join([x for x in [g.get("address", ""), g.get("city", "")] if x]),
        "pct": _web_valid_pct(g.get("commission_pct")),
        "link": (str(g.get("commission_pct")).strip()
                 if isinstance(g.get("commission_pct"), str) and re.search(r"https?://", str(g.get("commission_pct"))) else ""),
        "agent": (g.get("agent", "") or "").strip(),
        "ts": _excl_epoch(g.get("received_at", "")),
        "eid": str(g.get("event_id", "") or "").strip(),
        "notes": (g.get("notes") or g.get("הערות") or "").strip(),
        "raw": str(g.get("received_at", "") or "").strip(),
    } for g in sigs[:500]]
    # ממוצע הנכסים שהלקוח חתם עליהם (טפסי מתעניין) — לפי זיהוי הכתובת בנכסי המשרד/שת"פ.
    # מופרד מכירה/שכירות; מוצג באפור קטן על כרטיס החתימה (בקשת אייל 13/07).
    # ⚡ המפה נשמרת ב-cache פר-סקופ ל-120ש' — הבית ומסך החתימות קוראים לכאן בכל
    # ביקור, ובלי ה-cache החישוב רץ מחדש על כל בקשה (סעיף 2 בדוח הביצועים 14/07).
    try:
        _avgkey = "sigavg:%s:%s" % (eff["role"], _canon_key(eff.get("name", "")))
        by_client = _cache_get(_avgkey, 120)
        if by_client is None:
            idx = _office_prop_index()
            by_client = {}   # (לקוח, מכירה/שכירות) → [מחירים]
            for g in sigs[:500]:
                dt = str(g.get("deal_type", "")).upper()
                if not dt.startswith("CLIENT"):
                    continue
                ck = (_canon_key(g.get("client_name", "")), "R" if "RENT" in dt else "S")
                if not ck[0]:
                    continue
                for part in str(g.get("address", "") or "").split("|"):
                    info = _sign_prop_lookup(part.strip(), g.get("city", ""), idx=idx)
                    if info and info.get("price"):
                        by_client.setdefault(ck, []).append(info["price"])
            _cache_put(_avgkey, by_client)
        for d, g in zip(sig_out, sigs[:500]):
            dt = str(g.get("deal_type", "")).upper()
            if not dt.startswith("CLIENT"):
                continue
            ps = by_client.get((_canon_key(g.get("client_name", "")), "R" if "RENT" in dt else "S")) or []
            if ps:
                d["avg"] = "{:,}".format(sum(ps) // len(ps))
                d["avg_n"] = len(ps)
    except Exception as _ae:
        log.error(f"signatures avg error: {_ae}")
    return jsonify({"ok": True, "role": eff["role"], "name": eff["name"], "signatures": sig_out})

# ── תהליכים ועסקאות (אחסון מקומי בדיסק — ללא Google) ───────────────────────────
import os as _os2, threading as _th, json as _j2  # כינויים (מוגדרים כאן כי בלוק זה רץ לפני בלוק המפה)
_DEALS_PATH = _os2.path.join(_os2.environ.get("MAP_CACHE_DIR", "") or _os2.path.dirname(__file__), "deals.json")
_deals_lock = _th.Lock()
def _deals_load():
    try:
        with open(_DEALS_PATH, encoding="utf-8") as f:
            d = _j2.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []
def _deals_save_all(items):
    try:
        with open(_DEALS_PATH, "w", encoding="utf-8") as f:
            _j2.dump(items, f, ensure_ascii=False)
    except Exception as e:
        log.error(f"deals save error: {e}")
def _is_deals_group_manager(s):
    """מתאמת שהוגדרה כ'מנהל קבוצה' — רואה גם תהליכים/עסקאות של הסוכנים שלה.
    מוגדר בקונפיג v2_deals_group_managers (רשימת שמות ו/או טלפונים). בקשת אייל 09/07."""
    try:
        want = set()
        # env — עמיד לחלוטין לסנכרון הגיליון (מומלץ לפרודקשן)
        for x in (os.environ.get("DEALS_GROUP_MANAGERS", "") or "").split(","):
            x = x.strip()
            if x:
                want.add(_canon_key(x)); want.add(_last9(x))
        # קונפיג — ניתן לניהול; שורד סנכרון דרך גיבוי הגיליון ב-_save_config
        gm = _load_config().get("v2_deals_group_managers") or []
        if isinstance(gm, (list, tuple, set)):
            for x in gm:
                x = str(x or "").strip()
                if x:
                    want.add(_canon_key(x)); want.add(_last9(x))
        want.discard("")
        return (_canon_key(s.get("name", "")) in want) or (_last9(s.get("phone", "")) in want)
    except Exception:
        return False

def _deals_can_see(item, s):
    # מתאמת רגילה אינה רואה תהליכים/עסקאות של הסוכנים שלה (בקשת אייל 07/07) — רק את שלה, כמו סוכן.
    # חריג: "מנהל קבוצה" (v2_deals_group_managers) — רואה גם את של הסוכנים שלו (בקשת אייל 09/07).
    if s.get("role") == "admin":
        return True
    nm = _canon_key(s.get("name", ""))
    keys = {nm}
    t = _team_for(s.get("name", ""))   # צוות (קונפיג teams) — חברי צוות רואים גם תהליכים ועסקאות זה של זה
    if t:
        keys |= t[1]
    if s.get("role") == "coordinator" and _is_deals_group_manager(s):
        keys |= set(_canon_key(a) for a in (s.get("agent_names") or []))
    keys.discard("")
    ags = [_canon_key(a) for a in (item.get("agents") or [])]
    return any(a in keys for a in ags) or (_canon_key(item.get("by", "")) in keys)
def _deals_notify(rec, is_new=False, became_deal=False):
    """פוש: עסקה חדשה / תהליך חדש → למנהלים + לסוכן/ים שביצעו (לא לכל המשרד)."""
    try:
        addr = (rec.get("notes", "") or "נכס").strip()
        # קהל: מנהלים + הסוכנים המעורבים בעסקה/בתהליך
        targets = set(_manager_push_ids())
        for _a in (rec.get("agents") or []):
            for _ph in _phones_for_name(_a):
                _l = _last9(_ph)
                if _l: targets.add(_l)
        for _ph in _phones_for_name(rec.get("by", "") or ""):   # + מי שיצר את הרשומה
            _l = _last9(_ph)
            if _l: targets.add(_l)
        targets = list(targets)
        if rec.get("deal") and (is_new or became_deal):
            price = (rec.get("sale_price", "") or rec.get("price", "") or "").strip()
            body = addr + (" · ₪" + price if price else "")
            _th.Thread(target=lambda: send_push("עסקה חדשה 🎉", body, targets), daemon=True).start()
        elif (not rec.get("deal")) and is_new:
            ag = " + ".join([a for a in (rec.get("agents") or []) if a])
            body = (ag + " · " if ag else "") + addr
            _th.Thread(target=lambda: send_push("תהליך חדש 📋", body, targets), daemon=True).start()
    except Exception:
        pass

@app.route("/api/deals", methods=["GET"])
def api_deals():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    eff = s
    if s["role"] == "admin":
        as_name = request.args.get("as", "").strip()
        if as_name:
            eff = {"role": "agent", "name": as_name}   # "צפה כסוכן" — רואים רק את התהליכים של אותו סוכן
    all_items = _deals_load()
    items = [it for it in all_items if _deals_can_see(it, eff)]
    items.sort(key=lambda it: it.get("ts", 0), reverse=True)
    agents = sorted(set(n for n in web_phone_name_map().values() if n and n.strip()))
    if s["name"] and s["name"] not in agents:
        agents = [s["name"]] + agents
    imported = any(it.get("src") == "reminders" for it in all_items) and any(it.get("src") == "sales2026" for it in all_items)
    return jsonify({"ok": True, "role": s["role"], "name": eff["name"], "items": items, "agents": agents, "imported": imported})

@app.route("/api/deals/save", methods=["POST"])
def api_deals_save():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    b = request.get_json(silent=True) or {}
    agents = [str(a).strip() for a in (b.get("agents") or []) if str(a).strip()][:2]
    if not agents and s["role"] not in ("admin", "coordinator"):
        agents = [s["name"]]
    if not agents or not str(b.get("notes", "") or "").strip():
        return jsonify({"ok": False, "reason": "חובה סוכן וכתובת"}), 400
    with _deals_lock:
        items = _deals_load()
        iid = str(b.get("id", "") or "").strip()
        existing = next((it for it in items if it.get("id") == iid), None) if iid else None
        if existing and not _deals_can_see(existing, s):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        _was_deal = bool(existing.get("deal")) if existing else False
        rec = {
            "id": iid or (str(int(time.time() * 1000)) + str(_secrets.randbelow(1000))),
            "agents": agents,
            "notes": str(b.get("notes", "") or "").strip(),
            "side1": str(b.get("side1", "") or "").strip(),
            "side2": str(b.get("side2", "") or "").strip(),
            "lawyers": str(b.get("lawyers", "") or "").strip(),
            "lawyers2": str(b.get("lawyers2", "") or "").strip(),   # עו"ד מצד המוכר
            "offer": bool(b.get("offer")),                          # תהליך במצב "הצעה"
            "offer_seller": str(b.get("offer_seller", "") or "").strip(),
            "offer_buyer": str(b.get("offer_buyer", "") or "").strip(),
            "price": str(b.get("price", "") or "").strip(),
            "deal": bool(b.get("deal")),
            "sale_price": str(b.get("sale_price", "") or "").strip(),
            # תאריך סגירה לא חובה — אם ריק בעסקה, ברירת מחדל = היום (רגע השמירה)
            "close_date": (str(b.get("close_date", "") or "").strip()
                           or (time.strftime("%d/%m/%Y") if b.get("deal") else "")),
            # שדות אפי (טופס 24a/27a): שלב בתהליך + עמלה (אוטומטית 2%+מע"מ או ידנית)
            "stage": str(b.get("stage", "") or "").strip(),
            "commission": str(b.get("commission", "") or "").strip(),
            "commission_manual": bool(b.get("commission_manual")),
            "commission2": str(b.get("commission2", "") or "").strip(),
            "commission2_manual": bool(b.get("commission2_manual")),
        }
        if existing:
            rec["created"] = existing.get("created", "")
            rec["ts"] = existing.get("ts", time.time())
            rec["by"] = existing.get("by", s["name"])
            items = [rec if it.get("id") == rec["id"] else it for it in items]
        else:
            rec["created"] = time.strftime("%d/%m/%Y")
            rec["ts"] = time.time()
            rec["by"] = s["name"]
            items.append(rec)
        _deals_save_all(items)
    _deals_notify(rec, is_new=(not existing), became_deal=(bool(existing) and (not _was_deal) and bool(rec.get("deal"))))
    return jsonify({"ok": True, "id": rec["id"]})

_DEALS_SEED = [
    {"agents": ["ליקה", "חי"], "side1": "מוכר", "side2": "קונה", "price": "2215000", "notes": "נעמי שמר 10"},
    {"agents": ["אלי", "יהודית"], "side1": "מוכר", "side2": "קונה", "price": "1240000", "notes": "לויק"},
    {"agents": ["רויטל"], "side1": "קונה", "side2": "", "price": "", "notes": "דליה 9"},
    {"agents": ["רויטל"], "side1": "מוכר", "side2": "", "price": "960000", "notes": "דב פרומר"},
    {"agents": ["חי", "קובי"], "side1": "מוכר", "side2": "קונה", "price": "2550000", "notes": "אהובה עוזרי"},
    {"agents": ["ליקה", "רפי"], "side1": "מוכר", "side2": "קונה", "price": "1600000", "notes": "ההגנה 50"},
    {"agents": ["סיון"], "side1": "מוכר", "side2": "", "price": "", "notes": "ששת הימים"},
    {"agents": ["ליקה", "אלעד"], "side1": "מוכר", "side2": "קונה", "price": "", "notes": "השקדים 10"},
    {"agents": ["יאיר"], "side1": "מוכר", "side2": "", "price": "1890000", "notes": "אילנות"},
    {"agents": ["יאיר"], "side1": "מוכר וקונה", "side2": "", "price": "1000000", "notes": "מרדכי נמיר"},
    {"agents": ["קובי"], "side1": "קונה", "side2": "", "price": "4200000", "notes": "פנטהאוז קדם"},
    {"agents": ["ליקה"], "side1": "", "side2": "", "price": "1950000", "notes": "עפרה חזה 11"},
    {"agents": ["ליקה", "אלעד"], "side1": "מוכר", "side2": "קונה", "price": "", "notes": "נעמי שמר 38"},
    {"agents": ["חי"], "side1": "מוכר", "side2": "", "price": "1450000", "notes": "ורד 29"},
    {"agents": ["חי"], "side1": "קונה", "side2": "", "price": "1688000", "notes": "אהוד מנור 15"},
    {"agents": ["רויטל", "צדוק"], "side1": "קונה", "side2": "מוכר", "price": "1250000", "notes": "ציזלינג 36"},
]
try:
    _SALES_SEED = _j2.load(open(_os2.path.join(_os2.path.dirname(__file__), "sales_seed_2026.json"), encoding="utf-8"))  # עסקאות 2026 מקובץ המעקב (fallback לסנכרון החי)
except Exception:
    _SALES_SEED = []

# ── סנכרון חי של עסקאות מקובץ המעקב ב-Dropbox (בקשת אייל 09/07) ─────────────────
# שם-קצר בקובץ → שם/שמות מלאים של הסוכן במערכת (צוות = כמה שמות). מיפוי מפורש = בלי ניחוש.
_DROPBOX_AGENT_MAP = {
    "נדב": ["נדב רייזר"], "אלעד": ["אלעד לוי"], "רויטל": ["רויטל גל"],
    "ליאור": ["ליאור גרונפינקל"], "ליאור וקבלי": ["ליאור גרונפינקל", "מאור קבלי"],
    "ענבר": ["ענבר אלון"], "ליקה": ["ליקה אוברוב"], "חי": ["חי אלבס"],
    "אירנה": ["אירנה אוברוב"], "מתן": ["מתן הרשקו"], "עוז": ["עוז דנילוב"],
    "עידן": ["עידן חליווה"], "רפי": ["רפי דה פיצוטו"], "יאיר": ["יאיר חנוכייב"],
    "אלמוג": ["אלמוג וויל"], "לירון": ["לירון דהן"], "אבירן": ["אבירן"],
    "רוי": ["רוי אזולאי"], "ירין": ["ירין לוי"],
    "אלי ויהודית": ["אלי שמול", "יהודית שמול"], "אור צוקרמן": ["אור צוקרמן"],
    "הרשקו וקובי": ["מתן הרשקו"],
    # קובץ 2:
    "יהונתן": ["יהונתן"],                       # סוכן לשעבר — עסקאות היסטוריות נשמרות
    "שי ושרלי": ["שי", "שירלי גוטמן"],           # צוות
}
_DEALS_XLSX_SHEET = os.environ.get("DEALS_XLSX_SHEET", "עסקאות 26")

def _dropbox_direct(url):
    """קישור שיתוף של Dropbox → הורדה ישירה (dl=1)."""
    u = (url or "").strip()
    if "dropbox.com" not in u:
        return u
    if "dl=0" in u:
        return u.replace("dl=0", "dl=1")
    if "dl=1" in u:
        return u
    return u + ("&dl=1" if "?" in u else "?dl=1")

def _parse_deals_xlsx(raw_bytes, pwd):
    """מפענח (אם מוצפן) וקורא את גיליון העסקאות. זיהוי עמודות לפי שם כותרת — עמיד לשינוי סדר.
    מחזיר רשומות בפורמט seed (agents/side1/sale_price/close_date/notes), 2026 בלבד."""
    import io as _io3
    import msoffcrypto, openpyxl
    buf = _io3.BytesIO(raw_bytes)
    try:
        of = msoffcrypto.OfficeFile(buf)
        if of.is_encrypted():
            of.load_key(password=pwd or "")
            dec = _io3.BytesIO(); of.decrypt(dec); dec.seek(0); buf = dec
        else:
            buf.seek(0)
    except Exception:
        buf.seek(0)
    wb = openpyxl.load_workbook(buf, read_only=True, data_only=True)
    def _nz0(v): return re.sub(r"\s+", " ", str(v or "").strip())
    # זיהוי גיליון העסקאות לפי כותרות (עמיד לשם שונה: "עסקאות 26" מול "עסקאות26")
    ws = None
    for _sn in wb.sheetnames:
        _cand = wb[_sn]
        _hset = set(_nz0(h) for h in (next(_cand.iter_rows(min_row=1, max_row=1, values_only=True), ()) or ()))
        if "סוכן" in _hset and "סכום העסקה" in _hset:
            ws = _cand; break
    if ws is None:
        ws = wb[_DEALS_XLSX_SHEET] if _DEALS_XLSX_SHEET in wb.sheetnames else wb[wb.sheetnames[0]]
    rit = ws.iter_rows(values_only=True)
    header = next(rit, None) or []
    def _nz(v): return re.sub(r"\s+", " ", str(v or "").strip())
    def _col(*names):
        for i, h in enumerate(header):
            if _nz(h) in names:
                return i
        return None
    ci_ag = _col("סוכן"); ci_sd = _col("קונה / מוכר", "קונה/מוכר")
    ci_pr = _col("סכום העסקה"); ci_dt = _col("תאריך עסקה")
    ci_ct = _col("עיר"); ci_st = _col("רחוב")
    if ci_ag is None or ci_pr is None:
        return []
    def _g(r, i): return r[i] if (i is not None and i < len(r)) else None
    out = []
    for r in rit:
        ag = _nz(_g(r, ci_ag)); amt = str(_g(r, ci_pr) or "").strip()
        if not ag or not amt:
            continue
        dv = _g(r, ci_dt)
        d = dv.strftime("%d/%m/%Y") if hasattr(dv, "strftime") else _nz(dv)
        if not d.endswith("2026"):   # רק 2026 (בקשת אייל)
            continue
        agents = list(_DROPBOX_AGENT_MAP.get(ag, [ag]))
        price = str(int(float(amt))) if amt.replace(".", "", 1).isdigit() else amt
        notes = ", ".join([x for x in [_nz(_g(r, ci_st)), _nz(_g(r, ci_ct))] if x])
        out.append({"agents": agents, "side1": _nz(_g(r, ci_sd)), "side2": "",
                    "sale_price": price, "close_date": d, "notes": notes})
    return out

def _fetch_dropbox_deals():
    """מושך את קובץ/קבצי העסקאות מ-Dropbox ומחזיר רשומות. כישלון (רשת/פענוח/מבנה) → None (נופלים
    ל-seed הסטטי, שהוא תצלום אחרון של הקובץ). מוגדר ע"י env: DEALS_XLSX_URLS (מופרד בפסיקים), DEALS_XLSX_PWD."""
    urls = [u.strip() for u in (os.environ.get("DEALS_XLSX_URLS", "") or "").split(",") if u.strip()]
    if not urls:
        return None
    # סיסמה לכל קובץ (מקבילי, מופרד בפסיקים). גיבוי לשם הישן היחיד DEALS_XLSX_PWD.
    pwds = [p.strip() for p in (os.environ.get("DEALS_XLSX_PWDS", os.environ.get("DEALS_XLSX_PWD", "")) or "").split(",")]
    allrecs = []
    for i, u in enumerate(urls):
        pwd = pwds[i] if i < len(pwds) else (pwds[-1] if pwds else "")
        try:
            resp = requests.get(_dropbox_direct(u), timeout=30)
            if resp.status_code >= 300 or not resp.content:
                log.error(f"dropbox deals fetch failed HTTP {resp.status_code}")
                return None
            allrecs.extend(_parse_deals_xlsx(resp.content, pwd))
        except Exception as e:
            log.error(f"dropbox deals error: {e}")
            return None   # כישלון בקובץ כלשהו → fallback מלא (לא לאבד עסקאות של סוכן)
    return allrecs

@app.route("/api/deals/import", methods=["POST"])
def api_deals_import():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if s["role"] not in ("admin", "coordinator"):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    # מיפוי שם מקוצר (מהתזכורות) → שם מלא של סוכן במערכת, כדי שכל סוכן יראה את שלו
    _names = [n for n in web_phone_name_map().values() if n and n.strip()]
    def _map_agent(short):
        short = (short or "").strip()
        if not short:
            return short
        for full in _names:
            f = full.strip()
            parts = f.split()
            if f == short or (parts and (parts[0] == short or short in parts)):
                return full
        return short
    added = 0
    with _deals_lock:
        items = _deals_load()
        now = time.time()
        if not any(it.get("src") == "reminders" for it in items):   # תהליכים מהתזכורות
            for i, r in enumerate(_DEALS_SEED):
                items.append({
                    "id": str(int(now * 1000)) + str(1000 + i),
                    "agents": [_map_agent(a) for a in r["agents"]], "side1": r.get("side1", ""), "side2": r.get("side2", ""),
                    "notes": r.get("notes", ""), "price": r.get("price", ""), "lawyers": "",
                    "deal": False, "sale_price": "", "close_date": "",
                    "src": "reminders", "by": s["name"], "created": time.strftime("%d/%m/%Y"), "ts": now - i,
                })
                added += 1
        # עסקאות 2026 — מקור אמת: הקובץ החי מ-Dropbox (אם מוגדר/זמין), אחרת ה-seed הסטטי (תצלום אחרון).
        # רענון מלא: מסירים ייבוא קודם של sales2026 ומכניסים מחדש את המצב הנוכחי של הקובץ.
        items = [it for it in items if it.get("src") != "sales2026"]
        _today = time.strftime("%d/%m/%Y")
        _live = _fetch_dropbox_deals()
        _sales = _live if _live is not None else _SALES_SEED
        for i, r in enumerate(_sales):
            items.append({
                "id": str(int(now * 1000)) + str(5000 + i),
                "agents": [_map_agent(a) for a in (r.get("agents") or [])], "side1": r.get("side1", ""), "side2": r.get("side2", ""),
                "notes": r.get("notes", ""), "price": "", "lawyers": "",
                "deal": True, "sale_price": r.get("sale_price", ""), "close_date": r.get("close_date", ""),
                "src": "sales2026", "by": s["name"], "created": _today, "ts": now - 1000 - i,
            })
            added += 1
        if added:
            _deals_save_all(items)
    return jsonify({"ok": True, "count": added, "already": (added == 0)})

@app.route("/api/deals/delete", methods=["POST"])
def api_deals_delete():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    iid = str((request.get_json(silent=True) or {}).get("id", "") or "").strip()
    with _deals_lock:
        items = _deals_load()
        it = next((x for x in items if x.get("id") == iid), None)
        if it and not _deals_can_see(it, s):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        _deals_save_all([x for x in items if x.get("id") != iid])
    return jsonify({"ok": True})

# ── Activity log (admin only) ──────────────────────────────────────────────────
@app.route("/api/recent", methods=["GET", "POST"])
def api_recent():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        q = (body.get("q", "") or "").strip()
        kind = (body.get("kind", "") or "props").strip()
        if q: _push_recent(s["phone"], kind if kind in ("props", "excl") else "props", q)
        return jsonify({"ok": True})
    kind = request.args.get("kind", "")
    return jsonify({"ok": True, "items": _recent.get(s["phone"], {}).get(kind, [])})

@app.route("/api/agents", methods=["GET"])
def api_agents():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if s["role"] not in ("admin", "coordinator"):   # מתאמת — בשביל "אחר במשרד…" בתיאום פגישה
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    # מיזוג: אנשי קשר (קנוני) + סוכני קונפיג + לשונית שיחות — דדופ לפי מפתח גמיש
    by_canon = {}
    for n in (list(web_contacts_phone_name().values())
              + [ag.get("name", "") for ag in (_load_config().get("agents") or [])]
              + list(web_phone_name_map().values())):
        nn = _norm_name(n)
        if not nn: continue
        ck = _canon_key(nn)
        if ck not in by_canon: by_canon[ck] = nn
    names = sorted(by_canon.values())
    return jsonify({"ok": True, "agents": [{"name": n} for n in names]})

@app.route("/api/my/agents", methods=["GET"])
def api_my_agents():
    """רשימת סוכנים לשיוך קונה: מנהל=כולם, מתאמת=הסוכנים שלה, סוכן=ריק."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    role = s.get("role")
    if role == "admin":
        by_canon = {}
        for n in (list(web_contacts_phone_name().values())
                  + [ag.get("name", "") for ag in (_load_config().get("agents") or [])]
                  + list(web_phone_name_map().values())):
            nn = _norm_name(n)
            if not nn: continue
            ck = _canon_key(nn)
            if ck not in by_canon: by_canon[ck] = nn
        return jsonify({"ok": True, "agents": [{"name": n} for n in sorted(by_canon.values())]})
    if role == "coordinator":
        # דדופ קנוני — אותו שם בשני איותים (קונפיג מול גיליון) לא יופיע פעמיים;
        # עדיפות לאיות מאנשי הקשר (הקנוני), כמו ברשימת המנהל
        _contacts = {_canon_key(n): n for n in web_contacts_phone_name().values() if n}
        by_canon = {}
        for nm in (s.get("agent_names") or []):
            nn = _norm_name(nm)
            if not nn: continue
            ck = _canon_key(nn)
            if ck not in by_canon: by_canon[ck] = _contacts.get(ck, nn)
        for ph in (s.get("agents") or []):
            nm = web_contacts_phone_name().get(_last9(ph)) or web_phone_name_map().get(_last9(ph))
            nn = _norm_name(nm or "")
            if not nn: continue
            ck = _canon_key(nn)
            if ck not in by_canon: by_canon[ck] = _contacts.get(ck, nn)
        return jsonify({"ok": True, "agents": [{"name": n} for n in sorted(by_canon.values())]})
    return jsonify({"ok": True, "agents": []})

@app.route("/api/activity", methods=["GET"])
def api_activity():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if s["role"] != "admin": return jsonify({"ok": False, "reason": "forbidden"}), 403
    c = _cache_get("activity_today", 45)
    if c is None:
        jj = _buyers_apps_post("listactivity", {})
        c = jj.get("items", []) if (jj and jj.get("ok")) else []
        _cache_put("activity_today", c)
    seen = set(); merged = []
    for it in (list(c) + list(_activity[-400:])):
        try: tsr = round(float(it.get("ts", 0)))
        except Exception: tsr = 0
        k = (tsr, str(it.get("name", "")), str(it.get("action", "")), str(it.get("detail", "")))
        if k in seen: continue
        seen.add(k); merged.append(it)
    merged.sort(key=lambda x: float(x.get("ts", 0) or 0), reverse=True)
    # יומן שימוש אמין: כל פעולות היום (00:00 שעון ישראל → עכשיו), בלי תקרת 300 שחתכה את הבוקר
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        _mid = _dt.datetime.now(ZoneInfo("Asia/Jerusalem")).replace(hour=0, minute=0, second=0, microsecond=0)
    except Exception:
        _mid = _dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    _t0 = _mid.timestamp()
    today = [it for it in merged if float(it.get("ts", 0) or 0) >= _t0]
    return jsonify({"ok": True, "items": merged[:300], "today": today})

def _web_org_summary(frm, to, agent_name=None, agent_phones=None, agent_keys=None):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as _ex:
        _fc = _ex.submit(web_fetch_raw, "שיחות", frm, to)
        _fs = _ex.submit(get_signings, frm, to)
        _fp = _ex.submit(web_fetch_raw, "נכסים", frm, to)
        calls, sigs, props = _fc.result(), _fs.result(), _fp.result()
    # דירוג משרדי (לפני הסינון): איפה הסוכן עומד מול כל המשרד בגיוסים ובהחתמות
    _rank = None
    if agent_name or agent_keys:
        _rk_keys = set(agent_keys) if agent_keys else ({_canon_key(agent_name)} if (agent_name and _canon_key(agent_name)) else set())
        _cnt_b, _cnt_k = {}, {}
        for _g in sigs:
            _dtu = str(_g.get("deal_type", "") or "")
            _agk = _canon_key(_g.get("agent", ""))
            if not _agk:
                continue
            if "OWNER_EXCLUSIVE" in _dtu: _cnt_b[_agk] = _cnt_b.get(_agk, 0) + 1
            if "CLIENT_SALE" in _dtu:     _cnt_k[_agk] = _cnt_k.get(_agk, 0) + 1
        def _pos(cnt):
            if not cnt:
                return None
            mine = max([cnt.get(k, 0) for k in _rk_keys] or [0])
            return {"pos": len([v for v in cnt.values() if v > mine]) + 1,
                    "of": len(cnt), "n": mine}
        _rank = {"gius": _pos(_cnt_b), "konim": _pos(_cnt_k)}
    if agent_name or agent_phones or agent_keys:
        _nks = set(agent_keys) if agent_keys else ({_canon_key(agent_name)} if (agent_name and _canon_key(agent_name)) else set())
        _phs = set(agent_phones or [])
        def _is_mine(row, use_phone=False):
            if _nks and _canon_key(row.get("agent", "")) in _nks: return True
            if use_phone and _phs and _last9(row.get("agent_phone", "")) in _phs: return True
            return False
        calls = [c for c in calls if _is_mine(c, True)]
        sigs  = [g for g in sigs if _is_mine(g)]
        props = [p for p in props if _is_mine(p)]
    answered = cc = busy = 0; by_agent = {}
    for c in calls:
        st = str(c.get("status", "")).upper().strip()
        if st == "ANSWER": answered += 1
        elif st == "CALLER_CANCEL": cc += 1
        elif st == "BUSY": busy += 1
        ag = (c.get("agent", "") or "").strip()
        if ag:
            d = by_agent.setdefault(ag, {"total": 0, "answered": 0}); d["total"] += 1
            if st == "ANSWER": d["answered"] += 1
    total = len(calls); noanswer = total - answered - cc - busy
    rate = round(answered / total * 100) if total else 0
    agents = sorted(({"name": k, "total": v["total"], "answered": v["answered"],
                      "rate": round(v["answered"] / v["total"] * 100) if v["total"] else 0}
                     for k, v in by_agent.items()), key=lambda x: -x["total"])
    konim = bladiut = skhirut = 0; exc = []; sigs_list = []; sig_agents = {}
    for g in sigs:
        dt = str(g.get("deal_type", "")).upper()
        _ag = (g.get("agent", "") or "").strip()
        if "CLIENT_SALE" in dt: konim += 1
        elif "OWNER_EXCLUSIVE" in dt: bladiut += 1
        elif "OWNER_RENT" in dt or "CLIENT_RENT" in dt: skhirut += 1
        if _ag:
            _d = sig_agents.setdefault(_ag, {"konim": 0, "bladiut": 0})
            if "CLIENT_SALE" in dt: _d["konim"] += 1
            elif "OWNER_EXCLUSIVE" in dt: _d["bladiut"] += 1
        if "OWNER_EXCLUSIVE" in dt:
            exc.append({"date": g.get("_date_key", ""),
                        "address": ", ".join([x for x in [g.get("address", ""), g.get("city", "")] if x]),
                        "agent": (g.get("agent", "") or "").strip()})
        sigs_list.append({"date": g.get("_date_key", ""),
                          "type": _deal_label(g.get("deal_type", "")),
                          "client": (g.get("client_name", "") or "").strip(),
                          "address": ", ".join([x for x in [g.get("address", ""), g.get("city", "")] if x]),
                          "agent": (g.get("agent", "") or "").strip()})
    st_total = len(sigs)
    pct = lambda n: round(n / st_total * 100) if st_total else 0
    by_city = {}
    for p in props:
        city = (p.get("city", "") or "").strip()
        if city: by_city[city] = by_city.get(city, 0) + 1
    top_cities = sorted(({"city": k, "n": v} for k, v in by_city.items()), key=lambda x: -x["n"])[:5]
    return {
        "period": {"from": frm, "to": to},
        "calls": {"total": total, "answered": answered, "notAnswered": cc + busy + noanswer,
                  "cc": cc, "busy": busy, "noanswer": noanswer, "rate": rate},
        "agents": agents,
        "sigs": {"total": st_total, "konim": konim, "bladiut": bladiut, "skhirut": skhirut,
                 "pctK": pct(konim), "pctB": pct(bladiut), "pctS": pct(skhirut)},
        "exclusives": exc,
        "sigsList": sigs_list,
        "topGius": sorted(({"name": k, "n": v["bladiut"]} for k, v in sig_agents.items() if v["bladiut"]),
                          key=lambda x: -x["n"])[:10],
        "topKonim": sorted(({"name": k, "n": v["konim"]} for k, v in sig_agents.items() if v["konim"]),
                           key=lambda x: -x["n"])[:10],
        "props": {"total": len(props), "topCities": top_cities},
        "myRank": _rank,
    }

def _agent_insights(frm, to, prev_frm, prev_to, eff_name, eff_phones, cur_sm, eff_keys=None):
    """מלל חופשי על ביצועי הסוכן: מגמות מול התקופה הקודמת + דירוג בלעדיות."""
    out = []
    try:
        prev = _web_org_summary(prev_frm, prev_to, eff_name, eff_phones, eff_keys)
    except Exception:
        prev = None
    def _trend(label, cur, prevn, suf=""):
        if cur > prevn: return f"📈 {label}: עלייה מ-{prevn}{suf} ל-{cur}{suf}"
        if cur < prevn: return f"📉 {label}: ירידה מ-{prevn}{suf} ל-{cur}{suf}"
        return f"➡️ {label}: ללא שינוי ({cur}{suf})"
    def _add(label, cur, prevn, suf=""):
        if cur == 0 and prevn == 0: return
        out.append(_trend(label, cur, prevn, suf))
    if prev is not None:
        _add("שיחות נכנסות", cur_sm["calls"]["total"], prev["calls"]["total"])
        _add("אחוז מענה", cur_sm["calls"]["rate"], prev["calls"]["rate"], "%")
        _add("החתמות קונים", cur_sm["sigs"]["konim"], prev["sigs"]["konim"])
        _add("בלעדיות חדשות", cur_sm["sigs"]["bladiut"], prev["sigs"]["bladiut"])
        _add("נכסים חדשים", cur_sm["props"]["total"], prev["props"]["total"])
    # דירוג בגיוס בלעדיות מול כל המשרד (מוצג רק אם בעשירייה הראשונה)
    try:
        org_sigs = get_signings(frm, to)
        cnt = {}
        for g in org_sigs:
            if "OWNER_EXCLUSIVE" in str(g.get("deal_type", "")).upper():
                ag = _norm_name(g.get("agent", ""))
                if ag: cnt[ag] = cnt.get(ag, 0) + 1
        mine = cnt.get(_norm_name(eff_name or ""), 0)
        if mine > 0:
            rank = 1 + sum(1 for v in cnt.values() if v > mine)
            if rank <= 10:
                out.append(f"🏆 מקום {rank} בגיוס בלעדיות במשרד ({mine} בלעדיות)")
    except Exception:
        pass
    return out

def _report_wa_text(sm, label, frm, to):
    c = sm["calls"]; sg = sm["sigs"]; pr = sm.get("props", {}) or {}
    L = [f"📊 *סיכום {label}* ({frm}–{to})", ""]
    # שיחות
    L.append(f"📞 *שיחות:* {c['total']} · נענו {c['answered']} ({c['rate']}%)")
    L.append(f"   לא נענו {c['notAnswered']}: ניתק {c['cc']} · תפוס {c['busy']} · ללא מענה {c['noanswer']}")
    L.append("")
    # מתווכים מובילים (שיחות)
    L.append("👥 *מתווכים מובילים (שיחות):*")
    for i, a in enumerate(sm["agents"][:10], 1):
        L.append(f"{i}. {a['name']}: {a['total']} שיחות ({a['answered']} נענו · {a['rate']}%)")
    L.append("")
    # חתימות
    L.append(f"✍️ *חתימות:* {sg['total']} — קונים {sg['konim']} ({sg.get('pctK', 0)}%) · בלעדיות {sg['bladiut']} ({sg.get('pctB', 0)}%) · שכירויות {sg['skhirut']} ({sg.get('pctS', 0)}%)")
    # מובילים בגיוס נכסים
    _tg = sm.get("topGius") or []
    if _tg:
        L.append("")
        L.append("🏆 *מובילים בגיוס נכסים:*")
        for i, a in enumerate(_tg[:10], 1):
            L.append(f"{i}. {a['name']}: {a['n']} נכסים")
    # מובילים בהחתמת קונים
    _tk = sm.get("topKonim") or []
    if _tk:
        L.append("")
        L.append("🤝 *מובילים בהחתמת קונים:*")
        for i, a in enumerate(_tk[:10], 1):
            L.append(f"{i}. {a['name']}: {a['n']} קונים")
    # נכסים שגויסו בבלעדיות
    _exc = sm.get("exclusives") or []
    L.append("")
    L.append(f"🏠 *נכסים שגויסו בבלעדיות: {len(_exc)}*")
    for e in sorted(_exc, key=lambda x: str(x.get("date", "")), reverse=True):
        L.append("• " + (e.get("agent", "") or "—") + " · " + (e.get("address", "") or "—")
                 + ((" · " + e.get("date")) if e.get("date") else ""))
    return "\n".join(L)

@app.route("/api/report", methods=["GET"])
def api_report():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    period = request.args.get("period", "month")
    from datetime import datetime, timedelta, timezone
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    except Exception:
        now = datetime.now(timezone.utc) + timedelta(hours=3)
    _HE_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                  "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
    # בחירת חודש ספציפי מתחילת השנה (month=1..12)
    sel_month = request.args.get("month", "").strip()
    end = now
    label = {"day": "היום", "week": "השבוע", "lastweek": "שבוע שעבר", "month": "החודש", "year": "השנה"}.get(period, "החודש")
    if sel_month.isdigit() and 1 <= int(sel_month) <= 12:
        mo = int(sel_month)
        start = now.replace(month=mo, day=1, hour=0, minute=0, second=0, microsecond=0)
        if mo < now.month:  # חודש שכבר הסתיים — עד סוף החודש
            nxt = start.replace(year=start.year + 1, month=1) if mo == 12 else start.replace(month=mo + 1)
            end = nxt - timedelta(days=1)
        label = f"{_HE_MONTHS[mo - 1]} {start.year}"
    elif period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)   # מהיום ב-00:00
    elif period == "week":
        start = now - timedelta(days=(now.weekday() + 1) % 7)   # ראשון
    elif period == "lastweek":
        _sun = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
        start = _sun - timedelta(days=7)   # יום ראשון של שבוע שעבר
        end = _sun - timedelta(days=1)      # יום שבת של שבוע שעבר
    elif period == "year":
        start = now.replace(month=1, day=1)
    else:
        period = "month"; start = now.replace(day=1)
    frm = start.strftime("%d/%m/%Y"); to = end.strftime("%d/%m/%Y")
    as_name = request.args.get("as", "").strip() if s["role"] in ("admin", "coordinator") else ""
    eff_keys = None
    if s["role"] == "agent":
        eff_name = s.get("name", "")
        eff_phones = set(_phones_for_name(eff_name))
        if s.get("phone"): eff_phones.add(_last9(s["phone"]))
        scope = eff_name or "הדוח שלי"
        _team = _team_for(eff_name)
    elif as_name:
        eff_name = as_name
        eff_phones = set(_phones_for_name(as_name))
        scope = as_name
        _team = _team_for(as_name)
    else:
        eff_name = None; eff_phones = None; scope = "כל המשרד"; _team = None
    if _team:
        tphones, tkeys = _team
        eff_phones = (eff_phones or set()) | tphones
        eff_keys = tkeys
        scope = scope + " (צוות)"
    _rk = "report:%s:%s:%s" % (period, sel_month, scope)
    _rc = _cache_get(_rk, 120)
    if _rc is not None:
        return jsonify(_rc)
    insights = []
    try:
        # שליפות מקבילות: הסיכום המרכזי והמקורות האיטיים (נכסים/בלעדויות/נכס נולד)
        # רצים יחד — הזמן הכולל הוא האיטי שבהם, לא הסכום של כולם
        from concurrent.futures import ThreadPoolExecutor as _TPE
        with _TPE(max_workers=3) as _rex:
            _f_sheet = _rex.submit(fetch_sheet_rows)
            _f_excl = _rex.submit(fetch_external_exclusives) if s["role"] in ("admin", "coordinator") else None
            _f_nb = _rex.submit(fetch_newborn) if s["role"] in ("admin", "coordinator") else None
            sm = _web_org_summary(frm, to, eff_name, eff_phones, eff_keys)
        try:   # ספירת "מודעות" — אותו מקור של "נכסים במשרד" (יד2): סוכן=שלו, מנהל=סה"כ
            _lr = _f_sheet.result()
            if eff_keys:
                listings_total = sum(1 for r in _lr if _row_owned(r, eff_keys, eff_phones or set()))
            elif eff_name:
                listings_total = sum(1 for r in _lr if _agent_owns_row(r, eff_name, eff_phones or set()))
            else:
                listings_total = len(_lr)
        except Exception:
            listings_total = 0
        shtaf = []; shtaf_total = 0; shtaf_offices = 0   # גיוס נכסים בשת״פ — פילוח לפי משרד (למנהל/רכז)
        if s["role"] in ("admin", "coordinator"):
            try:
                _se = start.timestamp(); _ee = end.timestamp() + 86400
                _by = {}
                for _r in _dedupe_exclusives(_f_excl.result() if _f_excl else []):
                    _ep = _excl_epoch(_r.get("received_at", ""))
                    if _ep and _se <= _ep < _ee:
                        _raw = (str(_r.get("office", "") or "").strip() or "ללא שם משרד")
                        _off = "RE/MAX Family" if _is_our_office(_raw) else _raw   # אחד את כל הווריאציות שלנו
                        _by[_off] = _by.get(_off, 0) + 1
                _full = sorted([{"office": k, "count": v} for k, v in _by.items()], key=lambda x: -x["count"])
                shtaf_total = sum(o["count"] for o in _full)
                shtaf_offices = len(_full)
                shtaf = _full[:10]   # רק 10 המובילים
            except Exception:
                shtaf = []; shtaf_total = 0; shtaf_offices = 0
        nb_cities = []; nb_total = 0   # נכס נולד — פילוח לפי ערים לפי התקופה שנבחרה (למנהל/רכז)
        if s["role"] in ("admin", "coordinator"):
            try:
                _nse = start.timestamp(); _nee = end.timestamp() + 86400
                _bc = {}
                for _r in (_f_nb.result() if _f_nb else []):
                    _ep = _newborn_created_epoch(_r)
                    if _ep and _nse <= _ep < _nee:
                        nb_total += 1
                        _ct = _detect_city(_r.get("רחוב1", "") or _r.get("רחוב", "") or _r.get("עיר", ""))
                        _bc[_ct] = _bc.get(_ct, 0) + 1
                nb_cities = sorted(({"city": k, "n": v} for k, v in _bc.items()), key=lambda x: -x["n"])
            except Exception:
                nb_cities = []; nb_total = 0
        if eff_name:
            _delta = end - start
            _pe = start - timedelta(days=1)
            _ps = _pe - _delta
            insights = _agent_insights(frm, to, _ps.strftime("%d/%m/%Y"), _pe.strftime("%d/%m/%Y"), eff_name, eff_phones, sm, eff_keys)
        wa = _report_wa_text(sm, label + " · " + scope, frm, to)
        if listings_total:
            wa = wa + "\n\n📋 *מודעות פעילות:* " + str(listings_total)
        if insights:
            wa = "📊 *תובנות:*\n" + "\n".join(insights) + "\n\n" + wa
        if shtaf:
            _lines = "\n".join((("🏠 " if _is_our_office(o["office"]) else "• ") + o["office"] + ": " + str(o["count"]))
                               for o in shtaf)
            _note = (' · מציג 10 מובילים' if shtaf_offices > 10 else '')
            wa = wa + '\n\n🤝 *גיוס נכסים בשת"פ — ' + label + '* (סה"כ ' + str(shtaf_total) + ' נכסים, ' + str(shtaf_offices) + ' משרדים' + _note + ')\n' + _lines
        if nb_cities:
            _ncl = "\n".join("• " + cc["city"] + ": " + str(cc["n"]) for cc in nb_cities)
            wa = wa + '\n\n🏙️ *נכס נולד לפי ערים* (סה"כ ' + str(nb_total) + ' נכסים)\n' + _ncl
        wa = wa + "\n\n_הופק מ-Family Bot 🏠_"
        # טבלת פגישות ופולו-אפ מ"נכס נולד" — לפי הסטטוסים שנשמרו, בהתאם להיקף הדוח
        meetings = []
        try:
            _allowed = None
            if eff_name:
                _allowed = {_canon_key(eff_name)}
                if eff_keys: _allowed |= set(eff_keys)
            for _st in (_nb_statuses() or {}).values():
                if _st.get("status") not in ("meeting", "followup"): continue
                if _allowed is not None and _canon_key(_st.get("agent", "")) not in _allowed: continue
                meetings.append({"status": _st.get("status"),
                                 "label": _NB_STATUS_LABELS.get(_st.get("status"), ""),
                                 "date": _st.get("date", ""), "agent": _st.get("agent", ""),
                                 "addr": _st.get("addr", "")})
            meetings.sort(key=lambda x: str(x.get("date", "")))
        except Exception:
            meetings = []
        # חתך מנהל: פגישות בלבד (בלי פולו-אפ) של כל המשרד, מקובצות לפי מי שתיאם
        # (המתאם ב-'by' — נופל לסוכן ברשומות ישנות). מספרים + נכסים לפירוט בלחיצה.
        # רק בדוח מלא (מנהל/כל המשרד); מסונן לפי תאריך הפגישה בתוך התקופה. בקשת אייל 13/07.
        meet_mgr = []
        if s["role"] == "admin" and not eff_name:   # דוח מנהל מלא בלבד (לא דרך "as", לא מתאמת)
            try:
                _grp = {}
                for _st in (_nb_statuses() or {}).values():
                    if _st.get("status") != "meeting":   # פגישות בלבד
                        continue
                    _md = None
                    _mm = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(_st.get("date", "") or ""))
                    if _mm:
                        try:
                            from datetime import date as _date
                            _md = _date(int(_mm.group(1)), int(_mm.group(2)), int(_mm.group(3)))
                        except Exception:
                            _md = None
                    if _md is not None and not (start.date() <= _md <= end.date()):
                        continue   # פגישה מחוץ לתקופה (רשומה בלי תאריך תקין — נכללת)
                    _who = (str(_st.get("by", "") or "").strip()
                            or str(_st.get("agent", "") or "").strip() or "—")
                    g = _grp.setdefault(_who, {"by": _who, "count": 0, "items": []})
                    g["count"] += 1
                    g["items"].append({"addr": _st.get("addr", ""), "date": _st.get("date", ""),
                                       "agent": _st.get("agent", "")})
                for g in _grp.values():
                    g["items"].sort(key=lambda x: str(x.get("date", "")))
                meet_mgr = sorted(_grp.values(), key=lambda x: -x["count"])
            except Exception:
                meet_mgr = []
        # 5 המובילים בעסקאות (מהמאגר המקומי) — לפי מספר צדדים, עסקאות שנסגרו בתקופה
        top_deals = []
        try:
            from collections import Counter as _Counter
            _dc = _Counter()
            _office_keys = _office_agent_keys()
            for _it in _deals_load():
                if not _it.get("deal"): continue
                try:
                    _dd = datetime.strptime(str(_it.get("close_date", "") or "")[:10], "%d/%m/%Y").date()
                except Exception:
                    continue
                if not (start.date() <= _dd <= end.date()): continue
                _ags = [a for a in (_it.get("agents") or []) if a and _canon_key(a) in _office_keys]
                if not _ags: continue   # רק סוכני המשרד — מתווך חיצוני לא נספר
                if _it.get("side1") == "מוכר וקונה":
                    _dc[_ags[0]] += 2
                else:
                    for _a in _ags:
                        _dc[_a] += 1
            top_deals = [{"name": n, "n": c} for n, c in _dc.most_common(10)]
        except Exception:
            top_deals = []
        _resp = {"ok": True, "label": label, "scope": scope, "from": frm, "to": to,
                 "insights": insights, "summary": sm, "listings": listings_total,
                 "shtaf": shtaf, "shtaf_total": shtaf_total, "shtaf_offices": shtaf_offices,
                 "top_deals": top_deals,
                 "nbCities": nb_cities, "nbTotal": nb_total, "meetings": meetings,
                 "meetMgr": meet_mgr, "meetMgrTotal": sum(g["count"] for g in meet_mgr), "wa_text": wa}
        _cache_put(_rk, _resp)
        return jsonify(_resp)
    except Exception as e:
        log.error(f"report error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

# ── Property search ────────────────────────────────────────────────────────────
@app.route("/api/search/properties", methods=["POST"])
def api_search_properties():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    try:
        q = (request.get_json(silent=True) or {}).get("q", "").strip()
        _log_activity(s["name"], s["role"], s["phone"], "חיפוש נכסים", q or "(כל הנכסים)")
        if q and not (request.get_json(silent=True) or {}).get("nosave"):
            _push_recent(s["phone"], "props", q)
        _scan_price_changes()
        _pc_map = _price_changed_map()   # נכסים שהמחיר שלהם השתנה ב-7 ימים — תג לכולם
        phones = fetch_agents_phones()

        def _row_out(row, score=None):
            ag = (row.get("סוכן 1", "") or "").strip()
            d = {
                "type": (row.get("סוג נכס", "") or "").strip(),
                "city": (row.get("עיר / ישוב", "") or "").strip(),
                "neighborhood": (row.get("שכונה", "") or "").strip(),
                "address": (f"{row.get('כתובת','')} {row.get('מספר בית','')}").strip(),
                "rooms": (row.get("חדרים", "") or "").strip(),
                "size": (row.get('מ"ר', "") or row.get("מ״ר", "") or "").strip(),
                "floor": (row.get("קומה", "") or "").strip(),
                "price": (row.get("מחיר", "") or "").strip(),
                "priceChanged": _prop_price_key(row) in _pc_map,   # תג "עדכון מחיר" (לכולם)
                "date": (row.get("תאריך יצירה", "") or "").strip(),
                "agent": _canon_agent_name(ag),
                "wa": _wa_phone(phones.get(ag, row.get("טלפון 1", ""))),
                "desc": (row.get("_desc_ae", "") or "").strip(),
            }
            if score is not None:
                d["score"] = min(100, int(score))
            # קואורדינטות מה-geocache (אותו מפתח כמו במפה) — כדי לצייר את התוצאה ישירות
            _st = _mnb(row.get("כתובת", "")); _ho = _mnb(row.get("מספר בית", "")); _ci = _mnb(row.get("עיר / ישוב", ""))
            _ll = _mlookup(f"{_st} {_ho}, {_ci}".strip()) if (_st and _ci) else None
            d["lat"] = round(_ll[0], 6) if _ll else None
            d["lng"] = round(_ll[1], 6) if _ll else None
            return d

        # חיפוש ריק = כל הנכסים הפעילים, ממוינים מהחדש לישן (לפי תאריך יצירה)
        if not q:
            rows = [r for r in fetch_sheet_rows()
                    if (r.get("סטטוס", "") or "").strip() in ("", "פעילה")]
            rows.sort(key=_prop_epoch, reverse=True)
            out = [_row_out(r) for r in rows]
            return jsonify({"ok": True,
                            "summary": f"כל הנכסים הפעילים ({len(out)}) — מהחדש לישן",
                            "results": out})

        parsed = parse_search_query(q if q.startswith("מחפש") else ("מחפש דירה " + q))
        matches = search_listings_in_sheet(parsed) if parsed else []
        out = [_row_out(row, score) for score, row, flex in matches]
        return jsonify({"ok": True, "summary": (parsed or {}).get("summary_he", ""), "ptype": (parsed or {}).get("property_type", ""), "results": out})
    except Exception as e:
        log.error(f"properties search error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

# ── "הנכסים שלי" — כל הנכסים של הסוכן מגיליון המשרד, לפי שם וטלפון ──────────────
def _agent_owns_row(row, agent_name, agent_phones):
    """האם הנכס שייך לסוכן — לפי שם (סוכן 1/2) או מספר טלפון (טלפון 1/2)."""
    nn = _canon_key(agent_name)
    if nn and nn not in ("מנהל", "סוכן"):
        for col in ("סוכן 1", "סוכן 2"):
            if _canon_key(row.get(col, "")) == nn:
                return True
    if agent_phones:
        for col in ("טלפון 1", "טלפון 2", "טלפון"):
            ph = _last9(row.get(col, ""))
            if ph and ph in agent_phones:
                return True
    return False

@app.route("/api/my/properties", methods=["GET", "POST"])
def api_my_properties():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    try:
        # מנהל/מתאמת יכולים לצפות כסוכן עם as; אחרת הזהות של המחובר עצמו
        as_name = ""
        if s["role"] in ("admin", "coordinator"):
            as_name = ((request.get_json(silent=True) or {}).get("as", "")
                       or request.args.get("as", "")).strip()
        if as_name:
            eff_name = as_name
            eff_phones = set(_phones_for_name(as_name))
            keys, phones, multi = _scope_keys_phones("agent", eff_name, eff_phones)
        else:
            eff_name = s.get("name", "")
            eff_phones = set(_phones_for_name(eff_name))
            if s.get("phone"):
                eff_phones.add(_last9(s["phone"]))
            keys, phones, multi = _scope_keys_phones(
                s["role"], eff_name, eff_phones, s.get("agents"), s.get("agent_names"))
        rows = fetch_sheet_rows()
        mine = [r for r in rows if _row_owned(r, keys, phones)]
        phones_map = fetch_agents_phones()
        pending = _fetch_pending_listings()
        removed = _removed_listing_ids()   # נכסים שהסוכן ביקש להסיר — יורדים מיד מהתצוגה והספירה
        _scan_price_changes()
        _pc_map = _price_changed_map()      # תג "עדכון מחיר" (7 ימים, לכולם)
        out = []
        for r in mine:
            ag = (r.get("סוכן 1", "") or "").strip()
            lid = (r.get("מספר מודעה", "") or "").strip()
            if lid and lid in removed:      # ממתין להסרה בגיליון — כבר לא מוצג/נספר
                continue
            out.append({
                "id": lid,
                # מתאמת/מנהל יכולים לעדכן מחיר/להסיר מודעה של הסוכנים שלהם (התוצאות כבר מסוננות להיקף שלהם)
                "own": (s["role"] in ("admin", "coordinator")) or _agent_owns_row(r, eff_name, eff_phones),
                "pending": lid in pending,
                "type": (r.get("סוג נכס", "") or "").strip(),
                "city": (r.get("עיר / ישוב", "") or "").strip(),
                "neighborhood": (r.get("שכונה", "") or "").strip(),
                "address": (f"{r.get('כתובת','')} {r.get('מספר בית','')}").strip(),
                "rooms": (r.get("חדרים", "") or "").strip(),
                "size": (r.get('מ"ר', "") or r.get("מ״ר", "") or "").strip(),
                "floor": (r.get("קומה", "") or "").strip(),
                "price": (r.get("מחיר", "") or "").strip(),
                "priceChanged": _prop_price_key(r) in _pc_map,
                "agent": _canon_agent_name(ag),
                "wa": _wa_phone(phones_map.get(ag, r.get("טלפון 1", ""))),
                "desc": (r.get("_desc_ae", "") or "").strip(),
            })
        _log_activity(s["name"], s["role"], s["phone"], "הנכסים שלי",
                      eff_name if as_name else "")
        return jsonify({"ok": True, "count": len(out), "name": eff_name, "multi": multi, "results": out})
    except Exception as e:
        log.error(f"my properties error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

SECRETARY_EMAIL = os.environ.get("SECRETARY_EMAIL", "orianshmul@gmail.com")
def _fetch_pending_listings():
    c = _cache_get("pending_listings", 180)
    if c is not None: return c
    j = _buyers_apps_post("listpending", {})
    ids = set(str(x).strip() for x in (j.get("ids", []) if (j and j.get("ok")) else []))
    _cache_put("pending_listings", ids)
    return ids

def _removed_listing_ids():
    """מזהי מודעות שסוכן ביקש להסיר — נסתרים מ'הנכסים שלי' ומהספירה מיד, עד שהמזכירה
    מסירה מהגיליון (ואז נעלמים ממילא). נשמר בקונפיג (durable), נגזם אחרי 90 יום."""
    try:
        m = _load_config().get("v2_removed_listings") or {}
        return set(str(k) for k in m.keys())
    except Exception:
        return set()

def _prop_price_key(row):
    """מפתח יציב לזיהוי נכס לאורך העלאות — מספר מודעה, ובלעדיו כתובת+עיר מנורמלים."""
    lid = str(row.get("מספר מודעה", "") or "").strip()
    if lid:
        return "L:" + lid
    a = re.sub(r"\s+", " ", (str(row.get("כתובת", "")) + " " + str(row.get("מספר בית", "")) +
                             " " + str(row.get("עיר / ישוב", ""))).strip()).lower()
    return ("A:" + a) if a else ""

def _price_digits(p):
    return re.sub(r"\D", "", str(p or ""))

_PRICE_SCAN = {"ts": 0.0}
def _scan_price_changes():
    """משווה מחירי נכסים נוכחיים לסנאפשוט הקודם (בקונפיג); מחיר שהשתנה → רושם חותמת זמן.
    Throttle 120ש' (עומס זניח); כתיבה durable רק כשמשהו באמת השתנה. תג 'עדכון מחיר' 7 ימים."""
    now = time.time()
    if now - _PRICE_SCAN["ts"] < 120:
        return
    _PRICE_SCAN["ts"] = now
    try:
        rows = fetch_sheet_rows()
    except Exception:
        return
    cur = {}
    for r in rows:
        k = _prop_price_key(r); pn = _price_digits(r.get("מחיר", ""))
        if k and pn:
            cur[k] = pn
    if not cur:
        return
    def _mut(cfg):
        snap = dict(cfg.get("v2_price_snap") or {})
        changes = dict(cfg.get("v2_price_changes") or {})
        for k, pn in cur.items():
            old = snap.get(k)
            if old is not None and old != pn:   # מחיר השתנה (לא מופע ראשון) → תג
                changes[k] = int(now)
            snap[k] = pn
        cutoff = int(now) - 7 * 86400
        changes = {k: v for k, v in changes.items() if (v or 0) >= cutoff}   # גיזום >7 יום
        cfg["v2_price_snap"] = snap
        cfg["v2_price_changes"] = changes
    try:
        _config_mutate(_mut)
    except Exception as _e:
        log.warning(f"price scan failed: {_e}")

def _price_changed_map():
    """{key: ts} של נכסים שהמחיר שלהם השתנה ב-7 הימים האחרונים."""
    try:
        now = time.time()
        m = _load_config().get("v2_price_changes") or {}
        return {k: v for k, v in m.items() if (now - (v or 0)) < 7 * 86400}
    except Exception:
        return {}

def _mark_listing_removed(lid):
    lid = str(lid or "").strip()
    if not lid:
        return
    _now = int(time.time())
    def _mut(cfg):
        m = cfg.get("v2_removed_listings") or {}
        m[lid] = _now
        # גיזום ישנים (>90 יום) — כבר הוסרו מהגיליון מזמן
        cutoff = _now - 90 * 86400
        cfg["v2_removed_listings"] = {k: v for k, v in m.items() if (v or 0) >= cutoff}
    try:
        _config_mutate(_mut)
    except Exception as _e:
        log.warning(f"mark listing removed failed: {_e}")

# ניתוב בקשות עדכון/מחיקת נכס: סוכנים תחת מנהלים מסוימים → מייל ייעודי (בקשת אייל 12/07)
_LISTING_REQ_ROUTED_MANAGERS = ("גיל קדם", "אוהד פלד")
_LISTING_REQ_ROUTED_EMAIL = "ohadpeled7@gmail.com"

def _secretary_for_agent(agent_name, agent_phone):
    """סוכן המשויך למנהל 'גיל קדם' או 'אוהד פלד' → המייל של אוהד פלד; אחרת ברירת המחדל (מזכירה)."""
    try:
        aph = _last9(agent_phone or "")
        ak = _canon_key(agent_name or "")
        routed = {_canon_key(m) for m in _LISTING_REQ_ROUTED_MANAGERS}
        for _cp, c in (_coordinators_all() or {}).items():
            if _canon_key(c.get("name", "")) not in routed:
                continue
            if aph and aph in {_last9(p) for p in (c.get("agents") or set())}:
                return _LISTING_REQ_ROUTED_EMAIL
            if ak and ak in {_canon_key(n) for n in (c.get("names") or set())}:
                return _LISTING_REQ_ROUTED_EMAIL
    except Exception:
        pass
    return SECRETARY_EMAIL

@app.route("/api/listing/request", methods=["POST"])
def api_listing_request():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    kind = (body.get("kind") or "").strip()
    lid = str(body.get("id") or "").strip()
    if kind not in ("remove", "price") or not lid:
        return jsonify({"ok": False, "reason": "bad_request"}), 400
    eff_name = s.get("name", "")
    eff_phone = s.get("phone", "")
    if s["role"] in ("admin", "coordinator"):
        an = (body.get("as") or "").strip()
        if an:
            eff_name = an
            eff_phone = ""   # לא הטלפון של המנהל — ננתב לפי שם הסוכן
    payload = {
        "listing_id": lid,
        "address": (body.get("address") or "").strip(),
        "kind": kind,
        "new_price": (body.get("new_price") or "").strip(),
        "agent": eff_name,
        "agent_phone": _last9(s.get("phone", "")),
        "secretary": _secretary_for_agent(eff_name, eff_phone),
    }
    j = _buyers_apps_post("requestchange", payload)
    if not j or not j.get("ok"):
        return jsonify({"ok": False, "reason": (j or {}).get("error", "fail")}), 502
    _cache_clear("pending_listings")
    if kind == "remove":   # הסרה — הנכס יורד מיד מהתצוגה והספירה (המייל למזכירה כבר יצא)
        _mark_listing_removed(lid)
        _cache_clear("my_properties")
    _log_activity(s["name"], s["role"], s["phone"], ("בקשת הסרת מודעה" if kind == "remove" else "בקשת עדכון מחיר"), lid)
    return jsonify({"ok": True})

@app.route("/api/listing/done", methods=["POST"])
def api_listing_done():
    """סימון 'בוצע' — מסיר את הנכס מרשימת 'בטיפול אצל המזכירה'."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    lid = str((request.get_json(silent=True) or {}).get("id") or "").strip()
    if not lid: return jsonify({"ok": False, "reason": "bad_request"}), 400
    j = _buyers_apps_post("donelisting", {"listing_id": lid})
    if not j or not j.get("ok"):
        return jsonify({"ok": False, "reason": (j or {}).get("error", "fail")}), 502
    _cache_clear("pending_listings")
    _log_activity(s["name"], s["role"], s["phone"], "סימון בוצע (הסרת בטיפול)", lid)
    return jsonify({"ok": True})

# ── "נכס נולד" — נכסים חדשים עם חשיפה מושהית פר-סוכן ─────────────────────────────
# מקור נתונים לקריאה פר-מודול: sheets (ברירת מחדל) / supabase — feature flags
NEWBORN_SOURCE    = (os.environ.get("NEWBORN_SOURCE", "sheets") or "sheets").strip().lower()
CALLS_SOURCE      = (os.environ.get("CALLS_SOURCE", "sheets") or "sheets").strip().lower()
SIGNATURES_SOURCE = (os.environ.get("SIGNATURES_SOURCE", "sheets") or "sheets").strip().lower()
BUYERS_SOURCE     = (os.environ.get("BUYERS_SOURCE", "sheets") or "sheets").strip().lower()
EXCL_SOURCE       = (os.environ.get("EXCL_SOURCE", "sheets") or "sheets").strip().lower()
PROPS_SOURCE      = (os.environ.get("PROPS_SOURCE", "sheets") or "sheets").strip().lower()
CONFIG_SOURCE     = (os.environ.get("CONFIG_SOURCE", "sheets") or "sheets").strip().lower()
try:
    import supabase_db as _sbdb
except Exception:
    _sbdb = None

NEWBORN_SHEET_TAB   = os.environ.get("NEWBORN_SHEET_TAB", "נכס נולד")
NEWBORN_DELAYS_TAB  = os.environ.get("NEWBORN_DELAYS_TAB", "נכסנולד_הגדרות")
NEWBORN_DEFAULT_DELAY = int(os.environ.get("NEWBORN_DEFAULT_DELAY", "0") or 0)
# ביטול השהיות נכס נולד — כולם רואים הכל מיד, 0 ימים, בלי מוסתר ובלי מנהל-מושהה (בקשת אייל 09/07).
# להחזרת מנגנון ההשהיות: NEWBORN_DELAYS_DISABLED=0 ב-Render env (בלי שינוי קוד).
NEWBORN_DELAYS_DISABLED = os.environ.get("NEWBORN_DELAYS_DISABLED", "1") not in ("0", "false", "False", "no", "off", "")
NEWBORN_WINDOW_DAYS   = int(os.environ.get("NEWBORN_WINDOW_DAYS", "400") or 400)
NEWBORN_HIDDEN        = 10 ** 9   # ערך "מוסתר" — הסוכן לא רואה שום נכס
_NB_HIDDEN_TOKENS = {"מוסתר", "מוסתרת", "הסתר", "לעולם", "אין", "לא", "-", "–", "—", "x", "X", "✗"}


def _src_ttl(flag, sheets_ttl, sb_ttl):
    """TTL דינמי למטמון: קצר כשהמקור הוא Supabase (קריאה זולה ומהירה — מידע טרי),
    ארוך כשהמקור הוא Sheets (קריאה יקרה — שומרים על העומס הנמוך הקיים)."""
    return sb_ttl if (flag == "supabase" and _sbdb and _sbdb.enabled()) else sheets_ttl

def fetch_newborn():
    c = _cache_get("newborn_rows", _src_ttl(NEWBORN_SOURCE, 300, 90))
    if c is not None: return c
    with _sf_lock("newborn_rows"):
        c = _cache_get("newborn_rows", _src_ttl(NEWBORN_SOURCE, 300, 90))
        if c is not None: return c
        rows = None
        if NEWBORN_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
            try:
                rows = _sbdb.fetch_newborn_rows()
            except Exception as _sbe:
                log.error(f"supabase newborn read failed — falling back to sheets: {_sbe}")
                rows = None
        if rows is None:
            j = _buyers_apps_post("listnewborn", {})
            rows = (j.get("rows", []) or []) if (j and j.get("ok")) else []
        if rows:   # תשובה ריקה = כמעט תמיד תקלה זמנית — לא לקבע אותה במטמון ל-5 דקות
            _cache_put("newborn_rows", rows)
        return rows

_LAST_GOOD_NB_DELAYS = None

def _fetch_newborn_delays():
    """הגנה קריטית: אם קריאת גיליון ההשהיות נכשלת, ברירת המחדל 'מוסתר' שבגיליון
    אובדת וכולם רואים הכול. לכן: כישלון → טוב-אחרון; אין טוב-אחרון → נועלים (מוסתר)."""
    global _LAST_GOOD_NB_DELAYS
    if NEWBORN_DELAYS_DISABLED: return {"_default": 0}   # כולם 0 — בלי השהיות/מוסתר, מתעלם מגיליון/קונפיג
    c = _cache_get("newborn_delays", 600)
    if c is not None: return c
    d = {"_default": NEWBORN_DEFAULT_DELAY}
    j = _buyers_apps_post("listnewborndelays", {})
    _sheet_ok = bool(j and j.get("ok"))
    _delay_rows = (j.get("rows", []) or []) if _sheet_ok else []
    for r in _delay_rows:
        nm = _norm_name(r.get("סוכן", "") or r.get("שם", "") or "")
        raw = (r.get("ימים", "") or r.get("ימי השהיה", "") or r.get("השהיה", "") or "").strip()
        if raw in _NB_HIDDEN_TOKENS:
            days = NEWBORN_HIDDEN
        else:
            try: days = int(float(raw)) if raw != "" else None
            except Exception: days = None
        if days is None: continue
        if nm in ("ברירת מחדל", "ברירתמחדל", "default", "כללי"):
            d["_default"] = days
        elif nm:
            d[nm] = days
            _ckk = _canon_key(nm)
            if _ckk: d["c:" + _ckk] = days   # מפתח קנוני — סובל איות שונה (רווחים/גרשים)
    # שכבת קונפיג (קונסולת המפתח) — דורסת/משלימה את הגיליון
    _cfg = _load_config()
    _cd = _cfg.get("newbornDefaultDelay")
    if _cd not in (None, ""):
        try: d["_default"] = int(_cd)
        except Exception: pass
    for ag in (_cfg.get("agents") or []):
        nd = ag.get("newbornDelay")
        if nd is None or nd == "": continue
        if nd in ("hidden", "מוסתר", -1, "-1"):
            val = NEWBORN_HIDDEN
        else:
            try: val = int(nd)
            except Exception: continue
        for _nm in [ag.get("name", "")] + list(ag.get("aliases") or []):
            k = _norm_name(_nm)
            if k: d[k] = val
            _ckk = _canon_key(_nm)
            if _ckk: d["c:" + _ckk] = val
    if not _sheet_ok:
        # קריאת הגיליון נכשלה — לא מקבעים במטמון תמונה חסרה:
        if isinstance(_LAST_GOOD_NB_DELAYS, dict):
            return _LAST_GOOD_NB_DELAYS          # טוב-אחרון (בלי cache — ננסה שוב מיד)
        d["_default"] = NEWBORN_HIDDEN           # אין טוב-אחרון — נכשלים לכיוון הבטוח (מוסתר)
        return d
    _LAST_GOOD_NB_DELAYS = d
    _cache_put("newborn_delays", d)
    return d

def _nb_key(r):
    """מפתח יציב לזיהוי נכס נולד (למעקב פניות)."""
    pid = (r.get("מזהה", "") or "").strip()
    if pid: return "id:" + pid
    link = (r.get("קישור", "") or "").strip()
    if link: return "ln:" + link
    addr = (r.get("רחוב1", "") or r.get("רחוב", "") or "").strip()
    return "ad:" + addr + "|" + (r.get("נוצר בתאריך", "") or "").strip()

def _fetch_newborn_contacts():
    c = _cache_get("newborn_contacts", _src_ttl(NEWBORN_SOURCE, 150, 15))
    if c is not None: return c
    if NEWBORN_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            d = _sbdb.fetch_newborn_contacts()
            if d:
                _cache_put("newborn_contacts", d)
            return d
        except Exception as _sbe:
            log.error(f"supabase newborn contacts read failed — falling back to sheets: {_sbe}")
    j = _buyers_apps_post("listnewborncontacts", {})
    rows = (j.get("rows", []) or []) if (j and j.get("ok")) else []
    d = {}
    for r in rows:
        k = (r.get("key", "") or r.get("מפתח", "") or "").strip()
        ag = (r.get("agent", "") or r.get("סוכן", "") or "").strip()
        if not k: continue
        d.setdefault(k, [])
        if ag and ag not in d[k]: d[k].append(ag)
    if d:   # תשובה ריקה = כנראה תקלה זמנית — לא לקבע במטמון
        _cache_put("newborn_contacts", d)
    return d

# ── סטטוס טיפול לכל נכס נולד (פגישה/פולואפ/לא מעוניין) — נשמר בקונפיג ──
_NB_STATUS_LABELS = {
    "meeting": "נקבעה פגישה", "followup": "פולו-אפ",
    "not_interested": "לא מעוניין",
}
def _nb_statuses():
    """{key: {status,date,agent,ts}} מהקונפיג."""
    m = _load_config().get("nbStatus")
    return m if isinstance(m, dict) else {}

def _nb_notes():
    """הערות משותפות לכל נכס נולד — {key: [{name,text,by,ts}]}. כל המשתמשים רואים את ההערות של כולם."""
    m = _load_config().get("nbNotes")
    return m if isinstance(m, dict) else {}

def _nb_notes_for(key, me9="", is_mgr=False):
    """רשימת הערות משותפות לנכס לפי key (ממוין מהישן לחדש).
    me9/is_mgr קובעים את הדגל mine (האם המשתמש רשאי למחוק את ההערה)."""
    lst = _nb_notes().get(key)
    if not isinstance(lst, list): return []
    out = [{"name": x.get("name", ""), "text": x.get("text", ""), "ts": x.get("ts", 0),
            "mine": bool(is_mgr or (me9 and x.get("by") == me9))}
           for x in lst if isinstance(x, dict) and (x.get("text") or "").strip()]
    out.sort(key=lambda x: x.get("ts", 0))
    return out

def _nb_cal_create(rec, date, organizer_email):
    """יוצר אירועי יומן לפגישה/פולואפ לפי הרשומה והתאריך — ביומן הקובע + הסוכן. מחזיר [{email,id}]."""
    label = _NB_STATUS_LABELS.get(rec.get("status"), "")
    addr = rec.get("addr", "")
    summary = label + " · " + (addr or "נכס נולד")
    desc = "נכס נולד · נקבע מ-Family Bot"
    if rec.get("note"):   desc += "\nהערה: " + rec["note"]
    if rec.get("owner"):  desc += "\nבעל הנכס: " + rec["owner"]
    if addr:              desc += "\nכתובת: " + addr
    if rec.get("price"):  desc += "\nמחיר: " + rec["price"]
    if rec.get("ophone"): desc += "\nטלפון בעל הנכס: " + rec["ophone"]
    start_iso = date; end_iso = None
    if "T" in date:
        if len(date) == 16: start_iso = date + ":00"
        try:
            from datetime import datetime as _dtm, timedelta as _td
            end_iso = (_dtm.fromisoformat(start_iso) + _td(hours=1)).isoformat()
        except Exception:
            end_iso = None
    nm = rec.get("agent", "")
    _ps = list(_phones_for_name(nm))
    _agent_g = _gauth_email_for_phone(_ps[0]) if _ps else ""
    _agent_mail = _agent_g or _agent_email_for(nm, _ps[0] if _ps else "")
    targets = []
    if organizer_email: targets.append(organizer_email)
    if _agent_g and all(_agent_g.lower() != e.lower() for e in targets):
        targets.append(_agent_g)
    invite = [_agent_mail] if (not _agent_g and _agent_mail and organizer_email and _agent_mail.lower() != organizer_email.lower()) else []
    cal = []
    for em in targets:
        atts = invite if em == organizer_email else []
        eid = gcal_create_event(em, summary, desc, start_iso, end_iso,
                                attendees=atts, send_updates=("all" if atts else "none"))
        if eid: cal.append({"email": em, "id": eid})
    return cal

def _newborn_created_epoch(r):
    raw = (r.get("נוצר בתאריך", "") or r.get("תאריך יצירה", "") or "").strip()
    if not raw:
        return 0
    raw = raw.replace("-", "/").split(",")[0].strip()
    import datetime as _dt
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%d.%m.%Y %H:%M", "%d.%m.%Y",
                "%Y/%m/%d %H:%M", "%Y/%m/%d", "%d/%m/%y %H:%M", "%d/%m/%y"):
        try:
            return _dt.datetime.strptime(raw, fmt).timestamp()
        except Exception:
            pass
    try:
        return _prop_epoch(r) or 0
    except Exception:
        return 0

def _detect_city(addr):
    """זיהוי עיר מתוך כתובת חופשית (לפילוח 'נכס נולד' לפי ערים)."""
    a = str(addr or "")
    if "ביאליק" in a: return "קרית ביאליק"
    if "מוצקין" in a: return "קרית מוצקין"
    if "אתא" in a: return "קרית אתא"
    if "חיים" in a or "חיפה" in a: return "חיפה"
    if "קרית ים" in a or "קריית ים" in a: return "קרית ים"
    return "אחר"

def _newborn_price(p):
    p = str(p or "").strip()
    if not p:
        return ""
    try:
        n = int(round(float(p.replace(",", "").replace("₪", "").strip())))
        return f"{n:,} ₪"
    except Exception:
        return p

# ── 🗺️ MAP: geocoding (חינם, OSM) + cache לפי כתובת + endpoint ──────────────
import datetime as _dt, threading as _th, json as _j2, os as _os2
_MAP_CITIES=["קרית ביאליק","קריית ביאליק","קרית מוצקין","קריית מוצקין","קרית ים","קריית ים",
 "קרית אתא","קריית אתא","קרית חיים","קריית חיים","קרית טבעון","טירת כרמל","נשר","חיפה","נהריה","עכו","אפק"]
def _mnc(c): return (c or "").replace("קריית","קרית").strip()
def _mkey(s):
    s=re.sub(r'["״\'`.,]',' ',s or '').replace("קריית","קרית")
    return re.sub(r'\s+',' ',s).strip().lower()
def _mcoop(s):
    """שדה 'street' מבולגן (רחוב+מספר+קומה+שכונה+עיר) → (רחוב+מספר, עיר)."""
    s=(s or "").strip(); city=""
    for c in sorted(_MAP_CITIES,key=len,reverse=True):
        if c in s: city=_mnc(c); break
    sp=re.split(r'קומה',s)[0].strip()
    if not re.search(r'קומה',s):
        for c in _MAP_CITIES: sp=sp.replace(c,"")
    sp=re.sub(r'\bדירת?\b|\d+\s*מ["״]ר','',sp)
    return re.sub(r'\s+',' ',sp).strip(' ,'),city
def _mdate(s):
    s=(s or "").strip().replace("T"," ").replace("Z"," ").strip()  # תומך גם ב-ISO: 2026-06-07T03:04:15Z
    tok=s.split()[0] if s.split() else ""
    for f in ("%d/%m/%Y","%d/%m/%y","%Y-%m-%d","%d.%m.%Y"):
        try: return _dt.datetime.strptime(tok,f).date()
        except: pass
    return None
def _mnb(v): v=str(v or "").strip(); return "" if v in ("","-","—") else v
_MBB=(29.4,33.45,34.2,35.95)  # כל ישראל — מציג את כל הנכסים, מסנן רק טעויות גאוקוד מחוץ למדינה
# cache: נטען מ-map-geocache.json אם קיים (seed אופציונלי שמזרז), אחרת ריק ובונה את עצמו.
_MGEO_PATH=_os2.path.join(_os2.environ.get("MAP_CACHE_DIR","") or _os2.path.dirname(__file__),"map-geocache.json")  # MAP_CACHE_DIR=דיסק קבוע ב-Render → שורד פריסות
_GKEY=_os2.environ.get("GOOGLE_GEOCODE_KEY","")  # אם מוגדר → Google Geocoding (דיוק בניין); אחרת Nominatim/OSM
_GSRC="google" if _GKEY else "osm"
try:
    _raw=_j2.load(open(_MGEO_PATH,encoding="utf-8"))
    _mgeo=({k:v for k,v in _raw.items() if v and k!="__src__"} if _raw.get("__src__")==_GSRC else {})  # החליפו מקור גאוקוד → בונים מחדש
except Exception: _mgeo={}
_mq=[]; _mbusy=[False]; _mlock=_th.Lock(); _mtried=set()  # כתובות שנכשלו בריצה הנוכחית — לא לנסות שוב עד הפעלה הבאה (retry אחרי deploy)
def _mworker():
    while True:
        with _mlock:
            if not _mq: _mbusy[0]=False; return
            addr=_mq.pop(0)
        k=_mkey(addr); res=None
        try:
            if _GKEY:   # Google — דיוק ברמת בניין
                r=requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address":addr+", ישראל","key":_GKEY,"region":"il","language":"he"},timeout=15)
                j=r.json()
                if j.get("status")=="OK" and j.get("results"):
                    loc=j["results"][0]["geometry"]["location"]; res=[float(loc["lat"]),float(loc["lng"])]
            else:
                r=requests.get("https://nominatim.openstreetmap.org/search",
                    params={"q":addr+", ישראל","format":"json","limit":1,"countrycodes":"il"},
                    headers={"User-Agent":"remax-family-map/1.0"},timeout=15)
                d=r.json(); res=[float(d[0]["lat"]),float(d[0]["lon"])] if d else None
        except Exception: res=None
        with _mlock:
            if res:
                _mgeo[k]=res
                try: _j2.dump(dict(_mgeo,__src__=_GSRC),open(_MGEO_PATH,"w",encoding="utf-8"))
                except Exception: pass
            else:
                _mtried.add(k)  # נכשל — לא נשמר לדיסק; יְנוסה שוב בהפעלה הבאה
        time.sleep(0.12 if _GKEY else 1.1)  # Google מהיר (3000/min); Nominatim צריך ~1.1s
def _mlookup(addr):
    k=_mkey(addr)
    if k in _mgeo: return _mgeo[k]
    with _mlock:
        if k in _mtried: return None  # כבר נוסה ונכשל בריצה הזו — לא להציף את התור
        if addr not in _mq: _mq.append(addr)
        if not _mbusy[0]: _mbusy[0]=True; _th.Thread(target=_mworker,daemon=True).start()
    return None  # יופיע בטעינה הבאה אחרי שיגאוקד ברקע
@app.route("/api/map/properties",methods=["GET"])
def api_map_properties():
    s=_web_auth()
    if not s: return jsonify({"ok":False,"auth":False}),401
    c=_cache_get("map_props",120)
    if c is not None: return jsonify({"ok":True,"items":c})
    cut=_dt.date.today()-_dt.timedelta(days=92); out=[]
    for r in fetch_sheet_rows():  # נכסי משרד — כל הנכסים (ללא סינון תאריך)
        city=_mnb(r.get("עיר / ישוב","")); street=_mnb(r.get("כתובת","")); house=_mnb(r.get("מספר בית",""))
        if not(city and street): continue
        ll=_mlookup(f"{street} {house}, {city}".strip())
        if ll and _MBB[0]<=ll[0]<=_MBB[1] and _MBB[2]<=ll[1]<=_MBB[3]:
            out.append({"t":"office","a":f"{street} {house}".strip(),"c":city,"p":_mnb(r.get("מחיר","")),
                "r":_mnb(r.get("חדרים","")),"z":_mnb(r.get('מ"ר',"") or r.get("מ״ר","")),"fl":_mnb(r.get("קומה","")),
                "g":_mnb(r.get("סוכן 1","")),"l":"","d":(r.get("_desc_ae","") or "").strip(),"lat":round(ll[0],5),"lng":round(ll[1],5)})
    for r in fetch_external_exclusives():  # שת"פ — כל הנכסים (ללא סינון תאריך)
        raw=_mnb(r.get("street",""))
        if not raw: continue
        sp,city=_mcoop(raw); ll=_mlookup(f"{sp}, {city}" if city else sp)
        if ll and _MBB[0]<=ll[0]<=_MBB[1] and _MBB[2]<=ll[1]<=_MBB[3]:
            out.append({"t":"coop","a":sp,"c":city,"p":_mnb(r.get("price","")),"r":"",
                "g":_mnb(r.get("office","")),"l":_mnb(r.get("link","")),"d":(r.get("desti","") or r.get("dest","") or "").strip(),"lat":round(ll[0],5),"lng":round(ll[1],5)})
    _cache_put("map_props",out)
    return jsonify({"ok":True,"items":out})

def _addr_tokens(*parts):
    """מנרמל כתובת לאסימונים: (מספרים, מילות רחוב/עיר משמעותיות) — לצורך הצלבה."""
    t = " ".join(str(p or "") for p in parts)
    t = re.sub(r"[^0-9֐-׿ ]", " ", t)
    _noise = {"רחוב", "רח", "שדרות", "שד", "דרך", "סמטה", "ככר", "כיכר", "דירה", "בית", "קומה"}
    toks = [w for w in t.split() if w]
    nums = set(w for w in toks if w.isdigit())
    words = set(w for w in toks if (not w.isdigit()) and len(w) >= 2 and w not in _noise)
    return nums, words

def _famexcl_addr_list():
    """כתובות שכבר בבלעדיות/טיפול RE/MAX Family — לסימון ב'נכס נולד', עם שם הסוכן.
    שלושה מקורות (בקשת אייל 13/07): בלעדויות חיצוניות (שת"פ — רק שלנו),
    נכסי המשרד (יד2, כל מודעה פעילה) וחתימות בלעדיות (OWNER_EXCLUSIVE).
    מוחזר כאינדקס לפי מספר-בית: {num: [(nums, words, agent), ...]} — כדי שההצלבה
    בנכס נולד תהיה מהירה (השוואה רק מול כתובות שחולקות מספר בית). cache 300ש'
    (המקורות כבר cached — הבנייה כאן היא רק טוקניזציה, פעם ב-5 דקות)."""
    c = _cache_get("famexcl_index", 300)
    if c is not None:
        return c
    idx = {}
    def _add(addr_parts, agent):
        nums, words = _addr_tokens(*addr_parts)
        if not nums or not words:
            return
        ent = (nums, words, (agent or "").strip())
        for n in nums:
            idx.setdefault(n, []).append(ent)
    # 1) בלעדויות חיצוניות — רק של רימקס פמילי (אין שדה סוכן אמין → ריק)
    try:
        for r in (fetch_external_exclusives() or []):
            if _is_our_office(r.get("office", "")):
                _add((r.get("street", ""),), "")
    except Exception:
        pass
    # 2) נכסי המשרד (יד2) — כל מודעה פעילה; הסוכן = "סוכן 1"
    try:
        for r in fetch_sheet_rows():
            if (r.get("סטטוס", "") or "").strip() not in ("", "פעילה"):
                continue
            street = (r.get("כתובת", "") or r.get("רחוב1", "") or r.get("רחוב", "") or "").strip()
            house = (r.get("מספר בית", "") or r.get("מס בית", "") or r.get("מס' בית", "") or r.get("בית", "") or "").strip()
            city = (r.get("עיר / ישוב", "") or r.get("עיר", "") or "").strip()
            _add((street, house, city), _canon_agent_name((r.get("סוכן 1", "") or "").strip()))
    except Exception:
        pass
    # 3) חתימות בלעדיות (OWNER_EXCLUSIVE) — הסוכן = agent
    try:
        for g in get_signings():
            if "OWNER_EXCLUSIVE" not in str(g.get("deal_type", "")).upper():
                continue
            _add((g.get("address", ""), g.get("city", "")), _canon_agent_name((g.get("agent", "") or "").strip()))
    except Exception:
        pass
    _cache_put("famexcl_index", idx)
    return idx

def _is_famexcl(addr, city, fam_idx):
    """מחזיר את שם הסוכן שבבלעדיות אם הכתובת כבר בטיפול RE/MAX Family, אחרת None.
    שמרני: כל אסימוני הנכס (מספר+רחוב+עיר) חייבים להופיע בכתובת שבמקור.
    בודק רק מול כתובות שחולקות מספר בית (דרך האינדקס) — מהיר גם עם אלפי נכסים."""
    if not fam_idx:
        return None
    nb_nums, nb_words = _addr_tokens(addr, city)
    if not nb_nums or not nb_words:
        return None
    need = nb_nums | nb_words
    seen = set()
    best = None
    for n in nb_nums:
        for ex_nums, ex_words, agent in fam_idx.get(n, ()):
            _id = id(ex_words)
            if _id in seen:
                continue
            seen.add(_id)
            if need <= (ex_nums | ex_words):
                if agent:
                    return agent       # התאמה עם שם סוכן — עדיפה
                best = ""               # התאמה בלי שם (בלעדיות חיצונית) — שומרים כגיבוי
    return best

_NB_RESULT_VER = [0]   # מעלים בכל שינוי (סטטוס/הערה/פנייה) כדי לבטל את מטמון התוצאה לכל הסקופים
_NB_BUCKETS = [(0, 30), (30, 60), (60, 90), (90, 120), (120, 150), (150, 180), (180, 10**9)]   # דליי ותק לפי חודשים — חייב להתאים ל-NB_AGE_BUCKETS בפרונט

@app.route("/api/newborn", methods=["GET", "POST"])
def api_newborn():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    try:
        as_name = ""
        if s["role"] in ("admin", "coordinator"):
            as_name = ((request.get_json(silent=True) or {}).get("as", "")
                       or request.args.get("as", "")).strip()
        eff_name = as_name or s.get("name", "")
        eff_norm = _norm_name(eff_name)
        # חיפוש: מחזיר התאמות מכל הפול (300 האחרונים) — גם נכסים שעוד לא נחשפו לסוכן
        q = (request.args.get("q", "") or ((request.get_json(silent=True) or {}).get("q", "")) or "").strip().lower()
        # סינון לפי ותק בפרסום (דלי נבחר) — נשלח מהפרונט
        def _intp(nm):
            try: return int(str(request.args.get(nm) or ((request.get_json(silent=True) or {}).get(nm)) or "").strip())
            except Exception: return None
        min_days = _intp("minDays"); max_days = _intp("maxDays")
        # [PERF-3] etag: הקליינט שולח את טביעת-האצבע של התוצאה הקודמת; אם אין שינוי —
        # מוחזרת תשובה זעירה (unchanged) במקום מאות KB. חוסך דאטה/סוללה ברענון של כל דקה.
        _etag_in = (request.args.get("etag", "") or ((request.get_json(silent=True) or {}).get("etag", "")) or "").strip()
        # מטמון תוצאה לפי סקופ — פתיחה חוזרת של הטאב מיידית (מתבטל בכל שינוי דרך _NB_RESULT_VER)
        _nbkey = "nbres:%d:%s:%s:%s:%s:%s" % (_NB_RESULT_VER[0], _last9(s.get("phone", "")), as_name, q, min_days, max_days)
        _nbc = _cache_get(_nbkey, _src_ttl(NEWBORN_SOURCE, 90, 12))
        if _nbc is not None:
            if _etag_in and _etag_in == _nbc.get("etag"):
                return jsonify({"ok": True, "unchanged": True, "etag": _etag_in})
            return jsonify(_nbc)
        # מנהל מושהה (כמו אווה אזולאי) אינו רואה "נכס נולד" מיד — נכנס למסלול ההשהיה הרגיל
        _dphone = "" if as_name else s.get("phone", "")
        admin_all = (s["role"] == "admin" and not as_name and not _delayed_admin_days(eff_name, _dphone))
        delays = _fetch_newborn_delays()
        _eff_ck = "c:" + _canon_key(eff_name)   # התאמה קנונית — איות שונה של אותו סוכן עדיין נתפס
        _has_personal = (eff_norm in delays) or (_eff_ck in delays)
        delay = 0 if admin_all else int(delays.get(eff_norm, delays.get(_eff_ck, delays.get("_default", 0))))
        _dadays = _delayed_admin_days(eff_name, _dphone)
        if _dadays and not admin_all and not _has_personal:   # בלי הגדרה אישית → השהיית ברירת מחדל
            delay = _dadays
        if not admin_all and delay >= NEWBORN_HIDDEN:   # מוסתר — לא רואה כלום, אין באנר
            return jsonify({"ok": True, "count": 0, "released": 0, "delay": delay, "results": []})
        now = time.time()
        contacts = _fetch_newborn_contacts()
        nbstatuses = _nb_statuses()
        fam_list = _famexcl_addr_list()
        rows = [r for r in fetch_newborn() if _newborn_created_epoch(r)]
        rows.sort(key=_newborn_created_epoch, reverse=True)
        out = []
        bucket_counts = [0] * len(_NB_BUCKETS)
        for r in rows:
            created = _newborn_created_epoch(r)
            age_f = (now - created) / 86400
            if age_f > NEWBORN_WINDOW_DAYS:   # ישנים מדי לא מציגים
                continue
            def _nb(v):
                v = str(v or "").strip()
                return "" if v in ("-", "—", "") else v
            lister = _nb(r.get("משתמש", "") or r.get("סוכן 1", ""))
            own = bool(eff_norm) and bool(lister) and _norm_name(lister) == eff_norm
            rel_epoch = created + delay * 86400
            released = admin_all or own or now >= rel_epoch
            city = _nb(r.get("עיר", "") or r.get("עיר / ישוב", ""))
            _addr = _nb(r.get("רחוב1", "") or r.get("רחוב", ""))
            _owner = _nb(r.get("שם בעל הנכס", ""))
            if q:
                # מצב חיפוש — מכל הפול, ללא השהיה/הסתרה; חיפוש לפי רחוב, שכונה (שדה ייעודי או מהתיאור), עיר ובעל הנכס
                _hood = _nb(r.get("שכונה", "") or r.get("שכונה ", "") or r.get("שכונה/אזור", ""))
                _dsc = str(r.get("תיאור נכס", "") or "")
                if q not in (_addr + " " + _owner + " " + city + " " + _hood + " " + _dsc).lower():
                    continue
            else:
                if not released:
                    continue   # מציגים רק נכסים שכבר נחשפו לסוכן
            ad = int(age_f)
            for _bi, (_lo, _hi) in enumerate(_NB_BUCKETS):   # ספירת דליים על *כל* הנכסים הנראים (לא רק 300)
                if _lo <= ad < _hi:
                    bucket_counts[_bi] += 1
                    break
            if min_days is not None and max_days is not None and not (min_days <= ad < max_days):
                continue   # לא בדלי הוותק שנבחר
            if len(out) >= 5000:   # תקרת בטיחות גבוהה; כל הנכסים חוזרים בטעינה אחת לסינון חודשים בצד הלקוח
                continue
            _k = _nb_key(r)
            _vstat = nbstatuses.get(_canon_key(eff_name) + "::" + _k)
            ophone = _nb(r.get("טלפון בעל הנכס-", "") or r.get("טלפון בעל הנכס", ""))
            _famv = _is_famexcl(_addr, city, fam_list)   # שם הסוכן שבבלעדיות / '' / None
            out.append({
                "released": True,
                "own": own,
                "key": _k,
                "contacted": contacts.get(_k, []),
                "city": city,
                "address": _addr,
                "desc": _nb(r.get("תיאור נכס", "")),
                "price": _newborn_price(r.get("מחיר", "")),
                "notes": _nb(r.get("הערות חדש", ""))[:160],
                "owner": _owner,
                "phone": _fmt_vphone(ophone),
                "wa": _wa_phone(ophone),
                "agent": lister,
                "link": _nb(r.get("קישור", "")),
                "date": _nb(r.get("נוצר בתאריך", "") or r.get("תאריך יצירה", "")),
                "stat": _vstat or None,
                "unotes": _nb_notes_for(_k, _last9(s.get("phone", "")), (s["role"] == "admin" or _is_dev(s.get("phone", "")))),
                "ageDays": ad,
                "famexcl": (_famv is not None),
                "famexclAgent": (_famv or ""),
            })
        _res = {"ok": True, "count": len(out), "released": len(out), "delay": delay,
                "results": out, "bucketCounts": bucket_counts, "total": sum(bucket_counts)}
        # [PERF-3] טביעת-אצבע לתוצאה — מחושבת פעם אחת בבנייה (לא פר-בקשה)
        import zlib as _zl
        _res["etag"] = format(_zl.crc32(_json.dumps(
            [out, bucket_counts], ensure_ascii=False, sort_keys=True).encode("utf-8")) & 0xffffffff, "08x")
        if rows:   # אין לקבע במטמון תוצאה שנבנתה מקריאה ריקה/כושלת
            _cache_put(_nbkey, _res)
        if _etag_in and _etag_in == _res["etag"]:
            return jsonify({"ok": True, "unchanged": True, "etag": _etag_in})
        return jsonify(_res)
    except Exception as e:
        log.error(f"newborn error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

@app.route("/api/newborn/contact", methods=["POST"])
def api_newborn_contact():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    d = request.get_json(silent=True) or {}
    key = (d.get("key", "") or "").strip()
    addr = (d.get("addr", "") or "").strip()
    as_name = (d.get("as", "") or "").strip() if s["role"] in ("admin", "coordinator") else ""
    nm = as_name or s.get("name", "")
    _log_activity(nm, s["role"], s.get("phone", ""), "📲 וואטסאפ — נכס נולד", addr or key)
    if key:
        try:
            _threading.Thread(
                target=lambda: _buyers_apps_post("newborncontact",
                                                 {"key": key, "agent": nm, "addr": addr}),
                daemon=True).start()
        except Exception:
            pass
        _cache_clear("newborn_contacts")
    _NB_RESULT_VER[0] += 1
    return jsonify({"ok": True})

@app.route("/api/newborn/status", methods=["POST"])
def api_newborn_status():
    """עדכון סטטוס טיפול לנכס נולד. meeting/followup עם תאריך → אירוע ביומן Google של הסוכן."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    d = request.get_json(silent=True) or {}
    key = (d.get("key", "") or "").strip()
    addr = (d.get("addr", "") or "").strip()
    price = (d.get("price", "") or "").strip()
    owner_phone = (d.get("phone", "") or "").strip()
    owner_name = (d.get("owner", "") or "").strip()
    status = (d.get("status", "") or "").strip()
    date = (d.get("date", "") or "").strip()   # 'YYYY-MM-DD' או 'YYYY-MM-DDTHH:MM'
    as_name = (d.get("as", "") or "").strip() if s["role"] in ("admin", "coordinator") else ""
    # סוכן יעד: מתאמת/מנהל בוחרים סוכן; סוכן רגיל = עצמו. מתאמת מוגבלת לסוכנים שלה.
    chosen = (d.get("agent", "") or "").strip() if s["role"] in ("admin", "coordinator") else ""
    if chosen and s["role"] == "coordinator":
        cc = _coordinators_all().get(_last9(s.get("phone", "")))
        allowed = set()
        if cc:
            allowed |= set(_canon_key(n) for n in (cc.get("names") or set()))
            for ph in (cc.get("agents") or set()):
                _nmm = web_phone_name_map().get(_last9(ph)) or web_contacts_phone_name().get(_last9(ph))
                if _nmm: allowed.add(_canon_key(_nmm))
        if _canon_key(chosen) not in allowed:
            # "אחר במשרד…" — מותר לתאם גם לסוכן שאינו שלה, כל עוד הוא סוכן מוכר במשרד
            _office = set(_canon_key(n) for n in web_phone_name_map().values() if n)
            try:
                _office |= set(_canon_key(a.get("name", "")) for a in (_load_config().get("agents") or []) if a.get("name"))
            except Exception:
                pass
            if _canon_key(chosen) not in _office:
                chosen = ""   # שם לא מוכר — מתעלמים
    nm = chosen or as_name or s.get("name", "")
    if not key or status not in _NB_STATUS_LABELS:
        return jsonify({"ok": False, "reason": "bad_input"}), 400
    if status in ("meeting", "followup") and not date:
        return jsonify({"ok": False, "reason": "no_date"}), 400
    # מפתח לפי סוכן+נכס — כך שכל סוכן רואה את הסטטוס שלו והסתרת "לא ניתן לגיוס" היא אישית
    skey = _canon_key(nm) + "::" + key
    # תגית פולו-אפ: 'before' (לפני פגישה) / 'after' (אחרי פגישה) / '' (כללי). בקשת אייל 13/07.
    _tag = (d.get("tag", "") or "").strip()
    if _tag not in ("before", "after"):
        _tag = ""
    rec = {"status": status, "addr": addr, "agent": nm, "pkey": key, "ts": int(time.time()),
           "owner": owner_name, "price": price, "ophone": owner_phone,
           "note": str(d.get("note", "") or "")[:1000], "tag": _tag,
           "date": (date if status in ("meeting", "followup") else ""), "cal": []}
    # אירוע יומן לפגישה/פולואפ (שומרים מזהי אירוע למחיקה/עריכה עתידית)
    cal_ok = False
    if status in ("meeting", "followup") and date:
        rec["cal"] = _nb_cal_create(rec, date, _gauth_email_for_phone(s.get("phone", "")))
        cal_ok = bool(rec["cal"])
    # שמירה בקונפיג — RMW בטוח (נעילה + קריאה טרייה + כתיבה durable). בלי זה כמה
    # פגישות ברצף (או _mark_joined ברקע בכניסה) דרסו זו את זו והפגישות "נעלמו". אייל 13/07.
    def _mut(cfg):
        m = cfg.get("nbStatus")
        if not isinstance(m, dict): m = {}
        # "מי תיאם" — נשמר מהיוצר; בעריכה נשמר המקורי (לא נדרס למי שערך אחרון).
        _prev = m.get(skey) or {}
        rec["by"] = _prev.get("by") or s.get("name", "")
        rec["by_phone"] = _prev.get("by_phone") or _last9(s.get("phone", ""))
        m[skey] = rec
        cfg["nbStatus"] = m
    ok, _ = _config_mutate(_mut)
    if not ok:   # שמירה נכשלה — לא מדווחים הצלחה כוזבת
        return jsonify({"ok": False, "reason": "save_failed"})
    _NB_RESULT_VER[0] += 1
    # יומן פעילות: מי עשה = המתאם בפועל (המשתמש), לא סוכן היעד; היעד נכנס לפירוט
    _tgt = (" · לסוכן " + nm) if _canon_key(nm) != _canon_key(s.get("name", "")) else ""
    _log_activity(s.get("name", ""), s["role"], s.get("phone", ""), "סטטוס נכס נולד",
                  (_NB_STATUS_LABELS.get(status, status) + " · " + (addr or key) + _tgt)[:100])
    return jsonify({"ok": True, "calendar": cal_ok, "status": status, "date": date})

@app.route("/api/newborn/note", methods=["POST"])
def api_newborn_note():
    """הוספת הערה משותפת לנכס נולד — כל המשתמשים רואים את ההערות של כולם."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    d = request.get_json(silent=True) or {}
    key = (d.get("key", "") or "").strip()
    addr = (d.get("addr", "") or "").strip()
    text = (d.get("text", "") or "").strip()[:500]
    if not key or not text:
        return jsonify({"ok": False, "reason": "bad_input"}), 400
    def _mut(cfg):   # RMW בטוח — הערה לא תיעלם בגלל כתיבה מתחרה
        m = cfg.get("nbNotes")
        if not isinstance(m, dict): m = {}
        lst = m.get(key)
        if not isinstance(lst, list): lst = []
        lst.append({"name": s.get("name", ""), "by": _last9(s.get("phone", "")),
                    "text": text, "ts": int(time.time())})
        m[key] = lst
        cfg["nbNotes"] = m
    _config_mutate(_mut)
    _NB_RESULT_VER[0] += 1
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                  "הערה נכס נולד", (addr or key) + " · " + text[:60])
    return jsonify({"ok": True, "notes": _nb_notes_for(key, _last9(s.get("phone", "")), (s["role"] == "admin" or _is_dev(s.get("phone", ""))))})

@app.route("/api/newborn/note/delete", methods=["POST"])
def api_newborn_note_delete():
    """מחיקת הערה — רק הכותב או מנהל/מפתח."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    d = request.get_json(silent=True) or {}
    key = (d.get("key", "") or "").strip()
    ts = int(d.get("ts", 0) or 0)
    if not key or not ts:
        return jsonify({"ok": False, "reason": "bad_input"}), 400
    my9 = _last9(s.get("phone", ""))
    is_mgr = (s["role"] == "admin") or _is_dev(s.get("phone", ""))
    _found = [False]
    def _mut(cfg):   # RMW בטוח
        m = cfg.get("nbNotes")
        if not isinstance(m, dict): return
        lst = m.get(key)
        if not isinstance(lst, list): return
        _found[0] = True
        m[key] = [x for x in lst if not (int(x.get("ts", 0) or 0) == ts and (is_mgr or x.get("by") == my9))]
        cfg["nbNotes"] = m
    _config_mutate(_mut)
    if not _found[0]:
        return jsonify({"ok": True, "notes": []})
    _NB_RESULT_VER[0] += 1
    return jsonify({"ok": True, "notes": _nb_notes_for(key, my9, is_mgr)})

@app.route("/api/newborn/meetings", methods=["GET"])
def api_newborn_meetings():
    """פגישות ופולו-אפ מ'נכס נולד' — סוכן רואה את שלו, מתאמת את כל הצוות שלה, מנהל את הכל."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    allowed = None   # None = הכל (מנהל)
    if s["role"] == "coordinator":
        allowed = set()
        cc = _coordinators_all().get(_last9(s.get("phone", "")))
        if cc:
            allowed |= set(_canon_key(n) for n in (cc.get("names") or set()))
            for ph in (cc.get("agents") or set()):
                nm = web_phone_name_map().get(_last9(ph)) or web_contacts_phone_name().get(_last9(ph))
                if nm: allowed.add(_canon_key(nm))
        allowed.add(_canon_key(s.get("name", "")))
    elif s["role"] != "admin":
        allowed = {_canon_key(s.get("name", ""))}
    _inc_done = request.args.get("done") == "1"   # מסך היומן מבקש גם 'בוצע'; הבית לא
    out = []
    for k, st in (_nb_statuses() or {}).items():
        if st.get("status") not in ("meeting", "followup"):
            continue
        if allowed is not None and _canon_key(st.get("agent", "")) not in allowed:
            continue
        if st.get("done") and not _inc_done:
            continue   # 'בוצע' — לא מוצג בתצוגות הפעילות (בית/דורש טיפול)
        _oph = (st.get("ophone", "") or "").strip()
        _dig = "".join(ch for ch in _oph if ch.isdigit())
        _wa = ("" if not _dig else (_dig if _dig.startswith("972") else "972" + _dig.lstrip("0")))
        out.append({"status": st.get("status"), "label": _NB_STATUS_LABELS.get(st.get("status"), ""),
                    "date": st.get("date", ""), "agent": st.get("agent", ""),
                    "by": st.get("by", ""),   # מי תיאם את הפגישה/פולו-אפ (המתאם/מנהל שיצר)
                    "tag": st.get("tag", ""),   # 'before'/'after'/'' — קטגוריית פולו-אפ
                    "done": bool(st.get("done")),   # 'בוצע' (אחרי לחיצת וי)
                    "addr": st.get("addr", ""), "skey": k,
                    "ophone": _oph, "wa": _wa, "owner": st.get("owner", ""), "note": st.get("note", "")})
    out.sort(key=lambda x: str(x.get("date", "")))
    return jsonify({"ok": True, "results": out})

@app.route("/api/newborn/status/delete", methods=["POST"])
def api_newborn_status_delete():
    """מחיקת פגישה/פולו-אפ — מסיר מהקונפיג וגם מוחק את אירוע היומן."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    d = request.get_json(silent=True) or {}
    cfg = _load_config()
    m = cfg.get("nbStatus")
    if not isinstance(m, dict): m = {}
    # מחיקה לפי מפתח האחסון המדויק (skey) — תומך גם ברשומות ישנות ללא pkey
    skey = (d.get("skey", "") or "").strip()
    if not skey:
        pkey = (d.get("pkey", "") or d.get("key", "") or "").strip()
        agent = (d.get("agent", "") or "").strip() or s.get("name", "")
        if not pkey:
            return jsonify({"ok": False, "reason": "no_key"}), 400
        skey = _canon_key(agent) + "::" + pkey
    rec = m.get(skey)
    if not rec:
        return jsonify({"ok": False, "reason": "not_found"}), 404
    # הרשאה: סוכן מוחק את שלו; מתאמת את הסוכנים שלה; מנהל הכל
    if s["role"] != "admin":
        allowed = {_canon_key(s.get("name", ""))}
        if s["role"] == "coordinator":
            cc = _coordinators_all().get(_last9(s.get("phone", "")))
            if cc:
                allowed |= set(_canon_key(n) for n in (cc.get("names") or set()))
                for ph in (cc.get("agents") or set()):
                    nm = web_phone_name_map().get(_last9(ph)) or web_contacts_phone_name().get(_last9(ph))
                    if nm: allowed.add(_canon_key(nm))
        if _canon_key(rec.get("agent", "")) not in allowed:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
    for ev in (rec.get("cal") or []):   # מחיקה מהיומן
        try: gcal_delete_event(ev.get("email", ""), ev.get("id", ""))
        except Exception: pass
    def _mut(cfg):   # RMW בטוח — לא לדרוס פגישות אחרות שנכתבו בו-זמנית
        mm = cfg.get("nbStatus")
        if isinstance(mm, dict):
            mm.pop(skey, None)
            cfg["nbStatus"] = mm
    _config_mutate(_mut)
    _NB_RESULT_VER[0] += 1
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "מחיקת פגישה/פולו-אפ", (rec.get("addr") or skey)[:80])
    return jsonify({"ok": True})

@app.route("/api/newborn/status/edit", methods=["POST"])
def api_newborn_status_edit():
    """עריכת תאריך/שעה של פגישה/פולו-אפ — מעדכן ביומן (מוחק את הישן ויוצר חדש)."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    d = request.get_json(silent=True) or {}
    skey = (d.get("skey", "") or "").strip()
    new_date = (d.get("date", "") or "").strip()
    new_status = (d.get("status", "") or "").strip()
    note_in = d.get("note", None)   # None = לא נשלח (לא לגעת); "" = ניקוי הערה
    if not skey or (not new_date and new_status not in ("meeting", "followup") and note_in is None):
        return jsonify({"ok": False, "reason": "bad_input"}), 400
    cfg = _load_config()
    m = cfg.get("nbStatus")
    if not isinstance(m, dict): m = {}
    rec = m.get(skey)
    if not rec:
        return jsonify({"ok": False, "reason": "not_found"}), 404
    if rec.get("status") not in ("meeting", "followup"):
        return jsonify({"ok": False, "reason": "not_editable"}), 400
    # הרשאה: סוכן את שלו; מתאמת את הסוכנים שלה; מנהל הכל
    if s["role"] != "admin":
        allowed = {_canon_key(s.get("name", ""))}
        if s["role"] == "coordinator":
            cc = _coordinators_all().get(_last9(s.get("phone", "")))
            if cc:
                allowed |= set(_canon_key(n) for n in (cc.get("names") or set()))
                for ph in (cc.get("agents") or set()):
                    nm = web_phone_name_map().get(_last9(ph)) or web_contacts_phone_name().get(_last9(ph))
                    if nm: allowed.add(_canon_key(nm))
        if _canon_key(rec.get("agent", "")) not in allowed:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
    cal_changed = False
    if new_status in ("meeting", "followup") and new_status != rec.get("status"):
        rec["status"] = new_status
        cal_changed = True
    if note_in is not None and str(note_in)[:1000] != (rec.get("note") or ""):
        rec["note"] = str(note_in)[:1000]
        cal_changed = True   # ההערה מופיעה בתיאור אירוע היומן — רענון שישקף אותה
    if "tag" in d:   # עדכון תגית לפני/אחרי פגישה
        _t = (d.get("tag", "") or "").strip()
        rec["tag"] = _t if _t in ("before", "after") else ""
    if new_date and new_date != rec.get("date", ""):
        rec["date"] = new_date
        cal_changed = True
    if cal_changed:
        for ev in (rec.get("cal") or []):   # מחיקת אירוע היומן הישן
            try: gcal_delete_event(ev.get("email", ""), ev.get("id", ""))
            except Exception: pass
        rec["cal"] = _nb_cal_create(rec, rec.get("date", ""), _gauth_email_for_phone(s.get("phone", "")))
    rec["ts"] = int(time.time())
    def _mut(cfg):   # RMW בטוח — כותב רק את skey הזה, לא דורס פגישות אחרות בו-זמנית
        mm = cfg.get("nbStatus")
        if not isinstance(mm, dict): mm = {}
        mm[skey] = rec
        cfg["nbStatus"] = mm
    _config_mutate(_mut)
    _NB_RESULT_VER[0] += 1
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עריכת פגישה/פולו-אפ", (rec.get("addr") or skey)[:80])
    return jsonify({"ok": True, "calendar": bool(rec.get("cal"))})

@app.route("/api/newborn/status/done", methods=["POST"])
def api_newborn_status_done():
    """סימון פגישה/פולו-אפ כ'בוצע' (במקום מחיקה) — עובר לקטגוריית 'בוצע', נשמר.
    אפשר גם להחזיר (done=false). מסיר את אירוע היומן כשמסמנים בוצע. בקשת אייל 13/07."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    d = request.get_json(silent=True) or {}
    skey = (d.get("skey", "") or "").strip()
    done = bool(d.get("done", True))
    if not skey:
        return jsonify({"ok": False, "reason": "no_key"}), 400
    m = (_load_config().get("nbStatus") or {})
    rec = m.get(skey)
    if not rec:
        return jsonify({"ok": False, "reason": "not_found"}), 404
    # הרשאה: סוכן את שלו; מתאמת את הסוכנים שלה; מנהל הכל (זהה למחיקה/עריכה)
    if s["role"] != "admin":
        allowed = {_canon_key(s.get("name", ""))}
        if s["role"] == "coordinator":
            cc = _coordinators_all().get(_last9(s.get("phone", "")))
            if cc:
                allowed |= set(_canon_key(n) for n in (cc.get("names") or set()))
                for ph in (cc.get("agents") or set()):
                    nm = web_phone_name_map().get(_last9(ph)) or web_contacts_phone_name().get(_last9(ph))
                    if nm: allowed.add(_canon_key(nm))
        if _canon_key(rec.get("agent", "")) not in allowed:
            return jsonify({"ok": False, "reason": "forbidden"}), 403
    if done:   # בסימון בוצע — מסירים את אירוע היומן (העבר, אין צורך בתזכורת)
        for ev in (rec.get("cal") or []):
            try: gcal_delete_event(ev.get("email", ""), ev.get("id", ""))
            except Exception: pass
    def _mut(cfg):   # RMW בטוח — כותב רק את skey הזה
        mm = cfg.get("nbStatus")
        if not isinstance(mm, dict): return
        r = mm.get(skey)
        if not r: return
        r["done"] = done
        r["done_at"] = _sign_now_iso() if done else ""
        if done: r["cal"] = []
        cfg["nbStatus"] = mm
    _config_mutate(_mut)
    _NB_RESULT_VER[0] += 1
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""),
                  ("סימון בוצע" if done else "החזרה מבוצע") + " · פגישה/פולו-אפ", (rec.get("addr") or skey)[:80])
    return jsonify({"ok": True, "done": done})

# ── Exclusivity search ─────────────────────────────────────────────────────────
def _web_num(v):
    if v is None or v == "": return None
    try: return float(v)
    except: return None

def _dedupe_exclusives(rows):
    """אם אותו נכס מופיע כמה פעמים (לפי הכתובת) — להשאיר רק את החדש ביותר."""
    best = {}
    for r in rows:
        key = re.sub(r"\s+", " ", str(r.get("street", "") or "")).strip().lower()
        if not key:
            key = "id:" + str(r.get("event_id", ""))
        cur = best.get(key)
        if cur is None or _excl_epoch(r.get("received_at", "")) > _excl_epoch(cur.get("received_at", "")):
            best[key] = r
    return list(best.values())

@app.route("/api/search/exclusives", methods=["POST"])
def api_search_exclusives():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    try:
        q = (request.get_json(silent=True) or {}).get("q", "").strip()
        if q: _log_activity(s["name"], s["role"], s["phone"], "חיפוש בלעדיות", q)
        if not (request.get_json(silent=True) or {}).get("nosave"):
            _push_recent(s["phone"], "excl", q)
        parsed = parse_exclusivity_search_query(q if q.startswith("מחפש") else ("מחפש בלעדיות " + q)) or {}
        parsed["budget_max"] = _web_num(parsed.get("budget_max"))   # מנע TypeError בכפל
        parsed["rooms"]      = _web_num(parsed.get("rooms"))
        rows = _dedupe_exclusives(fetch_external_exclusives())
        if not (parsed.get("city") or parsed.get("cities") or parsed.get("neighborhood") or parsed.get("neighborhoods") or parsed.get("rooms") or parsed.get("budget_max") or parsed.get("keywords") or parsed.get("property_type")):
            # "כל הבלעדיות" (בלי חיפוש) — כל השת"פ, כמו שהמשרד מציג את כל 471 (בלי
            # חיתוך ל-30 שהסתיר נכסים; תיקון "רק 27 בשת\"פ", 19/07). ממויין מהחדש לישן.
            rows = sorted(rows, key=lambda r: _excl_epoch(r.get("received_at", "")), reverse=True)
            matches = [(1, r) for r in rows]
        else:
            scored = [(score_exclusivity_match(r, parsed), r) for r in rows]
            scored = [(sc, r) for sc, r in scored if sc > 0]
            scored.sort(key=lambda x: -x[0])
            matches = scored[:15]
        out = []
        for sc, r in matches:
            _raw = _mnb(r.get("street", "")); _ll = None
            if _raw:
                _sp, _ci = _mcoop(_raw); _ll = _mlookup(f"{_sp}, {_ci}" if _ci else _sp)
            out.append({
                "score": min(100, int(sc)),
                "street": str(r.get("street", "") or "").strip(),
                "dest": str(r.get("dest", "") or "").strip(),
                "desc": str(r.get("desti", "") or "").strip(),
                "price": str(r.get("price", "") or "").strip(),
                "office": str(r.get("office", "") or "").strip(),
                "own": _is_our_office(r.get("office", "")),   # בלעדיות חיצונית של רימקס פמילי עצמו → הבלטה בלקוח
                "date": str(r.get("received_at", "") or "")[:10],
                "link": str(r.get("link", "") or "").strip(),
                "lat": round(_ll[0], 6) if _ll else None,
                "lng": round(_ll[1], 6) if _ll else None,
            })
        return jsonify({"ok": True, "summary": parsed.get("summary_he", ""), "ptype": parsed.get("property_type", ""), "results": out})
    except Exception as e:
        log.error(f"exclusives search error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

# ── Buyer search (in agent's own answered calls) ───────────────────────────────
@app.route("/api/search/buyers", methods=["POST"])
def api_search_buyers():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    try:
        q = (request.get_json(silent=True) or {}).get("q", "").strip()
        _log_activity(s["name"], s["role"], s["phone"], "חיפוש קונים", q)
        parsed = parse_buyer_search_query(q if q.startswith("מחפש") else ("מחפש קונה " + q)) or {}
        # candidates = answered calls (agent → his own; admin → all)
        as_name = (request.get_json(silent=True) or {}).get("as", "").strip() if s["role"] == "admin" else ""
        as_pset = _phones_for_name(as_name) if as_name else set()
        if as_pset:
            candidates = [c for c in web_fetch_raw("שיחות")
                          if str(c.get("status", "")).upper() == "ANSWER" and _last9(c.get("agent_phone", "")) in as_pset]
        elif s["role"] == "admin":
            candidates = [c for c in web_fetch_raw("שיחות") if str(c.get("status", "")).upper() == "ANSWER"]
        elif s["role"] == "coordinator":
            agset = set(s.get("agents") or [])
            candidates = [c for c in web_fetch_raw("שיחות")
                          if str(c.get("status", "")).upper() == "ANSWER" and _last9(c.get("agent_phone", "")) in agset]
        else:
            candidates = fetch_calls_for_agent(s["phone"])
        target_budget = _web_num(parsed.get("budget"))
        if target_budget:
            filt = []
            for c in candidates:
                cb = extract_budget_from_transcript(c.get("transcript_summary", ""))
                if cb is None: continue
                if abs(cb - target_budget) / target_budget <= 0.30: filt.append(c)
            candidates = filt
        keywords = parsed.get("keywords") or []
        if not keywords:
            candidates.sort(key=lambda c: _epoch_from_iso(c.get("received_at", "")), reverse=True)
            matches = candidates[:10]
        else:
            scored = []
            for c in candidates:
                t = str(c.get("transcript_summary", "")).lower()
                sc = sum(1 for k in keywords if str(k).strip().lower() in t)
                if sc > 0: scored.append((sc, c))
            scored.sort(key=lambda x: (-x[0], -_epoch_from_iso(x[1].get("received_at", ""))))
            matches = [c for _, c in scored[:10]]
            if not matches:
                candidates.sort(key=lambda c: _epoch_from_iso(c.get("received_at", "")), reverse=True)
                matches = candidates[:10]
        out = []
        for c in matches:
            disp, tel = _il_phone(c.get("caller_phone", ""))
            out.append({
                "phone": disp,
                "tel": tel,
                "wa": _wa_phone(c.get("caller_phone", "")),
                "agent": (c.get("agent", "") or "").strip(),
                "date": _fmt_il_dt(c.get("received_at", "")),
                "budget": format_price_il(extract_budget_from_transcript(c.get("transcript_summary", ""))),
                "summary": re.sub(r"https?://\S+", "", str(c.get("transcript_summary", ""))).strip(),
            })
        return jsonify({"ok": True, "summary": parsed.get("summary_he", ""), "results": out})
    except Exception as e:
        log.error(f"buyers search error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

# ── Manual buyers — נשמרים בטאב "קונים" בקובץ נדל"ן וואן דרך ה-Apps Script ──────
def _buyers_apps_post(action, payload):
    """שולח פעולה (addbuyer/listbuyers) ל-Apps Script ומחזיר את ה-JSON."""
    if not (APPS_SCRIPT_URL and APPS_SCRIPT_TOKEN):
        return None
    data = {"action": action, "token": APPS_SCRIPT_TOKEN}
    data.update(payload or {})
    try:
        r = requests.post(APPS_SCRIPT_URL, data=data, timeout=30, allow_redirects=True)
        return r.json()
    except Exception as e:
        log.error(f"buyers {action} error: {e}")
        return None

# ── מסמכי החתימה: Supabase ראשי, הגיליון גיבוי (05/08 — Apps Script זחל 20-40ש'
#    והפיל את עמוד ההסכם; המסמך הוא הנתיב שהלקוח פוגש, אסור תלות בגוגל) ─────────
def _signdoc_save(payload):
    """שמירה: Supabase סינכרוני — ה-SMS נשלח רק אחרי ok (אין מסמך = אין קישור מת);
    הצלחה → העתק לגיליון ברקע. Supabase נופל → Apps Script סינכרוני (כמו קודם)."""
    if _sbdb and _sbdb.enabled() and _sbdb.signdoc_save(payload):
        def _bg():
            try:
                _buyers_apps_post("savesigndoc", payload)
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()
        return {"ok": True}
    return _buyers_apps_post("savesigndoc", payload)

def _signdoc_get(token):
    """קריאה: Supabase קודם (מילישניות); לא נמצא (מסמך ישן) → Apps Script —
    כל הקישורים שנשלחו לפני המעבר ממשיכים לעבוד."""
    if _sbdb and _sbdb.enabled():
        d = _sbdb.signdoc_get(token)
        if d is not None:
            return {"ok": True, "found": True, "doc": d}
    return _buyers_apps_post("getsigndoc", {"doc_token": token})

def _signdoc_update(token, fields):
    """עדכון (חתימת הלקוח): Supabase סינכרוני; עודכן → גיליון ברקע;
    לא נמצא (מסמך ישן שחי רק בגיליון) → Apps Script סינכרוני."""
    payload = {"doc_token": token}
    payload.update(fields)
    if _sbdb and _sbdb.enabled() and _sbdb.signdoc_update(token, fields):
        def _bg():
            try:
                _buyers_apps_post("updatesigndoc", payload)
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()
        return {"ok": True}
    return _buyers_apps_post("updatesigndoc", payload)


def _fetch_manual_buyers():
    c = _cache_get("buyers", _src_ttl(BUYERS_SOURCE, 60, 10))
    if c is not None:
        return c
    if BUYERS_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            rows = _sbdb.fetch_buyers_rows()
            if rows:
                _cache_put("buyers", rows)
            return rows
        except Exception as _sbe:
            log.error(f"supabase buyers read failed — falling back to sheets: {_sbe}")
    j = _buyers_apps_post("listbuyers", {})
    if not j or not j.get("ok"):
        return []
    rows = j.get("rows", []) or []
    _cache_put("buyers", rows)
    return rows

def _fmt_buyer_date(raw):
    """גוגל שיטס לפעמים ממיר את התאריך ל-ISO; מציג אותו יפה בשעון ישראל."""
    from datetime import datetime
    raw = str(raw or "").strip()
    if not raw:
        return ""
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        try:
            from zoneinfo import ZoneInfo
            if d.tzinfo:
                d = d.astimezone(ZoneInfo("Asia/Jerusalem"))
        except Exception:
            pass
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return raw

@app.route("/api/buyers/add", methods=["POST"])
def api_buyers_add():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    budget = (body.get("budget") or "").strip()
    summary = (body.get("summary") or "").strip()
    if not (name or phone or summary):
        return jsonify({"ok": False, "reason": "empty"}), 400
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    except Exception:
        now = datetime.now(timezone.utc) + timedelta(hours=3)
    # מנהל/מתאמת יכולים לשמור בשם סוכן אחר (as)
    eff_name, eff_phone = s.get("name", ""), _last9(s.get("phone", ""))
    if s["role"] in ("admin", "coordinator"):
        as_name = (body.get("as") or "").strip()
        # מתאמת — מותר לשייך רק לסוכנים שלה
        if as_name and s["role"] == "coordinator":
            cc = _coordinators_all().get(_last9(s.get("phone", "")))
            allowed = set()
            if cc:
                allowed |= set(_canon_key(n) for n in (cc.get("names") or set()))
                for ph in (cc.get("agents") or set()):
                    nm = web_phone_name_map().get(_last9(ph)) or web_contacts_phone_name().get(_last9(ph))
                    if nm: allowed.add(_canon_key(nm))
            if _canon_key(as_name) not in allowed:
                as_name = ""   # לא מהסוכנים שלה — מתעלמים ושומרים על שמה
        if as_name:
            eff_name = as_name
            ps = list(_phones_for_name(as_name))
            eff_phone = ps[0] if ps else ""
    # חסימת כפילות: אותו טלפון (או אותו שם אצל אותו סוכן) כבר קיים — אלא אם force
    if not body.get("force"):
        try:
            _ln = _last9(phone)
            _nk = _canon_key(name)
            _ek = _canon_key(eff_name)
            for _r in _fetch_manual_buyers():
                _same_phone = bool(_ln) and _last9(_r.get("phone", "")) == _ln
                _same_name = (not _ln) and bool(_nk) and _canon_key(_r.get("name", "")) == _nk \
                             and _canon_key(_r.get("agent", "")) == _ek
                if _same_phone or _same_name:
                    _own = (_r.get("agent", "") or "").strip()
                    # קונה של סוכן אחר — מוסיפים בשקט, בלי התראה (בקשת אייל 21/07).
                    # ההתראה נשארת רק על כפילות אצל אותו סוכן (הגנה מהוספה כפולה בטעות).
                    if _own and _canon_key(_own) != _ek:
                        continue
                    return jsonify({"ok": False, "dup": True,
                                    "reason": "הקונה כבר קיים אצלך",
                                    "agent": _own, "existing": (_r.get("name", "") or "").strip()})
        except Exception:
            pass
    payload = {
        "date": now.strftime("%d/%m/%Y %H:%M"),
        "name": name, "phone": phone, "budget": budget, "summary": summary,
        "agent": eff_name, "agent_phone": eff_phone,
    }
    j = _buyers_apps_post("addbuyer", payload)
    if not j or not j.get("ok"):
        return jsonify({"ok": False, "reason": (j or {}).get("error", "save_failed")}), 502
    _cache_clear("buyers")
    _log_activity(s["name"], s["role"], s["phone"], "הוספת קונה", name or phone)
    # התראת Push — קונה חדש ל"קונים שלי": לכל המנהלים (לא חוסם; שקט אם OneSignal לא מוגדר)
    try:
        _who = (name or phone or "לקוח חדש")
        _bd = "נוסף קונה חדש: " + _who + (" · 👤 " + eff_name if eff_name else "")
        # יעד: הסוכן שהקונה שויך אליו (לפי הטלפון שלו) + המנהלים
        _targets = list(_manager_push_ids())
        for _ph in _phones_for_name(eff_name):
            if _last9(_ph) and _last9(_ph) not in _targets: _targets.append(_last9(_ph))
        if _last9(eff_phone) and _last9(eff_phone) not in _targets: _targets.append(_last9(eff_phone))
        threading.Thread(target=send_push, args=("קונה חדש 🔔", _bd, _targets), daemon=True).start()
    except Exception:
        pass
    return jsonify({"ok": True})

@app.route("/api/push/test", methods=["GET", "POST"])
def api_push_test():
    """בדיקת התראת Push — למפתח בלבד. מאמת שכל הצינור (OneSignal) עובד."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    # אפשר לבדוק יעד ספציפי: /api/push/test?id=505709865 (ברירת מחדל: כל המנהלים)
    target = (request.args.get("id") or "").strip()
    ids = [_last9(target)] if target else _manager_push_ids()
    ok = send_push("בדיקת התראה 🔔", "Push עובד! התראת בדיקה מ-Family Bot", ids)
    return jsonify({"ok": ok, "configured": bool(ONESIGNAL_REST_KEY),
                    "targeted_ids": ids, "onesignal": _PUSH_LAST})

@app.route("/api/wa/test", methods=["GET", "POST"])
def api_wa_test():
    """בדיקת WhatsApp (Maytapi) — למפתח בלבד. /api/wa/test?to=0501234567"""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    to = (request.args.get("to") or s.get("phone", "")).strip()
    wa = _wa_phone(to)
    ok = send_text(wa, "בדיקת WhatsApp ✅ — Family Bot") if wa else False
    # אבחון התצורה (בלי לחשוף את הטוקן)
    cfg = {"phone_id": MAYTAPI_PHONE_ID, "product": MAYTAPI_PRODUCT,
           "token_set": bool(MAYTAPI_TOKEN), "base": MAYTAPI_BASE}
    return jsonify({"ok": ok, "to": wa, "config": cfg, "maytapi": _WA_LAST})

@app.route("/api/my/buyers", methods=["GET", "POST"])
def api_my_buyers():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    try:
        rows = _fetch_manual_buyers()
        as_name = ""
        if s["role"] in ("admin", "coordinator"):
            as_name = ((request.get_json(silent=True) or {}).get("as", "")
                       or request.args.get("as", "")).strip()
        if s["role"] == "admin" and not as_name:
            mine = rows; multi = True  # מנהל רואה את כל הקונים
        elif as_name:
            eff_name = as_name
            eff_phones = set(_phones_for_name(eff_name))
            keys, phones, multi = _scope_keys_phones("agent", eff_name, eff_phones)
            mine = [r for r in rows
                    if (_canon_key(r.get("agent", "")) in keys)
                    or (_last9(r.get("agent_phone", "")) in phones)]
        else:
            eff_name = s.get("name", "")
            eff_phones = set(_phones_for_name(eff_name))
            if s.get("phone"):
                eff_phones.add(_last9(s["phone"]))
            keys, phones, multi = _scope_keys_phones(
                s["role"], eff_name, eff_phones, s.get("agents"), s.get("agent_names"))
            mine = [r for r in rows
                    if (_canon_key(r.get("agent", "")) in keys)
                    or (_last9(r.get("agent_phone", "")) in phones)]
        mine.sort(key=lambda r: _excl_epoch(r.get("date", "")), reverse=True)
        out = []
        for r in mine:
            disp, tel = _il_phone(r.get("phone", ""))
            out.append({
                "name": str(r.get("name", "") or "").strip(),
                "phone": disp, "tel": tel, "wa": _wa_phone(r.get("phone", "")),
                "budget": str(r.get("budget", "") or "").strip(),
                "summary": str(r.get("summary", "") or "").strip(),
                "date": _fmt_buyer_date(r.get("date", "")),
                "agent": str(r.get("agent", "") or "").strip(),
                "row": r.get("row", ""),
                "search": str(r.get("search", "") or "").strip(),
            })
        return jsonify({"ok": True, "count": len(out), "multi": multi, "results": out})
    except Exception as e:
        log.error(f"my buyers error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

@app.route("/api/buyers/update", methods=["POST"])
def api_buyers_update():
    """שמירת חידוד החיפוש (עמודה 'חיפוש') לשורת קונה קיימת לפי מספר השורה."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    row = str(body.get("row", "")).strip()
    search = (body.get("search") or "").strip()
    if not row:
        return jsonify({"ok": False, "reason": "no_row"}), 400
    _up = {"row": row, "search": search}
    if (body.get("phone") or "").strip():   # עריכת טלפון הקונה (אם ה-Apps Script תומך בשדה)
        _up["phone"] = str(body.get("phone")).strip()
    if body.get("budget") is not None:      # עריכת תקציב הקונה (עמודה 'תקציב')
        _up["budget"] = str(body.get("budget")).strip()
    j = _buyers_apps_post("updatebuyer", _up)
    if not j or not j.get("ok"):
        return jsonify({"ok": False, "reason": (j or {}).get("error", "update_failed")}), 502
    _cache_clear("buyers")
    _log_activity(s["name"], s["role"], s["phone"], "עדכון חיפוש קונה", search[:60])
    return jsonify({"ok": True})

@app.route("/api/buyers/delete", methods=["POST"])
def api_buyers_delete():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    row = str(body.get("row", "")).strip()
    if not row:
        return jsonify({"ok": False, "reason": "no_row"}), 400
    j = _buyers_apps_post("deletebuyer", {"row": row})
    if not j or not j.get("ok"):
        return jsonify({"ok": False, "reason": (j or {}).get("error", "delete_failed")}), 502
    _cache_clear("buyers")
    _log_activity(s["name"], s["role"], s["phone"], "מחיקת קונה", row)
    return jsonify({"ok": True})

def _fetch_hidden_calls():
    c = _cache_get("hidden_calls", _src_ttl(CALLS_SOURCE, 180, 90))
    if c is not None: return c
    if CALLS_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            ids = _sbdb.fetch_hidden_call_ids()
            _cache_put("hidden_calls", ids)
            return ids
        except Exception as _sbe:
            log.error(f"supabase hidden calls read failed — falling back to sheets: {_sbe}")
    j = _buyers_apps_post("listhidden", {})
    ids = set(str(x) for x in (j.get("ids", []) if (j and j.get("ok")) else []))
    _cache_put("hidden_calls", ids)
    return ids

@app.route("/api/help", methods=["POST"])
def api_help():
    """דיווח תקלה / הצעת ייעול — נשלח במייל למנהל דרך Apps Script (MailApp)."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    kind = (body.get("kind") or "פנייה").strip()
    if not msg:
        return jsonify({"ok": False, "reason": "empty"}), 400
    to = os.environ.get("HELP_EMAIL", "eyalshmul@gmail.com")
    j = _buyers_apps_post("sendhelp", {"to": to, "kind": kind, "message": msg[:4000],
                                       "agent": s.get("name", ""), "phone": s.get("phone", "")})
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עזרה/הצעה", (kind + ": " + msg)[:120])
    _resp = (str(j)[:240] if j is not None else "None")
    return jsonify({"ok": bool(j and j.get("ok")), "resp": _resp})

@app.route("/api/sign/delete", methods=["POST"])
def api_sign_delete():
    """מחיקת הסכם מגיליון 'חתימות' — מפתח או מנהל בלבד. נמחק גם מהרשימה וגם מהדוחות (אותו מקור)."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if not (_is_dev(s.get("phone", "")) or s.get("role") == "admin"):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    eid = str(body.get("eid", "") or "").strip()
    received = str(body.get("received", "") or "").strip()
    client = str(body.get("client", "") or "").strip()
    if not (eid or (client and received)):
        return jsonify({"ok": False, "reason": "no_key"}), 400
    # מחיקה אופטימית (05/08): הסוכן לא מחכה ל-Apps Script (שנמדד 20-40ש' בהאטת גוגל) —
    # השורה יורדת מיד (גשר + מראה Supabase), והמקור בגיליון נמחק ברקע עם נסיונות חוזרים.
    _recent_sign_del_add(eid, received, client)
    _cache_clear("signings_sheet")
    _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "מחיקת הסכם", (client + " " + eid)[:80])
    def _del_bg():
        try:
            if _sbdb and _sbdb.enabled():
                _sbdb.signatures_delete(eid, received, client)   # ירידה מהמראה — הקריאות נקיות מיד
        except Exception:
            pass
        for _try in range(3):
            try:
                j = _buyers_apps_post("deletesigning",
                                      {"event_id": eid, "received_at": received, "client_name": client})
                if j and j.get("ok"):
                    break
            except Exception:
                pass
            time.sleep(25)
        _cache_clear("signings_sheet")
        _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
    threading.Thread(target=_del_bg, daemon=True).start()
    return jsonify({"ok": True, "deleted": 1})

@app.route("/api/calls/hide", methods=["POST"])
def api_calls_hide():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    eid = str((request.get_json(silent=True) or {}).get("id", "")).strip()
    if not eid: return jsonify({"ok": False, "reason": "no_id"}), 400
    j = _buyers_apps_post("hidecall", {"event_id": eid})
    if not j or not j.get("ok"): return jsonify({"ok": False, "reason": "fail"}), 502
    _cache_clear("hidden_calls")
    _log_activity(s["name"], s["role"], s["phone"], "הסתרת שיחה", eid)
    return jsonify({"ok": True})

@app.route("/api/calls/unhide", methods=["POST"])
def api_calls_unhide():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    eid = str((request.get_json(silent=True) or {}).get("id", "")).strip()
    if not eid: return jsonify({"ok": False, "reason": "no_id"}), 400
    j = _buyers_apps_post("unhidecall", {"event_id": eid})
    if not j or not j.get("ok"): return jsonify({"ok": False, "reason": "fail"}), 502
    _cache_clear("hidden_calls")
    return jsonify({"ok": True})

# ── (מצגת PDF ב-web הוסרה לבקשת המשתמש; פונקציות העזר נשארות לשימוש handler אחר) ──

# ── Frontend ───────────────────────────────────────────────────────────────────
# v1 נמחקה סופית (15/07/2026, אישור אייל) — /app נשאר כהפניה קבועה ל-/v2
# (אייקונים על מסך הבית של סוכנים עדיין מצביעים על /app; הטוקן ב-localStorage משותף).
@app.route("/app", methods=["GET"])
def family_bot_app():
    return redirect("/v2", code=302)

# ── מדיניות פרטיות (דרישת App Store — קישור ציבורי) ────────────────────────────
_PRIVACY_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>אפי — מדיניות פרטיות</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;800&display=swap" rel="stylesheet">
<style>body{margin:0;background:#F2EFE7}</style>
</head><body>
<div dir="rtl" style="max-width:760px; margin:0 auto; padding:56px 28px 80px; color:#1E3A5F; font-family:'Heebo',sans-serif; line-height:1.75;">

  <div style="display:flex; align-items:center; gap:14px; padding-bottom:22px; border-bottom:1px solid #DCD6C8; margin-bottom:30px;">
    <svg width="44" height="40" viewBox="0 0 118 106"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"></path><path d="M58 8L20 44h38z" fill="#C29435"></path><path d="M58 8l38 36H58z" fill="#EED9A0"></path><path d="M58 44L34 98h24z" fill="#D8AC4E"></path><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"></path><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"></circle></svg>
    <div style="display:flex; flex-direction:column; gap:2px;">
      <div style="font-size:26px; font-weight:800;">מדיניות פרטיות</div>
      <div style="font-size:14px; color:#8B8F99;">אפי · אפליקציה לניהול נדל״ן · עדכון אחרון: יולי 2026</div>
    </div>
  </div>

  

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">1. מי אנחנו</h2>
  <p style="margin:0; font-size:15.5px; color:#3D5273;">האפליקציה מופעלת על ידי פמילי נדל״ן והשקעות בע״מ, ח.פ. 515506293 ("אנחנו"), ומיועדת לסוכני ועובדי משרדי תיווך. ההצטרפות מתבצעת כיום בהזמנת מנהל המשרד; ככל שתתאפשר בעתיד הרשמה עצמאית של משרדים, יחולו עליה הוראות מדיניות זו.</p>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">2. איזה מידע אנחנו אוספים</h2>
  <ul style="margin:0; padding-right:22px; font-size:15.5px; color:#3D5273;">
    <li><b>פרטי משתמש:</b> שם, טלפון, כתובת מייל וחשבון Google (לצורך התחברות וסנכרון יומן).</li>
    <li><b>שיחות טלפון:</b> שיחות המתבצעות דרך המספר הווירטואלי של המשרד מוקלטות, מתומללות ומסוכמות באמצעות בינה מלאכותית — לצורך תיעוד לידים ושירות לקוחות.</li>
    <li><b>פרטי לקוחות ולידים:</b> שמות, מספרי טלפון, דרישות חיפוש והיסטוריית התקשרות שהוזנו על ידי המשתמשים.</li>
    <li><b>נכסים:</b> פרטי נכסים, כתובות ופרטי בעלי נכסים ממקורות פומביים ומהזנה ידנית.</li>
    <li><b>מסמכים חתומים:</b> הסכמי תיווך שנחתמו דיגיטלית.</li>
    <li><b>מיקום:</b> בעת שימוש במפה בלבד, ובאישורך — להצגת "המיקום שלי".</li>
    <li><b>נתוני שימוש:</b> פעולות באפליקציה (יומן פעילות פנימי למנהל המשרד).</li>
  </ul>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">3. הקלטת שיחות והסכמה</h2>
  <p style="margin:0; font-size:15.5px; color:#3D5273;">הקלטת ותמלול שיחות מתבצעים רק בקווי המשרד הייעודיים. באחריות המשרד ליידע את המתקשרים על ההקלטה בהתאם לדין החל. המשתמש באפליקציה מאשר זאת בעת ההצטרפות.</p>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">4. איך המידע משמש אותנו</h2>
  <ul style="margin:0; padding-right:22px; font-size:15.5px; color:#3D5273;">
    <li>ניהול לידים, קונים, נכסים, פגישות וחתימות של המשרד.</li>
    <li>הפקת סיכומי שיחות, התאמות נכסים ותקצירים באמצעות בינה מלאכותית.</li>
    <li>סנכרון פגישות עם יומן Google של המשתמש.</li>
    <li>דוחות פנימיים למנהל המשרד.</li>
  </ul>
  <p style="margin:8px 0 0; font-size:15.5px; color:#3D5273;"><b>אנחנו לא מוכרים מידע אישי ולא מעבירים אותו לגורמים שלישיים למטרות שיווק.</b></p>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">5. ספקי משנה</h2>
  <ul style="margin:0; padding-right:22px; font-size:15.5px; color:#3D5273;">
    <li><b>Supabase</b> — אחסון נתונים מאובטח (בסיס נתונים, קבצים, הרשאות).</li>
    <li><b>Google</b> — התחברות וסנכרון יומן (בכפוף למדיניות Google API Services).</li>
    <li><b>ספקי טלפוניה ותמלול</b> — הקלטה ותמלול שיחות בקווי המשרד.</li>
    <li><b>Anthropic (Claude)</b> — עיבוד סיכומים חכמים. התוכן אינו משמש לאימון מודלים.</li>
  </ul>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">6. אבטחה והפרדת נתונים</h2>
  <p style="margin:0; font-size:15.5px; color:#3D5273;">המידע מוצפן בתעבורה ובמנוחה. הרשאות מבוססות-תפקיד (סוכן / מתאמת / מנהל) והפרדה מלאה בין משרדים באמצעות Row Level Security. הגישה לנתוני המשרד מוגבלת לחברי אותו משרד בלבד.</p>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">7. שמירת מידע</h2>
  <p style="margin:0; font-size:15.5px; color:#3D5273;">המידע נשמר כל עוד חשבון המשרד פעיל, או עד לבקשת מחיקה. הקלטות שיחות נשמרות לתקופה מוגבלת הנדרשת לתפעול השוטף ולאחר מכן נמחקות.</p>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">8. הזכויות שלך ומחיקת חשבון</h2>
  <ul style="margin:0; padding-right:22px; font-size:15.5px; color:#3D5273;">
    <li>עיון, תיקון ומחיקה של מידע אישי — בפנייה אלינו או דרך מנהל המשרד.</li>
    <li><b>מחיקת חשבון:</b> בפנייה למנהל המשרד או אלינו בפרטי הקשר שבסעיף 9 — המחיקה תבוצע בתוך 30 יום. המחיקה מסירה את פרטי המשתמש והרשאותיו; נתוני המשרד העסקיים נשמרים באחריות המשרד.</li>
    <li>ניתוק סנכרון יומן Google — בכל עת מהגדרות החשבון.</li>
  </ul>

  <h2 style="font-size:19px; font-weight:800; margin:26px 0 8px;">9. יצירת קשר</h2>
  <p style="margin:0; font-size:15.5px; color:#3D5273;">לשאלות בנושא פרטיות: eyalshmul@gmail.com · 050-5709865 · יגאל בשן 2, קרית ביאליק. נשיב תוך 30 יום.</p>

  <div style="margin-top:36px; padding-top:18px; border-top:1px solid #DCD6C8; font-size:13px; color:#8B8F99;">
    מסמך זה עשוי להתעדכן מעת לעת; הודעה על שינוי מהותי תוצג באפליקציה.
  </div>
</div>
</body></html>'''

@app.route("/privacy", methods=["GET"])
def privacy_page():
    resp = Response(_PRIVACY_HTML, mimetype="text/html")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

# ── תנאי שימוש ופרטיות לחותמים (העמוד הציבורי /s/<token> מקשר לכאן) ─────────────
# נכתב בניסוח מקורי של אפי — לא העתקה של פלטפורמות אחרות.
_SIGN_TERMS_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>אפי — תנאי שימוש ופרטיות לחותמים</title>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;800&display=swap" rel="stylesheet">
<style>
body{margin:0;background:#F2EFE7;font-family:'Heebo',sans-serif;color:#1E3A5F;line-height:1.75}
.wrap{max-width:720px;margin:0 auto;padding:32px 20px 64px}
.brand{display:flex;align-items:center;gap:10px;margin-bottom:4px}
h1{font-weight:800;font-size:24px;margin:0}
.sub{color:#6B7280;font-size:14px;margin-bottom:24px}
h2{font-weight:600;font-size:17px;margin:26px 0 6px}
p,li{font-size:14.5px;margin:6px 0}
.card{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(30,58,95,.06);padding:24px 26px;margin-top:16px}
ol{padding-inline-start:20px}
a{color:#2E6BD6}
.ft{color:#6B7280;font-size:12px;text-align:center;margin-top:22px}
</style></head><body><div class="wrap">
<div class="brand">
<svg width="30" height="27" viewBox="0 0 118 106" aria-hidden="true"><path d="M58 8L20 44l14 54h48l14-54z" fill="#E4C56B"/><path d="M58 8L20 44h38z" fill="#C29435"/><path d="M58 8l38 36H58z" fill="#EED9A0"/><path d="M58 44L34 98h24z" fill="#D8AC4E"/><path d="M20 44l-14 8 14 6z" fill="#1E3A5F"/><circle cx="40" cy="34" r="4.2" fill="#1E3A5F"/></svg>
<h1>תנאי שימוש ופרטיות — חתימה דיגיטלית</h1>
</div>
<div class="sub">אפי (Effie) · עדכון אחרון: יולי 2026</div>
<div class="card">
<h2>1. מה העמוד הזה</h2>
<p>הגעת לכאן מקישור חתימה שנשלח אליך על-ידי משרד תיווך. אפי היא מערכת דיגיטלית המשמשת את המשרד לניהול, שליחה והחתמה של מסמכים. אפי היא כלי טכנולוגי בלבד: ההסכם עצמו נכרת בינך לבין משרד התיווך, ואפי אינה צד לו, אינה מנסחת אותו ואינה אחראית לתוכנו.</p>
<h2>2. החתימה שלך</h2>
<ol>
<li>חתימה בעמוד זה — לרבות הזנת תעודת זהות וחתימה על גבי המסך — מהווה חתימה מחייבת על ההסכם המוצג, כדין חתימה בכתב יד.</li>
<li>לפני החתימה באחריותך לקרוא את ההסכם במלואו. שאלות על תוכנו יש להפנות למתווך ששלח אותו.</li>
<li>חל איסור לשנות, להעתיק באופן מטעה, לשבש או לזייף מסמך שנשלח אליך. פעולות כאלה עלולות להוות עבירה על החוק.</li>
</ol>
<h2>3. תיעוד ואימות</h2>
<p>לצורך תוקף החתימה ואבטחת התהליך, המערכת מתעדת את מועד החתימה, פרטי הזיהוי שהוזנו, תמונת החתימה ונתוני גישה טכניים (כגון כתובת IP וסוג דפדפן). תיעוד זה נשמר כראיה לתקינות ההליך.</p>
<h2>4. פרטיות</h2>
<ol>
<li><b>מה נאסף:</b> שם, מספר זהות, טלפון, תמונת החתימה ונתוני הגישה הטכניים שלעיל — בלבד.</li>
<li><b>למה:</b> זיהויך, השלמת ההחתמה, ותיעוד ההליך עבור הצדדים להסכם.</li>
<li><b>למי מועבר:</b> למשרד התיווך שהזמין את ההחתמה. מעבר לכך לא מועבר מידע לגורם שלישי, אלא אם נדרש על פי דין.</li>
<li>העמוד משתמש באמצעים טכניים תפעוליים בלבד — אין עוגיות פרסום ואין מעקב שיווקי.</li>
</ol>
<h2>5. עותק ההסכם</h2>
<p>עם השלמת החתימה, ההסכם החתום נשמר אצל משרד התיווך, ובעמוד זה זמין כפתור "שמור / הדפס PDF". מומלץ לשמור עותק מיד. לקבלת עותק בשלב מאוחר יותר יש לפנות למשרד התיווך — המערכת אינה שירות ארכיון עבור החותם.</p>
<h2>6. הצגה חלקית של פרטי נכס</h2>
<p>ייתכן שחלק מפרטי הנכס (למשל כתובת מלאה) יוצגו באופן חלקי עד להשלמת החתימה, לפי שיקול דעת המתווך. האחריות להצגה זו היא של המתווך, ולא תעמוד לחותם טענה כלפי המערכת בגין כך.</p>
<h2>7. פניות והליכים משפטיים</h2>
<ol>
<li>כל פנייה הנוגעת להסכם — עותקים, בירורים או השגות — תופנה למשרד התיווך. המערכת אינה מעניקה ייעוץ משפטי.</li>
<li>המערכת אינה צד להסכם. צד שידרוש בכל זאת מנציגי המערכת מעורבות בהליך משפטי בין הצדדים — לרבות מתן עדות, מסירת תיעוד או היערכות לכך — יישא במלוא העלויות הכרוכות בכך, ובכלל זה השתתפות בסך 10,000 ₪ בתוספת מע"מ בגין זמן, היערכות וליווי מקצועי.</li>
</ol>
<h2>8. אחריות</h2>
<p>אחריות המערכת מוגבלת לתקינות הטכנית של תהליך החתימה. המערכת אינה אחראית לתוכן ההסכמים, לנכונות הנתונים שהוזנו על-ידי הצדדים, או לכל נזק שמקורו ביחסים שבין החותם לבין משרד התיווך.</p>
<h2>9. דין וסמכות שיפוט</h2>
<p>על השימוש בעמוד זה יחול דין מדינת ישראל. סמכות השיפוט הבלעדית נתונה לבתי המשפט המוסמכים במחוז חיפה.</p>
<h2>10. עדכון התנאים</h2>
<p>תנאים אלה עשויים להתעדכן מעת לעת; הנוסח המחייב הוא זה המפורסם בעמוד זה במועד החתימה.</p>
<h2>11. הסכמה</h2>
<p>סימון תיבת ההסכמה ולחיצה על "אשר וחתום" מהווים אישור שקראת, הבנת והסכמת לתנאים אלה.</p>
<p style="margin-top:14px">שאלות בנושא פרטיות: <a href="mailto:eyalshmul@gmail.com">eyalshmul@gmail.com</a></p>
</div>
<div class="ft">אפי · מערכת ניהול והחתמה דיגיטלית לנדל"ן</div>
</div></body></html>'''

@app.route("/sign-terms", methods=["GET"])
def sign_terms_page():
    resp = Response(_SIGN_TERMS_HTML, mimetype="text/html")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp

_APP_ICON_B64 = "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"
@app.route("/assets/icon", methods=["GET"])
def family_icon():
    import base64 as _b64
    resp = Response(_b64.b64decode(_APP_ICON_B64), mimetype="image/png")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp

@app.route("/assets/logo", methods=["GET"])
def family_logo():
    names = ["family-logo.png", "family-logo.webp", "family-logo.jpg", "family-logo.jpeg",
             "family-logo.png.jpg", "logo.png", "logo.jpg"]
    dirs = [Path(__file__).parent, Path("."), Path("/app")]
    for d in dirs:
        for n in names:
            p = d / n
            if p.exists():
                ext = p.suffix.lower()
                mt = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/webp" if ext == ".webp" else "image/png")
                resp = send_file(str(p), mimetype=mt, max_age=3600)
                resp.headers["Cache-Control"] = "public, max-age=3600"
                return resp
    return ("", 404)

# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND CACHE WARMER — מרענן ברקע את הקריאות הכבדות מ-Apps Script,
# כך שבקשות הסוכנים תמיד מקבלות תשובה מיידית מהמטמון (לא ממתינות בתור).
# עדכון אטומי בלבד (אף פעם לא מרוקן את המטמון תוך כדי). config-agnostic לשכפול.
# ══════════════════════════════════════════════════════════════════════════════
WARM_INTERVAL = int(os.environ.get("WARM_INTERVAL", "30") or 30)

def _key_age(key):
    with _TTL_LOCK:
        e = _TTL_CACHE.get(key)
    return (time.time() - e[0]) if e else 1e9

def _warm_key(key, ttl, fetch):
    """רענון-מקדים: מושך מחדש רק כשהמטמון יפוג לפני המחזור הבא של ה-warmer, כך
    שמשתמשים תמיד פוגעים במטמון חם — ואף מקור לא נקרא בתדירות גבוהה מה-TTL שלו."""
    if _key_age(key) < max(ttl - WARM_INTERVAL - 5, 1):
        return
    try:
        rows = fetch()
        if rows:   # תשובה ריקה = כמעט תמיד תקלה זמנית — לא מקבעים אותה במטמון
            _cache_put(key, rows)
    except Exception:
        pass

def _newborn_fetch_raw():
    if NEWBORN_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            return _sbdb.fetch_newborn_rows()
        except Exception as _sbe:
            log.error(f"warmer newborn supabase: {_sbe}")
    j = _buyers_apps_post("listnewborn", {})
    return (j.get("rows", []) or []) if (j and j.get("ok")) else []

def _props_fetch_raw():
    if PROPS_SOURCE == "supabase" and _sbdb and _sbdb.enabled():
        try:
            return _sbdb.fetch_properties_rows()
        except Exception as _sbe:
            log.error(f"warmer props supabase: {_sbe}")
    return _fetch_sheet_rows_raw()

def _warm_once():
    # המפתחות הכבדים — רענון-מקדים לפי דגל המקור (Supabase = שאילתה זולה; Sheets בקצב ה-TTL)
    _warm_key("raw:שיחות:01/01/2020:31/12/2099", _src_ttl(CALLS_SOURCE, 60, 90),
              lambda: _web_fetch_raw_uncached("שיחות"))
    _warm_key("raw:חתימות:01/01/2020:31/12/2099", _src_ttl(SIGNATURES_SOURCE, 60, 90),
              lambda: _web_fetch_raw_uncached("חתימות"))
    _warm_key("newborn_rows", _src_ttl(NEWBORN_SOURCE, 300, 90), _newborn_fetch_raw)
    _warm_key("sheet_rows", _src_ttl(PROPS_SOURCE, 60, 90), _props_fetch_raw)
    # אלה מנהלים מטמון בעצמם — קריאה דרך העטיפה עושה עבודה רק כשה-TTL פג,
    # וכך ברוב המקרים ה-warmer (ולא משתמש) משלם את המשיכה האיטית
    for _fn in (fetch_signings_from_sheet, _fetch_hidden_calls, fetch_external_exclusives, _load_config):
        try:
            _fn()
        except Exception:
            pass

_warmer_started = False
def _start_warmer():
    global _warmer_started
    if _warmer_started:
        return
    _warmer_started = True
    def _loop():
        time.sleep(3)
        while True:
            try:
                _warm_once()
            except Exception:
                pass
            time.sleep(WARM_INTERVAL)
    try:
        _threading.Thread(target=_loop, daemon=True, name="cache-warmer").start()
        log.info("Cache warmer started (interval %ss)" % WARM_INTERVAL)
    except Exception as _e:
        log.error("warmer start failed: %s" % _e)

# ה-warmer פעיל כברירת מחדל. הגרסה הישנה כובתה כי משכה הכל מ-Apps Script ללא מטמון
# כל 30ש' (מונופוליזציה שחנקה כתיבות); הנוכחית קוראת כל מקור לפי הדגל וה-TTL שלו —
# Supabase מתרענן בזול, Sheets לא נקרא תכוף יותר מהיום. לכיבוי: DISABLE_WARMER=1
if os.environ.get("DISABLE_WARMER", "") != "1":
    _start_warmer()

# ── פוש "נכס נולד 🐥" — גלאי שמזהה נכס חדש שנכנס למערכת ושולח לכל הסוכנים והמנהלים ──
def _all_agent_push_ids():
    """כל טלפוני הסוכנים (9 ספרות) + מנהלים — נכס נולד נשלח לכולם."""
    ids = set()
    try:
        for ph in (web_contacts_phone_name() or {}):   # last9 -> שם, מאנשי קשר
            l = _last9(ph)
            if l: ids.add(l)
        for ph in (web_phone_name_map() or {}):
            l = _last9(ph)
            if l: ids.add(l)
        for ag in (_load_config().get("agents") or []):
            for fld in ("phone", "vphone"):
                l = _last9(ag.get(fld, ""))
                if l: ids.add(l)
    except Exception:
        pass
    try: ids |= set(_manager_push_ids())
    except Exception: pass
    return [i for i in ids if i]

def _nb_push_targets():
    """פוש נכס נולד — רק למי שהמודעות פתוחות אצלו מיד (השהיה 0).
    מוסתר או מושהה (כולל מנהל מושהה) לא מקבל פוש על נכס שעוד לא נחשף לו."""
    delays = _fetch_newborn_delays()
    try:
        default = int(delays.get("_default", 0))
    except Exception:
        default = 0
    def _d_for(nm):
        if not nm:
            return default
        v = delays.get(_norm_name(nm), delays.get("c:" + _canon_key(nm), default))
        try:
            return int(v)
        except Exception:
            return default
    names_by_phone = {}
    for src_map in (web_contacts_phone_name(), web_phone_name_map()):
        for ph, nm in src_map.items():
            l = _last9(ph)
            if l and nm:
                names_by_phone.setdefault(l, nm)
    for ag in (_load_config().get("agents") or []):
        for fld in ("phone", "vphone"):
            l = _last9(ag.get(fld, ""))
            if l and ag.get("name"):
                names_by_phone.setdefault(l, ag["name"])
    ids = set(l for l, nm in names_by_phone.items() if _d_for(nm) == 0)
    try:
        ids |= set(_manager_push_ids())
    except Exception:
        pass
    for l in list(ids):
        nm = names_by_phone.get(l, "")
        if nm and _d_for(nm) != 0:
            ids.discard(l)
        elif _delayed_admin_days(nm, l):
            ids.discard(l)
    return [i for i in ids if i]

_seen_newborns = set()
_seen_newborns_seeded = False
_NB_SEEN_PATH = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(__file__), "newborn_seen.json")
_NB_PUSH_MAX_BURST = 15   # שסתום בטיחות: יותר מזה "חדשים" בבת אחת = אנומליה (איפוס מצב), לא מפציצים

def _nb_seen_load():
    """טעינת הסט מהדיסק (שורד restart/deploy — מונע הצפת פוש אחרי כל פריסה)."""
    global _seen_newborns, _seen_newborns_seeded
    try:
        with open(_NB_SEEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            _seen_newborns = set(str(x) for x in data)
            _seen_newborns_seeded = True
    except Exception:
        pass

def _nb_seen_save():
    try:
        with open(_NB_SEEN_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(_seen_newborns), f, ensure_ascii=False)
    except Exception:
        pass

def check_new_newborns():
    """מזהה נכס נולד חדש (diff מול הסט הקיים) ושולח פוש.
    הגנות מפני הצפה: (א) קריאה ריקה/כושלת לא זורעת ולא דוחפת; (ב) אם פתאום הרבה
    'חדשים' בבת אחת (איפוס מצב) — סופגים בשקט בלי פוש; (ג) הסט נשמר לדיסק לשרוד פריסות."""
    global _seen_newborns, _seen_newborns_seeded
    try:
        rows = fetch_newborn() or []
    except Exception:
        return
    keymap = {}
    for r in rows:
        if not _newborn_created_epoch(r):
            continue
        try: keymap[_nb_key(r)] = r
        except Exception: pass
    if not keymap:
        return   # קריאה ריקה/כושלת — לא לזרוע סט ריק (זה מה שגרם להצפת 300 פוש)
    if not _seen_newborns_seeded:
        _seen_newborns = set(keymap.keys())
        _seen_newborns_seeded = True
        _nb_seen_save()
        return
    new_keys = [k for k in keymap.keys() if k not in _seen_newborns]
    if len(new_keys) > _NB_PUSH_MAX_BURST:
        # אנומליה (מצב אופס/שינוי מפתחות) — מסמנים כמוכרים בלי לדחוף, כדי לא להפציץ
        _seen_newborns |= set(keymap.keys())
        _nb_seen_save()
        log.error(f"newborn push burst guard: {len(new_keys)} new at once — suppressed")
        return
    for k in new_keys:
        r = keymap[k]
        _addr = str(r.get("רחוב1", "") or r.get("רחוב", "") or "").strip()
        _city = str(r.get("עיר", "") or r.get("עיר / ישוב", "") or "").strip()
        label = (_addr + ((", " + _city) if _city else "")).strip(" ,") or "נכס חדש"
        try:
            threading.Thread(target=send_push,
                args=("נכס נולד 🐥", "נכס חדש נכנס למערכת: " + label, _nb_push_targets()),
                daemon=True).start()
        except Exception:
            pass
        _seen_newborns.add(k)
    if new_keys:
        _nb_seen_save()

def _newborn_push_loop():
    import time as _t
    _nb_seen_load()                    # טעינת הסט מהדיסק — אם קיים, לא זורעים מחדש (מונע הצפה אחרי deploy)
    _t.sleep(180)                      # השהיה ראשונית — לא להתחרות בטעינה הראשונה אחרי boot
    while True:
        try: check_new_newborns()
        except Exception: pass
        _t.sleep(600)                  # כל 10 דק' במקום 120ש' — עומס זניח על Apps Script
try:
    threading.Thread(target=_newborn_push_loop, daemon=True).start()
except Exception:
    pass

# ── וואטסאפ לסוכן על כל שיחה חדשה: תמלול + קישור להוסיף קונה ל"קונים שלי" ──────────
_seen_calls = set()
_seen_calls_seeded = False
_CALLS_SEEN_PATH = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(__file__), "calls_seen.json")
_CALLS_WA_MAX_BURST = 8   # שסתום בטיחות — פרץ גדול מדי = חסימת WhatsApp

def _calls_seen_load():
    global _seen_calls, _seen_calls_seeded
    try:
        with open(_CALLS_SEEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            _seen_calls = set(str(x) for x in data)
            _seen_calls_seeded = True
    except Exception:
        pass

def _calls_seen_save():
    try:
        with open(_CALLS_SEEN_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(_seen_calls)[-4000:], f, ensure_ascii=False)
    except Exception:
        pass

# קישורים מקוצרים להוספת קונה — וואטסאפ שובר URL ארוך, אז שומרים את המטען בצד
# ומנפיקים /l/<token> קצר שמפנה לקישור העמוק המלא. נשמר לדיסק הקבוע.
_AB_LINKS_PATH = os.path.join(os.environ.get("MAP_CACHE_DIR", "") or os.path.dirname(__file__), "ab_links.json")
_AB_LINKS = None

def _ab_links():
    global _AB_LINKS
    if _AB_LINKS is None:
        try:
            with open(_AB_LINKS_PATH, "r", encoding="utf-8") as f:
                _AB_LINKS = json.load(f)
            if not isinstance(_AB_LINKS, dict): _AB_LINKS = {}
        except Exception:
            _AB_LINKS = {}
    return _AB_LINKS

def _ab_link_make(payload_b64):
    m = _ab_links()
    tok = _hashlib.md5(payload_b64.encode("utf-8")).hexdigest()[:8]
    m[tok] = payload_b64
    if len(m) > 3000:   # שמירה על גודל סביר — מוחקים את הישנים
        for _k in list(m.keys())[:len(m) - 3000]:
            m.pop(_k, None)
    try:
        with open(_AB_LINKS_PATH, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
    except Exception:
        pass
    return tok

@app.route("/l/<tok>")
def ab_short_link(tok):
    """קישור מקוצר להוספת קונה: מנסה לפתוח את האפליקציה הנייטיבית (remaxfamily://),
    ואם אין — נופל לדפדפן. ?in=1 = ניווט מתוך האפליקציה עצמה (בלי ניסיון נייטיב)."""
    v = _ab_links().get(str(tok)[:16], "")
    if not v:
        return redirect("/app")
    target = "/app#ab=" + v
    if request.args.get("in"):
        return redirect(target)
    native = NATIVE_URL_SCHEME + "://ab?t=" + str(tok)[:16]
    return ("<!doctype html><html dir=rtl lang=he><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Family Bot</title></head>"
            "<body style='font-family:-apple-system,Arial,sans-serif;text-align:center;"
            "padding:56px 16px;background:#0D1B2A;color:#fff'>"
            "<div style='font-size:44px'>🏠</div>"
            "<div style='margin:12px 0 24px;font-weight:600'>פותח את Family Bot…</div>"
            "<a href='" + target + "' style='color:#E4B34A'>לחץ כאן אם לא נפתח אוטומטית</a>"
            "<script>var T='" + target + "';function go(){location.replace(T);}"
            "if(/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)){"
            "try{location.href='" + native + "';}catch(e){}setTimeout(go,1400);"
            "}else{go();}</script></body></html>")

def _wa_call_message(c):
    """בונה את הודעת הוואטסאפ לסוכן: תמלול/סיכום השיחה + קישור עמוק להוספת הקונה."""
    disp, tel = _il_phone(c.get("caller_phone", ""))
    raw = str(c.get("transcript_summary", "") or "")
    text = re.sub(r"https?://\S+", "", raw)
    text = re.sub(r"\*", "", text)
    text = re.sub(r"AI מתמלל ומסכם שיחות", "", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not re.sub(r"[\s.\-–—:·•]", "", re.sub(r"^\s*סיכום השיחה:?\s*", "", text)):
        text = ""
    st = str(c.get("status", "")).upper()
    st_he = "נענתה" if st == "ANSWER" else "לא נענתה"
    when = _fmt_il_dt(c.get("received_at", "")) or ""
    base = (os.environ.get("APP_BASE_URL") or "https://remax-bot.onrender.com").rstrip("/")
    import base64 as _b64c
    payload = json.dumps({"phone": (disp or tel or ""), "summary": text[:600]}, ensure_ascii=False)
    tok = _b64c.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    link = base + "/l/" + _ab_link_make(tok)   # קישור קצר — וואטסאפ שובר URL ארוך
    _ag = str(c.get("agent", "") or "").strip()
    lines = ["📞 *שיחה חדשה* — " + (disp or "מספר לא ידוע")]
    if _ag: lines.append("👤 " + _ag)
    if when: lines.append("🕐 " + when + " · " + st_he)
    lines.append("")
    lines.append("📝 " + (text if text else "אין סיכום לשיחה זו"))
    lines.append("")
    lines.append('➕ להוספת הקונה ל"קונים שלי":')
    lines.append(link)
    return "\n".join(lines)

def check_new_calls():
    """מזהה שיחה חדשה בגיליון 'שיחות' ושולח לסוכן וואטסאפ עם תמלול + קישור הוספת קונה.
    seed בריצה הראשונה + שמירה לדיסק + שסתום בטיחות — בדיוק כמו נכס נולד (מונע הצפה)."""
    global _seen_calls, _seen_calls_seeded
    try:
        rows = web_fetch_raw("שיחות") or []
    except Exception:
        return
    keymap = {}
    for r in rows:
        try:
            u = _call_uid(r)
        except Exception:
            u = ""
        if u: keymap[u] = r
    if not keymap:
        return
    if not _seen_calls_seeded:
        _seen_calls = set(keymap.keys())
        _seen_calls_seeded = True
        _calls_seen_save()
        return
    new_keys = [k for k in keymap.keys() if k not in _seen_calls]
    if len(new_keys) > _CALLS_WA_MAX_BURST:
        _seen_calls |= set(keymap.keys())
        _calls_seen_save()
        log.error(f"calls WA burst guard: {len(new_keys)} new at once — suppressed")
        return
    for k in new_keys:
        r = keymap[k]
        if not _wa_auto_on():   # מושהה — מסמנים כנצפה בלי לשלוח (אין הצפת עבר בהפעלה מחדש)
            _seen_calls.add(k)
            continue
        try:
            _cmsg = _wa_call_message(r)
            # לסוכן האישי — לפי *שם* הסוכן (כמו בחתימות): agent_phone בגיליון הוא
            # המספר הווירטואלי של המרכזיה, שאין לו וואטסאפ
            # יעד: הנייד האישי של הסוכן — לא המספר הווירטואלי (מרכזייה) שבשורת השיחה
            _vphone9 = _last9(r.get("agent_phone", ""))
            _agent_targets = set()
            for _p9 in _phones_for_name(str(r.get("agent", "") or "").strip()):
                _l = _last9(_p9)
                if _l and _l != _vphone9:
                    _agent_targets.add(_l)
            if not _agent_targets and _vphone9:   # אין נייד ידוע — ננסה את מה שיש
                _agent_targets.add(_vphone9)
            for _t9 in _agent_targets:
                _w = _wa_phone(_t9)
                if _w:
                    try: send_text(_w, _cmsg)
                    except Exception: pass
            if WA_GROUP_CALLS:
                send_text(WA_GROUP_CALLS, _cmsg)           # לקבוצת "שיחות" של המנהלים
        except Exception:
            pass
        _seen_calls.add(k)
    if new_keys:
        _calls_seen_save()

def _sync_signing_buyers():
    """כל חתימת מתעניין (קונים) ב-14 הימים האחרונים — נכנסת אוטומטית ל"קונים שלי",
    לא משנה מאיפה הגיעה (האפליקציה או השיטס). דדופ מובנה ב-_add_buyer_from_signing."""
    try:
        import datetime as _dt
        frm = (_dt.date.today() - _dt.timedelta(days=14)).strftime("%d/%m/%Y")
        to = _dt.date.today().strftime("%d/%m/%Y")
        for g in get_signings(frm, to):
            dt = str(g.get("deal_type", "") or "")
            if not (_deal_label(dt) == "קונים" or "מתעניין" in dt):
                continue
            ag = (g.get("agent", "") or "").strip()
            cl = (g.get("client_name", "") or "").strip()
            if not (ag and cl):
                continue
            addr = ", ".join([x for x in [g.get("address", ""), g.get("city", "")] if x])
            _add_buyer_from_signing(ag, cl, "", addr, "מהחתמת מתעניין")
    except Exception as _e:
        log.error(f"sync_signing_buyers: {_e}")

def _signing_buyers_loop():
    import time as _t
    _t.sleep(240)
    while True:
        try: _sync_signing_buyers()
        except Exception: pass
        _t.sleep(600)
try:
    threading.Thread(target=_signing_buyers_loop, daemon=True).start()
except Exception:
    pass

def _calls_wa_loop():
    import time as _t
    _calls_seen_load()
    _t.sleep(200)
    while True:
        try: check_new_calls()
        except Exception: pass
        _t.sleep(180)
try:
    threading.Thread(target=_calls_wa_loop, daemon=True).start()
except Exception:
    pass

# ── אֶפִי (/v2) — מודול נפרד; כשל כאן לא מפיל את האפליקציה הרצה ─────────────────
try:
    import effie_v2 as _effie_v2
    _effie_v2.register(app, globals())
except Exception as _effie_err:
    log.error(f"effie v2 init failed (old app unaffected): {_effie_err}")

# ══════════════════════════════════════════════════════════════════════════════
# WARMUP — חימום ה-caches הכבדים בעליית התהליך (deploy/restart מרוקן הכל)
# 05/08: המשתמש הראשון אחרי deploy ספג בנייה קרה — /api/report נמדד 78ש' (מול
# 0.3ש' חם) וחצה את תקרת ה-100ש' של Cloudflare → אריחי הבית הציגו אפסים.
# ══════════════════════════════════════════════════════════════════════════════
def _warmup_caches():
    for _wname, _wfn in (("sheet", fetch_sheet_rows),
                         ("calls", lambda: web_fetch_raw("שיחות")),
                         ("signatures", lambda: web_fetch_raw("חתימות"))):
        try:
            _t0 = time.time()
            _rows = _wfn()
            log.info(f"warmup {_wname}: {len(_rows or [])} rows in {time.time() - _t0:.1f}s")
        except Exception as _we:
            log.warning(f"warmup {_wname} failed: {_we}")

def _start_warmup():
    # WARMUP_ON_BOOT=0 מכבה (ברירת מחדל: פועל) — לסביבות בדיקה/סקריפטים
    if os.environ.get("WARMUP_ON_BOOT", "1") != "1":
        return
    threading.Thread(target=_warmup_caches, daemon=True, name="warmup").start()

_start_warmup()

# ══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    log.info("Installing dependencies...")
    install_deps()
    log.info(f"Bot starting — trigger word: '{TRIGGER_WORD}'")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
