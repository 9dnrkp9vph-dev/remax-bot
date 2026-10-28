# ai_digest.py — [AI-DIGEST 29/10 אייל] 'תריץ סריקת AI אוטומטית כל יום ב-11 בבוקר ותשלח לי מייל של כל השינויים
# מיום לפני, רק של המסך הזה (בלי שבתות וחגים)'. פונקציות טהורות; ההרצה והשליחה ב-app.py (_ai_digest_tick).
# 'שינוי' = התראה שלא הייתה בסריקה הקודמת (גם אם התאריך שלה ישן), או התראה שהמצב שלה השתנה.
# אחרי שבת/חג הסריקה הבאה מכסה את כל מה שהצטבר מאז המייל האחרון.
import html as _h
import time as _t

WEEKEND_DAY = 5   # שבת (datetime.weekday)


def digest_diff(records, prev, since_ts):
    """records = רשומות טאב ה-AI; prev = {key: status} מהמייל הקודם (None = ריצה ראשונה).
    מחזיר (חדשות, שעודכנו, צילום חדש). ריצה ראשונה: חדשות = מה שהתאריך שלו מאז since_ts."""
    snap, new, changed = {}, [], []
    for r in records or []:
        k = str(r.get("key") or "")
        if not k:
            continue
        st = str(r.get("status") or "")
        snap[k] = st
        if prev is None:
            if float(r.get("date") or 0) >= since_ts:
                new.append(r)
        elif k not in prev:
            new.append(r)
        elif prev.get(k, "") != st:
            changed.append(dict(r, prev_status=prev.get(k, "")))
    by = lambda r: -float(r.get("date") or 0)
    return sorted(new, key=by), sorted(changed, key=by), snap


def digest_due(now, rec, quiet, hour, now_ts=None):
    """פעם ביום מ-hour ואילך; לא בשבת ולא בחלון שבת/חג; כשל → ניסיון חוזר כל 15 דק', עד 8."""
    now_ts = _t.time() if now_ts is None else now_ts
    rec = rec or {}
    if now.hour < hour or now.weekday() == WEEKEND_DAY or quiet or rec.get("ok"):
        return False
    return int(rec.get("tries") or 0) < 8 and (now_ts - float(rec.get("ts") or 0)) >= 900


def _abs(base, link):
    link = str(link or "").strip()
    if link.startswith("/"):
        return base.rstrip("/") + link
    return link


def _links(r, base):
    out = []
    for lab, k in (("למודעה", "link"), ("לקונה", "buyer_link"), ("לעסקאות", "deals_link"), ("למסמכים", "inv_link")):
        u = _abs(base, r.get(k))
        if u.startswith("http"):
            out.append((lab, u))
    return out


