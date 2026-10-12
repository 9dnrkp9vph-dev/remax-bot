"""[DEALS-SYNC 12/10] לקוח Dropbox מינימלי (HTTP API v2) — רשימת תיקייה והורדה, refresh token מ-env.
המפתחות לא נכתבים ללוג. http מוזרק לבדיקות."""
import os, json, time
import requests

_TOK = {"v": "", "exp": 0}


def configured():
    return all((os.environ.get(k) or "").strip() for k in ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"))


def access_token(http=requests):
    if _TOK["v"] and time.time() < _TOK["exp"] - 60:
        return _TOK["v"]
    r = http.post("https://api.dropboxapi.com/oauth2/token", timeout=20, data={
        "grant_type": "refresh_token", "refresh_token": os.environ.get("DROPBOX_REFRESH_TOKEN", "").strip(),
        "client_id": os.environ.get("DROPBOX_APP_KEY", "").strip(),
        "client_secret": os.environ.get("DROPBOX_APP_SECRET", "").strip()})
    r.raise_for_status()
    j = r.json()
    _TOK.update(v=j["access_token"], exp=time.time() + int(j.get("expires_in", 14400)))
    return _TOK["v"]


def list_folder(path, http=requests):
    r = http.post("https://api.dropboxapi.com/2/files/list_folder", timeout=30,
                  headers={"Authorization": "Bearer " + access_token(http), "Content-Type": "application/json"},
                  json={"path": path, "recursive": False})
    r.raise_for_status()
    out = []
    for e in (r.json() or {}).get("entries", []):
        if e.get(".tag") == "file":
            out.append({"name": e["name"], "path": e["path_display"], "rev": e.get("rev", ""),
                        "server_modified": e.get("server_modified", ""), "size": e.get("size", 0)})
    return out


def download(path, http=requests):
    r = http.post("https://content.dropboxapi.com/2/files/download", timeout=120,
                  headers={"Authorization": "Bearer " + access_token(http),
                           "Dropbox-API-Arg": json.dumps({"path": path}, ensure_ascii=True)})
    r.raise_for_status()
    meta = json.loads(r.headers.get("Dropbox-API-Result") or "{}")
    return r.content, meta.get("rev", "")
