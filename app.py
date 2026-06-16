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
            if name and name not in ("שם מלא", "משרד", "משרד ביאליק", "רישיון תיווך"):
                out[_norm_name(name)] = {"name": name, "phone": phone, "license": lic}
        _agents_full_cache["data"] = out
        _agents_full_cache["ts"] = time.time()
        return out
    except Exception as e:
        log.error(f"agents full error: {e}")
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
            d = dict(zip(headers_row, row_padded))
            # תיאור הנכס מעמודה AE (אינדקס 30) — לתצוגת "עוד" בכרטיס
            if len(row_padded) > 30:
                d["_desc_ae"] = str(row_padded[30] or "").strip()
            rows.append(d)
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
    if _external_excl_cache["data"] is not None and (time.time() - _external_excl_cache["ts"]) < 300:
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
    "505709865": "1324",   # אייל שמול — קוד קבוע, בלי SMS
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

def _load_config():
    """קונפיג מערכת (dict) מטאב 'config' ב-Apps Script. מטמון 60ש'. ריק=ברירת מחדל."""
    c = _cache_get("app_config", 60)
    if c is not None: return c
    with _sf_lock("app_config"):
        c = _cache_get("app_config", 60)
        if c is not None: return c
        cfg = {}
        try:
            j = _buyers_apps_post("getconfig", {})
            if j and j.get("ok"):
                raw = (j.get("config") or "").strip()
                if raw: cfg = _json.loads(raw)
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict): cfg = {}
        _cache_put("app_config", cfg)
        return cfg

def _save_config(cfg):
    """כתיבת הקונפיג חזרה ל-Apps Script. מעדכן מטמון בהצלחה."""
    try:
        j = _buyers_apps_post("setconfig", {"config": _json.dumps(cfg, ensure_ascii=False)})
        ok = bool(j and j.get("ok"))
        if ok:
            _cache_put("app_config", cfg)
            _cache_clear("alias_key_map")
            _cache_clear("newborn_delays")
        return ok
    except Exception:
        return False

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

def _canon_key(name):
    """מפתח התאמה קנוני: name_key אחרי מיפוי כינויים (אם הוגדרו בקונפיג)."""
    k = _name_key(name)
    return _alias_key_map().get(k, k)

# ── תפקידים (6) → היקף נתונים + טאבים. קונפיג ריק = התנהגות נוכחית מדויקת. ──────
_ROLE_SCOPE = {"developer": "admin", "manager": "admin", "accountant": "admin",
               "secretary": "admin", "coordinator": "coordinator", "agent": "agent"}
_ALL_TABS = ["calls", "buyers", "sigs", "props", "excl", "newborn", "report", "activity"]

def _resolve_roles(last9):
    """מחזיר (scope_role, display_role). scope ל-data (admin/coordinator/agent), display ל-UI/טאבים.
    אם אין תפקיד בקונפיג — נופל בדיוק להתנהגות הקיימת (web_role_for)."""
    disp = (_load_config().get("roles") or {}).get(last9)
    if disp in _ROLE_SCOPE:
        return _ROLE_SCOPE[disp], disp
    base = web_role_for(last9) or "agent"
    return base, {"admin": "manager", "coordinator": "coordinator", "agent": "agent"}.get(base, "agent")

def _tabs_for_role(drole):
    """רשימת הטאבים הגלויים לתפקיד. ללא הגדרה בקונפיג = כל הטאבים (אפס שינוי)."""
    perms = (_load_config().get("rolePerms") or {}).get(drole)
    if perms and isinstance(perms.get("tabs"), list):
        return [t for t in perms["tabs"] if t in _ALL_TABS]
    return list(_ALL_TABS)

def _login_name(phone, scope, drole):
    if drole == "coordinator" and phone in _COORDINATORS:
        return _COORDINATORS[phone]["name"]
    if scope == "admin" and drole in ("manager", "developer"):
        return "מנהל"
    return web_contacts_phone_name().get(phone) or web_phone_name_map().get(phone) or ("מנהל" if scope == "admin" else "סוכן")

def _team_for(name):
    """צוות הסוכן: (phones:set, keys:set) של כל החברים כולל עצמו. None אם אין צוות.
    אדיטיבי — חל רק אם הסוכן חבר בצוות שהוגדר בקונפיג."""
    ck = _canon_key(name)
    if not ck: return None
    for grp in (_load_config().get("teams") or []):
        if not isinstance(grp, list): continue
        gkeys = set(_canon_key(m) for m in grp if m)
        if ck in gkeys:
            phones = set(); keys = set()
            for m in grp:
                k = _canon_key(m)
                if k: keys.add(k)
                for ph in _phones_for_name(m):
                    if ph: phones.add(ph)
            return phones, keys
    return None

def _row_owned(row, keys, phones):
    """האם שורת נכס שייכת לאחד מחברי הצוות (שם קנוני או טלפון)."""
    for col in ("סוכן 1", "סוכן 2"):
        if _canon_key(row.get(col, "")) in keys: return True
    if phones:
        for col in ("טלפון 1", "טלפון 2", "טלפון"):
            ph = _last9(row.get(col, ""))
            if ph and ph in phones: return True
    return False

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
    c = _cache_get(_ck, 60)
    if c is not None:
        return c
    with _sf_lock(_ck):
        c = _cache_get(_ck, 60)   # בדיקה כפולה — אולי חוט אחר כבר מילא בזמן ההמתנה
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
        scope, drole = _resolve_roles(phone)
        if not scope: scope = "admin"
        if _is_dev(phone): scope = "admin"; drole = "developer"
        role = scope
        name = _login_name(phone, scope, drole)
        token = _secrets.token_urlsafe(24)
        sess = {"phone": phone, "role": role, "drole": drole, "name": name, "exp": time.time() + _SESS_TTL}
        if _is_dev(phone): sess["dev"] = True
        if role == "coordinator" and phone in _COORDINATORS:
            sess["agents"] = list(_COORDINATORS[phone]["agents"])
            sess["agent_names"] = list(_COORDINATORS[phone]["names"])
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
    token = _secrets.token_urlsafe(24)
    sess = {"phone": phone, "role": role, "drole": drole, "name": name, "exp": time.time() + _SESS_TTL}
    if _is_dev(phone): sess["dev"] = True
    if role == "coordinator" and phone in _COORDINATORS:
        sess["agents"] = list(_COORDINATORS[phone]["agents"])
        sess["agent_names"] = list(_COORDINATORS[phone]["names"])
    _web_sessions[token] = sess
    _log_activity(name, sess["role"], phone, "כניסה")
    return jsonify({"ok": True, "token": token, "role": role, "drole": drole, "name": name, "dev": sess.get("dev", False), "tabs": _tabs_for_role(drole)})

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
    if _scope == "coordinator" and _last9(phone) in _COORDINATORS:
        sess["agents"] = list(_COORDINATORS[_last9(phone)]["agents"])
        sess["agent_names"] = list(_COORDINATORS[_last9(phone)]["names"])
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
    def _scan(names):
        cnt = {}
        for nm in names:
            nm = (nm or "").strip()
            if nm: cnt[nm] = cnt.get(nm, 0) + 1
        out = [{"name": nm, "count": c} for nm, c in cnt.items() if _name_key(nm) not in known_keys]
        out.sort(key=lambda x: -x["count"])
        return out
    sig_names = [g.get("agent", "") for g in get_signings()]
    list_names = []
    for r in fetch_sheet_rows():
        list_names.append(r.get("סוכן 1", "")); list_names.append(r.get("סוכן 2", ""))
    agents = []
    for v in sorted(known.values(), key=lambda x: x["name"]):
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
                       "nbDelay": nb_val, "nbHidden": nb_hidden})
    return jsonify({"ok": True, "agents": agents, "nbDefault": _nb_def,
                    "unmatchedSignings": _scan(sig_names),
                    "unmatchedListings": _scan(list_names)})

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
    cfg = _load_config()
    agents = cfg.setdefault("agents", [])
    entry = next((a for a in agents if _name_key(a.get("name", "")) == _name_key(agent)), None)
    if not entry:
        entry = {"name": agent, "aliases": []}
        agents.append(entry)
    al = entry.setdefault("aliases", [])
    if alias not in al:
        al.append(alias)
    ok = _save_config(cfg)
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
    cfg = _load_config()
    agents = cfg.setdefault("agents", [])
    if not any(_name_key(a.get("name", "")) == _name_key(name) for a in agents):
        ent = {"name": name, "aliases": []}
        if (body.get("phone") or "").strip():  ent["phone"]  = _last9(body["phone"])
        if (body.get("vphone") or "").strip(): ent["vphone"] = body["vphone"].strip()
        agents.append(ent)
    ok = _save_config(cfg)
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
    cfg = _load_config()
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
    ok = _save_config(cfg)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון סוכן", name)
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
    cfg = _load_config()
    roles = cfg.setdefault("roles", {})
    if role in _ROLE_SCOPE:
        roles[phone] = role
    else:
        roles.pop(phone, None)
    ok = _save_config(cfg)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "שיוך תפקיד", role + " ← " + phone)
    return jsonify({"ok": ok})

