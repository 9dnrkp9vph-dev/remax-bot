"""
שרת בוט וואטסאפ — מצגות נדל"ן אוטומטיות
RE/MAX Family | Railway.app deployment

זרימה:
1. סוכן שולח "מצגת" + טקסט + תמונות
2. השרת מפרסר עם Claude API
3. מייצר PDF
4. שולח חזרה בוואטסאפ דרך Maytapi
"""

import os, re, json, time, uuid, base64, tempfile, subprocess, logging, threading
from pathlib import Path
from io import BytesIO

import requests
from flask import Flask, request, jsonify

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Config from env vars ───────────────────────────────────────────────────────
MAYTAPI_TOKEN    = os.environ["MAYTAPI_TOKEN"]      # מהדאשבורד של maytapi
MAYTAPI_PHONE_ID = os.environ["MAYTAPI_PHONE_ID"]   # phone ID
MAYTAPI_PRODUCT  = os.environ["MAYTAPI_PRODUCT_ID"] # product ID
CLAUDE_API_KEY   = os.environ["CLAUDE_API_KEY"]
TRIGGER_WORD     = os.environ.get("TRIGGER_WORD", "מצגת")
GOOGLE_SHEETS_API_KEY  = os.environ.get("GOOGLE_SHEETS_API_KEY", "")
PROPERTIES_SHEET_ID    = os.environ.get("PROPERTIES_SHEET_ID", "1PnQm-ifyLrh6sBbNNQbNlAHmJWeBnbzXJJERmTuaAVM")
PROPERTIES_SHEET_NAME  = "נכסים"
CONTACTS_SHEET_NAME    = "אנשי קשר"
SEARCH_TRIGGERS        = ["מחפש דירה", "מחפשת דירה", "מחפש נכס", "מחפשת נכס"]

MAYTAPI_BASE = f"https://api.maytapi.com/api/{MAYTAPI_PRODUCT}/{MAYTAPI_PHONE_ID}"

# ── Temp dir for processing ────────────────────────────────────────────────────
WORK_DIR = Path(tempfile.gettempdir()) / "remax_bot"
WORK_DIR.mkdir(exist_ok=True)

# ── Active sessions: phone → {text, images, timer} ────────────────────────────
sessions = {}
SESSION_TIMEOUT = 45  # seconds to wait for more images

# ══════════════════════════════════════════════════════════════════════════════
# MAYTAPI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def maytapi_headers():
    return {"x-maytapi-key": MAYTAPI_TOKEN, "Content-Type": "application/json"}

def send_text(to: str, text: str):
    r = requests.post(f"{MAYTAPI_BASE}/sendMessage",
        headers=maytapi_headers(),
        json={"to_number": to, "type": "text", "message": text})
    log.info(f"send_text → {r.status_code}")

def download_profile_pic(phone: str, dest: Path) -> bool:
    """הורד תמונת פרופיל ושמור לקובץ — מנסה כמה endpoints"""
    try:
        number = phone.replace("+","").replace("-","").strip()
        number_at = f"{number}@c.us"

        # נסה endpoint 1: getProfilePic עם params
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
    """הורד מדיה מ-Maytapi"""
    try:
        # Maytapi media download requires auth token in header
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
    """שלח את הטקסט ל-Claude וקבל JSON מובנה"""
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
    # נקה backticks בכל פורמט
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = text.strip("`").strip()
    # מצא את ה-JSON בתוך הטקסט
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
    """בדוק אם יש לוגו RE/MAX בתמונה (אדום+כחול בפינות)"""
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(img_path).convert("RGB")
        arr = np.array(img)
        h, w = arr.shape[:2]
        # חפש פיקסלים אדומים אופייניים ל-RE/MAX (CC0033)
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
    """הסר לוגו מפינה (top-left נפוץ)"""
    from PIL import Image, ImageFilter, ImageDraw
    import numpy as np
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]
    # חתוך 340px מלמעלה (מיקום לוגו נפוץ)
    crop_top = int(h * 0.25)
    cropped = img.crop((0, crop_top, w, h))
    cropped.save(out_path, "JPEG", quality=93)

