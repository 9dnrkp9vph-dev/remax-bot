"""מפיק refresh token לאפליקציית Dropbox של אפי — רץ על המחשב של אייל, פעם אחת.
App key: הקלדה רגילה. App secret וקוד האישור: הקלדה מוסתרת. ה-refresh token מועתק ללוח (pbcopy) — לא מודפס."""
import getpass, subprocess, webbrowser, urllib.parse, requests


def main():
    key = input("App key: ").strip()
    secret = getpass.getpass("App secret: ").strip()
    url = "https://www.dropbox.com/oauth2/authorize?" + urllib.parse.urlencode(
        {"client_id": key, "response_type": "code", "token_access_type": "offline"})
    print("נפתח דפדפן לאישור. אחרי 'Allow' — העתק את הקוד שמוצג.")
    webbrowser.open(url)
    code = getpass.getpass("הדבק את הקוד: ").strip()
    r = requests.post("https://api.dropboxapi.com/oauth2/token", timeout=20,
                      data={"code": code, "grant_type": "authorization_code", "client_id": key, "client_secret": secret})
    j = r.json() if r.ok else {}
    rt = j.get("refresh_token", "")
    if not rt:
        print("לא התקבל טוקן (%s). נסה שוב." % r.status_code)
        return
    subprocess.run(["pbcopy"], input=rt.encode(), check=True)
    print("ה-refresh token הועתק ללוח. הדבק אותו ב-Render כ-DROPBOX_REFRESH_TOKEN.")
    # בדיקה: האם רואים את שלוש תיקיות 2026 (בלי להדפיס שום מפתח)
    import os, sys, datetime
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    os.environ.update(DROPBOX_APP_KEY=key, DROPBOX_APP_SECRET=secret, DROPBOX_REFRESH_TOKEN=rt)
    import dropbox_api as X
    year = datetime.date.today().year
    dirs = {"ביאליק": "/הפרלמנט/אייל/מעקב עסקאות/%d", "מוצקין": "/הפרלמנט/אוהד/מעקב עסקאות מוצקין/%d",
            "קרית ים": "/הפרלמנט/מעקב עסקאות קרית ים/%d"}
    print("\nבדיקת גישה לתיקיות %d:" % year)
    for name, path in dirs.items():
        try:
            fs = [e for e in X.list_folder(path % year) if e["name"].lower().endswith((".xlsx", ".xlsm", ".xls"))
                  and not e["name"].startswith("~$") and ("מעקב" in e["name"] or "עסקאות" in e["name"])]
            last = max(fs, key=lambda e: e["server_modified"]) if fs else None
            print("  %s: %s" % (name, ("ייקרא: " + last["name"]) if last else "אין קובץ מעקב"))
        except Exception as ex:
            print("  %s: אין גישה (%s)" % (name, type(ex).__name__))


if __name__ == "__main__":
    main()
