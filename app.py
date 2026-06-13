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
from flask import Flask, request, jsonify
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
- "קרקע" / "קומת קרקע" → must_have כולל "גינה", property_type = "דירת גן"
חוקי property_type — חשוב מאוד!
- "דירת גן" → property_type = "דירת גן" (לא "דירה"! לא פנטהאוז!)
- "פנטהאוז" / "גג" / "קומה עליונה" → property_type = "פנטהאוז"
- "קוטג'" / "דו משפחתי" / "בית פרטי" → property_type = "קוטג'"
- "וילה" → property_type = "וילה"
- "דופלקס" → property_type = "דופלקס"
- דירה רגילה ללא ציון מיוחד → property_type = "דירה"
שדות JSON:
- city: עיר ראשית (אחת מהערים למעלה או null) — אם ציינו עיר אחת
- cities: רשימת ערים (אם ציינו יותר מעיר אחת, למשל ["קרית מוצקין","קרית ביאליק"]) — אחרת null
- neighborhood: שכונה (substring לחיפוש, או null)
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
    """מפה: שם סוכן (מנורמל) -> טלפון וירטואלי (עמודה C ב'אנשי קשר')."""
    if _vphone_cache["data"] is not None and (time.time() - _vphone_cache["ts"]) < 300:
        return _vphone_cache["data"]
    if not GOOGLE_SHEETS_API_KEY:
        return {}
    from urllib.parse import quote
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{PROPERTIES_SHEET_ID}/values/{quote(CONTACTS_SHEET_NAME)}!A1:C200?key={GOOGLE_SHEETS_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return {}
        out = {}
        for row in r.json().get("values", []):
            if len(row) < 3:
                continue
            name = (row[0] or "").strip()
            vp = _fmt_vphone((row[2] or "").strip())
            if name and vp and name not in ("שם מלא", "משרד", "משרד ביאליק", "טלפון וירטואלי"):
                out[_norm_name(name)] = vp
        _vphone_cache["data"] = out
        _vphone_cache["ts"] = time.time()
        return out
    except Exception as e:
        log.error(f"vphone fetch error: {e}")
        return {}

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
    c = _cache_get('sheet_rows', 60)
    if c is not None:
        return c
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
            rows.append(dict(zip(headers_row, row_padded)))
        EXCLUDED_AGENTS = {"אווה אזולאי"}
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
    c = _cache_get("signings_sheet", 60)
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
            })
        _cache_put("signings_sheet", out)
        return out
    except Exception as e:
        log.error(f"signings sheet error: {e}")
        return []
def get_signings(frm="01/01/2020", to="31/12/2099"):
    """חתימות לתקופה. אם יש טאב מלא (ייצוא מהקרם) — הוא הבסיס המדויק, ומוסיפים מהמקור
    האוטומטי (Apps Script) רק חתימות חדשות יותר מההדבקה האחרונה, כך שהדוח תמיד עדכני
    גם בלי הדבקה ידנית כל יום. אם אין טאב מלא — נופלים חזרה למקור האוטומטי בלבד."""
    manual = fetch_signings_from_sheet()
    if manual:
        max_e = max((_excl_epoch(g.get("received_at", "")) for g in manual), default=0)
        try:
            auto = web_fetch_raw("חתימות")
        except Exception:
            auto = []
        extra = [g for g in auto if _excl_epoch(g.get("received_at", "")) > max_e]
        allsig = manual + extra
    else:
        allsig = web_fetch_raw("חתימות", frm, to)
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
                if flex_level == 0:
                    return 0
                elif flex_level == 1 and r_floor > floor_max + 1:
                    return 0
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
        if not matched_city:
            return 0
    else:
        score += 5
    # ── שכונה — חובה ב-flex 0 ו-1, בונוס/קנס ב-flex 2 ──
    q_neigh = (query.get("neighborhood") or "").strip()
    r_neigh = (row.get("שכונה", "") or "").strip()
    if q_neigh:
        if r_neigh and (q_neigh in r_neigh or r_neigh in q_neigh):
            score += 30
        else:
            if flex_level <= 1:
                return 0
            score -= 15
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
        if diff_pct < 0.05:
            score += 25
        elif diff_pct < 0.10:
            score += 20
        elif diff_pct < 0.20:
            score += 15
        else:
            score += 8
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
    if q_ptype and r_ptype:
        if q_ptype == r_ptype:
            score += 15
        elif q_ptype in r_ptype or r_ptype in q_ptype:
            score += 7
        else:
            if q_ptype == "דירה" and r_ptype in PENTHOUSE_TYPES:
                return 0
            if flex_level == 0:
                return 0
            elif flex_level == 1:
                score -= 15
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
                    return 0
                score -= 15
        if flex_level == 2 and missing_features == len(must_have):
            return 0
    return max(0, score)
def search_listings_in_sheet(query: dict) -> list:
    rows = fetch_sheet_rows()
    if not rows:
        return []
    q_ptype = (query.get("property_type") or "").strip()
    is_garden = q_ptype == "דירת גן"
    for flex in [0, 1, 2]:
        scored = []
        for row in rows:
            s = score_match(row, query, flex_level=flex)
            if s > 0:
                scored.append((s, row, flex))
        scored.sort(key=lambda x: -x[0])
        if len(scored) >= 3 or flex == 2:
            results = [(s, r, f) for (s, r, f) in scored[:10]]
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
                        results += [(s, r, f) for (s, r, f) in fallback_scored[:3]]
                        break
            return results
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
    from datetime import datetime
    try:
        d = datetime.fromisoformat(str(s).replace("Z","+00:00"))
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
    if _external_excl_cache["data"] is not None and (time.time() - _external_excl_cache["ts"]) < 60:
        return _external_excl_cache["data"]
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
- city: עיר מנורמלת לפי הרשימה למעלה, או null
- neighborhood: שכונה מנורמלת לפי הרשימה למעלה (substring לחיפוש), או null
- rooms: מספר חדרים (מספר עשרוני) או null
- budget_max: תקציב מקסימלי בש"ח כמספר (לדוגמה "עד 2 מיליון" → 2000000), או null
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
        return parsed
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

    # עיר
    q_city = (query.get("city") or "").strip()
    if q_city:
        if q_city.lower() in combined or q_city.replace("קרית","קריית").lower() in combined:
            score += 30
        else:
            return 0

    # שכונה (התאמה רכה)
    q_nb = (query.get("neighborhood") or "").strip()
    if q_nb and q_nb.lower() in combined:
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
        if not (parsed.get("city") or parsed.get("neighborhood") or parsed.get("rooms") or parsed.get("budget_max") or parsed.get("keywords")):
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
# מנהלים קבועים (מוגדרים לפי מספר טלפון) — בנוסף למשתנה הסביבה ADMIN_PHONES אם קיים
_DEFAULT_ADMIN_PHONES = [
    "0546000808",  # אודי שמול
    "0544448065",  # מתן ביטון
    "0525640615",  # אוריין שמול
]
ADMIN_PHONES = _DEFAULT_ADMIN_PHONES + [p.strip() for p in os.environ.get("ADMIN_PHONES", "").split(",") if p.strip()]

# קודי כניסה קבועים שעוקפים את ה-SMS (Twilio) — { 9 ספרות אחרונות של הטלפון: קוד }
# לשימוש אישי בלבד. מי שמכניס מספר+קוד תואמים נכנס בלי SMS.
_BYPASS_LOGINS = {
    "505709865": "1324",   # אייל שמול
}

# --- in-memory OTP + sessions ---
_otp_store = {}     # last9 -> {"code","exp","tries"}
_web_sessions = {}  # token -> {"phone","role","name","exp"}
_OTP_TTL  = 300
_SESS_TTL = 6 * 3600

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

def web_send_sms(last9, body):
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

def web_fetch_raw(type_he, frm="01/01/2020", to="31/12/2099"):
    _ck = "raw:" + str(type_he) + ":" + str(frm) + ":" + str(to)
    c = _cache_get(_ck, 30)
    if c is not None:
        return c
    rows = _web_fetch_raw_uncached(type_he, frm, to)
    if rows:
        _cache_put(_ck, rows)
    return rows
def _web_fetch_raw_uncached(type_he, frm="01/01/2020", to="31/12/2099"):
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

def _phones_for_name(name):
    nn = _norm_name(name)
    if not nn: return set()
    s = set(p for p, n in web_phone_name_map().items() if _norm_name(n) == nn)
    for p, n in web_contacts_phone_name().items():
        if _norm_name(n) == nn:
            s.add(p)
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

def web_role_for(last9):
    if last9 in set(_last9(a) for a in ADMIN_PHONES): return "admin"
    if last9 in _COORDINATORS: return "coordinator"
    if web_contacts_phone_name().get(last9) or web_phone_name_map().get(last9): return "agent"
    return None

def _web_auth():
    tok = (request.headers.get("X-Auth-Token") or request.args.get("token")
           or ((request.get_json(silent=True) or {}).get("token") if request.method == "POST" else None))
    if not tok: return None
    s = _web_sessions.get(tok)
    if not s: return None
    if s["exp"] < time.time():
        _web_sessions.pop(tok, None); return None
    return s

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

# --- recent searches per user (phone -> {kind: [queries]}) ---
_recent = {}
def _push_recent(phone, kind, q):
    q = (q or "").strip()
    if not q or not phone: return
    lst = _recent.setdefault(phone, {}).setdefault(kind, [])
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
    code = f"{_secrets.randbelow(900000) + 100000}"
    _otp_store[phone] = {"code": code, "exp": time.time() + _OTP_TTL, "tries": 0}
    _host = (request.host or "remax-bot.onrender.com").split(":")[0]
    _sms = f"קוד הכניסה שלך ל-Family Bot: {code} (תקף ל-5 דקות)\n\n@{_host} #{code}"
    if not web_send_sms(phone, _sms):
        return jsonify({"ok": False, "reason": "sms_failed"})
    return jsonify({"ok": True})

@app.route("/api/auth/verify", methods=["POST"])
def api_auth_verify():
    body  = request.get_json(silent=True) or {}
    phone = _last9(body.get("phone", "")); code = str(body.get("code", "")).strip()
    # קוד כניסה קבוע (עוקף SMS) — רק למספרים שהוגדרו ב-_BYPASS_LOGINS
    if phone in _BYPASS_LOGINS and code == _BYPASS_LOGINS[phone]:
        role = web_role_for(phone) or "admin"
        if role == "admin": name = "מנהל"
        elif role == "coordinator": name = _COORDINATORS[phone]["name"]
        else: name = web_contacts_phone_name().get(phone) or web_phone_name_map().get(phone) or "סוכן"
        token = _secrets.token_urlsafe(24)
        sess = {"phone": phone, "role": role, "name": name, "exp": time.time() + _SESS_TTL}
        if role == "coordinator":
            sess["agents"] = list(_COORDINATORS[phone]["agents"])
            sess["agent_names"] = list(_COORDINATORS[phone]["names"])
        _web_sessions[token] = sess
        _log_activity(name, role, phone, "כניסה (קוד קבוע)")
        return jsonify({"ok": True, "token": token, "role": role, "name": name})
    rec = _otp_store.get(phone)
    if not rec or rec["exp"] < time.time(): return jsonify({"ok": False, "reason": "expired"})
    if rec["tries"] >= 5: _otp_store.pop(phone, None); return jsonify({"ok": False, "reason": "too_many"})
    if code != rec["code"]:
        rec["tries"] += 1; return jsonify({"ok": False, "reason": "wrong"})
    _otp_store.pop(phone, None)
    role = web_role_for(phone)
    if role == "admin": name = "מנהל"
    elif role == "coordinator": name = _COORDINATORS[phone]["name"]
    else: name = web_phone_name_map().get(phone) or "סוכן"
    token = _secrets.token_urlsafe(24)
    sess = {"phone": phone, "role": role, "name": name, "exp": time.time() + _SESS_TTL}
    if role == "coordinator":
        sess["agents"] = list(_COORDINATORS[phone]["agents"])
        sess["agent_names"] = list(_COORDINATORS[phone]["names"])
    _web_sessions[token] = sess
    _log_activity(name, role, phone, "כניסה")
    return jsonify({"ok": True, "token": token, "role": role, "name": name})

