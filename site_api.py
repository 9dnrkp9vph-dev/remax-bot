"""site_api.py — ממשק אפי לאתר refamily.co.il (שלב ג', 13/10/2026).

מודול נפרד מ-effie_v2: ראוטים לאתר (חיפוש AI + טפסים במייל) וניהול האתר (הסתר/מומלץ, מסך "האתר").
נרשם מ-app.py אחרי effie_v2.register:  site_api.register_site(app, globals())
env: SITE_KEY — אותו ערך באתר ובאפי (ריק = הראוטים לאתר כבויים); SITE_PUBLIC_URL — כתובת האתר לקישור "צפה באתר".
"""
from __future__ import annotations
import hmac
import html as _html
import os
import re

FORM_KINDS = {"value": "הערכת שווי", "contact": "צור קשר", "career": "קריירה"}
FIELD_LABELS = {"name": "שם", "phone": "טלפון", "address": "כתובת הנכס", "city": "עיר", "when": "מתי מתכננים למכור",
                "experience": "ניסיון בנדל\"ן", "message": "הודעה", "page": "עמוד"}
MAX_FEATURED = 6


def key_ok(given, expected) -> bool:
    return bool(expected) and bool(given) and hmac.compare_digest(str(given), str(expected))


def search_result(parsed, matches, hidden) -> dict:
    """תוצאות החיפוש החכם לאתר: רק מספרי מודעה של נכסים פעילים ולא מוסתרים — בלי שום פרט אישי."""
    keys = []
    for m in matches or []:
        row = m[1] if isinstance(m, (tuple, list)) else m
        lid = str(row.get("מספר מודעה", "") or "").strip()
        if not lid or lid in hidden or str(row.get("ירד מפרסום", "") or "").strip():
            continue
        if lid not in keys:
            keys.append(lid)
    return {"ok": True, "keys": keys[:200], "summary": str((parsed or {}).get("summary_he") or "")[:200]}


def form_email(kind, fields, office_name):
    """פנייה מהאתר → (נושא, HTML מוגן, טקסט)."""
    title = FORM_KINDS[kind]
    name = re.sub(r"\s+", " ", str(fields.get("name", "") or "")).strip()[:80]
    subject = "פנייה מהאתר — " + title + (" — " + name if name else "")
    rows = [(FIELD_LABELS[k], str(v or "")[:1500]) for k, v in fields.items()
            if k in FIELD_LABELS and str(v or "").strip()]
    text = "\n".join("%s: %s" % (l, v) for l, v in rows)
    html = ('<div dir="rtl" style="font-family:Arial,sans-serif;font-size:15px;color:#1E3A5F">'
            '<h2 style="margin:0 0 12px">' + _html.escape(subject) + '</h2><table cellpadding="6">' +
            "".join('<tr><td style="color:#6B7280">%s</td><td><b>%s</b></td></tr>'
                    % (_html.escape(l), _html.escape(v).replace("\n", "<br>")) for l, v in rows) +
            '</table><p style="color:#6B7280;font-size:12px">נשלח מהאתר של ' + _html.escape(office_name or "") +
            '</p></div>')
    return subject, html, text


def prop_flags(rows):
    """שורות website_settings → (מוסתרים:set, מומלצים:list לפי סדר העדכון)."""
    hidden, featured = set(), []
    for r in rows or []:
        if r.get("kind") != "prop":
            continue
        d = r.get("data") or {}
        k = str(r.get("key") or "")
        if d.get("hidden"):
            hidden.add(k)
        if d.get("featured") and k not in featured:
            featured.append(k)
    return hidden, featured


def can_edit_prop(sess, row, owns, is_dev) -> bool:
    """הסתר/מומלץ: מנהל ומפתח — כל נכס; סוכן — רק נכס שלו."""
    if not sess:
        return False
    if is_dev or sess.get("role") == "admin":
        return True
    try:
        return bool(owns(row, sess.get("name", ""), sess.get("_phones") or [sess.get("phone", "")]))
    except Exception:
        return False


