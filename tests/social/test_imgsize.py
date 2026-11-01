# tests/social/test_imgsize.py — התמונה ממלאת את הריבוע באינסטגרם (01/11: תמונת יד2 ~800px ישבה בחצי גודל באמצע)
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from PIL import Image
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP

def make(w, h):
    # לוח שחמט עדין: הטשטוש ברקע הופך אותו לאפור, רק התמונה עצמה שומרת על ניגודיות
    im = Image.new("RGB", (w, h))
    im.putdata([(255, 255, 255) if ((x // 8) + (y // 8)) % 2 else (0, 0, 0) for y in range(h) for x in range(w)])
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()

def red_box(jpg):
    im = Image.open(io.BytesIO(jpg)).convert("RGB")
    px = im.load(); S = im.size[0]
    sharp = lambda a, b: abs(sum(a) - sum(b)) > 300
    xs = [x for x in range(0, S - 24, 4) if any(sharp(px[x, S // 2], px[x + d, S // 2]) for d in range(1, 24))]
    ys = [y for y in range(0, S - 24, 4) if any(sharp(px[S // 2, y], px[S // 2, y + d]) for d in range(1, 24))]
    return im.size, (max(xs) - min(xs) + 24 if xs else 0), (max(ys) - min(ys) + 24 if ys else 0)

S = SP.IMG_MAX_PX
size, w, h = red_box(SP.soc_jpeg(make(800, 600), True))       # לרוחב, קטנה — כמו יד2
ck(size == (S, S), size)
ck(w >= S - 40, ("landscape should fill width", w))
ck(abs(h - S * 600 / 800) <= 40, ("height keeps ratio", h))
size, w, h = red_box(SP.soc_jpeg(make(600, 800), True))       # לאורך
ck(h >= S - 40 and abs(w - S * 600 / 800) <= 40, ("portrait fills height", w, h))
size, w, h = red_box(SP.soc_jpeg(make(3000, 2000), True))     # גדולה — מוקטנת, עדיין ממלאת רוחב
ck(w >= S - 40, ("big landscape fills width", w))
print("ok", n)

# הורדה בגודל המלא מיד2 (?c=6) — ונפילה לכתובת המקורית בכשל
ck(SP.soc_big_url("https://img.yad2.co.il/Pic/a/o/x.jpeg") == "https://img.yad2.co.il/Pic/a/o/x.jpeg?c=6", "yad2 gets c=6")
ck(SP.soc_big_url("https://img.yad2.co.il/Pic/a/x.jpeg?c=3") == "https://img.yad2.co.il/Pic/a/x.jpeg?c=6", "c replaced")
ck(SP.soc_big_url("https://example.com/x.jpg") == "https://example.com/x.jpg", "others untouched")

class R:
    def __init__(s, code, content=b""): s.status_code, s.content = code, content
class H:
    def __init__(s, plan): s.plan, s.urls = plan, []
    def get(s, url, **kw):
        s.urls.append(url); return s.plan(url)
big = make(1200, 900)
h = H(lambda u: R(200, big))
ck(SP.soc_fetch_jpeg(h, "https://img.yad2.co.il/p/x.jpeg", True) is not None and h.urls == ["https://img.yad2.co.il/p/x.jpeg?c=6"], h.urls)
h = H(lambda u: R(404) if "c=6" in u else R(200, big))
ck(SP.soc_fetch_jpeg(h, "https://img.yad2.co.il/p/x.jpeg", True) is not None and len(h.urls) == 2, ("fallback", h.urls))
print("ok", n)