def add_remax_logo_to_image(img_path: Path, out_path: Path, logo_path: Path):
    """הוסף לוגו RE/MAX לפינה ימנית-תחתונה"""
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
    """חיפוש אמיתי על האזור דרך Claude עם web search"""
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

    # Claude עם web search מחזיר תוצאה אחרי כמה סבבים
    content = r.json().get("content", [])
    # קח את ה-text האחרון
    text = ""
    for block in reversed(content):
        if block.get("type") == "text":
            text = block["text"].strip()
            break

    text = re.sub(r"```json\s*|\s*```", "", text).strip()
    # מצא JSON במחרוזת
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try: return json.loads(match.group())
        except: pass
    return []

def get_transactions(city: str, neighborhood: str, rooms: str, address: str) -> list:
    """חיפוש עסקאות אמיתיות דרך Claude עם web search"""
    area = neighborhood or city
    # חלץ שם רחוב בלבד מהכתובת
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

    # ── Fonts ──────────────────────────────────────────────────────────────────
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

    # ── Colors ─────────────────────────────────────────────────────────────────
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

    # ── PAGE 1: COVER ──────────────────────────────────────────────────────────
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

    # ── PAGE 2: GALLERY ────────────────────────────────────────────────────────
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
        # כיתובים יוצגו לפי סדר התמונות שנשלחו
        # כיתובים מהמלל המקורי אם זמין, אחרת גנרי
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

    # ── PAGE 3: DETAILS + TEXT ─────────────────────────────────────────────────
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

    # ── PAGE 4: AREA INFO ──────────────────────────────────────────────────────
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

    # ── PAGE 5: TRANSACTIONS ───────────────────────────────────────────────────
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
            # חשב ממוצעים מהעסקאות
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
                shekel = "\u20aa"
                summary_rows = [
                    (f"טווח מחירים — {rooms_str} חד' באזור:", f"{mn:,} – {mx:,} {shekel}"),
                    ('מחיר ממוצע למ"ר:', f"~{avg_ppm:,} {shekel}" if avg_ppm else "—"),
                    ("מחיר השיווק:", f"{price_display}  \u2190 השווה לשוק"),
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

    # ── PAGE 6: CONTACT ────────────────────────────────────────────────────────
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

    # תמונת פרופיל של הסוכן
    profile_pic_path = data.get("_profile_pic")
    profile_pic_img = None
    if profile_pic_path and os.path.exists(profile_pic_path):
        try:
            from PIL import Image as PILImg
            pic = PILImg.open(profile_pic_path).convert("RGB")
            # חתוך לעיגול — שמור כ-JPG מרובע
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

    # ── Render ─────────────────────────────────────────────────────────────────
    out_path = session_dir / "presentation.pdf"
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=14*mm, bottomMargin=12*mm)
    doc.build(story, onFirstPage=page_cb, onLaterPages=page_cb)
    return out_path


# VERSION: v12-fixed
# ══════════════════════════════════════════════════════════════════════════════
# SESSION PROCESSOR
# ══════════════════════════════════════════════════════════════════════════════

def process_session(phone: str):
    """מעבד את הסשן — פירסור + PDF + שליחה"""
    session = sessions.pop(phone, None)
    if not session:
        return

    send_text(phone, "⏳ מכין את המצגת... כולל חיפוש עסקאות ומידע על השכונה.\nאנא המתן כ-90 שניות 🏠")

    session_dir = WORK_DIR / str(uuid.uuid4())
    session_dir.mkdir(exist_ok=True)

    try:
        # 1. פרסר טקסט
        log.info(f"Parsing text for {phone}")
        data = parse_listing_text(session["text"])
        if not data:
            send_text(phone, "❌ לא הצלחתי לפרסר את פרטי הנכס. נסה שוב.")
            return

        # 2. עבד תמונות
        processed_images = []
        # מצא את קובץ הלוגו
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

            # בדוק אם יש לוגו RE/MAX — אל תמחק!
            if has_remax_logo(img_path):
                processed_images.append(img_path)
                log.info(f"Image {i}: RE/MAX logo found — keeping as-is")
            else:
                # הוסף לוגו אם יש קובץ לוגו
                if logo_path and logo_path.exists():
                    out_img = session_dir / f"img_{i}_logo.jpg"
                    add_remax_logo_to_image(img_path, out_img, logo_path)
                    processed_images.append(out_img)
                    log.info(f"Image {i}: added RE/MAX logo")
                else:
                    processed_images.append(img_path)
                    log.info(f"Image {i}: no logo file available")

        # 3. חפש אזור ועסקאות במקביל לעיבוד תמונות
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

        import time
        with ThreadPoolExecutor(max_workers=1) as executor:
            f3 = executor.submit(fetch_pic)
        fetch_area()
        time.sleep(5)
        fetch_trans()
        try: f3.result(timeout=15)
        except: pass

        data["_area_info"]    = area_result[0] if isinstance(area_result[0], list) else []
        data["_transactions"] = trans_result[0] if isinstance(trans_result[0], list) else []

        # 4. צור PDF
        log.info(f"Generating PDF for {phone}")
        pdf_path = generate_pdf(data, processed_images, session_dir)

        # 4. שלח
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
        # נקה קבצים זמניים
        import shutil
        try: shutil.rmtree(session_dir)
        except: pass