def digest_render(new, changed, office, base, day):
    """→ (נושא, html, טקסט). מייל בעברית מימין לשמאל, טבלאות עם עיצוב מוטמע (כמו הדוח היומי)."""
    tab = base.rstrip("/") + "/v2/crm/ai"
    if new or changed:
        parts = []
        if new:
            parts.append("%d חדשות" % len(new) if len(new) > 1 else "1 חדשה")
        if changed:
            parts.append("%d עודכנו" % len(changed) if len(changed) > 1 else "1 עודכנה")
        subj = "התראות AI · %s · %s" % (day, " · ".join(parts))
    else:
        subj = "התראות AI · %s · אין שינויים" % day
    e = lambda s: _h.escape(str(s or ""))

    def row_html(r, extra=""):
        links = " · ".join('<a href="%s" style="color:#2E6BD6">%s</a>' % (e(u), e(lab)) for lab, u in _links(r, base))
        return ('<tr><td style="padding:10px;border-bottom:1px solid #EEE;vertical-align:top">'
                '<div style="font-size:12px;color:#7A5E1C;font-weight:700">%s</div>'
                '<div style="font-size:15px;font-weight:700;color:#1E3A5F">%s · <span dir="ltr">%s</span></div>'
                '<div style="font-size:14px;color:#222">%s</div>%s'
                '<div style="font-size:12px;color:#5B6472">סוכן: %s%s</div>%s</td></tr>') % (
            e(r.get("type")), e(r.get("name")), e(r.get("phone")), e(r.get("what")),
            ('<div style="font-size:12px;color:#5B6472">לקוח עבר: %s</div>' % e(r.get("past"))) if r.get("past") else "",
            e(r.get("agent")) or "—", extra,
            ('<div style="font-size:13px;margin-top:4px">%s</div>' % links) if links else "")

    def section(title, rows):
        return ('<h3 style="color:#1E3A5F;font-size:16px;margin:18px 0 6px">%s</h3>'
                '<table width="100%%" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px">%s</table>') % (
            e(title), "".join(rows))

    body = []
    if new:
        body.append(section("התראות חדשות · %d" % len(new), [row_html(r) for r in new]))
    if changed:
        body.append(section("התראות שהמצב שלהן השתנה · %d" % len(changed),
                            [row_html(r, " · היה: %s · עכשיו: %s" % (e(r.get("prev_status")) or "—", e(r.get("status")) or "—"))
                             for r in changed]))
    if not body:
        body.append('<p style="font-size:15px;color:#222">אין התראות חדשות ואין שינויים מאז המייל הקודם.</p>')
    html = ('<div dir="rtl" style="font-family:Arial,Helvetica,sans-serif;background:#F2EFE7;padding:18px;text-align:right">'
            '<h2 style="color:#1E3A5F;margin:0 0 4px">התראות AI · %s</h2>'
            '<div style="color:#5B6472;font-size:13px">%s · השינויים מאז המייל הקודם</div>%s'
            '<p style="margin-top:18px"><a href="%s" style="background:#2E6BD6;color:#fff;padding:10px 16px;border-radius:10px;'
            'text-decoration:none;font-weight:700">פתח את טאב AI ב-CRM</a></p></div>') % (e(day), e(office), "".join(body), e(tab))

    lines = [subj, ""]
    for title, rows in (("התראות חדשות", new), ("עודכנו", changed)):
        if rows:
            lines.append(title + ":")
            for r in rows:
                st = (" · היה: %s · עכשיו: %s" % (r.get("prev_status") or "—", r.get("status") or "—")) if "prev_status" in r else ""
                lines.append("- %s · %s %s · %s · סוכן: %s%s" % (r.get("type"), r.get("name"), r.get("phone"), r.get("what"),
                                                             r.get("agent") or "—", st))
                for lab, u in _links(r, base):
                    lines.append("  %s: %s" % (lab, u))
            lines.append("")
    if not (new or changed):
        lines.append("אין התראות חדשות ואין שינויים מאז המייל הקודם.")
    lines.append("טאב AI: " + tab)
    return subj, html, "\n".join(lines)


def digest_wa_text(new, changed, base, day):
    """[29/10 אייל] לקוחות חוזרים — הודעת וואטסאפ לבעל המשרד בלבד ('רק לוואטסאפ שלי כרגע, לא לסוכנים').
    רק התראות 'לקוח חוזר' (חדשות או שהמצב שלהן השתנה); אין כאלה → '' (לא שולחים)."""
    rows = [r for r in list(new or []) + list(changed or []) if r.get("type") == "לקוח חוזר"]
    if not rows:
        return ""
    lines = ["לקוחות חוזרים · %s" % day, ""]
    for r in rows:
        lines.append("• %s %s" % (r.get("name") or "", r.get("phone") or ""))
        lines.append("  %s" % (r.get("what") or ""))
        lines.append("  סוכן: %s · %s" % (r.get("agent") or "—", r.get("status") or ""))
        if r.get("past"):
            lines.append("  לקוח עבר: %s" % r["past"])
    lines += ["", "ב-CRM: " + base.rstrip("/") + "/v2/crm/ai"]
    return "\n".join(lines)
