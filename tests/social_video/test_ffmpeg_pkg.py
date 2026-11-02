# tests/social_video/test_ffmpeg_pkg.py — ה-ffmpeg של Render מגיע מ-imageio-ffmpeg; xfade קיים רק מ-ffmpeg 4.3.
# 0.5.1 ארז ffmpeg 4.2.2 (No such filter: 'xfade' בפרוד, 02/11); מ-0.6.0 הוא ffmpeg 7.0.2.
import os, re
req = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "requirements.txt")).read()
m = re.search(r"^imageio-ffmpeg==(\d+)\.(\d+)\.(\d+)", req, re.M)
assert m, "imageio-ffmpeg not pinned"
assert tuple(map(int, m.groups())) >= (0, 6, 0), "imageio-ffmpeg %s bundles ffmpeg < 4.3 (no xfade)" % ".".join(m.groups())
print("ffmpeg_pkg OK 2")
