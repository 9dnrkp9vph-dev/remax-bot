# tests/crm/test_crm_redesign.py — [10/11 אייל: 'כן, לבנות' על ההדמיה] תפריט צד מקובץ בכל דפי ה-CRM,
# לוח בקרה עם 'מחכה לטיפול' בראש, בריאות בשורה אחת, טלפונים 05X, תגית 'חייג חזרה' במקום כתובת, ציון כנקודות.
import os, sys, json, subprocess, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
os.environ["DISABLE_WARMER"] = "1"; os.environ["CRM_ALLOW_APP_TOKEN"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import effie_v2 as E

def fn(src, name):
    """גוף פונקציית JS בשם name מתוך מחרוזת HTML (התאמת סוגריים)."""
    i = src.index("function " + name + "(")
    j = src.index("{", i); d = 0
    for k in range(j, len(src)):
        d += {"{": 1, "}": -1}.get(src[k], 0)
        if d == 0:
            return src[i:k + 1]
    raise ValueError(name)

def node(code):
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)

# 1. תפריט הצד בכל דפי ה-CRM
for nm in ("_CRM_SCREEN_HTML", "_CRM_DASH_HTML", "_CRM_MKT_HTML", "_CRM_PARALLEL_HTML", "_CRM_ACCESS_HTML"):
    ck('id="crmNav"' in getattr(E, nm), nm + " has side nav")
NAV = E._CRM_NAV_HTML
out = node(fn(NAV, "navGroups") + """
var g = navGroups([['calls','לוג שיחות'],['buyers','קונים'],['props','נכסים'],['team','צוות'],['xyz','משהו']], {dashboard:true, access:true}, 'calls');
console.log(JSON.stringify(g));""")
titles = [x[0] for x in out]
ck(titles == ["היום", "לקוחות", "נכסים", "מערכת"], titles)
today = [i[0] for i in out[0][1]]
ck(today[:2] == ["dashboard", "calls"], today)
ck("access" in [i[0] for i in out[3][1]] and "xyz" in [i[0] for i in out[3][1]], out[3])
ck("marketing" in [i[0] for i in out[2][1]], out[2])

# 2. מסך מודול: טלפונים, חייג חזרה, ציון
S = E._CRM_SCREEN_HTML
out = node(fn(S, "esc") + fn(S, "fmtPh") + fn(S, "fdate") + fn(S, "stCls") + fn(S, "cell") + """
console.log(JSON.stringify([fmtPh('528123007'), fmtPh('97948803'), fmtPh('0528123007'), fmtPh('972528123007'),
  cell({s:'https://maskyoo.com/zipper_993/api/public.php?service=click2call_link&x=1'}, ['s','סיכום','long']),
  cell({s:'⚠️ *שים לב: המתקשר הוא מתווך* - רימקס סמארט'}, ['s','סיכום','long']),
  cell({sc:3}, ['sc','ציון','score'])]));""")
ck(out[0] == "052-8123007" and out[1] == "09-7948803" and out[2] == "052-8123007" and out[3] == "052-8123007", out[:4])
ck("חייג חזרה" in out[4] and "maskyoo.com/zipper" not in out[4].split('href=')[0], out[4])
ck("מתווך" in out[5] and "chipw" in out[5] and "שים לב" not in out[5], out[5])
ck(out[6].count('class="dt f"') == 3 and out[6].count('class="dt"') == 2, out[6])
ck("view" in fn(S, "initFromUrl"), "screen reads ?view=")

# 3. לוח הבקרה
D = E._CRM_DASH_HTML
out = node(fn(D, "esc") + fn(D, "ago") + fn(D, "healthLine") + fn(D, "sigGroups") + """
var H=[{label:'שיחות',status:'ok',last:Date.now()/1000-60},{label:'פרסום ברשתות',status:'ok',last:'2026-11-09T10:00:00+00:00'},{label:'חתימות',status:'bad',last:null}];
console.log(JSON.stringify([ago('2026-11-09T10:00:00+00:00'), ago(null), healthLine(H), healthLine(H.slice(0,2)),
  sigGroups([{client:'מיכאל אשל',agent:'רויטל גל',type:'מוכר'},{client:'מיכאל אשל',agent:'רויטל גל',type:'בלעדיות'},{client:'מיכאל אשל',agent:'רויטל גל',type:'מוכר'},{client:'דן',agent:'אלי',type:'קונים'}])]));""")
ck("NaN" not in out[0] and out[0].startswith("לפני"), out[0])
ck(out[1] == "—", out[1])
ck("חתימות" in out[2] and "תקלה" in out[2], out[2])
ck("תקינים" in out[3] and "2" in out[3], out[3])
ck(len(out[4]) == 2 and out[4][0]["types"] == ["מוכר", "בלעדיות"] and out[4][0]["n"] == 3, out[4])
for name in ("inboxCard", "ledger"):
    ck(("function " + name + "(") in D, name)

# 4. נקודת קצה לתפריט
import app as A
A._web_auth = lambda: {"phone": "505709865", "name": "אייל", "role": "admin"}
A._is_dev = lambda p: True
j = A.app.test_client().get("/v2/api/crm/nav").get_json()
ck(j and j.get("ok") and any(m[0] == "calls" for m in j["modules"]) and "me" in j, j)
print("crm_redesign OK", n)
