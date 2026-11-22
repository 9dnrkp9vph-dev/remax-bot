# -*- coding: utf-8 -*-
"""tools/run_tests.py — מריץ את כל הבדיקות שב-tests/ ומחזיר קוד יציאה אחד (0 = הכל עבר).

למה לא pytest: רוב הבדיקות כאן הן סקריפטים שרצים מלמעלה למטה ומסיימים ב-sys.exit / SystemExit,
ו-pytest קורס עליהן באיסוף. לכן כל קובץ test_*.py רץ כתהליך נפרד, בדיוק כמו שמריצים אותו ביד:
    python3 tests/<תיקייה>/test_<שם>.py

שימוש:
    python3 tools/run_tests.py              # הכל
    python3 tools/run_tests.py goals meets  # רק קבצים שהנתיב שלהם מכיל אחת המילים
    python3 tools/run_tests.py -j 1         # בלי מקביליות

הסקריפט לא נוגע בקוד האפליקציה ולא רץ בשרת — רק במחשב המפתח וב-GitHub Actions.
בדיקה שנכשלה בריצה המקבילית רצה שוב לבד, כדי שהתנגשות בין שתי בדיקות לא תיראה כמו תקלה בקוד.
"""
import concurrent.futures
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT = 180   # שניות לקובץ בדיקה

# ערכי דמה: app.py דורש שהמשתנים האלה יהיו קיימים בזמן הייבוא. אין כאן שום סוד אמיתי,
# וערך שכבר הוגדר בסביבה לא נדרס.
DUMMY_ENV = {
    "MAYTAPI_TOKEN": "dummy",
    "MAYTAPI_PHONE_ID": "1",
    "MAYTAPI_PRODUCT_ID": "1",
    "CLAUDE_API_KEY": "dummy",
    # הבדיקות נכתבו ורצות על מחשב בשעון ישראל, ואחת מהן (tests/signing/test_last_form_budget.py) תלויה בזה:
    # בשעון UTC (GitHub Actions) היא נכשלת בהפרש של 3 שעות. קובעים אזור זמן אחיד כדי שהתוצאה תהיה זהה בכל מקום.
    "TZ": "Asia/Jerusalem",
}


def find_tests(words):
    out = []
    for d, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                rel = os.path.relpath(os.path.join(d, f), ROOT)
                if not words or any(w in rel for w in words):
                    out.append(rel)
    return sorted(out)


def run_one(rel):
    env = dict(os.environ)
    for k, v in DUMMY_ENV.items():
        env.setdefault(k, v)
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, rel], cwd=ROOT, env=env, timeout=TIMEOUT,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        code, out = p.returncode, p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code, out = -1, (e.stdout or b"").decode("utf-8", "replace") + "\n[timeout after %ds]" % TIMEOUT
    return rel, code, out, time.time() - t0


def main(argv):
    jobs, words = 4, []
    it = iter(argv)
    for a in it:
        if a == "-j":
            jobs = max(1, int(next(it, "1")))
        else:
            words.append(a)
    tests = find_tests(words)
    if not tests:
        print("no test files found")
        return 1
    t0 = time.time()
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for rel, code, out, _dt in ex.map(run_one, tests):
            if code != 0:
                failed.append(rel)
    # ריצה חוזרת, אחד-אחד, רק למה שנכשל
    real = []
    for rel in failed:
        _rel, code, out, _dt = run_one(rel)
        if code != 0:
            real.append((rel, code, out))
        else:
            print("flaky (passed when run alone): %s" % rel)
    for rel, code, out in real:
        print("\n" + "=" * 78)
        print("FAILED (exit %s): %s" % (code, rel))
        print("-" * 78)
        print("\n".join(out.strip().splitlines()[-25:]))
    print("\n%d test files · %d passed · %d failed · %.0fs" % (
        len(tests), len(tests) - len(real), len(real), time.time() - t0))
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