# ── History (calls + signatures) ───────────────────────────────────────────────
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
        names = set(_norm_name(n) for n in (eff.get("agent_names") or []))
        for a in agset:
            nm = _norm_name(web_phone_name_map().get(a, ""))
            if nm: names.add(nm)
        names.discard("")
        calls = [c for c in calls if _last9(c.get("agent_phone", "")) in agset]
        sigs  = [g for g in sigs if _norm_name(g.get("agent", "")) in names]
    elif eff["role"] != "admin":
        nm = _norm_name(eff["name"])
        if eff.get("phones"):
            pset = eff["phones"]
            calls = [c for c in calls if _last9(c.get("agent_phone", "")) in pset]
        else:
            ph = eff["phone"]
            calls = [c for c in calls if _last9(c.get("agent_phone", "")) == ph]
        sigs  = [g for g in sigs if _norm_name(g.get("agent", "")) == nm]
    _hidden = _fetch_hidden_calls()
    if request.args.get("hidden") == "1":
        calls = [c for c in calls if str(c.get("event_id", "")) in _hidden]
    else:
        calls = [c for c in calls if str(c.get("event_id", "")) not in _hidden]
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
        caller_disp, caller_tel = _il_phone(c.get("caller_phone", ""))
        call_out.append({
            "time": _fmt_il_dt(c.get("received_at", "")),
            "status": str(c.get("status", "")).upper(),
            "caller": caller_disp,
            "tel": caller_tel,
            "duration": c.get("duration_sec", ""),
            "agent": (c.get("agent", "") or "").strip(),
            "summary": text,
            "clientDetails": client_details,
            "callback": callback,
            "id": str(c.get("event_id", "") or ""),
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
    } for g in sigs[:500]]
    vphone = fetch_agent_virtual_phones().get(_norm_name(eff["name"]), "")
    return jsonify({"ok": True, "role": eff["role"], "name": eff["name"],
                    "vphone": vphone, "calls": call_out, "signatures": sig_out})

# ── Activity log (admin only) ──────────────────────────────────────────────────
@app.route("/api/recent", methods=["GET"])
def api_recent():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    kind = request.args.get("kind", "")
    return jsonify({"ok": True, "items": _recent.get(s["phone"], {}).get(kind, [])})

@app.route("/api/agents", methods=["GET"])
def api_agents():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if s["role"] != "admin": return jsonify({"ok": False, "reason": "forbidden"}), 403
    names = sorted(set(_norm_name(n) for n in web_phone_name_map().values() if _norm_name(n)))
    return jsonify({"ok": True, "agents": [{"name": n} for n in names]})

@app.route("/api/activity", methods=["GET"])
def api_activity():
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if s["role"] != "admin": return jsonify({"ok": False, "reason": "forbidden"}), 403
    c = _cache_get("activity_today", 30)
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
    return jsonify({"ok": True, "items": merged[:300]})