def register_site(app, G, store=None):
    from flask import request, jsonify
    log = G.get("log")
    _store = {"s": store}

    def st():
        if _store["s"] is None:
            _store["s"] = SettingsStore(G.get("_sbdb"))
        return _store["s"]

    def _site_key_ok(body):
        return key_ok((body or {}).get("key", ""), (os.environ.get("SITE_KEY") or "").strip())

    @app.route("/site/api/search", methods=["POST"])
    def site_api_search():
        b = request.get_json(silent=True) or {}
        if not _site_key_ok(b):
            return jsonify({"ok": False}), 403
        q = re.sub(r"\s+", " ", str(b.get("q", "") or "")).strip()[:120]
        if not q:
            return jsonify({"ok": True, "keys": [], "summary": ""})
        try:
            parsed = G["_parse_props_query"](q) or {}
            matches = G["search_listings_in_sheet"](parsed) if parsed else []
            hidden, _ = prop_flags(st().all())
            return jsonify(search_result(parsed, matches, hidden))
        except Exception as e:
            if log: log.warning(f"site search: {e}")
            return jsonify({"ok": False})

    @app.route("/site/api/form", methods=["POST"])
    def site_api_form():
        b = request.get_json(silent=True) or {}
        if not _site_key_ok(b):
            return jsonify({"ok": False}), 403
        kind = str(b.get("kind", "") or "")
        if kind not in FORM_KINDS:
            return jsonify({"ok": False, "reason": "kind"}), 400
        raw = b.get("fields") if isinstance(b.get("fields"), dict) else {}
        fields = {str(k)[:20]: str(v or "")[:1500] for k, v in list(raw.items())[:15]}
        try:
            office = ""
            try:
                office = str(((G["_load_config"]() or {}).get("v2_office") or {}).get("name", "") or "")
            except Exception:
                office = ""
            subject, html, text = form_email(kind, fields, office or "המשרד")
            res = G["_report_send_email"](subject, html, text)
            ok = bool(res[0]) if isinstance(res, (tuple, list)) else bool(res)
            G["_log_activity"]("אתר", "site", "", "פנייה מהאתר — " + FORM_KINDS[kind],
                               (fields.get("name", "") + " · " + fields.get("page", "")).strip(" ·"))
            return jsonify({"ok": ok})
        except Exception as e:
            if log: log.warning(f"site form: {e}")
            return jsonify({"ok": False})

    # ---- הסתר / מומלץ באתר (כרטיסי הנכסים באפי) ----
    @app.route("/v2/api/site/state", methods=["GET"])
    def site_state():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        rows = st().all()
        hidden, featured = prop_flags(rows)
        return jsonify({"ok": True, "hidden": sorted(hidden), "featured": featured, "max_featured": MAX_FEATURED,
                        "available": bool(getattr(st(), "available", True))})

    @app.route("/v2/api/site/prop", methods=["POST"])
    def site_prop():
        s = G["_web_auth"]()
        if not s:
            return jsonify({"ok": False, "auth": False}), 401
        b = request.get_json(silent=True) or {}
        key = str(b.get("key", "") or "").strip()[:80]
        row = next((r for r in (G["fetch_sheet_rows"]() or []) if str(r.get("מספר מודעה", "") or "").strip() == key), None) if key else None
        if not row:
            return jsonify({"ok": False, "reason": "not_found"}), 404
        sess = dict(s)
        try:
            sess["_phones"] = [s.get("phone", "")] + list(G["_phones_for_name"](s.get("name", "")) or [])
        except Exception:
            sess["_phones"] = [s.get("phone", "")]
        is_dev = False
        try:
            is_dev = bool(G["_is_dev"](s.get("phone", ""))) or s.get("drole") == "developer"
        except Exception:
            pass
        if not can_edit_prop(sess, row, G["_agent_owns_row"], is_dev):
            return jsonify({"ok": False, "reason": "forbidden"}), 403
        rows = st().all()
        if not getattr(st(), "available", True):
            return jsonify({"ok": False, "reason": "no_table"})
        hidden, featured = prop_flags(rows)
        cur = {"hidden": key in hidden, "featured": key in featured}
        new = dict(cur)
        if "hidden" in b:
            new["hidden"] = bool(b.get("hidden"))
        if "featured" in b:
            new["featured"] = bool(b.get("featured"))
        if new["featured"] and not cur["featured"] and len(featured) >= MAX_FEATURED:
            return jsonify({"ok": False, "reason": "featured_full"})
        if not st().put("prop", key, new, s.get("name", "")):
            return jsonify({"ok": False, "reason": "save_failed"})
        acts = []
        if new["hidden"] != cur["hidden"]:
            acts.append("אתר — הסתרת נכס" if new["hidden"] else "אתר — הצגת נכס")
        if new["featured"] != cur["featured"]:
            acts.append("אתר — סימון מומלץ" if new["featured"] else "אתר — ביטול מומלץ")
        where = " ".join(str(row.get(k, "") or "") for k in ("כתובת", "עיר / ישוב")).strip()
        for a in acts:
            G["_log_activity"](s.get("name", ""), s.get("role", ""), s.get("phone", ""), a, (where + " · " + key).strip(" ·"))
        return jsonify({"ok": True, "hidden": new["hidden"], "featured": new["featured"]})


class SettingsStore:
    """website_settings ב-Supabase (שורה לכל kind+key). טבלה חסרה/כשל → available=False, all()=[]."""

    def __init__(self, sb):
        self.sb = sb
        self.available = True

    def all(self):
        sb = self.sb
        if not (sb and sb.enabled()):
            self.available = False
            return []
        try:
            import requests
            r = requests.get(sb.SUPABASE_URL + "/rest/v1/website_settings", headers=sb._headers(),
                             params={"office_id": "eq." + sb.SB_OFFICE_ID, "select": "kind,key,data"}, timeout=10)
            r.raise_for_status()
            self.available = True
            return r.json() or []
        except Exception:
            self.available = False
            return []

    def put(self, kind, key, data, by):
        sb = self.sb
        if not (sb and sb.enabled()):
            return False
        try:
            import requests
            from datetime import datetime, timezone
            r = requests.post(sb.SUPABASE_URL + "/rest/v1/website_settings?on_conflict=office_id,kind,key",
                              headers={**sb._headers(), "Content-Type": "application/json",
                                       "Prefer": "resolution=merge-duplicates,return=minimal"},
                              json={"office_id": sb.SB_OFFICE_ID, "kind": kind, "key": key, "data": data,
                                    "updated_by": str(by or "")[:80],
                                    "updated_at": datetime.now(timezone.utc).isoformat()}, timeout=10)
            return r.status_code < 300
        except Exception:
            return False
