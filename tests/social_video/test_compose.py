# tests/social_video/test_compose.py — הרכבה אמיתית ב-ffmpeg (מדולג אם אין ffmpeg)
import os, sys, io, json, subprocess, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
from PIL import Image
import social_video as V
from _fakes import ROW
FF = V.vid_ffmpeg()
if not FF:
    print("video_compose SKIPPED (no ffmpeg)"); sys.exit(0)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
d = tempfile.mkdtemp()

def jpg(color):
    b = io.BytesIO(); Image.new("RGB", (1440, 960), color).save(b, "JPEG"); return b.getvalue()
slides = [(jpg((200, 120, 60)), (0.03, 0.03, 0.17, 0.13)), (jpg((60, 160, 90)), None), (jpg((40, 60, 160)), None)]
T = V.vid_texts(ROW, ["מעלית"], "", "דנה כהן", "072-555-0101", "")
clip = os.path.join(d, "clip.mp4")
subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=768x1364:rate=24", "-t", "5",
                "-pix_fmt", "yuv420p", clip], check=True)

def probe(p):
    fp = FF.replace("ffmpeg", "ffprobe")
    if os.path.exists(fp) or FF == "ffmpeg":
        out = subprocess.run([fp, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration",
                              "-of", "json", p], capture_output=True, text=True).stdout
        return json.loads(out)
    return None

for ai in (True, False):
    tl = V.vid_timeline(2, ai)
    L = V.vid_layers(T, tl, os.path.join(ROOT, "family-logo.png"), ai, os.path.join(d, "L%d" % ai))
    out = os.path.join(d, "out%d.mp4" % ai)
    r = V.vid_compose(clip if ai else None, slides, L, tl, None, out)
    ck(r["ok"], r)
    ck(abs(r["duration"] - 14) <= 0.6, r)
    ck(os.path.exists(r["cover"]) and Image.open(r["cover"]).size == (1080, 1920), r)
    head = open(out, "rb").read(65536)
    ck(head.find(b"moov") != -1 and (head.find(b"mdat") == -1 or head.find(b"moov") < head.find(b"mdat")), "faststart")
    j = probe(out)
    if j:
        v = [s for s in j["streams"] if s["codec_type"] == "video"][0]
        a = [s for s in j["streams"] if s["codec_type"] == "audio"]
        ck(v["width"] == 1080 and v["height"] == 1920 and v["codec_name"] == "h264", v)
        ck(a and a[0]["codec_name"] == "aac", a)

ck(V.vid_music("tok1") in (None,) or os.path.exists(V.vid_music("tok1")), "music path")

def boom(*a, **k):
    raise subprocess.TimeoutExpired("ffmpeg", 1)
r = V.vid_compose(clip, slides, L, V.vid_timeline(2, False), None, os.path.join(d, "x.mp4"), run=boom)
ck(r["ok"] is False and "timeout" in r.get("error", ""), r)
print("video_compose OK", n)
