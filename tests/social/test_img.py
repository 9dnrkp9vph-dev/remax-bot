# tests/social/test_img.py — soc_jpeg / ImgStore / soc_fetch_jpeg
import os, sys, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import social_publish as SP
from PIL import Image

def mk(w, h, fmt="PNG", color=(200, 30, 30)):
    im = Image.new("RGB", (w, h), color)
    for x in range(w // 2 - 20, w // 2 + 20):          # ריבוע כחול במרכז
        for y in range(h // 2 - 20, h // 2 + 20):
            im.putpixel((x, y), (20, 40, 220))
    b = io.BytesIO(); im.save(b, fmt); return b.getvalue()

raw = mk(2000, 1000)
j = SP.soc_jpeg(raw, False)
ck(j[:2] == b"\xff\xd8", "jpeg magic")
im = Image.open(io.BytesIO(j)); ck(im.size == (1440, 720), im.size)
sq = Image.open(io.BytesIO(SP.soc_jpeg(raw, True)))
ck(sq.size == (1440, 1440), sq.size)
c = sq.convert("RGB").getpixel((720, 720)); ck(c[2] > 150 and c[0] < 100, ("center kept", c))
corner = sq.convert("RGB").getpixel((5, 5)); ck(corner != (255, 255, 255) and corner[0] > 100, ("blur bg", corner))
ck(SP.soc_jpeg(mk(800, 600, "WEBP"), False)[:2] == b"\xff\xd8", "webp -> jpeg")
ck(SP.soc_jpeg(b"not an image", False) is None, "garbage")

S = SP.ImgStore()
t1 = S.put("https://x/a.jpg", 1000.0); t2 = S.put("https://x/b.jpg", 1000.0)
ck(t1 != t2 and len(t1) >= 16, (t1, t2))
ck(S.get(t1, 1000.0 + 3600) == "https://x/a.jpg", "get")
ck(S.get(t1, 1000.0 + 25 * 3600) is None, "expired")
ck(S.get("nope", 1000.0) is None, "missing")

class Resp:
    def __init__(s, code, content, ctype="image/jpeg"): s.status_code = code; s.content = content; s.headers = {"Content-Type": ctype}
class Http:
    def __init__(s, mode): s.mode = mode
    def get(s, url, timeout=None, headers=None):
        if s.mode == "timeout": raise TimeoutError("t")
        if s.mode == "404": return Resp(404, b"")
        if s.mode == "html": return Resp(200, b"<html>", "text/html")
        return Resp(200, raw)
for m in ("timeout", "404", "html"):
    ck(SP.soc_fetch_jpeg(Http(m), "https://x/a.jpg", False) is None, m)
ck(SP.soc_fetch_jpeg(Http("ok"), "https://x/a.jpg", True)[:2] == b"\xff\xd8", "ok")
print("social_img OK", n)
