# tests/social_video/test_layers.py — שכבות PNG: גודל, אזור בטוח, "הדמיית תנועה"
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from PIL import Image
import social_video as V
from _fakes import ROW
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
LOGO = os.path.join(ROOT, "family-logo.png")
T = V.vid_texts(ROW, ["מעלית", "ממ\"ד"], "משופצת מהיסוד", "דנה כהן", "072-555-0101", "")

def text_bbox(path):
    """תיבת הפיקסלים של הטקסט והלוגו: אטומים, בהירים (לבן/זהב) — לא ההצללה הכהה."""
    im = Image.open(path).convert("RGBA")
    px = im.load(); xs = []; ys = []
    for y in range(0, im.height, 3):
        for x in range(0, im.width, 3):
            r, g, b, a = px[x, y]
            if a > 200 and r > 170 and g > 140:
                xs.append(x); ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None

d = tempfile.mkdtemp()
tl = V.vid_timeline(2, True)
L = V.vid_layers(T, tl, LOGO, True, d)
ck(sorted(L) == ["ai", "end", "s2", "s3"], L)
for k, p in L.items():
    im = Image.open(p)
    ck(im.size == (1080, 1920) and im.mode == "RGBA", (k, im.size, im.mode))
    bb = text_bbox(p)
    ck(bb is not None, k)
    x0, y0, x1, y1 = V.SAFE
    ck(bb[0] >= x0 - 3 and bb[1] >= y0 - 3 and bb[2] <= x1 + 3 and bb[3] <= y1 + 3, (k, bb))

def note_pixels(path):
    im = Image.open(path).convert("RGBA"); px = im.load()
    return sum(1 for y in range(1195, 1240) for x in range(880, 1015) if px[x, y][3] > 150 and px[x, y][0] > 170)
ck(note_pixels(L["ai"]) > 20, "AI note on ai layer")
d2 = tempfile.mkdtemp()
L2 = V.vid_layers(T, V.vid_timeline(2, False), LOGO, False, d2)
ck("kb" in L2 and note_pixels(L2["kb"]) == 0, "no AI note on kb")

empty = {"open": {"chip": "", "title": "", "place": "", "price": ""}, "s2": {"main": "", "sub": ""},
         "s3": {"main": "", "sub": ""}, "end": {"recap": "", "agent": "", "phone": "", "cta": ""}}
L3 = V.vid_layers(empty, V.vid_timeline(1, True), LOGO, True, tempfile.mkdtemp())
ck(sorted(L3) == ["ai", "end", "s2"], L3)
print("video_layers OK", n)