def schedule_processing(phone: str):
    """המתן SESSION_TIMEOUT שניות ואז עבד"""
    if phone in sessions and sessions[phone].get("timer"):
        sessions[phone]["timer"].cancel()
    timer = threading.Timer(SESSION_TIMEOUT, process_session, args=[phone])
    timer.daemon = True
    timer.start()
    if phone in sessions:
        sessions[phone]["timer"] = timer

# ══════════════════════════════════════════════════════════════════════════════
# SEARCH BOT — מציאת לקוחות תואמים
# ══════════════════════════════════════════════════════════════════════════════

def parse_search_query(text: str) -> dict:
    """שלח את בקשת החיפוש ל-Claude וקבל JSON עם פילטרים לחיפוש נכסים"""
    prompt = f"""אתה עוזר לסוכן נדל"ן ברימקס שמחפש נכסים במאגר המשרד עבור לקוח.
הסוכן שלח לך הודעה עם דרישות הלקוח. חלץ פרמטרים ל-JSON בלבד (ללא markdown, ללא backticks).

נרמול ערים — הערים האפשריות:
- "מוצקין" / "קרית מוצקין" / "קריית מוצקין" → city = "קרית מוצקין"
- "ביאליק" / "קרית ביאליק" → city = "קרית ביאליק"
- "אתא" / "קרית אתא" → city = "קרית אתא"
- "ים" / "קרית ים" → city = "קרית ים"
- "חיים" / "קרית חיים" → city = "חיפה" (קרית חיים היא שכונה בחיפה)
- "חיפה" → city = "חיפה"

נרמול שכונות:
- "ותיקה" / "מוצקין הותיקה" → neighborhood = "ותיק"
- "אפק" → neighborhood = "אפק"
- "סביונים" / "סביוני ים" → neighborhood = "סביונ"
- "גבעת טל" → neighborhood = "גבעת טל"
- "קרית חיים מערבית" / "מערבית" → neighborhood = "מערבית"

חוקי זיהוי must_have — חשוב מאוד!
- "דירת גן" / "עם גינה" / "עם חצר" → must_have כולל "גינה", property_type = "דירת גן"
- "עם חנייה" / "חנייה פרטית" → must_have כולל "חנייה"
- "עם מעלית" → must_have כולל "מעלית"
- "עם ממ"ד" → must_have כולל "ממ\"ד"
- "עם מרפסת" → must_have כולל "מרפסת"
- "קרקע" / "קומת קרקע" → must_have כולל "גינה", property_type = "דירת גן"

חוקי property_type — חשוב מאוד!
- "דירת גן" → property_type = "דירת גן" (לא "דירה"! לא פנטהאוז!)
- "פנטהאוז" / "גג" / "קומה עליונה" → property_type = "פנטהאוז"
- "קוטג'" / "דו משפחתי" / "בית פרטי" → property_type = "קוטג'"
- "וילה" → property_type = "וילה"
- "דופלקס" → property_type = "דופלקס"
- דירה רגילה ללא ציון מיוחד → property_type = "דירה"

שדות JSON:
- city: עיר (אחת מהערים למעלה או null)
- neighborhood: שכונה (substring לחיפוש, או null)
- street: שם רחוב (אם הסוכן ציין, או null)
- rooms_min: מספר חדרים מינימלי (מספר עשרוני, או null)
- rooms_max: מספר חדרים מקסימלי (מספר עשרוני, או null) - "4 חדרים" → min=max=4
- budget_min: מחיר מינימלי בש"ח (מספר, או null)
- budget_max: מחיר מקסימלי בש"ח (מספר, או null) - "עד 2 מיליון" → 2000000
- size_min: מ"ר מינימלי (מספר, או null)
- size_max: מ"ר מקסימלי (מספר, או null)
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
- "מחפש דירה 4 חדרים בקרית מוצקין עד 2 מיליון" →
  city="קרית מוצקין", rooms_min=4, rooms_max=4, budget_max=2000000,
  property_type="דירה", must_have=[]

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
        return json.loads(text_out)
    except Exception as e:
        log.error(f"Search JSON parse error: {e}")
        return {}


# Cache למספרי טלפון של סוכנים (כדי לא לקרוא בכל פעם)
_agents_cache = {"data": None, "ts": 0}

def fetch_agents_phones() -> dict:
    """קרא את הטאב 'אנשי קשר' והחזר מילון: {שם סוכן: טלפון}"""
    import time
    # cache ל-5 דקות
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


def fetch_sheet_rows() -> list:
    """קרא את כל הנכסים מהגיליון"""
    if not GOOGLE_SHEETS_API_KEY:
        log.error("GOOGLE_SHEETS_API_KEY not set!")
        return []

    from urllib.parse import quote
    sheet_encoded = quote(PROPERTIES_SHEET_NAME)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{sheet_encoded}!A1:Z?key={GOOGLE_SHEETS_API_KEY}"
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
            rows.append(dict(zip(headers_row, row_padded)))
        return rows
    except Exception as e:
        log.error(f"Fetch sheet error: {e}")
        return []


def normalize_city(city: str) -> str:
    if not city:
        return ""
    c = city.strip().replace("קריית", "קרית")
    return re.sub(r"\s+", " ", c)



def parse_price(s: str) -> int:
    """המר מחיר משפת אנוש למספר. '₪ 2,590,000' → 2590000"""
    if not s:
        return 0
    digits = re.sub(r"[^\d]", "", str(s))
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0


def score_match(row: dict, query: dict, flex_level: int = 0) -> int:
    """דרג נכס - 0=לא רלוונטי, 100=מושלם"""
    score = 0

    # ── סוג עסקה - חובה להתאים ──
    deal_type = (row.get("סוג עסקה", "") or "").strip()
    want_deal = query.get("deal_type", "מכירה") or "מכירה"
    if deal_type and deal_type != want_deal:
        return 0

    # ── עיר - חובה ──
    q_city = normalize_city(query.get("city", "") or "")
    r_city = normalize_city(row.get("עיר / ישוב", "") or "")
    if q_city:
        if r_city == q_city:
            score += 30
        elif r_city and (r_city in q_city or q_city in r_city):
            score += 18
        else:
            return 0
    else:
        score += 5

    # ── שכונה - בונוס ──
    q_neigh = (query.get("neighborhood") or "").strip()
    r_neigh = (row.get("שכונה", "") or "").strip()
    if q_neigh and r_neigh:
        if q_neigh in r_neigh or r_neigh in q_neigh:
            score += 20

    # ── רחוב - בונוס גדול ──
    q_street = (query.get("street") or "").strip()
    r_street = (row.get("כתובת", "") or "").strip()
    if q_street and r_street:
        if q_street in r_street or r_street in q_street:
            score += 25

    # ── מחיר - חובה להיות בטווח ──
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
        if diff_pct < 0.05:
            score += 25
        elif diff_pct < 0.10:
            score += 20
        elif diff_pct < 0.20:
            score += 15
        else:
            score += 8

    # ── חדרים ──
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
        if in_range:
            if q_rmin and q_rmax and q_rmin == q_rmax and r_rooms == q_rmin:
                score += 20
            else:
                score += 12
        elif flex_level == 0:
            return 0

    # ── מ"ר ──
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

    # ── סוג נכס — בונוס/קנס ──
    q_ptype = (query.get("property_type") or "").strip()
    r_ptype = (row.get("סוג נכס", "") or "").strip()
    if q_ptype and r_ptype:
        if q_ptype == r_ptype:
            score += 15
        elif q_ptype in r_ptype or r_ptype in q_ptype:
            score += 7
        else:
            # סוג נכס שונה לגמרי — סנן ב-flex=0, קנס ב-flex=1
            if flex_level == 0:
                return 0
            elif flex_level == 1:
                score -= 15

    # ── תכונות חובה (must_have) — מחמיר! ──
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
        for feature in must_have:
            feature_clean = feature.strip()

            # גינה — מחפש בעמודת "סוג נכס" שמכיל "גן"
            if feature_clean == "גינה":
                prop_type_val = (row.get("סוג נכס", "") or "").strip()
                has_feature = "גן" in prop_type_val or "גינה" in prop_type_val or "קרקע" in prop_type_val
            else:
                col = col_map.get(feature_clean, feature_clean)
                val = (row.get(col, "") or "").strip()
                has_feature = val and val not in ("ללא", "לא", "", "0", "אין")

            if has_feature:
                score += 10
            else:
                missing_features += 1
                if flex_level <= 1:
                    return 0   # חובה ב-flex=0 וגם flex=1
                score -= 15

        # אם חסרות כל התכונות גם ב-flex=2 — אל תחזיר
        if flex_level == 2 and missing_features == len(must_have):
            return 0

    return max(0, score)
def search_listings_in_sheet(query: dict) -> list:
    rows = fetch_sheet_rows()
    if not rows:
        return []

    q_ptype = (query.get("property_type") or "").strip()
    is_garden = q_ptype == "דירת גן"

    # ── שלב 1: חפש בדיוק את סוג הנכס המבוקש ──
    for flex in [0, 1, 2]:
        scored = []
        for row in rows:
            s = score_match(row, query, flex_level=flex)
            if s > 0:
                scored.append((s, row, flex))
        scored.sort(key=lambda x: -x[0])
        if len(scored) >= 3 or flex == 2:
            results = [(s, r, f) for (s, r, f) in scored[:5]]
            # ── שלב 2: אם חיפשו דירת גן ואין תוצאות — הוסף קוטג' ──
            if is_garden and len(results) < 3:
                fallback_query = dict(query)
                fallback_query["property_type"] = "קוטג'"
                for flex2 in [0, 1, 2]:
                    fallback_scored = []
                    for row in rows:
                        s = score_match(row, fallback_query, flex_level=flex2)
                        if s > 0:
                            fallback_scored.append((s, row, flex2))
                    fallback_scored.sort(key=lambda x: -x[0])
                    if fallback_scored:
                        # הוסף עד 3 קוטג'ים כהשלמה
                        results += [(s, r, f) for (s, r, f) in fallback_scored[:3]]
                        break
            return results
    return []



def format_match_reply(query: dict, matches: list) -> str:
    """בנה הודעת WhatsApp עם נכסים תואמים"""
    if not matches:
        return ("\U0001f50d חיפשתי במאגר הנכסים ולא מצאתי נכס מתאים כרגע.\n\n"
                "טיפים:\n"
                "\u2022 נסה לציין רק עיר ומספר חדרים\n"
                "\u2022 הרחב את טווח התקציב\n"
                "\u2022 דוגמה: \"מחפש דירה 4 חדרים בקרית ביאליק עד 2 מיליון\"")

    summary = query.get("summary_he", "")
    lines = [f"\U0001f3e0 *מצאתי {len(matches)} נכסים מתאימים!*"]
    if summary:
        lines.append(f"_{summary}_")
    lines.append("")

    for i, (score, row, flex) in enumerate(matches, 1):
        city      = (row.get("עיר / ישוב", "") or "").strip()
        neigh     = (row.get("שכונה", "") or "").strip()
        street    = (row.get("כתובת", "") or "").strip()
        number    = (row.get("מספר בית", "") or "").strip()
        rooms     = (row.get("חדרים", "") or "").strip()
        size      = (row.get('מ"ר', "") or row.get("מ\u05f4ר", "") or "").strip()
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
        if (row.get("מ\u05f4ד", "") or "").strip() == "כן": features.append('ממ"ד')
        if features:
            lines.append(f"   \u2728 {' \u2022 '.join(features)}")

        if agent_name:
            lines.append(f"   \U0001f464 סוכן: *{agent_name}*")

        # חפש את הטלפון האמיתי של הסוכן מהטאב "אנשי קשר"
        agents_phones = fetch_agents_phones()
        real_phone = agents_phones.get(agent_name, agent_phone)

        if real_phone:
            wa_clean = re.sub(r"[^\d]", "", real_phone)
            if wa_clean and not wa_clean.startswith("972"):
                wa_clean = "972" + wa_clean.lstrip("0")
            lines.append(f"   \U0001f4f2 https://wa.me/{wa_clean}")

        lines.append("")

    lines.append("\u2501" * 9)
    lines.append("\U0001f4a1 לחץ על קישור ה-WhatsApp לקבלת פרטים מהסוכן")
    return "\n".join(lines)
def log_bot_query(sender_phone: str, query_text: str, parsed: dict, matches: list):
    if not GOOGLE_SHEETS_API_KEY:
        return
    try:
        from datetime import datetime
        now = datetime.now()
        row = [
            now.strftime("%Y-%m-%d %H:%M:%S"),
            sender_phone, "",
            query_text[:200],
            parsed.get("city", "") or "",
            str(parsed.get("rooms_max", "") or ""),
            str(parsed.get("budget_max", "") or ""),
            str(len(matches)),
            str(matches[0][0]) if matches else "0",
            (matches[0][1].get("Agent_Name", "") if matches else ""),
            (matches[0][1].get("Client_FirstName", "") if matches else ""),
        ]
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
               f"/values/{BOT_QUERIES_SHEET}!A1:append"
               f"?valueInputOption=USER_ENTERED&key={GOOGLE_SHEETS_API_KEY}")
        requests.post(url, json={"values": [row]}, timeout=10)
    except Exception as e:
        log.warning(f"Log bot query failed: {e}")


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
        # log_bot_query(sender_phone, message_text, parsed, matches)
    except Exception as e:
        log.error(f"Search handler error: {e}", exc_info=True)
        send_text(sender_phone, f"❌ שגיאה: {str(e)[:100]}")


def is_search_query(text: str) -> bool:
    """זהה אם ההודעה היא בקשת חיפוש - חייב להתחיל בצמד מילים: מחפש/ת + דירה/דירת"""
    if not text:
        return False
    t = text.strip()
    # הסר "אני " מההתחלה אם יש
    if t.startswith("אני "):
        t = t[4:].strip()
    # חייב להתחיל בדיוק ב: מחפש/מחפשת + רווח + דירה/דירת
    import re
    pattern = r'^מחפש[ת]?\s+דיר[הת]\b'
    return bool(re.match(pattern, t))


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # Maytapi sends GET to verify the webhook URL
    if request.method == "GET":
        return jsonify({"status": "ok", "message": "RE/MAX Bot Webhook Active"}), 200
    try:
        body = request.get_json(force=True)
        log.info(f"Webhook: {json.dumps(body)[:300]}")

        msg  = body.get("message", {})
        from_number = (body.get("conversation", "")
                       or msg.get("from_number", "")
                       or body.get("from", ""))
        if not from_number:
            return jsonify({"ok": True})

        msg_type = msg.get("type", "")
        text     = msg.get("text", "") or msg.get("caption", "") or ""
        media    = msg.get("url", "") or msg.get("media_url", "")

        # ── טריגר חיפוש — "אני מחפש" / "אני מחפשת" ───────────────────
        if msg_type == "text" and is_search_query(text):
            threading.Thread(
                target=handle_search_request,
                args=[from_number, text],
                daemon=True
            ).start()
            return jsonify({"ok": True})

        # ── טריגר: הודעת טקסט עם מילת הקוד ────────────────────────────────
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

        # ── תמונה בתוך סשן פעיל ──────────────────────────────────────────────
        if from_number in sessions and msg_type in ("image", "media"):
            sessions[from_number]["images"].append({
                "url": media,
                "data": msg.get("data"),
            })
            count = len(sessions[from_number]["images"])
            send_text(from_number, f"📸 קיבלתי תמונה {count}/4")
            # אם יש כבר 4 — עבד מיד
            if count >= 4:
                threading.Thread(target=process_session, args=[from_number], daemon=True).start()
            else:
                schedule_processing(from_number)
            return jsonify({"ok": True})

        # ── טקסט נוסף בתוך סשן (פרטים נוספים) ──────────────────────────────
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
# STARTUP
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("Installing dependencies...")
    install_deps()
    log.info(f"Bot starting — trigger word: '{TRIGGER_WORD}'")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