@app.route("/api/dev/roleperms", methods=["GET", "POST"])
def api_dev_roleperms():
    """מטריצת טאבים לכל תפקיד. GET=קריאה, POST {role, tabs:[...]}=עדכון."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    cfg = _load_config()
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
    rp = cfg.setdefault("rolePerms", {})
    rp[role] = {"tabs": [t for t in tabs if t in _ALL_TABS]}
    ok = _save_config(cfg)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון הרשאות תפקיד", role)
    return jsonify({"ok": ok})

@app.route("/api/dev/teams", methods=["GET", "POST"])
def api_dev_teams():
    """צוותים (מי רואה את מי). GET=קריאה, POST {teams:[[name,name,...],...]}=שמירה."""
    s = _web_auth()
    if not s or not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    cfg = _load_config()
    if request.method == "GET":
        return jsonify({"ok": True, "teams": cfg.get("teams") or []})
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
    cfg["teams"] = clean
    ok = _save_config(cfg)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "עדכון צוותים", str(len(clean)))
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
    cfg = _load_config()
    if request.method == "GET":
        eff = {t: _contract_text(t) for t in _CONTRACT_TYPES}
        return jsonify({"ok": True, "types": _CONTRACT_TYPES, "contracts": eff})
    body = request.get_json(silent=True) or {}
    ctype = (body.get("type") or "").strip()
    text = body.get("body")
    if ctype not in _CONTRACT_TYPES or not isinstance(text, str):
        return jsonify({"ok": False, "reason": "bad"}), 400
    contracts = cfg.setdefault("contracts", {})
    contracts[ctype] = text
    ok = _save_config(cfg)
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
        out.append({"address": addr, "price": (r.get("מחיר", "") or "").strip()})
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
    notes = (body.get("notes") or "").strip()
    signature = body.get("signature") or ""
    header = body.get("header") or ""
    if not docs:
        return jsonify({"ok": False, "reason": "no_docs"}), 400
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
    ok_any = False
    for d in docs:
        j = _buyers_apps_post("addsigning", {
            "event_id": eid, "deal_type": d.get("deal_type", ""), "agent": agent,
            "client_name": client, "address": address, "city": city,
            "commission_pct": link, "received_at": now_iso, "notes": notes})
        if j and j.get("ok"):
            ok_any = True
    doc_saved = False; doc_resp = ""
    try:   # שמירת המסמך לעמוד הציבורי (טוקן → הסכם + חתימה)
        jd = _buyers_apps_post("savesigndoc", {
            "doc_token": token, "event_id": eid, "status": "signed",
            "header": header, "docs": _json.dumps(docs, ensure_ascii=False),
            "signature": signature, "signed_at": now_iso})
        doc_saved = bool(jd and jd.get("ok"))
        doc_resp = str(jd)[:200] if jd is not None else "None (אין תגובה)"
    except Exception as _e:
        doc_saved = False; doc_resp = "EXC: " + str(_e)[:160]
    if ok_any:
        _cache_clear("signings_sheet")
        _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
        _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "החתמה דיגיטלית", (client + " · " + address).strip(" ·"))
    return jsonify({"ok": ok_any, "event_id": eid, "link": link, "doc_saved": doc_saved, "doc_resp": doc_resp})

def _sign_now_iso():
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat()
    except Exception:
        return _dt.datetime.utcnow().isoformat()

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
    # שורת חתימה 'ממתינה' — event_id=token זמני, ללא קישור (commission_pct ריק) עד שהלקוח חותם
    ok_any = False
    for d in docs:
        j = _buyers_apps_post("addsigning", {
            "event_id": token, "deal_type": d.get("deal_type", ""), "agent": agent,
            "client_name": client, "address": address, "city": city,
            "commission_pct": "", "received_at": now_iso, "notes": notes})
        if j and j.get("ok"):
            ok_any = True
    # שמירת המסמך במצב 'pending' — ללא חתימה, ימתין שהלקוח יחתום
    try:
        _buyers_apps_post("savesigndoc", {
            "doc_token": token, "event_id": token, "status": "pending",
            "header": header, "docs": _json.dumps(docs, ensure_ascii=False),
            "signature": "", "signed_at": ""})
    except Exception:
        pass
    # שליחה ב-SMS וב-WhatsApp
    msg = ("שלום %s,\nהתבקשת לחתום על מסמך מטעם RE/MAX Family (%s).\nלצפייה וחתימה:\n%s" % (client, agent, link))
    sms_ok = False; wa_ok = False
    try: sms_ok = bool(web_send_sms(last9, msg))
    except Exception: sms_ok = False
    try:
        wa = _wa_phone(phone)
        if wa: send_text(wa, msg); wa_ok = True
    except Exception: wa_ok = False
    if ok_any:
        _cache_clear("signings_sheet")
        _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
        _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "שליחת חתימה מרחוק", (client + " · " + address).strip(" ·"))
    return jsonify({"ok": ok_any, "sms": sms_ok, "wa": wa_ok, "phone": last9})

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
    j = _buyers_apps_post("getsigndoc", {"doc_token": token})
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
        ju = _buyers_apps_post("updatesigndoc", {
            "doc_token": token, "event_id": cid, "status": "signed",
            "header": header, "signature": signature, "signed_at": now_iso})
        upd_ok = bool(ju and ju.get("ok"))
    except Exception:
        upd_ok = False
    # הוספת הקישור לשורת החתימה הקיימת + עדכון event_id ל-ת״ז
    try:
        _buyers_apps_post("updatesigning", {"doc_token": token, "commission_pct": link, "event_id": cid})
    except Exception:
        pass
    _cache_clear("signings_sheet")
    _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
    return jsonify({"ok": upd_ok, "link": link})

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
        if wa: send_text(wa, msg); wa_ok = True
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
    """עמוד ציבורי של ההסכם החתום (ללא התחברות) — נפתח מהקישור בשורת החתימה / מה-SMS."""
    import html as _h
    j = _buyers_apps_post("getsigndoc", {"doc_token": token})
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
             "@media print{.pb,.signbox{display:none}body{background:#fff;padding:0}.page{box-shadow:none;border-radius:0;max-width:100%;border:none}}"
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
    _agent_box = ""
    if _p["agent"]:
        _agent_box = ("<div class=agentbox><div class=an>" + _h.escape(_p["agent"]) + "</div>" +
            (("<div class=al>רישיון תיווך מס׳: " + _h.escape(_alic) + "</div>") if _alic else "") +
            (("<div class=al>טלפון: " + _h.escape(_aphone) + "</div>") if _aphone else "") +
            "<div class=al>RE/MAX Family</div></div>")
    _logobar = "<div class=logobar>" + _agent_box + "<img src='/assets/logo?v=3' alt='RE/MAX Family'></div>"
    meta_html = (_logobar +
        "<div class=docnum>הסכם מס׳ " + _docnum + "</div>" +
        (("<div class=cline>" + " · ".join(_cparts) + "</div>") if _cparts else "") +
        _ptbl)
    if status == "pending":
        _form = (docs_html +
                 "<div class=signbox><div class=signlbl>תעודת זהות</div>"
                 "<input id=cid class=signinp type=text inputmode=numeric maxlength=9 name=sg_tz autocomplete=off autocorrect=off data-form-type=other data-lpignore=true placeholder='9 ספרות' oninput='chkId()'>"
                 "<div id=idmsg></div>"
                 "<div class=signlbl style='margin-top:14px'>✍️ חתימה</div>"
                 "<canvas id=pad class=signpad></canvas>"
                 "<div style='text-align:left'><button class=clrbtn onclick='clrPad()'>נקה</button></div>"
                 "<button id=sbtn class=pb onclick='doSign()'>✅ אשר וחתום</button>"
                 "<div style='text-align:center;color:#888;font-size:12px;margin-bottom:20px'>בלחיצה אני מאשר/ת את תוכן המסמך וחותם/ת עליו</div>"
                 "</div></div>")
        _js = ("<script>var TOKEN=" + _json.dumps(token) + ";"
               "function validIL(v){v=String(v).replace(/\\D/g,'');if(v.length>9)return false;while(v.length<9)v='0'+v;var s=0;for(var i=0;i<9;i++){var n=parseInt(v[i],10)*((i%2)+1);if(n>9)n-=9;s+=n;}return s%10===0;}"
               "function chkId(){var v=document.getElementById('cid').value;var m=document.getElementById('idmsg');if(!v){m.textContent='';return;}if(validIL(v)){m.textContent='✓ תקין';m.style.color='#1a8a4a';}else{m.textContent='✗ ת״ז לא תקינה';m.style.color='#c0392b';}}"
               "var cv=document.getElementById('pad'),cx=cv.getContext('2d'),drawing=false,signed=false;"
               "function szPad(){var r=cv.getBoundingClientRect();cv.width=r.width;cv.height=180;cx.lineWidth=2.5;cx.lineCap='round';cx.lineJoin='round';cx.strokeStyle='#0D1B2A';}"
               "szPad();"
               "function pos(e){var r=cv.getBoundingClientRect();var t=(e.touches&&e.touches[0])?e.touches[0]:e;return{x:t.clientX-r.left,y:t.clientY-r.top};}"
               "function dn(e){drawing=true;var p=pos(e);cx.beginPath();cx.moveTo(p.x,p.y);if(e.cancelable)e.preventDefault();}"
               "function mv(e){if(!drawing)return;var p=pos(e);cx.lineTo(p.x,p.y);cx.stroke();signed=true;if(e.cancelable)e.preventDefault();}"
               "function up(){drawing=false;}"
               "cv.addEventListener('mousedown',dn);cv.addEventListener('mousemove',mv);window.addEventListener('mouseup',up);"
               "cv.addEventListener('touchstart',dn,{passive:false});cv.addEventListener('touchmove',mv,{passive:false});cv.addEventListener('touchend',up);"
               "function clrPad(){cx.clearRect(0,0,cv.width,cv.height);signed=false;}"
               "function doSign(){var id=document.getElementById('cid').value;if(!validIL(id)){alert('תעודת הזהות אינה תקינה');return;}if(!signed){alert('נא לחתום בתיבת החתימה');return;}"
               "var tw=440,th=Math.round(tw*cv.height/cv.width);var c=document.createElement('canvas');c.width=tw;c.height=th;var x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,tw,th);x.drawImage(cv,0,0,tw,th);var sig=c.toDataURL('image/jpeg',0.55);"
               "var b=document.getElementById('sbtn');b.disabled=true;b.textContent='שומר…';"
               "fetch('/api/sign/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:TOKEN,cid:id,signature:sig})}).then(function(r){return r.json();}).then(function(r){if(r&&r.ok){location.reload();}else{b.disabled=false;b.textContent='✅ אשר וחתום';alert('שמירה נכשלה: '+((r&&r.reason)||'שגיאה'));}}).catch(function(){b.disabled=false;b.textContent='✅ אשר וחתום';alert('שגיאת רשת');});}"
               "</script>")
        return _head + meta_html + _form + _js + "</body></html>"
    _tail = (docs_html + sig_html + "</div>"
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
    cfg = _load_config()
    if v in ("", None):
        cfg.pop("newbornDefaultDelay", None)
    else:
        try: cfg["newbornDefaultDelay"] = int(v)
        except Exception: return jsonify({"ok": False, "reason": "bad"}), 400
    ok = _save_config(cfg)
    _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "ברירת מחדל נכס נולד", str(v))
    return jsonify({"ok": ok})

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
    return jsonify({"ok": True, "msg": msg, "url_set": bool(APPS_SCRIPT_URL),
                    "getconfig_ok": getok, "write_ok": bool(wrote), "readback_ok": readback,
                    "raw": str(raw_get)[:200]})

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
        "eid": str(g.get("event_id", "") or "").strip(),
        "raw": str(g.get("received_at", "") or "").strip(),
    } for g in sigs[:500]]
    vphone = _vphone_for_name(eff["name"])
    return jsonify({"ok": True, "role": eff["role"], "name": eff["name"],
                    "dev": bool(s.get("dev", False)),
                    "drole": s.get("drole", ""), "tabs": _tabs_for_role(s.get("drole", "")),
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
    return jsonify({"ok": True, "items": merged[:300]})

def _web_org_summary(frm, to, agent_name=None, agent_phones=None, agent_keys=None):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as _ex:
        _fc = _ex.submit(web_fetch_raw, "שיחות", frm, to)
        _fs = _ex.submit(get_signings, frm, to)
        _fp = _ex.submit(web_fetch_raw, "נכסים", frm, to)
        calls, sigs, props = _fc.result(), _fs.result(), _fp.result()
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
                          key=lambda x: -x["n"])[:5],
        "topKonim": sorted(({"name": k, "n": v["konim"]} for k, v in sig_agents.items() if v["konim"]),
                           key=lambda x: -x["n"])[:5],
        "props": {"total": len(props), "topCities": top_cities},
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
    label = {"week": "השבוע", "lastweek": "שבוע שעבר", "month": "החודש", "year": "השנה"}.get(period, "החודש")
    if sel_month.isdigit() and 1 <= int(sel_month) <= 12:
        mo = int(sel_month)
        start = now.replace(month=mo, day=1, hour=0, minute=0, second=0, microsecond=0)
        if mo < now.month:  # חודש שכבר הסתיים — עד סוף החודש
            nxt = start.replace(year=start.year + 1, month=1) if mo == 12 else start.replace(month=mo + 1)
            end = nxt - timedelta(days=1)
        label = f"{_HE_MONTHS[mo - 1]} {start.year}"
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
    insights = []
    try:
        sm = _web_org_summary(frm, to, eff_name, eff_phones, eff_keys)
        try:   # ספירת "מודעות" — אותו מקור של "נכסים במשרד" (יד2): סוכן=שלו, מנהל=סה"כ
            _lr = fetch_sheet_rows()
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
                for _r in _dedupe_exclusives(fetch_external_exclusives()):
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
                for _r in fetch_newborn():
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
        return jsonify({"ok": True, "label": label, "scope": scope, "from": frm, "to": to,
                        "insights": insights, "summary": sm, "listings": listings_total,
                        "shtaf": shtaf, "shtaf_total": shtaf_total, "shtaf_offices": shtaf_offices,
                        "nbCities": nb_cities, "nbTotal": nb_total, "wa_text": wa})
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
                "desc": (row.get("_desc_ae", "") or "").strip(),
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
    c = _cache_get("pending_listings", 180)
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
NEWBORN_SHEET_TAB   = os.environ.get("NEWBORN_SHEET_TAB", "נכס נולד")
NEWBORN_DELAYS_TAB  = os.environ.get("NEWBORN_DELAYS_TAB", "נכסנולד_הגדרות")
NEWBORN_DEFAULT_DELAY = int(os.environ.get("NEWBORN_DEFAULT_DELAY", "0") or 0)
NEWBORN_WINDOW_DAYS   = int(os.environ.get("NEWBORN_WINDOW_DAYS", "190") or 190)
NEWBORN_HIDDEN        = 10 ** 9   # ערך "מוסתר" — הסוכן לא רואה שום נכס
_NB_HIDDEN_TOKENS = {"מוסתר", "מוסתרת", "הסתר", "לעולם", "אין", "לא", "-", "–", "—", "x", "X", "✗"}

def fetch_newborn():
    c = _cache_get("newborn_rows", 300)
    if c is not None: return c
    with _sf_lock("newborn_rows"):
        c = _cache_get("newborn_rows", 300)
        if c is not None: return c
        j = _buyers_apps_post("listnewborn", {})
        rows = (j.get("rows", []) or []) if (j and j.get("ok")) else []
        _cache_put("newborn_rows", rows)
        return rows

def _fetch_newborn_delays():
    c = _cache_get("newborn_delays", 600)
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
    c = _cache_get("newborn_contacts", 150)
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
                "phone": _fmt_vphone(ophone),
                "wa": _wa_phone(ophone),
                "agent": lister,
                "link": _nb(r.get("קישור", "")),
                "date": _nb(r.get("נוצר בתאריך", "") or r.get("תאריך יצירה", "")),
            })
            if len(out) >= 300:   # תקרת בטיחות; הפרונט מציג 20 בכל פעם עם "טען עוד"
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
        if q: _log_activity(s["name"], s["role"], s["phone"], "חיפוש בלעדיות", q)
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
    c = _cache_get("buyers", 60)
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
    c = _cache_get("hidden_calls", 180)
    if c is not None: return c
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
    """מחיקת הסכם מגיליון 'חתימות' — מפתח בלבד. נמחק גם מהרשימה וגם מהדוחות (אותו מקור)."""
    s = _web_auth()
    if not s: return jsonify({"ok": False, "auth": False}), 401
    if not _is_dev(s.get("phone", "")):
        return jsonify({"ok": False, "reason": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    eid = str(body.get("eid", "") or "").strip()
    received = str(body.get("received", "") or "").strip()
    client = str(body.get("client", "") or "").strip()
    if not (eid or (client and received)):
        return jsonify({"ok": False, "reason": "no_key"}), 400
    j = _buyers_apps_post("deletesigning", {"event_id": eid, "received_at": received, "client_name": client})
    ok = bool(j and j.get("ok"))
    if ok:
        _cache_clear("signings_sheet")
        _cache_clear("raw:חתימות:01/01/2020:31/12/2099")
        _log_activity(s.get("name", ""), s.get("role", ""), s.get("phone", ""), "מחיקת הסכם", (client + " " + eid)[:80])
    return jsonify({"ok": ok, "deleted": (j.get("deleted") if j else 0)})

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
    resp = Response(FAMILY_BOT_HTML, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
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
.callrow .cbtns .wab{display:inline-block;background:#e7f6ec;color:#0f7a37;border:1px solid #b6e3c4;font-weight:800;font-size:12px;padding:6px 12px;border-radius:10px;text-decoration:none}
.ans,.noans{font-size:12px;padding:3px 11px}
.ouroffice{display:inline-block;background:#fdeef0;color:#c01f2a;font-weight:900;padding:1px 9px;border-radius:8px;border:1px solid #f3c4c9}
.nbcardx{position:relative;background:#fff;border:1px solid #edf0f4;border-radius:16px;padding:14px 15px;margin-bottom:12px;box-shadow:0 4px 16px rgba(13,27,42,.05);overflow:hidden}
.nbcardx:before{content:"";position:absolute;inset-inline-start:0;top:0;bottom:0;width:4px;background:linear-gradient(180deg,var(--gold),#a87d1a)}
.nbcardx .nbtop{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.nbcardx .nbaddr{font-size:16px;font-weight:900;color:var(--ink);line-height:1.3}
.nbcardx .nbdate{font-size:12px;color:#8a929d;font-weight:700;white-space:nowrap}
.nbcardx .nbdesc{font-size:14px;color:#33405a;margin-top:5px;line-height:1.5}
.nbcardx .nbprice{font-size:16px;font-weight:900;color:#0f7a37;margin-top:6px}
.nbcardx .nbowner{font-size:14px;font-weight:800;color:var(--ink);margin-top:9px;padding-top:9px;border-top:1px solid #f0f2f5}
.nbcardx .nbacts{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.nbcardx .nbbtn{display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:800;padding:10px 15px;border-radius:11px;cursor:pointer;text-decoration:none;border:1px solid transparent}
.nbcardx .nbbtn.call{background:#eef4ff;color:#1d4ed8;border-color:#cfe0fb}
.nbcardx .nbbtn.wa{background:#e7f6ec;color:#0f7a37;border-color:#b6e3c4}
.nbcardx .nbbtn.link{background:#0D1B2A;color:#fff;border-color:#0D1B2A}
.nbcardx .nbcontact{margin-top:9px}
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
/* ===== ריענון 2 (Claude design) — באטץ' 1: יסודות · פלטת נייבי+זהב ===== */
:root{--ink:#15263b;--gold:#bb8a2c;--green:#1f8a4c;--red:#d23b3b;--blue:#003DA5;--muted:#8b93a1;--line:#efece6}
body{overflow-x:clip}
body{background:#f6f5f2!important;background-color:#f6f5f2!important;color:var(--ink);letter-spacing:-.012em}
.wrap{overflow-x:hidden}
.sg_prow{max-width:100%}
.card{background:#fff;border-radius:20px;box-shadow:0 8px 22px rgba(20,30,50,.05);border:1px solid var(--line)}
h2{border-inline-start-color:var(--gold)}
input,textarea{background:#fbfcfd;border:1.5px solid #e7e3da}
input:focus,textarea:focus{border-color:var(--ink);box-shadow:0 0 0 3px rgba(21,38,59,.09)}
button{background:linear-gradient(180deg,#16273c,#0D1B2A);color:#fff;box-shadow:0 6px 18px rgba(20,30,50,.18);border-radius:12px}
button:hover{filter:brightness(1.06)}
.btn-primary{background:linear-gradient(180deg,#16273c,#0D1B2A)!important;color:#fff!important;border:none!important;box-shadow:0 6px 18px rgba(20,30,50,.2)!important}
button.gold,.btn-gold{background:linear-gradient(180deg,#d4a437,#c0901f)!important;color:#231700!important;border:none!important;box-shadow:0 6px 16px rgba(187,138,44,.28)!important;font-weight:800}
button.sec,.btn-ghost,.sec{background:#fff!important;color:var(--ink)!important;border:1px solid var(--line)!important;box-shadow:0 2px 8px rgba(20,30,50,.04)!important}
/* ===== באטץ' 2: כותרת + טאב-בר + אייקוני SVG ===== */
.tic svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;display:block}
.tab .tic{width:36px;height:28px}
.tab{color:#9aa1ac}
.tab.on{color:var(--ink)!important}
.tab.on .tic{background:linear-gradient(180deg,rgba(187,138,44,.22),rgba(187,138,44,.07));box-shadow:inset 0 0 0 1px rgba(187,138,44,.3)}
.tabs{background:rgba(255,255,255,.96);border-top:1px solid var(--line)}
.hicon{width:18px;height:18px;fill:none;stroke:var(--ink);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;display:block}
.sharebtn{background:#fff!important;border:1px solid var(--line)!important}
.brand{padding-bottom:14px}
.brand:after{background:linear-gradient(90deg,transparent,rgba(187,138,44,.5),transparent)}
.brandname{position:relative;background:linear-gradient(180deg,#22364f,#15263b)!important;color:#fff!important;width:40px;height:40px;border-radius:50%!important;padding:0!important;display:inline-flex!important;align-items:center;justify-content:center;font-size:14px!important;font-weight:800!important;border:none!important;box-shadow:0 3px 10px rgba(20,30,50,.2)!important;gap:0!important}
.brandname:before{content:""!important;position:absolute;bottom:1px;inset-inline-end:1px;width:10px;height:10px;border-radius:50%;background:var(--green)!important;border:2px solid #f6f5f2;box-shadow:none!important}
/* ===== באטץ' 3: שיחות + קונים ===== */
.callrow:before{display:none!important}
.callrow{padding:14px 16px;border-color:var(--line);box-shadow:0 8px 22px rgba(20,30,50,.05)}
.callrow.new{box-shadow:0 0 0 1.5px rgba(187,138,44,.55),0 8px 22px rgba(20,30,50,.05)}
.callrow .cphone{font-size:19px;white-space:nowrap}
.callrow .csum{border-top:none!important;color:#5b6473;padding-top:2px}
.callrow .csummore{color:var(--gold)}
.ans{background:#e6f4ec!important;color:var(--green)!important}
.noans{background:#fae8e8!important;color:var(--red)!important}
.callrow .cbtns .addbuyer{background:linear-gradient(180deg,#16273c,#0D1B2A)!important;color:#fff!important;border:none!important;padding:7px 14px!important;border-radius:10px!important;font-size:12.5px!important;box-shadow:0 3px 10px rgba(20,30,50,.16)!important}
.callrow .cbtns .wab{background:#e6f4ec!important;color:var(--green)!important;border:1px solid #bfe3cd!important}
.callrow .cbtns .hidecall{background:#fff!important;border:1px solid var(--line)!important;color:#6b7280!important}
.buyerrow{border-right:none!important;background:#fff!important;border:1.5px solid #e7d6a8;border-radius:18px;box-shadow:0 8px 22px rgba(20,30,50,.05);padding:14px 16px}
.btag{background:#fbf3df!important;color:#7a5c12!important;border:1px solid #ead9ab}
.bbudget{background:#fbf3df!important;color:#7a5c12!important;border:1px solid #ead9ab!important}
.bsum{color:#5b6473}
.bmore{color:var(--gold)!important}
.bsearch{background:linear-gradient(180deg,#16273c,#0D1B2A)!important;border:none!important;color:#fff!important;border-radius:11px!important}
.bsearch[data-k=excl]{background:#fff!important;color:var(--ink)!important;border:1px solid var(--line)!important}
.bsearch[data-k=props]{background:linear-gradient(180deg,#2f6fd6,#1f5fbe)!important;color:#fff!important;border:none!important;box-shadow:0 4px 12px rgba(31,95,190,.28)!important}
.searchbtn{background:linear-gradient(180deg,#2f6fd6,#1f5fbe)!important;color:#fff!important;border:none!important;box-shadow:0 6px 16px rgba(31,95,190,.26)!important}
/* ===== באטץ' 4: נכסים + שת"פ + נכס נולד ===== */
.score{background:#e6f4ec!important;color:var(--green)!important;border-radius:999px}
.ouroffice{background:#fae8e8!important;color:var(--red)!important;border:1px solid #f0c9cc!important}
.rchip{background:rgba(21,38,59,.05)!important;color:var(--ink)!important;border:1px solid var(--line)!important}
.cbtn{background:linear-gradient(180deg,#16273c,#0D1B2A)!important}
.nbcardx:before{display:none!important}
.nbcardx{padding:14px 16px;border-color:var(--line);box-shadow:0 8px 22px rgba(20,30,50,.05)}
.nbcardx .nbprice{color:var(--ink)!important}
.nbcardx .nbbtn.link{background:linear-gradient(180deg,#16273c,#0D1B2A)!important;border-color:transparent!important}
.nbbanner{background:linear-gradient(90deg,#fbf3df,#f7ead0)!important;border:1px solid #e7d6a8!important;color:#6b4e0e!important}
/* ===== באטץ' 5: דוחות + קונסולת ניהול + חתימות + התחברות ===== */
.stat{background:#fff!important;border:1px solid var(--line)!important;border-radius:16px!important;box-shadow:0 6px 16px rgba(20,30,50,.04)!important}
.stat .n{color:var(--ink)}
.grid .stat:nth-child(2) .n{color:var(--green)!important}
.grid .stat:nth-child(5) .n{color:var(--gold)!important}
.insight{border-bottom-color:var(--line)}
th{border-bottom-color:var(--line)}td{border-bottom-color:var(--line)}
.loginlogo img{filter:none}
#login .card{box-shadow:0 10px 30px rgba(20,30,50,.07)}
.selwrap select{border-color:#e7e3da!important}
.appmenu{border-color:var(--line);box-shadow:0 16px 40px rgba(20,30,50,.18)}
.ovlbox{border-radius:18px}
.chip{background:#f1efe9;border-color:#e7e3da;color:var(--ink)}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
input.chip,textarea.chip,select.chip{background:#fff!important;border:1px solid #e7e3da!important;color:var(--ink)!important;font-weight:600}
input[type=checkbox],input[type=radio]{accent-color:var(--gold);width:21px!important;height:21px!important;min-width:21px!important;flex:0 0 auto!important;margin:0!important;padding:0!important}
.eico{width:14px;height:14px;vertical-align:-2px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;display:inline-block;margin-inline-end:3px}
/* ===== באטץ' 6: מסך שיחות לפי המוקאפ ===== */
#view h2{border-inline-start:none;padding-inline-start:0;font-size:22px}
#callkpi{grid-template-columns:1fr 1fr 1fr;margin-top:10px}
#callkpi:empty{display:none}
.callrow .crow1{display:flex;align-items:center;gap:11px;margin-bottom:2px}
.callrow .cstat{width:40px;height:40px;border-radius:12px;flex:0 0 auto;display:flex;align-items:center;justify-content:center}
.callrow .cstat svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.callrow .cstat.ok{background:#e6f4ec;color:var(--green)}
.callrow .cstat.no{background:#fae8e8;color:var(--red)}
.callrow .cmain{flex:1;min-width:0}
.callrow .csub{color:var(--muted);font-size:12.5px;font-weight:600;margin-top:1px}
.callrow .cdetails{background:none!important;border-inline-start:none!important;border-radius:0!important;padding:0!important;margin-top:8px!important;color:#5b6473}
.callrow .cdetails b{display:none}
/* ===== באטץ' 8: טאב חתימות (כפתורים + כרטיסים) ===== */
.chips .chip.on{background:linear-gradient(180deg,#2f6fd6,#1f5fbe)!important;color:#fff!important;box-shadow:0 4px 12px rgba(31,95,190,.28)!important}
.chips .chip.on:after{display:none!important}
.sgdel{flex:0 0 auto!important;width:34px!important;height:34px!important;min-width:34px!important;padding:0!important;margin:0!important;display:inline-flex!important;align-items:center;justify-content:center;font-size:15px;border-radius:9px!important}
.sg_prow .chip{height:34px;padding-top:0;padding-bottom:0}
.sgback{width:auto!important;margin:0!important;display:inline-flex;align-items:center;gap:5px;background:linear-gradient(180deg,#d4a437,#c0901f)!important;color:#231700!important;border:none!important;font-weight:800;font-size:13px;padding:9px 15px!important;border-radius:11px!important;box-shadow:0 4px 12px rgba(187,138,44,.26)!important;cursor:pointer;flex:0 0 auto}
.sgback svg{width:15px;height:15px;fill:none;stroke:#231700;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.sglbl{display:flex;align-items:center;gap:5px;font-weight:700}
.sglbl .eico{stroke:var(--gold);margin:0;width:15px;height:15px}
.sgbtns{display:flex;gap:8px;margin-top:12px}
.sgbtns .sgbtn{flex:1;width:auto!important;margin:0!important;display:inline-flex;align-items:center;justify-content:center;gap:6px}
.sgbtn .eico{stroke:#231700;margin:0}
.scard{background:#fff;border:1px solid var(--line);border-radius:18px;padding:14px 16px;margin-bottom:11px;box-shadow:0 8px 22px rgba(20,30,50,.05)}
.scard.excl{border:1.5px solid #e7d6a8}
.scard.pending{border:1.5px dashed #e0c98a;background:#fffdf8}
.pendlbl{color:var(--gold);font-weight:800}
.scard .sdel{flex:0 0 auto;width:32px;height:32px;min-width:32px;padding:0;margin:0;display:inline-flex;align-items:center;justify-content:center;background:#fff;border:1px solid #f0c9cc;border-radius:9px;color:var(--red);cursor:pointer}
.scard .sdel .eico{stroke:var(--red);margin:0}
.scard .stop{align-items:center}
.scard.new{box-shadow:0 0 0 1.5px rgba(187,138,44,.5),0 8px 22px rgba(20,30,50,.05)}
.scard .stop{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.scard .sname{font-size:15.5px;font-weight:800;color:var(--ink)}
.scard .stag{flex:0 0 auto;font-size:11px;font-weight:800;padding:3px 11px;border-radius:999px;white-space:nowrap}
.stag.t-buyer{background:#eef2fb;color:#2f5fbe}
.stag.t-seller{background:#fdeef0;color:#c01f2a}
.stag.t-excl{background:#fbf3df;color:#7a5c12}
.stag.t-rent{background:#e6f4ec;color:var(--green)}
.scard .saddr{color:#5b6473;font-size:13.5px;margin-top:8px;display:flex;align-items:center;gap:4px}
.scard .sdate{color:var(--muted);font-size:12.5px;margin-top:5px}
.scard .slink{display:inline-flex;align-items:center;background:linear-gradient(180deg,#16273c,#0D1B2A);color:#fff;font-weight:800;font-size:12.5px;padding:9px 15px;border-radius:11px;text-decoration:none}
.scard .slink .eico{stroke:#fff}
.callrow .cbtns .addbuyer{background:linear-gradient(180deg,#2f6fd6,#1f5fbe)!important;color:#fff!important;border:none!important;box-shadow:0 4px 12px rgba(31,95,190,.28)!important}
.callrow .cbtns .addbuyer .eico{stroke:#fff}
.callrow .cbtns .cbtn{display:inline-flex!important;align-items:center;justify-content:center;background:#eef1f6!important;color:#46505f!important;border:1px solid var(--line)!important;box-shadow:none!important;font-weight:800!important;font-size:12px!important;padding:6px 12px!important;border-radius:10px!important}
.brandname:empty{display:none!important}
/* ===== כרטיסי נכסים / שת"פ עשירים (מוקאפ 05/06) ===== */
.pcard{background:#fff;border:1.5px solid #e7d6a8;border-radius:18px;padding:14px 16px;margin-bottom:11px;box-shadow:0 8px 22px rgba(20,30,50,.05)}
.pcard .ptop{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.pcard .ptitle{font-size:15.5px;font-weight:800;color:var(--ink);line-height:1.35}
.pcard .pscore{flex:0 0 auto;background:#e6f4ec;color:var(--green);font-weight:800;font-size:12px;padding:3px 10px;border-radius:999px;white-space:nowrap}
.pcard .pmeta{color:var(--muted);font-size:13px;margin-top:5px;line-height:1.5}
.pcard .pdesc{color:#5b6473;font-size:13.5px;margin-top:7px;line-height:1.6;white-space:pre-line}
.pcard .pdesc.clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pcard .pmore{display:inline-block;margin-top:3px;color:var(--gold);font-weight:800;font-size:12.5px;cursor:pointer}
.pcard .ptop .shchk{flex:0 0 auto;margin:2px 0 0 0}
#sharebar{position:fixed;bottom:74px;left:50%;transform:translateX(-50%);width:calc(100% - 28px);max-width:592px;background:linear-gradient(180deg,#2f6fd6,#1f5fbe);color:#fff;text-align:center;padding:14px;font-weight:800;font-size:15px;border-radius:14px;box-shadow:0 8px 24px rgba(31,95,190,.35);z-index:55;cursor:pointer}
#sharebar.hidden{display:none}
.pcard .pprice{font-size:19px;font-weight:900;color:var(--ink);margin-top:7px}
.pcard .pagent{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px;padding-top:9px;border-top:1px solid var(--line);font-size:13.5px;font-weight:700;color:var(--ink)}
.pcard .pagent span{display:inline-flex;align-items:center}
.pcard .pwa{display:inline-flex;align-items:center;background:#e6f4ec;color:var(--green)!important;border:1px solid #bfe3cd;font-weight:800;font-size:12px;padding:6px 13px;border-radius:10px;text-decoration:none}
.pcard .pacts{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px;align-items:center}
.pcard .pacts .lreq{width:auto;margin:0;padding:8px 13px;font-size:12.5px;font-weight:800;border-radius:10px;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
.pcard .pacts .plink{background:linear-gradient(180deg,#16273c,#0D1B2A);color:#fff;font-weight:800;font-size:12.5px;padding:9px 15px;border-radius:10px;text-decoration:none}
.pcard .lpend{background:#fff3d6;color:#7a5c12;border:1px solid #e7d39a;font-weight:800;font-size:12px;padding:5px 11px;border-radius:9px}
/* ===== מסך התחברות לפי המוקאפ ===== */
.wrap:has(#login:not(.hidden)) .brand{display:none!important}
.loginlogo{margin:34px 0 8px}
.loginlogo img{width:auto!important;height:62px!important;max-width:64%!important;border-radius:0!important;border:none!important}
.loginhead{text-align:center;font-size:24px;font-weight:800;color:var(--ink);margin:6px 0 4px}
.loginsub{text-align:center;font-size:14px;color:var(--muted);line-height:1.6;max-width:330px;margin:0 auto 6px;padding:0 12px}
#login .card{margin-top:14px;box-shadow:0 10px 30px rgba(20,30,50,.07)}
#login .card label{display:block;text-align:right;margin-bottom:6px}
#login #phone,#login #code{text-align:center;direction:ltr;font-size:18px;font-weight:700;letter-spacing:.5px}
</style></head><body><div class="wrap">
<div class="brand"><div class="menuwrap"><button class="sec sharebtn" id="menubtn" onclick="toggleMenu(event)" title="תפריט"><svg viewBox="0 0 18 18" class="hicon"><path d="M3 5h12M3 9h12M3 13h12"/></svg></button><div id="appmenu" class="appmenu hidden"><div class="mi hidden" id="mi-dev" onclick="closeMenu();openDevConsole()">⚙️ ניהול (מפתח)</div><div class="mi hidden" id="mi-activity" onclick="menuGo('activity')">📣 עדכונים</div><div class="mi" id="mi-report" onclick="menuGo('report')">📊 דוחות</div><div class="mi-sub hidden" id="mi-imp"><div class="mi-lbl">👁 צפה כסוכן</div><select id="impsel" onchange="setImp(this.value)"><option value="">— כל הסוכנים —</option></select></div><div class="mi-sub hidden" id="mi-testlogin"><div class="mi-lbl">🧪 כניסה כסוכן (בדיקה)</div><select id="testsel" onchange="loginAsAgent(this.value)"><option value="">— בחר סוכן —</option></select></div><hr><div class="mi" onclick="closeMenu();openHelp()">💬 עזרה / דיווח תקלה</div><div class="mi" onclick="closeMenu();addToHome()">➕ הוסף למסך הבית</div><div class="mi" onclick="closeMenu();window.open('https://www.instagram.com/remax.family?igsh=bXdmdzJjMWVkc3li&utm_source=qr','_blank')"><svg viewBox="0 0 24 24" style="width:19px;height:19px;fill:none;stroke:#E1306C;stroke-width:1.9;flex:0 0 auto"><rect x="2.5" y="2.5" width="19" height="19" rx="5.5"/><circle cx="12" cy="12" r="4.2"/><circle cx="17.6" cy="6.4" r="1.2" fill="#E1306C" stroke="none"/></svg> אינסטגרם של המשרד</div><div class="mi" onclick="closeMenu();window.open('https://www.madlan.co.il/madad/2026/%D7%A7%D7%A8%D7%99%D7%95%D7%AA','_blank')">🏅 מדד המתווכים — מדלן 2026</div><div class="mi" onclick="closeMenu();shareApp()">📲 שתף אפליקציה</div><div class="mi mi-danger" onclick="logout()">🚪 יציאה</div></div></div><img src="/assets/logo?v=3" alt="RE/MAX Family" onerror="this.style.display='none';var t=document.getElementById('brandtxt');if(t)t.style.display='block';"><div id="brandtxt" class="brandtxt" style="display:none">🏠 Family Bot</div><span id="brandname" class="brandname"></span></div>

<div id="login">
  <div class="loginlogo"><img src="/assets/logo?v=3" alt="RE/MAX Family" onerror="this.style.display='none'"></div>
  <div class="loginhead">ברוך הבא</div>
  <div class="loginsub">התחבר עם מספר הטלפון שלך — נשלח לך קוד אימות חד-פעמי ב-SMS.</div>
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
  <div id="sharebar" class="hidden" onclick="shareOpen()">📤 שלח ללקוח (<span id="sharecount">0</span>)</div>
  <div class="tabs">
    <div class="tab on" data-t="calls" onclick="tab('calls')"><span class="tic"><svg viewBox="0 0 18 18"><path d="M16 13.4v2.1a1.4 1.4 0 0 1-1.5 1.4 13.9 13.9 0 0 1-6.1-2.2 13.7 13.7 0 0 1-4.2-4.2A13.9 13.9 0 0 1 2 4.4 1.4 1.4 0 0 1 3.4 3h2.1a1.4 1.4 0 0 1 1.4 1.2c.1.7.3 1.4.5 2a1.4 1.4 0 0 1-.3 1.5l-.9.9a11.2 11.2 0 0 0 4.2 4.2l.9-.9a1.4 1.4 0 0 1 1.5-.3c.6.2 1.3.4 2 .5A1.4 1.4 0 0 1 16 13.4z"/></svg></span>שיחות שלי</div>
    <div class="tab" data-t="buyers" onclick="tab('buyers')"><span class="tic"><svg viewBox="0 0 18 18"><circle cx="9" cy="6" r="3"/><path d="M3.6 16a5.4 5.4 0 0 1 10.8 0"/></svg></span>הקונים שלי</div>
    <div class="tab" data-t="sigs" onclick="tab('sigs')"><span class="tic"><svg viewBox="0 0 18 18"><path d="M11.8 3.4l2.8 2.8L6 14.8 3 15.4l.6-3z"/><path d="M10.6 4.6l2.8 2.8"/></svg></span>חתימות שלי</div>
    <div class="tab" data-t="props" onclick="tab('props')"><span class="tic"><svg viewBox="0 0 18 18"><rect x="4.2" y="2.6" width="9.6" height="12.8" rx="1"/><path d="M7 6h1.2M9.8 6H11M7 9h1.2M9.8 9H11M7 12h4"/><path d="M2.6 15.4h12.8"/></svg></span>נכסים במשרד</div>
    <div class="tab" data-t="excl" onclick="tab('excl')"><span class="tic"><svg viewBox="0 0 18 18"><rect x="2.4" y="6" width="6.4" height="9.4" rx="1"/><rect x="9.4" y="3" width="6.2" height="12.4" rx="1"/></svg></span>נכסים בשת״פ</div>
    <div class="tab" data-t="newborn" id="nbtab" onclick="tab('newborn')"><span class="tic">🐥</span>נכס נולד<span class="tabbadge hidden" id="nbtabbadge"></span></div>
  </div>
  <div id="nbmodal" class="nbmodal hidden" onclick="if(event.target===this)closeNewborn()"></div>
</div>

<script>
var TOKEN=null,ROLE=null,DROLE=null,NAME=null,DEV=false,TABS=null,TABNOW="calls",RANGE="day",timer=null,seenCall=0,seenSig=0,IMP=null,IMPNAME=null,CUR_EP=null,CUR_KIND=null;
function $(id){return document.getElementById(id);}
function show(id){$("s1").classList.add("hidden");$("s2").classList.add("hidden");$(id).classList.remove("hidden");}
function api(path,opt){opt=opt||{};opt.headers=opt.headers||{};if(TOKEN)opt.headers["X-Auth-Token"]=TOKEN;return fetch(path,opt).then(function(r){return r.json();});}
try{var sp=localStorage.getItem("fbPhone");if(sp)$("phone").value=sp;}catch(e){}
try{var st=localStorage.getItem("fbTok");if(st){TOKEN=st;ROLE=localStorage.getItem("fbRole");DROLE=localStorage.getItem("fbDrole")||"";NAME=localStorage.getItem("fbName");DEV=localStorage.getItem("fbDev")=="1";try{TABS=JSON.parse(localStorage.getItem("fbTabs")||"null");}catch(e2){TABS=null;}enter();}}catch(e){}
function sendCode(){var p=$("phone").value.trim();if(!p){alert("הזן מספר");return;}try{localStorage.setItem("fbPhone",p);}catch(e){}$("m1").textContent="שולח…";
  api("/api/auth/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone:p})}).then(function(r){
    if(r.ok){show("s2");$("m2").textContent="";startOtp();}
    else{$("m1").innerHTML="<span class=err>"+(r.reason=="unknown"?"המספר לא מזוהה":(r.reason=="sms_failed"?"שליחת SMS נכשלה (בדוק Twilio)":"שגיאה"))+"</span>";}
  }).catch(function(){$("m1").innerHTML="<span class=err>שגיאה</span>";});}
function startOtp(){if(!("OTPCredential" in window))return;try{navigator.credentials.get({otp:{transport:["sms"]}}).then(function(o){if(o&&o.code){$("code").value=o.code;verify();}}).catch(function(){});}catch(e){}}
function verify(){var p=$("phone").value.trim(),c=$("code").value.trim();if(!c){alert("הזן קוד");return;}$("m2").textContent="בודק…";
  api("/api/auth/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone:p,code:c})}).then(function(r){
    if(r.ok){TOKEN=r.token;ROLE=r.role;DROLE=r.drole||"";NAME=r.name;DEV=!!r.dev;TABS=r.tabs||null;try{localStorage.setItem("fbTok",TOKEN);localStorage.setItem("fbRole",ROLE);localStorage.setItem("fbDrole",DROLE);localStorage.setItem("fbName",NAME);localStorage.setItem("fbDev",DEV?"1":"");localStorage.setItem("fbTabs",JSON.stringify(TABS||null));}catch(e){}enter();}
    else{$("m2").innerHTML="<span class=err>"+(r.reason=="wrong"?"קוד שגוי":(r.reason=="expired"?"הקוד פג":"שגיאה"))+"</span>";}
  }).catch(function(){$("m2").innerHTML="<span class=err>שגיאה</span>";});}
function enter(){$("login").classList.add("hidden");$("appui").classList.remove("hidden");var bn=$("brandname");if(bn){var _nm=(NAME||"").trim();var _ini=_nm?_nm.split(/\s+/).slice(0,2).map(function(w){return (w||"").charAt(0);}).join(""):"";bn.textContent=_ini;bn.title=_nm?("שלום, "+_nm):"";}if(DROLE=="manager"||DROLE=="developer"||DEV){loadAgents();var ma=$("mi-activity"),mim=$("mi-imp"),mtl=$("mi-testlogin");if(ma)ma.classList.remove("hidden");if(mim)mim.classList.remove("hidden");if(mtl)mtl.classList.remove("hidden");}if(DEV){var md=$("mi-dev");if(md)md.classList.remove("hidden");}applyTabPerms();tab(firstAllowedTab());setTimeout(loadNbBanner,1500);}
function firstAllowedTab(){var order=["calls","buyers","sigs","props","excl","newborn"];if(!TABS||!TABS.length)return "calls";for(var i=0;i<order.length;i++){if(TABS.indexOf(order[i])>=0)return order[i];}return "calls";}
function applyTabPerms(){
  var navKeys=["calls","buyers","sigs","props","excl","newborn"];
  document.querySelectorAll(".tab").forEach(function(t){var k=t.dataset.t;if(navKeys.indexOf(k)<0)return;t.style.display=(!TABS||!TABS.length||TABS.indexOf(k)>=0)?"":"none";});
  var mr=$("mi-report");if(mr)mr.style.display=(!TABS||!TABS.length||TABS.indexOf("report")>=0)?"":"none";
  var ma=$("mi-activity");if(ma&&TABS&&TABS.length&&TABS.indexOf("activity")<0)ma.style.display="none";
  if(TABS&&TABS.length&&navKeys.indexOf(TABNOW)>=0&&TABS.indexOf(TABNOW)<0){tab(firstAllowedTab());}
}

// ── קונסולת מפתח ──────────────────────────────────────────────
function openDevConsole(){if(!DEV)return;var b=document.body;b.style.position="";b.style.top="";TABNOW="dev";document.querySelectorAll(".tab").forEach(function(x){x.classList.remove("on");});if(timer){clearInterval(timer);timer=null;}$("view").innerHTML='<div class=card><div style="display:flex;justify-content:space-between;align-items:center"><b>קונסולת ניהול</b><button class="btn-ghost" onclick="tab(\'calls\')">✕ סגור</button></div><div class=muted style="margin-top:4px">זהות סוכנים, כינויי שם והתאמות · מפתח בלבד</div><div style="margin-top:6px"><button class="btn-ghost" onclick="devDiag()">🔧 בדיקת חיבור</button><span id=devdiag class=muted></span></div></div><div id=devbody><div class=muted style="text-align:center;padding:20px">טוען…</div></div><div id=devperms></div><div id=devteams></div><div id=devcontracts></div>';loadDevPeople();loadRolePerms();loadTeams();loadContracts();}
function devDiag(){$("devdiag").textContent=" בודק…";api("/api/dev/diag").then(function(r){$("devdiag").textContent=" "+((r&&r.msg)||"שגיאה");}).catch(function(){$("devdiag").textContent=" שגיאת רשת";});}
function loadDevPeople(){api("/api/dev/people").then(function(r){if(!r||!r.ok){$("devbody").innerHTML='<div class=card>שגיאה בטעינה</div>';return;}renderDevPeople(r);}).catch(function(){$("devbody").innerHTML='<div class=card>שגיאה</div>';});}
var DEVAGENTS=[],DEVDATA=null,DEVALL=false,DEVFILTER="";
function devToggleAll(){DEVALL=!DEVALL;if(DEVDATA)renderDevPeople(DEVDATA);}
function devSearch(v){DEVFILTER=v;if(DEVDATA)renderDevPeople(DEVDATA);var el=$("devsearch");if(el){el.focus();try{el.setSelectionRange(el.value.length,el.value.length);}catch(e){}}}
function renderDevPeople(r){DEVDATA=r;DEVAGENTS=r.agents||[];
  var opts='<option value="">— שייך לסוכן —</option>'+DEVAGENTS.map(function(a){return '<option value="'+esc(a.name)+'">'+esc(a.name)+'</option>';}).join("");
  function block(title,arr,pre){if(!arr||!arr.length)return '<div class=card><b>'+title+'</b><div class=muted style="margin-top:6px">הכל מזוהה ✓</div></div>';
    return '<div class=card><b>'+title+' ('+arr.length+')</b><div class=muted style="margin:4px 0 8px">שמות שלא מתאימים לאף סוכן — שייך לקיים או צור חדש:</div>'+arr.map(function(u,i){var id=pre+i;
      return '<div style="padding:8px 0;border-bottom:1px solid rgba(127,127,127,.18)"><div><b>'+esc(u.name)+'</b> <span class=muted>('+u.count+')</span></div><select id="'+id+'" class="chip" style="width:100%;box-sizing:border-box;margin-top:5px">'+opts+'</select><div style="display:flex;gap:6px;margin-top:5px"><button class="btn-gold" style="flex:1" onclick="devAssign(\''+encodeURIComponent(u.name)+'\',\''+id+'\')">שייך</button><button class="btn-ghost" style="flex:1" onclick="devNewAgent(\''+encodeURIComponent(u.name)+'\')">➕ חדש</button></div></div>';}).join("")+'</div>';}
  var defc='<div class=card><b>🐥 ימי נכס נולד — ברירת מחדל</b><div class=muted style="margin:4px 0 6px">ימים לכל סוכן ללא הגדרה אישית</div><div style="display:flex;gap:6px;align-items:center"><input id="nbdef" class="chip" style="width:90px;box-sizing:border-box" type="number" value="'+esc(r.nbDefault)+'"><button class="btn-gold" style="flex:1" onclick="devSetDefault()">שמור</button></div></div>';
  var NSHOW=5;var flt=(DEVFILTER||"").trim();
  function devCard(a,i){return '<div style="padding:10px 0;border-bottom:1px solid rgba(127,127,127,.18)"><div style="font-weight:600">'+esc(a.name)+((a.aliases&&a.aliases.length)?' <span class=muted style="font-weight:400">('+a.aliases.map(esc).join(", ")+')</span>':'')+'</div><div style="display:flex;gap:6px;margin-top:6px"><input id="vp'+i+'" class="chip" style="flex:1;min-width:0;box-sizing:border-box" placeholder="📞 וירטואלי" value="'+esc(a.vphone||"")+'"><input id="nb'+i+'" class="chip" style="width:72px;box-sizing:border-box" type="number" placeholder="ימים" value="'+esc(a.nbHidden?"":a.nbDelay)+'"></div><div style="display:flex;gap:12px;margin-top:7px;align-items:center"><label class=muted style="display:flex;gap:4px;align-items:center"><input type=checkbox id="hd'+i+'" '+(a.nbHidden?"checked":"")+'>מוסתר</label><button class="btn-gold" style="flex:1" onclick="devSaveAgent('+i+')">שמור</button></div><div style="display:flex;gap:6px;margin-top:6px;align-items:center"><span class=muted style="font-size:12px">תפקיד:</span><select id="rl'+i+'" class="chip" style="flex:1;min-width:0" onchange="devSetRole('+i+')">'+roleOpts(a.role)+'</select></div></div>';}
  var cards="";DEVAGENTS.forEach(function(a,i){var show=flt?(String(a.name).indexOf(flt)>=0):(DEVALL||i<NSHOW);if(show)cards+=devCard(a,i);});
  if(flt&&!cards)cards='<div class=muted style="padding:8px 0">לא נמצא סוכן בשם זה.</div>';
  var more=(!flt&&DEVAGENTS.length>NSHOW)?('<div style="text-align:center;margin-top:10px"><button class="btn-ghost" onclick="devToggleAll()">'+(DEVALL?"פחות ▲":("עוד "+(DEVAGENTS.length-NSHOW)+" ▼"))+'</button></div>'):'';
  var srch='<input id="devsearch" class="chip" style="width:100%;box-sizing:border-box;margin:2px 0 8px" placeholder="🔍 חפש סוכן לפי שם" value="'+esc(flt)+'" oninput="devSearch(this.value)">';
  var dir='<div class=card><b>👥 ספריית סוכנים ('+DEVAGENTS.length+')</b><div class=muted style="margin:4px 0 6px">מספר וירטואלי · ימי נכס נולד (ריק=ברירת מחדל, ✓מוסתר=לא רואה כלום) · תפקיד</div>'+srch+cards+more+'<div style="display:flex;gap:6px;margin-top:12px"><input id="newag" class="chip" style="flex:1;min-width:0;box-sizing:border-box" placeholder="שם סוכן חדש"><button class="btn-gold" onclick="devAddAgent()">➕ הוסף</button></div></div>';
  $("devbody").innerHTML=block("🔴 לא מזוהה — חתימות",r.unmatchedSignings,"sg")+block("🔴 לא מזוהה — נכסים",r.unmatchedListings,"ls")+defc+dir;renderTeams();}
function devPost(url,body){api(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(r){if(r&&r.ok){loadDevPeople();}else{alert("השמירה נכשלה — לחץ '🔧 בדיקת חיבור' כדי לראות למה (כנראה ה-Apps Script לא פרוס בגרסה חדשה).");}}).catch(function(){alert("שגיאת רשת");});}
function devAssign(nameEnc,selId){var sel=$(selId);var agent=sel?sel.value:"";if(!agent){alert("בחר סוכן מהרשימה");return;}devPost("/api/dev/alias",{alias:decodeURIComponent(nameEnc),agent:agent});}
function devNewAgent(nameEnc){var name=decodeURIComponent(nameEnc);if(!confirm("ליצור סוכן חדש בשם: "+name+"?"))return;devPost("/api/dev/agent_add",{name:name});}
function devAddAgent(){var el=$("newag");var name=el?el.value.trim():"";if(!name){alert("הקלד שם סוכן");return;}devPost("/api/dev/agent_add",{name:name});}
function devSaveAgent(i){var a=DEVAGENTS[i];if(!a)return;var hid=$("hd"+i).checked;var nb=$("nb"+i).value.trim();devPost("/api/dev/agent_update",{name:a.name,vphone:$("vp"+i).value.trim(),newbornDelay:(hid?"hidden":nb)});}
function devSetDefault(){devPost("/api/dev/newborn_default",{days:$("nbdef").value.trim()});}
function roleOpts(cur){var rs=[["","— תפקיד (ברירת מחדל) —"],["manager","מנהל"],["accountant","מנהלת חשבונות"],["secretary","מזכירה"],["coordinator","מתאמת"],["agent","סוכן"]];return rs.map(function(x){return '<option value="'+x[0]+'"'+(cur==x[0]?" selected":"")+'>'+x[1]+'</option>';}).join("");}
function devSetRole(i){var a=DEVAGENTS[i];if(!a)return;var ph=a.phone||(a.phones&&a.phones[0]);if(!ph){alert("לסוכן אין מספר טלפון — אי אפשר לשייך תפקיד");loadDevPeople();return;}devPost("/api/dev/role",{phone:ph,role:$("rl"+i).value});}
var ROLEPERMS={};
function loadRolePerms(){api("/api/dev/roleperms").then(function(r){if(!r||!r.ok)return;renderRolePerms(r);}).catch(function(){});}
function renderRolePerms(r){ROLEPERMS=r.perms||{};
  var roles=[["manager","מנהל"],["accountant","מנהלת חשבונות"],["secretary","מזכירה"],["coordinator","מתאמת"],["agent","סוכן"]];
  var tabs=[["calls","שיחות"],["buyers","קונים"],["sigs","חתימות"],["props","נכסים במשרד"],["excl","שת״פ"],["newborn","נכס נולד"],["report","דוחות"],["activity","עדכונים"]];
  var html='<div class=card><b>🔐 הרשאות טאבים לפי תפקיד</b><div class=muted style="margin:4px 0 8px">סמן אילו טאבים כל תפקיד רואה (שמירה לכל תפקיד בנפרד).</div>';
  html+=roles.map(function(rl){var cur=ROLEPERMS[rl[0]]||[];
    return '<div style="padding:9px 0;border-bottom:1px solid rgba(127,127,127,.18)"><div style="font-weight:600;margin-bottom:5px">'+rl[1]+'</div><div style="display:flex;flex-wrap:wrap;gap:10px">'+tabs.map(function(t){return '<label class=muted style="display:flex;gap:3px;align-items:center"><input type=checkbox id="p_'+rl[0]+'_'+t[0]+'" '+(cur.indexOf(t[0])>=0?"checked":"")+'>'+t[1]+'</label>';}).join("")+'</div><div style="margin-top:6px"><button class="btn-gold" onclick="devSavePerms(\''+rl[0]+'\')">שמור '+rl[1]+'</button></div></div>';
  }).join("")+'</div>';
  $("devperms").innerHTML=html;}
function devSavePerms(role){var tabs=["calls","buyers","sigs","props","excl","newborn","report","activity"];var sel=[];tabs.forEach(function(t){var c=$("p_"+role+"_"+t);if(c&&c.checked)sel.push(t);});api("/api/dev/roleperms",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({role:role,tabs:sel})}).then(function(r){if(r&&r.ok)loadRolePerms();else alert("שמירה נכשלה");}).catch(function(){alert("שגיאה");});}
var TEAMS=[];
function loadTeams(){api("/api/dev/teams").then(function(r){if(r&&r.ok){TEAMS=r.teams||[];renderTeams();}}).catch(function(){});}
function renderTeams(){if(!$("devteams"))return;
  var aopts='<option value="">— בחר סוכן —</option>'+(DEVAGENTS||[]).map(function(a){return '<option value="'+esc(a.name)+'">'+esc(a.name)+'</option>';}).join("");
  var html='<div class=card><b>👥 צוותים (מי רואה את מי)</b><div class=muted style="margin:4px 0 8px">חברי צוות רואים זה את נתוני זה, והדוח שלהם משותף (סכום הצוות).</div>';
  html+=(TEAMS.length?TEAMS.map(function(t,i){return '<div style="padding:8px 0;border-bottom:1px solid rgba(127,127,127,.18)"><div><b>'+t.map(esc).join(" + ")+'</b></div><div style="display:flex;gap:6px;margin-top:5px"><select id="tm'+i+'" class="chip" style="flex:1;min-width:0">'+aopts+'</select><button class="btn-gold" onclick="teamAdd('+i+')">➕ הוסף</button><button class="btn-ghost" onclick="teamDel('+i+')">✖</button></div></div>';}).join(""):'<div class=muted style="padding:4px 0">אין צוותים מוגדרים.</div>');
  html+='<div style="margin-top:10px"><div class=muted style="margin-bottom:4px">צוות חדש:</div><div style="display:flex;gap:6px;flex-wrap:wrap"><select id="tnew1" class="chip" style="flex:1;min-width:120px">'+aopts+'</select><select id="tnew2" class="chip" style="flex:1;min-width:120px">'+aopts+'</select><button class="btn-gold" onclick="teamCreate()">צור</button></div></div></div>';
  $("devteams").innerHTML=html;}
function saveTeams(){api("/api/dev/teams",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({teams:TEAMS})}).then(function(r){if(r&&r.ok)loadTeams();else alert("שמירה נכשלה");}).catch(function(){alert("שגיאה");});}
function teamCreate(){var a=$("tnew1").value,b=$("tnew2").value;if(!a||!b||a==b){alert("בחר שני סוכנים שונים");return;}TEAMS.push([a,b]);saveTeams();}
function teamAdd(i){var v=$("tm"+i).value;if(!v){alert("בחר סוכן");return;}if(TEAMS[i].indexOf(v)<0)TEAMS[i].push(v);saveTeams();}
function teamDel(i){if(!confirm("להסיר את הצוות?"))return;TEAMS.splice(i,1);saveTeams();}
var CONTRACTS={},CTYPES={},CTYPE="seller";
function loadContracts(){api("/api/dev/contract").then(function(r){if(r&&r.ok){CONTRACTS=r.contracts||{};CTYPES=r.types||{};if(!CTYPES[CTYPE]){var ks=Object.keys(CTYPES);if(ks.length)CTYPE=ks[0];}renderContracts();}}).catch(function(){});}
function renderContracts(){if(!$("devcontracts"))return;
  var topts=Object.keys(CTYPES).map(function(k){return '<option value="'+k+'"'+(k==CTYPE?" selected":"")+'>'+esc(CTYPES[k])+'</option>';}).join("");
  var ph=["{תאריך}","{שם_הסוכן}","{שם_הלקוח}","{טלפון_הלקוח}","{תז_הלקוח}","{כתובת_הנכס}","{מחיר_מבוקש}","{שכירות_מבוקשת}","{עמלת_קניה}","{עמלת_שכירות}","{תקופת_בלעדיות}","{הערות}"];
  var html='<div class=card><b>📄 נוסחי הסכמים (לעריכה)</b><div class=muted style="margin:4px 0 8px">הדבק כאן את הנוסח המשפטי שלך. המשתנים יתמלאו אוטומטית בזמן החתימה. (שמור כל סוג בנפרד)</div>';
  html+='<select id="ctype" class="chip" style="width:100%;box-sizing:border-box;margin-bottom:6px" onchange="ctypeChange(this.value)">'+topts+'</select>';
  html+='<textarea id="cbody" class="chip" style="width:100%;box-sizing:border-box;min-height:220px;font-family:inherit;line-height:1.6" placeholder="הדבק כאן את נוסח ההסכם...">'+esc(CONTRACTS[CTYPE]||"")+'</textarea>';
  html+='<div class=muted style="margin:6px 0;font-size:12px">משתנים זמינים: '+ph.map(esc).join(" · ")+'</div>';
  html+='<button class="btn-gold" style="width:100%" onclick="saveContract()">שמור נוסח</button></div>';
  $("devcontracts").innerHTML=html;}
function ctypeChange(v){var ta=$("cbody");if(ta)CONTRACTS[CTYPE]=ta.value;CTYPE=v;renderContracts();}
function saveContract(){var ta=$("cbody");if(!ta)return;CONTRACTS[CTYPE]=ta.value;api("/api/dev/contract",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({type:CTYPE,body:ta.value})}).then(function(r){if(r&&r.ok)alert("נשמר ✓");else alert("שמירה נכשלה");}).catch(function(){alert("שגיאה");});}
function tab(t){var _b=document.body;_b.style.position="";_b.style.top="";_b.style.left="";_b.style.right="";_b.style.width="";TABNOW=t;document.querySelectorAll(".tab").forEach(function(x){x.classList.toggle("on",x.dataset.t==t);});if(timer){clearInterval(timer);timer=null;}render();setTimeout(shareUpd,50);}
function render(){if(TABNOW=="calls")viewCalls();else if(TABNOW=="sigs")viewSigs();else if(TABNOW=="activity")viewActivity();else if(TABNOW=="report")viewReport();else if(TABNOW=="newborn")viewNewborn();else viewSearch(TABNOW);}
var REPTEXT="";
function kpi(n,l){return "<div class=stat><div class=n>"+n+"</div><div class=l>"+l+"</div></div>";}
function viewReport(){
  var MN=["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"];
  var cm=new Date().getMonth()+1,opts='<option value="">החודש</option>';
  for(var m=1;m<=cm;m++)opts+='<option value="'+m+'">'+MN[m-1]+'</option>';
  $("view").innerHTML='<div class=card><h2>דוחות מנהל</h2><div class=chips id=rpc><div class=chip data-r=lastweek>שבוע שעבר</div><div class=chip data-r=week>השבוע</div><select id=monthsel class="chip monthsel on" title="בחר חודש">'+opts+'</select><div class=chip data-r=year>השנה</div></div></div><div id=rep></div>';
  document.querySelectorAll("#rpc .chip").forEach(function(c){if(c.tagName=="SELECT")return;c.onclick=function(){document.querySelectorAll("#rpc .chip").forEach(function(x){x.classList.remove("on");});c.classList.add("on");var ms=$("monthsel");if(ms){ms.classList.remove("on");ms.value="";}loadReport(c.dataset.r);};});
  var msel=$("monthsel");if(msel)msel.onchange=function(){document.querySelectorAll("#rpc .chip").forEach(function(x){x.classList.remove("on");});msel.classList.add("on");if(this.value)loadReport("month",this.value);else loadReport("month");};
  loadReport("month");
}
var REPEXC=[],REPSIGS=[],REPSIGB=null;
function toggleSigs(){var b=$("sigslist");if(!b)return;if(b.innerHTML){b.innerHTML="";return;}var g=REPSIGB||{};
  var head="<div class=grid>"+kpi(g.konim+" ("+g.pctK+"%)","קונים")+kpi(g.bladiut+" ("+g.pctB+"%)","בלעדיות")+kpi(g.skhirut+" ("+g.pctS+"%)","שכירויות")+kpi(g.total,"סה״כ")+"</div>";
  var list;
  if(REPSIGS&&REPSIGS.length){var arr=REPSIGS.slice().sort(function(a,c){return String(c.date).localeCompare(String(a.date));});
    list=arr.map(function(e){return "<div class=row><b>"+esc(e.type||"חתימה")+"</b>"+(e.client?" · "+esc(e.client):"")+"<div class=muted>"+[e.address?esc(e.address):"",e.agent?"👤 "+esc(e.agent):"",e.date?"📅 "+fmtD(e.date):""].filter(Boolean).join(" · ")+"</div></div>";}).join("");
  }else{list="<div class=muted>אין חתימות בתקופה.</div>";}
  b.innerHTML="<div class=card><h2>חתימות ("+(g.total||0)+")</h2>"+head+"<div style=margin-top:8px>"+list+"</div></div>";}
function fmtD(s){s=String(s||"");if(s.indexOf("T")>-1){var pp=s.slice(0,10).split("-");if(pp.length==3)return pp[2]+"/"+pp[1]+"/"+pp[0];}return s.slice(0,16);}
function toggleExc(){var b=$("exclist");if(!b)return;if(b.innerHTML){b.innerHTML="";return;}if(!REPEXC||!REPEXC.length){b.innerHTML="<div class=card><div class=muted>אין בלעדיות בתקופה.</div></div>";return;}var list=REPEXC.slice().sort(function(a,c){return String(c.date).localeCompare(String(a.date));});b.innerHTML="<div class=card><h2>🏘️ בלעדיות ("+REPEXC.length+")</h2>"+list.map(function(e){return "<div class=row><b>"+esc(e.address||"—")+"</b><div class=muted>"+[e.agent?"👤 "+esc(e.agent):"",e.date?"📅 "+fmtD(e.date):""].filter(Boolean).join(" · ")+"</div></div>";}).join("")+"</div>";}
function toggleAds(){var b=$("adslist");if(!b)return;if(b.innerHTML){b.innerHTML="";return;}
  b.innerHTML="<div class=card><div class=muted>טוען מודעות… ⏳</div></div>";
  api("/api/my/properties",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({as:IMP||""})}).then(function(r){
    if(!r||!r.ok){b.innerHTML="<div class=card class=err>שגיאה</div>";return;}
    var items=r.results||[];
    if(!items.length){b.innerHTML="<div class=card><div class=muted>אין מודעות על שם הסוכן.</div></div>";return;}
    b.innerHTML="<div class=card><h2>מודעות הסוכן ("+items.length+")</h2>"+items.map(function(x){var y={};for(var k in x)y[k]=x[k];y.own=false;return card("props",y);}).join("")+"</div>";
  }).catch(function(){b.innerHTML="<div class=card><div class=err>שגיאה</div></div>";});}
function loadReport(p,month){$("rep").innerHTML="<div class=card>טוען…</div>";api("/api/report?period="+p+(month?"&month="+month:"")+((typeof IMP!="undefined"&&IMP)?("&as="+encodeURIComponent(IMP)):"")).then(function(r){
  if(!r.ok){if(r.auth===false){relogin();return;}$("rep").innerHTML="<div class=card err>"+(r.reason=="forbidden"?"למנהל בלבד":"שגיאה")+"</div>";return;}
  REPTEXT=r.wa_text;var sm=r.summary,c=sm.calls,sg=sm.sigs;REPEXC=sm.exclusives||[];REPSIGS=sm.sigsList||[];REPSIGB=sg;
  var h="<div class=card><div class=muted>📊 "+esc(r.label)+(r.scope?" · "+esc(r.scope):"")+" · "+r.from+"–"+r.to+"</div><div class=grid>"+kpi(c.total,"שיחות")+kpi(c.answered,"נענו")+kpi(c.rate+"%","אחוז מענה")+"<div class=stat style=cursor:pointer onclick=toggleSigs()><div class=n>"+sg.total+"</div><div class=l>חתימות 👁</div></div>"+"<div class=stat style=cursor:pointer onclick=toggleExc()><div class=n>"+sm.exclusives.length+"</div><div class=l>בלעדיות 👁</div></div>"+"<div class=stat style=cursor:pointer onclick=toggleAds()><div class=n>"+(r.listings!=null?r.listings:0)+"</div><div class=l>מודעות 👁</div></div></div></div><div id=sigslist></div><div id=exclist></div><div id=adslist></div>";
  if(r.insights&&r.insights.length){h+="<div class=card><h2>תובנות</h2>"+r.insights.map(function(t){return "<div class=insight>"+esc(t)+"</div>";}).join("")+"</div>";}
  if(r.scope=="כל המשרד"){var ag="<table><tr><th style=text-align:start>מתווך</th><th>שיחות</th><th>נענו</th><th>%</th></tr>";sm.agents.slice(0,10).forEach(function(a,i){ag+="<tr><td>"+(i+1)+". "+esc(a.name)+"</td><td style=text-align:center>"+a.total+"</td><td style=text-align:center>"+a.answered+"</td><td style=text-align:center>"+a.rate+"%</td></tr>";});ag+="</table>";
  h+="<div class=card><h2>מתווכים מובילים</h2>"+ag+"</div>";
  if(sm.topGius&&sm.topGius.length){var tg="<table><tr><th style=text-align:start>מתווך</th><th>נכסים</th></tr>";sm.topGius.forEach(function(a,i){tg+="<tr><td>"+(i+1)+". "+esc(a.name)+"</td><td style=text-align:center><b>"+a.n+"</b></td></tr>";});tg+="</table>";h+="<div class=card><h2>מובילים בגיוס נכסים</h2>"+tg+"</div>";}
  if(sm.topKonim&&sm.topKonim.length){var tk="<table><tr><th style=text-align:start>מתווך</th><th>קונים</th></tr>";sm.topKonim.forEach(function(a,i){tk+="<tr><td>"+(i+1)+". "+esc(a.name)+"</td><td style=text-align:center><b>"+a.n+"</b></td></tr>";});tk+="</table>";h+="<div class=card><h2>מובילים בהחתמת קונים</h2>"+tk+"</div>";}}
  if(r.shtaf&&r.shtaf.length){var tot=(r.shtaf_total!=null?r.shtaf_total:r.shtaf.reduce(function(a,o){return a+o.count;},0));var noff=(r.shtaf_offices!=null?r.shtaf_offices:r.shtaf.length);var st="<table><tr><th style=text-align:start>שם המשרד</th><th>נכסים</th></tr>";r.shtaf.forEach(function(o){st+="<tr><td>"+(isOurOffice(o.office)?"<span class=ouroffice>🏠 "+esc(o.office)+"</span>":esc(o.office))+"</td><td style=text-align:center><b>"+o.count+"</b></td></tr>";});st+="</table>";h+="<div class=card><h2>גיוס נכסים בשת״פ</h2><div class=muted style=margin-bottom:8px>"+esc(r.label)+" · "+noff+" משרדים · סה״כ "+tot+" נכסים"+(noff>10?" · מציג 10 מובילים":"")+"</div>"+st+"</div>";}
  if(r.scope=="כל המשרד"&&r.nbCities&&r.nbCities.length){var nc="<table><tr><th style=text-align:start>עיר</th><th>נכסים</th></tr>";r.nbCities.forEach(function(c){nc+="<tr><td>"+esc(c.city)+"</td><td style=text-align:center><b>"+c.n+"</b></td></tr>";});nc+="</table>";h+="<div class=card><h2>נכס נולד לפי ערים</h2><div class=muted style=margin-bottom:8px>"+esc(r.label)+" · סה״כ "+(r.nbTotal||0)+" נכסים</div>"+nc+"</div>";}
  h+="<div class=card><button class=gold onclick=exportWa()>📲 ייצוא לוואטסאפ</button><button class=sec onclick=copyRep()>📋 העתק טקסט</button></div>";
  $("rep").innerHTML=h;
}).catch(function(){$("rep").innerHTML="<div class=card err>שגיאה</div>";});}
function exportWa(){window.open("https://wa.me/?text="+encodeURIComponent(REPTEXT),"_blank");}
function copyRep(){try{navigator.clipboard.writeText(REPTEXT).then(function(){alert("הטקסט הועתק");});}catch(e){alert("העתקה נכשלה");}}
function viewActivity(){
  $("view").innerHTML='<div class=card><h2>📣 עדכונים — שימוש במערכת</h2><div class=muted id=acthdr>טוען…</div></div><div id=actlist></div>';
  loadActivity();timer=setInterval(loadActivity,60000);
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

function rangeChips(){var rs=[["day","היום"],["week","השבוע"],["month","החודש"],["all","הכל"]];return '<div class=chips id=rc>'+rs.map(function(x){return '<div class="chip'+(RANGE==x[0]?" on":"")+'" data-r='+x[0]+'>'+x[1]+'</div>';}).join("")+'</div>';}
function bindChips(reload){document.querySelectorAll("#rc .chip").forEach(function(c){c.onclick=function(){document.querySelectorAll("#rc .chip").forEach(function(x){x.classList.remove("on");});c.classList.add("on");RANGE=c.dataset.r;seenCall=0;seenSig=0;reload();};});}
function inRange(ts){var d=new Date();var start;if(RANGE=="day"){start=new Date();start.setHours(0,0,0,0);}else if(RANGE=="week"){start=new Date();start.setDate(d.getDate()-d.getDay());start.setHours(0,0,0,0);}else if(RANGE=="month"){start=new Date(d.getFullYear(),d.getMonth(),1);}else{start=new Date(d.getFullYear(),0,1);}return ts>=start.getTime()/1000;}
function periodLabel(){return RANGE=="day"?"היום":(RANGE=="week"?"השבוע":(RANGE=="month"?"החודש":"מתחילת השנה"));}

function isMulti(){return (ROLE=="admin"||ROLE=="coordinator")&&!IMP;}
function scopeLabel(){if(IMP)return ' <span class=badge>👁 צופה כ: '+esc(IMPNAME)+'</span>';return ROLE=="admin"?' <span class=badge>כל הסוכנים</span>':(ROLE=="coordinator"?' <span class=badge>הסוכנים שלי</span>':' — '+esc(NAME));}
function setImp(v){IMP=v||null;IMPNAME=null;if(IMP){var sel=$("impsel");for(var i=0;i<sel.options.length;i++){if(sel.options[i].value==IMP){IMPNAME=sel.options[i].textContent;break;}}}loadNbBanner();render();}
function loadAgents(){api("/api/agents").then(function(r){if(!r||!r.ok)return;var sel=$("impsel"),ts=$("testsel");r.agents.forEach(function(a){if(sel){var o=document.createElement("option");o.value=a.name;o.textContent=a.name;sel.appendChild(o);}if(ts){var o2=document.createElement("option");o2.value=a.name;o2.textContent=a.name;ts.appendChild(o2);}});}).catch(function(){});}
function loginAsAgent(name){if(!name)return;if(!confirm("להיכנס למערכת כסוכן '"+name+"' (בדיקה אמיתית)?\nכדי לחזור למנהל — צא והתחבר מחדש עם המספר שלך.")){var t=$("testsel");if(t)t.value="";return;}
  api("/api/admin/loginas",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name})}).then(function(r){
    if(!r||!r.ok){alert("נכשל"+(r&&r.reason?" ("+r.reason+")":""));return;}
    try{localStorage.setItem("fbTok",r.token);localStorage.setItem("fbRole",r.role);localStorage.setItem("fbDrole",r.drole||"");localStorage.setItem("fbName",r.name);localStorage.setItem("fbDev","0");if(r.tabs)localStorage.setItem("fbTabs",JSON.stringify(r.tabs));else localStorage.removeItem("fbTabs");}catch(e){}
    closeMenu();location.reload();
  }).catch(function(){alert("שגיאה");});}
var HIDDENMODE=false;
function toggleHidden(){HIDDENMODE=!HIDDENMODE;loadCalls();}
function hideCall(id){if(!id){alert("חסר מזהה");return;}api("/api/calls/hide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})}).then(function(r){if(r&&r.ok)loadCalls();else alert("הסתרה נכשלה");}).catch(function(){alert("שגיאה");});}
function unhideCall(id){if(!id)return;api("/api/calls/unhide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})}).then(function(r){if(r&&r.ok)loadCalls();else alert("שחזור נכשל");}).catch(function(){alert("שגיאה");});}
function viewCalls(){
  $("view").innerHTML='<div class=card><h2>שיחות שלי'+scopeLabel()+'</h2>'+rangeChips()+'<div class=muted id=live>טוען…</div><div class=grid id=callkpi></div><div style=text-align:center;margin-top:6px><span id=vphone class=vphone></span><span class=hlink id=htoggle onclick=toggleHidden()>הצג מוסתרות</span></div></div><div id=calls></div>';
  bindChips(loadCalls);seenCall=0;loadCalls();timer=setInterval(loadCalls,45000);
}
function viewSigs(){
  $("view").innerHTML='<div class=card><h2 style="margin:0 0 2px">חתימות שלי'+scopeLabel()+'</h2><div class=sgbtns><button class="btn-gold sgbtn" onclick="openSignForm(\'buyer\')"><svg class=eico viewBox=\'0 0 18 18\'><circle cx=\'9\' cy=\'6\' r=\'2.6\'/><path d=\'M4 15a5 5 0 0 1 10 0\'/></svg>החתם מתעניין</button><button class="btn-gold sgbtn" onclick="openSignForm(\'seller\')"><svg class=eico viewBox=\'0 0 18 18\'><rect x=\'4.2\' y=\'2.6\' width=\'9.6\' height=\'12.8\' rx=\'1\'/><path d=\'M7 6h1.2M9.8 6H11M7 9h1.2M9.8 9H11M7 12h4\'/><path d=\'M2.6 15.4h12.8\'/></svg>החתם בעל נכס</button></div>'+rangeChips()+'<div class=muted id=live>טוען…</div></div><div id=sigs></div>';
  bindChips(loadSigs);seenSig=0;loadSigs();timer=setInterval(loadSigs,60000);
}
// ── מסך החתמת לקוח (במקום) ─────────────────────────────────────
var SG_DATE="",SG_CONTRACT="",SG_AUD="buyer";
function validILID(v){var s=(v||"").replace(/\D/g,"");if(!s||s.length>9)return false;s=("000000000"+s).slice(-9);var t=0;for(var i=0;i<9;i++){var d=parseInt(s[i],10)*(i%2===0?1:2);t+=d>9?d-9:d;}return t%10===0;}
function sgCheckId(){var el=$("sg_cid"),m=$("sg_idmsg");if(!el||!m)return;var v=el.value.trim();if(!v){m.textContent="";return;}if(validILID(v)){m.textContent="✓ תעודת זהות תקינה";m.style.color="#1a7f37";}else{m.textContent="✗ תעודת זהות לא תקינה";m.style.color="#c0322f";}}
function initSigPad(id){var c=$(id);if(!c)return;var rect=c.getBoundingClientRect();c.width=rect.width||320;c.height=rect.height||160;var ctx=c.getContext("2d");ctx.lineWidth=2.2;ctx.lineCap="round";ctx.lineJoin="round";ctx.strokeStyle="#0D1B2A";var drawing=false;
  function pos(e){var r=c.getBoundingClientRect();var t=(e.touches&&e.touches[0])?e.touches[0]:e;return {x:t.clientX-r.left,y:t.clientY-r.top};}
  function st(e){drawing=true;var p=pos(e);ctx.beginPath();ctx.moveTo(p.x,p.y);e.preventDefault();}
  function mv(e){if(!drawing)return;var p=pos(e);ctx.lineTo(p.x,p.y);ctx.stroke();c.dataset.signed="1";e.preventDefault();}
  function en(){drawing=false;}
  c.onmousedown=st;c.onmousemove=mv;c.onmouseup=en;c.onmouseleave=en;c.ontouchstart=st;c.ontouchmove=mv;c.ontouchend=en;}
function clearSig(id){var c=$(id);if(!c)return;c.getContext("2d").clearRect(0,0,c.width,c.height);c.dataset.signed="";}
function sgFill(body,v){
  var addrTxt=(v.props&&v.props.length)?v.props.map(function(p){return p.addr;}).join(", "):(v.addr||"");
  var priceTxt=(v.props&&v.props.length)?v.props.map(function(p){return p.price;}).filter(Boolean).join(" / "):(v.price||"");
  var map={
  "SALE_FEE":(v.cbuy?(v.cbuy+(v.cbuyunit=="₪"?" ₪":"%")):"____"),"RENT_FEE":(v.crent?(v.crent+" חודשי שכירות"):"____"),
  "EXCLUSIVE_FROM":(v.exfrom||"____"),"EXCLUSIVE_TO":(v.exto||"____"),"CON_REF_ID":(v.refid||"____"),"CON_REF_DATE":(v.refdate||v.date),
  "{תאריך}":v.date,"{שם_הסוכן}":v.agent,"{שם_הלקוח}":v.cname,"{טלפון_הלקוח}":v.cphone,"{תז_הלקוח}":v.cid,"{כתובת_הנכס}":addrTxt,"{מחיר_מבוקש}":priceTxt,"{עמלת_קניה}":v.cbuy,"{עמלת_שכירות}":v.crent};
  var out=body||"";for(var k in map){out=out.split(k).join(map[k]==null?"":map[k]);}return out;}
function sgResolveKey(){var a=SG_AUD||"buyer";
  if(a=="buyer"){var b=$("sg_buy")&&$("sg_buy").checked,r=$("sg_rent")&&$("sg_rent").checked;return (b&&r)?"buyer_both":(r&&!b?"buyer_rent":"buyer_buy");}
  var s=$("sg_sell")&&$("sg_sell").checked,sr=$("sg_srent")&&$("sg_srent").checked;return (s&&sr)?"seller_both":((sr&&!s)?"seller_both":"seller_sell");}
function sgAudUI(){var a=$("sg_aud")?$("sg_aud").value:"buyer";var bd=$("sg_buyerdeal"),sd=$("sg_sellerdeal");if(bd)bd.style.display=(a=="buyer")?"":"none";if(sd)sd.style.display=(a=="seller")?"":"none";}
function sgExclSel(){var w=$("sg_exdates");if(w)w.style.display=($("sg_exsel")&&$("sg_exsel").value=="custom")?"":"none";}
function fmtDate(iso){if(!iso)return "";var p=String(iso).split("-");return p.length==3?(p[2]+"/"+p[1]+"/"+p[0]):iso;}
function sgFmtD(d){return ("0"+d.getDate()).slice(-2)+"/"+("0"+(d.getMonth()+1)).slice(-2)+"/"+d.getFullYear();}
function sgMode(){var m=document.querySelector('input[name=sgmode]:checked');var remote=m&&m.value=="remote";var pw=$("sg_padwrap"),rw=$("sg_remotewrap");if(pw)pw.style.display=remote?"none":"";if(rw)rw.style.display=remote?"":"none";var b=$("sg_gobtn");if(b)b.textContent=remote?"שלח ללקוח לחתימה":"צור הסכם וחתום";if(!remote){setTimeout(function(){try{initSigPad("sg_pad");}catch(e){}},30);}}
function openSign(){if(timer){clearInterval(timer);timer=null;}
  var cards=[["buyer","החתמת מתעניין","🧑","#2f9bc4"],["seller","החתמת בעל נכס","🧔","#e09a3a"],["shtaf","הסכם שת״פ","🤝","#8e44ad"],["referral","הפניית לקוח","↪️","#15a085"]];
  var grid=cards.map(function(c){return '<div onclick="openSignCard(\''+c[0]+'\')" style="cursor:pointer;text-align:center;padding:8px 4px"><div style="width:80px;height:80px;border-radius:50%;background:'+c[3]+';display:flex;align-items:center;justify-content:center;font-size:38px;margin:0 auto 8px;box-shadow:0 3px 10px rgba(0,0,0,.18)">'+c[2]+'</div><div style="font-weight:700;font-size:14px;line-height:1.2">'+c[1]+'</div></div>';}).join("");
  $("view").innerHTML='<div class=card><div style="display:flex;justify-content:space-between;align-items:center"><b>✍️ מערכת חתימות</b><button class="btn-ghost" onclick="tab(\'sigs\')">✕ סגור</button></div><div class=muted style="margin-top:4px">בחר סוג החתמה</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px">'+grid+'</div></div><div id=sg_preview></div>';}
function openSignCard(aud){if(aud=="shtaf"||aud=="referral"){alert("בקרוב 🙂 — כרגע זמינים: החתמת מתעניין והחתמת בעל נכס.");return;}openSignForm(aud);}
function openSignForm(aud){SG_AUD=aud;
  var d=new Date();SG_DATE=("0"+d.getDate()).slice(-2)+"/"+("0"+(d.getMonth()+1)).slice(-2)+"/"+d.getFullYear();
  var title=(aud=="seller")?"החתמת בעל נכס":"החתמת מתעניין";
  var deal=(aud=="buyer")
   ? '<div id="sg_buyerdeal" style="margin-top:12px"><div class="muted sglbl"><svg class=eico viewBox="0 0 18 18"><path d="M11.8 3.4l2.8 2.8L6 14.8 3 15.4l.6-3z"/><path d="M10.6 4.6l2.8 2.8"/></svg>סוג עסקה ועמלה</div>'
     +'<label style="display:flex;align-items:center;gap:8px;margin-top:8px"><input type=checkbox id="sg_buy" checked><span style="flex:1;min-width:0">קניה — עמלה</span><input id="sg_cbuy" class=chip style="width:54px;flex:0 0 auto" inputmode=decimal value="2"><select id="sg_cbuyunit" class=chip style="width:56px;flex:0 0 auto"><option>%</option><option>₪</option></select></label>'
     +'<label style="display:flex;align-items:center;gap:8px;margin-top:8px"><input type=checkbox id="sg_rent"><span style="flex:1;min-width:0">שכירות — עמלה</span><input id="sg_crent" class=chip style="width:54px;flex:0 0 auto" inputmode=decimal value="1"><span style="flex:0 0 auto;color:var(--muted);font-size:13px">חודשים</span></label></div>'
   : '<div id="sg_sellerdeal" style="margin-top:12px"><div class="muted sglbl"><svg class=eico viewBox="0 0 18 18"><path d="M11.8 3.4l2.8 2.8L6 14.8 3 15.4l.6-3z"/><path d="M10.6 4.6l2.8 2.8"/></svg>סוג עסקה ועמלה</div>'
     +'<label style="display:flex;align-items:center;gap:8px;margin-top:8px"><input type=checkbox id="sg_sell" checked><span style="flex:1;min-width:0">מכירה — עמלה</span><input id="sg_scbuy" class=chip style="width:54px;flex:0 0 auto" inputmode=decimal value="2"><select id="sg_scbuyunit" class=chip style="width:56px;flex:0 0 auto"><option>%</option><option>₪</option></select></label>'
     +'<label style="display:flex;align-items:center;gap:8px;margin-top:8px"><input type=checkbox id="sg_srent"><span style="flex:1;min-width:0">השכרה — עמלה</span><input id="sg_scrent" class=chip style="width:54px;flex:0 0 auto" inputmode=decimal value="1"><span style="flex:0 0 auto;color:var(--muted);font-size:13px">חודשים</span></label>'
     +'<div style="margin-top:10px"><div class=muted>תקופת בלעדיות (כולל = הלקוח חותם על 2 טפסים)</div><select id="sg_exsel" class=chip style="width:100%;box-sizing:border-box;margin-top:6px" onchange="sgExclSel()"><option value="">ללא בלעדיות</option><option value="1">בלעדיות חודש 1</option><option value="2">בלעדיות 2 חודשים</option><option value="3">בלעדיות 3 חודשים</option><option value="4">בלעדיות 4 חודשים</option><option value="5">בלעדיות 5 חודשים</option><option value="6">בלעדיות 6 חודשים</option><option value="custom">* תאריך מותאם אישית</option></select></div>'
     +'<div id="sg_exdates" style="display:none;margin-top:6px"><div style="display:flex;gap:6px;flex-wrap:wrap"><label class=muted style="flex:1;min-width:130px">מתאריך<input id="sg_exfrom" type=date class=chip style="width:100%;box-sizing:border-box;margin-top:3px"></label><label class=muted style="flex:1;min-width:130px">עד תאריך<input id="sg_exto" type=date class=chip style="width:100%;box-sizing:border-box;margin-top:3px"></label></div></div></div>';
  var propsec=(aud=="buyer")
   ? '<div style="margin-top:12px"><div class="muted sglbl"><svg class=eico viewBox="0 0 18 18"><rect x="4.2" y="2.6" width="9.6" height="12.8" rx="1"/><path d="M7 6h1.2M9.8 6H11M7 9h1.2M9.8 9H11M7 12h4"/><path d="M2.6 15.4h12.8"/></svg>פרטי הנכס (אפשר להוסיף יותר מנכס אחד)</div><div id="sg_proplist_rows"></div><datalist id="sg_proplist"></datalist><button class="btn-ghost" style="margin-top:8px" onclick="sgAddProp()">➕ הוסף נכס</button></div>'
   : '<div style="margin-top:12px"><div class="muted sglbl"><svg class=eico viewBox="0 0 18 18"><rect x="4.2" y="2.6" width="9.6" height="12.8" rx="1"/><path d="M7 6h1.2M9.8 6H11M7 9h1.2M9.8 9H11M7 12h4"/><path d="M2.6 15.4h12.8"/></svg>פרטי הנכס</div><input id="sg_addr" class=chip style="width:100%;box-sizing:border-box;margin-top:6px" placeholder="כתובת הנכס (התחל להקליד — מהמודעות שלך)" list="sg_proplist" autocomplete="off" oninput="sgPropType()"><datalist id="sg_proplist"></datalist><input id="sg_price" class=chip style="width:100%;box-sizing:border-box;margin-top:6px" placeholder="מחיר מבוקש (₪)" inputmode=numeric></div>';
  $("view").innerHTML='<div class=card><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><h2 style="margin:0">'+title+'</h2><button class="sgback" onclick="tab(\'sigs\')"><svg viewBox="0 0 18 18"><path d="M7 4l5 5-5 5"/></svg>חזרה</button></div>'
   + deal
   +'<div style="margin-top:12px"><div class="muted sglbl"><svg class=eico viewBox="0 0 18 18"><circle cx="9" cy="6" r="2.6"/><path d="M4 15a5 5 0 0 1 10 0"/></svg>פרטי הלקוח</div>'
   +'<input id="sg_cname" class=chip style="width:100%;box-sizing:border-box;margin-top:6px" placeholder="שם הלקוח (התחל להקליד — קונה שמור מ״הקונים שלי״)" list="sg_clientlist" autocomplete="off" oninput="sgClientType()"><datalist id="sg_clientlist"></datalist>'
   +'<input id="sg_cphone" class=chip style="width:100%;box-sizing:border-box;margin-top:6px" placeholder="טלפון" inputmode=tel>'
   +'<input id="sg_cid" class=chip style="width:100%;box-sizing:border-box;margin-top:6px" placeholder="תעודת זהות" type="text" inputmode=numeric maxlength="9" name="sg_tz" autocomplete="off" autocorrect="off" data-form-type="other" data-lpignore="true" oninput="sgCheckId()"><div id="sg_idmsg" style="font-size:12px;margin-top:3px"></div></div>'
   + propsec
   +'<div style="margin-top:12px"><div class=muted>הערות (לא חובה)</div><textarea id="sg_notes" class=chip style="width:100%;box-sizing:border-box;min-height:60px;margin-top:6px" placeholder="הערות שיתווספו לתחתית ההסכם"></textarea></div>'
   +'<div style="margin-top:14px"><div class=muted>אופן ההחתמה</div>'
   +'<label style="display:flex;align-items:center;gap:10px;margin-top:10px"><input type=radio name="sgmode" value="remote" checked onchange="sgMode()"><span style="line-height:1.35">שליחה לחתימה ב-SMS ו-WhatsApp</span></label>'
   +'<label style="display:flex;align-items:center;gap:10px;margin-top:10px"><input type=radio name="sgmode" value="local" onchange="sgMode()"><span style="line-height:1.35">הפקה ללא שליחה (חתימה במקום)</span></label></div>'
   +'<div id="sg_padwrap" style="margin-top:14px"><div class=muted>✍️ חתימת הלקוח</div><canvas id="sg_pad" style="width:100%;height:160px;border:1px solid rgba(127,127,127,.4);border-radius:10px;touch-action:none;background:#fff;margin-top:6px;display:block"></canvas><div style="text-align:left;margin-top:4px"><button class="btn-ghost" onclick="clearSig(\'sg_pad\')">נקה</button></div></div>'
   +'<div id="sg_remotewrap" style="display:none;margin-top:14px"><div class=muted style="padding:11px 13px;background:#eef2fb;border:1px solid #d8e2f5;border-radius:10px;color:#2f5fbe;line-height:1.55">קישור לחתימה יישלח ללקוח ב-SMS וב-WhatsApp. הלקוח ימלא ת״ז ויחתום במכשירו, והקישור החתום יתווסף לשורת החתימה.</div></div>'
   +'<button id="sg_gobtn" class="btn-gold" style="width:100%;margin-top:14px" onclick="sgGenerate()">צור הסכם וחתום</button></div><div id="sg_preview"></div>';
  if(aud=="buyer")sgAddProp();
  sgMode();loadSignPickers();}
function sgAddProp(){var box=$("sg_proplist_rows");if(!box)return;var row=document.createElement("div");row.className="sg_prow";row.style.cssText="display:flex;gap:6px;margin-top:6px;align-items:center";row.innerHTML='<input class="sg_addr_m chip" style="flex:3;min-width:130px;box-sizing:border-box" placeholder="כתובת + מספר בית" list="sg_proplist" autocomplete="off" oninput="sgPropTypeM(this)"><input class="sg_price_m chip" style="flex:1.5;min-width:85px;box-sizing:border-box" placeholder="מחיר ₪" inputmode=numeric><button class="btn-ghost sgdel" type=button onclick="sgDelProp(this)">✕</button>';box.appendChild(row);}
function sgDelProp(btn){var box=$("sg_proplist_rows");var row=btn.parentNode;if(box&&box.querySelectorAll(".sg_prow").length<=1){row.querySelector(".sg_addr_m").value="";row.querySelector(".sg_price_m").value="";return;}row.parentNode.removeChild(row);}
function sgPropTypeM(el){var ad=String(el.value||"").trim();var p=SG_PROPS[ad];if(p&&p.price){var pr=el.parentNode.querySelector(".sg_price_m");if(pr&&!pr.value)pr.value=p.price;}}
function sgCollectProps(){var out=[];var rows=document.querySelectorAll("#sg_proplist_rows .sg_prow");for(var i=0;i<rows.length;i++){var a=String((rows[i].querySelector(".sg_addr_m")||{}).value||"").trim();var p=String((rows[i].querySelector(".sg_price_m")||{}).value||"").trim();if(a)out.push({addr:a,price:p});}return out;}
var SG_CLIENTS={},SG_PROPS={};
function loadSignPickers(){
  api("/api/my/buyers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({as:(typeof IMP!="undefined"?(IMP||""):"")})}).then(function(r){
    if(!r||!r.ok)return;SG_CLIENTS={};var opts="";(r.results||[]).forEach(function(b){var nm=String(b.name||"").trim();if(!nm||SG_CLIENTS[nm])return;SG_CLIENTS[nm]={phone:(b.phone||"")};opts+='<option value="'+esc(nm)+'">'+(b.phone?esc(b.phone):"")+(b.budget?(" · "+esc(b.budget)):"")+'</option>';});var dl=$("sg_clientlist");if(dl)dl.innerHTML=opts;
  }).catch(function(){});
  api("/api/sign/properties"+(typeof IMP!="undefined"&&IMP?("?as="+encodeURIComponent(IMP)):"")).then(function(r){
    if(!r||!r.ok)return;SG_PROPS={};var opts="";(r.properties||[]).forEach(function(p){var ad=String(p.address||"").trim();if(!ad||SG_PROPS[ad])return;SG_PROPS[ad]={price:(p.price||"")};opts+='<option value="'+esc(ad)+'"></option>';});var dl=$("sg_proplist");if(dl)dl.innerHTML=opts;
  }).catch(function(){});}
function sgClientType(){var nm=String(($("sg_cname")||{}).value||"").trim();var c=SG_CLIENTS[nm];if(c&&c.phone)$("sg_cphone").value=c.phone;}
function sgPropType(){var ad=String(($("sg_addr")||{}).value||"").trim();var p=SG_PROPS[ad];if(p&&p.price)$("sg_price").value=p.price;}
function sgGenerate(){
  var m=document.querySelector('input[name=sgmode]:checked');
  var isRemote=m&&m.value=="remote";
  var cid=($("sg_cid").value||"").trim();
  if(cid&&!validILID(cid)){alert("תעודת הזהות אינה תקינה");return;}
  var _cnm=($("sg_cname").value||"").trim();
  if(!_cnm){alert("חסר שם לקוח");return;}
  if(_cnm.split(/\s+/).filter(Boolean).length<2){alert("נא להזין שם מלא — שם פרטי ושם משפחה");return;}
  var pad=$("sg_pad");
  if(isRemote){if(!($("sg_cphone").value||"").trim()){alert("חסר טלפון לקוח לשליחת הקישור");return;}}
  else{if(!pad||pad.dataset.signed!="1"){alert("חסרה חתימת הלקוח");return;}}
  var aud=SG_AUD||"buyer";
  var exfrom="",exto="",exclOn=false;
  if(aud=="seller"){var xsel=$("sg_exsel")?$("sg_exsel").value:"";
    if(xsel=="custom"){if($("sg_exfrom").value&&$("sg_exto").value){exclOn=true;exfrom=fmtDate($("sg_exfrom").value);exto=fmtDate($("sg_exto").value);}}
    else if(xsel){var xn=parseInt(xsel,10);var xf=new Date(),xt=new Date();xt.setMonth(xt.getMonth()+xn);exclOn=true;exfrom=sgFmtD(xf);exto=sgFmtD(xt);}}
  var props=(aud=="buyer")?sgCollectProps():(($("sg_addr")&&$("sg_addr").value.trim())?[{addr:$("sg_addr").value.trim(),price:($("sg_price")?$("sg_price").value.trim():"")}]:[]);
  var vAddr=props.map(function(p){return p.addr;}).join(" | ");var vPrice=(props[0]?props[0].price:"");
  var v={date:SG_DATE,agent:(((typeof IMP!="undefined"&&IMP)?(IMPNAME||IMP):NAME)||""),cname:$("sg_cname").value.trim(),cphone:$("sg_cphone").value.trim(),cid:cid,addr:vAddr,price:vPrice,props:props,
    cbuy:(aud=="buyer"?$("sg_cbuy").value.trim():$("sg_scbuy").value.trim()),
    cbuyunit:(aud=="buyer"?($("sg_cbuyunit")?$("sg_cbuyunit").value:"%"):($("sg_scbuyunit")?$("sg_scbuyunit").value:"%")),
    crent:(aud=="buyer"?$("sg_crent").value.trim():$("sg_scrent").value.trim()),
    notes:($("sg_notes")?$("sg_notes").value.trim():""),
    exfrom:exfrom,exto:exto,refid:("RF"+Date.now().toString().slice(-8)),refdate:SG_DATE};
  var sig=isRemote?"":sgShrinkSig(pad);
  var keys=[sgResolveKey()];
  if(exclOn)keys.push("exclusive");
  $("sg_preview").innerHTML='<div class=card style="text-align:center;padding:18px"><div style="font-size:28px">⏳</div><b>'+(isRemote?"מכין ושולח ללקוח…":"מפיק את ההסכם…")+'</b></div>';try{$("sg_preview").scrollIntoView({behavior:"smooth",block:"center"});}catch(e){}
  var docs=[];
  function step(i){if(i>=keys.length){if(isRemote){sgSendRemote(docs,v);}else{renderSignDocs(docs,v,sig);}return;}
    api("/api/sign/contract?type="+encodeURIComponent(keys[i])).then(function(r){var fb=sgFill((r&&r.body)||"",v);if(v.notes)fb=fb+String.fromCharCode(10)+String.fromCharCode(10)+"הערות: "+v.notes;docs.push({title:(r&&r.title)||"",body:fb,deal_type:sgDealType(keys[i])});step(i+1);}).catch(function(){docs.push({title:"שגיאה",body:"",deal_type:""});step(i+1);});}
  step(0);}
function sgShrinkSig(pad){try{var tw=440;var th=Math.round(tw*(pad.height||160)/(pad.width||440));var c=document.createElement("canvas");c.width=tw;c.height=th;var x=c.getContext("2d");x.fillStyle="#fff";x.fillRect(0,0,tw,th);x.drawImage(pad,0,0,tw,th);return c.toDataURL("image/jpeg",0.55);}catch(e){return pad.toDataURL("image/jpeg",0.5);}}
function sgDealType(key){return {buyer_buy:"CLIENT_SALE",buyer_both:"CLIENT_SALE",buyer_rent:"CLIENT_RENT",seller_sell:"OWNER_SALE",seller_both:"OWNER_SALE",exclusive:"OWNER_EXCLUSIVE"}[key]||"";}
var SG_LASTDOCS=null,SG_LASTV=null,SG_LASTSIG="",SG_LASTHDR="";
function sgSubmit(){
  if(!SG_LASTDOCS||!SG_LASTDOCS.length){alert("אין מה לשמור");return;}
  var v=SG_LASTV;
  api("/api/sign/submit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({agent:v.agent,client:v.cname,cid:v.cid,address:v.addr,notes:(v.notes||""),signature:SG_LASTSIG,header:SG_LASTHDR,docs:SG_LASTDOCS.map(function(d){return {deal_type:d.deal_type,title:d.title,body:d.body};})})}).then(function(r){
    if(r&&r.ok){var _warn=(r.doc_saved===false)?'<div class=muted style="margin-top:8px;color:#c0392b">⚠️ המסמך עצמו לא נשמר (Apps Script) — הקישור לא יעבוד. צלם לי מסך.<br><span style="font-size:10px;direction:ltr;display:block;word-break:break-all">'+(r.doc_resp||'')+'</span></div>':'';window._sgShare={phone:(v.cphone||""),link:(r.link||""),name:(v.cname||"")};var _wabtn=(v.cphone&&r.link)?'<button class="btn-gold" style="width:100%;margin-top:10px;background:#25D366;border-color:#25D366" onclick="sgShareWA()">📲 שלח ללקוח בוואטסאפ</button>':'';$("sg_preview").innerHTML='<div class=card style="text-align:center"><div style="font-size:42px">✅</div><b>נשמר בהצלחה!</b><div class=muted style="margin-top:6px">הרשומה נכנסה לגליון חתימות ולדוחות.</div>'+_warn+_wabtn+'<button class="btn-ghost" style="width:100%;margin-top:8px" onclick="tab(\'sigs\')">לטאב חתימות</button></div>';try{$("sg_preview").scrollIntoView({behavior:"smooth",block:"center"});}catch(e){}}
    else{alert("השמירה נכשלה — ודא שה-Apps Script פרוס בגרסה חדשה (עם הפעולה addsigning).");}
  }).catch(function(){alert("שגיאת רשת");});}
function sgBuildHeader(v){var ph;if(v.props&&v.props.length>1){ph="נכסים:\n"+v.props.map(function(p,i){return "  "+(i+1)+". "+p.addr+(p.price?(" — "+p.price+" ₪"):"");}).join("\n");}else{ph="נכס: "+(v.addr||"—")+(v.price?(" · מחיר מבוקש: "+v.price+" ₪"):"");}return "תאריך: "+v.date+" · המתווך/הסוכן: "+v.agent+"\nלקוח: "+v.cname+(v.cphone?(" · טל' "+v.cphone):"")+(v.cid?(" · ת״ז "+v.cid):"")+"\n"+ph;}
function sgSendRemote(docs,v){
  var hdr=sgBuildHeader(v);
  api("/api/sign/send_remote",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({agent:v.agent,client:v.cname,phone:v.cphone,address:v.addr,notes:(v.notes||""),header:hdr,docs:docs.map(function(d){return {deal_type:d.deal_type,title:d.title,body:d.body};})})}).then(function(r){
    if(r&&r.ok){var ch=[];if(r.sms)ch.push("SMS");if(r.wa)ch.push("WhatsApp");var chs=ch.length?ch.join(" + "):"(בדוק הגדרות שליחה)";
      $("sg_preview").innerHTML='<div class=card style="text-align:center"><div style="font-size:42px">📲</div><b>נשלח ללקוח!</b><div class=muted style="margin-top:6px">קישור לחתימה נשלח אל '+esc(v.cname)+' ('+chs+').<br>החתימה תופיע בטאב ״חתימות״ — הקישור החתום יתווסף ברגע שהלקוח יחתום.</div><button class="btn-gold" style="width:100%;margin-top:12px" onclick="tab(\'sigs\')">לטאב חתימות</button></div>';
      try{$("sg_preview").scrollIntoView({behavior:"smooth",block:"center"});}catch(e){}}
    else{$("sg_preview").innerHTML='';alert("השליחה נכשלה: "+((r&&r.reason)||"שגיאה")+". ודא שה-Apps Script פרוס בגרסה חדשה.");}
  }).catch(function(){$("sg_preview").innerHTML='';alert("שגיאת רשת");});}
function sgShareWA(){var d=window._sgShare||{};if(!d.phone||!d.link){alert("אין טלפון/קישור לשליחה");return;}
  api("/api/sign/share",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone:d.phone,link:d.link,client:d.name})}).then(function(r){
    if(r&&r.ok){alert("📲 נשלח ללקוח"+((r.wa&&r.sms)?" (וואטסאפ + SMS)":(r.wa?" בוואטסאפ":" ב-SMS")));}
    else{alert("השליחה נכשלה — ודא שיש טלפון תקין");}
  }).catch(function(){alert("שגיאת רשת");});}
function renderSignDocs(docs,v,sig){
  SG_LASTDOCS=docs;SG_LASTV=v;SG_LASTSIG=sig;
  var hdr=sgBuildHeader(v);
  SG_LASTHDR=hdr;
  var html=docs.map(function(dn){return '<div class=card><b>📄 '+esc(dn.title)+'</b><div style="white-space:pre-wrap;line-height:1.7;margin-top:8px;border:1px solid rgba(127,127,127,.25);border-radius:10px;padding:12px;background:#fff;color:#111;direction:rtl">'+esc(hdr)+"\\n\\n"+esc(dn.body)+'<div style="margin-top:14px;border-top:1px dashed #bbb;padding-top:8px;color:#111">חתימת '+esc(v.cname)+':<br><img src="'+sig+'" style="max-height:80px;background:#fff"></div></div></div>';}).join("");
  html+='<div class=card>'+(docs.length>1?'<div class=muted style="margin-bottom:8px">בעל נכס + בלעדיות = 2 מסמכים</div>':'')+'<button class="btn-gold" style="width:100%" onclick="sgSubmit()">✅ אשר, חתום ושמור</button><div class=muted style="margin-top:6px;text-align:center;font-size:12px">השמירה תיכנס לגליון חתימות ולדוחות</div></div>';
  $("sg_preview").innerHTML=html;try{$("sg_preview").scrollIntoView({behavior:"smooth"});}catch(e){}}
function csumMore(el){var s=el.nextElementSibling;if(!s||!s.classList.contains("csum"))return;var hidden=s.classList.toggle("collapsed");el.textContent=hidden?"עוד — סיכום שיחה ▾":"פחות ▴";}
function callDetails(c){
  var sum=c.summary?("<span class=csummore onclick=csumMore(this)>עוד — סיכום שיחה ▾</span><div class='csum collapsed'>"+esc(c.summary)+"</div>"):"";
  if(c.clientDetails)return "<div class=cdetails><b>📋 פרטים על הלקוח</b><div>"+esc(c.clientDetails.replace(/^פרטים שנאספו על הלקוח:?\s*/,""))+"</div>"+sum+"</div>";
  if(c.summary)return "<div class=csumwrap>"+sum+"</div>";
  return "";
}
var NEWBUYERS=0,_nbTs=0,_nbList=null,_nbImp="";
function _nbCount(){if(!_nbList)return;
  NEWBUYERS=_nbList.filter(function(b){var s=String(b.date||"");var m=s.match(/^(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})/);if(!m)return false;var ts=new Date(+m[3],+m[2]-1,+m[1]).getTime()/1000;return inRange(ts);}).length;
  var kp=$("callkpi");if(kp&&kp.children&&kp.children[2]){var n=kp.children[2].querySelector(".n");if(n)n.textContent=NEWBUYERS;}}
function loadNewBuyers(){_nbCount();
  var imp=(typeof IMP!="undefined"?(IMP||""):"");var now=Date.now();
  if(_nbList&&imp===_nbImp&&now-_nbTs<60000)return;_nbTs=now;_nbImp=imp;
  api("/api/my/buyers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({as:imp})}).then(function(r){
    if(!r||!r.ok)return;_nbList=r.results||[];_nbCount();
  }).catch(function(){});}
function statusHe(s){var k=String(s||"").toUpperCase().replace(/[_-]/g," ").replace(/\s+/g," ").trim();var m={"ANSWER":"נענתה","ANSWERED":"נענתה","NO ANSWER":"ללא מענה","NOANSWER":"ללא מענה","BUSY":"תפוס","CALLER CANCEL":"המתקשר ניתק","CALLER CANCELLED":"המתקשר ניתק","CANCEL":"בוטלה","CANCELLED":"בוטלה","CANCELED":"בוטלה","FAILED":"נכשלה","REJECTED":"נדחתה","MISSED":"שיחה שלא נענתה","VOICEMAIL":"תא קולי","CONGESTION":"עומס ברשת","UNKNOWN":"לא ידוע"};return m[k]||s;}
function loadCalls(){api("/api/history?"+(IMP?("as="+encodeURIComponent(IMP)+"&"):"")+(HIDDENMODE?"hidden=1":"")).then(function(r){
  if(!r.ok){relogin();return;}
  if(r.tabs&&!IMP){TABS=r.tabs;try{localStorage.setItem("fbTabs",JSON.stringify(TABS));}catch(e){}applyTabPerms();}
  var calls=r.calls.filter(function(c){return inRange(c.ts);});
  $("live").innerHTML="🟢 חי · "+periodLabel()+" · "+calls.length+(HIDDENMODE?" מוסתרות":" שיחות");
  var _ans=calls.filter(function(c){return c.status=="ANSWER";}).length;
  var _newb=(typeof NEWBUYERS!=="undefined"?NEWBUYERS:0);
  var _kp=$("callkpi");if(_kp)_kp.innerHTML=calls.length?(kpi(calls.length,"שיחות")+kpi(_ans,"נענו")+kpi(_newb,"קונים חדשים")):"";
  loadNewBuyers();
  var ht=$("htoggle");if(ht)ht.textContent=HIDDENMODE?"חזרה לשיחות":"הצג מוסתרות";
  VPHONE=r.vphone||"";var vp=$("vphone");if(vp)vp.innerHTML=VPHONE?("🤖📞 <span class=vpnum>"+esc(VPHONE)+"</span> <span id=vpcopybtn class=vpcopy onclick=copyVphone()>📋 העתק</span>"):"";
  var maxC=calls.length?calls[0].ts:0;
  $("calls").innerHTML=(calls.length?calls.map(function(c){
    var isNew=seenCall&&c.ts>seenCall;var st=c.status=="ANSWER"?"<span class=ans>נענתה</span>":"<span class=noans>"+c.status+"</span>";
    var callerLink=c.caller?("<a href='tel:"+(c.tel||c.caller)+"'>"+c.caller+"</a>"):"-";
    var cb=c.callback?(" <a class=cbtn href='"+c.callback+"' target=_blank rel=noopener>🔁 חייג חזרה</a>"):"";
    var bsum=(c.summary||"")+(c.clientDetails?("\n"+c.clientDetails):"");
    var addb=" <button class=addbuyer data-ph=\""+esc(c.tel||c.caller||"")+"\" data-sum=\""+encodeURIComponent(bsum)+"\"><svg class=eico viewBox='0 0 18 18'><circle cx='9' cy='6' r='2.6'/><path d='M4 15a5 5 0 0 1 10 0'/></svg>הוסף קונה</button>";
    var hideb=" <button class=hidecall data-id=\""+esc(c.id||"")+"\" data-act=\""+(HIDDENMODE?"unhide":"hide")+"\">"+(HIDDENMODE?"שחזר":"הסתר")+"</button>";
    var wab=c.wa?(" <a class=wab href='https://wa.me/"+c.wa+"' target=_blank rel=noopener><svg class=eico viewBox='0 0 18 18'><path d='M15.5 8.6a6.3 6.3 0 0 1-9.2 5.6L3 15l.9-3.2A6.3 6.3 0 1 1 15.5 8.6z'/></svg>וואטסאפ</a>"):"";
    var _phsvg="<svg viewBox='0 0 18 18'><path d='M16 13.4v2.1a1.4 1.4 0 0 1-1.5 1.4 13.9 13.9 0 0 1-6.1-2.2 13.7 13.7 0 0 1-4.2-4.2A13.9 13.9 0 0 1 2 4.4 1.4 1.4 0 0 1 3.4 3h2.1a1.4 1.4 0 0 1 1.4 1.2c.1.7.3 1.4.5 2a1.4 1.4 0 0 1-.3 1.5l-.9.9a11.2 11.2 0 0 0 4.2 4.2l.9-.9a1.4 1.4 0 0 1 1.5-.3c.6.2 1.3.4 2 .5A1.4 1.4 0 0 1 16 13.4z'/></svg>";
    var _ok=(c.status=="ANSWER");
    var _statusWord=statusHe(c.status);
    var _sub=c.time+(c.duration?(" · "+c.duration+"ש׳"):"")+" · "+_statusWord+((isMulti()&&c.agent)?(" · "+esc(c.agent)):"");
    return "<div class='callrow"+(isNew?" new":"")+"'>"+
      "<div class=crow1><div class='cstat "+(_ok?"ok":"no")+"'>"+_phsvg+"</div>"+
        "<div class=cmain><div class=cphone>"+callerLink+"</div><div class=csub>"+_sub+"</div></div></div>"+
      callDetails(c)+
      "<div class=cbtns>"+wab+cb+addb+hideb+"</div>"+
    "</div>";
  }).join(""):"<div class=card><div class=muted>אין שיחות בטווח.</div></div>");
  document.querySelectorAll("#calls .addbuyer").forEach(function(b){b.onclick=function(){openBuyerForm({phone:b.getAttribute("data-ph")||"",summary:decodeURIComponent(b.getAttribute("data-sum")||"")});};});
  document.querySelectorAll("#calls .hidecall").forEach(function(b){b.onclick=function(){var id=b.getAttribute("data-id");if(b.getAttribute("data-act")=="unhide")unhideCall(id);else hideCall(id);};});
  seenCall=maxC;
}).catch(function(){});}
function sigDelete(eid,raw,client){
  if(!confirm("למחוק את ההסכם לצמיתות? (יימחק גם מהגיליון וגם מהדוחות)"))return;
  api("/api/sign/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({eid:decodeURIComponent(eid||""),received:decodeURIComponent(raw||""),client:decodeURIComponent(client||"")})}).then(function(r){
    if(r&&r.ok){loadSigs();}
    else{alert(r&&r.reason=="forbidden"?"רק למשתמש מורשה":"המחיקה נכשלה — ודא שה-Apps Script פרוס עם deletesigning.");}
  }).catch(function(){alert("שגיאת רשת");});}
function sigTag(t){t=String(t||"");if(/בלעד/.test(t))return {cls:"t-excl",excl:true};if(/מוכר|מכיר|בעל/.test(t))return {cls:"t-seller",excl:false};if(/שכיר/.test(t))return {cls:"t-rent",excl:false};return {cls:"t-buyer",excl:false};}
function loadSigs(){api("/api/history"+(IMP?("?as="+encodeURIComponent(IMP)):"")).then(function(r){
  if(!r.ok){relogin();return;}
  var sigs=r.signatures.filter(function(g){return inRange(g.ts);});
  $("live").innerHTML="🟢 חי · "+periodLabel()+" · "+sigs.length+" חתימות";
  var maxS=sigs.length?sigs[0].ts:0;
  var _dsv="<svg class=eico viewBox='0 0 18 18'><rect x='4' y='2.5' width='10' height='13' rx='1.4'/><path d='M6.5 6h5M6.5 9h5M6.5 12h3'/></svg>";
  $("sigs").innerHTML=(sigs.length?('<div class=muted style="margin:2px 2px 10px;font-weight:700">חתימות אחרונות</div>'+sigs.map(function(g){
    var isNew=seenSig&&g.ts>seenSig;var tg=sigTag(g.type);
    var signed=!!(g.link||(g.pct!=null&&g.pct!==""));
    var meta="<span class='"+(signed?"":"pendlbl")+"'>"+(signed?"נחתם":"ממתין לחתימה")+"</span> · "+g.time+((isMulti()&&g.agent)?(" · "+esc(g.agent)):"");
    var delb=(typeof DEV!="undefined"&&DEV)?("<button class=sdel title='מחק הסכם' onclick=\"sigDelete('"+encodeURIComponent(g.eid||"")+"','"+encodeURIComponent(g.raw||"")+"','"+encodeURIComponent(g.client||"")+"')\"><svg class=eico viewBox='0 0 18 18'><path d='M3.5 5h11M7 5V3.5h4V5M5 5l.6 9.5a1 1 0 0 0 1 .9h4.8a1 1 0 0 0 1-.9L13 5'/><path d='M8 8v4M10 8v4'/></svg></button>"):"";
    return "<div class='scard"+(tg.excl?" excl":"")+(signed?"":" pending")+(isNew?" new":"")+"'>"+
      "<div class=stop><b class=sname>"+esc(g.client||g.type||"חתימה")+"</b><span class='stag "+tg.cls+"'>"+esc(g.type)+"</span>"+delb+"</div>"+
      (g.address?"<div class=saddr>"+_dsv+esc(g.address)+"</div>":"")+
      "<div class=sdate>"+meta+"</div>"+
      (g.link?"<div style='margin-top:10px'><a class=slink href='"+g.link+"' target=_blank rel=noopener>"+_dsv+"קישור להסכם</a></div>":"")+
    "</div>";
  }).join("")):"<div class=card><div class=muted>אין חתימות בטווח.</div></div>");
  seenSig=maxS;
}).catch(function(){});}

function viewSearch(kind){
  var cfg={props:{t:"🏢 נכסים במשרד",ph:"דירת 4 חדרים בקרית ביאליק עד 2 מיליון",ep:"/api/search/properties"},
           excl:{t:"🏘️ נכסים בשת״פ",ph:"דירת 5 חדרים באפקה",ep:"/api/search/exclusives"},
           buyers:{t:"👤 הקונים שלי",ph:"4 חדרים תקציב 2 מיליון",ep:"/api/search/buyers"}}[kind];
  $("view").innerHTML='<div class=card><h2>'+cfg.t+'</h2><input id=sq placeholder="'+cfg.ph+'"><button class=searchbtn onclick=doSearch("'+cfg.ep+'","'+kind+'")>חיפוש</button>'+(kind=="buyers"?' <button class=sec onclick=openBuyerForm({})>➕ הוסף קונה</button>':'')+'<div id=recent></div><div id=sres></div>'+(kind=="props"?'<div id=myprops></div>':'')+(kind=="buyers"?'<div id=mybuyers></div>':'')+'</div>';
  CUR_EP=cfg.ep;CUR_KIND=kind;
  if(kind=="props"||kind=="excl")loadRecent(kind);
  if(kind=="props")loadMyProps();
  if(kind=="buyers")loadMyBuyers();
  if(kind=="excl")doSearch(cfg.ep,kind);   // טען מיד את כל הבלעדיות האחרונות
}
function loadMyProps(){var box=$("myprops");if(!box)return;box.innerHTML="<div class=muted style=margin:8px_0>טוען את הנכסים שלך… ⏳</div>";
  api("/api/my/properties",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({as:IMP||""})}).then(function(r){
    if(!$("myprops"))return;if(!r||!r.ok){$("myprops").innerHTML="";return;}
    if(!r.results.length){$("myprops").innerHTML="<div class=muted style=margin:8px_0>לא נמצאו נכסים על שמך בגיליון המשרד.</div>";return;}
    var h="<div class=muted style=margin:12px_0_4px>🏠 הנכסים שלי במשרד ("+r.results.length+")</div>";
    h+=r.results.map(function(x){return card("props",x);}).join("");
    $("myprops").innerHTML=h;
    document.querySelectorAll("#myprops .lreq").forEach(function(b){b.onclick=function(){var id=b.getAttribute("data-id"),addr=decodeURIComponent(b.getAttribute("data-addr")||""),k=b.getAttribute("data-k");if(k=="done"){if(confirm("לסמן שהטיפול בוצע? הנכס לא יסומן יותר כ׳בטיפול אצל המזכירה׳."))listingDone(id);}else if(k=="remove"){if(confirm("לשלוח בקשה למזכירה להסיר את המודעה?\n"+addr))listingReq("remove",id,addr,"");}else{var np=prompt("מחיר חדש למודעה:\n"+addr);if(np&&np.trim())listingReq("price",id,addr,np.trim());}};});
  }).catch(function(){if($("myprops"))$("myprops").innerHTML="";});}
function listingReq(kind,id,addr,np){api("/api/listing/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:kind,id:id,address:addr,new_price:np,as:(typeof IMP!="undefined"?IMP:"")||""})}).then(function(r){if(r&&r.ok){alert("✅ הבקשה נשלחה למזכירה");loadMyProps();}else alert("שליחה נכשלה"+(r&&r.reason?" ("+r.reason+")":""));}).catch(function(){alert("שגיאה");});}
function listingDone(id){api("/api/listing/done",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})}).then(function(r){if(r&&r.ok){loadMyProps();}else alert("עדכון נכשל");}).catch(function(){alert("שגיאה");});}
function openHelp(){closeHelp();var h='<div class=ovl id=helpovl><div class=ovlbox><div style="display:flex;justify-content:space-between;align-items:center"><b>עזרה / דיווח תקלה</b><button class="btn-ghost" style="width:auto;padding:4px 11px;margin:0" onclick="closeHelp()">✕</button></div><div class=muted style="margin:6px 0 10px">דווח על תקלה או שלח הצעת ייעול — יישלח ישירות במייל לאייל.</div><select id=help_kind class=chip style="width:100%;box-sizing:border-box"><option>תקלה / באג</option><option>הצעת ייעול</option><option>אחר</option></select><textarea id=help_msg placeholder="תאר/י את הבעיה או ההצעה..." style="width:100%;box-sizing:border-box;min-height:120px;margin-top:8px"></textarea><div id=help_st class=muted style="margin-top:6px;min-height:16px"></div><button class="btn-gold" style="width:100%;margin-top:8px" onclick="sendHelp()">שלח</button></div></div>';var d=document.createElement("div");d.innerHTML=h;document.body.appendChild(d.firstElementChild);var o=$("helpovl");if(o)o.onclick=function(e){if(e.target.id=="helpovl")closeHelp();};}
function closeHelp(){var o=$("helpovl");if(o)o.parentNode.removeChild(o);}
function sendHelp(){var m=($("help_msg").value||"").trim();var st=$("help_st");if(!m){st.innerHTML="<span class=err>נא לכתוב הודעה</span>";return;}var k=$("help_kind").value;st.textContent="שולח…";api("/api/help",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:m,kind:k})}).then(function(r){if(r&&r.ok){st.innerHTML="<span style='color:#1f8a4c;font-weight:700'>✓ נשלח בהצלחה! תודה.</span>";setTimeout(closeHelp,1200);}else{st.innerHTML="<span class=err>השליחה נכשלה — נסה שוב מאוחר יותר.</span>";}}).catch(function(){st.innerHTML="<span class=err>שגיאת רשת</span>";});}
function shareApp(){var u=location.origin+"/app";var t="📞 תמלול שיחות אוטומטי\n👥 ניהול קונים ולידים במקום אחד\n✍️ חתימה דיגיטלית על מסמכים\n🤖 מציאת נכסים באמצעות AI\n🏠 \"נכס נולד\" – איתור נכסים חדשים לפני כולם\n"+u;window.open("https://wa.me/?text="+encodeURIComponent(t),"_blank");}
var DEFERRED_INSTALL=null;
window.addEventListener("beforeinstallprompt",function(e){e.preventDefault();DEFERRED_INSTALL=e;});
function addToHome(){
  if(window.navigator.standalone){alert("האפליקציה כבר מותקנת על מסך הבית 🎉");return;}
  if(DEFERRED_INSTALL){DEFERRED_INSTALL.prompt();DEFERRED_INSTALL.userChoice.then(function(){DEFERRED_INSTALL=null;});return;}
  var isIOS=/iphone|ipad|ipod/i.test(navigator.userAgent);
  if(isIOS){alert("להוספה למסך הבית (אייפון):\n\n1. לחץ על כפתור השיתוף ⬆️ בתחתית הדפדפן (Safari)\n2. גלול ובחר ״הוספה למסך הבית״\n3. לחץ ״הוסף״\n\nכך תקבל אייקון של RE/MAX Family ישירות במסך הבית.");}
  else{alert("להוספה למסך הבית:\n\nפתח את תפריט הדפדפן (⋮) ובחר ״הוספה למסך הבית״ / Install app.");}
}
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
    var h="<div class=muted style=margin:12px_0_4px>הקונים שלי ("+r.results.length+")</div>";
    h+=r.results.map(function(x){return buyerCard(x);}).join("");
    $("mybuyers").innerHTML=h;
    document.querySelectorAll("#mybuyers .bsearch").forEach(function(b){b.onclick=function(){buyerSearch(b);};});
  }).catch(function(){if($("mybuyers"))$("mybuyers").innerHTML="";});}
function fmtBudget(v){v=String(v||"").trim();if(!v)return"";var n=v.replace(/[,\s₪]/g,"");if(/^[0-9]+$/.test(n))return Number(n).toLocaleString('he-IL')+" ₪";return v;}
function buyerCard(x){
  var ph=x.phone?("<a href='tel:"+(x.tel||x.phone)+"'>"+esc(x.phone)+"</a>"):"";
  var n=BSEQ++,sid="bs"+n,rid="br"+n;
  var _ps="<svg class=eico viewBox='0 0 18 18'><path d='M16 13.4v2.1a1.4 1.4 0 0 1-1.5 1.4 13.9 13.9 0 0 1-6.1-2.2 13.7 13.7 0 0 1-4.2-4.2A13.9 13.9 0 0 1 2 4.4 1.4 1.4 0 0 1 3.4 3h2.1a1.4 1.4 0 0 1 1.4 1.2c.1.7.3 1.4.5 2a1.4 1.4 0 0 1-.3 1.5l-.9.9a11.2 11.2 0 0 0 4.2 4.2l.9-.9a1.4 1.4 0 0 1 1.5-.3c.6.2 1.3.4 2 .5A1.4 1.4 0 0 1 16 13.4z'/></svg>";
  var _us="<svg class=eico viewBox='0 0 18 18'><circle cx='9' cy='6' r='2.6'/><path d='M4 15a5 5 0 0 1 10 0'/></svg>";
  var meta=[(ph?_ps+ph:""),(x.wa?"<a href='https://wa.me/"+x.wa+"' target=_blank>וואטסאפ</a>":""),(x.date?esc(x.date):""),((isMulti()&&x.agent)?_us+esc(x.agent):"")].filter(Boolean).join(" · ");
  var q=encodeURIComponent(((x.budget||"")+" "+(x.summary||"")).trim().slice(0,800));
  return "<div class='row buyerrow'>"+
    "<div class=bhead><b class=bname>"+esc(x.name||"ללא שם")+"</b>"+(x.budget?"<span class=bbudget>"+esc(fmtBudget(x.budget))+"</span>":"")+"<button class=bdel onclick=\"delBuyer('"+esc(String(x.row||""))+"')\" title='מחק קונה'><svg class=eico viewBox='0 0 18 18'><path d='M3.5 5h11M7 5V3.5h4V5M5 5l.6 9.5a1 1 0 0 0 1 .9h4.8a1 1 0 0 0 1-.9L13 5'/><path d='M8 8v4M10 8v4'/></svg></button></div>"+
    (meta?"<div class=muted bmeta>"+meta+"</div>":"")+
    (x.summary?("<div class=bsum id="+sid+">"+esc(x.summary)+"</div><span class=bmore onclick=\"var e=document.getElementById('"+sid+"');e.classList.toggle('open');this.textContent=e.classList.contains('open')?'הצג פחות':'הצג עוד';\">הצג עוד</span>"):"")+
    "<input class=bqedit id=q"+n+" value=\""+esc(x.search||"").replace(/\"/g,"&quot;")+"\" placeholder=\"חידוד חיפוש (לא חובה): למשל 4 חדרים קרית ביאליק עד 2 מיליון\">"+
    "<div class=bbtns><button class=bsearch data-k=props data-q=\""+q+"\" data-e=q"+n+" data-row=\""+esc(String(x.row||""))+"\" data-r=\""+rid+"\"><svg class=eico viewBox='0 0 18 18'><rect x='4.2' y='2.6' width='9.6' height='12.8' rx='1'/><path d='M7 6h1.2M9.8 6H11M7 9h1.2M9.8 9H11M7 12h4'/><path d='M2.6 15.4h12.8'/></svg>חפש במשרד</button><button class=bsearch data-k=excl data-q=\""+q+"\" data-e=q"+n+" data-row=\""+esc(String(x.row||""))+"\" data-r=\""+rid+"\"><svg class=eico viewBox='0 0 18 18'><rect x='2.4' y='6' width='6.4' height='9.4' rx='1'/><rect x='9.4' y='3' width='6.2' height='12.4' rx='1'/></svg>חפש בשת״פ</button></div>"+
    "<div id="+rid+" class=bresults></div>"+
    "</div>";
}
var BSEQ=0,PDSEQ=0,SHARE_REG={},SHARE_SEQ=0;
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
    $("sres").innerHTML=h;shareUpd();
    if(kind=="props"||kind=="excl")loadRecent(kind);
  }).catch(function(){$("sres").innerHTML="<span class=err>שגיאה</span>";});
}
var SHARE_CLI={};
function shareUpd(){var n=document.querySelectorAll(".shchk:checked").length;var b=$("sharebar");if(!b)return;var sc=$("sharecount");if(sc)sc.textContent=n;if(n>0)b.classList.remove("hidden");else b.classList.add("hidden");}
function shareClose(){var o=$("shareovl");if(o)o.parentNode.removeChild(o);}
function shareOpen(){var n=document.querySelectorAll(".shchk:checked").length;if(!n)return;shareClose();
  var h='<div class=ovl id=shareovl><div class=ovlbox><div style="display:flex;justify-content:space-between;align-items:center"><b>שלח '+n+' נכסים ללקוח</b><button class="btn-ghost" style="width:auto;padding:4px 11px;margin:0" onclick="shareClose()">✕</button></div><div class=muted style="margin:6px 0 10px">בחר לקוח מ״הקונים שלי״ — תיפתח שיחת וואטסאפ שלך עם ההודעה מוכנה, בלי פרטי המקור.</div><input id=share_cli class=chip style="width:100%;box-sizing:border-box" placeholder="שם הלקוח (התחל להקליד)" list=share_clilist autocomplete=off><datalist id=share_clilist></datalist><div id=share_st class=muted style="margin-top:6px;min-height:16px"></div><button class="btn-gold" style="width:100%;margin-top:8px" onclick="shareSend()">פתח וואטסאפ ושלח</button></div></div>';
  var d=document.createElement("div");d.innerHTML=h;document.body.appendChild(d.firstElementChild);var o=$("shareovl");if(o)o.onclick=function(e){if(e.target.id=="shareovl")shareClose();};
  api("/api/my/buyers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({as:(typeof IMP!="undefined"?(IMP||""):"")})}).then(function(r){if(!r||!r.ok)return;SHARE_CLI={};var opts="";(r.results||[]).forEach(function(b){var nm=String(b.name||"").trim();if(!nm||SHARE_CLI[nm])return;SHARE_CLI[nm]={wa:(b.wa||""),phone:(b.phone||"")};opts+='<option value="'+esc(nm)+'">'+(b.phone?esc(b.phone):"")+'</option>';});var dl=$("share_clilist");if(dl)dl.innerHTML=opts;}).catch(function(){});}
function shareSend(){var nm=($("share_cli")?$("share_cli").value:"").trim();var c=SHARE_CLI[nm];var st=$("share_st");if(!c||!c.wa){if(st)st.innerHTML="<span class=err>בחר לקוח מהרשימה (עם מספר טלפון)</span>";return;}
  var ids=[];document.querySelectorAll(".shchk:checked").forEach(function(x){ids.push(x.dataset.sid);});
  if(!ids.length){if(st)st.innerHTML="<span class=err>לא נבחרו נכסים</span>";return;}
  var parts=ids.map(function(id){var p=SHARE_REG[id];if(!p)return"";var L=[];L.push("🏠 "+(p.type?p.type+" · ":"")+p.address+(p.city?", "+p.city:"")+(p.neighborhood?" ("+p.neighborhood+")":""));var meta=[p.rooms?p.rooms+" חד׳":"",p.size?p.size+" מ״ר":"",p.floor?"קומה "+p.floor:""].filter(Boolean).join(" · ");if(meta)L.push(meta);if(p.price)L.push("מחיר: "+p.price+" ₪");if(p.desc)L.push(p.desc);return L.join("\n");}).filter(Boolean);
  var msg="שלום"+(nm?" "+nm:"")+",\nריכזתי עבורך כמה נכסים שיכולים להתאים:\n\n"+parts.join("\n\n——————\n\n");
  window.open("https://wa.me/"+c.wa+"?text="+encodeURIComponent(msg),"_blank");shareClose();}
function card(kind,x){
  var _usvg="<svg class=eico viewBox='0 0 18 18'><circle cx='9' cy='6' r='2.6'/><path d='M4 15a5 5 0 0 1 10 0'/></svg>";
  if(kind=="props"){
    var pmeta=[x.rooms?x.rooms+" חד׳":"",x.size?x.size+' מ״ר':"",x.floor?"קומה "+x.floor:"",x.date?esc(x.date):""].filter(Boolean).join(" · ");
    var pacts=x.own?(x.pending?
        "<span class=lpend>בטיפול אצל המזכירה</span> <button class=lreq data-k=done data-id=\""+esc(x.id||"")+"\">✓ בוצע</button>":
        ("<button class=lreq data-k=remove data-id=\""+esc(x.id||"")+"\" data-addr=\""+encodeURIComponent(x.address||"")+"\">הסר מודעה</button> <button class=lreq data-k=price data-id=\""+esc(x.id||"")+"\" data-addr=\""+encodeURIComponent(x.address||"")+"\">עדכן מחיר</button>")):"";
    var did="pd"+(PDSEQ++);
    var pdesc=x.desc?("<div class='pdesc clamp' id="+did+">"+esc(x.desc)+"</div><span class=pmore onclick=\"var e=$('"+did+"');e.classList.toggle('clamp');this.textContent=e.classList.contains('clamp')?'עוד ▾':'פחות ▴';\">עוד ▾</span>"):"";
    var sid="sh"+(SHARE_SEQ++);SHARE_REG[sid]={type:(x.type||""),address:(x.address||""),city:(x.city||""),neighborhood:(x.neighborhood||""),rooms:(x.rooms||""),size:(x.size||""),floor:(x.floor||""),price:(x.price||""),desc:(x.desc||"")};
    return "<div class=pcard><div class=ptop><input type=checkbox class=shchk data-sid="+sid+" onchange=shareUpd() title='בחר לשליחה ללקוח'><div class=ptitle>"+esc(x.type||"נכס")+" · "+esc(x.address)+(x.neighborhood?" — "+esc(x.neighborhood):"")+", "+esc(x.city)+"</div>"+((x.score!==undefined&&x.score!=="")?"<span class=pscore>"+x.score+"%</span>":"")+"</div>"+
      (pmeta?"<div class=pmeta>"+pmeta+"</div>":"")+
      (x.price?"<div class=pprice>"+esc(fmtBudget(x.price))+"</div>":"")+
      pdesc+
      (x.agent?"<div class=pagent><span>"+_usvg+esc(x.agent)+"</span>"+(x.wa?"<a class=pwa href='https://wa.me/"+x.wa+"' target=_blank rel=noopener>וואטסאפ</a>":"")+"</div>":"")+
      (pacts?"<div class=pacts>"+pacts+"</div>":"")+"</div>";}
  if(kind=="excl"){var _dd=daysSince(x.date);
    var emeta=[(x.office?(isOurOffice(x.office)?"<span class=ouroffice>"+esc(x.office)+"</span>":esc(x.office)):""),x.date?esc(x.date):"",(_dd!=null?daysLabel(_dd):"")].filter(Boolean).join(" · ");
    var esid="sh"+(SHARE_SEQ++);SHARE_REG[esid]={type:"",address:(x.street||""),city:"",neighborhood:"",rooms:"",size:"",floor:"",price:(x.price||""),desc:((x.dest?x.dest+(x.desc?"\n":""):"")+(x.desc||""))};
    return "<div class=pcard><div class=ptop><input type=checkbox class=shchk data-sid="+esid+" onchange=shareUpd() title='בחר לשליחה ללקוח'><div class=ptitle>"+esc(x.street)+"</div><span class=pscore>"+x.score+"%</span></div>"+
      (x.dest?"<div class=pmeta>"+esc(x.dest)+"</div>":"")+
      (x.desc?"<div class=pdesc>"+esc(x.desc)+"</div>":"")+
      (x.price?"<div class=pprice>"+esc(fmtBudget(x.price))+"</div>":"")+
      (emeta?"<div class=pmeta>"+emeta+"</div>":"")+
      (x.link?"<div class=pacts><a class=plink href='"+x.link+"' target=_blank rel=noopener>נדל\"ן וואן</a></div>":"")+"</div>";}
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
function nbLock(on){var b=document.body;b.style.position="";b.style.top="";b.style.left="";b.style.right="";b.style.width="";}
var NBITEMS=[],NBSHOWN=20;
function viewNewborn(){
  NBSHOWN=20;
  $("view").innerHTML='<div class=card><h2>🐥 נכס נולד'+scopeLabel()+'</h2><div class=muted>צרו קשר עם בעלי הנכסים — המטרה: גיוס בבלעדיות 🏠</div><div class=muted id=nblive style=margin-top:6px>טוען…</div></div><div id=nblist></div><div id=nbmore style="text-align:center;margin:2px 0 16px"></div>';
  loadNewbornPage();
}
function renderNewborn(){
  if(!$("nblist"))return;
  if(!NBITEMS.length){$("nblist").innerHTML="<div class=card><div class=muted>אין נכסים זמינים עבורך כרגע.</div></div>";if($("nbmore"))$("nbmore").innerHTML="";return;}
  $("nblist").innerHTML=NBITEMS.slice(0,NBSHOWN).map(nbCard).join("");
  var m=$("nbmore");if(m){m.innerHTML=(NBITEMS.length>NBSHOWN)?"<button class=sec onclick=nbLoadMore() style=width:auto;display:inline-block;padding:11px 24px>טען עוד ("+(NBITEMS.length-NBSHOWN)+")</button>":"";}
}
function nbLoadMore(){NBSHOWN+=20;renderNewborn();}
function loadNewbornPage(){
  api("/api/newborn"+nbAs()).then(function(r){
    if(!$("nblist"))return;
    if(!r||!r.ok){$("nblist").innerHTML="<div class=card><div class=err>שגיאה</div></div>";return;}
    NBDATA=r;
    NBITEMS=(r.results||[]).filter(function(x){return x.released;});
    var lv=$("nblive");if(lv)lv.innerHTML="🟢 "+NBITEMS.length+" נכסים לגיוס";
    renderNewborn();
  }).catch(function(){if($("nblist"))$("nblist").innerHTML="<div class=card><div class=err>שגיאה</div></div>";});
}
function nbCard(x){
  var k=encodeURIComponent(x.key||""),a=encodeURIComponent(x.address||""),ph=x.phone||"";
  return "<div class=nbcardx>"+
    "<div class=nbtop><b class=nbaddr>🏠 "+esc(x.address||x.city||"נכס")+"</b>"+(x.date?"<span class=nbdate>📅 "+esc(x.date)+"</span>":"")+"</div>"+
    ((x.city&&x.address)?"<div class=muted>"+esc(x.city)+"</div>":"")+
    (x.desc?"<div class=nbdesc>"+esc(x.desc)+"</div>":"")+
    (x.price?"<div class=nbprice>💰 "+esc(x.price)+"</div>":"")+
    (x.notes?"<div class=muted style=margin-top:4px>"+esc(x.notes)+"</div>":"")+
    "<div class=nbowner>👤 "+esc(x.owner||"בעל הנכס")+(ph?" · "+esc(ph):"")+"</div>"+
    "<div class=nbacts>"+
      (ph?"<a class='nbbtn call' href='tel:"+esc(ph)+"' onclick=\"nbMark('"+k+"','"+a+"')\">📞 חייג</a>":"")+
      (x.wa?"<a class='nbbtn wa' href='https://wa.me/"+x.wa+"?text="+nbWaMsg(x)+"' target=_blank rel=noopener onclick=\"nbMark('"+k+"','"+a+"')\">💬 וואטסאפ</a>":"")+
      (x.link?"<a class='nbbtn link' href='"+esc(x.link)+"' target=_blank rel=noopener>🔗 צפייה במודעה</a>":"")+
    "</div>"+
    ((ROLE=="admin"&&x.contacted&&x.contacted.length)?"<div class=nbcontact>📲 כבר פנו: "+x.contacted.map(esc).join(", ")+"</div>":"")+
  "</div>";
}
function nbWaMsg(x){var who=NAME?(" מדבר/ת "+NAME):"";var m="שלום!"+who+" מ-RE/MAX Family 🏠 ראיתי את הנכס שלך"+(x.address?(" ב"+x.address):"")+" למכירה, ואשמח לעזור לך למכור אותו במחיר הטוב ביותר ובליווי מקצועי. אפשר לדבר?";return encodeURIComponent(m);}
function nbMark(k,a,reload){try{k=decodeURIComponent(k||"");a=decodeURIComponent(a||"");api("/api/newborn/contact",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,addr:a,as:IMP||""})}).then(function(){if(reload)loadNewbornPage();}).catch(function(){});}catch(e){}return true;}
function closeNewborn(){$("nbmodal").classList.add("hidden");nbLock(false);}
var VPHONE="";
function copyVphone(){if(!VPHONE)return;var b=$("vpcopybtn");var ok=function(){if(b){var t=b.innerHTML;b.innerHTML="✓ הועתק";setTimeout(function(){b.innerHTML=t;},1500);}};
  try{if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(VPHONE).then(ok,function(){vpFallbackCopy(VPHONE);ok();});return;}}catch(e){}
  vpFallbackCopy(VPHONE);ok();}
function vpFallbackCopy(t){try{var ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.focus();ta.select();document.execCommand("copy");document.body.removeChild(ta);}catch(e){}}
function nbWa(k,a){try{k=decodeURIComponent(k||"");a=decodeURIComponent(a||"");api("/api/newborn/contact",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,addr:a,as:IMP||""})}).catch(function(){});}catch(e){}return true;}
function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function isOurOffice(o){var t=String(o||"").toLowerCase().replace(/[\s\/\\.\-_'"׳״]/g,"");var rmx=t.indexOf("remax")>-1||t.indexOf("רימקס")>-1||t.indexOf("רמקס")>-1;var fam=t.indexOf("family")>-1||t.indexOf("פמילי")>-1||t.indexOf("פמלי")>-1;return rmx&&fam;}
function daysSince(s){if(!s)return null;s=String(s).trim();var d;var m=s.match(/^(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})/);if(m){d=new Date(+m[3],+m[2]-1,+m[1]);}else{d=new Date(s.slice(0,10));}if(isNaN(d))return null;var n=Math.floor((Date.now()-d.getTime())/86400000);return n<0?0:n;}
function daysLabel(dd){return dd==0?"נכנס לבלעדיות היום":(dd==1?"יום אחד בבלעדיות":dd+" ימים בבלעדיות");}
</script></div></body></html>'''

# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND CACHE WARMER — מרענן ברקע את הקריאות הכבדות מ-Apps Script,
# כך שבקשות הסוכנים תמיד מקבלות תשובה מיידית מהמטמון (לא ממתינות בתור).
# עדכון אטומי בלבד (אף פעם לא מרוקן את המטמון תוך כדי). config-agnostic לשכפול.
# ══════════════════════════════════════════════════════════════════════════════
WARM_INTERVAL = int(os.environ.get("WARM_INTERVAL", "30") or 30)

def _warm_once():
    for _tab in ("שיחות", "חתימות", "נכסים"):
        try:
            _r = _web_fetch_raw_uncached(_tab)
            if _r:
                _cache_put("raw:%s:01/01/2020:31/12/2099" % _tab, _r)
        except Exception:
            pass
    try:
        _j = _buyers_apps_post("listnewborn", {})
        if _j and _j.get("ok"):
            _cache_put("newborn_rows", _j.get("rows", []) or [])
    except Exception:
        pass
    try:   # קונפיג (תפקידים/צוותים/כינויים) — שמירה חמה כדי שלא יחסום תחת עומס
        _jc = _buyers_apps_post("getconfig", {})
        if _jc and _jc.get("ok"):
            _rawc = (_jc.get("config") or "").strip()
            _cfgc = _json.loads(_rawc) if _rawc else {}
            if isinstance(_cfgc, dict): _cache_put("app_config", _cfgc)
    except Exception:
        pass
    try:
        if APPS_SCRIPT_URL and APPS_SCRIPT_TOKEN:
            from urllib.parse import quote as _q
            _u = ("%s?action=raw&type=%s&from=01/01/2020&to=31/12/2099&token=%s"
                  % (APPS_SCRIPT_URL, _q("בלעדויות חיצוניות"), APPS_SCRIPT_TOKEN))
            _rr = requests.get(_u, timeout=30, allow_redirects=True)
            if _rr.status_code == 200 and _rr.json().get("ok"):
                _external_excl_cache["data"] = _rr.json().get("rows", [])
                _external_excl_cache["ts"] = time.time()
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

_start_warmer()

# ══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    log.info("Installing dependencies...")
    install_deps()
    log.info(f"Bot starting — trigger word: '{TRIGGER_WORD}'")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
