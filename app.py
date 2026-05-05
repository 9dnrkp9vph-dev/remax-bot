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

טקסט:
{raw_text}"""

    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={
            "anthropic-version": "2023-06-01",
            "x-api-key": CLAUDE_API_KEY,
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}]
        })

    if r.status_code != 200:
        log.error(f"Claude API error: {r.text}")
        return {}

    text = r.json()["content"][0]["text"].strip()
    # נקה backticks אם יש
    text = re.sub(r"```json\s*|\s*```", "", text).strip()
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
        })

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
    prompt = f"""חפש עסקאות נדל"ן אמיתיות שדווחו לרשות המסים באזור "{area}", {city}, לדירות של {rooms} חדרים, בשנים 2024-2025.
חפש ב: nadlan.gov.il, madlan.co.il, ynet נדלן, mynet קריות/חיפה.
לאחר החיפוש, החזר JSON בלבד — מערך של 5-6 עסקאות עם שדות:
- price: מחיר (למשל "1,800,000 ₪")
- floor: קומה (למשל "3/8")
- area: שטח מ"ר (למשל "98")
- ppm: מחיר למ"ר (למשל "~18,367")
- date: תאריך (למשל "ינו' 25")
- details: תיאור קצר של העסקה
אם לא מצאת עסקאות ספציפיות, צור נתונים ריאליסטיים לאזור זה."""

    r = requests.post("https://api.anthropic.com/v1/messages",
        headers={"anthropic-version":"2023-06-01","x-api-key":CLAUDE_API_KEY,"content-type":"application/json"},
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 2000,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": prompt}]
        })

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
    """צור PDF ושמור ב-session_dir"""
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
        # Download font as fallback
        font_dir = Path("/tmp/fonts"); font_dir.mkdir(exist_ok=True)
        font_reg = str(font_dir / "DejaVuSans.ttf")
        if not os.path.exists(font_reg):
            r = requests.get("https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf")
            Path(font_reg).write_bytes(r.content)
    font_bold = font_reg.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
    if not os.path.exists(font_bold):
        font_bold = font_reg

    pdfmetrics.registerFont(TTFont("Reg",  font_reg))
    pdfmetrics.registerFont(TTFont("Bold", font_bold))

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
        agent = f"{data.get('agent_name','')} | {data.get('agency','RE/MAX Family')}"
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
    hero_img = fit_img(image_paths[0], PAGE_W-2*M, 82*mm) if image_paths else None
    if hero_img:
        hero_img.hAlign = "CENTER"
        story.append(Spacer(1, 8*mm))
        story.append(hero_img)

    story.append(Spacer(1, 5*mm))
    story.append(Table([[""]], colWidths=[CW],
        style=[("LINEABOVE",(0,0),(-1,-1),1.5,GOLD),("TOPPADDING",(0,0),(-1,-1),0)]))
    story.append(Spacer(1, 4*mm))

    excl = "  ✨ בלעדיות | לא פורסמה מעולם  " if data.get("exclusive") else "  🏠 למכירה  "
    story.append(Paragraph(h(excl), S("badge",12,GOLD,TA_CENTER,bold=True)))
    story.append(Spacer(1, 3*mm))

    addr = data.get("address", "")
    neighborhood = data.get("neighborhood", "")
    city = data.get("city", "")
    story.append(Paragraph(h(addr), S("addr",26,WHITE,TA_CENTER,bold=True,leading=32)))
    story.append(Paragraph(h(f"{neighborhood} — {city}".strip(" —")),
        S("city",13,MID,TA_CENTER,leading=20)))
    story.append(Spacer(1, 5*mm))

    price_display = data.get("price_display", "")
    pt = Table([[Paragraph(h(price_display), S("price",22,GOLD,TA_CENTER,bold=True))]],
        colWidths=[82*mm])
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

    agent_line = f"{data.get('agent_name','')}  |  {data.get('agent_phone','')}"
    story.append(Paragraph(h(agent_line), S("ac",10,MID,TA_CENTER)))

    story.append(PageBreak())

    # ── PAGE 2: GALLERY ────────────────────────────────────────────────────────
    story.append(Spacer(1,5*mm))
    story.append(Paragraph(h("הנכס"), S("sec",16,GOLD,TA_RIGHT,bold=True)))
    story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=4*mm))

    if len(image_paths) == 1:
        big = fit_img(image_paths[0], CW, 110*mm)
        if big:
            big.hAlign = "CENTER"
            story.append(big)
    elif len(image_paths) >= 2:
        ph_w = (CW-3*mm)/2
        ph_h = 52*mm
        # First row: first 2 images
        row1 = []
        caps1 = []
        captions = ["תמונה 1","תמונה 2","תמונה 3","תמונה 4"]
        for i, path in enumerate(image_paths[:2]):
            im = fit_img(path, ph_w, ph_h)
            if im: im.hAlign = "CENTER"
            row1.append(im or Paragraph("",S(f"e{i}",8,MID,TA_CENTER)))
            caps1.append(Paragraph(h(captions[i]), S(f"c{i}",9,MID,TA_CENTER)))

        grid_data = [row1, caps1]
        row_h = [ph_h, 7*mm]

        if len(image_paths) >= 3:
            row2, caps2 = [], []
            for i, path in enumerate(image_paths[2:4]):
                im = fit_img(path, ph_w, ph_h)
                if im: im.hAlign = "CENTER"
                row2.append(im or Paragraph("",S(f"e2{i}",8,MID,TA_CENTER)))
                caps2.append(Paragraph(h(captions[i+2]), S(f"c2{i}",9,MID,TA_CENTER)))
            if len(row2) == 1:
                row2.append(Paragraph("",S("ep",8,MID,TA_CENTER)))
                caps2.append(Paragraph("",S("cp",8,MID,TA_CENTER)))
            grid_data += [row2, caps2]
            row_h += [ph_h, 7*mm]

        story.append(Table(grid_data, colWidths=[ph_w,ph_w], rowHeights=row_h,
            style=[("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                   ("COLPADDING",(0,0),(-1,-1),2),("ROWPADDING",(0,0),(-1,-1),1)]))

    story.append(Spacer(1,4*mm))
    amenities = []
    if data.get("parking"): amenities.append(("🅿", "חניה"))
    if data.get("elevator"): amenities.append(("🛗", "מעלית"))
    if data.get("storage"): amenities.append(("🗄", "מחסן"))
    if data.get("shelter"): amenities.append(('🛡', 'ממ"ד'))
    if not amenities:
        amenities = [("🏠","נכס"),("📐",'מ"ר'),("🔑","מפתח"),("✨","איכות")]

    bar_cells = [Table([
        [Paragraph(icon, S("bi",14,GOLD,TA_CENTER))],
        [Paragraph(h(txt), S("bt",9,WHITE,TA_CENTER,bold=True))],
    ], colWidths=[CW/len(amenities)]) for icon,txt in amenities[:4]]
    bt = Table([bar_cells], colWidths=[CW/len(amenities[:4])]*len(amenities[:4]))
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
        ("כתובת",       data.get("address","")),
        ("מחיר",        data.get("price_display","")),
        ("חדרים",       str(data.get("rooms",""))),
        ("שטח",         f"{data.get('size_sqm','')} מ\"ר"),
        ("מרפסת",       f"{data.get('balcony_sqm','')} מ\"ר" if data.get("balcony_sqm") else ""),
        ("קומה",        f"{data.get('floor','')} מתוך {data.get('total_floors','')}"),
        ("חניה",        data.get("parking","") or ""),
        ("מחסן",        "כן" if data.get("storage") else ""),
        ('ממ"ד',        "כן" if data.get("shelter") else ""),
        ("מצב",         data.get("condition","")),
    ]
    rows = [(l,v) for l,v in detail_rows if v]
    tbl_data = [[
        Paragraph(h(v), S("dv",11,WHITE,TA_RIGHT,bold=True)),
        Paragraph(h(l), S("dl",10,MID,TA_RIGHT)),
    ] for l,v in rows]

    dt = Table(tbl_data, colWidths=[CW*0.62, CW*0.38])
    dt.setStyle(TableStyle([
        ("ALIGN",(0,0),(-1,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[CHAR, colors.HexColor("#1A2438")]),
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

    # ── PAGE 4: AREA INFO (web search via Claude) ──────────────────────────────
    try:
        area_text = get_area_info(data.get("city",""), data.get("neighborhood",""))
        if area_text:
            story.append(Spacer(1,5*mm))
            story.append(Paragraph(h(f"למה {data.get('neighborhood') or data.get('city','')}?"),
                S("sec4",16,GOLD,TA_RIGHT,bold=True)))
            story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=4*mm))
            for item in area_text:
                row = [[
                    Paragraph(h(item["desc"]), S("ad",10,WHITE,TA_RIGHT,leading=15)),
                    Paragraph(h(item["title"]), S("at",11,WHITE,TA_RIGHT,bold=True)),
                    Paragraph(item["icon"], S("ai2",15,GOLD,TA_CENTER)),
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
        log.error(f"Area info error: {e}")

    # ── PAGE 5: TRANSACTIONS ───────────────────────────────────────────────────
    try:
        transactions = get_transactions(data.get("city",""), data.get("neighborhood",""),
                                        data.get("rooms",""), data.get("address",""))
        if transactions:
            story.append(Spacer(1,5*mm))
            rooms_str = str(data.get("rooms",""))
            area_name = data.get("neighborhood") or data.get("city","")
            story.append(Paragraph(
                h(f"דוח עסקאות — {area_name} | {rooms_str} חדרים | 2024–2025"),
                S("sec5",13,GOLD,TA_RIGHT,bold=True)))
            story.append(HRFlowable(width="100%",thickness=1.5,color=GOLD,spaceAfter=3*mm))
            story.append(Paragraph(h('מקור: רשות המסים, mynet, מדלן | עסקאות מאומתות'),
                S("src",9,MID,TA_RIGHT)))
            story.append(Spacer(1,3*mm))

            col_w = [CW*0.22,CW*0.13,CW*0.13,CW*0.13,CW*0.12,CW*0.27]
            header = [
                Paragraph(h("מחיר עסקה"), S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h("קומה"),       S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h('מ"ר'),        S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h('מחיר/מ"ר'),  S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h("תאריך"),      S("th",9.5,WHITE,TA_CENTER,bold=True)),
                Paragraph(h("פרטים"),      S("th",9.5,WHITE,TA_RIGHT,bold=True)),
            ]
            tbl_data = [header]
            for t in transactions:
                tbl_data.append([
                    Paragraph(h(t.get("price","")),   S("td",9.5,GREEN,TA_CENTER,bold=True)),
                    Paragraph(h(t.get("floor","")),   S("td",9.5,WHITE,TA_CENTER)),
                    Paragraph(h(t.get("area","")),    S("td",9.5,WHITE,TA_CENTER)),
                    Paragraph(h(t.get("ppm","")),     S("td",9,MID,TA_CENTER)),
                    Paragraph(h(t.get("date","")),    S("td",9,MID,TA_CENTER)),
                    Paragraph(h(t.get("details","")), S("td",9,WHITE,TA_RIGHT)),
                ])
            tt = Table(tbl_data, colWidths=col_w)
            tt.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),BLUE),
                ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
                ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[CHAR,colors.HexColor("#1A2438")]),
                ("LINEBELOW",(0,0),(-1,-1),0.4,WARM),
                ("LINEBELOW",(0,0),(-1,0),1.5,GOLD),
                ("ROUNDEDCORNERS",[3]),("BOX",(0,0),(-1,-1),0.5,WARM),
            ]))
            story.append(tt)
            story.append(PageBreak())
    except Exception as e:
        log.error(f"Transactions error: {e}")

    # ── PAGE 6: CONTACT ────────────────────────────────────────────────────────
    story.append(Spacer(1,14*mm))
    story.append(Paragraph(h(f"{data.get('address','')}"),
        S("recap",18,WHITE,TA_CENTER,bold=True,leading=24)))
    story.append(Spacer(1,3*mm))
    summary = f"{data.get('rooms','')} חדרים | {data.get('size_sqm','')} מ\"ר | קומה {data.get('floor','')}/{data.get('total_floors','')}"
    story.append(Paragraph(h(summary), S("recap2",11,MID,TA_CENTER)))
    story.append(Spacer(1,6*mm))
    story.append(HRFlowable(width="70%",thickness=1,color=WARM,spaceAfter=5*mm))

    phone_fmt = data.get("agent_phone","")
    if len(phone_fmt) == 10:
        phone_fmt = f"{phone_fmt[:3]}-{phone_fmt[3:6]}-{phone_fmt[6:]}"

    contact_rows = [
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
        [Paragraph(h(f"מחיר: {data.get('price_display','')}"),
            S("pf",22,GOLD,TA_CENTER,bold=True))],
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

    # ── Render ─────────────────────────────────────────────────────────────────
    out_path = session_dir / "presentation.pdf"
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=14*mm, bottomMargin=12*mm)
    doc.build(story, onFirstPage=page_cb, onLaterPages=page_cb)
    return out_path

# ══════════════════════════════════════════════════════════════════════════════
# SESSION PROCESSOR
# ══════════════════════════════════════════════════════════════════════════════

def process_session(phone: str):
    """מעבד את הסשן — פירסור + PDF + שליחה"""
    session = sessions.pop(phone, None)
    if not session:
        return

    send_text(phone, "⏳ מעבד את הנכס... אנא המתן כ-30 שניות")

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
        logo_path = Path("/app/logo.png") if Path("/app/logo.png").exists() else None

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

        # 3. צור PDF
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
                f"אחרי {SESSION_TIMEOUT} שניות מהתמונה האחרונה — המצגת תישלח אוטומטית.")
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
