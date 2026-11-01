"""social_video.py — סרטוני סטורי + ריל לנכסי המשרד (Kling ב-fal + ffmpeg), אישור בוואטסאפ, פרסום ל-Meta.

ספק: docs/superpowers/specs/2026-11-02-social-video-stories-reels-design.md
תוכנית: docs/superpowers/plans/2026-11-02-social-video.md
החלק העליון טהור (טקסטים, תזמון, חיתוך, תקרות, מכונת מצבים); הרינדור, fal, Claude ו-Graph מוזרקים.
SOCIAL_MODE: רק 'publish' שולח וואטסאפ אישור וכותב ל-Meta (social_publish.soc_mode).
"""
from __future__ import annotations
import re

import social_publish as SP

DAILY_CAP = 3
MONTH_AI_CAP = 100
APPROVE_H = 48
RETRY_DAYS = 3
REPEAT_DAYS = 14
KEEP_FINAL_DAYS = 3
KEEP_MAX_DAYS = 10
DIR_MAX_BYTES = 1_000_000_000
FAL_TIMEOUT_S = 480
RENDER_TIMEOUT_S = 180
W, H = 1080, 1920
SAFE = (65, 290, 1015, 1240)
XFADE = 0.4
LOOP_SEC = 600
CTA = "שלחו הודעה ונחזור אליכם"


# ── טקסטים ותזמון ────────────────────────────────────────────────────────────────
def vid_texts(row, feats, highlight, agent, vphone, office_phone):
    """שורת נכס → הטקסטים שעל המסך, לפי קטע. בלי מספר בית, בלי טלפון בעלים, בלי 'None'."""
    rent = "שכר" in str(row.get("סוג עסקה") or "")
    rooms = SP._num(row.get("חדרים"))
    kind = SP._norm(row.get("סוג נכס")) or "נכס"
    deal = "להשכרה" if rent else "למכירה"
    what = (rooms + " חדרים") if rooms and rooms != "0" else kind
    nb, city = SP._norm(row.get("שכונה")), SP._norm(row.get("עיר / ישוב"))
    pr = SP._price(row.get("מחיר"))
    price = (pr + " ₪" + (" לחודש" if rent else "")) if pr else ""
    size, fl = SP._num(row.get('מ"ר')), SP.soc_floor(row)
    spec = " · ".join(x for x in ((size + ' מ"ר') if size and size != "0" else "", ("קומה " + fl) if fl else "") if x)
    ft = " · ".join([f for f in (feats or []) if f][:3])
    hl = SP.soc_scrub_house(SP.soc_scrub_phones(highlight or ""), row.get("כתובת")).strip(" ·-,")
    s3 = {"main": hl, "sub": ft} if hl else {"main": ft, "sub": ""}
    return {
        "open": {"chip": "חדש בשוק", "title": what + " " + deal,
                 "place": ", ".join(x for x in (nb, city) if x), "price": price},
        "s2": {"main": spec, "sub": ""},
        "s3": s3,
        "end": {"recap": " · ".join(x for x in ((rooms + " חדרים") if rooms and rooms != "0" else "", pr and pr + " ₪") if x),
                "agent": str(agent or "").strip(), "phone": str(vphone or office_phone or "").strip(), "cta": CTA},
    }


def vid_timeline(n_slides, ai):
    """רשימת (קטע, אורך בשניות) — ~14ש' כולל. n_slides = תמונות מצגת אחרי תמונת ה-AI (1 או יותר)."""
    first = "ai" if ai else "kb"
    if n_slides <= 1:
        return [(first, 5), ("s2", 4.5), ("end", 4.5)]
    return [(first, 5), ("s2", 4), ("s3", 2.5), ("end", 2.5)]