def _web_org_summary(frm, to, agent_name=None, agent_phones=None):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as _ex:
        _fc = _ex.submit(web_fetch_raw, "שיחות", frm, to)
        _fs = _ex.submit(get_signings, frm, to)
        _fp = _ex.submit(web_fetch_raw, "נכסים", frm, to)
        calls, sigs, props = _fc.result(), _fs.result(), _fp.result()
    if agent_name or agent_phones:
        _nn = _norm_name(agent_name or "")
        _phs = set(agent_phones or [])
        def _is_mine(row, use_phone=False):
            if _nn and _norm_name(row.get("agent", "")) == _nn: return True
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
    konim = bladiut = skhirut = 0; exc = []
    for g in sigs:
        dt = str(g.get("deal_type", "")).upper()
        if "CLIENT_SALE" in dt: konim += 1
        elif "OWNER_EXCLUSIVE" in dt: bladiut += 1
        elif "OWNER_RENT" in dt or "CLIENT_RENT" in dt: skhirut += 1
        if "OWNER_EXCLUSIVE" in dt:
            exc.append({"date": g.get("_date_key", ""),
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
        "props": {"total": len(props), "topCities": top_cities},
    }

def _agent_insights(frm, to, prev_frm, prev_to, eff_name, eff_phones, cur_sm):
    """מלל חופשי על ביצועי הסוכן: מגמות מול התקופה הקודמת + דירוג בלעדיות."""
    out = []
    try:
        prev = _web_org_summary(prev_frm, prev_to, eff_name, eff_phones)
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
    c = sm["calls"]; sg = sm["sigs"]
    L = [f"📊 *סיכום {label}* ({frm}–{to})", ""]
    L.append(f"📞 שיחות: {c['total']} · נענו: {c['answered']} ({c['rate']}%)")
    L.append(f"   לא נענו: {c['notAnswered']} (CC {c['cc']} · BUSY {c['busy']} · ללא מענה {c['noanswer']})")
    L.append("")
    L.append("👥 *מתווכים מובילים:*")
    for i, a in enumerate(sm["agents"][:10], 1):
        L.append(f"{i}. {a['name']}: {a['total']} שיחות ({a['answered']} נענו · {a['rate']}%)")
    L.append("")
    L.append(f"✍️ חתימות: {sg['total']} — קונים {sg['konim']} · בלעדיות {sg['bladiut']} · שכירויות {sg['skhirut']}")
    L.append(f"🏘️ נכסים חדשים: {sm['props']['total']}")
    L.append(f"🏆 בלעדיות חדשות: {len(sm['exclusives'])}")
    L.append("")
    L.append("_הופק מ-Family Bot 🏠_")
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
    label = {"week": "השבוע", "month": "החודש", "year": "השנה"}.get(period, "החודש")
    if sel_month.isdigit() and 1 <= int(sel_month) <= 12:
        mo = int(sel_month)
        start = now.replace(month=mo, day=1, hour=0, minute=0, second=0, microsecond=0)
        if mo < now.month:  # חודש שכבר הסתיים — עד סוף החודש
            nxt = start.replace(year=start.year + 1, month=1) if mo == 12 else start.replace(month=mo + 1)
            end = nxt - timedelta(days=1)
        label = f"{_HE_MONTHS[mo - 1]} {start.year}"
    elif period == "week":
        start = now - timedelta(days=(now.weekday() + 1) % 7)   # ראשון
    elif period == "year":
        start = now.replace(month=1, day=1)
    else:
        period = "month"; start = now.replace(day=1)
    frm = start.strftime("%d/%m/%Y"); to = end.strftime("%d/%m/%Y")
    as_name = request.args.get("as", "").strip() if s["role"] in ("admin", "coordinator") else ""
    if s["role"] == "agent":
        eff_name = s.get("name", "")
        eff_phones = set(_phones_for_name(eff_name))
        if s.get("phone"): eff_phones.add(_last9(s["phone"]))
        scope = eff_name or "הדוח שלי"
    elif as_name:
        eff_name = as_name
        eff_phones = set(_phones_for_name(as_name))
        scope = as_name
    else:
        eff_name = None; eff_phones = None; scope = "כל המשרד"
    insights = []
    try:
        sm = _web_org_summary(frm, to, eff_name, eff_phones)
        try:   # ספירת "מודעות" — אותו מקור של "נכסים במשרד" (יד2): סוכן=שלו, מנהל=סה"כ
            _lr = fetch_sheet_rows()
            listings_total = (sum(1 for r in _lr if _agent_owns_row(r, eff_name, eff_phones or set()))
                              if eff_name else len(_lr))
        except Exception:
            listings_total = 0
        shtaf = []   # גיוס נכסים בשת״פ — פילוח לפי משרד בתקופה (למנהל/רכז)
        if s["role"] in ("admin", "coordinator"):
            try:
                _se = start.timestamp(); _ee = end.timestamp() + 86400
                _by = {}
                for _r in _dedupe_exclusives(fetch_external_exclusives()):
                    _ep = _excl_epoch(_r.get("received_at", ""))
                    if _ep and _se <= _ep < _ee:
                        _off = (str(_r.get("office", "") or "").strip() or "ללא שם משרד")
                        _by[_off] = _by.get(_off, 0) + 1
                shtaf = sorted([{"office": k, "count": v} for k, v in _by.items()], key=lambda x: -x["count"])
            except Exception:
                shtaf = []
        if eff_name:
            _delta = end - start
            _pe = start - timedelta(days=1)
            _ps = _pe - _delta
            insights = _agent_insights(frm, to, _ps.strftime("%d/%m/%Y"), _pe.strftime("%d/%m/%Y"), eff_name, eff_phones, sm)
        wa = _report_wa_text(sm, label + " · " + scope, frm, to)
        if insights:
            wa = "📊 *תובנות:*\n" + "\n".join(insights) + "\n\n" + wa
        if shtaf:
            _tot = sum(o["count"] for o in shtaf)
            _lines = "\n".join((("🏠 " if _is_our_office(o["office"]) else "• ") + o["office"] + ": " + str(o["count"]))
                               for o in shtaf)
            wa = wa + '\n\n🤝 *גיוס נכסים בשת"פ — ' + label + '* (סה"כ ' + str(_tot) + ')\n' + _lines
        return jsonify({"ok": True, "label": label, "scope": scope, "from": frm, "to": to,
                        "insights": insights, "summary": sm, "listings": listings_total,
                        "shtaf": shtaf, "wa_text": wa})
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
                "date": (row.get("תאריך יצירה", "") or "").strip(),
                "agent": ag,
                "wa": _wa_phone(phones.get(ag, row.get("טלפון 1", ""))),
            }
            if score is not None:
                d["score"] = min(100, int(score))
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
        return jsonify({"ok": True, "summary": (parsed or {}).get("summary_he", ""), "results": out})
    except Exception as e:
        log.error(f"properties search error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

# ── "הנכסים שלי" — כל הנכסים של הסוכן מגיליון המשרד, לפי שם וטלפון ──────────────
def _agent_owns_row(row, agent_name, agent_phones):
    """האם הנכס שייך לסוכן — לפי שם (סוכן 1/2) או מספר טלפון (טלפון 1/2)."""
    nn = _norm_name(agent_name)
    if nn and nn not in ("מנהל", "סוכן"):
        for col in ("סוכן 1", "סוכן 2"):
            if _norm_name(row.get(col, "")) == nn:
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
        # מנהל יכול לצפות כסוכן עם as; אחרת הזהות של המחובר עצמו
        as_name = ""
        if s["role"] == "admin":
            as_name = ((request.get_json(silent=True) or {}).get("as", "")
                       or request.args.get("as", "")).strip()
        if as_name:
            eff_name = as_name
            eff_phones = set(_phones_for_name(as_name))
        else:
            eff_name = s.get("name", "")
            eff_phones = set(_phones_for_name(eff_name))
            if s.get("phone"):
                eff_phones.add(_last9(s["phone"]))
        rows = fetch_sheet_rows()
        mine = [r for r in rows if _agent_owns_row(r, eff_name, eff_phones)]
        phones_map = fetch_agents_phones()
        pending = _fetch_pending_listings()
        out = []
        for r in mine:
            ag = (r.get("סוכן 1", "") or "").strip()
            lid = (r.get("מספר מודעה", "") or "").strip()
            out.append({
                "id": lid,
                "own": True,
                "pending": lid in pending,
                "type": (r.get("סוג נכס", "") or "").strip(),
                "city": (r.get("עיר / ישוב", "") or "").strip(),
                "neighborhood": (r.get("שכונה", "") or "").strip(),
                "address": (f"{r.get('כתובת','')} {r.get('מספר בית','')}").strip(),
                "rooms": (r.get("חדרים", "") or "").strip(),
                "size": (r.get('מ"ר', "") or r.get("מ״ר", "") or "").strip(),
                "floor": (r.get("קומה", "") or "").strip(),
                "price": (r.get("מחיר", "") or "").strip(),
                "agent": ag,
                "wa": _wa_phone(phones_map.get(ag, r.get("טלפון 1", ""))),
            })
        _log_activity(s["name"], s["role"], s["phone"], "הנכסים שלי",
                      eff_name if as_name else "")
        return jsonify({"ok": True, "count": len(out), "name": eff_name, "results": out})
    except Exception as e:
        log.error(f"my properties error: {e}", exc_info=True)
        return jsonify({"ok": False, "reason": str(e)[:160]}), 500

SECRETARY_EMAIL = os.environ.get("SECRETARY_EMAIL", "orianshmul@gmail.com")
def _fetch_pending_listings():
    c = _cache_get("pending_listings", 60)
    if c is not None: return c
    j = _buyers_apps_post("listpending", {})
    ids = set(str(x).strip() for x in (j.get("ids", []) if (j and j.get("ok")) else []))
    _cache_put("pending_listings", ids)
    return ids

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
    if s["role"] in ("admin", "coordinator"):
        an = (body.get("as") or "").strip()
        if an: eff_name = an
    payload = {
        "listing_id": lid,
        "address": (body.get("address") or "").strip(),
        "kind": kind,
        "new_price": (body.get("new_price") or "").strip(),
        "agent": eff_name,
        "agent_phone": _last9(s.get("phone", "")),
        "secretary": SECRETARY_EMAIL,
    }
    j = _buyers_apps_post("requestchange", payload)
    if not j or not j.get("ok"):
        return jsonify({"ok": False, "reason": (j or {}).get("error", "fail")}), 502
    _cache_clear("pending_listings")
    _log_activity(s["name"], s["role"], s["phone"], ("בקשת הסרת מודעה" if kind == "remove" else "בקשת עדכון מחיר"), lid)
    return jsonify({"ok": True})

# ── "נכס נולד" — נכסים חדשים עם חשיפה מושהית פר-סוכן ─────────────────────────────
NEWBORN_SHEET_TAB   = os.environ.get("NEWBORN_SHEET_TAB", "נכס נולד")
NEWBORN_DELAYS_TAB  = os.environ.get("NEWBORN_DELAYS_TAB", "נכסנולד_הגדרות")
NEWBORN_DEFAULT_DELAY = int(os.environ.get("NEWBORN_DEFAULT_DELAY", "0") or 0)
NEWBORN_WINDOW_DAYS   = int(os.environ.get("NEWBORN_WINDOW_DAYS", "90") or 90)
NEWBORN_HIDDEN        = 10 ** 9   # ערך "מוסתר" — הסוכן לא רואה שום נכס
_NB_HIDDEN_TOKENS = {"מוסתר", "מוסתרת", "הסתר", "לעולם", "אין", "לא", "-", "–", "—", "x", "X", "✗"}

def fetch_newborn():
    c = _cache_get("newborn_rows", 60)
    if c is not None: return c
    j = _buyers_apps_post("listnewborn", {})
    rows = (j.get("rows", []) or []) if (j and j.get("ok")) else []
    _cache_put("newborn_rows", rows)
    return rows

def _fetch_newborn_delays():
    c = _cache_get("newborn_delays", 60)
    if c is not None: return c
    d = {"_default": NEWBORN_DEFAULT_DELAY}
    j = _buyers_apps_post("listnewborndelays", {})
    _delay_rows = (j.get("rows", []) or []) if (j and j.get("ok")) else []
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
    c = _cache_get("newborn_contacts", 45)
    if c is not None: return c
    j = _buyers_apps_post("listnewborncontacts", {})
    rows = (j.get("rows", []) or []) if (j and j.get("ok")) else []
    d = {}
    for r in rows:
        k = (r.get("key", "") or r.get("מפתח", "") or "").strip()
        ag = (r.get("agent", "") or r.get("סוכן", "") or "").strip()
        if not k: continue
        d.setdefault(k, [])
        if ag and ag not in d[k]: d[k].append(ag)
    _cache_put("newborn_contacts", d)
    return d

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

def _newborn_price(p):
    p = str(p or "").strip()
    if not p:
        return ""
    try:
        n = int(round(float(p.replace(",", "").replace("₪", "").strip())))
        return f"{n:,} ₪"
    except Exception:
        return p

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
        admin_all = (s["role"] == "admin" and not as_name)
        delays = _fetch_newborn_delays()
        delay = 0 if admin_all else int(delays.get(eff_norm, delays.get("_default", 0)))
        if not admin_all and delay >= NEWBORN_HIDDEN:   # מוסתר — לא רואה כלום, אין באנר
            return jsonify({"ok": True, "count": 0, "released": 0, "delay": delay, "results": []})
        now = time.time()
        contacts = _fetch_newborn_contacts()
        rows = [r for r in fetch_newborn() if _newborn_created_epoch(r)]
        rows.sort(key=_newborn_created_epoch, reverse=True)
        out = []
        for r in rows:
            created = _newborn_created_epoch(r)
            if (now - created) / 86400 > NEWBORN_WINDOW_DAYS:   # ישנים מדי לא מציגים
                continue
            def _nb(v):
                v = str(v or "").strip()
                return "" if v in ("-", "—", "") else v
            lister = _nb(r.get("משתמש", "") or r.get("סוכן 1", ""))
            own = bool(eff_norm) and bool(lister) and _norm_name(lister) == eff_norm
            rel_epoch = created + delay * 86400
            released = admin_all or own or now >= rel_epoch
            if not released:
                continue   # מציגים רק נכסים שכבר נחשפו לסוכן (14+ ימים מהיצירה)
            city = _nb(r.get("עיר", "") or r.get("עיר / ישוב", ""))
            ophone = _nb(r.get("טלפון בעל הנכס-", "") or r.get("טלפון בעל הנכס", ""))
            _k = _nb_key(r)
            out.append({
                "released": True,
                "own": own,
                "key": _k,
                "contacted": contacts.get(_k, []),
                "city": city,
                "address": _nb(r.get("רחוב1", "") or r.get("רחוב", "")),
                "desc": _nb(r.get("תיאור נכס", "")),
                "price": _newborn_price(r.get("מחיר", "")),
                "notes": _nb(r.get("הערות חדש", ""))[:160],
                "owner": _nb(r.get("שם בעל הנכס", "")),
                "phone": ophone,
                "wa": _wa_phone(ophone),
                "agent": lister,
                "link": _nb(r.get("קישור", "")),
                "date": _nb(r.get("נוצר בתאריך", "") or r.get("תאריך יצירה", "")),
            })
            if len(out) >= 20:   # רק 20 הנכסים האחרונים שנחשפו (ממוינים מהחדש לישן)
                break
        return jsonify({"ok": True, "count": len(out),
                        "released": sum(1 for x in out if x["released"]), "delay": delay, "results": out})
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
    return jsonify({"ok": True})

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
        _log_activity(s["name"], s["role"], s["phone"], "חיפוש בלעדיות", q)
        if not (request.get_json(silent=True) or {}).get("nosave"):
            _push_recent(s["phone"], "excl", q)
        parsed = parse_exclusivity_search_query(q if q.startswith("מחפש") else ("מחפש בלעדיות " + q)) or {}
        parsed["budget_max"] = _web_num(parsed.get("budget_max"))   # מנע TypeError בכפל
        parsed["rooms"]      = _web_num(parsed.get("rooms"))
        rows = _dedupe_exclusives(fetch_external_exclusives())
        if not (parsed.get("city") or parsed.get("rooms") or parsed.get("budget_max") or parsed.get("keywords")):
            rows = sorted(rows, key=lambda r: _excl_epoch(r.get("received_at", "")), reverse=True)
            matches = [(1, r) for r in rows[:30]]
        else:
            scored = [(score_exclusivity_match(r, parsed), r) for r in rows]
            scored = [(sc, r) for sc, r in scored if sc > 0]
            scored.sort(key=lambda x: -x[0])
            matches = scored[:15]
        out = [{
            "score": min(100, int(sc)),
            "street": str(r.get("street", "") or "").strip(),
            "dest": str(r.get("dest", "") or "").strip(),
            "desc": str(r.get("desti", "") or "").strip(),
            "price": str(r.get("price", "") or "").strip(),
            "office": str(r.get("office", "") or "").strip(),
            "date": str(r.get("received_at", "") or "")[:10],
            "link": str(r.get("link", "") or "").strip(),
        } for sc, r in matches]
        return jsonify({"ok": True, "summary": parsed.get("summary_he", ""), "results": out})
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

def _fetch_manual_buyers():
    c = _cache_get("buyers", 20)
    if c is not None:
        return c
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
        if as_name:
            eff_name = as_name
            ps = list(_phones_for_name(as_name))
            eff_phone = ps[0] if ps else ""
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
    return jsonify({"ok": True})

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
            mine = rows  # מנהל רואה את כל הקונים
        else:
            eff_name = as_name or s.get("name", "")
            eff_phones = set(_phones_for_name(eff_name))
            if not as_name and s.get("phone"):
                eff_phones.add(_last9(s["phone"]))
            nn = _norm_name(eff_name)
            mine = [r for r in rows
                    if (_norm_name(r.get("agent", "")) == nn and nn)
                    or (_last9(r.get("agent_phone", "")) in eff_phones)]
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
        return jsonify({"ok": True, "count": len(out), "results": out})
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
    j = _buyers_apps_post("updatebuyer", {"row": row, "search": search})
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
    c = _cache_get("hidden_calls", 60)
    if c is not None: return c
    j = _buyers_apps_post("listhidden", {})
    ids = set(str(x) for x in (j.get("ids", []) if (j and j.get("ok")) else []))
    _cache_put("hidden_calls", ids)
    return ids

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
@app.route("/app", methods=["GET"])
def family_bot_app():
    return Response(FAMILY_BOT_HTML, mimetype="text/html")

_APP_ICON_B64 = "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"
@app.route("/assets/icon", methods=["GET"])
def family_icon():
    import base64 as _b64
    resp = Response(_b64.b64decode(_APP_ICON_B64), mimetype="image/png")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp

@app.route("/assets/logo", methods=["GET"])
def family_logo():
    names = ["family-logo.jpg", "family-logo.jpeg", "family-logo.png", "family-logo.webp",
             "family-logo.png.jpg", "logo.png", "logo.jpg"]
    dirs = [Path(__file__).parent, Path("."), Path("/app")]
    for d in dirs:
        for n in names:
            p = d / n
            if p.exists():
                ext = p.suffix.lower()
                mt = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/webp" if ext == ".webp" else "image/png")
                resp = send_file(str(p), mimetype=mt, max_age=0)
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                return resp
    return ("", 404)

FAMILY_BOT_HTML = r'''<!DOCTYPE html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Family Bot">
<meta name="theme-color" content="#0D1B2A">
<link rel="apple-touch-icon" href="/assets/icon">
<link rel="apple-touch-icon-precomposed" href="/assets/icon">
<link rel="icon" href="/assets/icon">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800;900&display=swap" rel="stylesheet">
<title>Family Bot</title>
<style>
:root{--ink:#0D1B2A;--gold:#C9972A;--red:#E11B22;--blue:#003DA5;--bg:#eef1f5;--muted:#6b7280;--line:#eef0f3}
*{box-sizing:border-box}
body{font-family:"Heebo","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;margin:0;background:linear-gradient(180deg,#f4f7fb 0,var(--bg) 240px) no-repeat;background-color:var(--bg);min-height:100vh;color:var(--ink);-webkit-font-smoothing:antialiased;letter-spacing:-.01em}
.wrap{max-width:620px;margin:0 auto;padding:calc(10px + env(safe-area-inset-top,0)) 14px 100px}
.brand{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:12px;margin:6px 0 12px;padding-bottom:12px;border-bottom:2px solid var(--gold)}
.brand img{max-height:42px;max-width:60%;object-fit:contain}.brandtxt{font-size:20px;font-weight:800}
.brandname{font-size:15px;font-weight:800;color:var(--ink);background:#fff;border:1px solid #e6e8ec;border-radius:999px;padding:5px 13px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.loginlogo{text-align:center;margin:18px 0 22px}
.loginlogo img{width:75%;max-width:300px;height:auto}
.card{background:#fff;border-radius:18px;padding:17px;margin:13px 0;box-shadow:0 1px 2px rgba(13,27,42,.04),0 10px 28px rgba(13,27,42,.06);border:1px solid #eceef2}
h1{font-size:20px;margin:6px 0;font-weight:800}
h2{font-size:16px;margin:0 0 12px;font-weight:800;padding-inline-start:10px;border-inline-start:4px solid var(--gold);line-height:1.25}
input,textarea{font-size:16px;padding:13px 14px;border-radius:13px;border:1.5px solid #e0e4e9;width:100%;font-family:inherit;background:#fbfcfd;transition:border-color .15s,box-shadow .15s}
input:focus,textarea:focus{outline:none;border-color:var(--ink);box-shadow:0 0 0 3px rgba(13,27,42,.08)}
button{font-size:16px;padding:14px;border-radius:13px;border:none;width:100%;font-family:inherit;background:var(--ink);color:#fff;margin-top:10px;font-weight:800;cursor:pointer;transition:transform .06s,filter .15s,box-shadow .15s;box-shadow:0 4px 14px rgba(13,27,42,.16)}
button:active{transform:translateY(1px)}button:hover{filter:brightness(1.08)}
button.gold{background:linear-gradient(180deg,#d4a437,#c0901f);color:#231700;box-shadow:0 4px 14px rgba(201,151,42,.32)}button.sec{background:#eef1f5;color:var(--ink);border:1px solid #e2e6ea;box-shadow:none}
.tabs{position:fixed;bottom:0;left:0;right:0;background:rgba(255,255,255,.97);backdrop-filter:blur(8px);display:flex;border-top:1px solid #e6e9ee;max-width:620px;margin:0 auto;box-shadow:0 -3px 14px rgba(13,27,42,.06);padding-bottom:env(safe-area-inset-bottom,0)}
.tab{flex:1;text-align:center;padding:11px 1px;font-size:12px;line-height:1.25;color:var(--muted);cursor:pointer;border-top:3px solid transparent}
.tab.on{color:var(--ink);font-weight:800;border-top-color:var(--gold);background:linear-gradient(to bottom,rgba(201,151,42,.12),transparent)}
.chips{display:flex;gap:7px;margin:6px 0 2px}
.chip{flex:1;text-align:center;padding:10px 6px;border-radius:11px;background:#eef1f5;color:var(--ink);cursor:pointer;font-size:13px;font-weight:700;border:1px solid #e3e7eb}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.monthsel{flex:1;min-width:0;text-align:center;padding:10px 6px;border-radius:11px;background:#eef1f5;color:var(--ink);cursor:pointer;font-size:13px;font-weight:700;border:1px solid #e3e7eb}
.addbuyer{display:inline-block;width:auto;padding:3px 9px;margin:0;font-size:12px;font-weight:700;border:1px solid var(--gold,#caa14a);background:#fff7e6;color:#7a5c12;border-radius:9px;cursor:pointer}
.hidecall{display:inline-block;width:auto;padding:3px 9px;margin:0;font-size:12px;font-weight:700;border:1px solid #c9ccd1;background:#f3f4f6;color:#555;border-radius:9px;cursor:pointer}
.hlink{color:var(--muted);font-size:12px;font-weight:700;cursor:pointer;text-decoration:underline}
.lbtns{margin-top:6px;display:flex;gap:8px;flex-wrap:wrap}
.lreq{width:auto;padding:4px 10px;margin:0;font-size:12px;font-weight:700;border-radius:9px;cursor:pointer;border:1px solid #c9ccd1;background:#f3f4f6;color:#444}
.lpend{display:inline-block;background:#fff3d6;color:#7a5c12;font-weight:800;padding:3px 10px;border-radius:9px;border:1px solid #e7d39a;font-size:12px}
.ovl{position:fixed;inset:0;background:rgba(13,27,42,.55);display:flex;align-items:center;justify-content:center;z-index:9999;padding:14px}
.ovlbox{background:#fff;border-radius:16px;padding:16px;width:100%;max-width:430px;box-shadow:0 12px 40px rgba(0,0,0,.3);max-height:90vh;overflow:auto}
.ovlbox input,.ovlbox textarea{width:100%;margin:5px 0;padding:10px;border:1px solid #d8dde3;border-radius:10px;font-size:14px;font-family:inherit;box-sizing:border-box}
.ovlbtns{display:flex;gap:8px;margin-top:8px}.ovlbtns button{flex:1}
.buyerrow{border-right:4px solid var(--gold,#caa14a);background:#fffdf7}
.bhead{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:2px}
.btag{display:inline-block;background:var(--gold,#caa14a);color:#2e2204;font-size:11px;font-weight:800;padding:2px 8px;border-radius:8px}
.bname{font-size:16px}
.bbudget{display:inline-block;background:#fff3d6;color:#7a5c12;font-weight:800;padding:2px 9px;border-radius:8px;border:1px solid #e7d39a;font-size:13px}
.bdel{margin-inline-start:auto;width:auto;padding:3px 8px;margin-top:0;margin-bottom:0;background:#fff;border:1px solid #e3a3a3;color:#b03a3a;border-radius:8px;font-size:13px;cursor:pointer;line-height:1}
.bmeta{margin:2px 0}
.bsum{margin-top:5px;color:#33405a;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.bsum.open{-webkit-line-clamp:unset;overflow:visible}
.bmore{display:inline-block;margin-top:3px;color:var(--gold,#8a6d1e);font-size:12px;font-weight:700;cursor:pointer}
.bqedit{width:100%;margin-top:8px;padding:9px 10px;border:1px dashed #cbb88a;border-radius:10px;font-size:13px;font-family:inherit;box-sizing:border-box;background:#fffdf7}
.bbtns{display:flex;gap:8px;margin-top:8px}
.bsearch{flex:1;width:auto;padding:9px 6px;margin:0;font-size:13px;font-weight:700;border-radius:10px;border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer}
.bsearch[data-k=excl]{background:#fff;color:var(--ink)}
.bresults{margin-top:8px}
.bresults:empty{margin:0}
.bresh{font-size:12px;font-weight:700;color:var(--muted);margin:4px 0 6px}
.insight{padding:7px 2px;border-bottom:1px solid #eef1f5;font-size:14px;font-weight:600}.insight:last-child{border-bottom:none}
.row{border-bottom:1px solid var(--line);padding:12px 2px;font-size:14.5px;line-height:1.55}.row:last-child{border:none}
.badge{display:inline-block;background:rgba(13,27,42,.08);color:var(--ink);font-size:11px;font-weight:800;padding:3px 9px;border-radius:999px;margin-inline-start:6px;vertical-align:middle}
.ans{display:inline-block;background:#e7f6ec;color:#137a3a;font-weight:800;font-size:12px;padding:2px 9px;border-radius:999px}
.noans{display:inline-block;background:#fdeaea;color:#c02626;font-weight:800;font-size:12px;padding:2px 9px;border-radius:999px}
.muted{color:var(--muted);font-size:13px}
.new{animation:hl 2.6s ease-out}@keyframes hl{0%{background:#fff7df}100%{background:transparent}}
.score{float:left;background:var(--ink);color:#fff;border-radius:999px;padding:2px 9px;font-size:12px;font-weight:800}
a{color:var(--blue);font-weight:700;text-decoration:none}a:hover{text-decoration:underline}
.err{color:var(--red);font-weight:700}.hidden{display:none}
.vphone{display:inline-block;font-size:12px;font-weight:800;color:#0d5aa7;background:#eaf3fb;border:1px solid #bcd9f0;border-radius:9px;padding:2px 9px;margin-inline-end:8px}
.vpnum{user-select:all;-webkit-user-select:all;letter-spacing:.3px}
.vpcopy{cursor:pointer;color:#0d5aa7;font-weight:800;margin-inline-start:6px;border-inline-start:1px solid #bcd9f0;padding-inline-start:6px}
.cbtn{display:inline-block;background:#137a3a;color:#fff!important;border-radius:10px;padding:4px 12px;font-size:12.5px;font-weight:800;text-decoration:none;margin-top:5px}
.rchips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px}.rchip{background:rgba(0,61,165,.08);color:var(--blue);border-radius:999px;padding:6px 12px;font-size:13px;font-weight:700;cursor:pointer;border:1px solid rgba(0,61,165,.15);max-width:240px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px;margin-top:8px}
.stat{background:linear-gradient(180deg,#fff,#f7f9fb);border:1px solid #eceff2;border-radius:14px;padding:13px 6px;text-align:center;box-shadow:0 1px 2px rgba(13,27,42,.03)}
.stat .n{font-size:21px;font-weight:800;color:var(--ink)}.stat .l{font-size:11px;color:var(--muted);margin-top:3px}
table{width:100%;border-collapse:collapse}th{font-size:12px;color:var(--muted);font-weight:700;padding:7px 4px;border-bottom:2px solid #eef0f3}td{padding:9px 4px;border-bottom:1px solid var(--line);font-size:14px}
.cdetails{background:rgba(201,151,42,.12);border-inline-start:3px solid var(--gold);border-radius:0 8px 8px 0;padding:9px 11px;margin-top:8px;font-size:14px;line-height:1.55}.cdetails b{color:#7a5a12;display:block;margin-bottom:3px}
 .nbbanner{cursor:pointer;background:linear-gradient(90deg,#fff4d6,#ffe9b3);border:1px solid #e7cf86;color:#6b4e0e;font-weight:800;border-radius:14px;padding:10px 14px;margin-bottom:10px;text-align:center;box-shadow:0 2px 10px rgba(180,140,20,.15)}
 .nbmodal{position:fixed;inset:0;background:rgba(13,27,42,.55);z-index:99;display:flex;align-items:flex-start;justify-content:center;overflow:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;padding:24px 12px}
 .nbmodal.hidden{display:none!important}
 .nbcard{background:#fff;border-radius:18px;max-width:560px;width:100%;padding:14px 16px;box-shadow:0 18px 50px rgba(0,0,0,.3)}
 .nbhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
 .nbx{width:auto;padding:4px 12px;margin:0;border-radius:9px;border:1px solid #d1d5db;background:#f3f4f6;color:#444;font-weight:800;cursor:pointer}
 .nblock{background:#f7f7f9;border:1px dashed #cfd2d8;color:#666}
 .nbcontact{display:inline-block;margin-top:5px;background:#e7f7ec;color:#1a7d3c;font-weight:800;font-size:12px;padding:3px 10px;border-radius:9px;border:1px solid #b6e3c4}
/* ===== ריענון עיצובי (מאושר) — אזור-אזור, ללא שינוי לוגיקה ===== */
.brand{justify-content:space-between!important;border-bottom:none!important;position:relative;padding-bottom:14px}
.brand:after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}
.sharebtn{width:38px!important;height:38px!important;padding:0!important;font-size:16px!important;border-radius:12px!important;display:inline-flex!important;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(13,27,42,.06)!important;margin:0!important}
.brandname{background:linear-gradient(180deg,#fff,#f7f9fc)!important;border:1px solid #e7d9b3!important;color:#5a4a1e!important;box-shadow:0 2px 8px rgba(201,151,42,.14)!important;display:inline-flex!important;align-items:center;gap:6px}
.brandname:before{content:"";width:7px;height:7px;border-radius:50%;background:#2ec26a;box-shadow:0 0 0 3px rgba(46,194,106,.18);flex:0 0 auto}
.btn-primary{background:linear-gradient(180deg,#16273c,#0D1B2A)!important;color:#fff!important;border:none!important;box-shadow:0 6px 18px rgba(13,27,42,.22)!important;font-weight:800}
.btn-gold{background:#fff!important;color:#5a4a1e!important;border:1px solid #ead9ab!important;box-shadow:0 4px 14px rgba(201,151,42,.12)!important;font-weight:800}
.selwrap{position:relative;display:inline-block;width:auto;margin:0 0 6px;vertical-align:middle}
.selwrap select{appearance:none;-webkit-appearance:none;padding:9px 30px 9px 12px!important;border-radius:12px!important;border:1px solid #e2e6ec!important;font-weight:700;color:var(--ink);background:#fff;box-shadow:0 2px 8px rgba(13,27,42,.04);margin:0!important}
.selwrap:after{content:"⌄";position:absolute;inset-inline-start:11px;top:4px;font-size:18px;color:#9aa3ad;pointer-events:none}
.btn-ghost{position:relative}
.btn-ghost .ndot{position:absolute;top:4px;inset-inline-start:8px;width:8px;height:8px;border-radius:50%;background:var(--red);border:1.5px solid #eef1f5}
.chips{background:#eef1f6;border:1px solid #e3e7ed;border-radius:13px;padding:3px;gap:2px!important}
.chips .chip{border:none!important;background:transparent!important;color:#5a6470!important;border-radius:10px!important;font-weight:800!important;padding:9px 4px!important}
.chips .chip.on{background:#fff!important;color:var(--ink)!important;border:none!important;box-shadow:0 2px 8px rgba(13,27,42,.12)!important;position:relative}
.chips .chip.on:after{content:"";display:block;height:2px;width:18px;margin:3px auto -2px;border-radius:2px;background:var(--gold)}
.callrow{position:relative;background:#fff;border:1px solid #edf0f4;border-radius:16px;padding:13px 15px;margin-bottom:11px;box-shadow:0 4px 16px rgba(13,27,42,.05);overflow:hidden}
.callrow:before{content:"";position:absolute;inset-inline-start:0;top:0;bottom:0;width:4px;background:linear-gradient(180deg,var(--gold),#a87d1a)}
.callrow.new{box-shadow:0 0 0 2px rgba(201,151,42,.4),0 4px 16px rgba(13,27,42,.06)}
.callrow .ctop{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:5px}
.callrow .ctime{font-size:12px;color:#8a929d;font-weight:700;white-space:nowrap}
.callrow .cphone{font-size:18px;font-weight:900;color:var(--ink);letter-spacing:.3px}
.callrow .cphone a{color:var(--ink);text-decoration:none}
.callrow .cmeta{color:var(--muted);font-size:12.5px;margin:3px 0 0}
.callrow .csumwrap{margin-top:7px}
.callrow .csum{font-size:14px;line-height:1.6;color:#33405a;margin-top:6px;padding-top:6px;border-top:1px dashed rgba(122,90,18,.25)}
.callrow .csum.collapsed{display:none}
.callrow .csummore{display:inline-block;margin-top:6px;color:#7a5a12;font-size:12.5px;font-weight:800;cursor:pointer}
.callrow .cdetails .csummore{margin-top:8px}
.callrow .cbtns{display:flex;gap:7px;margin-top:9px;flex-wrap:wrap;align-items:center}
.callrow .cbtns .addbuyer,.callrow .cbtns .hidecall{margin:0!important}
.ans,.noans{font-size:12px;padding:3px 11px}
.ouroffice{display:inline-block;background:#fdeef0;color:#c01f2a;font-weight:900;padding:1px 9px;border-radius:8px;border:1px solid #f3c4c9}
.tab{display:flex!important;flex-direction:column;align-items:center;justify-content:center;gap:0;position:relative}
.tabbadge{position:absolute;top:3px;inset-inline-start:50%;transform:translateX(58%);background:linear-gradient(180deg,#d4a437,#c0901f);color:#231700;font-size:10px;font-weight:900;min-width:17px;height:17px;border-radius:999px;display:flex;align-items:center;justify-content:center;padding:0 4px;box-shadow:0 1px 4px rgba(201,151,42,.45)}
.menuwrap{position:relative}
.appmenu{position:absolute;top:46px;inset-inline-start:0;z-index:60;background:#fff;border:1px solid #e6e9ef;border-radius:14px;box-shadow:0 16px 40px rgba(13,27,42,.22);padding:6px;min-width:218px}
.appmenu .mi{display:flex;align-items:center;gap:9px;padding:11px 12px;border-radius:10px;font-size:14.5px;font-weight:700;color:var(--ink);cursor:pointer}
.appmenu .mi:active,.appmenu .mi:hover{background:#f3f5f9}
.appmenu .mi-danger{color:#c0322f}
.appmenu hr{border:none;border-top:1px solid #eef0f4;margin:4px 4px}
.appmenu .mi-sub{padding:9px 12px 7px}
.appmenu .mi-sub .mi-lbl{font-size:13px;font-weight:800;color:var(--muted);margin-bottom:6px}
.appmenu .mi-sub select{width:100%;padding:10px 10px;border-radius:10px;border:1px solid #e2e6ec;font-family:inherit;font-size:14px;font-weight:700;color:var(--ink);background:#fff}
.tab .tic{display:inline-flex;align-items:center;justify-content:center;width:34px;height:27px;border-radius:9px;font-size:15px;margin-bottom:2px}
.tab.on{border-top-color:transparent!important;background:none!important}
.tab.on .tic{background:linear-gradient(180deg,rgba(201,151,42,.2),rgba(201,151,42,.06));box-shadow:inset 0 0 0 1px rgba(201,151,42,.28)}
</style></head><body><div class="wrap">
<div class="brand"><div class="menuwrap"><button class="sec sharebtn" id="menubtn" onclick="toggleMenu(event)" title="תפריט">☰</button><div id="appmenu" class="appmenu hidden"><div class="mi hidden" id="mi-activity" onclick="menuGo('activity')">📣 עדכונים</div><div class="mi" onclick="menuGo('report')">📊 דוחות</div><div class="mi-sub hidden" id="mi-imp"><div class="mi-lbl">👁 צפה כסוכן</div><select id="impsel" onchange="setImp(this.value)"><option value="">— כל הסוכנים —</option></select></div><hr><div class="mi" onclick="closeMenu();shareApp()">📲 שתף אפליקציה</div><div class="mi mi-danger" onclick="logout()">🚪 יציאה</div></div></div><img src="/assets/logo?v=3" alt="RE/MAX Family" onerror="this.style.display='none';var t=document.getElementById('brandtxt');if(t)t.style.display='block';"><div id="brandtxt" class="brandtxt" style="display:none">🏠 Family Bot</div><span id="brandname" class="brandname"></span></div>

<div id="login">
  <div class="loginlogo"><img src="/assets/icon" alt="RE/MAX Family" onerror="this.style.display='none'"></div>
  <div class="card" id="s1">
    <label class="muted">מספר הטלפון שלך</label>
    <input id="phone" type="tel" inputmode="numeric" placeholder="05X-XXXXXXX">
    <button onclick="sendCode()">שלח קוד ב-SMS</button>
    <div id="m1" class="muted"></div>
  </div>
  <div class="card hidden" id="s2">
    <label class="muted">הזן את הקוד מה-SMS</label>
    <input id="code" type="tel" inputmode="numeric" autocomplete="one-time-code" placeholder="______">
    <button onclick="verify()">כניסה</button>
    <button class="sec" onclick="show('s1')">החלף מספר</button>
    <div id="m2" class="muted"></div>
  </div>
</div>

<div id="appui" class="hidden">
  <div id="view"></div>
  <div class="tabs">
    <div class="tab on" data-t="calls" onclick="tab('calls')"><span class="tic">📞</span>שיחות שלי</div>
    <div class="tab" data-t="buyers" onclick="tab('buyers')"><span class="tic">👤</span>הקונים שלי</div>
    <div class="tab" data-t="sigs" onclick="tab('sigs')"><span class="tic">✍️</span>חתימות שלי</div>
    <div class="tab" data-t="props" onclick="tab('props')"><span class="tic">🏢</span>נכסים במשרד</div>
    <div class="tab" data-t="excl" onclick="tab('excl')"><span class="tic">🏘️</span>נכסים בשת״פ</div>
    <div class="tab" id="nbtab" onclick="openNewborn()"><span class="tic">🐥</span>נכס נולד<span class="tabbadge hidden" id="nbtabbadge"></span></div>
  </div>
  <div id="nbmodal" class="nbmodal hidden" onclick="if(event.target===this)closeNewborn()"></div>
</div>

<script>
var TOKEN=null,ROLE=null,NAME=null,TABNOW="calls",RANGE="month",timer=null,seenCall=0,seenSig=0,IMP=null,IMPNAME=null,CUR_EP=null,CUR_KIND=null;
function $(id){return document.getElementById(id);}
function show(id){$("s1").classList.add("hidden");$("s2").classList.add("hidden");$(id).classList.remove("hidden");}
function api(path,opt){opt=opt||{};opt.headers=opt.headers||{};if(TOKEN)opt.headers["X-Auth-Token"]=TOKEN;return fetch(path,opt).then(function(r){return r.json();});}
try{var sp=localStorage.getItem("fbPhone");if(sp)$("phone").value=sp;}catch(e){}
try{var st=localStorage.getItem("fbTok");if(st){TOKEN=st;ROLE=localStorage.getItem("fbRole");NAME=localStorage.getItem("fbName");enter();}}catch(e){}
function sendCode(){var p=$("phone").value.trim();if(!p){alert("הזן מספר");return;}try{localStorage.setItem("fbPhone",p);}catch(e){}$("m1").textContent="שולח…";
  api("/api/auth/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone:p})}).then(function(r){
    if(r.ok){show("s2");$("m2").textContent="";startOtp();}
    else{$("m1").innerHTML="<span class=err>"+(r.reason=="unknown"?"המספר לא מזוהה":(r.reason=="sms_failed"?"שליחת SMS נכשלה (בדוק Twilio)":"שגיאה"))+"</span>";}
  }).catch(function(){$("m1").innerHTML="<span class=err>שגיאה</span>";});}
function startOtp(){if(!("OTPCredential" in window))return;try{navigator.credentials.get({otp:{transport:["sms"]}}).then(function(o){if(o&&o.code){$("code").value=o.code;verify();}}).catch(function(){});}catch(e){}}
function verify(){var p=$("phone").value.trim(),c=$("code").value.trim();if(!c){alert("הזן קוד");return;}$("m2").textContent="בודק…";
  api("/api/auth/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone:p,code:c})}).then(function(r){
    if(r.ok){TOKEN=r.token;ROLE=r.role;NAME=r.name;try{localStorage.setItem("fbTok",TOKEN);localStorage.setItem("fbRole",ROLE);localStorage.setItem("fbName",NAME);}catch(e){}enter();}
    else{$("m2").innerHTML="<span class=err>"+(r.reason=="wrong"?"קוד שגוי":(r.reason=="expired"?"הקוד פג":"שגיאה"))+"</span>";}
  }).catch(function(){$("m2").innerHTML="<span class=err>שגיאה</span>";});}
function enter(){$("login").classList.add("hidden");$("appui").classList.remove("hidden");var bn=$("brandname");if(bn){bn.textContent=NAME?("שלום, "+NAME):"";}if(ROLE=="admin"){loadAgents();var ma=$("mi-activity"),mim=$("mi-imp");if(ma)ma.classList.remove("hidden");if(mim)mim.classList.remove("hidden");}tab("calls");setTimeout(loadNbBanner,1500);}
function tab(t){TABNOW=t;document.querySelectorAll(".tab").forEach(function(x){x.classList.toggle("on",x.dataset.t==t);});if(timer){clearInterval(timer);timer=null;}render();}
function render(){if(TABNOW=="calls")viewCalls();else if(TABNOW=="sigs")viewSigs();else if(TABNOW=="activity")viewActivity();else if(TABNOW=="report")viewReport();else viewSearch(TABNOW);}
var REPTEXT="";
function kpi(n,l){return "<div class=stat><div class=n>"+n+"</div><div class=l>"+l+"</div></div>";}
function viewReport(){
  var MN=["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"];
  var cm=new Date().getMonth()+1,opts='<option value="">▾ חודש</option>';
  for(var m=1;m<=cm;m++)opts+='<option value="'+m+'">'+MN[m-1]+'</option>';
  $("view").innerHTML='<div class=card><h2>📊 דוחות מנהל</h2><div class=chips id=rpc><div class=chip data-r=week>השבוע</div><div class="chip on" data-r=month>החודש</div><select id=monthsel class=monthsel>'+opts+'</select><div class=chip data-r=year>השנה</div></div></div><div id=rep></div>';
  document.querySelectorAll("#rpc .chip").forEach(function(c){c.onclick=function(){document.querySelectorAll("#rpc .chip").forEach(function(x){x.classList.remove("on");});c.classList.add("on");var ms=$("monthsel");if(ms)ms.value="";loadReport(c.dataset.r);};});
  var msel=$("monthsel");if(msel)msel.onchange=function(){if(!this.value)return;document.querySelectorAll("#rpc .chip").forEach(function(x){x.classList.remove("on");});loadReport("month",this.value);};
  loadReport("month");
}
var REPEXC=[];
function fmtD(s){s=String(s||"");if(s.indexOf("T")>-1){var pp=s.slice(0,10).split("-");if(pp.length==3)return pp[2]+"/"+pp[1]+"/"+pp[0];}return s.slice(0,16);}
function toggleExc(){var b=$("exclist");if(!b)return;if(b.innerHTML){b.innerHTML="";return;}if(!REPEXC||!REPEXC.length){b.innerHTML="<div class=card><div class=muted>אין בלעדיות בתקופה.</div></div>";return;}var list=REPEXC.slice().sort(function(a,c){return String(c.date).localeCompare(String(a.date));});b.innerHTML="<div class=card><h2>🏘️ בלעדיות ("+REPEXC.length+")</h2>"+list.map(function(e){return "<div class=row><b>"+esc(e.address||"—")+"</b><div class=muted>"+[e.agent?"👤 "+esc(e.agent):"",e.date?"📅 "+fmtD(e.date):""].filter(Boolean).join(" · ")+"</div></div>";}).join("")+"</div>";}
function loadReport(p,month){$("rep").innerHTML="<div class=card>טוען…</div>";api("/api/report?period="+p+(month?"&month="+month:"")+((typeof IMP!="undefined"&&IMP)?("&as="+encodeURIComponent(IMP)):"")).then(function(r){
  if(!r.ok){if(r.auth===false){relogin();return;}$("rep").innerHTML="<div class=card err>"+(r.reason=="forbidden"?"למנהל בלבד":"שגיאה")+"</div>";return;}
  REPTEXT=r.wa_text;var sm=r.summary,c=sm.calls,sg=sm.sigs;REPEXC=sm.exclusives||[];
  var h="<div class=card><div class=muted>📊 "+esc(r.label)+(r.scope?" · "+esc(r.scope):"")+" · "+r.from+"–"+r.to+"</div><div class=grid>"+kpi(c.total,"שיחות")+kpi(c.answered,"נענו")+kpi(c.rate+"%","אחוז מענה")+kpi(sg.total,"חתימות")+"<div class=stat style=cursor:pointer onclick=toggleExc()><div class=n>"+sm.exclusives.length+"</div><div class=l>בלעדיות 👁</div></div>"+kpi((r.listings!=null?r.listings:0),"מודעות")+"</div></div><div id=exclist></div>";
  if(r.insights&&r.insights.length){h+="<div class=card><h2>📊 תובנות</h2>"+r.insights.map(function(t){return "<div class=insight>"+esc(t)+"</div>";}).join("")+"</div>";}
  if(r.scope=="כל המשרד"){var ag="<table><tr><th style=text-align:start>מתווך</th><th>שיחות</th><th>נענו</th><th>%</th></tr>";sm.agents.slice(0,10).forEach(function(a,i){ag+="<tr><td>"+(i+1)+". "+esc(a.name)+"</td><td style=text-align:center>"+a.total+"</td><td style=text-align:center>"+a.answered+"</td><td style=text-align:center>"+a.rate+"%</td></tr>";});ag+="</table>";
  h+="<div class=card><h2>👥 מתווכים מובילים</h2>"+ag+"</div>";}
  h+="<div class=card><h2>✍️ חתימות</h2><div class=grid>"+kpi(sg.konim+" ("+sg.pctK+"%)","קונים")+kpi(sg.bladiut+" ("+sg.pctB+"%)","בלעדיות")+kpi(sg.skhirut+" ("+sg.pctS+"%)","שכירויות")+kpi(sg.total,"סה״כ")+"</div></div>";
  if(r.shtaf&&r.shtaf.length){var tot=r.shtaf.reduce(function(a,o){return a+o.count;},0);var st="<table><tr><th style=text-align:start>שם המשרד</th><th>נכסים</th></tr>";r.shtaf.forEach(function(o){st+="<tr><td>"+(isOurOffice(o.office)?"<span class=ouroffice>🏠 "+esc(o.office)+"</span>":esc(o.office))+"</td><td style=text-align:center><b>"+o.count+"</b></td></tr>";});st+="</table>";h+="<div class=card><h2>🤝 גיוס נכסים בשת״פ</h2><div class=muted style=margin-bottom:8px>"+esc(r.label)+" · "+r.shtaf.length+" משרדים · סה״כ "+tot+" נכסים</div>"+st+"</div>";}
  h+="<div class=card><button class=gold onclick=exportWa()>📲 ייצוא לוואטסאפ</button><button class=sec onclick=copyRep()>📋 העתק טקסט</button></div>";
  $("rep").innerHTML=h;
}).catch(function(){$("rep").innerHTML="<div class=card err>שגיאה</div>";});}
function exportWa(){window.open("https://wa.me/?text="+encodeURIComponent(REPTEXT),"_blank");}
function copyRep(){try{navigator.clipboard.writeText(REPTEXT).then(function(){alert("הטקסט הועתק");});}catch(e){alert("העתקה נכשלה");}}
function viewActivity(){
  $("view").innerHTML='<div class=card><h2>📣 עדכונים — שימוש במערכת</h2><div class=muted id=acthdr>טוען…</div></div><div id=actlist></div>';
  loadActivity();timer=setInterval(loadActivity,30000);
}
function loadActivity(){api("/api/activity").then(function(r){
  if(!r.ok){if(r.auth===false){relogin();return;}$("actlist").innerHTML="<div class=card err>"+(r.reason=="forbidden"?"למנהל בלבד":"שגיאה")+"</div>";return;}
  $("acthdr").innerHTML="🟢 חי · "+r.items.length+" פעולות אחרונות";
  $("actlist").innerHTML="<div class=card>"+(r.items.length?r.items.map(function(a){
    var t=new Date(a.ts*1000);var ts=("0"+t.getDate()).slice(-2)+"/"+("0"+(t.getMonth()+1)).slice(-2)+" "+("0"+t.getHours()).slice(-2)+":"+("0"+t.getMinutes()).slice(-2);
    var ph=a.phone?("0"+a.phone):"";var icon=a.action=="כניסה"?"🔑":"🔎";
    return "<div class=row>"+icon+" <b>"+esc(a.name)+"</b>"+(ph?" <span class=muted>("+ph+")</span>":"")+" · "+esc(a.action)+(a.detail?": "+esc(a.detail):"")+"<div class=muted>"+ts+"</div></div>";
  }).join(""):"<div class=muted>אין פעולות עדיין.</div>")+"</div>";
}).catch(function(){});}

function rangeChips(){return '<div class=chips id=rc><div class=chip data-r=day>היום</div><div class=chip data-r=week>השבוע</div><div class="chip on" data-r=month>החודש</div><div class=chip data-r=all>הכל</div></div>';}
function bindChips(reload){document.querySelectorAll("#rc .chip").forEach(function(c){c.onclick=function(){document.querySelectorAll("#rc .chip").forEach(function(x){x.classList.remove("on");});c.classList.add("on");RANGE=c.dataset.r;seenCall=0;seenSig=0;reload();};});}
function inRange(ts){var d=new Date();var start;if(RANGE=="day"){start=new Date();start.setHours(0,0,0,0);}else if(RANGE=="week"){start=new Date();start.setDate(d.getDate()-d.getDay());start.setHours(0,0,0,0);}else if(RANGE=="month"){start=new Date(d.getFullYear(),d.getMonth(),1);}else{start=new Date(d.getFullYear(),0,1);}return ts>=start.getTime()/1000;}
function periodLabel(){return RANGE=="day"?"היום":(RANGE=="week"?"השבוע":(RANGE=="month"?"החודש":"מתחילת השנה"));}

function isMulti(){return (ROLE=="admin"||ROLE=="coordinator")&&!IMP;}
function scopeLabel(){if(IMP)return ' <span class=badge>👁 צופה כ: '+esc(IMPNAME)+'</span>';return ROLE=="admin"?' <span class=badge>כל הסוכנים</span>':(ROLE=="coordinator"?' <span class=badge>הסוכנים שלי</span>':' — '+esc(NAME));}
function setImp(v){IMP=v||null;IMPNAME=null;if(IMP){var sel=$("impsel");for(var i=0;i<sel.options.length;i++){if(sel.options[i].value==IMP){IMPNAME=sel.options[i].textContent;break;}}}loadNbBanner();render();}
function loadAgents(){api("/api/agents").then(function(r){if(!r||!r.ok)return;var sel=$("impsel");r.agents.forEach(function(a){var o=document.createElement("option");o.value=a.name;o.textContent=a.name;sel.appendChild(o);});}).catch(function(){});}
var HIDDENMODE=false;
function toggleHidden(){HIDDENMODE=!HIDDENMODE;loadCalls();}
function hideCall(id){if(!id){alert("חסר מזהה");return;}api("/api/calls/hide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})}).then(function(r){if(r&&r.ok)loadCalls();else alert("הסתרה נכשלה");}).catch(function(){alert("שגיאה");});}
function unhideCall(id){if(!id)return;api("/api/calls/unhide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})}).then(function(r){if(r&&r.ok)loadCalls();else alert("שחזור נכשל");}).catch(function(){alert("שגיאה");});}
function viewCalls(){
  $("view").innerHTML='<div class=card><h2>📞 שיחות'+scopeLabel()+'</h2>'+rangeChips()+'<div class=muted id=live>טוען…</div><div style=text-align:center;margin-top:6px><span id=vphone class=vphone></span><span class=hlink id=htoggle onclick=toggleHidden()>🙈 הצג מוסתרות</span></div></div><div id=calls></div>';
  bindChips(loadCalls);seenCall=0;loadCalls();timer=setInterval(loadCalls,30000);
}
function viewSigs(){
  $("view").innerHTML='<div class=card><h2>✍️ חתימות'+scopeLabel()+'</h2>'+rangeChips()+'<div class=muted id=live>טוען…</div></div><div id=sigs></div>';
  bindChips(loadSigs);seenSig=0;loadSigs();timer=setInterval(loadSigs,30000);
}
function csumMore(el){var s=el.nextElementSibling;if(!s||!s.classList.contains("csum"))return;var hidden=s.classList.toggle("collapsed");el.textContent=hidden?"עוד — סיכום שיחה ▾":"פחות ▴";}
function callDetails(c){
  var sum=c.summary?("<span class=csummore onclick=csumMore(this)>עוד — סיכום שיחה ▾</span><div class='csum collapsed'>"+esc(c.summary)+"</div>"):"";
  if(c.clientDetails)return "<div class=cdetails><b>📋 פרטים על הלקוח</b><div>"+esc(c.clientDetails.replace(/^פרטים שנאספו על הלקוח:?\s*/,""))+"</div>"+sum+"</div>";
  if(c.summary)return "<div class=csumwrap>"+sum+"</div>";
  return "";
}
function loadCalls(){api("/api/history?"+(IMP?("as="+encodeURIComponent(IMP)+"&"):"")+(HIDDENMODE?"hidden=1":"")).then(function(r){
  if(!r.ok){relogin();return;}
  var calls=r.calls.filter(function(c){return inRange(c.ts);});
  $("live").innerHTML="🟢 חי · "+periodLabel()+" · "+calls.length+(HIDDENMODE?" מוסתרות":" שיחות");
  var ht=$("htoggle");if(ht)ht.textContent=HIDDENMODE?"↩️ חזרה לשיחות":"🙈 הצג מוסתרות";
  VPHONE=r.vphone||"";var vp=$("vphone");if(vp)vp.innerHTML=VPHONE?("🤖📞 <span class=vpnum>"+esc(VPHONE)+"</span> <span id=vpcopybtn class=vpcopy onclick=copyVphone()>📋 העתק</span>"):"";
  var maxC=calls.length?calls[0].ts:0;
  $("calls").innerHTML=(calls.length?calls.map(function(c){
    var isNew=seenCall&&c.ts>seenCall;var st=c.status=="ANSWER"?"<span class=ans>נענתה</span>":"<span class=noans>"+c.status+"</span>";
    var callerLink=c.caller?("<a href='tel:"+(c.tel||c.caller)+"'>"+c.caller+"</a>"):"-";
    var cb=c.callback?(" <a class=cbtn href='"+c.callback+"' target=_blank rel=noopener>🔁 חייג חזרה</a>"):"";
    var bsum=(c.summary||"")+(c.clientDetails?("\n"+c.clientDetails):"");
    var addb=" <button class=addbuyer data-ph=\""+esc(c.tel||c.caller||"")+"\" data-sum=\""+encodeURIComponent(bsum)+"\">➕ קונה</button>";
    var hideb=" <button class=hidecall data-id=\""+esc(c.id||"")+"\" data-act=\""+(HIDDENMODE?"unhide":"hide")+"\">"+(HIDDENMODE?"↩️ שחזר":"🙈 הסתר")+"</button>";
    return "<div class='callrow"+(isNew?" new":"")+"'>"+
      "<div class=ctop>"+st+"<span class=ctime>"+c.time+(c.duration?(" · "+c.duration+'ש׳'):"")+"</span></div>"+
      "<div class=cphone>📞 "+callerLink+"</div>"+
      (isMulti()&&c.agent?"<div class=cmeta>👤 קיבל: "+esc(c.agent)+"</div>":"")+
      callDetails(c)+
      "<div class=cbtns>"+cb+addb+hideb+"</div>"+
    "</div>";
  }).join(""):"<div class=card><div class=muted>אין שיחות בטווח.</div></div>");
  document.querySelectorAll("#calls .addbuyer").forEach(function(b){b.onclick=function(){openBuyerForm({phone:b.getAttribute("data-ph")||"",summary:decodeURIComponent(b.getAttribute("data-sum")||"")});};});
  document.querySelectorAll("#calls .hidecall").forEach(function(b){b.onclick=function(){var id=b.getAttribute("data-id");if(b.getAttribute("data-act")=="unhide")unhideCall(id);else hideCall(id);};});
  seenCall=maxC;
}).catch(function(){});}
function loadSigs(){api("/api/history"+(IMP?("?as="+encodeURIComponent(IMP)):"")).then(function(r){
  if(!r.ok){relogin();return;}
  var sigs=r.signatures.filter(function(g){return inRange(g.ts);});
  $("live").innerHTML="🟢 חי · "+periodLabel()+" · "+sigs.length+" חתימות";
  var maxS=sigs.length?sigs[0].ts:0;
  $("sigs").innerHTML="<div class=card>"+(sigs.length?sigs.map(function(g){
    var isNew=seenSig&&g.ts>seenSig;var p=(g.pct!=null)?(" · "+g.pct+"%"):"";
    return "<div class='row"+(isNew?" new":"")+"'><b>"+esc(g.type)+"</b>"+p+(g.client?" · "+esc(g.client):"")+"<div class=muted>"+esc(g.address)+(isMulti()&&g.agent?" · "+esc(g.agent):"")+" · "+g.time+"</div>"+(g.link?"<div><a class=cbtn style=background:#0D1B2A href='"+g.link+"' target=_blank rel=noopener>📄 קישור לחתימה</a></div>":"")+"</div>";
  }).join(""):"<div class=muted>אין חתימות בטווח.</div>")+"</div>";
  seenSig=maxS;
}).catch(function(){});}

function viewSearch(kind){
  var cfg={props:{t:"🏢 נכסים במשרד",ph:"דירת 4 חדרים בקרית ביאליק עד 2 מיליון",ep:"/api/search/properties"},
           excl:{t:"🏘️ נכסים בשת״פ",ph:"דירת 5 חדרים באפקה",ep:"/api/search/exclusives"},
           buyers:{t:"👤 הקונים שלי",ph:"4 חדרים תקציב 2 מיליון",ep:"/api/search/buyers"}}[kind];
  $("view").innerHTML='<div class=card><h2>'+cfg.t+'</h2><input id=sq placeholder="'+cfg.ph+'"><button onclick=doSearch("'+cfg.ep+'","'+kind+'")>חיפוש</button>'+(kind=="buyers"?' <button class=sec onclick=openBuyerForm({})>➕ הוסף קונה</button>':'')+'<div id=recent></div><div id=sres></div>'+(kind=="props"?'<div id=myprops></div>':'')+(kind=="buyers"?'<div id=mybuyers></div>':'')+'</div>';
  CUR_EP=cfg.ep;CUR_KIND=kind;
  if(kind=="props"||kind=="excl")loadRecent(kind);
  if(kind=="props")loadMyProps();
  if(kind=="buyers")loadMyBuyers();
}
function loadMyProps(){var box=$("myprops");if(!box)return;box.innerHTML="<div class=muted style=margin:8px_0>טוען את הנכסים שלך… ⏳</div>";
  api("/api/my/properties",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({as:IMP||""})}).then(function(r){
    if(!$("myprops"))return;if(!r||!r.ok){$("myprops").innerHTML="";return;}
    if(!r.results.length){$("myprops").innerHTML="<div class=muted style=margin:8px_0>לא נמצאו נכסים על שמך בגיליון המשרד.</div>";return;}
    var h="<div class=muted style=margin:12px_0_4px>🏠 הנכסים שלי במשרד ("+r.results.length+")</div>";
    h+=r.results.map(function(x){return card("props",x);}).join("");
    $("myprops").innerHTML=h;
    document.querySelectorAll("#myprops .lreq").forEach(function(b){b.onclick=function(){var id=b.getAttribute("data-id"),addr=decodeURIComponent(b.getAttribute("data-addr")||""),k=b.getAttribute("data-k");if(k=="remove"){if(confirm("לשלוח בקשה למזכירה להסיר את המודעה?\n"+addr))listingReq("remove",id,addr,"");}else{var np=prompt("מחיר חדש למודעה:\n"+addr);if(np&&np.trim())listingReq("price",id,addr,np.trim());}};});
  }).catch(function(){if($("myprops"))$("myprops").innerHTML="";});}
function listingReq(kind,id,addr,np){api("/api/listing/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:kind,id:id,address:addr,new_price:np,as:(typeof IMP!="undefined"?IMP:"")||""})}).then(function(r){if(r&&r.ok){alert("✅ הבקשה נשלחה למזכירה");loadMyProps();}else alert("שליחה נכשלה"+(r&&r.reason?" ("+r.reason+")":""));}).catch(function(){alert("שגיאה");});}
function shareApp(){var u=location.origin+"/app";var t="📲 אפליקציית RE/MAX Family\nחיפוש נכסים, קונים, בלעדיות ויצירת מצגות נדל\"ן:\n"+u;window.open("https://wa.me/?text="+encodeURIComponent(t),"_blank");}
function openBuyerForm(pf){pf=pf||{};closeBuyer();
  var ov=document.createElement("div");ov.className="ovl";ov.id="buyerovl";
  ov.innerHTML='<div class=ovlbox><h3 style=margin:0_0_8px>➕ הוספת קונה</h3>'+
    '<input id=bf_name placeholder="שם הלקוח">'+
    '<input id=bf_phone placeholder="טלפון">'+
    '<input id=bf_budget placeholder="תקציב (למשל 2,000,000)">'+
    '<textarea id=bf_sum rows=6 placeholder="סיכום השיחה — ניתן לערוך"></textarea>'+
    '<div class=ovlbtns><button class=gold onclick=saveBuyer()>שמירה</button><button class=sec onclick=closeBuyer()>ביטול</button></div>'+
    '<div id=bf_msg class=muted></div></div>';
  ov.onclick=function(e){if(e.target===ov)closeBuyer();};
  document.body.appendChild(ov);
  $("bf_name").value=pf.name||"";$("bf_phone").value=pf.phone||"";$("bf_budget").value=pf.budget||"";$("bf_sum").value=pf.summary||"";
  $("bf_name").focus();
}
function closeBuyer(){var o=$("buyerovl");if(o)o.remove();}
function saveBuyer(){
  var body={name:$("bf_name").value.trim(),phone:$("bf_phone").value.trim(),budget:$("bf_budget").value.trim(),summary:$("bf_sum").value.trim(),as:(typeof IMP!="undefined"?IMP:"")||""};
  if(!body.name&&!body.phone&&!body.summary){$("bf_msg").innerHTML="<span class=err>יש למלא לפחות שדה אחד</span>";return;}
  $("bf_msg").textContent="שומר… ⏳";
  api("/api/buyers/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(r){
    if(!r||!r.ok){$("bf_msg").innerHTML="<span class=err>שמירה נכשלה"+(r&&r.reason?" ("+esc(r.reason)+")":"")+"</span>";return;}
    closeBuyer();if(TABNOW=="buyers"&&typeof loadMyBuyers=="function")loadMyBuyers();alert("✅ הקונה נשמר");
  }).catch(function(){$("bf_msg").innerHTML="<span class=err>שגיאה</span>";});
}
function loadMyBuyers(){var box=$("mybuyers");if(!box)return;box.innerHTML="<div class=muted style=margin:8px_0>טוען קונים… ⏳</div>";
  api("/api/my/buyers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({as:(typeof IMP!="undefined"?IMP:"")||""})}).then(function(r){
    if(!$("mybuyers"))return;if(!r||!r.ok){$("mybuyers").innerHTML="";return;}
    if(!r.results.length){$("mybuyers").innerHTML="<div class=muted style=margin:8px_0>אין קונים שמורים עדיין. הוסף קונה משיחה (➕ קונה) או בכפתור למעלה.</div>";return;}
    var h="<div class=muted style=margin:12px_0_4px>👤 הקונים שלי ("+r.results.length+")</div>";
    h+=r.results.map(function(x){return buyerCard(x);}).join("");
    $("mybuyers").innerHTML=h;
    document.querySelectorAll("#mybuyers .bsearch").forEach(function(b){b.onclick=function(){buyerSearch(b);};});
  }).catch(function(){if($("mybuyers"))$("mybuyers").innerHTML="";});}
function buyerCard(x){
  var ph=x.phone?("<a href='tel:"+(x.tel||x.phone)+"'>"+esc(x.phone)+"</a>"):"";
  var n=BSEQ++,sid="bs"+n,rid="br"+n;
  var meta=[(ph?"📞 "+ph:""),(x.wa?"<a href='https://wa.me/"+x.wa+"' target=_blank>וואטסאפ</a>":""),(x.date?"📅 "+esc(x.date):""),((isMulti()&&x.agent)?"👤 "+esc(x.agent):"")].filter(Boolean).join(" · ");
  var q=encodeURIComponent(((x.budget||"")+" "+(x.summary||"")).trim().slice(0,800));
  return "<div class='row buyerrow'>"+
    "<div class=bhead><span class=btag>👤 קונה</span> <b class=bname>"+esc(x.name||"ללא שם")+"</b>"+(x.budget?"<span class=bbudget>💰 "+esc(x.budget)+"</span>":"")+"<button class=bdel onclick=\"delBuyer('"+esc(String(x.row||""))+"')\" title='מחק קונה'>🗑</button></div>"+
    (meta?"<div class=muted bmeta>"+meta+"</div>":"")+
    (x.summary?("<div class=bsum id="+sid+">"+esc(x.summary)+"</div><span class=bmore onclick=\"var e=document.getElementById('"+sid+"');e.classList.toggle('open');this.textContent=e.classList.contains('open')?'הצג פחות':'הצג עוד';\">הצג עוד</span>"):"")+
    "<input class=bqedit id=q"+n+" value=\""+esc(x.search||"").replace(/\"/g,"&quot;")+"\" placeholder=\"חידוד חיפוש (לא חובה): למשל 4 חדרים קרית ביאליק עד 2 מיליון\">"+
    "<div class=bbtns><button class=bsearch data-k=props data-q=\""+q+"\" data-e=q"+n+" data-row=\""+esc(String(x.row||""))+"\" data-r=\""+rid+"\">🏢 חפש במשרד</button><button class=bsearch data-k=excl data-q=\""+q+"\" data-e=q"+n+" data-row=\""+esc(String(x.row||""))+"\" data-r=\""+rid+"\">🏘️ חפש בשת״פ</button></div>"+
    "<div id="+rid+" class=bresults></div>"+
    "</div>";
}
var BSEQ=0;
function delBuyer(row){
  if(!row){alert("לא ניתן למחוק (חסר מזהה)");return;}
  if(!confirm("למחוק את הקונה לצמיתות?"))return;
  api("/api/buyers/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({row:row})}).then(function(r){
    if(!r||!r.ok){alert("מחיקה נכשלה"+(r&&r.reason?" ("+r.reason+")":""));return;}
    if(typeof loadMyBuyers=="function")loadMyBuyers();
  }).catch(function(){alert("שגיאה");});
}
function buyerSearch(b){
  var kind=b.getAttribute("data-k"),rid=b.getAttribute("data-r");
  var ein=document.getElementById(b.getAttribute("data-e")||"");
  var refine=ein&&ein.value.trim();
  var base=decodeURIComponent(b.getAttribute("data-q")||"");
  var q=refine?(base+"\n\n*** דגש/חידוד מהסוכן (עדיפות גבוהה — גובר על הסיכום שלמעלה): "+refine+" *** אם לא צוין כאן תקציב חדש, השאר את התקציב מהסיכום."):base;
  var box=document.getElementById(rid);if(!box)return;
  var rw=b.getAttribute("data-row");
  if(refine&&rw){api("/api/buyers/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({row:rw,search:refine})}).catch(function(){});}
  var ep=kind=="props"?"/api/search/properties":"/api/search/exclusives";
  box.innerHTML="<div class=muted style=margin:6px_0>מחפש "+(kind=="props"?"במשרד":"בשת״פ")+"… ⏳</div>";
  api(ep,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({q:q,as:(typeof IMP!="undefined"?IMP:"")||"",nosave:true})}).then(function(r){
    if(!box)return;
    if(!r||!r.ok){box.innerHTML="<span class=err>שגיאה בחיפוש"+(r&&r.reason?" ("+esc(r.reason)+")":"")+"</span>";return;}
    if(!r.results.length){box.innerHTML="<div class=muted style=margin:6px_0>לא נמצאו נכסים תואמים "+(kind=="props"?"במשרד":"בשת״פ")+".</div>";return;}
    var h="<div class=bresh>"+(kind=="props"?"🏢 נכסים במשרד":"🏘️ נכסים בשת״פ")+" ("+r.results.length+")"+(r.summary?" · "+esc(r.summary):"")+"</div>";
    h+=r.results.map(function(y){return card(kind,y);}).join("");
    box.innerHTML=h;
  }).catch(function(){if(box)box.innerHTML="<span class=err>שגיאה</span>";});
}
function loadRecent(kind){api("/api/recent?kind="+kind).then(function(r){
  var box=$("recent");if(!box)return;
  if(!r||!r.ok||!r.items.length){box.innerHTML="";return;}
  box.innerHTML="<div class=muted style=margin:6px_0>חיפושים אחרונים:</div><div id=rchips class=rchips></div>";
  var c=$("rchips");
  r.items.forEach(function(q){var sp=document.createElement("span");sp.className="rchip";sp.textContent=q;sp.onclick=function(){$("sq").value=q;doSearch(CUR_EP,CUR_KIND);};c.appendChild(sp);});
}).catch(function(){});}
function doSearch(ep,kind){
  var q=$("sq").value.trim();$("sres").innerHTML="<div class=muted>מחפש… ⏳</div>";
  api(ep,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({q:q,as:IMP||""})}).then(function(r){
    if(!r.ok){if(r.auth===false){relogin();return;}$("sres").innerHTML="<span class=err>שגיאה בשרת: "+esc(r.reason||"")+"</span>";return;}
    if(!r.results.length){$("sres").innerHTML="<div class=muted>לא נמצאו תוצאות. נסה עם פחות פרטים.</div>";return;}
    var h=r.summary?("<div class=muted style=margin:6px_0>"+esc(r.summary)+"</div>"):"";
    h+=r.results.map(function(x){return card(kind,x);}).join("");
    $("sres").innerHTML=h;
    if(kind=="props"||kind=="excl")loadRecent(kind);
  }).catch(function(){$("sres").innerHTML="<span class=err>שגיאה</span>";});
}
function card(kind,x){
  if(kind=="props"){return "<div class=row>"+((x.score!==undefined&&x.score!=="")?"<span class=score>"+x.score+"%</span>":"")+"<b>"+esc(x.type||"נכס")+"</b> · "+esc(x.address)+(x.neighborhood?" — "+esc(x.neighborhood):"")+", "+esc(x.city)+
    "<div class=muted>"+[x.rooms?x.rooms+" חד׳":"",x.size?x.size+' מ״ר':"",x.floor?"קומה "+x.floor:"",x.price,x.date?"📅 "+x.date:""].filter(Boolean).join(" · ")+"</div>"+
    (x.agent?"<div>👤 "+esc(x.agent)+(x.wa?" · <a href='https://wa.me/"+x.wa+"' target=_blank>וואטסאפ</a>":"")+"</div>":"")+(x.own?("<div class=lbtns>"+(x.pending?"<span class=lpend>🔧 בטיפול אצל המזכירה</span>":("<button class=lreq data-k=remove data-id=\""+esc(x.id||"")+"\" data-addr=\""+encodeURIComponent(x.address||"")+"\">🗑 הסר מודעה</button> <button class=lreq data-k=price data-id=\""+esc(x.id||"")+"\" data-addr=\""+encodeURIComponent(x.address||"")+"\">💰 עדכן מחיר</button>"))+"</div>"):"")+"</div>";}
  if(kind=="excl"){return "<div class=row><span class=score>"+x.score+"%</span><b>"+esc(x.street)+"</b><div class=muted>"+esc(x.dest)+"</div>"+
    (x.desc?"<div>"+esc(x.desc)+"</div>":"")+"<div class=muted>"+[x.price?esc(x.price):"",(x.office?(isOurOffice(x.office)?"<span class=ouroffice>🏠 "+esc(x.office)+"</span>":esc(x.office)):""),x.date?esc(x.date):""].filter(Boolean).join(" · ")+"</div>"+
    (x.link?"<div><a class=cbtn style=background:#0D1B2A href='"+x.link+"' target=_blank rel=noopener>🔗 נדל\"ן וואן</a></div>":"")+"</div>";}
  var ph=x.phone?("<a href='tel:"+(x.tel||x.phone)+"'>"+esc(x.phone)+"</a>"):"-";
  return "<div class=row>📞 <b>"+ph+"</b>"+(x.wa?" · <a href='https://wa.me/"+x.wa+"' target=_blank>וואטסאפ</a>":"")+
    (x.agent?" · 👤 קיבל: "+esc(x.agent):"")+
    "<div class=muted>"+[x.date,x.budget].filter(Boolean).map(esc).join(" · ")+"</div>"+(x.summary?"<div>"+esc(x.summary)+"</div>":"")+"</div>";
}
function relogin(){try{localStorage.removeItem("fbTok");}catch(e){}location.reload();}
function toggleMenu(e){if(e){e.stopPropagation();}var m=$("appmenu");if(m)m.classList.toggle("hidden");}
function closeMenu(){var m=$("appmenu");if(m)m.classList.add("hidden");}
function menuGo(t){closeMenu();tab(t);}
document.addEventListener("click",function(e){var m=$("appmenu");if(m&&!m.classList.contains("hidden")&&!e.target.closest(".menuwrap"))closeMenu();});
function logout(){if(!confirm("להתנתק מהמערכת?"))return;try{localStorage.removeItem("fbTok");localStorage.removeItem("fbRole");localStorage.removeItem("fbName");}catch(e){}location.reload();}
var NBDATA=null;
function nbAs(){return IMP?("?as="+encodeURIComponent(IMP)):"";}
function loadNbBanner(){var b=$("nbtabbadge");if(!b)return;
  api("/api/newborn"+nbAs()).then(function(r){
    if(!r||!r.ok)return;NBDATA=r;
    if(r.count>0){b.textContent=r.count;b.classList.remove("hidden");}else{b.classList.add("hidden");}
  }).catch(function(){});}
function openNewborn(){
  api("/api/newborn"+nbAs()).then(function(r){
    if(!r||!r.ok)return;NBDATA=r;
    var rows=(r.results||[]).slice(0,20).map(function(x){
      if(x.released){
        return "<div class=row><b>🏠 "+esc(x.address||x.city||"נכס")+"</b>"+(x.city&&x.address?", "+esc(x.city):"")+(x.own?" <span class=badge>שלי</span>":"")+
          (x.desc?"<div>"+esc(x.desc)+"</div>":"")+
          "<div class=muted>"+[x.price,x.date?"📅 "+x.date:""].filter(Boolean).join(" · ")+"</div>"+
          (x.notes?"<div class=muted>"+esc(x.notes)+"</div>":"")+
          ((x.owner||x.phone)?"<div>👤 "+esc(x.owner||"בעל הנכס")+(x.wa?" · <a href='https://wa.me/"+x.wa+"' target=_blank rel=noopener onclick=\"nbWa('"+encodeURIComponent(x.key||'')+"','"+encodeURIComponent(x.address||'')+"')\">וואטסאפ</a>":(x.phone?" · <a href='tel:"+esc(x.phone)+"'>"+esc(x.phone)+"</a>":""))+"</div>":"")+
          (x.contacted&&x.contacted.length?"<div class=nbcontact>📲 כבר פנו: "+x.contacted.map(esc).join(", ")+"</div>":"")+
          (x.link?"<div><a class=cbtn style=background:#0D1B2A href='"+esc(x.link)+"' target=_blank rel=noopener>🔗 פרטים</a></div>":"")+"</div>";
      }
      return "<div class='row nblock'>🔒 <b>נכס חדש"+(x.city?" ב"+esc(x.city):"")+"</b>"+(x.type?" · "+esc(x.type):"")+"<div class=muted>ייחשף עבורך בעוד "+x.release_in+" ימים</div></div>";
    }).join("");
    if(!rows)rows="<div class=muted>אין נכסים זמינים עבורך כרגע.</div>";
    $("nbmodal").innerHTML="<div class=nbcard><div class=nbhead><h2 style=margin:0>🐣 נכס נולד</h2><button class=nbx onclick=closeNewborn()>✕</button></div>"+rows+"</div>";
    $("nbmodal").classList.remove("hidden");
    nbLock(true);
  }).catch(function(){});}
var _nbScrollY=0;
function nbLock(on){var b=document.body;if(on){_nbScrollY=window.scrollY||window.pageYOffset||0;b.style.position="fixed";b.style.top=(-_nbScrollY)+"px";b.style.left="0";b.style.right="0";b.style.width="100%";}else{b.style.position="";b.style.top="";b.style.left="";b.style.right="";b.style.width="";window.scrollTo(0,_nbScrollY);}}
function closeNewborn(){$("nbmodal").classList.add("hidden");nbLock(false);}
var VPHONE="";
function copyVphone(){if(!VPHONE)return;var b=$("vpcopybtn");var ok=function(){if(b){var t=b.innerHTML;b.innerHTML="✓ הועתק";setTimeout(function(){b.innerHTML=t;},1500);}};
  try{if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(VPHONE).then(ok,function(){vpFallbackCopy(VPHONE);ok();});return;}}catch(e){}
  vpFallbackCopy(VPHONE);ok();}
function vpFallbackCopy(t){try{var ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.focus();ta.select();document.execCommand("copy");document.body.removeChild(ta);}catch(e){}}
function nbWa(k,a){try{k=decodeURIComponent(k||"");a=decodeURIComponent(a||"");api("/api/newborn/contact",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,addr:a,as:IMP||""})}).catch(function(){});}catch(e){}return true;}
function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function isOurOffice(o){var t=String(o||"").toLowerCase().replace(/[\s\/\\.\-_'"׳״]/g,"");var rmx=t.indexOf("remax")>-1||t.indexOf("רימקס")>-1||t.indexOf("רמקס")>-1;var fam=t.indexOf("family")>-1||t.indexOf("פמילי")>-1||t.indexOf("פמלי")>-1;return rmx&&fam;}
</script></div></body></html>'''

# ══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    log.info("Installing dependencies...")
    install_deps()
    log.info(f"Bot starting — trigger word: '{TRIGGER_WORD}'")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
