"""prop_share.py — שליחת נכס ללקוח בוואטסאפ עם התמונות (אייל 01/11).

הסוכן לוחץ בכרטיס הנכס (המשרד שלנו / שלי) → טקסט מוכן + עד 10 תמונות → חלון השיתוף של הטלפון.
בטקסט אין שם סוכן, מספר בית, טלפונים או קישורים. התמונות עוברות דרך השרת (יד2 לא מרשה להוריד מהדפדפן).
עזרי הניקוי והתמונות משותפים עם social_publish.
"""
from __future__ import annotations
import re
import time

from social_publish import (soc_scrub_phones, soc_scrub_house, soc_floor, soc_images, soc_fetch_jpeg,
                            _num, _norm, _price, _cut)

DESC_MAX = 700
MAX_IMAGES = 10
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)


def share_images(row):
    return soc_images(row)[:MAX_IMAGES]


def _scrub_name(text, name):
    full = _norm(name)
    for part in sorted({full} | ({full.split()[0]} if len(full.split()) > 1 else set()), key=len, reverse=True):   # השם המלא קודם
        if len(part) >= 2:
            text = re.sub(r"(?<![א-ת])[ובלהמשכ]?" + re.escape(part).replace(r"\ ", r"\s+") + r"(?![א-ת])", "", text)
    return text


def share_text(row, clean_desc, feats):
    """שורת נכס → טקסט ללקוח. בלי אימוג'ים, בלי שם הסוכן, מספר בית, טלפונים וקישורים."""
    rent = "שכר" in str(row.get("סוג עסקה") or "")
    kind = _norm(row.get("סוג נכס")) or "נכס"
    rooms, size, fl = _num(row.get("חדרים")), _num(row.get('מ"ר')), soc_floor(row)
    head = kind + ((" " + rooms + " חדרים") if rooms and rooms != "0" else "") + (" להשכרה" if rent else " למכירה")
    spec = [head] + [x for x in ((size + ' מ"ר') if size and size != "0" else "", ("קומה " + fl) if fl else "") if x]
    street = re.sub(r"\s*(?:מס['׳]?\s*)?[\d/]+[א-ת]?\s*$", "", _norm(row.get("כתובת")))
    where = ", ".join(x for x in (street, _norm(row.get("שכונה")), _norm(row.get("עיר / ישוב"))) if x)
    lines = [" · ".join(spec)]
    if where:
        lines.append(where)
    pr = _price(row.get("מחיר"))
    if pr:
        lines.append("מחיר: " + pr + " ₪" + (" לחודש" if rent else ""))
    ft = [f for f in (feats(row) or []) if f]
    if ft:
        lines.append(" · ".join(ft))
    desc = clean_desc(row.get("_desc_ae") or row.get("תיאור") or "")
    desc = _URL_RE.sub("", soc_scrub_phones(desc))
    desc = soc_scrub_house(desc, row.get("כתובת"))
    desc = _scrub_name(desc, row.get("סוכן 1") or "")
    desc = re.sub(r"[ \t]{2,}", " ", desc)
    desc = _cut(re.sub(r"\s+\n", "\n", desc).strip(" ,.-"), DESC_MAX)
    text = "\n".join(lines)
    return text + ("\n\n" + desc if desc else "")


def register(app, G):
    from flask import jsonify, request, Response
    from urllib.parse import quote
    import requests as _http
    cache = {}

    def find(key):
        if not key:
            return None
        rows = list(G["fetch_sheet_rows"]() or [])
        for lbl in (G.get("OFFICE_DEALS") or {}).values():
            try:
                rows += list(G["fetch_sheet_rows_deal"](lbl) or [])
            except Exception:
                pass
        return next((r for r in rows if G["_prop_price_key"](r) == key), None)

    def clean_desc():
        try:
            import effie_v2
            return effie_v2.y2_clean_desc
        except Exception:
            return lambda d: str(d or "")

    @app.route("/v2/api/prop/share", methods=["GET"])
    def v2_api_prop_share():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        key = str(request.args.get("key", "") or "").strip()
        row = find(key)
        if not row:
            return jsonify({"ok": False, "reason": "not_found"}), 404
        n = len(share_images(row))
        try:
            G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), "שליחת נכס ללקוח",
                               ", ".join(x for x in (_norm(row.get("כתובת")), _norm(row.get("עיר / ישוב"))) if x) +
                               " · " + str(n) + " תמונות")
        except Exception:
            pass
        return jsonify({"ok": True, "text": share_text(row, clean_desc(), G["_row_feats"]),
                        "images": ["/v2/api/prop/share/img?key=%s&i=%d" % (quote(key), i) for i in range(n)]})

    @app.route("/v2/api/prop/share/img", methods=["GET"])
    def v2_api_prop_share_img():
        if not G["_web_auth"]():
            return Response("", status=401)
        key = str(request.args.get("key", "") or "").strip()
        try:
            i = int(request.args.get("i", "0"))
        except ValueError:
            return Response("", status=400)
        now = time.time()
        hit = cache.get((key, i))
        if hit and now - hit[0] < 900:
            data = hit[1]
        else:
            row = find(key)
            urls = share_images(row) if row else []
            if not (0 <= i < len(urls)):
                return Response("", status=404)
            data = soc_fetch_jpeg(_http, urls[i], False)
            if not data:
                return Response("", status=404)
            if len(cache) > 80:
                for k in sorted(cache, key=lambda k: cache[k][0])[:40]:
                    cache.pop(k, None)
            cache[(key, i)] = (now, data)
        return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=900"})
